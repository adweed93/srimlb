"""MLB Favorites Dashboard - Flask Web App (mobile-friendly)."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import statsapi
from flask import Flask, render_template, jsonify, request

from mlb_notifications import NotificationChecker
from mlb_thresholds import get_thresholds

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))

FAVORITES_FILE = Path(__file__).parent / "mlb_favorites.json"
LAST_RUN_FILE = Path(__file__).parent / "mlb_last_run.json"


def load_favorites():
    if FAVORITES_FILE.exists():
        return json.loads(FAVORITES_FILE.read_text())
    return {"players": [], "teams": []}


def save_favorites(favs):
    FAVORITES_FILE.write_text(json.dumps(favs, indent=2))


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/favorites")
def get_favorites():
    return jsonify(load_favorites())


@app.route("/api/search/player")
def search_player():
    q = request.args.get("q", "")
    if not q:
        return jsonify([])
    results = statsapi.lookup_player(q)
    return jsonify([{"id": p["id"], "name": p["fullName"], "team": p.get("currentTeam", {}).get("name", "N/A")} for p in results[:10]])


@app.route("/api/search/team")
def search_team():
    q = request.args.get("q", "")
    if not q:
        return jsonify([])
    results = statsapi.lookup_team(q)
    return jsonify([{"id": t["id"], "name": t["name"]} for t in results[:10]])


@app.route("/api/favorites/add", methods=["POST"])
def add_favorite():
    data = request.json
    favs = load_favorites()
    key = "teams" if data.get("type") == "team" else "players"
    if not any(f["id"] == data["id"] for f in favs[key]):
        favs[key].append({"id": data["id"], "name": data["name"]})
        save_favorites(favs)
    return jsonify({"ok": True})


@app.route("/api/favorites/remove", methods=["POST"])
def remove_favorite():
    data = request.json
    favs = load_favorites()
    key = "teams" if data.get("type") == "team" else "players"
    favs[key] = [f for f in favs[key] if f["id"] != data["id"]]
    save_favorites(favs)
    return jsonify({"ok": True})


@app.route("/api/live")
def live_games():
    games = statsapi.schedule()
    fav_ids = {t["id"] for t in load_favorites().get("teams", [])}
    result = {"live": [], "upcoming": [], "final": []}
    for g in games:
        entry = {
            "away": g["away_name"], "home": g["home_name"],
            "away_score": g.get("away_score", 0), "home_score": g.get("home_score", 0),
            "status": g["status"], "inning": g.get("current_inning", ""),
            "inning_state": g.get("inning_state", ""),
            "fav": g.get("home_id") in fav_ids or g.get("away_id") in fav_ids,
        }
        if g["status"] == "In Progress":
            result["live"].append(entry)
        elif g["status"] == "Final":
            result["final"].append(entry)
        else:
            result["upcoming"].append(entry)
    return jsonify(result)


@app.route("/api/team/<int:team_id>")
def team_stats(team_id):
    standings = statsapi.standings_data()
    schedule = statsapi.schedule(team=team_id)
    record = {}
    for div_data in standings.values():
        for t in div_data["teams"]:
            if t["team_id"] == team_id:
                record = {"w": t["w"], "l": t["l"], "rank": t["div_rank"], "gb": t["gb"], "div": div_data["div_name"]}
                break

    recent = []
    final_games = [g for g in schedule if g["status"] == "Final"]
    for g in final_games[-7:]:
        home = g.get("home_id") == team_id
        recent.append({
            "date": g["game_date"], "opponent": g["away_name"] if home else g["home_name"],
            "score": f"{g.get('home_score',0)}-{g.get('away_score',0)}" if home else f"{g.get('away_score',0)}-{g.get('home_score',0)}",
            "won": (home and g.get("home_score", 0) > g.get("away_score", 0)) or (not home and g.get("away_score", 0) > g.get("home_score", 0)),
            "home": home,
        })

    live = None
    for g in schedule:
        if g["status"] == "In Progress":
            live = {"away": g["away_name"], "home": g["home_name"], "away_score": g.get("away_score", 0), "home_score": g.get("home_score", 0), "inning": g.get("current_inning", ""), "inning_state": g.get("inning_state", "")}
            break

    return jsonify({"record": record, "recent": recent, "live": live})


@app.route("/api/player/<int:player_id>")
def player_stats(player_id):
    info = statsapi.player_stat_data(player_id, type="season")
    stats = {}
    for sg in info.get("stats", []):
        if sg["group"] == "hitting":
            stats = sg.get("stats", {})
            break
        elif sg["group"] == "pitching":
            stats = sg.get("stats", {})
            break

    # Anomaly check
    t = get_thresholds()
    anomalies = []
    games = int(stats.get("gamesPlayed", 0))
    if games > 20 and info.get("position") != "P":
        bat_season = t.get("batting_season", {})
        avg = float(stats.get("avg", "0"))
        hr = int(stats.get("homeRuns", 0))
        hr_pace = (hr / games) * 162
        if avg >= bat_season.get("avg_alltime", 0.37):
            anomalies.append({"msg": f"Batting .{int(avg*1000)} — ALL-TIME TERRITORY", "level": "alltime"})
        elif avg >= bat_season.get("avg_anomalous", 0.33):
            anomalies.append({"msg": f"Batting .{int(avg*1000)} — elite", "level": "alert"})
        if hr_pace >= bat_season.get("hr_pace_alltime", 52):
            anomalies.append({"msg": f"On pace for {int(hr_pace)} HRs — RECORD PACE", "level": "alltime"})
        elif hr_pace >= bat_season.get("hr_pace_anomalous", 39):
            anomalies.append({"msg": f"On pace for {int(hr_pace)} HRs", "level": "alert"})

    return jsonify({
        "name": info.get("first_name", "") + " " + info.get("last_name", ""),
        "position": info.get("position", ""),
        "team": info.get("current_team", ""),
        "stats": stats,
        "anomalies": anomalies,
    })


@app.route("/api/notifications")
def notifications():
    favs = load_favorites()
    checker = NotificationChecker(favs)
    checker.check_all()
    notifs = checker.get_all_notifications()
    return jsonify(notifs)


@app.route("/api/notifications/clear", methods=["POST"])
def clear_notifications():
    checker = NotificationChecker(load_favorites())
    checker.clear_notifications()
    return jsonify({"ok": True})


@app.route("/api/synopsis")
def synopsis():
    favs = load_favorites()
    data = {"teams": [], "players": []}
    for team in favs.get("teams", []):
        try:
            standings = statsapi.standings_data()
            schedule = statsapi.schedule(team=team["id"])
            record = {}
            for div_data in standings.values():
                for t in div_data["teams"]:
                    if t["team_id"] == team["id"]:
                        record = {"w": t["w"], "l": t["l"], "rank": t["div_rank"], "gb": t["gb"]}
                        break
            final = [g for g in schedule if g["status"] == "Final"]
            recent = []
            for g in final[-5:]:
                home = g.get("home_id") == team["id"]
                won = (home and g.get("home_score", 0) > g.get("away_score", 0)) or (not home and g.get("away_score", 0) > g.get("home_score", 0))
                recent.append({"won": won, "score": f"{g.get('away_score',0)}-{g.get('home_score',0)}", "vs": g["away_name"] if home else g["home_name"]})
            data["teams"].append({"name": team["name"], "record": record, "recent": recent})
        except Exception:
            data["teams"].append({"name": team["name"], "record": {}, "recent": []})

    for player in favs.get("players", []):
        try:
            info = statsapi.player_stat_data(player["id"], type="season")
            stats = {}
            for sg in info.get("stats", []):
                if sg["group"] in ("hitting", "pitching"):
                    stats = sg.get("stats", {})
                    break
            data["players"].append({"name": player["name"], "position": info.get("position", ""), "team": info.get("current_team", ""), "stats": stats})
        except Exception:
            data["players"].append({"name": player["name"], "position": "", "team": "", "stats": {}})

    return jsonify(data)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
