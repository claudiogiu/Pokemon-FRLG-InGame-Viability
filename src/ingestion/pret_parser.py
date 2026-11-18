import logging
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, List, Tuple

from src.domain.entities import GameMove, SpeciesRecord, TrainerPokemon
from src.services.pret_service import PretService
from src.settings import StudyConfig

logger = logging.getLogger(__name__)

_STAT_FIELDS: Dict[str, str] = {
    "baseHP": "hp",
    "baseAttack": "attack",
    "baseDefense": "defense",
    "baseSpeed": "speed",
    "baseSpAttack": "special_attack",
    "baseSpDefense": "special_defense",
}
_SPECIES_BLOCK = re.compile(r"\[SPECIES_(\w+)\]\s*=\s*\n\s*\{(.*?)\n    \},", re.S)
_LEARNSET_BLOCK = re.compile(r"static const u16 (s\w+LevelUpLearnset)\[\] = \{(.*?)\};", re.S)
_LEARNSET_ENTRY = re.compile(r"LEVEL_UP_MOVE\(\s*(\d+),\s*MOVE_(\w+)\)")
_POINTER_ENTRY = re.compile(r"\[SPECIES_(\w+)\]\s*=\s*(s\w+LevelUpLearnset)")
_TMHM_BLOCK = re.compile(r"\[SPECIES_(\w+)\]\s*=\s*TMHM_LEARNSET\((.*?)\),\n", re.S)
_TMHM_ENTRY = re.compile(r"TMHM\((?:TM|HM)\d+_(\w+)\)")
_TUTOR_BLOCK = re.compile(r"\[SPECIES_(\w+)\]\s*=\s*(TUTOR\(.*?),\n\n", re.S)
_TUTOR_ENTRY = re.compile(r"TUTOR\(MOVE_(\w+)\)")
_MOVE_BLOCK = re.compile(r"\[MOVE_(\w+)\]\s*=\s*\n\s*\{(.*?)\n    \},", re.S)
_PARTY_BLOCK = re.compile(r"static const struct TrainerMon\w+ (sParty_\w+)\[\] = \{(.*?)\n\};", re.S)
_PARTY_MEMBER = re.compile(r"\{\s*\.iv(.*?)\n    \}", re.S)
_MEMBER_FIELDS = re.compile(r"=\s*(\d+),.*?\.lvl = (\d+),.*?\.species = SPECIES_(\w+)", re.S)
_MEMBER_MOVES = re.compile(r"\.moves = \{(.*?)\}", re.S)


@dataclass(frozen=True)
class PretData:
    """
    Interface for the cartridge data parsed from the decompilation, keyed by
    species, move, or party name.

    Attributes:
        species (Dict[str, SpeciesRecord]): Battle data of every species.
        level_up (Dict[str, Tuple[Tuple[int, str], ...]]): Level and move of every level-up learnset entry.
        machines (Dict[str, Tuple[str, ...]]): Technical and hidden machine moves compatible with every species.
        tutors (Dict[str, Tuple[str, ...]]): Tutor moves compatible with every species.
        moves (Dict[str, GameMove]): Definition of every move.
        parties (Dict[str, Tuple[TrainerPokemon, ...]]): Trainer parties keyed by their source symbol.

    Methods:
        None.
    """

    species: Dict[str, SpeciesRecord]
    level_up: Dict[str, Tuple[Tuple[int, str], ...]]
    machines: Dict[str, Tuple[str, ...]]
    tutors: Dict[str, Tuple[str, ...]]
    moves: Dict[str, GameMove]
    parties: Dict[str, Tuple[TrainerPokemon, ...]]


