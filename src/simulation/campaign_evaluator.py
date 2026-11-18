import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.domain.entities import (
    GameMove,
    MajorBattle,
    PlaythroughReference,
    PokemonField,
    TrainerPokemon,
)
from src.features.type_chart import TypeChart
from src.ingestion.pret_parser import PretData
from src.settings import StudyConfig
from src.simulation.battle_simulator import BattleSimulator
from src.simulation.damage_calculator import Combatant, DamageCalculator

logger = logging.getLogger(__name__)

_BOSS_COLUMN: str = "boss"
_FORM_COLUMN: str = "form_used"
_SCORE_COLUMN: str = "duel_score"
_AVAILABLE_COLUMN: str = "available"
_STANDARDIZED_COLUMN: str = "standardized_score"


class CampaignEvaluator:
    """
    Interface for replaying the major battles of FireRed and LeafGreen with
    every evolutionary line, using at each battle the most evolved form and
    the moves obtainable by then, so that strength is measured against the
    opponents actually faced in a standard playthrough.

    Attributes:
        config (StudyConfig): Configuration of the study.
        reference (PlaythroughReference): Major battles, move progression, and battle rules.
        data (PretData): Cartridge data parsed from the decompilation.
        simulator (BattleSimulator): Duel resolver.
        battles (Tuple[MajorBattle, ...]): Major battles with their parties.

    Methods:
        _build_battles() -> Tuple[MajorBattle, ...]:
            Returns the major battles with the parsed parties.

        _lineage(species: str, dataset: pd.DataFrame) -> List[str]:
            Returns the species and its pre-evolutions, most evolved first.

        _form_for(lineage: List[str], dataset: pd.DataFrame, badges: int, level: int) -> Optional[str]:
            Returns the most evolved form obtainable with the given badges at the given level.

        _player_moves(lineage: List[str], form: str, badges: int, level: int) -> Tuple[GameMove, ...]:
            Returns the moves the form can know at the given progression and level.

        _default_moves(species: str, level: int) -> Tuple[str, ...]:
            Returns the moves a trainer Pokémon without a custom moveset knows, as the last level-up moves learned.

        _opponent(member: TrainerPokemon) -> Combatant:
            Returns the combatant representing a trainer Pokémon.

        _evaluate_battle(form: str, moves: Tuple[GameMove, ...], level: int, battle: MajorBattle) -> float:
            Returns the mean duel score of the form against the battle parties.

        evaluate(dataset: pd.DataFrame, species_list: List[str]) -> pd.DataFrame:
            Returns one row per evolutionary line and major battle with the simulated results.

        aggregate(results: pd.DataFrame) -> pd.DataFrame:
            Returns one row per evolutionary line with the battle quality, the total contribution, its earliness, and the share of available battles.
    """

    def __init__(self, config: StudyConfig, reference: PlaythroughReference, data: PretData, chart: TypeChart) -> None:
        self.config: StudyConfig = config
        self.reference: PlaythroughReference = reference
        self.data: PretData = data
        calculator = DamageCalculator(config.campaign, reference, chart)
        self.simulator: BattleSimulator = BattleSimulator(config.campaign, config.strategies, reference, calculator)
        self.battles: Tuple[MajorBattle, ...] = self._build_battles()
        logger.info(f"Campaign evaluator initialization completed. Major battles: {len(self.battles)}.")

    def _build_battles(self) -> Tuple[MajorBattle, ...]:
        battles: List[MajorBattle] = []
        for name, label, badges, symbols, league in self.reference.bosses:
            missing = [symbol for symbol in symbols if symbol not in self.data.parties]
            if missing:
                raise ValueError(f"The decompilation does not define the parties: {', '.join(missing)}.")
            parties = tuple(self.data.parties[symbol] for symbol in symbols)
            ace_level = max(member.level for party in parties for member in party)
            player_level = self.config.campaign.league_player_level if league else ace_level
            battles.append(MajorBattle(name, label, badges, player_level, parties))
        return tuple(battles)

    def _lineage(self, species: str, dataset: pd.DataFrame) -> List[str]:
        parents = dict(zip(dataset[PokemonField.SPECIES.value], dataset[PokemonField.PRE_EVOLUTION.value], strict=True))
        lineage = [species]
        while isinstance(parents.get(lineage[-1]), str):
            lineage.append(parents[lineage[-1]])
        return lineage

    def _form_for(self, lineage: List[str], dataset: pd.DataFrame, badges: int, level: int) -> Optional[str]:
        indexed = dataset.set_index(PokemonField.SPECIES.value)
        for form in lineage:
            row = indexed.loc[form]
            if row[PokemonField.BADGES_REQUIRED.value] <= badges and row[PokemonField.OBTAIN_LEVEL.value] <= level:
                return form
        return None

    def _player_moves(self, lineage: List[str], form: str, badges: int, level: int) -> Tuple[GameMove, ...]:
        names = {
            move for member in lineage[lineage.index(form):]
            for learned_level, move in self.data.level_up.get(member, ())
            if learned_level <= level
        }
        names |= {move for move in self.data.machines.get(form, ()) if self.reference.machine_badges.get(move, badges + 1) <= badges}
        names |= {move for move in self.data.tutors.get(form, ()) if self.reference.tutor_badges.get(move, badges + 1) <= badges}
        return tuple(self.data.moves[name] for name in sorted(names) if name in self.data.moves)

    def _default_moves(self, species: str, level: int) -> Tuple[str, ...]:
        learned: List[str] = []
        for learned_level, move in self.data.level_up.get(species, ()):
            if learned_level <= level and move not in learned:
                learned.append(move)
        return tuple(learned[-self.config.campaign.default_move_count:])

    def _opponent(self, member: TrainerPokemon) -> Combatant:
        record = self.data.species[member.species]
        move_names = member.moves or self._default_moves(member.species, member.level)
        return Combatant(
            record=record,
            level=member.level,
            individual_value=member.individual_value,
            effort_value=0,
            ability=record.abilities[0] if record.abilities else None,
            moves=tuple(self.data.moves[name] for name in move_names if name in self.data.moves),
        )

    def _evaluate_battle(self, form: str, moves: Tuple[GameMove, ...], level: int, battle: MajorBattle) -> float:
        record = self.data.species[form]
        abilities = record.abilities or (None,)
        scores: List[float] = []
        for ability in abilities:
            player = Combatant(
                record=record,
                level=level,
                individual_value=self.config.campaign.player_iv,
                effort_value=self.config.campaign.player_ev,
                ability=ability,
                moves=moves,
            )
            for party in battle.parties:
                for member in party:
                    outcome = self.simulator.duel(player, self._opponent(member))
                    scores.append(outcome.score)
        return float(np.mean(scores))

    def evaluate(self, dataset: pd.DataFrame, species_list: List[str]) -> pd.DataFrame:
        logger.info(f"Starting simulation of the major battles. Lines: {len(species_list)}. Battles: {len(self.battles)}.")
        rows: List[Dict[str, Any]] = []
        for species in species_list:
            lineage = self._lineage(species, dataset)
            for battle in self.battles:
                level = battle.player_level
                form = self._form_for(lineage, dataset, battle.badges_before, level)
                row: Dict[str, Any] = {
                    PokemonField.SPECIES.value: species,
                    _BOSS_COLUMN: battle.name,
                    _FORM_COLUMN: form,
                    _AVAILABLE_COLUMN: form is not None,
                    _SCORE_COLUMN: np.nan,
                }
                if form is not None and form in self.data.species:
                    moves = self._player_moves(lineage, form, battle.badges_before, level)
                    row[_SCORE_COLUMN] = self._evaluate_battle(form, moves, level, battle)
                rows.append(row)
        results = pd.DataFrame(rows)
        logger.info(
            f"Simulation of the major battles successfully completed. "
            f"Line-battle pairs: {len(results)}. "
            f"Available pairs: {int(results[_AVAILABLE_COLUMN].sum())}. "
        )
        return results

    def aggregate(self, results: pd.DataFrame) -> pd.DataFrame:
        logger.info("Starting aggregation of the simulated battles.")
        standardized = results.copy()
        grouped = standardized.groupby(_BOSS_COLUMN)[_SCORE_COLUMN]
        standardized[_STANDARDIZED_COLUMN] = (standardized[_SCORE_COLUMN] - grouped.transform("mean")) / grouped.transform("std")
        battle_order = [battle.name for battle in self.battles]
        by_species = standardized[PokemonField.SPECIES.value]
        contributions = standardized[_SCORE_COLUMN].fillna(0.0).groupby(by_species).sum()
        progress = standardized[_BOSS_COLUMN].map({name: index / (len(battle_order) - 1) for index, name in enumerate(battle_order)})
        weighted_progress = (standardized[_SCORE_COLUMN].fillna(0.0) * progress).groupby(by_species).sum()
        summary = pd.DataFrame(
            {
                PokemonField.BATTLE_QUALITY.value: standardized[_STANDARDIZED_COLUMN].groupby(by_species).mean(),
                PokemonField.TOTAL_CONTRIBUTION.value: contributions / len(battle_order),
                PokemonField.CONTRIBUTION_EARLINESS.value: 1.0 - weighted_progress / contributions.replace(0.0, np.nan),
                PokemonField.BATTLES_AVAILABLE_SHARE.value: standardized[_AVAILABLE_COLUMN].groupby(by_species).sum() / len(battle_order),
            }
        )
        aggregated = summary.rename_axis(PokemonField.SPECIES.value).reset_index()
        logger.info(f"Aggregation of the simulated battles successfully completed. Lines: {len(aggregated)}.")
        return aggregated
