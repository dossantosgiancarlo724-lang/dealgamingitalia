"""Safe launcher for the deal bot with robust European price parsing.

This module patches the parser in bot.py before starting the existing bot.
It prevents matching the suffix of thousands-formatted prices such as 1.159€.
"""
import re
import bot as _bot


_PRICE_TOKEN = r"(?:\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{4,6}(?:[.,]\d{1,2})?|\d{1,3}(?:[.,]\d{1,2})?)"
_PRICE_AFTER_EUR = re.compile(rf"(?<![\d.,])({_PRICE_TOKEN})\s*€")
_PRICE_BEFORE_EUR = re.compile(rf"€\s*({_PRICE_TOKEN})(?![\d.,])")


def _parse_price_token(value):
    s = value.strip().replace("\xa0", "")
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 1 and len(parts[-1]) == 3 and all(p.isdigit() for p in parts):
            s = "".join(parts)
        else:
            s = s.replace(",", ".")
    elif "," in s:
        parts = s.split(",")
        if len(parts) > 1 and len(parts[-1]) == 3 and all(p.isdigit() for p in parts):
            s = "".join(parts)
        else:
            s = s.replace(",", ".")
    return float(s)


def extract_prices(text):
    """Extract real euro prices without matching suffixes of thousands values."""
    text = text or ""
    values = []
    spans = []
    for match in _PRICE_AFTER_EUR.finditer(text):
        values.append(_parse_price_token(match.group(1)))
        spans.append(match.span())
    for match in _PRICE_BEFORE_EUR.finditer(text):
        # Avoid duplicate matches if a future source contains both forms around the same token.
        if not any(max(spans[i][0], match.start()) < min(spans[i][1], match.end()) for i in range(len(spans))):
            values.append(_parse_price_token(match.group(1)))
    return values


def _find_explicit_old_new_pair(text):
    """Find phrases such as 'da 1.159€ a 1.059€' or 'prima 749€ ora 499€'."""
    t = text or ""
    pair = re.compile(
        rf"(?:da|prima|precedente|era|was)\s*€?\s*({_PRICE_TOKEN})\s*€?\s*(?:a|ora|adesso|oggi|diventa|->|→)\s*€?\s*({_PRICE_TOKEN})\s*€?",
        re.IGNORECASE,
    )
    m = pair.search(t)
    if not m:
        return None
    first = _parse_price_token(m.group(1))
    second = _parse_price_token(m.group(2))
    if first > second > 0:
        return first, second
    return None


def derive_prices_and_discount(text):
    """Return (current, original, discount), rejecting ambiguous price data."""
    text = text or ""
    explicit_discount = _bot.extract_discount(text)
    explicit_pair = _find_explicit_old_new_pair(text)
    if explicit_pair:
        original, current = explicit_pair
        discount = (original - current) / original * 100.0
        if 0 < discount <= 100:
            return current, original, discount

    prices = extract_prices(text)
    unique = []
    for p in prices:
        if p > 0 and all(abs(p - x) > 0.009 for x in unique):
            unique.append(p)

    # Two prices with no other price candidates are safe to compare.
    if len(unique) == 2:
        original, current = max(unique), min(unique)
        if original > current:
            discount = (original - current) / original * 100.0
            if 0 < discount <= 100:
                return current, original, discount

    # If only one price is present, an explicit percentage can be used to calculate
    # the old price. This is safe only when there is no competing price value.
    if len(unique) == 1 and explicit_discount and 0 < explicit_discount < 100:
        current = unique[0]
        original = current / (1 - explicit_discount / 100.0)
        return current, original, explicit_discount

    # Ambiguous or incomplete price data must never be published.
    return None, None, None


# Patch the existing bot module before main() starts.
_bot.extract_prices = extract_prices
_bot.derive_prices_and_discount = derive_prices_and_discount


if __name__ == "__main__":
    _bot.asyncio.run(_bot.main())
