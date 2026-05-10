"""Compute anomaly thresholds from real MLB historical data using pybaseball."""

import json
from datetime import datetime
from pathlib import Path

import numpy as np

THRESHOLDS_CACHE = Path(__file__).parent / "mlb_thresholds_cache.json"
CACHE_MAX_AGE_DAYS = 7


def _cache_valid():
    if not THRESHOLDS_CACHE.exists():
        return False
    try:
        data = json.loads(THRESHOLDS_CACHE.read_text())
        cached_date = datetime.fromisoformat(data["computed_at"])
        return (datetime.now() - cached_date).days < CACHE_MAX_AGE_DAYS
    except Exception:
        return False


def _load_cache():
    return json.loads(THRESHOLDS_CACHE.read_text())


def _save_cache(data):
    data["computed_at"] = datetime.now().isoformat()
    THRESHOLDS_CACHE.write_text(json.dumps(data, indent=2))


def compute_thresholds():
    """Compute thresholds from historical data. Returns cached if recent."""
    if _cache_valid():
        return _load_cache()

    thresholds = {}

    # Try pybaseball first
    thresholds = _try_pybaseball()

    # If pybaseball failed, try MLB Stats API
    if not thresholds.get("batting_anomalous"):
        thresholds = _try_statsapi()

    # If both failed, use fallback
    if not thresholds.get("batting_anomalous"):
        return _fallback_thresholds()

    _save_cache(thresholds)
    return thresholds


def _try_statsapi():
    """Compute thresholds from MLB Stats API single-season leaders."""
    import statsapi

    thresholds = {}
    try:
        # Fetch all-time single season records via stats API
        # Use league leaders to find top performances
        hr_leaders = statsapi.league_leaders("homeRuns", season=2024, limit=50)
        so_leaders = statsapi.league_leaders("strikeouts", season=2024, limit=50, playerPool="All", statGroup="pitching")

        # Parse HR leaders to get distribution
        # league_leaders returns formatted string, parse the numbers
        hr_values = _parse_leader_values(hr_leaders)
        so_values = _parse_leader_values(so_leaders)

        if hr_values:
            # 95th percentile of top-50 = anomalous game threshold basis
            # Top-50 HR hitters average ~0.2 HR/game, anomalous = 2+, alltime = 3+
            avg_hr_per_game = np.mean(hr_values) / 162
            thresholds["batting_anomalous"] = {
                "homeRuns": {"game": max(2, int(np.ceil(np.percentile(hr_values, 80) / 162 * 8))), "label": "Multi-HR game"},
                "hits": {"game": 4, "label": "4+ hit game"},
                "rbi": {"game": max(4, int(np.ceil(np.percentile(hr_values, 90) / 162 * 6))), "label": "Big RBI game"},
                "stolenBases": {"game": 3, "label": "3+ stolen bases"},
            }
            thresholds["batting_alltime"] = {
                "homeRuns": {"game": max(3, int(np.ceil(np.percentile(hr_values, 98) / 162 * 8))), "label": "HR EXPLOSION"},
                "hits": {"game": 5, "label": "5+ HIT GAME"},
                "rbi": {"game": max(7, int(np.ceil(np.percentile(hr_values, 98) / 162 * 10))), "label": "HISTORIC RBI GAME"},
                "stolenBases": {"game": 5, "label": "STOLEN BASE SPREE"},
            }
            thresholds["batting_season"] = {
                "avg_anomalous": 0.330,
                "avg_alltime": 0.370,
                "hr_pace_anomalous": int(np.percentile(hr_values, 90)),
                "hr_pace_alltime": int(np.percentile(hr_values, 98)),
            }

        if so_values:
            so_per_start = np.mean(so_values) / 33  # ~33 starts per season
            thresholds["pitching_anomalous"] = {
                "strikeOuts": {"game": max(10, int(np.ceil(np.percentile(so_values, 80) / 33))), "label": "High-K game"},
            }
            thresholds["pitching_alltime"] = {
                "strikeOuts": {"game": max(14, int(np.ceil(np.percentile(so_values, 98) / 33))), "label": "HISTORIC K GAME"},
            }
            thresholds["pitching_season"] = {
                "era_anomalous": 2.50,
                "era_alltime": 1.80,
            }

        thresholds["team_anomalous"] = {"win_streak": 7, "loss_streak": 7, "runs_scored_game": 14}
        thresholds["team_alltime"] = {"win_streak": 13, "runs_scored_game": 20}

    except Exception:
        pass

    return thresholds


def _parse_leader_values(leader_str):
    """Parse numeric stat values from statsapi.league_leaders output."""
    values = []
    if not leader_str:
        return values
    for line in leader_str.strip().split("\n"):
        parts = line.strip().split()
        # Last token is usually the stat value
        for part in reversed(parts):
            try:
                val = int(part)
                values.append(val)
                break
            except ValueError:
                try:
                    val = float(part)
                    values.append(val)
                    break
                except ValueError:
                    continue
    return values


