import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

from src.settings import RAW_DIR, SourceConfig

logger = logging.getLogger(__name__)


class SpriteService:
    """
    Interface for downloading the in-game sprites referenced by the dataset
    into a local cache, so that the figures embed the original artwork of the
    version under study without repeated remote requests.

    Attributes:
        config (SourceConfig): Parameters of the remote source, including timeout and concurrency.
        cache_dir (Path): Folder holding the cached sprites.
        _session (requests.Session): Persistent HTTP session.

    Methods:
        _cache_path(url: str) -> Path:
            Returns the cache file associated with the sprite address.

        pinned(url: str) -> str:
            Returns the sprite address rewritten to the pinned commit of the sprite repository.

        fetch(url: str) -> Path:
            Returns the local file of the sprite, downloading it when absent.

        fetch_many(urls: Dict[str, str]) -> Dict[str, Path]:
            Returns the local files of several sprites keyed as the supplied addresses.
    """

    def __init__(self, config: SourceConfig, cache_dir: Optional[Path] = None) -> None:
        resolved_dir = cache_dir or (RAW_DIR / "sprites")
        resolved_dir.mkdir(parents=True, exist_ok=True)
        self.config: SourceConfig = config
        self.cache_dir: Path = resolved_dir
        self._session: requests.Session = requests.Session()
        self._session.mount("https://", HTTPAdapter(pool_maxsize=config.worker_count))
        logger.info("Sprite service initialization completed.")

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / "__".join(url.split("/")[-3:])

    def pinned(self, url: str) -> str:
        repository = self.config.sprite_repository
        return url.replace(f"{repository}/master/", f"{repository}/{self.config.sprite_commit}/")

    def fetch(self, url: str) -> Path:
        url = self.pinned(url)
        cache_path = self._cache_path(url)
        if cache_path.is_file():
            return cache_path
        try:
            response = self._session.get(url, timeout=self.config.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Sprite download failed: {e}")
            raise RuntimeError(f"The sprite repository did not return a valid image for {url}.") from e
        cache_path.write_bytes(response.content)
        return cache_path

    def fetch_many(self, urls: Dict[str, str]) -> Dict[str, Path]:
        keys: List[str] = [key for key, url in urls.items() if url]
        logger.info(f"Starting retrieval of sprites. Sprites: {len(keys)}.")
        with ThreadPoolExecutor(max_workers=self.config.worker_count) as executor:
            paths = list(executor.map(self.fetch, [urls[key] for key in keys]))
        logger.info(f"Sprites successfully retrieved. Sprites: {len(paths)}.")
        return dict(zip(keys, paths, strict=True))
