"""Minimal dependency-free SVG charts for the experiment reports (matplotlib is not a project dependency)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from html import escape

PALETTE = ("#8a8f98", "#2f6b3a", "#c08a1e", "#3b6ea8", "#b23b3b")
W, H = 720, 420
LEFT, RIGHT, TOP, BOTTOM = 70, 20, 50, 80


def _nice_max(v: float) -> float:
    if v <= 0 or not math.isfinite(v):
        return 1.0
    exp = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * exp:
            return m * exp
    return 10 * exp


def _frame(title: str, y_label: str, y_max: float) -> list[str]:
    ph = H - TOP - BOTTOM
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'font-family="sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="{W / 2}" y="24" text-anchor="middle" font-size="15" font-weight="bold">'
        f"{escape(title)}</text>",
        f'<text x="16" y="{TOP + ph / 2}" transform="rotate(-90 16 {TOP + ph / 2})" '
        f'text-anchor="middle">{escape(y_label)}</text>',
    ]
    for i in range(6):
        val = y_max * i / 5
        y = TOP + ph - ph * i / 5
        out.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{W - RIGHT}" y2="{y:.1f}" stroke="#e5e5e5"/>')
        out.append(f'<text x="{LEFT - 6}" y="{y + 4:.1f}" text-anchor="end">{val:.3g}</text>')
    out.append(f'<line x1="{LEFT}" y1="{TOP + ph}" x2="{W - RIGHT}" y2="{TOP + ph}" stroke="#333"/>')
    return out


def bar_chart_svg(
    title: str, categories: Sequence[str], series: Sequence[tuple[str, Sequence[float]]], *, y_label: str
) -> str:
    """Grouped bars: one group per category, one bar per series; NaN values are skipped."""
    vals = [v for _, vs in series for v in vs if math.isfinite(v)]
    y_max = _nice_max(max(vals) if vals else 1.0)
    ph, pw = H - TOP - BOTTOM, W - LEFT - RIGHT
    out = _frame(title, y_label, y_max)
    gw = pw / max(len(categories), 1)
    bw = gw * 0.8 / max(len(series), 1)
    for ci, cat in enumerate(categories):
        x0 = LEFT + ci * gw + gw * 0.1
        for si, (_, vs) in enumerate(series):
            v = vs[ci]
            if not math.isfinite(v):
                continue
            h = ph * v / y_max
            x = x0 + si * bw
            out.append(
                f'<rect x="{x:.1f}" y="{TOP + ph - h:.1f}" width="{bw * 0.92:.1f}" height="{h:.1f}" '
                f'fill="{PALETTE[si % len(PALETTE)]}"/>'
            )
            out.append(
                f'<text x="{x + bw * 0.46:.1f}" y="{TOP + ph - h - 4:.1f}" '
                f'text-anchor="middle">{v:.3f}</text>'
            )
        out.append(
            f'<text x="{x0 + gw * 0.4:.1f}" y="{TOP + ph + 18}" text-anchor="middle">{escape(cat)}</text>'
        )
    _legend(out, [name for name, _ in series])
    out.append("</svg>")
    return "\n".join(out)


def line_chart_svg(
    title: str,
    points: Sequence[tuple[float, float]],
    references: Sequence[tuple[str, float]],
    *,
    x_label: str,
    y_label: str,
    y_cap: float | None = None,
) -> str:
    """Line over a log-scale x axis plus dashed horizontal reference lines. Points above ``y_cap`` are drawn
    at the top edge (triangle marker) with their true value as label."""
    ys = [y for _, y in points] + [v for _, v in references]
    top = max(ys) if ys else 1.0
    y_max = _nice_max(min(top, y_cap) if y_cap is not None else top)
    ph, pw = H - TOP - BOTTOM, W - LEFT - RIGHT
    out = _frame(title, y_label, y_max)
    xs = [math.log10(x) for x, _ in points] or [0.0, 1.0]
    x_lo, x_hi = math.floor(min(xs)), math.ceil(max(xs))
    x_hi = x_hi if x_hi > x_lo else x_lo + 1

    def px(x: float) -> float:
        return LEFT + pw * (math.log10(x) - x_lo) / (x_hi - x_lo)

    def py(y: float) -> float:
        return TOP + ph - ph * min(y, y_max) / y_max

    for e in range(x_lo, x_hi + 1):
        x = LEFT + pw * (e - x_lo) / (x_hi - x_lo)
        out.append(f'<line x1="{x:.1f}" y1="{TOP}" x2="{x:.1f}" y2="{TOP + ph}" stroke="#f0f0f0"/>')
        out.append(f'<text x="{x:.1f}" y="{TOP + ph + 18}" text-anchor="middle">{10**e:g}</text>')
    out.append(f'<text x="{LEFT + pw / 2}" y="{H - 40}" text-anchor="middle">{escape(x_label)}</text>')
    for i, (_, v) in enumerate(references):
        color = PALETTE[(i + 2) % len(PALETTE)]
        out.append(
            f'<line x1="{LEFT}" y1="{py(v):.1f}" x2="{W - RIGHT}" y2="{py(v):.1f}" stroke="{color}" '
            'stroke-dasharray="6 4" stroke-width="1.5"/>'
        )
    if points:
        path = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in points)
        out.append(f'<polyline points="{path}" fill="none" stroke="{PALETTE[1]}" stroke-width="2"/>')
        for x, y in points:
            cx, cy = px(x), py(y)
            if y > y_max:
                tri = f"{cx - 5:.1f},{cy + 6:.1f} {cx + 5:.1f},{cy + 6:.1f} {cx:.1f},{cy - 3:.1f}"
                out.append(f'<polygon points="{tri}" fill="{PALETTE[4]}"/>')
                out.append(f'<text x="{cx + 8:.1f}" y="{cy + 14:.1f}">{y:.3g} (ngoài trục)</text>')
            else:
                out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.5" fill="{PALETTE[1]}"/>')
                out.append(f'<text x="{cx:.1f}" y="{cy - 8:.1f}" text-anchor="middle">{y:.3f}</text>')
    names = ["FL + DP"] + [f"{n} ({v:.3f})" for n, v in references]
    colors = [PALETTE[1]] + [PALETTE[(i + 2) % len(PALETTE)] for i in range(len(references))]
    _legend(out, names, colors)
    out.append("</svg>")
    return "\n".join(out)


def _legend(out: list[str], names: Sequence[str], colors: Sequence[str] | None = None) -> None:
    colors = colors or [PALETTE[i % len(PALETTE)] for i in range(len(names))]
    x = LEFT
    y = H - 16
    for name, color in zip(names, colors, strict=True):
        out.append(f'<rect x="{x}" y="{y - 10}" width="12" height="12" fill="{color}"/>')
        out.append(f'<text x="{x + 16}" y="{y}">{escape(name)}</text>')
        x += 24 + 7 * len(name)
