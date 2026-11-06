"""Amounts as people write them, converted once, in one place.

Zaprite's API takes integers in the smallest unit. People write "$1,280",
"1280 usd" or "0.05 BTC". Getting that wrong is silent and expensive: 1280
instead of 128000 is a hundredfold under-billing that still looks like a valid
order. So the conversion lives here, with one rule per input type:

    int      -> already minor units (the API's own shape, unchanged)
    float    -> major units, because a decimal point is a decimal point
    str      -> "$1,280", "1,280.50", "1280 usd" are major; "50000 sats" are sats
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

# Currencies with no minor unit in practice, or a whole-unit minor unit.
_WHOLE = {"JPY", "KRW", "VND", "CLP", "ISK"}
_SATS = {"BTC", "LBTC", "L-BTC", "SATS", "SAT"}
_TWO_DP_STABLES = {"USDT", "USDC", "USDT0", "USDC.E", "DAI"}

_SYMBOLS = "$€£₿"


class AmountError(ValueError):
    """A person-facing refusal. The message is shown as written."""


def minor_factor(currency: str) -> int:
    code = (currency or "").strip().upper()
    if code in _SATS:
        return 100_000_000
    if code in _WHOLE:
        return 1
    return 100


def parse_amount(value: object, currency: str = "USD") -> tuple[int, str]:
    """Return (minor_units, a phrase naming what was understood)."""
    code = (currency or "USD").strip().upper()
    factor = minor_factor(code)

    if isinstance(value, bool):
        raise AmountError("That amount is not a number. Write it as 1280 or $1,280.")
    if isinstance(value, int):
        if value <= 0:
            raise AmountError("The amount has to be more than zero.")
        # An integer is the API's own shape: minor units. But 1280 meaning "$1,280"
        # is the mistake a person makes, so small fiat integers get asked about.
        if code not in _SATS and code not in _WHOLE and value < 1000:
            raise AmountError(
                f"{value} would be {_phrase(value, code)}. "
                f'If you meant {value:,} {code}, write "${value:,}" or {value * 100}.'
            )
        return value, _phrase(value, code)
    if isinstance(value, float):
        return _from_major(Decimal(str(value)), code, factor)

    if isinstance(value, str):
        text = value.strip()
        for symbol in _SYMBOLS:
            text = text.replace(symbol, "")
        lowered = text.lower()
        for token in list(_SATS | _TWO_DP_STABLES) + ["usd", "eur", "gbp", "cad", "aud"]:
            token = token.lower()
            if lowered.endswith(" " + token) or lowered.endswith(token):
                text = text[: len(text) - len(token)]
                break
        text = text.replace(",", "").replace("_", "").strip()
        if not text:
            raise AmountError("I didn't catch an amount. Write it as 1280 or $1,280.")
        try:
            number = Decimal(text)
        except InvalidOperation:
            raise AmountError(f"I couldn't read {value!r} as an amount. Try 1280 or $1,280.") from None
        has_point = "." in text
        if code in _SATS and not has_point:
            # "50000 BTC" with no decimal point is almost certainly sats, not 50,000 BTC.
            if number <= 0:
                raise AmountError("The amount has to be more than zero.")
            return int(number), f"{int(number)} sats"
        return _from_major(number, code, factor)

    raise AmountError("That amount is not a number. Write it as 1280 or $1,280.")


def _from_major(number: Decimal, code: str, factor: int) -> tuple[int, str]:
    if number <= 0:
        raise AmountError("The amount has to be more than zero.")
    minor = int((number * factor).to_integral_value())
    if minor > 10**13:
        raise AmountError("That amount is larger than this plugin will send. Check the currency.")
    return minor, _phrase(minor, code)


def _phrase(minor: int, code: str) -> str:
    if code in _SATS:
        return f"{minor / 100_000_000:.8f} {code}"
    factor = minor_factor(code)
    if factor == 1:
        return f"{minor:,} {code}"
    return f"{minor / factor:,.2f} {code}"