def _try_pybaseball():
    """Try to compute thresholds from pybaseball FanGraphs data."""
    thresholds = {}
    try:
        from pybaseball import batting_stats, pitching_stats
    except ImportError:
        return thresholds

    try:
        batting = batting_stats(2019, 2024, qual=50)

        if batting is not None and not batting.empty:
            batting["HR_per_game"] = batting["HR"] / batting["G"]
            batting["H_per_game"] = batting["H"] / batting["G"]
            batting["RBI_per_game"] = batting["RBI"] / batting["G"]
            batting["SB_per_game"] = batting["SB"] / batting["G"]

            thresholds["batting_anomalous"] = {
                "homeRuns": {"game": max(2, int(np.ceil(np.percentile(batting["HR_per_game"], 99) * 3))), "label": "Multi-HR game"},
                "hits": {"game": max(4, int(np.ceil(np.percentile(batting["H_per_game"], 99) * 3))), "label": "4+ hit game"},
                "rbi": {"game": max(4, int(np.ceil(np.percentile(batting["RBI_per_game"], 99) * 4))), "label": "Big RBI game"},
                "stolenBases": {"game": max(3, int(np.ceil(np.percentile(batting["SB_per_game"], 99) * 5))), "label": "Multi-SB game"},
            }
            thresholds["batting_alltime"] = {
                "homeRuns": {"game": max(3, int(np.ceil(np.percentile(batting["HR_per_game"], 99.9) * 4))), "label": "HR EXPLOSION"},
                "hits": {"game": max(5, int(np.ceil(np.percentile(batting["H_per_game"], 99.9) * 3))), "label": "5+ HIT GAME"},
                "rbi": {"game": max(7, int(np.ceil(np.percentile(batting["RBI_per_game"], 99.9) * 5))), "label": "HISTORIC RBI GAME"},
                "stolenBases": {"game": max(5, int(np.ceil(np.percentile(batting["SB_per_game"], 99.9) * 6))), "label": "STOLEN BASE SPREE"},
            }
            thresholds["batting_season"] = {
                "avg_anomalous": round(float(np.percentile(batting["AVG"].dropna(), 98)), 3),
                "avg_alltime": round(float(np.percentile(batting["AVG"].dropna(), 99.5)), 3),
                "hr_pace_anomalous": int(np.percentile(batting["HR"].dropna(), 97)),
                "hr_pace_alltime": int(np.percentile(batting["HR"].dropna(), 99.5)),
            }
    except Exception:
        pass

    try:
        pitching = pitching_stats(2019, 2024, qual=30)

        if pitching is not None and not pitching.empty:
            pitching["SO_per_game"] = pitching["SO"] / pitching["GS"].replace(0, 1)

            thresholds["pitching_anomalous"] = {
                "strikeOuts": {"game": max(10, int(np.ceil(np.percentile(pitching["SO_per_game"].dropna(), 98)))), "label": "High-K game"},
            }
            thresholds["pitching_alltime"] = {
                "strikeOuts": {"game": max(14, int(np.ceil(np.percentile(pitching["SO_per_game"].dropna(), 99.9)))), "label": "HISTORIC K GAME"},
            }
            thresholds["pitching_season"] = {
                "era_anomalous": round(float(np.percentile(pitching["ERA"].dropna(), 3)), 2),
                "era_alltime": round(float(np.percentile(pitching["ERA"].dropna(), 0.5)), 2),
            }
    except Exception:
        pass

    thresholds["team_anomalous"] = {"win_streak": 7, "loss_streak": 7, "runs_scored_game": 14}
    thresholds["team_alltime"] = {"win_streak": 13, "runs_scored_game": 20}

    return thresholds


def _fallback_thresholds():
    """Hardcoded fallback if pybaseball data can't be fetched."""
    return {
        "batting_anomalous": {
            "homeRuns": {"game": 2, "label": "Multi-HR game"},
            "hits": {"game": 4, "label": "4+ hit game"},
            "rbi": {"game": 5, "label": "5+ RBI game"},
            "stolenBases": {"game": 3, "label": "3+ stolen bases"},
        },
        "batting_alltime": {
            "homeRuns": {"game": 3, "label": "3-HR GAME"},
            "hits": {"game": 5, "label": "5+ HIT GAME"},
            "rbi": {"game": 8, "label": "8+ RBI GAME"},
            "stolenBases": {"game": 5, "label": "5+ STOLEN BASES"},
        },
        "pitching_anomalous": {
            "strikeOuts": {"game": 10, "label": "10+ strikeout game"},
        },
        "pitching_alltime": {
            "strikeOuts": {"game": 15, "label": "15+ STRIKEOUT GAME"},
        },
        "batting_season": {
            "avg_anomalous": 0.330, "avg_alltime": 0.370,
            "hr_pace_anomalous": 45, "hr_pace_alltime": 62,
        },
        "pitching_season": {
            "era_anomalous": 2.20, "era_alltime": 1.50,
        },
        "team_anomalous": {"win_streak": 7, "loss_streak": 7, "runs_scored_game": 14},
        "team_alltime": {"win_streak": 13, "runs_scored_game": 20},
        "computed_at": datetime.now().isoformat(),
    }


def get_thresholds():
    """Main entry point - returns thresholds dict, computing if needed."""
    return compute_thresholds()
