import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.domain.entities import PokemonField
from src.ingestion.reference_registry import GameReferenceRegistry
from src.modeling.axis_composer import AxisComposer
from src.modeling.smogon_calibrator import CalibrationResult, SmogonCalibrator
from src.plotting.quadrant_plot import QuadrantPlot
from src.services.font_service import FontService
from src.services.sprite_service import SpriteService
from src.settings import FIGURES_DIR, PROCESSED_DIR, StudyConfig

logger = logging.getLogger(__name__)


class StudyPipeline:
    """
    Interface for analysing the reference dataset: calibration of the battle
    and ease features against the Smogon tiers, placement on the quadrant
    map, export of the results, and rendering of the figure.

    Attributes:
        config (StudyConfig): Configuration of the study.
        processed_dir (Path): Folder receiving the results table.
        figures_dir (Path): Folder receiving the figure.

    Methods:
        _population(lines: pd.DataFrame) -> pd.DataFrame:
            Returns the final forms admitted to the analysis.

        _agreement(calibration: CalibrationResult) -> str:
            Returns the subtitle stating what the figure shows and its agreement with the Smogon tiers.

        run(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
            Executes the analysis and returns the analysed population.
    """

    def __init__(self, config: StudyConfig, processed_dir: Optional[Path] = None, figures_dir: Optional[Path] = None) -> None:
        self.config: StudyConfig = config
        self.processed_dir: Path = processed_dir or PROCESSED_DIR
        self.figures_dir: Path = figures_dir or FIGURES_DIR
        logger.info("Study pipeline initialization completed.")

    def _population(self, lines: pd.DataFrame) -> pd.DataFrame:
        mask = lines[PokemonField.IS_FINAL_FORM.value] & ~lines[PokemonField.SPECIES.value].isin(self.config.population.excluded_species)
        population = lines[mask].reset_index(drop=True)
        logger.info(f"Analysed population successfully selected. Lines: {len(population)}.")
        return population

    def _agreement(self, calibration: CalibrationResult) -> str:
        return f"{self.config.report.subtitle} (Agreement With Smogon, $\\rho$ = {calibration.cross_validated_spearman:.2f})"

    def run(self, tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        logger.info("Starting the study analysis.")
        lines = tables[self.config.dataset.lines_name]
        game_reference = GameReferenceRegistry().load()
        calibrator = SmogonCalibrator(self.config.calibration, dict(game_reference.tier_scores))
        population, calibration = calibrator.calibrate(self._population(lines))
        composer = AxisComposer(self.config)
        population = composer.compose(population)
        population.to_parquet(self.processed_dir / self.config.report.results_name, index=False)
        sprites = SpriteService(self.config.source).fetch_many(
            dict(zip(population[PokemonField.SPECIES.value], population[PokemonField.SPRITE_URL.value], strict=True))
        )
        font_family = FontService(self.config.fonts, self.config.source).register()
        QuadrantPlot(self.config, self.figures_dir, font_family).build(population, sprites, composer.medians(population), self._agreement(calibration))
        logger.info("Study analysis successfully completed.")
        return population
