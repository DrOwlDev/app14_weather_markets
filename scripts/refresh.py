#!/usr/bin/env python3
"""Fetch Polymarket daily-temperature markets + Open-Meteo ensembles, score edges."""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CITIES_PATH = ROOT / "config" / "cities.json"
DATA_DIR = ROOT / "data"
OPPORTUNITIES_PATH = DATA_DIR / "opportunities.json"
MARKETS_PATH = DATA_DIR / "markets.json"

GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
USER_AGENT = "app14-weather-markets/1.0 (+https://github.com; polymarket scanner)"

DAY_HORIZON = 2  # today + next N local days
MIN_LIQUIDITY_SNAPSHOT = 0.0
REQUEST_PAUSE_S = 0.05
HTTP_TIMEOUT_S = 25
HTTP_RETRIES = 2


def http_get_json(url: str, *, retries: int = HTTP_RETRIES) -> Any:
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                return json.load(resp)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, TimeoutError) as err:
            last_err = err
            time.sleep(0.8 * (attempt + 1))
        except Exception as err:  # noqa: BLE001 — keep CI moving on unexpected socket errors
            last_err = err
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} tries: {url}") from last_err


def load_cities() -> list[dict[str, Any]]:
    return json.loads(CITIES_PATH.read_text(encoding="utf-8"))


def city_index(cities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_name = {c["name"].lower(): c for c in cities}
    # aliases
    by_name["new york"] = by_name.get("nyc", by_name.get("new york", {}))
    by_name["seoul"] = by_name.get("seoul (incheon)", by_name.get("seoul", {}))
    return {k: v for k, v in by_name.items() if v}


def parse_city_from_title(title: str) -> str | None:
    if " in " not in title or " on " not in title:
        return None
    return title.split(" in ", 1)[1].split(" on ", 1)[0].strip()


def market_kind(title: str) -> str | None:
    lower = title.lower()
    if lower.startswith("highest"):
        return "high"
    if lower.startswith("lowest"):
        return "low"
    return None


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def yes_price(market: dict[str, Any]) -> float | None:
    prices = parse_jsonish(market.get("outcomePrices"))
    if isinstance(prices, list) and prices:
        try:
            return float(prices[0])
        except (TypeError, ValueError):
            return None
    return None


def best_ask(market: dict[str, Any]) -> float | None:
    ask = market.get("bestAsk")
    if ask is None:
        return None
    try:
        return float(ask)
    except (TypeError, ValueError):
        return None


def liquidity(market: dict[str, Any]) -> float:
    for key in ("liquidityNum", "liquidity"):
        val = market.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return 0.0


_BUCKET_RE = re.compile(
    r"(?P<below>(?P<blo>-?\d+(?:\.\d+)?)\s*°?\s*[CF]\s+or\s+below)"
    r"|(?P<above>(?P<aup>-?\d+(?:\.\d+)?)\s*°?\s*[CF]\s+or\s+higher)"
    r"|(?P<range>(?P<rlo>-?\d+(?:\.\d+)?)\s*[-–]\s*(?P<rhi>-?\d+(?:\.\d+)?)\s*°?\s*[CF])"
    r"|(?P<single>(?P<slo>-?\d+(?:\.\d+)?)\s*°?\s*[CF])",
    re.IGNORECASE,
)


def parse_bucket(label: str) -> tuple[float, float] | None:
    """Return inclusive [lo, hi] bounds in the market's native unit."""
    text = (label or "").replace("°", "°").strip()
    # normalize weird encodings
    text = text.replace("Â°", "°")
    m = _BUCKET_RE.fullmatch(text.replace(" ", " ").strip())
    if not m:
        # try without fullmatch whitespace quirks
        m = _BUCKET_RE.search(text)
        if not m:
            return None
    if m.group("below"):
        hi = float(m.group("blo"))
        return (-math.inf, hi)
    if m.group("above"):
        lo = float(m.group("aup"))
        return (lo, math.inf)
    if m.group("range"):
        return (float(m.group("rlo")), float(m.group("rhi")))
    if m.group("single"):
        v = float(m.group("slo"))
        return (v, v)
    return None


def round_temp(value: float) -> int:
    return int(math.floor(value + 0.5)) if value >= 0 else int(math.ceil(value - 0.5))


def c_to_unit(temp_c: float, unit: str) -> float:
    if unit.upper() == "F":
        return temp_c * 9.0 / 5.0 + 32.0
    return temp_c


def member_in_bucket(temp_native: float, lo: float, hi: float) -> bool:
    rounded = round_temp(temp_native)
    if math.isinf(lo) and lo < 0:
        return rounded <= hi
    if math.isinf(hi) and hi > 0:
        return rounded >= lo
    return lo <= rounded <= hi


def fetch_gamma_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    offset = 0
    limit = 100
    while True:
        qs = urllib.parse.urlencode(
            {
                "tag_slug": "daily-temperature",
                "active": "true",
                "closed": "false",
                "limit": limit,
                "offset": offset,
            }
        )
        batch = http_get_json(f"{GAMMA_EVENTS_URL}?{qs}")
        if not isinstance(batch, list) or not batch:
            break
        events.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
        time.sleep(REQUEST_PAUSE_S)
    return events


def _members_from_daily(daily: dict[str, Any], daily_var: str) -> dict[str, list[float]]:
    times = daily.get("time") or []
    member_keys = [
        k
        for k in daily.keys()
        if k == daily_var or k.startswith(f"{daily_var}_member")
    ]
    out: dict[str, list[float]] = {}
    for i, day in enumerate(times):
        vals: list[float] = []
        for key in member_keys:
            series = daily.get(key) or []
            if i >= len(series):
                continue
            val = series[i]
            if val is None:
                continue
            try:
                vals.append(float(val))
            except (TypeError, ValueError):
                continue
        if vals:
            out[day] = vals
    return out


def fetch_ensemble_both(
    lat: float, lon: float, tz: str
) -> dict[str, dict[str, list[float]]]:
    """Fetch high + low ensembles in one request. Returns {high|low: {date: members}}."""
    qs = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": tz,
            "forecast_days": DAY_HORIZON + 2,
            "models": "gfs_seamless",
        }
    )
    payload = http_get_json(f"{ENSEMBLE_URL}?{qs}")
    daily = payload.get("daily") or {}
    return {
        "high": _members_from_daily(daily, "temperature_2m_max"),
        "low": _members_from_daily(daily, "temperature_2m_min"),
    }


