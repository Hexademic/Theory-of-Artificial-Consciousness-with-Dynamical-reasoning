"""
minimalkith.src — Minimal interoceptive organism reference implementation.

Public API
----------
Core components:
    Metabolic, ISE, RitualGate, PredictiveModel, Actuator, Proprioceptor

Environment:
    Environment, EnvironmentConfig

Interoceptive loop:
    InteroceptiveLoop, InteroceptiveState

Persistence:
    Database

Harness:
    HarnessConfig, run_single, run_batch

Analysis (six functions):
    compute_peri_event_histogram
    lagged_cross_correlation
    time_lagged_regression
    granger_test
    pre_post_error_reduction
    ablation_effect_size

Reporting:
    BatchReport, BatchAnalysis
"""

from .core import (
    Metabolic,
    ISE,
    RitualGate,
    PredictiveModel,
    Actuator,
    Proprioceptor,
)
from .environment import Environment, EnvironmentConfig
from .interoception import InteroceptiveLoop, InteroceptiveState
from .persistence import Database
from .harness import HarnessConfig, run_single, run_batch
from .analysis import (
    compute_peri_event_histogram,
    lagged_cross_correlation,
    time_lagged_regression,
    granger_test,
    pre_post_error_reduction,
    ablation_effect_size,
)
from .reporting import BatchReport, BatchAnalysis

__all__ = [
    # core
    "Metabolic", "ISE", "RitualGate",
    "PredictiveModel", "Actuator", "Proprioceptor",
    # environment
    "Environment", "EnvironmentConfig",
    # interoception
    "InteroceptiveLoop", "InteroceptiveState",
    # persistence
    "Database",
    # harness
    "HarnessConfig", "run_single", "run_batch",
    # analysis
    "compute_peri_event_histogram",
    "lagged_cross_correlation",
    "time_lagged_regression",
    "granger_test",
    "pre_post_error_reduction",
    "ablation_effect_size",
    # reporting
    "BatchReport", "BatchAnalysis",
]
