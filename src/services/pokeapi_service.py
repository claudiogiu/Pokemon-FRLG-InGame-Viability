import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

from src.settings import RAW_DIR, SourceConfig

logger = logging.getLogger(__name__)


class PokeApiService:
    """
    Interface for retrieving documents from the static PokéAPI data
    repository at a pinned commit, with a local file cache, so that every
    resource is downloaded once and the dataset is reproducible byte for byte.

    Attributes:
        config (SourceConfig): Parameters of the remote source.
        cache_dir (Path): Folder holding the cached documents.
        _session (requests.Session): Persistent HTTP session.

    Methods:
        _cache_path(resource: str) -> Path:
            Returns the cache file associated with the resource path.

        fetch(resource: str) -> Dict[str, Any]:
            Returns the document of the resource, from cache when available.

        fetch_many(resources: List[str]) -> Dict[str, Dict[str, Any]]:
            Returns the documents of several resources, retrieved concurrently.
    """

    def __init__(self, config: SourceConfig, cache_dir: Optional[Path] = None) -> None:
        resolved_dir = cache_dir or (RAW_DIR / "pokeapi")
        resolved_dir.mkdir(parents=True, exist_ok=True)
        self.config: SourceConfig = config
        self.cache_dir: Path = resolved_dir
        self._session: requests.Session = requests.Session()
        self._session.mount("https://", HTTPAdapter(pool_maxsize=config.worker_count))
        logger.info("PokéAPI service initialization completed.")

    def _cache_path(self, resource: str) -> Path:
        return self.cache_dir / f"{resource.strip('/').replace('/', '__')}.json"

    def fetch(self, resource: str) -> Dict[str, Any]:
        cache_path = self._cache_path(resource)
        if cache_path.is_file():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        url = f"{self.config.base_url}/{self.config.commit}/{self.config.api_prefix}/{resource.strip('/')}/{self.config.document_name}"
        logger.debug(f"Sending GET request to the PokéAPI static data. Endpoint: {url}.")
        try:
            response = self._session.get(url, timeout=self.config.timeout_seconds)
            response.raise_for_status()
            document = response.json()
        except (requests.RequestException, ValueError) as e:
            logger.error(f"PokéAPI request failed: {e}")
            raise RuntimeError(f"The PokéAPI static data did not return a valid document for {resource}.") from e
        cache_path.write_text(json.dumps(document), encoding="utf-8")
        return document

    def fetch_many(self, resources: List[str]) -> Dict[str, Dict[str, Any]]:
        unique_resources = sorted(set(resources))
        logger.info(f"Starting retrieval of PokéAPI documents. Resources: {len(unique_resources)}.")
        with ThreadPoolExecutor(max_workers=self.config.worker_count) as executor:
            documents = list(executor.map(self.fetch, unique_resources))
        logger.info(f"PokéAPI documents successfully retrieved. Resources: {len(documents)}.")
        return dict(zip(unique_resources, documents, strict=True))