def local_dates_for_city(tz_name: str) -> set[str]:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    today = datetime.now(tz).date()
    return {(today + timedelta(days=i)).isoformat() for i in range(DAY_HORIZON + 1)}


def score_event(
    event: dict[str, Any],
    city: dict[str, Any],
    members_by_date: dict[str, list[float]],
) -> list[dict[str, Any]]:
    event_date = event.get("eventDate") or ""
    if event_date not in members_by_date:
        return []
    members_c = members_by_date[event_date]
    unit = city["unit"]
    members_native = [c_to_unit(v, unit) for v in members_c]
    if not members_native:
        return []

    title = event.get("title") or ""
    kind = market_kind(title) or "high"
    slug = event.get("slug") or ""
    mean_native = sum(members_native) / len(members_native)
    rows: list[dict[str, Any]] = []

    for market in event.get("markets") or []:
        label = market.get("groupItemTitle") or ""
        bounds = parse_bucket(label)
        if not bounds:
            continue
        lo, hi = bounds
        hits = sum(1 for t in members_native if member_in_bucket(t, lo, hi))
        model_prob = hits / len(members_native)
        y_price = yes_price(market)
        ask = best_ask(market)
        # Prefer a real ask when it is tradeable; otherwise fall back to mid.
        if ask is not None and 0.0 < ask < 0.99:
            market_price = ask
        elif y_price is not None:
            market_price = y_price
        else:
            continue
        liq = liquidity(market)
        # Drop empty / stub books (ask pegged at 0 or 1 with no mid)
        if y_price is None and ask is not None and ask in (0.0, 1.0):
            continue
        if liq <= MIN_LIQUIDITY_SNAPSHOT and market_price in (0.0, 1.0):
            continue
        edge = model_prob - market_price
        ask_out = ask if ask is not None and 0.0 < ask < 0.99 else None
        rows.append(
            {
                "city": city["name"],
                "date": event_date,
                "kind": kind,
                "eventSlug": slug,
                "bucket": label,
                "yesPrice": round(y_price, 4) if y_price is not None else None,
                "bestAsk": round(ask_out, 4) if ask_out is not None else None,
                "modelProb": round(model_prob, 4),
                "edge": round(edge, 4),
                "liquidity": round(liq, 2),
                "forecastMean": round(mean_native, 2),
                "unit": unit,
                "ensembleSize": len(members_native),
                "icao": city["icao"],
                "url": f"https://polymarket.com/event/{slug}",
            }
        )
    return rows


