import logging
import math
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from src.domain.entities import GameMove, PlaythroughReference, SpeciesRecord
from src.features.type_chart import TypeChart
from src.settings import CampaignConfig

logger = logging.getLogger(__name__)

_LEVEL_DIVISOR: int = 5
_LEVEL_OFFSET: int = 2
_DAMAGE_DIVISOR: int = 50
_DAMAGE_OFFSET: int = 2
_STAT_SCALE: int = 100
_STAT_OFFSET: int = 5
_HP_OFFSET: int = 10
_EFFORT_DIVISOR: int = 4
_PERCENT: float = 100.0
_HALVING_FACTOR: float = 0.5
_STAGE_BASE: float = 2.0
_NO_STAGES: Mapping[str, int] = {}


@dataclass(frozen=True)
class Combatant:
    """
    Interface for a Pokémon ready to battle, with its level, individual
    values, ability, and usable moves.

    Attributes:
        record (SpeciesRecord): Cartridge data of the species.
        level (int): Battle level.
        individual_value (int): Individual value applied to every statistic.
        effort_value (int): Effort value applied to every statistic.
        ability (Optional[str]): Active ability, if any.
        moves (Tuple[GameMove, ...]): Moves usable in battle.

    Methods:
        None.
    """

    record: SpeciesRecord
    level: int
    individual_value: int
    effort_value: int
    ability: Optional[str]
    moves: Tuple[GameMove, ...]


class DamageCalculator:
    """
    Interface for computing statistics and expected damage with the
    third-generation formulas, including stat stages, so that duels are
    resolved with the arithmetic of the cartridge under neutral natures and
    averaged random factors.

    Attributes:
        config (CampaignConfig): Assumptions of the simulation.
        reference (PlaythroughReference): Move effect and ability rules.
        chart (TypeChart): Type chart of the generation.

    Methods:
        stats(combatant: Combatant) -> Dict[str, int]:
            Returns the battle statistics of the combatant.

        stage_multiplier(stage: int) -> float:
            Returns the third-generation multiplier of a stat stage.

        _effective_power(move: GameMove) -> float:
            Returns the power used by the damage formula, or zero for unsupported moves.

        expected_damage(attacker: Combatant, defender: Combatant, move: GameMove, attacker_intimidated: bool, attacker_stages: Mapping[str, int], defender_stages: Mapping[str, int]) -> float:
            Returns the accuracy-weighted average damage of one use of the move.

        best_damage(attacker: Combatant, defender: Combatant, attacker_intimidated: bool, attacker_stages: Mapping[str, int], defender_stages: Mapping[str, int]) -> Tuple[float, str]:
            Returns the highest expected damage among the attacker moves and the move achieving it.
    """

    def __init__(self, config: CampaignConfig, reference: PlaythroughReference, chart: TypeChart) -> None:
        self.config: CampaignConfig = config
        self.reference: PlaythroughReference = reference
        self.chart: TypeChart = chart
        logger.info("Damage calculator initialization completed.")

    def stats(self, combatant: Combatant) -> Dict[str, int]:
        effort = combatant.effort_value // _EFFORT_DIVISOR
        computed: Dict[str, int] = {}
        for name, base in combatant.record.stats.items():
            core = (2 * base + combatant.individual_value + effort) * combatant.level // _STAT_SCALE
            computed[name] = core + combatant.level + _HP_OFFSET if name == "hp" else core + _STAT_OFFSET
        return computed

    def stage_multiplier(self, stage: int) -> float:
        if stage >= 0:
            return (_STAGE_BASE + stage) / _STAGE_BASE
        return _STAGE_BASE / (_STAGE_BASE - stage)

    def _effective_power(self, move: GameMove) -> float:
        if move.effect in self.reference.excluded_effects:
            return 0.0
        power = float(self.reference.fixed_power.get(move.effect, move.power))
        return power * float(self.reference.power_multipliers.get(move.effect, 1.0))

    def expected_damage(
        self,
        attacker: Combatant,
        defender: Combatant,
        move: GameMove,
        attacker_intimidated: bool,
        attacker_stages: Mapping[str, int] = _NO_STAGES,
        defender_stages: Mapping[str, int] = _NO_STAGES,
    ) -> float:
        if move.move_type not in self.chart.type_names or move.effect in self.reference.excluded_effects:
            return 0.0
        effectiveness = self.chart.effectiveness(move.move_type, defender.record.types)
        if self.reference.immunity_abilities.get(defender.ability) == move.move_type:
            effectiveness = 0.0
        if effectiveness == 0.0:
            return 0.0
        hit_chance = move.accuracy / _PERCENT if move.accuracy > 0 else 1.0
        if move.effect in self.reference.level_damage_effects:
            return attacker.level * hit_chance
        if move.effect in self.reference.fixed_damage:
            return float(self.reference.fixed_damage[move.effect]) * hit_chance
        power = self._effective_power(move)
        if power <= 1.0:
            return 0.0
        attacker_stats, defender_stats = self.stats(attacker), self.stats(defender)
        physical = self.chart.is_physical(move.move_type)
        attack_name = "attack" if physical else "special_attack"
        defense_name = "defense" if physical else "special_defense"
        attack = attacker_stats[attack_name] * self.stage_multiplier(attacker_stages.get(attack_name, 0))
        defense = defender_stats[defense_name] * self.stage_multiplier(defender_stages.get(defense_name, 0))
        if physical and attacker_intimidated:
            attack *= self.config.intimidate_multiplier
        if move.move_type in self.reference.halving_abilities.get(defender.ability, ()):
            attack *= _HALVING_FACTOR
        level_factor = 2 * attacker.level // _LEVEL_DIVISOR + _LEVEL_OFFSET
        base = math.floor(math.floor(level_factor * power * attack / defense) / _DAMAGE_DIVISOR) + _DAMAGE_OFFSET
        stab = self.config.stab_multiplier if move.move_type in attacker.record.types else 1.0
        return base * stab * effectiveness * self.config.damage_roll_mean * hit_chance

    def best_damage(
        self,
        attacker: Combatant,
        defender: Combatant,
        attacker_intimidated: bool,
        attacker_stages: Mapping[str, int] = _NO_STAGES,
        defender_stages: Mapping[str, int] = _NO_STAGES,
    ) -> Tuple[float, str]:
        best: Tuple[float, str] = (0.0, "")
        for move in attacker.moves:
            damage = self.expected_damage(attacker, defender, move, attacker_intimidated, attacker_stages, defender_stages)
            if damage > best[0]:
                best = (damage, move.name)
        return best
