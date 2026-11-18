import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Tuple

from src.domain.entities import PlaythroughReference
from src.settings import CampaignConfig, StrategyConfig
from src.simulation.damage_calculator import Combatant, DamageCalculator

logger = logging.getLogger(__name__)

_MAXIMUM_STAGE: int = 6
_DIRECT_PLAN: str = "direct"
_PERCENT: float = 100.0


@dataclass(frozen=True)
class Plan:
    """
    Interface for a line of play of the player in a duel: preparatory turns
    followed by repeated use of the most damaging move.

    Attributes:
        name (str): Name of the plan, the preparatory move or direct attack.
        preparation_turns (int): Turns spent before attacking.
        player_stages (Mapping[str, int]): Stat stages of the player after the preparation.
        opponent_speed_factor (float): Multiplier applied to the opponent speed after the preparation.
        opponent_action_rate (float): Share of turns in which the opponent acts after the preparation.
        free_turns (float): Turns in which the opponent cannot act after the preparation.
        opponent_disabled_on_preparation (bool): Whether a faster player prevents the opponent from acting during the preparation.
        success_chance (float): Probability that the preparation succeeds.

    Methods:
        None.
    """

    name: str
    preparation_turns: int = 0
    player_stages: Mapping[str, int] = field(default_factory=dict)
    opponent_speed_factor: float = 1.0
    opponent_action_rate: float = 1.0
    free_turns: float = 0.0
    opponent_disabled_on_preparation: bool = False
    success_chance: float = 1.0


@dataclass(frozen=True)
class DuelOutcome:
    """
    Interface for the result of a one-against-one duel started at full health.

    Attributes:
        win (float): Probability-weighted victory of the player, between zero and one.
        health_left (float): Expected fraction of health the player keeps after the duel.
        turns (float): Expected number of turns the player needs, preparation included.
        score (float): Efficiency of the duel, zero for a defeat and otherwise rewarding few turns and little damage taken.
        plan (str): Plan chosen by the player.

    Methods:
        None.
    """

    win: float
    health_left: float
    turns: float
    score: float
    plan: str


