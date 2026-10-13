"""Decision layer: inventory plans, markdown and stock transfer. Pure functions, no I/O."""

from decision.distribution import QuantileDistribution, sample_demand
from decision.inventory import critical_ratio, plan_inventory
from decision.markdown import DISCOUNT_LEVELS, demand_multiplier, suggest_markdown
from decision.transfer import compare_markdown_vs_transfer, stock_balance, transfer_stock
from decision.types import (
    Comparison,
    Constraints,
    ForecastQuantiles,
    InventoryPlan,
    MarkdownPlan,
    MarkdownSlot,
    PlanLine,
    SkuEconomics,
    StockLot,
    TransferLine,
    TransferPlan,
)

__all__ = [
    "DISCOUNT_LEVELS",
    "Comparison",
    "Constraints",
    "ForecastQuantiles",
    "InventoryPlan",
    "MarkdownPlan",
    "MarkdownSlot",
    "PlanLine",
    "QuantileDistribution",
    "SkuEconomics",
    "StockLot",
    "TransferLine",
    "TransferPlan",
    "compare_markdown_vs_transfer",
    "critical_ratio",
    "demand_multiplier",
    "plan_inventory",
    "sample_demand",
    "stock_balance",
    "suggest_markdown",
    "transfer_stock",
]
