import logging
import tomllib
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
CONFIG_TOML_PATH: Path = PROJECT_ROOT / "config.toml"
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
PROCESSED_DIR: Path = DATA_DIR / "processed"
FIGURES_DIR: Path = PROJECT_ROOT / "figures"


class SourceConfig(BaseModel):
    """Parameters of the pinned PokéAPI static data and sprites, and of the game generation under study."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    commit: str
    api_prefix: str
    document_name: str
    timeout_seconds: float
    worker_count: int
    generation_index: int
    versions: List[str]
    pokedex_limit: int
    sprite_version: str
    sprite_repository: str
    sprite_commit: str


class PretConfig(BaseModel):
    """Pinned location of the pokefirered decompilation files providing the exact third-generation game data."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    commit: str
    species_file: str
    level_up_file: str
    level_up_pointer_file: str
    tmhm_file: str
    tutor_file: str
    moves_file: str
    parties_file: str


class CampaignConfig(BaseModel):
    """Assumptions of the simulated duels against the major battles of the game."""

    model_config = ConfigDict(frozen=True)

    player_iv: int
    player_ev: int
    trainer_iv_scale: int
    maximum_iv: int
    default_move_count: int
    damage_roll_mean: float
    stab_multiplier: float
    intimidate_multiplier: float
    league_player_level: int
    turn_weight: float
    sleep_free_turns: float
    paralysis_speed_factor: float
    paralysis_action_rate: float
    maximum_setup_uses: int


class PopulationConfig(BaseModel):
    """Selection of the evolutionary lines admitted to the analysis."""

    model_config = ConfigDict(frozen=True)

    excluded_species: List[str]


class CalibrationConfig(BaseModel):
    """Feature groups and regularization of the calibration against the community tiers."""

    model_config = ConfigDict(frozen=True)

    battle_features: List[str]
    ease_features: List[str]
    negative_features: List[str]
    regularization: float
    target: str


class AxesConfig(BaseModel):
    """Columns and labels of the two axes of the quadrant map and names of its four quadrants."""

    model_config = ConfigDict(frozen=True)

    x_feature: str
    x_label: str
    y_feature: str
    y_label: str
    quadrant_labels: List[str]


class DatasetConfig(BaseModel):
    """Names of the rebuilt dataset files."""

    model_config = ConfigDict(frozen=True)

    lines_name: str
    battles_name: str


class ReportConfig(BaseModel):
    """Title, names, and dimensions of the produced figure and results table."""

    model_config = ConfigDict(frozen=True)

    title: str
    subtitle: str
    figure_name: str
    results_name: str
    figure_dpi: int
    sprite_zoom: float
    figure_width: float
    figure_height: float


class FontConfig(BaseModel):
    """Pinned location and family of the open font used by the figure, downloaded so that the rendering does not depend on the system fonts."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    commit: str
    family: str
    files: List[str]


class StyleConfig(BaseModel):
    """Visual parameters of the figure, kept apart so that the style can be iterated without code changes."""

    model_config = ConfigDict(frozen=True)

    surface: str
    text_primary: str
    text_secondary: str
    grid: str
    quadrant_line: str
    quadrant_colors: List[str]
    quadrant_alpha: float
    quadrant_label_colors: List[str]


class StrategyConfig(BaseModel):
    """Moves and abilities enabling the setup, sleep, and paralysis plans of the simulated duels."""

    model_config = ConfigDict(frozen=True)

    sleep_moves: List[str]
    paralysis_moves: List[str]
    type_checked_status_moves: List[str]
    sleep_blocking_abilities: List[str]
    paralysis_blocking_abilities: List[str]
    setup_moves: Dict[str, Dict[str, int]]


class AcquisitionConfig(BaseModel):
    """Rules translating encounter rate, Safari Zone, Sevii Islands, trades, and Game Corner prices into an acquisition effort."""

    model_config = ConfigDict(frozen=True)

    chance_thresholds: List[int]
    safari_prefix: str
    safari_penalty: int
    sevii_badges: int
    sevii_penalty: int
    npc_trade_effort: int
    coin_thresholds: List[int]
    prize_corner_location: str
    maximum_effort: int
    prize_corner_coins: Dict[str, int]


class StudyConfig(BaseModel):
    """Complete configuration of the study, grouped by topic."""

    model_config = ConfigDict(frozen=True)

    source: SourceConfig
    pret: PretConfig
    campaign: CampaignConfig
    population: PopulationConfig
    calibration: CalibrationConfig
    axes: AxesConfig
    dataset: DatasetConfig
    report: ReportConfig
    fonts: FontConfig
    style: StyleConfig
    strategies: StrategyConfig
    acquisition: AcquisitionConfig
    seed: int


class StudyConfigLoader:
    """
    Interface for loading and validating the parameter sections of the single
    configuration document of the project, so that every assumption of the
    study is declared rather than embedded in the source.

    Attributes:
        config_path (Path): Filesystem location of the configuration TOML document.

    Methods:
        load() -> StudyConfig:
            Reads, validates, and returns the study configuration.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path: Path = config_path or CONFIG_TOML_PATH

    def load(self) -> StudyConfig:
        if not self.config_path.is_file():
            raise ValueError(f"The configuration file does not exist: {self.config_path}.")
        logger.info("Starting loading of the study configuration.")
        with self.config_path.open("rb") as f:
            raw = tomllib.load(f)
        config = StudyConfig(
            source=SourceConfig(**raw["source"]),
            pret=PretConfig(**raw["pret"]),
            campaign=CampaignConfig(**raw["campaign"]),
            population=PopulationConfig(**raw["population"]),
            calibration=CalibrationConfig(**raw["calibration"]),
            axes=AxesConfig(**raw["axes"]),
            dataset=DatasetConfig(**raw["dataset"]),
            report=ReportConfig(**raw["report"]),
            fonts=FontConfig(**raw["fonts"]),
            style=StyleConfig(**raw["style"]),
            strategies=StrategyConfig(**raw["strategies"]),
            acquisition=AcquisitionConfig(**raw["acquisition"]),
            seed=raw["study"]["seed"],
        )
        if len(config.axes.quadrant_labels) != 4 or len(config.style.quadrant_colors) != 4 or len(config.style.quadrant_label_colors) != 4:
            raise ValueError("The quadrant map requires exactly four quadrant labels, four quadrant colors, and four label colors.")
        if not config.calibration.battle_features or not config.calibration.ease_features:
            raise ValueError("The calibration requires at least one battle feature and one ease feature.")
        if not 0.0 <= config.campaign.turn_weight <= 1.0:
            raise ValueError("The turn weight of the duel efficiency must lie between zero and one.")
        logger.info(
            f"Study configuration successfully loaded. "
            f"Versions: {config.source.versions}. "
            f"Battle features: {len(config.calibration.battle_features)}. "
            f"Ease features: {len(config.calibration.ease_features)}. "
            f"Seed: {config.seed}. "
        )
        return config
