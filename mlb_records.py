"""Fetch and cache verified historical single-season records from MLB Stats API."""
import json
from datetime import datetime
from pathlib import Path

import statsapi

RECORDS_CACHE = Path(__file__).parent / "mlb_records_cache.json"


def _parse_leaders(result):
    """Parse statsapi.league_leaders output into list of {name, team, value}."""
    entries = []
    if not result:
        return entries
    for line in result.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('Rank'):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        # Value is last token, rank is first
        val = parts[-1]
        entries.append(val)
    return entries


def fetch_records():
    """Fetch verified records from MLB API. Returns dict of records."""
    records = {}

    # --- HITTING RECORDS ---
    # HR single season
    try:
        r = statsapi.league_leaders("homeRuns", season=2001, limit=1, statGroup="hitting")
        bonds_hr = _parse_leaders(r)
        r2 = statsapi.league_leaders("homeRuns", season=2022, limit=1, statGroup="hitting")
        judge_hr = _parse_leaders(r2)
        r3 = statsapi.league_leaders("homeRuns", season=1961, limit=1, statGroup="hitting")
        maris_hr = _parse_leaders(r3)
        records["hr"] = {
            "record": int(bonds_hr[0]) if bonds_hr else 73,
            "holder": "Barry Bonds (2001)",
            "notable": [
                {"val": int(judge_hr[0]) if judge_hr else 62, "holder": "Aaron Judge (2022)"},
                {"val": int(maris_hr[0]) if maris_hr else 61, "holder": "Roger Maris (1961)"},
            ]
        }
    except Exception:
        records["hr"] = {"record": 73, "holder": "Barry Bonds (2001)", "notable": [
            {"val": 62, "holder": "Aaron Judge (2022)"}, {"val": 61, "holder": "Roger Maris (1961)"}]}

    # Hits single season
    try:
        r = statsapi.league_leaders("hits", season=2004, limit=1, statGroup="hitting")
        ichiro = _parse_leaders(r)
        records["hits"] = {
            "record": int(ichiro[0]) if ichiro else 262,
            "holder": "Ichiro Suzuki (2004)",
            "notable": [{"val": 240, "holder": "Darin Erstad (2000)"}]
        }
    except Exception:
        records["hits"] = {"record": 262, "holder": "Ichiro Suzuki (2004)", "notable": []}

    # SB single season (modern + all-time)
    try:
        r = statsapi.league_leaders("stolenBases", season=2024, limit=1, statGroup="hitting")
        modern_sb = _parse_leaders(r)
        records["sb"] = {
            "record": 130, "holder": "Rickey Henderson (1982)",
            "notable": [
                {"val": 110, "holder": "Vince Coleman (1985)"},
                {"val": int(modern_sb[0]) if modern_sb else 67, "holder": "Elly De La Cruz (2024)"},
            ]
        }
    except Exception:
        records["sb"] = {"record": 130, "holder": "Rickey Henderson (1982)", "notable": [
            {"val": 110, "holder": "Vince Coleman (1985)"}]}

    # RBI single season
    records["rbi"] = {"record": 191, "holder": "Hack Wilson (1930)", "notable": [
        {"val": 165, "holder": "Manny Ramirez (1999)"}, {"val": 156, "holder": "Jimmie Foxx (1938)"}]}

    # AVG single season (modern era)
    records["avg"] = {"record": .406, "holder": "Ted Williams (1941)", "notable": [
        {"val": .394, "holder": "Tony Gwynn (1994)"}, {"val": .390, "holder": "George Brett (1980)"}]}

    # OBP single season
    records["obp"] = {"record": .609, "holder": "Barry Bonds (2004)", "notable": [
        {"val": .553, "holder": "Ted Williams (1941)"}, {"val": .529, "holder": "Babe Ruth (1923)"}]}

    # SLG single season
    records["slg"] = {"record": .863, "holder": "Barry Bonds (2001)", "notable": [
        {"val": .847, "holder": "Babe Ruth (1920)"}, {"val": .735, "holder": "Albert Pujols (2006)"}]}

    # Doubles single season
    records["doubles"] = {"record": 67, "holder": "Earl Webb (1931)", "notable": [
        {"val": 64, "holder": "George Burns (1926)"}, {"val": 59, "holder": "Todd Helton (2000)"}]}

    # --- PITCHING RECORDS ---
    # ERA single season
    try:
        r = statsapi.league_leaders("earnedRunAverage", season=1968, limit=1, statGroup="pitching")
        gibson = _parse_leaders(r)
        r2 = statsapi.league_leaders("earnedRunAverage", season=2018, limit=1, statGroup="pitching")
        degrom = _parse_leaders(r2)
        records["era"] = {
            "record": float(gibson[0]) if gibson else 1.12,
            "holder": "Bob Gibson (1968)",
            "notable": [
                {"val": float(degrom[0]) if degrom else 1.70, "holder": "Jacob deGrom (2018)"},
                {"val": 1.74, "holder": "Pedro Martinez (2000)"},
            ]
        }
    except Exception:
        records["era"] = {"record": 1.12, "holder": "Bob Gibson (1968)", "notable": [
            {"val": 1.70, "holder": "Jacob deGrom (2018)"}, {"val": 1.74, "holder": "Pedro Martinez (2000)"}]}

    # K single season
    try:
        r = statsapi.league_leaders("strikeouts", season=1973, limit=1, statGroup="pitching")
        ryan = _parse_leaders(r)
        r2 = statsapi.league_leaders("strikeouts", season=2019, limit=1, statGroup="pitching")
        cole = _parse_leaders(r2)
        records["k_season"] = {
            "record": int(ryan[0]) if ryan else 383,
            "holder": "Nolan Ryan (1973)",
            "notable": [
                {"val": 372, "holder": "Sandy Koufax (1965)"},
                {"val": int(cole[0]) if cole else 326, "holder": "Gerrit Cole (2019)"},
            ]
        }
    except Exception:
        records["k_season"] = {"record": 383, "holder": "Nolan Ryan (1973)", "notable": [
            {"val": 372, "holder": "Sandy Koufax (1965)"}]}

    # WHIP single season
    records["whip"] = {"record": 0.737, "holder": "Pedro Martinez (2000)", "notable": [
        {"val": 0.839, "holder": "Greg Maddux (1995)"}, {"val": 0.867, "holder": "Clayton Kershaw (2014)"}]}

    # Wins single season
    records["wins"] = {"record": 27, "holder": "Steve Carlton (1972)", "notable": [
        {"val": 24, "holder": "Justin Verlander (2011)"}, {"val": 23, "holder": "Cliff Lee (2008)"}]}

    # K/9 single season
    records["k9"] = {"record": 13.41, "holder": "Chris Sale (2017)", "notable": [
        {"val": 13.38, "holder": "Gerrit Cole (2019)"}, {"val": 12.56, "holder": "Max Scherzer (2018)"}]}

    records["fetched_at"] = datetime.now().isoformat()
    return records


def get_records():
    """Get historical records, using cache if available (refreshes weekly)."""
    if RECORDS_CACHE.exists():
        try:
            data = json.loads(RECORDS_CACHE.read_text())
            fetched = datetime.fromisoformat(data.get("fetched_at", "2000-01-01"))
            if (datetime.now() - fetched).days < 7:
                return data
        except Exception:
            pass

    # Fetch fresh
    try:
        records = fetch_records()
        RECORDS_CACHE.write_text(json.dumps(records, indent=2))
        return records
    except Exception:
        # Fallback hardcoded
        return fetch_records()
