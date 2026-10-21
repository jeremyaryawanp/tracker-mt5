import re
from decimal import Decimal

from app.models.enums import AssetClass

CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "SGD", "HKD", "NOK", "SEK",
    "DKK", "ZAR", "MXN", "TRY", "PLN", "CZK", "HUF", "CNH", "IDR", "THB", "ILS", "RUB",
}
METALS = {
    "XAU": Decimal("0.1"),
    "XAG": Decimal("0.01"),
    "XPT": Decimal("0.1"),
    "XPD": Decimal("0.1"),
}
CRYPTO = ("BTC", "ETH", "LTC", "XRP", "SOL", "BCH", "ADA", "DOGE")


def base_symbol(symbol: str) -> str:
    """Strip common broker suffixes/prefixes: 'EURUSD.m', 'XAUUSDm', 'EURUSD-ECN' -> core."""
    s = symbol.upper()
    m = re.match(r"^[^A-Z]*([A-Z]{6})", s)
    if m and (m.group(1)[:3] in CURRENCIES | set(METALS) and m.group(1)[3:] in CURRENCIES):
        return m.group(1)
    return re.split(r"[.\-_#]", s)[0]


def classify(symbol: str, path: str | None = None) -> AssetClass:
    core = base_symbol(symbol)
    p = (path or "").lower()
    if core[:3] in METALS or "metal" in p:
        return AssetClass.METAL
    if any(core.startswith(c) for c in CRYPTO) or "crypto" in p:
        return AssetClass.CRYPTO
    if len(core) == 6 and core[:3] in CURRENCIES and core[3:] in CURRENCIES:
        return AssetClass.FX
    if "forex" in p:
        return AssetClass.FX
    if "ind" in p:
        return AssetClass.INDEX
    return AssetClass.OTHER


def derive_pip(
    symbol: str, digits: int | None, point: Decimal | None, asset_class: AssetClass
) -> tuple[Decimal | None, str]:
    """Return (pip size in price units, human-readable unit definition)."""
    core = base_symbol(symbol)
    if asset_class == AssetClass.FX and digits is not None:
        size = Decimal(10) ** -(digits - 1 if digits in (3, 5) else digits)
        return size, f"1 pip = {size} price units (FX, {digits}-digit quote)"
    if asset_class == AssetClass.METAL and core[:3] in METALS:
        size = METALS[core[:3]]
        return size, f"1 pip = {size} price units (metal default; configurable)"
    if point is not None:
        return point, f"1 pip = 1 point = {point} price units (default; configurable)"
    return None, "pip size unknown — configure it for this symbol"
