"""MLB Notifications - Detects statistically anomalous events for favorite players/teams."""

import json
import threading
from datetime import datetime
from pathlib import Path

import statsapi
from mlb_thresholds import get_thresholds

NOTIF_FILE = Path(__file__).parent / "mlb_notifications.json"
CHECK_INTERVAL_MS = 60000  # Check every 60 seconds

# Thresholds loaded dynamically from real historical data (pybaseball)
_thresholds = None

def _get_thresh():
    global _thresholds
    if _thresholds is None:
        _thresholds = get_thresholds()
    return _thresholds


def load_notifications():
    if NOTIF_FILE.exists():
        return json.loads(NOTIF_FILE.read_text())
    return {"notifications": [], "seen_events": []}


def save_notifications(data):
    NOTIF_FILE.write_text(json.dumps(data, indent=2))


def add_notification(msg, category="info"):
    data = load_notifications()
    notif = {
        "time": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "message": msg,
        "category": category,
        "read": False,
    }
    data["notifications"].insert(0, notif)
    # Keep last 50
    data["notifications"] = data["notifications"][:50]
    save_notifications(data)
    return notif


def _event_key(player_id, game_id, event_type):
    return f"{player_id}_{game_id}_{event_type}"


def _already_notified(key):
    data = load_notifications()
    return key in data.get("seen_events", [])


def _mark_notified(key):
    data = load_notifications()
    data.setdefault("seen_events", []).append(key)
    # Keep last 200 event keys
    data["seen_events"] = data["seen_events"][-200:]
    save_notifications(data)


def check_player_anomalies(player):
    """Check a player's current game stats for anomalies. Returns list of (msg, category) tuples."""
    alerts = []
    player_id = player["id"]

    try:
        info = statsapi.player_stat_data(player_id, type="season")
        position = info.get("position", "")
        stats_list = info.get("stats", [])
        if not stats_list:
            return alerts

        season_stats = stats_list[0].get("stats", {})

        game_log = statsapi.player_stat_data(player_id, type="gameLog")
        if not game_log.get("stats"):
            return alerts

        game_stats_list = game_log["stats"][0].get("stats", {})
        if not game_stats_list:
            return alerts

        if position != "P":
            games_played = int(season_stats.get("gamesPlayed", 1)) or 1
            season_hr = int(season_stats.get("homeRuns", 0))
            season_avg = float(season_stats.get("avg", ".000").replace(".", "0.") if season_stats.get("avg", "").startswith(".") else season_stats.get("avg", 0))

            for stat_key, thresh in _get_thresh()["batting_anomalous"].items():
                val = int(game_stats_list.get(stat_key, 0))
                if val >= thresh["game"]:
                    # Check if all-time level
                    alltime = _get_thresh()["batting_alltime"].get(stat_key)
                    if alltime and val >= alltime["game"]:
                        event_key = _event_key(player_id, datetime.now().strftime("%Y%m%d"), f"{stat_key}_alltime")
                        if not _already_notified(event_key):
                            alerts.append((f"👑 {player['name']}: {alltime['label']}! ({val} {stat_key} today) — ALL-TIME TERRITORY", "alltime"))
                            _mark_notified(event_key)
                    else:
                        event_key = _event_key(player_id, datetime.now().strftime("%Y%m%d"), stat_key)
                        if not _already_notified(event_key):
                            alerts.append((f"🔥 {player['name']}: {thresh['label']}! ({val} {stat_key} today)", "alert"))
                            _mark_notified(event_key)

            bat_season = _get_thresh().get("batting_season", {})
            if season_avg >= bat_season.get("avg_alltime", 0.370) and games_played > 30:
                event_key = _event_key(player_id, "season", "avg_alltime")
                if not _already_notified(event_key):
                    alerts.append((f"👑 {player['name']} batting .{int(season_avg*1000)} — HISTORIC AVG! — ALL-TIME TERRITORY", "alltime"))
                    _mark_notified(event_key)
            elif season_avg >= bat_season.get("avg_anomalous", 0.330) and games_played > 20:
                event_key = _event_key(player_id, "season", "avg_anom")
                if not _already_notified(event_key):
                    alerts.append((f"📈 {player['name']} batting .{int(season_avg*1000)} on the season!", "alert"))
                    _mark_notified(event_key)

            if games_played > 20:
                hr_pace = (season_hr / games_played) * 162
                if hr_pace >= bat_season.get("hr_pace_alltime", 62):
                    event_key = _event_key(player_id, "season", f"hrpace_alltime")
                    if not _already_notified(event_key):
                        alerts.append((f"👑 {player['name']} on pace for {int(hr_pace)} HRs — RECORD PACE! — ALL-TIME TERRITORY", "alltime"))
                        _mark_notified(event_key)
                elif hr_pace >= bat_season.get("hr_pace_anomalous", 45):
                    event_key = _event_key(player_id, "season", f"hrpace{int(hr_pace)//5}")
                    if not _already_notified(event_key):
                        alerts.append((f"💣 {player['name']} on pace for {int(hr_pace)} HRs this season!", "alert"))
                        _mark_notified(event_key)

        else:
            for stat_key, thresh in _get_thresh().get("pitching_anomalous", {}).items():
                val_raw = game_stats_list.get(stat_key, 0)
                val = int(float(val_raw)) if val_raw else 0
                if val >= thresh["game"]:
                    alltime = _get_thresh().get("pitching_alltime", {}).get(stat_key)
                    if alltime and val >= alltime["game"]:
                        event_key = _event_key(player_id, datetime.now().strftime("%Y%m%d"), f"{stat_key}_alltime")
                        if not _already_notified(event_key):
                            alerts.append((f"👑 {player['name']}: {alltime['label']}! ({val} today) — ALL-TIME TERRITORY", "alltime"))
                            _mark_notified(event_key)
                    else:
                        event_key = _event_key(player_id, datetime.now().strftime("%Y%m%d"), stat_key)
                        if not _already_notified(event_key):
                            alerts.append((f"🔥 {player['name']}: {thresh['label']}! ({val} today)", "alert"))
                            _mark_notified(event_key)

            era = float(season_stats.get("era", "99.00"))
            games_started = int(season_stats.get("gamesStarted", 0))
            pitch_season = _get_thresh().get("pitching_season", {})
            if era <= pitch_season.get("era_alltime", 1.50) and games_started >= 8:
                event_key = _event_key(player_id, "season", "era_alltime")
                if not _already_notified(event_key):
                    alerts.append((f"👑 {player['name']} has a {era:.2f} ERA through {games_started} starts — ALL-TIME TERRITORY", "alltime"))
                    _mark_notified(event_key)
            elif era <= pitch_season.get("era_anomalous", 2.20) and games_started >= 5:
                event_key = _event_key(player_id, "season", "era_anom")
                if not _already_notified(event_key):
                    alerts.append((f"🧊 {player['name']} has a {era:.2f} ERA through {games_started} starts!", "alert"))
                    _mark_notified(event_key)

    except Exception:
        pass

    return alerts


