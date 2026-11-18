import logging
import math
from typing import Dict, Sequence, Tuple

from src.features.generation_resolver import GenerationResolver

logger = logging.getLogger(__name__)

_RELATION_MULTIPLIERS: Dict[str, float] = {
    "double_damage_to": 2.0,
    "half_damage_to": 0.5,
    "no_damage_to": 0.0,
}
_PHYSICAL_TYPES: Tuple[str, ...] = (
    "normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost", "steel",
)


class TypeChart:
    """
    Interface for the type effectiveness chart of the generation under study,
    together with the third-generation rule assigning the physical or special
    category to a move from its type.

    Attributes:
        type_names (Tuple[str, ...]): Types existing in the generation under study.
        _multipliers (Dict[Tuple[str, str], float]): Effectiveness of each attacking type on each defending type.

    Methods:
        effectiveness(attacking_type: str, defending_types: Sequence[str]) -> float:
            Returns the damage multiplier of an attacking type on a combination of defending types.


        is_physical(move_type: str) -> bool:
            Returns whether moves of the type use the physical statistics.
    """

    def __init__(self, resolver: GenerationResolver, type_documents: Dict[str, Dict]) -> None:
        existing = sorted(name for name, document in type_documents.items() if resolver.exists_in_generation(document))
        if not existing:
            raise ValueError("No type exists in the generation under study.")
        multipliers: Dict[Tuple[str, str], float] = {}
        for attacking_type in existing:
            relations = resolver.damage_relations(type_documents[attacking_type])
            for defending_type in existing:
                multipliers[(attacking_type, defending_type)] = 1.0
            for relation, factor in _RELATION_MULTIPLIERS.items():
                for defending_type in relations.get(relation, []):
                    if defending_type in existing:
                        multipliers[(attacking_type, defending_type)] = factor
        self.type_names: Tuple[str, ...] = tuple(existing)
        self._multipliers: Dict[Tuple[str, str], float] = multipliers
        logger.info(f"Type chart initialization completed. Types: {len(self.type_names)}.")

    def effectiveness(self, attacking_type: str, defending_types: Sequence[str]) -> float:
        return math.prod(self._multipliers[(attacking_type, defending_type)] for defending_type in defending_types)

    def is_physical(self, move_type: str) -> bool:
        return move_type in _PHYSICAL_TYPES
