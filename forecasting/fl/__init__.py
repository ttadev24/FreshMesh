"""Federated learning for FreshMesh demand forecasting (Flower FedAvg + FedPer, optional client-level DP).

Entry points: ``python -m forecasting.fl train|experiment``, ``run_federated`` and ``fl_summary``.
"""

from forecasting.fl.client import FLConfig
from forecasting.fl.runtime import FLResult, run_federated
from forecasting.fl.summary import fl_summary

__all__ = ["FLConfig", "FLResult", "fl_summary", "run_federated"]
