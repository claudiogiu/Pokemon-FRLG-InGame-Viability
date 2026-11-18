import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.domain.entities import PokemonField
from src.features.dataset_builder import DatasetBuilder
from src.features.playthrough_feature_builder import PlaythroughFeatureBuilder
from src.ingestion.pret_parser import PretParser
from src.ingestion.raw_collector import RawCollector
from src.ingestion.reference_registry import GameReferenceRegistry, PlaythroughReferenceRegistry
from src.services.pokeapi_service import PokeApiService
from src.services.pret_service import PretService
from src.services.sprite_service import SpriteService
from src.settings import PROCESSED_DIR, StudyConfig

logger = logging.getLogger(__name__)


class DatasetPipeline:
    """
    Interface for rebuilding the reference dataset from the pinned remote
    sources: PokéAPI static data, the pokefirered decompilation, and the
    simulation of the major battles, so that every execution produces the same
    tables without the data being versioned.

    Attributes:
        config (StudyConfig): Configuration of the study.
        processed_dir (Path): Folder receiving the rebuilt tables.

    Methods:
        run() -> Dict[str, pd.DataFrame]:
            Rebuilds, writes, and returns the dataset tables keyed by file name.
    """

    def __init__(self, config: StudyConfig, processed_dir: Optional[Path] = None) -> None:
        self.config: StudyConfig = config
        self.processed_dir: Path = processed_dir or PROCESSED_DIR
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Dataset pipeline initialization completed.")

    def run(self) -> Dict[str, pd.DataFrame]:
        logger.info("Starting reconstruction of the reference dataset.")
        game_reference = GameReferenceRegistry().load()
        bundle = RawCollector(PokeApiService(self.config.source), self.config.source).collect()
        builder = DatasetBuilder(self.config, game_reference, bundle)
        lines = builder.build()
        sprite_service = SpriteService(self.config.source)
        lines[PokemonField.SPRITE_URL.value] = lines[PokemonField.SPRITE_URL.value].map(
            lambda url: sprite_service.pinned(url) if isinstance(url, str) else url
        )
        pret_data = PretParser(self.config, PretService(self.config.pret, self.config.source)).parse()
        playthrough = PlaythroughFeatureBuilder(self.config, PlaythroughReferenceRegistry().load(), pret_data, builder.chart)
        lines, battles = playthrough.enrich(lines)
        tables = {self.config.dataset.lines_name: lines, self.config.dataset.battles_name: battles}
        for name, table in tables.items():
            table.to_parquet(self.processed_dir / name, index=False)
        logger.info(f"Reference dataset successfully rebuilt. Lines: {len(lines)}. Battle rows: {len(battles)}.")
        return tables
