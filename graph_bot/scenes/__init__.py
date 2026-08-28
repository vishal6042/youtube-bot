"""Manim concept scenes (the 'teachable' pillar).

Each module defines one BrandScene subclass. Register it below so topics can
reference it by name via `scene:` in topics.yaml.
"""
from __future__ import annotations

# scene key -> (module path, class name)
SCENES: dict[str, tuple[str, str]] = {
    "gradient_descent": ("graph_bot.scenes.gradient_descent", "GradientDescent"),
    "simpsons_paradox": ("graph_bot.scenes.simpsons_paradox", "SimpsonsParadox"),
    "kmeans": ("graph_bot.scenes.kmeans", "KMeans"),
    # ML Basics series (narrated)
    "ml_what_is": ("graph_bot.scenes.ml_what_is", "WhatIsML"),
    "ml_overfitting": ("graph_bot.scenes.ml_overfitting", "Overfitting"),
    "ml_train_test": ("graph_bot.scenes.ml_train_test", "TrainTestSplit"),
    "ml_features_labels": ("graph_bot.scenes.ml_features_labels", "FeaturesLabels"),
    "ml_supervised": ("graph_bot.scenes.ml_supervised", "SupervisedVsUnsupervised"),
    "ml_class_vs_reg": ("graph_bot.scenes.ml_class_vs_reg", "ClassificationVsRegression"),
    "ml_loss": ("graph_bot.scenes.ml_loss", "LossFunction"),
    "ml_train_infer": ("graph_bot.scenes.ml_train_infer", "TrainingVsInference"),
    "ml_bias_variance": ("graph_bot.scenes.ml_bias_variance", "BiasVariance"),
    "ml_accuracy_lies": ("graph_bot.scenes.ml_accuracy_lies", "AccuracyLies"),
    # How Charts Lie series (narrated)
    "lie_truncated_axis": ("graph_bot.scenes.lie_truncated_axis", "TruncatedAxis"),
    "lie_inverted_axis": ("graph_bot.scenes.lie_inverted_axis", "InvertedAxis"),
    "lie_mean_median": ("graph_bot.scenes.lie_mean_median", "MeanVsMedian"),
    "lie_area_radius": ("graph_bot.scenes.lie_area_radius", "AreaVsRadius"),
}
