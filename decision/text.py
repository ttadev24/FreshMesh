"""Vietnamese number formatting for user-facing sentences (1.234.567 đ, 12,5%)."""


def vnd(amount: float) -> str:
    return f"{round(amount):,}".replace(",", ".") + " đ"


def pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + "%"


def units(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")
