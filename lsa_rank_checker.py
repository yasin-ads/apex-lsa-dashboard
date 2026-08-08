#!/usr/bin/env python3
"""
LSA Rank Checker - Apex Lock N Key
==================================

Purpose
-------
Check the Google Local Services Ads (LSA / Google Guaranteed) position of
Apex Lock N Key city by city, WITHOUT logging into any Google account.

Data source
-----------
This script uses SerpApi's official `google_local_services` engine.

Important
---------
- One LSA rank check = one SerpApi search.
- City CID discovery also uses SerpApi, but discovered CIDs are cached locally.
- This script checks the general Locksmith LSA ranking for each city.
- It does NOT use Google Maps ranking, organic ranking, or a signed-in Google account.
- It never invents a rank. If a result is unavailable, it reports an explicit status.

Verified service-area list
--------------------------
The 54 cities below were transcribed from the Local Services Ads service-area
screenshots supplied for this account. If the live account now contains 58
cities, add the four newer city names to `EXTRA_CITIES` below. They will be
resolved automatically the next time `--find-cids` is run.

Setup
-----
1. Create a SerpApi account/key:
   https://serpapi.com/users/sign_up

2. Windows PowerShell:
   $env:SERPAPI_KEY="YOUR_KEY"

   Windows CMD:
   set SERPAPI_KEY=YOUR_KEY

   macOS/Linux:
   export SERPAPI_KEY="YOUR_KEY"

3. First run only - resolve city CIDs:
   python lsa_rank_checker_final.py --find-cids

4. Run the rank scan:
   python lsa_rank_checker_final.py

Output
------
- Console:
    Burlington, MA      -> #4
    Billerica, MA       -> #11
    Bedford, MA         -> NOT_RANKING

- CSV:
    lsa_ranking_results.csv
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# =============================================================================
# CONFIGURATION
# =============================================================================

BUSINESS_NAME = "Apex Lock N Key"

# Loose aliases protect against minor Google name formatting differences.
BUSINESS_ALIASES = (
    "apex lock n key",
    "apex lock and key",
    "apex lock & key",
    "apexlocknkey",
)

# SerpApi-supported Local Services category.
LSA_QUERY = "locksmith"

# The 54 service areas visible in the supplied LSA screenshots.
VERIFIED_CITIES = [
    "Acton, MA",
    "Andover, MA",
    "Arlington, MA",
    "Bedford, MA",
    "Belmont, MA",
    "Billerica, MA",
    "Boston, MA",
    "Braintree, MA",
    "Brookline, MA",
    "Burlington, MA",
    "Cambridge, MA",
    "Canton, MA",
    "Chelmsford, MA",
    "Chelsea, MA",
    "Concord, MA",
    "Dedham, MA",
    "Dracut, MA",
    "Everett, MA",
    "Framingham, MA",
    "Haverhill, MA",
    "Lawrence, MA",
    "Lexington, MA",
    "Littleton, MA",
    "Lowell, MA",
    "Malden, MA",
    "Marlborough, MA",
    "Medford, MA",
    "Melrose, MA",
    "Methuen, MA",
    "Milton, MA",
    "Natick, MA",
    "Needham, MA",
    "Newton, MA",
    "North Andover, MA",
    "Norwood, MA",
    "Quincy, MA",
    "Reading, MA",
    "Revere, MA",
    "Somerville, MA",
    "Stoneham, MA",
    "Sudbury, MA",
    "Tewksbury, MA",
    "Wakefield, MA",
    "Waltham, MA",
    "Watertown, MA",
    "Wayland, MA",
    "Wellesley, MA",
    "Westford, MA",
    "Weston, MA",
    "Westwood, MA",
    "Wilmington, MA",
    "Winchester, MA",
    "Winthrop, MA",
    "Woburn, MA",
]

# If the account now has 58 cities, place the four additional city names here.
# Example:
# EXTRA_CITIES = ["Carlisle, MA", "Town 2, MA", "Town 3, MA", "Town 4, MA"]
EXTRA_CITIES: list[str] = []

CITIES = VERIFIED_CITIES + EXTRA_CITIES

API_KEY = os.environ.get("SERPAPI_KEY", "").strip()

CACHE_FILE = Path("city_cids.json")
OUTPUT_CSV = Path("data/lsa_ranking_results.csv")
RAW_DIR = Path("data/raw_lsa_json")
LATEST_JSON = Path("data/latest.json")
HISTORY_JSON = Path("data/history.json")

# Slow enough to avoid unnecessary bursts.
PAUSE_BETWEEN_CALLS = 1.0

# Retry transient request failures.
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 3

# Save raw JSON for troubleshooting / proof.
SAVE_RAW_JSON = True


# =============================================================================
# HTTP / API HELPERS
# =============================================================================

def serpapi_get(params: dict[str, Any]) -> dict[str, Any]:
    """Call SerpApi and return parsed JSON with retry handling."""
    if not API_KEY:
        raise RuntimeError("SERPAPI_KEY is not set.")

    payload = dict(params)
    payload["api_key"] = API_KEY
    payload["output"] = "json"

    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(payload)

    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "LSA-Rank-Checker/1.0",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))

            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError(f"SerpApi error: {data['error']}")

            if not isinstance(data, dict):
                raise RuntimeError("Unexpected non-object JSON response.")

            return data

        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            json.JSONDecodeError,
            RuntimeError,
        ) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)

    raise RuntimeError(f"API request failed after {MAX_RETRIES} attempts: {last_error}")


def sanitize_filename(value: str) -> str:
    """Convert a label into a filesystem-safe filename."""
    keep = []
    for char in value:
        if char.isalnum():
            keep.append(char.lower())
        elif char in (" ", "-", ","):
            keep.append("_")
    return "".join(keep).strip("_")


# =============================================================================
# CITY CID DISCOVERY
# =============================================================================

def load_cid_cache() -> dict[str, str]:
    """Load previously discovered city CIDs."""
    if not CACHE_FILE.exists():
        return {}

    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items() if v}
    except (OSError, json.JSONDecodeError):
        return {}


def save_cid_cache(cache: dict[str, str]) -> None:
    """Persist city CIDs."""
    CACHE_FILE.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def find_city_cid(city_label: str) -> str | None:
    """
    Resolve a Google data_cid for a city using SerpApi's Google Maps engine.

    A city-level data_cid is required by the Google Local Services API.
    """
    data = serpapi_get(
        {
            "engine": "google_maps",
            "q": city_label,
            "type": "search",
            "hl": "en",
            "gl": "us",
        }
    )

    # Some responses expose the requested place directly.
    place = data.get("place_results") or {}
    if isinstance(place, dict) and place.get("data_cid"):
        return str(place["data_cid"])

    # Otherwise inspect local results and prefer an exact city-name match.
    city_name = city_label.split(",")[0].strip().lower()
    candidates = data.get("local_results") or []

    exact_matches: list[str] = []
    fallback_matches: list[str] = []

    for item in candidates:
        if not isinstance(item, dict):
            continue

        cid = item.get("data_cid")
        if not cid:
            continue

        title = str(item.get("title", "")).strip().lower()
        address = str(item.get("address", "")).strip().lower()

        if title == city_name or title.startswith(city_name + ","):
            exact_matches.append(str(cid))
        elif city_name in title or city_name in address:
            fallback_matches.append(str(cid))

    if exact_matches:
        return exact_matches[0]

    if fallback_matches:
        return fallback_matches[0]

    return None


def discover_all_cids() -> None:
    """Resolve and cache a city CID for every configured city."""
    cache = load_cid_cache()

    print(f"Configured cities: {len(CITIES)}")
    print("Resolving city CIDs...\n")

    for city in CITIES:
        if cache.get(city):
            print(f"[CACHED] {city:<22} -> {cache[city]}")
            continue

        try:
            cid = find_city_cid(city)
        except RuntimeError as exc:
            print(f"[ERROR ] {city:<22} -> {exc}")
            time.sleep(PAUSE_BETWEEN_CALLS)
            continue

        if cid:
            cache[city] = cid
            save_cid_cache(cache)
            print(f"[FOUND ] {city:<22} -> {cid}")
        else:
            print(f"[MISS  ] {city:<22} -> CID_NOT_FOUND")

        time.sleep(PAUSE_BETWEEN_CALLS)

    print(f"\nSaved {len(cache)} CIDs to: {CACHE_FILE}")


# =============================================================================
# LSA RANKING
# =============================================================================

def normalize_business_name(value: str) -> str:
    """Normalize a business name for loose comparison."""
    return " ".join((value or "").lower().replace("&", "and").split())


def is_target_business(name: str) -> bool:
    """Return True when an LSA advertiser title matches Apex Lock N Key."""
    normalized = normalize_business_name(name)

    if normalized == normalize_business_name(BUSINESS_NAME):
        return True

    alias_normalized = {
        normalize_business_name(alias) for alias in BUSINESS_ALIASES
    }
    return normalized in alias_normalized


def extract_ads(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the ordered LSA advertiser list from a SerpApi response."""
    ads = data.get("local_ads") or []

    # The Local Services engine normally returns local_ads as a list.
    if isinstance(ads, list):
        return [item for item in ads if isinstance(item, dict)]

    # Defensive fallback if the API shape changes to a wrapper object.
    if isinstance(ads, dict):
        for key in ("ads", "results", "local_ads"):
            nested = ads.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]

    return []


