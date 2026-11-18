import logging
from typing import Optional

import pandas as pd

from src.pipeline.dataset_pipeline import DatasetPipeline
from src.pipeline.study_pipeline import StudyPipeline
from src.settings import StudyConfig, StudyConfigLoader

logger = logging.getLogger(__name__)


class StudyOrchestrator:
    """
    Interface for executing the study end to end: automatic reconstruction of
    the dataset from the pinned remote sources, followed by the analysis and
    the rendering of the figure.

    Attributes:
        config (StudyConfig): Configuration of the study.

    Methods:
        run() -> pd.DataFrame:
            Rebuilds the dataset, executes the analysis, and returns the analysed population.
    """

    def __init__(self, config: Optional[StudyConfig] = None) -> None:
        self.config: StudyConfig = config or StudyConfigLoader().load()
        logger.info("Study orchestrator initialization completed.")

    def run(self) -> pd.DataFrame:
        logger.info("Starting the study execution.")
        tables = DatasetPipeline(self.config).run()
        population = StudyPipeline(self.config).run(tables)
        logger.info("Study execution successfully completed.")
        return population
