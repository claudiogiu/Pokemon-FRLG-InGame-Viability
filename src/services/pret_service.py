import logging
from pathlib import Path
from typing import Optional

import requests

from src.settings import RAW_DIR, PretConfig, SourceConfig

logger = logging.getLogger(__name__)


class PretService:
    """
    Interface for retrieving source files of the pokefirered decompilation
    at a pinned commit, with a local cache, so that the exact data of the cartridge (base
    statistics, learnsets, move effects, trainer parties) is read once and
    every subsequent execution is reproducible offline.

    Attributes:
        config (PretConfig): Location of the decompilation files.
        source_config (SourceConfig): Network parameters shared with the other remote sources.
        cache_dir (Path): Folder holding the cached files.
        _session (requests.Session): Persistent HTTP session.

    Methods:
        fetch(relative_path: str) -> str:
            Returns the text of the decompilation file, from cache when available.
    """

    def __init__(self, config: PretConfig, source_config: SourceConfig, cache_dir: Optional[Path] = None) -> None:
        resolved_dir = cache_dir or (RAW_DIR / "pret")
        resolved_dir.mkdir(parents=True, exist_ok=True)
        self.config: PretConfig = config
        self.source_config: SourceConfig = source_config
        self.cache_dir: Path = resolved_dir
        self._session: requests.Session = requests.Session()
        logger.info("Decompilation service initialization completed.")

    def fetch(self, relative_path: str) -> str:
        cache_path = self.cache_dir / relative_path.replace("/", "__")
        if cache_path.is_file():
            return cache_path.read_text(encoding="utf-8")
        url = f"{self.config.base_url}/{self.config.commit}/{relative_path}"
        logger.info(f"Sending GET request to the decompilation repository. File: {relative_path}.")
        try:
            response = self._session.get(url, timeout=self.source_config.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Decompilation file retrieval failed: {e}")
            raise RuntimeError(f"The decompilation repository did not return the file {relative_path}.") from e
        cache_path.write_text(response.text, encoding="utf-8")
        return response.text