def check_rank(city: str, data_cid: str) -> dict[str, str]:
    """
    Check the general Locksmith LSA rank for one city.

    Status values:
      #N              Exact position returned by the ordered LSA list.
      NOT_RANKING     LSA results exist, but Apex is absent from the returned list.
      NO_LSA_RESULTS  Google returned no LSA advertisers for that city/query.
      API_ERROR       SerpApi request failed.
      NO_CID          City CID has not been resolved.
    """
    record = {
        "City": city,
        "Rank": "",
        "Status": "",
        "Total Advertisers": "",
        "Checked At UTC": dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        ),
    }

    if not data_cid:
        record["Rank"] = "-"
        record["Status"] = "NO_CID"
        return record

    try:
        data = serpapi_get(
            {
                "engine": "google_local_services",
                "q": LSA_QUERY,
                "data_cid": data_cid,
                "hl": "en",
                # Default cache behavior is intentional:
                # SerpApi cache expires after about one hour and cached calls are free.
                "no_cache": "false",
            }
        )
    except RuntimeError as exc:
        record["Rank"] = "-"
        record["Status"] = f"API_ERROR: {exc}"
        return record

    if SAVE_RAW_JSON:
        RAW_DIR.mkdir(exist_ok=True)
        raw_path = RAW_DIR / f"{sanitize_filename(city)}.json"
        raw_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    ads = extract_ads(data)
    record["Total Advertisers"] = str(len(ads))

    if not ads:
        record["Rank"] = "-"
        record["Status"] = "NO_LSA_RESULTS"
        return record

    for index, ad in enumerate(ads, start=1):
        title = str(ad.get("title", "")).strip()
        if is_target_business(title):
            record["Rank"] = f"#{index}"
            record["Status"] = "RANKED"
            return record

    record["Rank"] = "-"
    record["Status"] = "NOT_RANKING"
    return record



