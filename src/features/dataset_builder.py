import logging
import math
from typing import Any, Dict, List, Tuple

import pandas as pd

from src.domain.entities import GameReference, PokemonField
from src.features.availability_resolver import AvailabilityResolver
from src.features.generation_resolver import GenerationResolver
from src.features.type_chart import TypeChart
from src.ingestion.raw_collector import RawBundle
from src.settings import StudyConfig

logger = logging.getLogger(__name__)


class DatasetBuilder:
    """
    Interface for crossing types, base statistics, evolutions, availability,
    sprites, and Smogon tiers into one table with one row per species, so
    that the battle simulation and the calibration read a single prepared table.

    Attributes:
        config (StudyConfig): Configuration of the study.
        reference (GameReference): Curated progression tables and Smogon tiers.
        bundle (RawBundle): Raw documents of the data source.
        resolver (GenerationResolver): Reconstruction of generation-specific attributes.
        chart (TypeChart): Type chart of the generation under study.

    Methods:
        _tier(species: str) -> Tuple[Any, Any]:
            Returns the Smogon tier letter and its ordinal score, or missing values when unranked.

        build() -> pd.DataFrame:
            Produces the dataset of the study.
    """

    def __init__(self, config: StudyConfig, reference: GameReference, bundle: RawBundle) -> None:
        self.config: StudyConfig = config
        self.reference: GameReference = reference
        self.bundle: RawBundle = bundle
        self.resolver: GenerationResolver = GenerationResolver(config.source)
        self.chart: TypeChart = TypeChart(self.resolver, bundle.types)
        logger.info("Dataset builder initialization completed.")

    def _tier(self, species: str) -> Tuple[Any, Any]:
        letter = self.reference.smogon_tiers.get(species)
        if letter is None:
            return None, math.nan
        return letter, self.reference.tier_scores[letter]

    def build(self) -> pd.DataFrame:
        logger.info("Starting construction of the study dataset.")
        names = {i: document["name"] for i, document in self.bundle.species.items()}
        encounters_by_species = {names[i]: self.bundle.encounters[i] for i in names}
        availability = AvailabilityResolver(
            self.config.source, self.config.acquisition, self.reference, list(self.bundle.evolution_chains.values())
        )
        rows: List[Dict[str, Any]] = []
        for pokedex_id, species in sorted(names.items()):
            types = self.resolver.types_of(self.bundle.pokemon[pokedex_id])
            acquisition = availability.resolve(species, encounters_by_species)
            tier_letter, tier_score = self._tier(species)
            parent = availability.parent_of(species)
            rows.append({
                PokemonField.POKEDEX_ID.value: pokedex_id,
                PokemonField.SPECIES.value: species,
                PokemonField.PRIMARY_TYPE.value: types[0],
                PokemonField.SECONDARY_TYPE.value: types[1] if len(types) > 1 else None,
                PokemonField.IS_FINAL_FORM.value: not any(
                    child in encounters_by_species for child in availability.evolutions_of(species)
                ),
                PokemonField.PRE_EVOLUTION.value: parent if parent in encounters_by_species else None,
                **self.resolver.stats_of(self.bundle.pokemon[pokedex_id]),
                PokemonField.BADGES_REQUIRED.value: acquisition.badges_required,
                PokemonField.OBTAIN_LEVEL.value: acquisition.obtain_level,
                PokemonField.REQUIRES_TRADE.value: int(acquisition.requires_trade),
                PokemonField.ACQUISITION_EFFORT.value: acquisition.effort,
                PokemonField.SPRITE_URL.value: self.bundle.pokemon[pokedex_id]["sprites"]["versions"]["generation-iii"]
                .get(self.config.source.sprite_version, {})
                .get("front_default"),
                PokemonField.SMOGON_TIER.value: tier_letter,
                PokemonField.SMOGON_TIER_SCORE.value: tier_score,
            })
        dataset = pd.DataFrame(rows)
        logger.info(
            f"Study dataset successfully constructed. "
            f"Rows: {len(dataset)}. "
            f"Columns: {dataset.shape[1]}. "
            f"Final forms: {int(dataset[PokemonField.IS_FINAL_FORM.value].sum())}. "
        )
        return dataset