def build_snapshot(cities: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    by_city = city_index(cities)
    allowed_dates = {c["name"]: local_dates_for_city(c["timezone"]) for c in cities}

    # Cache by ICAO: {"high": {date: members}, "low": {...}}
    forecast_cache: dict[str, dict[str, dict[str, list[float]]]] = {}
    opportunities: list[dict[str, Any]] = []
    markets_snapshot: list[dict[str, Any]] = []
    skipped_unknown_city = 0
    skipped_date = 0

    for event in events:
        title = event.get("title") or ""
        city_name = parse_city_from_title(title)
        if not city_name:
            continue
        city = by_city.get(city_name.lower())
        if not city:
            skipped_unknown_city += 1
            continue
        kind = market_kind(title)
        if not kind:
            continue
        event_date = event.get("eventDate") or ""
        if event_date not in allowed_dates.get(city["name"], set()):
            skipped_date += 1
            continue

        icao = city["icao"]
        if icao not in forecast_cache:
            try:
                forecast_cache[icao] = fetch_ensemble_both(
                    city["lat"], city["lon"], city["timezone"]
                )
                print(f"ensemble ok {city['name']} ({icao})")
                time.sleep(REQUEST_PAUSE_S)
            except Exception as err:
                print(f"ensemble failed for {city['name']}: {err}")
                forecast_cache[icao] = {"high": {}, "low": {}}

        members = forecast_cache[icao].get(kind) or {}
        rows = score_event(event, city, members)
        opportunities.extend(rows)
        markets_snapshot.append(
            {
                "title": title,
                "slug": event.get("slug"),
                "eventDate": event_date,
                "city": city["name"],
                "kind": kind,
                "marketCount": len(event.get("markets") or []),
            }
        )

    opportunities.sort(key=lambda r: abs(r["edge"]), reverse=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "generatedAt": generated_at,
        "source": {
            "gamma": "tag_slug=daily-temperature",
            "forecast": "open-meteo ensemble gfs_seamless",
        },
        "stats": {
            "eventsFetched": len(events),
            "eventsScored": len(markets_snapshot),
            "opportunities": len(opportunities),
            "skippedUnknownCity": skipped_unknown_city,
            "skippedOutsideHorizon": skipped_date,
            "forecastCalls": len(forecast_cache),
        },
        "opportunities": opportunities,
        "markets": markets_snapshot,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cities = load_cities()
    print(f"loaded {len(cities)} cities")
    events = fetch_gamma_events()
    print(f"fetched {len(events)} gamma events")
    snapshot = build_snapshot(cities, events)

    opportunities_doc = {
        "generatedAt": snapshot["generatedAt"],
        "source": snapshot["source"],
        "stats": snapshot["stats"],
        "opportunities": snapshot["opportunities"],
    }
    markets_doc = {
        "generatedAt": snapshot["generatedAt"],
        "markets": snapshot["markets"],
    }
    OPPORTUNITIES_PATH.write_text(
        json.dumps(opportunities_doc, indent=2) + "\n", encoding="utf-8"
    )
    MARKETS_PATH.write_text(json.dumps(markets_doc, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {OPPORTUNITIES_PATH.relative_to(ROOT)} "
        f"({len(snapshot['opportunities'])} rows) at {snapshot['generatedAt']}"
    )
    print(f"stats: {json.dumps(snapshot['stats'])}")


if __name__ == "__main__":
    main()
