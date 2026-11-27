"""Pay amounts in text, and the checks that keep a pay report honest (plan section 2.1, Day 12).

* `ranges(text)`: every pay range or amount written in the text, as annual amounts in
  whole currency units ("12-18 LPA" -> 1,200,000-1,800,000 INR; "$120k-$150k" -> USD).
* `supported(quote, source_text, low, high)`: a model-extracted range counts only when its
  quote is really in the source and the numbers are really in the quote. This is what
  stops an invented salary from reaching the report.
* `summarize(...)`: the market range (medians across sources, one currency) and a
  suggested ask that never goes below your own floor.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

LAKH, CRORE = 100_000, 10_000_000


@dataclass
class Amount:
    low: float
    high: float
    currency: str            # INR | USD | EUR | GBP
    monthly: bool = False

    @property
    def annual(self) -> "Amount":
        return Amount(self.low * 12, self.high * 12, self.currency) if self.monthly else self


_NUM = r"(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)"
_UNIT = r"(lpa|lakhs?|lacs?|l\b|cr(?:ores?)?\b|k\b|m\b)?"
RANGE = re.compile(rf"(?P<cur>₹|rs\.?|inr|\$|usd|€|eur|£|gbp)?\s*{_NUM}\s*{_UNIT}\s*(?:\([^()]{{1,30}}\)\s*)?(?:-|–|—|to|and)\s*(?P<cur2>₹|rs\.?|inr|\$|usd|€|eur|£|gbp)?\s*{_NUM}\s*{_UNIT}"
                   rf"(?P<tail>\s*(?:lpa|per annum|p\.?a\.?|a year|/year|per year|/yr|per month|/month|pm\b|monthly|inr|usd)?)", re.I)
SINGLE = re.compile(rf"(?P<cur>₹|rs\.?|inr|\$|usd|€|eur|£|gbp)\s*{_NUM}\s*{_UNIT}|{_NUM}\s*(?P<u>lpa|lakhs?|lacs?|cr(?:ores?)?)\b", re.I)
CURRENCY = {"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP"}


def _value(num: str, unit: str | None) -> float:
    v = float(num.replace(",", ""))
    u = (unit or "").lower()
    if u in ("lpa", "lakh", "lakhs", "lac", "lacs", "l"):
        return v * LAKH
    if u.startswith("cr"):
        return v * CRORE
    if u == "k":
        return v * 1_000
    if u == "m":
        return v * 1_000_000
    return v


def _currency(*marks: str | None, units: tuple[str | None, ...] = ()) -> str | None:
    for m in marks:
        if m:
            return CURRENCY.get(m.lower().rstrip("."), CURRENCY.get(m.lower()))
    if any((u or "").lower() in ("lpa", "lakh", "lakhs", "lac", "lacs", "l") or (u or "").lower().startswith("cr") for u in units):
        return "INR"
    return None


def ranges(text: str) -> list[Amount]:
    out: list[Amount] = []
    for m in RANGE.finditer(text or ""):
        n1, u1, n2, u2 = m.group(2), m.group(3), m.group(5), m.group(6)
        tail = (m.group("tail") or "").lower()
        unit1 = u1 or u2                              # "12-18 LPA": the unit after the second number counts for both
        cur = _currency(m.group("cur"), m.group("cur2"), tail.strip() if tail.strip() in ("inr", "usd") else None, units=(u1, u2, "lpa" if "lpa" in tail else None))
        if cur is None:
            continue
        low, high = _value(n1, unit1 if not u1 and u2 else u1), _value(n2, u2 or u1)
        if "lpa" in tail and not (u1 or u2):
            low, high = low * LAKH, high * LAKH
        if low <= 0 or high < low or high > 50 * low:
            continue
        out.append(Amount(low, high, cur, monthly=any(w in tail for w in ("month", "pm"))))
    if not out:
        for m in SINGLE.finditer(text or ""):
            if m.group("cur"):
                cur, v = _currency(m.group("cur")), _value(m.group(2), m.group(3))
            else:
                cur, v = "INR", _value(m.group(4), m.group("u"))
            # "₹17,00,000 per year, ₹1,41,667 per month or ₹817 per hour": the same pay three ways.
            after = (text or "")[m.end():m.end() + 24].lower()
            before = (text or "")[max(0, m.start() - 40):m.start()].lower()
            if re.match(r"\s*(?:per|an|a|/)\s*(?:hour|hr)\b", after) or re.search(r"hourly[^.,;]*$", before):
                continue
            monthly = bool(re.match(r"\s*(?:per|a|/)\s*(?:month|mo)\b|\s*monthly\b|\s*pm\b", after)
                           or re.search(r"monthly[^.,;]*$", before))
            if cur and v > 0 and (v * (12 if monthly else 1)) >= (50_000 if cur == "INR" else 5_000):   # not a salary otherwise
                out.append(Amount(v, v, cur, monthly=monthly))
        # The same figure stated per year and per month is one figure.
        annual = []
        for a in (x.annual for x in out):
            if not any(abs(a.low - b.low) <= 0.02 * a.low and a.currency == b.currency for b in annual):
                annual.append(a)
        return annual
    return [a.annual for a in out]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("–", "-").replace("—", "-")).strip().lower()


def supported(quote: str, source_text: str, low: float, high: float, currency: str) -> bool:
    """The quote is in the source, and it states this range (within 2%)."""
    if not quote or _norm(quote) not in _norm(source_text):
        return False
    close = lambda a, b: abs(a - b) <= 0.02 * max(a, b)                     # noqa: E731
    return any(a.currency == currency and close(a.low, low) and close(a.high, high) for a in ranges(quote))


def label(amount: float, currency: str) -> str:
    if currency == "INR":
        return f"{amount / LAKH:.1f}".rstrip("0").rstrip(".") + " LPA"
    sign = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, currency + " ")
    return f"{sign}{amount / 1000:.0f}k"


@dataclass
class Summary:
    currency: str
    low: float
    high: float
    n: int


def summarize(found: list[Amount], prefer: str = "INR") -> Summary | None:
    if not found:
        return None
    currencies = [a.currency for a in found]
    currency = prefer if prefer in currencies else max(set(currencies), key=currencies.count)
    same = [a for a in found if a.currency == currency]
    if len(same) == 1:
        return Summary(currency, same[0].low, same[0].high, 1)
    # The middle half of every reported figure (range ends and single figures alike).
    ends = sorted([a.low for a in same] + [a.high for a in same])
    q = statistics.quantiles(ends, n=4, method="inclusive")
    return Summary(currency, q[0], q[2], len(same))


def suggest(market: Summary | None, floor: Amount | None) -> tuple[float, float, str] | None:
    """An ask: at least your floor, and at least the market midpoint; up to the market top."""
    if market is None and floor is None:
        return None
    if market is None:
        return floor.low, floor.high, "From your own floor only; there wasn't enough public pay data for this role."
    mid = (market.low + market.high) / 2
    low = max(mid, floor.low) if floor and floor.currency == market.currency else mid
    high = max(market.high, low)
    why = f"Market midpoint {label(mid, market.currency)} to top {label(market.high, market.currency)} across {market.n} source" \
          f"{'s' if market.n > 1 else ''}"
    if floor and floor.currency == market.currency and floor.low > mid:
        why += f"; raised to your floor of {label(floor.low, market.currency)}"
    return low, high, why + "."
