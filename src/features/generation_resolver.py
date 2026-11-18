import logging
from typing import Any, Dict, List, Optional, Tuple

from src.domain.entities import PokemonField
from src.settings import SourceConfig

logger = logging.getLogger(__name__)

_ROMAN_NUMERALS: Dict[str, int] = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
}
_STAT_NAMES: Dict[str, str] = {
    "hp": PokemonField.HP.value,
    "attack": PokemonField.ATTACK.value,
    "defense": PokemonField.DEFENSE.value,
    "special-attack": PokemonField.SPECIAL_ATTACK.value,
    "special-defense": PokemonField.SPECIAL_DEFENSE.value,
    "speed": PokemonField.SPEED.value,
}


class GenerationResolver:
    """
    Interface for reconstructing types, base statistics, and type relations as they were in the generation under study, so that later
    changes recorded by the data source (Fairy type, stat buffs) do not contaminate the dataset.

    Attributes:
        config (SourceConfig): Parameters of the game under study.

    Methods:
        _generation_index(name: str) -> int:
            Returns the numeric index of a generation name.

        _applicable_past_entry(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            Returns the oldest historical entry still valid in the generation under study.

        types_of(pokemon: Dict[str, Any]) -> Tuple[str, ...]:
            Returns the types of the Pokémon in the generation under study.

        stats_of(pokemon: Dict[str, Any]) -> Dict[str, int]:
            Returns the base statistics of the Pokémon in the generation under study.


        damage_relations(type_document: Dict[str, Any]) -> Dict[str, List[str]]:
            Returns the damage relations of the type in the generation under study.

        exists_in_generation(type_document: Dict[str, Any]) -> bool:
            Returns whether the type exists in the generation under study.
    """

    def __init__(self, config: SourceConfig) -> None:
        self.config: SourceConfig = config
        logger.info("Generation resolver initialization completed.")

    def _generation_index(self, name: str) -> int:
        return _ROMAN_NUMERALS[name.replace("generation-", "")]

    def _applicable_past_entry(self, entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        valid = [
            entry for entry in entries
            if self._generation_index(entry["generation"]["name"]) >= self.config.generation_index
        ]
        if not valid:
            return None
        return min(valid, key=lambda entry: self._generation_index(entry["generation"]["name"]))

    def types_of(self, pokemon: Dict[str, Any]) -> Tuple[str, ...]:
        past_entry = self._applicable_past_entry(pokemon.get("past_types", []))
        slots = past_entry["types"] if past_entry is not None else pokemon["types"]
        return tuple(slot["type"]["name"] for slot in sorted(slots, key=lambda slot: slot["slot"]))

    def stats_of(self, pokemon: Dict[str, Any]) -> Dict[str, int]:
        stats = {_STAT_NAMES[entry["stat"]["name"]]: entry["base_stat"] for entry in pokemon["stats"]}
        past_entry = self._applicable_past_entry(pokemon.get("past_stats", []))
        if past_entry is not None:
            for entry in past_entry["stats"]:
                if entry["stat"]["name"] in _STAT_NAMES:
                    stats[_STAT_NAMES[entry["stat"]["name"]]] = entry["base_stat"]
        return stats


    def damage_relations(self, type_document: Dict[str, Any]) -> Dict[str, List[str]]:
        past_entry = self._applicable_past_entry(type_document.get("past_damage_relations", []))
        relations = past_entry["damage_relations"] if past_entry is not None else type_document["damage_relations"]
        return {key: [entry["name"] for entry in values] for key, values in relations.items()}

    def exists_in_generation(self, type_document: Dict[str, Any]) -> bool:
        if type_document.get("generation") is None or not type_document.get("pokemon"):
            return False
        return self._generation_index(type_document["generation"]["name"]) <= self.config.generation_index
