from decimal import Decimal

NA = "Data unavailable"


def money(v, currency: str = "") -> str:
    if v is None:
        return "—"
    v = Decimal(str(v))
    return f"{'-' if v < 0 else ''}{abs(v):,.2f} {currency}".strip()


def pct(v) -> str:
    return "—" if v is None else f"{Decimal(str(v)):.1f}%"


def num(v, places: int = 2, na: str = NA) -> str:
    return na if v is None else f"{Decimal(str(v)):,.{places}f}"


def pf(value, infinite: bool) -> str:
    return "∞" if infinite else ("—" if value is None else f"{Decimal(str(value)):.2f}")


def duration(seconds) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    return f"{d}d {h}h" if d else f"{h}h {m}m" if h else f"{m}m"


def tone(v) -> str:
    if v is None:
        return "text-slate-200"
    v = Decimal(str(v))
    return "text-emerald-400" if v > 0 else "text-rose-400" if v < 0 else "text-slate-200"
