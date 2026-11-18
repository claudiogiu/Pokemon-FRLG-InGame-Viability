import logging
from pathlib import Path
from typing import Optional

import requests
from matplotlib import font_manager

from src.settings import RAW_DIR, FontConfig, SourceConfig

logger = logging.getLogger(__name__)


class FontService:
    """
    Interface for downloading the open font of the figure from the Google
    Fonts repository at a pinned commit and registering it with Matplotlib,
    so that the figure renders identically on every system.

    Attributes:
        config (FontConfig): Pinned location and family of the font.
        source_config (SourceConfig): Network parameters shared with the other remote sources.
        cache_dir (Path): Folder holding the downloaded font files.
        _session (requests.Session): Persistent HTTP session.

    Methods:
        _fetch(relative_path: str) -> Path:
            Returns the local file of a font, downloading it when absent.

        register() -> str:
            Downloads and registers every configured font file and returns the font family.
    """

    def __init__(self, config: FontConfig, source_config: SourceConfig, cache_dir: Optional[Path] = None) -> None:
        resolved_dir = cache_dir or (RAW_DIR / "fonts")
        resolved_dir.mkdir(parents=True, exist_ok=True)
        self.config: FontConfig = config
        self.source_config: SourceConfig = source_config
        self.cache_dir: Path = resolved_dir
        self._session: requests.Session = requests.Session()
        logger.info("Font service initialization completed.")

    def _fetch(self, relative_path: str) -> Path:
        cache_path = self.cache_dir / Path(relative_path).name
        if cache_path.is_file():
            return cache_path
        url = f"{self.config.base_url}/{self.config.commit}/{relative_path}"
        try:
            response = self._session.get(url, timeout=self.source_config.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Font download failed: {e}")
            raise RuntimeError(f"The font repository did not return the file {relative_path}.") from e
        cache_path.write_bytes(response.content)
        return cache_path

    def register(self) -> str:
        logger.info(f"Starting registration of the figure font. Files: {len(self.config.files)}.")
        for relative_path in self.config.files:
            font_manager.fontManager.addfont(str(self._fetch(relative_path)))
        logger.info(f"Figure font successfully registered. Family: {self.config.family}.")
        return self.config.family
