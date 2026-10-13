from routing.validate import Screening


def build_instance(
    screening: Screening, num_vehicles: int, vehicle_capacity: int, shift_minutes: int
) -> str:
    """Render a routing-PL instance (see routing-PL src/data/readme.txt).

    Node ids inside the solver: depot 0, customers 1..n, lockers n+1..n+m.
    """
    orders = screening.routable
    lockers = screening.lockers
    lines = [f"{len(orders)} {len(lockers)}", f"{num_vehicles} {vehicle_capacity}"]
    lines += [str(r.order.demand) for r in orders]
    lines.append(f"0.0000 0.0000 0 {shift_minutes} 0 0")
    lines += [
        f"{r.x:.4f} {r.y:.4f} {r.earliest} {r.latest} {r.service} {int(r.mode)}" for r in orders
    ]
    lines += [f"{l.x:.4f} {l.y:.4f} 0 {shift_minutes} 0 4" for l in lockers]
    for r in orders:
        allowed = set(r.allowed_lockers)
        lines.append(" ".join("1" if i in allowed else "0" for i in range(len(lockers))))
    return "\n".join(lines)
