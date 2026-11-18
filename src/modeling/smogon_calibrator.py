import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge

from src.domain.entities import PokemonField
from src.settings import CalibrationConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalibrationResult:
    """
    Interface for the outcome of the calibration against the Smogon tiers.

    Attributes:
        weights (Dict[str, float]): Non-negative weight of every oriented feature.
        in_sample_spearman (float): Spearman coefficient between fitted scores and tiers.
        cross_validated_spearman (float): Spearman coefficient between leave-one-out predictions and tiers.
        equal_weight_spearman (float): Spearman coefficient obtained with equal weights, as an uncalibrated baseline.
        within_one_tier (float): Share of lines whose predicted tier differs from the Smogon tier by at most one step.
        sample_size (int): Number of tiered lines used for the calibration.

    Methods:
        None.
    """

    weights: Dict[str, float]
    in_sample_spearman: float
    cross_validated_spearman: float
    equal_weight_spearman: float
    within_one_tier: float
    sample_size: int


class SmogonCalibrator:
    """
    Interface for weighting the battle and ease features so that their
    combination agrees as closely as possible with the Smogon in-game tiers,
    using a ridge regression with non-negative weights on features oriented
    so that higher always means better, and judging the agreement with
    leave-one-out predictions so that the reported accuracy is not inflated
    by fitting.

    Attributes:
        config (CalibrationConfig): Feature groups, orientation, regularization, and target.
        tier_scores (Dict[str, int]): Ordinal score of each Smogon tier letter.

    Methods:
        features() -> List[str]:
            Returns every calibrated feature, battle features first.

        oriented_matrix(population: pd.DataFrame) -> pd.DataFrame:
            Returns the standardized features oriented so that higher means better.

        _fit(matrix: np.ndarray, target: np.ndarray) -> Ridge:
            Returns the fitted non-negative ridge model.

        _predicted_tiers(scores: pd.Series, tiers: pd.Series) -> pd.Series:
            Returns tier letters assigned by rank so that the predicted distribution matches the Smogon one.

        calibrate(population: pd.DataFrame) -> Tuple[pd.DataFrame, CalibrationResult]:
            Returns the population with predicted scores and tiers, and the calibration summary.
    """

    def __init__(self, config: CalibrationConfig, tier_scores: Dict[str, int]) -> None:
        self.config: CalibrationConfig = config
        self.tier_scores: Dict[str, int] = tier_scores
        logger.info("Smogon calibrator initialization completed.")

    def features(self) -> List[str]:
        return list(self.config.battle_features) + list(self.config.ease_features)

    def oriented_matrix(self, population: pd.DataFrame) -> pd.DataFrame:
        values = population[self.features()].astype(float)
        if values.isna().any().any():
            logger.warning(f"Missing feature values replaced by the mean. Cells: {int(values.isna().sum().sum())}.")
        standardized = ((values - values.mean()) / values.std(ddof=0)).fillna(0.0)
        signs = [-1.0 if feature in self.config.negative_features else 1.0 for feature in self.features()]
        return standardized * signs

    def _fit(self, matrix: np.ndarray, target: np.ndarray) -> Ridge:
        return Ridge(alpha=self.config.regularization, positive=True).fit(matrix, target)

    def _predicted_tiers(self, scores: pd.Series, tiers: pd.Series) -> pd.Series:
        ordered_letters = sorted(self.tier_scores, key=lambda letter: self.tier_scores[letter], reverse=True)
        counts = tiers.value_counts()
        shares = np.array([counts.get(letter, 0) for letter in ordered_letters], dtype=float)
        boundaries = np.cumsum(shares / shares.sum()) * len(scores)
        ranks = scores.rank(ascending=False, method="first").to_numpy() - 1
        positions = np.searchsorted(boundaries, ranks, side="right")
        return pd.Series([ordered_letters[min(position, len(ordered_letters) - 1)] for position in positions], index=scores.index)

    def calibrate(self, population: pd.DataFrame) -> Tuple[pd.DataFrame, CalibrationResult]:
        logger.info(f"Starting calibration against the Smogon tiers. Features: {len(self.features())}.")
        oriented = self.oriented_matrix(population)
        target = population[self.config.target]
        tiered = target.notna().to_numpy()
        matrix, labels = oriented.to_numpy()[tiered], target.to_numpy()[tiered]
        if tiered.sum() <= len(self.features()):
            raise ValueError("The calibration requires more tiered lines than features.")
        model = self._fit(matrix, labels)
        cross_validated = np.empty(len(labels))
        for index in range(len(labels)):
            mask = np.arange(len(labels)) != index
            cross_validated[index] = self._fit(matrix[mask], labels[mask]).predict(matrix[index : index + 1])[0]
        enriched = population.copy()
        enriched[PokemonField.PREDICTED_SCORE.value] = model.predict(oriented.to_numpy())
        enriched[PokemonField.CROSS_VALIDATED_SCORE.value] = np.nan
        enriched.loc[tiered, PokemonField.CROSS_VALIDATED_SCORE.value] = cross_validated
        tier_letters = population[PokemonField.SMOGON_TIER.value]
        enriched[PokemonField.PREDICTED_TIER.value] = None
        enriched.loc[tiered, PokemonField.PREDICTED_TIER.value] = self._predicted_tiers(
            enriched.loc[tiered, PokemonField.CROSS_VALIDATED_SCORE.value], tier_letters[tiered]
        )
        predicted_scores = enriched.loc[tiered, PokemonField.PREDICTED_TIER.value].map(self.tier_scores).to_numpy()
        result = CalibrationResult(
            weights=dict(zip(self.features(), (float(weight) for weight in model.coef_), strict=True)),
            in_sample_spearman=float(spearmanr(model.predict(matrix), labels)[0]),
            cross_validated_spearman=float(spearmanr(cross_validated, labels)[0]),
            equal_weight_spearman=float(spearmanr(matrix.mean(axis=1), labels)[0]),
            within_one_tier=float(np.mean(np.abs(predicted_scores - labels) <= 1)),
            sample_size=int(tiered.sum()),
        )
        weight_report = ". ".join(f"{name}: {weight:.3f}" for name, weight in result.weights.items())
        logger.info(
            f"Calibration against the Smogon tiers successfully completed. "
            f"Lines: {result.sample_size}. "
            f"Spearman in sample: {result.in_sample_spearman:.3f}. "
            f"Spearman leave-one-out: {result.cross_validated_spearman:.3f}. "
            f"Spearman with equal weights: {result.equal_weight_spearman:.3f}. "
            f"Within one tier: {result.within_one_tier:.3f}. "
            f"Weights: {weight_report}."
        )
        return enriched, result
