import logging
from typing import Tuple

import pandas as pd

from src.domain.entities import PokemonField
from src.settings import StudyConfig

logger = logging.getLogger(__name__)


class AxisComposer:
    """
    Interface for placing every line on the two axes of the quadrant map,
    the calibrated strength estimate and the availability over the game, and
    for assigning it to a quadrant split at the medians, so that the map
    separates the lines that carry a whole playthrough from those that are
    strong only late or useful only early.

    Attributes:
        config (StudyConfig): Configuration of the study, including axis columns and quadrant names.

    Methods:
        medians(population: pd.DataFrame) -> Tuple[float, float]:
            Returns the medians of the two axes.

        compose(population: pd.DataFrame) -> pd.DataFrame:
            Returns the population enriched with the two axes and the quadrant label.
    """

    def __init__(self, config: StudyConfig) -> None:
        self.config: StudyConfig = config
        logger.info("Axis composer initialization completed.")

    def medians(self, population: pd.DataFrame) -> Tuple[float, float]:
        return (
            float(population[PokemonField.AXIS_X.value].median()),
            float(population[PokemonField.AXIS_Y.value].median()),
        )

    def compose(self, population: pd.DataFrame) -> pd.DataFrame:
        axes = self.config.axes
        missing = [column for column in (axes.x_feature, axes.y_feature) if column not in population.columns]
        if missing:
            raise ValueError(f"The quadrant axes reference unknown columns: {', '.join(missing)}.")
        logger.info(f"Starting composition of the quadrant axes. Horizontal: {axes.x_feature}. Vertical: {axes.y_feature}.")
        enriched = population.copy()
        enriched[PokemonField.AXIS_X.value] = enriched[axes.x_feature].astype(float)
        enriched[PokemonField.AXIS_Y.value] = enriched[axes.y_feature].astype(float)
        x_median, y_median = self.medians(enriched)
        quadrant_index = (
            (enriched[PokemonField.AXIS_X.value] >= x_median).astype(int)
            + 2 * (enriched[PokemonField.AXIS_Y.value] >= y_median).astype(int)
        )
        enriched[PokemonField.QUADRANT.value] = quadrant_index.map(dict(enumerate(axes.quadrant_labels)))
        counts = enriched[PokemonField.QUADRANT.value].value_counts().to_dict()
        logger.info(f"Quadrant axes successfully composed. Quadrant sizes: {counts}.")
        return enriched
