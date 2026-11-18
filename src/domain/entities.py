from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Tuple


@dataclass(frozen=True)
class GameReference:
    """
    Interface for the curated knowledge of the game that the remote data
    source does not provide, so that progression and the community ranking are declared once and shared by every component.

    Attributes:
        location_badges (MappingProxyType): Badges required to reach each location area.
        method_badges (MappingProxyType): Badges required to use each encounter method.
        item_badges (MappingProxyType): Badges required to obtain each evolution item.
        smogon_tiers (MappingProxyType): Smogon in-game tier of each final form.
        tier_scores (MappingProxyType): Ordinal score of each Smogon tier letter.

    Methods:
        None.
    """

    location_badges: MappingProxyType
    method_badges: MappingProxyType
    item_badges: MappingProxyType
    smogon_tiers: MappingProxyType
    tier_scores: MappingProxyType


class PokemonField(str, Enum):
    """Enumeration defining the column names of the study dataset."""

    POKEDEX_ID = "pokedex_id"
    SPECIES = "species"
    PRIMARY_TYPE = "primary_type"
    SECONDARY_TYPE = "secondary_type"
    IS_FINAL_FORM = "is_final_form"
    PRE_EVOLUTION = "pre_evolution"
    HP = "hp"
    ATTACK = "attack"
    DEFENSE = "defense"
    SPECIAL_ATTACK = "special_attack"
    SPECIAL_DEFENSE = "special_defense"
    SPEED = "speed"
    BADGES_REQUIRED = "badges_required"
    OBTAIN_LEVEL = "obtain_level"
    REQUIRES_TRADE = "requires_trade"
    SMOGON_TIER = "smogon_tier"
    SMOGON_TIER_SCORE = "smogon_tier_score"
    SPRITE_URL = "sprite_url"
    AXIS_X = "axis_x"
    AXIS_Y = "axis_y"
    QUADRANT = "quadrant"
    BATTLE_QUALITY = "battle_quality"
    TOTAL_CONTRIBUTION = "total_contribution"
    CONTRIBUTION_EARLINESS = "contribution_earliness"
    ACQUISITION_EFFORT = "acquisition_effort"
    PREDICTED_SCORE = "predicted_score"
    CROSS_VALIDATED_SCORE = "cross_validated_score"
    PREDICTED_TIER = "predicted_tier"
    BATTLES_AVAILABLE_SHARE = "battles_available_share"
    EXPERIENCE_TO_LEVEL_50 = "experience_to_level_50"
    FINAL_FORM_LEVEL = "final_form_level"
    STAT_SOURCE_MISMATCH = "stat_source_mismatch"




@dataclass(frozen=True)
class GameMove:
    """
    Interface for a move exactly as defined in the third-generation cartridge.

    Attributes:
        name (str): Move name in lowercase hyphenated form.
        effect (str): Battle effect identifier of the cartridge.
        power (int): Base power, zero for status moves.
        move_type (str): Move type.
        accuracy (int): Accuracy in percent, zero for moves that never miss.

    Methods:
        None.
    """

    name: str
    effect: str
    power: int
    move_type: str
    accuracy: int


@dataclass(frozen=True)
class SpeciesRecord:
    """
    Interface for the battle-relevant data of a species in the third-generation cartridge.

    Attributes:
        name (str): Species name in lowercase hyphenated form.
        stats (MappingProxyType): Base statistics keyed by statistic name.
        types (Tuple[str, ...]): Types of the species.
        abilities (Tuple[str, ...]): Distinct abilities the species can have.
        growth_rate (str): Experience group identifier.

    Methods:
        None.
    """

    name: str
    stats: MappingProxyType
    types: Tuple[str, ...]
    abilities: Tuple[str, ...]
    growth_rate: str


@dataclass(frozen=True)
class TrainerPokemon:
    """
    Interface for a Pokémon fielded by a trainer in a major battle.

    Attributes:
        species (str): Species name.
        level (int): Level of the Pokémon.
        individual_value (int): Individual value applied to every statistic.
        moves (Tuple[str, ...]): Moves known by the Pokémon.

    Methods:
        None.
    """

    species: str
    level: int
    individual_value: int
    moves: Tuple[str, ...]


@dataclass(frozen=True)
class MajorBattle:
    """
    Interface for a major battle of the game and the parties that can be faced in it.

    Attributes:
        name (str): Identifier of the battle.
        label (str): Display name of the opponent.
        badges_before (int): Badges owned by the player when the battle takes place.
        player_level (int): Level of the player's Pokémon in the battle.
        parties (Tuple[Tuple[TrainerPokemon, ...], ...]): Alternative parties of the opponent, averaged in the evaluation.

    Methods:
        None.
    """

    name: str
    label: str
    badges_before: int
    player_level: int
    parties: Tuple[Tuple[TrainerPokemon, ...], ...]


@dataclass(frozen=True)
class PlaythroughReference:
    """
    Interface for the curated progression of moves and the battle rules that
    the simulation applies, so that every assumption is declared in one asset.

    Attributes:
        bosses (Tuple[Tuple[str, str, int, Tuple[str, ...], bool], ...]): Name, label, badges owned, party symbols, and league flag of each major battle, in game order.
        machine_badges (MappingProxyType): Badges required to obtain each technical or hidden machine move.
        tutor_badges (MappingProxyType): Badges required to reach each move tutor.
        excluded_effects (Tuple[str, ...]): Move effects ignored by the damage model.
        level_damage_effects (Tuple[str, ...]): Move effects dealing damage equal to the user level.
        fixed_damage (MappingProxyType): Fixed damage of the corresponding move effects.
        fixed_power (MappingProxyType): Power assumed for move effects with variable power.
        power_multipliers (MappingProxyType): Multipliers applied to the power of multi-hit, charging, and recharging moves.
        immunity_abilities (MappingProxyType): Type made harmless by each ability.
        halving_abilities (MappingProxyType): Types whose damage is halved by each ability.
        intimidating_abilities (Tuple[str, ...]): Abilities lowering the opposing attack on entry.
        growth_experience (MappingProxyType): Experience required to reach level fifty for each experience group.

    Methods:
        None.
    """

    bosses: Tuple[Tuple[str, str, int, Tuple[str, ...], bool], ...]
    machine_badges: MappingProxyType
    tutor_badges: MappingProxyType
    excluded_effects: Tuple[str, ...]
    level_damage_effects: Tuple[str, ...]
    fixed_damage: MappingProxyType
    fixed_power: MappingProxyType
    power_multipliers: MappingProxyType
    immunity_abilities: MappingProxyType
    halving_abilities: MappingProxyType
    intimidating_abilities: Tuple[str, ...]
    growth_experience: MappingProxyType

