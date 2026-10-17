"""Waste ↔ stockout trade-off frontiers: the non-dominated (stockout %, waste %) points of a policy family and
the waste it needs at a given stockout level. Used by the FreshRetailNet inventory experiment (protocol frn-v1
§3) and by the owner-chosen trade-off of the product."""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import combinations

import numpy as np

from decision.text import pct, units, vnd

Point = tuple[float, float]  # (stockout %, waste %), both lower is better


def pareto(points: Sequence[Point]) -> list[Point]:
    """Non-dominated points sorted by stockout ascending (waste then strictly decreasing)."""
    out: list[Point] = []
    best_waste = math.inf
    for stockout, waste in sorted(set(points)):
        if waste < best_waste:
            out.append((stockout, waste))
            best_waste = waste
    return out


def waste_at(frontier: Sequence[Point], stockout: float) -> float:
    """Waste % the frontier needs at ``stockout`` % (linear interpolation); NaN outside its stockout range
    (the family cannot reach that level)."""
    if not frontier or stockout < frontier[0][0] or stockout > frontier[-1][0]:
        return math.nan
    xs = [p[0] for p in frontier]
    ys = [p[1] for p in frontier]
    return float(np.interp(stockout, xs, ys))


# ---------------------------------------------------------------- goal-seeking on an inventory frontier

# goal key -> (frontier field, comparison, Vietnamese name)
GOAL_LIMITS: dict[str, tuple[str, str, str]] = {
    "max_stockout_pct": ("expected_stockout_pct", "<=", "hết hàng"),
    "min_service_pct": ("service_level_pct", ">=", "xác suất không hết hàng"),
    "max_cost_vnd": ("total_cost_vnd", "<=", "tiền nhập"),
    "max_leftover_units": ("expected_leftover_units", "<=", "tồn mang sang hôm sau"),
}


def _fmt(field: str, value: float) -> str:
    if field.endswith("_vnd"):
        return vnd(value)
    if field.endswith("_units"):
        return f"{units(value)} đơn vị"
    return pct(value)


def _say(key: str, value: float) -> str:
    field, op, name = GOAL_LIMITS[key]
    return f"{name} {'≤' if op == '<=' else '≥'} {_fmt(field, value)}"


def _meets(point: dict, goal: dict[str, float], keys: Sequence[str]) -> bool:
    for k in keys:
        field, op, _ = GOAL_LIMITS[k]
        if not (point[field] <= goal[k] if op == "<=" else point[field] >= goal[k]):
            return False
    return True


def choose_for_goal(frontier: Sequence[dict], goal: dict[str, float | None]) -> dict:
    """The cheapest frontier point meeting every goal (keys of ``GOAL_LIMITS``). When a goal is out of reach
    or two goals conflict, nothing is chosen silently: the answer says which goal fails and by how much, and
    asks the owner one question with the concrete options (the human decides)."""
    goals = {k: float(v) for k, v in goal.items() if v is not None}
    unknown = set(goals) - set(GOAL_LIMITS)
    if unknown:
        raise ValueError(f"unknown goal keys: {sorted(unknown)}")
    ordered = sorted(frontier, key=lambda p: (p["total_cost_vnd"], -p["service_level_pct"]))
    hits = [p for p in ordered if _meets(p, goals, list(goals))]
    if hits:
        p = hits[0]
        reached = "; ".join(f"{GOAL_LIMITS[k][2]} {_fmt(GOAL_LIMITS[k][0], p[GOAL_LIMITS[k][0]])}"
                            for k in goals)  # fmt: skip
        reason = (
            f"{p['label_vi']} là phương án rẻ nhất đạt đủ mục tiêu ({reached}), "
            f"tiền nhập {vnd(p['total_cost_vnd'])}."
        )
        return {
            "met": True,
            "name": p["name"],
            "label_vi": p["label_vi"],
            "reason_vi": reason,
            "escalation": None,
        }

    for k in goals:  # a goal no service level can reach on its own
        if not any(_meets(p, goals, [k]) for p in ordered):
            field, op, _ = GOAL_LIMITS[k]
            best = (min if op == "<=" else max)(p[field] for p in ordered)
            reason = f"Không mức phục vụ nào đạt {_say(k, goals[k])}; tốt nhất là {_fmt(field, best)}."
            question = (
                f"Một lần nhập không thể đạt {_say(k, goals[k])}. Bạn chấp nhận {_fmt(field, best)} không?"
            )
            choices = [f"Chấp nhận {_fmt(field, best)}", "Giữ mục tiêu, tôi tự điều chỉnh đơn"]
            return _unmet(reason, question, choices)

    # Every goal is reachable alone: name a pair that cannot be met together (budget first).
    pairs = sorted(combinations(goals, 2), key=lambda pr: "max_cost_vnd" not in pr)
    a, b = next((pr for pr in pairs if not any(_meets(p, goals, pr) for p in ordered)), pairs[0])
    pa, pb = _best_keeping(ordered, goals, a, b), _best_keeping(ordered, goals, b, a)
    fa, fb = GOAL_LIMITS[a][0], GOAL_LIMITS[b][0]
    question = (
        f"Không thể vừa {_say(a, goals[a])} vừa {_say(b, goals[b])}. Bạn ưu tiên giữ {GOAL_LIMITS[a][2]} "
        f"({pa['label_vi']}: {GOAL_LIMITS[b][2]} {_fmt(fb, pa[fb])}) hay giữ {GOAL_LIMITS[b][2]} "
        f"({pb['label_vi']}: {GOAL_LIMITS[a][2]} {_fmt(fa, pb[fa])})?"
    )
    choices = [f"{pa['label_vi']} ({pa['name']})", f"{pb['label_vi']} ({pb['name']})"]
    return _unmet(question, question, choices)


def _best_keeping(ordered: Sequence[dict], goals: dict[str, float], keep: str, other: str) -> dict:
    """Among points meeting ``keep``, the one closest to ``other`` (cheapest on ties): the real option."""
    field, op, _ = GOAL_LIMITS[other]
    candidates = [p for p in ordered if _meets(p, goals, [keep])]
    return min(candidates, key=lambda p: (p[field] if op == "<=" else -p[field], p["total_cost_vnd"]))


def _unmet(reason: str, question: str, choices: list[str]) -> dict:
    escalation = {"kind": "out_of_scope", "reason_vi": reason, "question_vi": question, "choices_vi": choices}
    return {"met": False, "name": None, "label_vi": None, "reason_vi": reason, "escalation": escalation}
