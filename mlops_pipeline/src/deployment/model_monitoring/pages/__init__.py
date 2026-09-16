"""Dash page renderers."""

from .feature_drift import layout as feature_drift_layout
from .operations import layout as operations_layout
from .overview import layout as overview_layout
from .performance import layout as performance_layout
from .predictions import layout as predictions_layout

__all__ = [
    "feature_drift_layout",
    "operations_layout",
    "overview_layout",
    "performance_layout",
    "predictions_layout",
]
