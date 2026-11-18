from typing import Any, Dict, List, Protocol


class PokemonDataSource(Protocol):
    """
    Interface for retrieving the raw documents describing species, moves, and
    types, so that the dataset construction does not depend on the provider.

    Attributes:
        None.

    Methods:
        fetch(resource: str) -> Dict[str, Any]:
            Returns the document of the requested resource path.

        fetch_many(resources: List[str]) -> Dict[str, Dict[str, Any]]:
            Returns the documents of the requested resource paths, keyed by path.
    """

    def fetch(self, resource: str) -> Dict[str, Any]: ...

    def fetch_many(self, resources: List[str]) -> Dict[str, Dict[str, Any]]: ...