def write_dashboard_json(results: list[dict[str, str]]) -> None:
    """Write latest results and append a compact historical snapshot."""
    LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)

    now_utc = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    latest_payload = {
        "business": BUSINESS_NAME,
        "category": LSA_QUERY,
        "checked_at_utc": now_utc,
        "city_count": len(CITIES),
        "results": results,
    }
    LATEST_JSON.write_text(
        json.dumps(latest_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    history = []
    if HISTORY_JSON.exists():
        try:
            loaded = json.loads(HISTORY_JSON.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                history = loaded
        except (OSError, json.JSONDecodeError):
            history = []

    snapshot = {
        "checked_at_utc": now_utc,
        "results": [
            {
                "City": row["City"],
                "Rank": row["Rank"],
                "Status": row["Status"],
            }
            for row in results
        ],
    }
    history.append(snapshot)
    history = history[-180:]

    HISTORY_JSON.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# =============================================================================
# MAIN
# =============================================================================

def validate_configuration() -> None:
    """Fail early on obvious configuration problems."""
    if len(set(CITIES)) != len(CITIES):
        duplicates = sorted({c for c in CITIES if CITIES.count(c) > 1})
        raise RuntimeError(f"Duplicate cities found: {duplicates}")

    if not API_KEY:
        raise RuntimeError(
            "SERPAPI_KEY is not set. Set it first, then run the script again."
        )


def run_scan() -> None:
    """Run one Locksmith LSA rank check for every configured city."""
    validate_configuration()

    cache = load_cid_cache()

    print("=" * 72)
    print("LSA RANK CHECKER - Apex Lock N Key")
    print(f"Cities configured : {len(CITIES)}")
    print(f"LSA category      : {LSA_QUERY}")
    print("=" * 72)
    print()

    if len(CITIES) != 58:
        print(
            f"NOTE: The supplied screenshots contain {len(VERIFIED_CITIES)} verified "
            "service-area cities, not 58."
        )
        print(
            "      If the live account now has 58, add the four newer city names "
            "to EXTRA_CITIES."
        )
        print()

    missing = [city for city in CITIES if not cache.get(city)]
    if missing:
        print("Missing city CIDs:")
        for city in missing:
            print(f"  - {city}")
        print()
        print("Run this once first:")
        print("  python lsa_rank_checker_final.py --find-cids")
        print()
        raise RuntimeError("CID discovery is required before ranking scan.")

    results: list[dict[str, str]] = []

    for number, city in enumerate(CITIES, start=1):
        result = check_rank(city, cache[city])
        results.append(result)

        print(
            f"[{number:02d}/{len(CITIES):02d}] "
            f"{city:<22} -> {result['Rank']:<5}  {result['Status']}"
        )

        time.sleep(PAUSE_BETWEEN_CALLS)

    fieldnames = [
        "City",
        "Rank",
        "Status",
        "Total Advertisers",
        "Checked At UTC",
    ]

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    write_dashboard_json(results)

    ranked = sum(1 for row in results if row["Status"] == "RANKED")
    not_ranking = sum(1 for row in results if row["Status"] == "NOT_RANKING")
    no_results = sum(1 for row in results if row["Status"] == "NO_LSA_RESULTS")
    errors = sum(1 for row in results if row["Status"].startswith("API_ERROR"))

    print()
    print("=" * 72)
    print("SCAN COMPLETE")
    print(f"Ranked cities     : {ranked}")
    print(f"Not ranking       : {not_ranking}")
    print(f"No LSA results    : {no_results}")
    print(f"API errors        : {errors}")
    print(f"CSV saved to      : {OUTPUT_CSV}")
    if SAVE_RAW_JSON:
        print(f"Raw JSON saved in : {RAW_DIR}/")
    print("=" * 72)


def main() -> None:
    try:
        validate_configuration()

        if "--find-cids" in sys.argv:
            discover_all_cids()
            return

        run_scan()

    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(130)

    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
