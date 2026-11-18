import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from src.domain.ports import PokemonDataSource
from src.settings import SourceConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawBundle:
    """
    Interface for the raw documents required to build the study dataset,
    grouped by resource family and keyed by identifier.

    Attributes:
        pokemon (Dict[int, Dict[str, Any]]): Pokémon documents keyed by National Pokédex number.
        species (Dict[int, Dict[str, Any]]): Species documents keyed by National Pokédex number.
        encounters (Dict[int, List[Dict[str, Any]]]): Encounter documents keyed by National Pokédex number.
        evolution_chains (Dict[str, Dict[str, Any]]): Evolution chain documents keyed by resource path.
        types (Dict[str, Dict[str, Any]]): Type documents keyed by type name.

    Methods:
        None.
    """

    pokemon: Dict[int, Dict[str, Any]]
    species: Dict[int, Dict[str, Any]]
    encounters: Dict[int, List[Dict[str, Any]]]
    evolution_chains: Dict[str, Dict[str, Any]]
    types: Dict[str, Dict[str, Any]]


class RawCollector:
    """
    Interface for collecting every raw document needed by the study from a
    Pokémon data source, so that the feature construction works on a complete
    in-memory bundle.

    Attributes:
        source (PokemonDataSource): Provider of the raw documents.
        config (SourceConfig): Parameters of the source and of the game under study.

    Methods:
        _resource_path(url: str) -> str:
            Returns the resource path of a PokéAPI address, without the version prefix.


        collect() -> RawBundle:
            Retrieves and returns the raw documents of the study.
    """

    def __init__(self, source: PokemonDataSource, config: SourceConfig) -> None:
        self.source: PokemonDataSource = source
        self.config: SourceConfig = config
        logger.info("Raw collector initialization completed.")

    def _resource_path(self, url: str) -> str:
        return url.split("/api/v2/", 1)[-1].strip("/")


    def collect(self) -> RawBundle:
        logger.info(f"Starting collection of raw documents. Pokédex limit: {self.config.pokedex_limit}.")
        identifiers = list(range(1, self.config.pokedex_limit + 1))
        pokemon_documents = self.source.fetch_many([f"pokemon/{i}" for i in identifiers])
        species_documents = self.source.fetch_many([f"pokemon-species/{i}" for i in identifiers])
        encounter_documents = self.source.fetch_many([f"pokemon/{i}/encounters" for i in identifiers])
        pokemon = {i: pokemon_documents[f"pokemon/{i}"] for i in identifiers}
        species = {i: species_documents[f"pokemon-species/{i}"] for i in identifiers}
        encounters = {i: encounter_documents[f"pokemon/{i}/encounters"] for i in identifiers}
        chain_paths = [self._resource_path(document["evolution_chain"]["url"]) for document in species.values()]
        evolution_chains = self.source.fetch_many(chain_paths)
        type_index = self.source.fetch("type")
        type_paths = {entry["name"]: self._resource_path(entry["url"]) for entry in type_index["results"]}
        type_documents = self.source.fetch_many(list(type_paths.values()))
        types = {name: type_documents[path] for name, path in type_paths.items()}
        logger.info(
            f"Raw documents successfully collected. "
            f"Pokémon: {len(pokemon)}. "
            f"Evolution chains: {len(evolution_chains)}. "
            f"Types: {len(types)}. "
        )
        return RawBundle(
            pokemon=pokemon,
            species=species,
            encounters=encounters,
            evolution_chains=evolution_chains,
            types=types,
        )
