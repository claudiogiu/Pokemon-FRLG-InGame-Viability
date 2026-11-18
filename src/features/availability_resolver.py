import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.domain.entities import GameReference
from src.settings import AcquisitionConfig, SourceConfig

logger = logging.getLogger(__name__)

_UNREACHABLE_BADGES: int = 99
_UNREACHABLE_LEVEL: int = 100


@dataclass(frozen=True)
class Acquisition:
    """
    Interface for the earliest way of obtaining a species in the game under
    study, expressed as progression and level.

    Attributes:
        badges_required (int): Badges owned when the species first becomes obtainable, nine meaning after the Champion.
        obtain_level (int): Level at which the species is first obtained.
        requires_trade (bool): Whether obtaining the species requires a trade evolution.
        effort (int): Ordinal effort of the acquisition, from encounter rate, Safari Zone, Sevii Islands, trades, and Game Corner prices.
        route (str): Short description of the acquisition route.

    Methods:
        None.
    """

    badges_required: int
    obtain_level: int
    requires_trade: bool
    effort: int
    route: str


@dataclass(frozen=True)
class EvolutionLink:
    """
    Interface for the evolution step leading to a species from its pre-evolution.

    Attributes:
        parent (str): Name of the pre-evolution.
        trigger (str): Evolution trigger as named by the data source.
        minimum_level (Optional[int]): Level required by a level-up evolution.
        item (Optional[str]): Item required by an item evolution.

    Methods:
        None.
    """

    parent: str
    trigger: str
    minimum_level: Optional[int]
    item: Optional[str]


class AvailabilityResolver:
    """
    Interface for determining when each species becomes obtainable in the
    game under study, combining wild and gift encounters with evolutions, so
    that availability can be treated as a measurable feature.

    Attributes:
        config (SourceConfig): Parameters of the game under study.
        acquisition (AcquisitionConfig): Rules of the acquisition effort.
        reference (GameReference): Curated progression tables.
        _links (Dict[str, EvolutionLink]): Evolution step leading to each species.
        _children (Dict[str, List[str]]): Evolutions of each species.
        _cache (Dict[str, Acquisition]): Already resolved acquisitions.

    Methods:
        _walk_chain(node: Dict[str, Any]) -> None:
            Records the evolution links of a chain node and of its descendants.

        _effort(species: str, method: str, location: str, chance: int) -> int:
            Returns the ordinal acquisition effort of one encounter.

        _encounter_acquisition(species: str, encounters: List[Dict[str, Any]]) -> Optional[Acquisition]:
            Returns the earliest and easiest wild or gift acquisition of a species, if any.

        evolutions_of(species: str) -> List[str]:
            Returns the direct evolutions of the species.

        parent_of(species: str) -> Optional[str]:
            Returns the direct pre-evolution of the species, if any.

        resolve(species: str, encounters_by_species: Dict[str, List[Dict[str, Any]]]) -> Acquisition:
            Returns the earliest acquisition of the species.
    """

    def __init__(
        self, config: SourceConfig, acquisition: AcquisitionConfig, reference: GameReference, chains: List[Dict[str, Any]]
    ) -> None:
        self.config: SourceConfig = config
        self.acquisition: AcquisitionConfig = acquisition
        self.reference: GameReference = reference
        self._links: Dict[str, EvolutionLink] = {}
        self._children: Dict[str, List[str]] = {}
        self._cache: Dict[str, Acquisition] = {}
        for chain in chains:
            self._walk_chain(chain["chain"])
        logger.info(f"Availability resolver initialization completed. Evolution links: {len(self._links)}.")

    def _walk_chain(self, node: Dict[str, Any]) -> None:
        parent = node["species"]["name"]
        self._children.setdefault(parent, [])
        for child in node["evolves_to"]:
            name = child["species"]["name"]
            details = child["evolution_details"]
            detail = details[0] if details else {}
            self._children[parent].append(name)
            self._links[name] = EvolutionLink(
                parent=parent,
                trigger=detail.get("trigger", {}).get("name", "unknown") if detail else "unknown",
                minimum_level=detail.get("min_level") if detail else None,
                item=detail["item"]["name"] if detail and detail.get("item") else None,
            )
            self._walk_chain(child)

    def _effort(self, species: str, method: str, location: str, chance: int) -> int:
        rules = self.acquisition
        if location == rules.prize_corner_location:
            coins = rules.prize_corner_coins.get(species, 0)
            effort = sum(1 for threshold in rules.coin_thresholds if coins >= threshold)
        elif method == "npc-trade":
            effort = rules.npc_trade_effort
        elif method in ("gift", "only-one", "pokeflute", "static", "gift-egg"):
            effort = 0
        else:
            effort = sum(1 for threshold in rules.chance_thresholds if chance < threshold)
        if location.startswith(rules.safari_prefix):
            effort += rules.safari_penalty
        if self.reference.location_badges.get(location) == rules.sevii_badges:
            effort += rules.sevii_penalty
        return min(effort, rules.maximum_effort)

    def _encounter_acquisition(self, species: str, encounters: List[Dict[str, Any]]) -> Optional[Acquisition]:
        candidates: List[Tuple[int, int, int, str]] = []
        for encounter in encounters:
            location = encounter["location_area"]["name"]
            for version_detail in encounter["version_details"]:
                if version_detail["version"]["name"] not in self.config.versions:
                    continue
                if location not in self.reference.location_badges:
                    logger.warning(f"Location area missing from the game reference. Location: {location}.")
                    continue
                for detail in version_detail["encounter_details"]:
                    method = detail["method"]["name"]
                    badges = max(
                        self.reference.location_badges[location],
                        self.reference.method_badges.get(method, 0),
                    )
                    effort = self._effort(species, method, location, int(detail.get("chance") or 0))
                    candidates.append((badges, effort, detail["min_level"], f"{method} at {location}"))
        if not candidates:
            return None
        badges, effort, level, route = min(candidates)
        return Acquisition(badges_required=badges, obtain_level=level, requires_trade=False, effort=effort, route=route)

    def evolutions_of(self, species: str) -> List[str]:
        return list(self._children.get(species, []))

    def parent_of(self, species: str) -> Optional[str]:
        link = self._links.get(species)
        return link.parent if link is not None else None

    def resolve(self, species: str, encounters_by_species: Dict[str, List[Dict[str, Any]]]) -> Acquisition:
        if species in self._cache:
            return self._cache[species]
        options: List[Acquisition] = []
        direct = self._encounter_acquisition(species, encounters_by_species.get(species, []))
        if direct is not None:
            options.append(direct)
        link = self._links.get(species)
        if link is not None and link.parent in encounters_by_species:
            parent = self.resolve(link.parent, encounters_by_species)
            badges, level, trade = parent.badges_required, parent.obtain_level, parent.requires_trade
            if link.trigger == "level-up" and link.minimum_level is not None:
                level = max(level, link.minimum_level)
            elif link.trigger == "use-item" and link.item is not None:
                badges = max(badges, self.reference.item_badges.get(link.item, _UNREACHABLE_BADGES))
            elif link.trigger == "trade":
                trade = True
            options.append(
                Acquisition(
                    badges_required=badges,
                    obtain_level=level,
                    requires_trade=trade,
                    effort=parent.effort,
                    route=f"{link.trigger} from {link.parent}",
                )
            )
        if not options:
            acquisition = Acquisition(_UNREACHABLE_BADGES, _UNREACHABLE_LEVEL, False, self.acquisition.maximum_effort, "unobtainable")
        else:
            acquisition = min(options, key=lambda option: (option.badges_required, option.effort, option.obtain_level))
        self._cache[species] = acquisition
        return acquisition
