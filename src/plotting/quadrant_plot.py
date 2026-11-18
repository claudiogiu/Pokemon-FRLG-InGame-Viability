import logging
from pathlib import Path
from typing import Dict, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Rectangle
from PIL import Image

from src.domain.entities import PokemonField
from src.settings import StudyConfig

logger = logging.getLogger(__name__)

_AXIS_PADDING_SHARE: float = 0.06
_RGBA_MAXIMUM: float = 255.0
_QUADRANT_INSET: float = 0.018
_TITLE_SIZE: float = 20.0
_SUBTITLE_SIZE: float = 12.5
_QUADRANT_LABEL_SIZE: float = 15.0
_AXIS_LABEL_SIZE: float = 13.5
_TICK_SIZE: float = 11.0


class QuadrantPlot:
    """
    Interface for rendering the quadrant map of the study, where every
    evolutionary line is drawn with its in-game sprite at the coordinates of
    its estimated strength and of the timing of its contribution, over four
    lightly tinted quadrants, so that the profile of each line is read at a
    glance with minimal text.

    Attributes:
        config (StudyConfig): Configuration of the study, including axes, report, and style.
        figures_dir (Path): Folder receiving the figure.

    Methods:
        _load_sprite(path: Path) -> np.ndarray:
            Returns the sprite cropped to its visible pixels as an RGBA array.

        _draw_quadrants(axes: Axes, medians: Tuple[float, float]) -> None:
            Draws the tinted quadrants, the median lines, and the quadrant names.

        _draw_sprites(axes: Axes, population: pd.DataFrame, sprites: Dict[str, Path]) -> None:
            Places every sprite at its coordinates.

        build(population: pd.DataFrame, sprites: Dict[str, Path], medians: Tuple[float, float], subtitle: str) -> Path:
            Renders the quadrant map and returns its location.
    """

    def __init__(self, config: StudyConfig, figures_dir: Path, font_family: str) -> None:
        figures_dir.mkdir(parents=True, exist_ok=True)
        self.config: StudyConfig = config
        self.figures_dir: Path = figures_dir
        plt.rcParams["font.family"] = font_family
        plt.rcParams["mathtext.fontset"] = "custom"
        for role in ("rm", "it", "bf", "sf", "cal", "tt"):
            plt.rcParams[f"mathtext.{role}"] = font_family
        logger.info(f"Quadrant plot initialization completed. Font family: {font_family}.")

    def _load_sprite(self, path: Path) -> np.ndarray:
        image = Image.open(path).convert("RGBA")
        bounding_box = image.getbbox()
        if bounding_box is not None:
            image = image.crop(bounding_box)
        return np.asarray(image, dtype=float) / _RGBA_MAXIMUM

    def _draw_quadrants(self, axes: Axes, medians: Tuple[float, float]) -> None:
        style = self.config.style
        x_median, y_median = medians
        (x_low, x_high), (y_low, y_high) = axes.get_xlim(), axes.get_ylim()
        regions = (
            (x_low, y_low, x_median - x_low, y_median - y_low),
            (x_median, y_low, x_high - x_median, y_median - y_low),
            (x_low, y_median, x_median - x_low, y_high - y_median),
            (x_median, y_median, x_high - x_median, y_high - y_median),
        )
        for (x_start, y_start, width, height), color in zip(regions, style.quadrant_colors, strict=True):
            axes.add_patch(Rectangle((x_start, y_start), width, height, facecolor=color, alpha=style.quadrant_alpha, linewidth=0.0, zorder=0))
        axes.axvline(x_median, color=style.quadrant_line, linewidth=1.0, linestyle="--", zorder=1)
        axes.axhline(y_median, color=style.quadrant_line, linewidth=1.0, linestyle="--", zorder=1)
        placements = (
            (_QUADRANT_INSET, _QUADRANT_INSET, "left", "bottom"),
            (1 - _QUADRANT_INSET, _QUADRANT_INSET, "right", "bottom"),
            (_QUADRANT_INSET, 1 - _QUADRANT_INSET, "left", "top"),
            (1 - _QUADRANT_INSET, 1 - _QUADRANT_INSET, "right", "top"),
        )
        for text, color, (x_position, y_position, horizontal, vertical) in zip(
            self.config.axes.quadrant_labels, style.quadrant_label_colors, placements, strict=True
        ):
            axes.text(
                x_position, y_position, text, transform=axes.transAxes, ha=horizontal, va=vertical,
                fontsize=_QUADRANT_LABEL_SIZE, fontweight="bold", color=color, zorder=1,
            )

    def _draw_sprites(self, axes: Axes, population: pd.DataFrame, sprites: Dict[str, Path]) -> None:
        for _, row in population.iterrows():
            species = row[PokemonField.SPECIES.value]
            if species not in sprites:
                continue
            image = OffsetImage(self._load_sprite(sprites[species]), zoom=self.config.report.sprite_zoom, interpolation="nearest")
            position = (row[PokemonField.AXIS_X.value], row[PokemonField.AXIS_Y.value])
            axes.add_artist(AnnotationBbox(image, position, frameon=False, zorder=3))

    def build(self, population: pd.DataFrame, sprites: Dict[str, Path], medians: Tuple[float, float], subtitle: str) -> Path:
        logger.info(f"Starting rendering of the quadrant map. Lines: {len(population)}.")
        style = self.config.style
        report = self.config.report
        axes_config = self.config.axes
        figure, axes = plt.subplots(figsize=(report.figure_width, report.figure_height), facecolor=style.surface)
        axes.set_facecolor(style.surface)
        x_values = population[PokemonField.AXIS_X.value]
        y_values = population[PokemonField.AXIS_Y.value]
        x_padding = (x_values.max() - x_values.min()) * _AXIS_PADDING_SHARE
        y_padding = (y_values.max() - y_values.min()) * _AXIS_PADDING_SHARE
        axes.set_xlim(x_values.min() - x_padding, x_values.max() + x_padding)
        axes.set_ylim(y_values.min() - y_padding, y_values.max() + y_padding)
        self._draw_quadrants(axes, medians)
        self._draw_sprites(axes, population, sprites)
        axes.grid(True, color=style.grid, linewidth=0.6, linestyle="--", alpha=0.6)
        axes.set_axisbelow(True)
        for side in ("top", "right"):
            axes.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            axes.spines[side].set_color(style.quadrant_line)
        axes.tick_params(colors=style.text_secondary, labelsize=_TICK_SIZE)
        axes.set_xlabel(axes_config.x_label, fontsize=_AXIS_LABEL_SIZE, color=style.text_primary)
        axes.set_ylabel(axes_config.y_label, fontsize=_AXIS_LABEL_SIZE, color=style.text_primary)
        figure.suptitle(report.title, fontsize=_TITLE_SIZE, fontweight="bold", color=style.text_primary)
        axes.set_title(subtitle, fontsize=_SUBTITLE_SIZE, color=style.text_secondary, pad=12)
        figure.tight_layout()
        path = self.figures_dir / report.figure_name
        figure.savefig(path, dpi=report.figure_dpi, facecolor=style.surface, metadata={"Software": None})
        plt.close(figure)
        logger.info(f"Quadrant map successfully rendered. File: {path.name}.")
        return path