def check_team_anomalies(team):
    """Check team for streaks and anomalous performances."""
    alerts = []
    team_id = team["id"]

    try:
        schedule = statsapi.schedule(team=team_id)
        final_games = [g for g in schedule if g["status"] == "Final"]

        if not final_games:
            return alerts

        # Check win/loss streak from recent games
        streak = 0
        streak_type = None
        for g in reversed(final_games):
            home = g.get("home_id") == team_id
            won = (home and g.get("home_score", 0) > g.get("away_score", 0)) or \
                  (not home and g.get("away_score", 0) > g.get("home_score", 0))
            if streak_type is None:
                streak_type = "W" if won else "L"
                streak = 1
            elif (won and streak_type == "W") or (not won and streak_type == "L"):
                streak += 1
            else:
                break

        team_thresh = _get_thresh().get("team_anomalous", {})
        team_alltime = _get_thresh().get("team_alltime", {})

        if streak >= team_thresh.get("win_streak", 7) and streak_type == "W":
            if streak >= team_alltime.get("win_streak", 13):
                event_key = f"team_{team_id}_winstreak_alltime_{streak}"
                if not _already_notified(event_key):
                    alerts.append((f"👑 {team['name']} on a {streak}-GAME WIN STREAK — ALL-TIME TERRITORY", "alltime"))
                    _mark_notified(event_key)
            else:
                event_key = f"team_{team_id}_winstreak_{streak}"
                if not _already_notified(event_key):
                    alerts.append((f"🔥 {team['name']} are on a {streak}-game win streak!", "alert"))
                    _mark_notified(event_key)

        if streak >= team_thresh.get("loss_streak", 7) and streak_type == "L":
            event_key = f"team_{team_id}_lossstreak_{streak}"
            if not _already_notified(event_key):
                alerts.append((f"📉 {team['name']} have lost {streak} in a row", "alert"))
                _mark_notified(event_key)

        # Check last game for blowout
        last = final_games[-1]
        home = last.get("home_id") == team_id
        team_score = last.get("home_score", 0) if home else last.get("away_score", 0)
        if team_score >= team_alltime.get("runs_scored_game", 20):
            event_key = f"team_{team_id}_{last['game_id']}_blowout_alltime"
            if not _already_notified(event_key):
                alerts.append((f"👑 {team['name']} scored {team_score} RUNS — ALL-TIME TERRITORY", "alltime"))
                _mark_notified(event_key)
        elif team_score >= team_thresh.get("runs_scored_game", 14):
            event_key = f"team_{team_id}_{last['game_id']}_blowout"
            if not _already_notified(event_key):
                alerts.append((f"💥 {team['name']} scored {team_score} runs last game!", "alert"))
                _mark_notified(event_key)

    except Exception:
        pass

    return alerts


class NotificationChecker:
    """Background checker that periodically scans favorites for anomalies."""

    def __init__(self, favorites, on_new_notifications=None):
        self.favorites = favorites
        self.on_new = on_new_notifications
        self._running = False

    def check_all(self):
        """Run one check cycle. Returns list of new alert strings."""
        all_alerts = []
        for player in self.favorites.get("players", []):
            all_alerts.extend(check_player_anomalies(player))
        for team in self.favorites.get("teams", []):
            all_alerts.extend(check_team_anomalies(team))

        # Save as notifications
        for msg, category in all_alerts:
            add_notification(msg, category)

        return all_alerts

    def get_all_notifications(self):
        data = load_notifications()
        return data.get("notifications", [])

    def clear_notifications(self):
        data = load_notifications()
        data["notifications"] = []
        save_notifications(data)