class PretParser:
    """
    Interface for translating the C sources of the pokefirered decompilation
    into typed records, so that the battle simulation relies on the exact
    values of the cartridge rather than on later revisions.

    Attributes:
        config (StudyConfig): Configuration of the study.
        service (PretService): Provider of the decompilation files.

    Methods:
        _name(constant: str) -> str:
            Returns the lowercase hyphenated name of a cartridge constant suffix.

        _field(block: str, field: str) -> str:
            Returns the raw value of a field inside a C initializer block.

        _parse_species(text: str) -> Dict[str, SpeciesRecord]:
            Returns the species records of the species file.

        _parse_level_up(text: str, pointers: str) -> Dict[str, Tuple[Tuple[int, str], ...]]:
            Returns the level-up learnsets keyed by species.

        _parse_machines(text: str) -> Dict[str, Tuple[str, ...]]:
            Returns the machine-compatible moves keyed by species.

        _parse_tutors(text: str) -> Dict[str, Tuple[str, ...]]:
            Returns the tutor-compatible moves keyed by species.

        _parse_moves(text: str) -> Dict[str, GameMove]:
            Returns the move definitions keyed by move name.

        _parse_parties(text: str) -> Dict[str, Tuple[TrainerPokemon, ...]]:
            Returns the trainer parties keyed by symbol.

        parse() -> PretData:
            Retrieves and parses every decompilation file of the study.
    """

    def __init__(self, config: StudyConfig, service: PretService) -> None:
        self.config: StudyConfig = config
        self.service: PretService = service
        logger.info("Decompilation parser initialization completed.")

    def _name(self, constant: str) -> str:
        return constant.lower().replace("_", "-")

    def _field(self, block: str, field: str) -> str:
        match = re.search(rf"\.{field}\s*=\s*(\{{[^}}]*\}}|[^,\n]+)", block)
        if match is None:
            raise RuntimeError(f"The decompilation block does not define the field {field}.")
        return match.group(1).strip()

    def _parse_species(self, text: str) -> Dict[str, SpeciesRecord]:
        records: Dict[str, SpeciesRecord] = {}
        for constant, block in _SPECIES_BLOCK.findall(text):
            if ".baseHP" not in block:
                continue
            stats = {name: int(self._field(block, field)) for field, name in _STAT_FIELDS.items()}
            types = tuple(dict.fromkeys(re.findall(r"TYPE_(\w+)", self._field(block, "types"))))
            abilities = tuple(
                dict.fromkeys(
                    ability for ability in re.findall(r"ABILITY_\w+", self._field(block, "abilities"))
                    if ability != "ABILITY_NONE"
                )
            )
            records[self._name(constant)] = SpeciesRecord(
                name=self._name(constant),
                stats=MappingProxyType(stats),
                types=tuple(self._name(type_name) for type_name in types),
                abilities=abilities,
                growth_rate=self._field(block, "growthRate"),
            )
        return records

    def _parse_level_up(self, text: str, pointers: str) -> Dict[str, Tuple[Tuple[int, str], ...]]:
        learnsets = {
            symbol: tuple((int(level), self._name(move)) for level, move in _LEARNSET_ENTRY.findall(body))
            for symbol, body in _LEARNSET_BLOCK.findall(text)
        }
        return {self._name(constant): learnsets[symbol] for constant, symbol in _POINTER_ENTRY.findall(pointers)}

    def _parse_machines(self, text: str) -> Dict[str, Tuple[str, ...]]:
        return {
            self._name(constant): tuple(self._name(move) for move in _TMHM_ENTRY.findall(body))
            for constant, body in _TMHM_BLOCK.findall(text)
        }

    def _parse_tutors(self, text: str) -> Dict[str, Tuple[str, ...]]:
        return {
            self._name(constant): tuple(self._name(move) for move in _TUTOR_ENTRY.findall(body))
            for constant, body in _TUTOR_BLOCK.findall(text)
        }

    def _parse_moves(self, text: str) -> Dict[str, GameMove]:
        moves: Dict[str, GameMove] = {}
        for constant, block in _MOVE_BLOCK.findall(text):
            moves[self._name(constant)] = GameMove(
                name=self._name(constant),
                effect=self._field(block, "effect"),
                power=int(self._field(block, "power")),
                move_type=self._name(self._field(block, "type").replace("TYPE_", "")),
                accuracy=int(self._field(block, "accuracy")),
            )
        return moves

    def _parse_parties(self, text: str) -> Dict[str, Tuple[TrainerPokemon, ...]]:
        scale = self.config.campaign.trainer_iv_scale
        maximum = self.config.campaign.maximum_iv
        parties: Dict[str, Tuple[TrainerPokemon, ...]] = {}
        for symbol, body in _PARTY_BLOCK.findall(text):
            members: List[TrainerPokemon] = []
            for member in _PARTY_MEMBER.findall(body):
                fields = _MEMBER_FIELDS.search(member)
                if fields is None:
                    continue
                iv, level, species = fields.groups()
                moves_match = _MEMBER_MOVES.search(member)
                moves = moves_match.group(1) if moves_match is not None else ""
                members.append(
                    TrainerPokemon(
                        species=self._name(species),
                        level=int(level),
                        individual_value=round(int(iv) * maximum / scale),
                        moves=tuple(
                            self._name(move) for move in re.findall(r"MOVE_(\w+)", moves) if move != "NONE"
                        ),
                    )
                )
            if members:
                parties[symbol] = tuple(members)
        return parties

    def parse(self) -> PretData:
        logger.info("Starting parsing of the decompilation files.")
        pret = self.config.pret
        data = PretData(
            species=self._parse_species(self.service.fetch(pret.species_file)),
            level_up=self._parse_level_up(
                self.service.fetch(pret.level_up_file), self.service.fetch(pret.level_up_pointer_file)
            ),
            machines=self._parse_machines(self.service.fetch(pret.tmhm_file)),
            tutors=self._parse_tutors(self.service.fetch(pret.tutor_file)),
            moves=self._parse_moves(self.service.fetch(pret.moves_file)),
            parties=self._parse_parties(self.service.fetch(pret.parties_file)),
        )
        logger.info(
            f"Decompilation files successfully parsed. "
            f"Species: {len(data.species)}. "
            f"Learnsets: {len(data.level_up)}. "
            f"Machine sets: {len(data.machines)}. "
            f"Tutor sets: {len(data.tutors)}. "
            f"Moves: {len(data.moves)}. "
            f"Parties: {len(data.parties)}. "
        )
        return data
