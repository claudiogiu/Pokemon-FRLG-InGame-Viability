import logging
from typing import List, Tuple

import pandas as pd

from src.domain.entities import PlaythroughReference, PokemonField
from src.features.type_chart import TypeChart
from src.ingestion.pret_parser import PretData
from src.settings import StudyConfig
from src.simulation.campaign_evaluator import CampaignEvaluator

logger = logging.getLogger(__name__)


class PlaythroughFeatureBuilder:
    """
    Interface for enriching the study dataset with the features of a standard
    playthrough: the simulated performance against the major battles, the
    share of those battles a line can take part in, the experience it needs,
    and the agreement between the two data sources.

    Attributes:
        config (StudyConfig): Configuration of the study.
        reference (PlaythroughReference): Major battles, move progression, and battle rules.
        data (PretData): Cartridge data parsed from the decompilation.
        evaluator (CampaignEvaluator): Simulator of the major battles.

    Methods:
        _source_mismatch(dataset: pd.DataFrame) -> pd.Series:
            Returns whether the base statistics or types of each species differ between the two data sources.

        enrich(dataset: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
            Returns the enriched dataset and the long table of simulated battles.
    """

    def __init__(self, config: StudyConfig, reference: PlaythroughReference, data: PretData, chart: TypeChart) -> None:
        self.config: StudyConfig = config
        self.reference: PlaythroughReference = reference
        self.data: PretData = data
        self.evaluator: CampaignEvaluator = CampaignEvaluator(config, reference, data, chart)
        logger.info("Playthrough feature builder initialization completed.")

    def _source_mismatch(self, dataset: pd.DataFrame) -> pd.Series:
        stat_names = list(next(iter(self.data.species.values())).stats.keys())
        mismatches: List[bool] = []
        for _, row in dataset.iterrows():
            record = self.data.species.get(row[PokemonField.SPECIES.value])
            if record is None:
                mismatches.append(True)
                continue
            types = tuple(value for value in (row[PokemonField.PRIMARY_TYPE.value], row[PokemonField.SECONDARY_TYPE.value]) if isinstance(value, str))
            same_stats = all(int(row[name]) == record.stats[name] for name in stat_names)
            mismatches.append(not (same_stats and types == record.types))
        return pd.Series(mismatches, index=dataset.index)

    def enrich(self, dataset: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        logger.info("Starting enrichment of the dataset with playthrough features.")
        enriched = dataset.copy()
        enriched[PokemonField.STAT_SOURCE_MISMATCH.value] = self._source_mismatch(enriched)
        logger.info(
            f"Cross-source verification completed. "
            f"Species with differing statistics or types: {int(enriched[PokemonField.STAT_SOURCE_MISMATCH.value].sum())}."
        )
        enriched[PokemonField.EXPERIENCE_TO_LEVEL_50.value] = enriched[PokemonField.SPECIES.value].map(
            lambda species: self.reference.growth_experience[self.data.species[species].growth_rate]
        )
        enriched[PokemonField.FINAL_FORM_LEVEL.value] = enriched[PokemonField.OBTAIN_LEVEL.value]
        final_forms = enriched.loc[enriched[PokemonField.IS_FINAL_FORM.value], PokemonField.SPECIES.value].tolist()
        battles = self.evaluator.evaluate(enriched, final_forms)
        aggregated = self.evaluator.aggregate(battles)
        enriched = enriched.merge(aggregated, on=PokemonField.SPECIES.value, how="left")
        logger.info(f"Dataset successfully enriched with playthrough features. Columns: {enriched.shape[1]}.")
        return enriched, battles
