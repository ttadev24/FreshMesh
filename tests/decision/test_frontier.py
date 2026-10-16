import datetime as dt
import math

from decision.frontier import pareto, waste_at
from decision.inventory import quantity_for_service
from decision.types import ForecastQuantiles, SkuEconomics, StockLot


def test_pareto_keeps_only_non_dominated_points_in_stockout_order():
    pts = [(10.0, 5.0), (5.0, 9.0), (12.0, 6.0), (2.0, 20.0), (5.0, 8.0), (20.0, 1.0)]
    assert pareto(pts) == [(2.0, 20.0), (5.0, 8.0), (10.0, 5.0), (20.0, 1.0)]


def test_waste_at_interpolates_and_refuses_to_extrapolate():
    f = [(2.0, 20.0), (10.0, 4.0), (20.0, 1.0)]
    assert waste_at(f, 6.0) == 12.0 and waste_at(f, 10.0) == 4.0
    assert math.isnan(waste_at(f, 1.0)) and math.isnan(waste_at(f, 25.0)) and math.isnan(waste_at([], 5.0))


SKU = SkuEconomics("K", "Rau", unit_cost=1.0, unit_price=2.0, salvage_price=0.0, shelf_life_days=2)
DAY = dt.date(2024, 6, 12)


def test_quantity_for_service_rises_with_the_target_and_counts_stock_on_hand():
    rows = [ForecastQuantiles("S", "K", DAY, 20.0, 30.0, 45.0)]
    lean, s_lean = quantity_for_service("S", SKU, rows, [], 0.5)
    safe, s_safe = quantity_for_service("S", SKU, rows, [], 0.9)
    assert lean < safe and s_lean >= 0.5 and s_safe >= 0.9
    assert 25 <= lean <= 35  # around the median
    with_stock, _ = quantity_for_service("S", SKU, rows, [StockLot("S", "K", 10, DAY)], 0.9)
    assert with_stock < safe  # usable stock reduces the order