class BattleSimulator:
    """
    Interface for resolving a deterministic duel in which the player picks
    the most efficient plan among direct attack, stat-boosting setup, sleep,
    and paralysis, then both sides repeat their most damaging move with
    accuracy-weighted average damage, so that each pairing receives a
    reproducible efficiency score in the spirit of the Smogon in-game tiers.

    Attributes:
        config (CampaignConfig): Assumptions of the simulation.
        strategies (StrategyConfig): Moves and abilities enabling the plans.
        reference (PlaythroughReference): Ability rules.
        calculator (DamageCalculator): Damage and statistic calculator.

    Methods:
        _plans(player: Combatant, opponent: Combatant) -> List[Plan]:
            Returns the plans available to the player against the opponent.

        _resolve(plan: Plan, player: Combatant, opponent: Combatant) -> Tuple[float, float, float]:
            Returns the victory, health kept, and turns of a successful plan, averaged over speed ties.

        _evaluate(plan: Plan, player: Combatant, opponent: Combatant) -> DuelOutcome:
            Returns the expected outcome of the plan, including the failure of its preparation.

        duel(player: Combatant, opponent: Combatant) -> DuelOutcome:
            Returns the outcome of the most efficient plan.
    """

    def __init__(
        self, config: CampaignConfig, strategies: StrategyConfig, reference: PlaythroughReference, calculator: DamageCalculator
    ) -> None:
        self.config: CampaignConfig = config
        self.strategies: StrategyConfig = strategies
        self.reference: PlaythroughReference = reference
        self.calculator: DamageCalculator = calculator
        logger.debug("Battle simulator initialization completed.")

    def _plans(self, player: Combatant, opponent: Combatant) -> List[Plan]:
        plans: List[Plan] = [Plan(name=_DIRECT_PLAN)]
        known = {move.name: move for move in player.moves}
        for name, boosts in self.strategies.setup_moves.items():
            if name not in known:
                continue
            for uses in range(1, self.config.maximum_setup_uses + 1):
                stages: Dict[str, int] = {
                    stat: max(-_MAXIMUM_STAGE, min(_MAXIMUM_STAGE, change * uses)) for stat, change in boosts.items()
                }
                plans.append(Plan(name=name, preparation_turns=uses, player_stages=stages))
        for name in self.strategies.sleep_moves + self.strategies.paralysis_moves:
            move = known.get(name)
            if move is None:
                continue
            is_sleep = name in self.strategies.sleep_moves
            blockers = self.strategies.sleep_blocking_abilities if is_sleep else self.strategies.paralysis_blocking_abilities
            if opponent.ability in blockers:
                continue
            if name in self.strategies.type_checked_status_moves and self.calculator.chart.effectiveness(move.move_type, opponent.record.types) == 0.0:
                continue
            chance = move.accuracy / _PERCENT if move.accuracy > 0 else 1.0
            if is_sleep:
                plans.append(Plan(name=name, preparation_turns=1, free_turns=self.config.sleep_free_turns, opponent_disabled_on_preparation=True, success_chance=chance))
            else:
                plans.append(
                    Plan(
                        name=name,
                        preparation_turns=1,
                        opponent_speed_factor=self.config.paralysis_speed_factor,
                        opponent_action_rate=self.config.paralysis_action_rate,
                        success_chance=chance,
                    )
                )
        return plans

    def _resolve(self, plan: Plan, player: Combatant, opponent: Combatant) -> Tuple[float, float, float]:
        player_stats = self.calculator.stats(player)
        opponent_stats = self.calculator.stats(opponent)
        player_intimidated = opponent.ability in self.reference.intimidating_abilities
        opponent_intimidated = player.ability in self.reference.intimidating_abilities
        damage_dealt, _ = self.calculator.best_damage(player, opponent, player_intimidated, plan.player_stages)
        damage_taken, _ = self.calculator.best_damage(opponent, player, opponent_intimidated, {}, plan.player_stages)
        if damage_dealt <= 0.0:
            return 0.0, 0.0, math.inf
        attack_turns = math.ceil(opponent_stats["hp"] / damage_dealt)
        player_speed = player_stats["speed"] * self.calculator.stage_multiplier(plan.player_stages.get("speed", 0))
        opponent_speed = opponent_stats["speed"] * plan.opponent_speed_factor
        orders = [True] if player_speed > opponent_speed else [False] if player_speed < opponent_speed else [True, False]
        results: List[Tuple[float, float]] = []
        for player_first in orders:
            preparation_hits = plan.preparation_turns
            if plan.opponent_disabled_on_preparation and player_first:
                preparation_hits -= 1
            attack_hits = max(0.0, attack_turns - plan.free_turns - (1 if player_first else 0)) * plan.opponent_action_rate
            received = (preparation_hits + attack_hits) * damage_taken
            won = received < player_stats["hp"]
            results.append((1.0 if won else 0.0, max(0.0, 1.0 - received / player_stats["hp"]) if won else 0.0))
        win = sum(result[0] for result in results) / len(results)
        health_left = sum(result[1] for result in results) / len(results)
        return win, health_left, float(plan.preparation_turns + attack_turns)

    def _evaluate(self, plan: Plan, player: Combatant, opponent: Combatant) -> DuelOutcome:
        weight = self.config.turn_weight
        win, health_left, turns = self._resolve(plan, player, opponent)
        branches = [(plan.success_chance, win, health_left, turns)]
        if plan.success_chance < 1.0:
            failure = Plan(name=plan.name, preparation_turns=plan.preparation_turns)
            branches.append((1.0 - plan.success_chance, *self._resolve(failure, player, opponent)))
        expected_win = sum(chance * branch_win for chance, branch_win, _, _ in branches)
        expected_health = sum(chance * branch_health for chance, _, branch_health, _ in branches)
        expected_turns = sum(chance * branch_turns for chance, _, _, branch_turns in branches if math.isfinite(branch_turns))
        score = sum(
            chance * branch_win * (weight / branch_turns + (1.0 - weight) * branch_health)
            for chance, branch_win, branch_health, branch_turns in branches
            if branch_win > 0.0
        )
        return DuelOutcome(win=expected_win, health_left=expected_health, turns=expected_turns, score=score, plan=plan.name)

    def duel(self, player: Combatant, opponent: Combatant) -> DuelOutcome:
        outcomes = [self._evaluate(plan, player, opponent) for plan in self._plans(player, opponent)]
        return max(outcomes, key=lambda outcome: (outcome.score, outcome.plan == _DIRECT_PLAN))
