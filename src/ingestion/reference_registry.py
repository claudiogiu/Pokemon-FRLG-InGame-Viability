import logging
import tomllib
from pathlib import Path
from types import MappingProxyType
from typing import Optional

from src.domain.entities import GameReference, PlaythroughReference
from src.settings import CONFIG_TOML_PATH

logger = logging.getLogger(__name__)


class GameReferenceRegistry:
    """
    Interface for loading the curated game reference sections of the
    configuration document, so that progression tables and the Smogon tiers are declared in the configuration instead of the source code.

    Attributes:
        reference_path (Path): Filesystem location of the game reference TOML document.

    Methods:
        load() -> GameReference:
            Reads, validates, and returns the game reference.
    """

    def __init__(self, reference_path: Optional[Path] = None) -> None:
        self.reference_path: Path = reference_path or CONFIG_TOML_PATH

    def load(self) -> GameReference:
        if not self.reference_path.is_file():
            raise ValueError(f"The game reference document does not exist: {self.reference_path}.")
        logger.info("Starting loading of the game reference.")
        with self.reference_path.open("rb") as f:
            raw = tomllib.load(f)
        reference = GameReference(
            location_badges=MappingProxyType(dict(raw["location_badges"])),
            method_badges=MappingProxyType(dict(raw["method_badges"])),
            item_badges=MappingProxyType(dict(raw["item_badges"])),
            smogon_tiers=MappingProxyType(dict(raw["smogon_tiers"])),
            tier_scores=MappingProxyType(dict(raw["tier_scores"])),
        )
        logger.info(
            f"Game reference successfully loaded. "
            f"Locations: {len(reference.location_badges)}. "
            f"Smogon tiers: {len(reference.smogon_tiers)}. "
        )
        return reference


class PlaythroughReferenceRegistry:
    """
    Interface for loading the curated playthrough sections of the
    configuration document, so that the major battles, the progression of machines and tutors, and the battle
    rules of the simulation are declared in the configuration.

    Attributes:
        reference_path (Path): Filesystem location of the playthrough reference TOML document.

    Methods:
        load() -> PlaythroughReference:
            Reads, validates, and returns the playthrough reference.
    """

    def __init__(self, reference_path: Optional[Path] = None) -> None:
        self.reference_path: Path = reference_path or CONFIG_TOML_PATH

    def load(self) -> PlaythroughReference:
        if not self.reference_path.is_file():
            raise ValueError(f"The playthrough reference document does not exist: {self.reference_path}.")
        logger.info("Starting loading of the playthrough reference.")
        with self.reference_path.open("rb") as f:
            raw = tomllib.load(f)
        effects = raw["move_effects"]
        abilities = raw["abilities"]
        reference = PlaythroughReference(
            bosses=tuple(
                sorted(
                    (
                        (boss["name"], boss["label"], int(boss["badges_before"]), tuple(boss["parties"]), bool(boss.get("league", False)))
                        for boss in raw["bosses"]
                    ),
                    key=lambda boss: boss[2],
                )
            ),
            machine_badges=MappingProxyType(dict(raw["tm_badges"])),
            tutor_badges=MappingProxyType(dict(raw["tutor_badges"])),
            excluded_effects=tuple(effects["excluded"]),
            level_damage_effects=tuple(effects["level_damage"]),
            fixed_damage=MappingProxyType(dict(effects["fixed_damage"])),
            fixed_power=MappingProxyType(dict(effects["fixed_power"])),
            power_multipliers=MappingProxyType(dict(effects["power_multipliers"])),
            immunity_abilities=MappingProxyType(dict(abilities["immunities"])),
            halving_abilities=MappingProxyType({key: tuple(value) for key, value in abilities["halved_incoming"].items()}),
            intimidating_abilities=tuple(abilities["attack_drop_on_entry"]),
            growth_experience=MappingProxyType(dict(raw["growth_experience_level_50"])),
        )
        if not reference.bosses:
            raise ValueError("The playthrough reference declares no major battle.")
        logger.info(
            f"Playthrough reference successfully loaded. "
            f"Major battles: {len(reference.bosses)}. "
            f"Machines: {len(reference.machine_badges)}. "
            f"Tutors: {len(reference.tutor_badges)}. "
        )
        return reference
