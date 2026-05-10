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
    # Resolve team names from IDs
    teams_data = {t["id"]: t["name"] for t in statsapi.get("teams", {"sportIds": 1})["teams"]}
    return jsonify([{
        "id": p["id"],
        "name": p["fullName"],
        "team": teams_data.get(p.get("currentTeam", {}).get("id"), "Free Agent")
    } for p in results[:10]])


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
            "game_id": g.get("game_id"),
        })

    live = None
    for g in schedule:
        if g["status"] == "In Progress":
            live = {"away": g["away_name"], "home": g["home_name"], "away_score": g.get("away_score", 0), "home_score": g.get("home_score", 0), "inning": g.get("current_inning", ""), "inning_state": g.get("inning_state", ""), "game_id": g.get("game_id")}
            break

    return jsonify({"record": record, "recent": recent, "live": live})


@app.route("/api/player/<int:player_id>")
def player_stats(player_id):
    info = statsapi.player_stat_data(player_id, type="season")
    stats = {}
    group = ""
    for sg in info.get("stats", []):
        if sg["group"] == "hitting":
            stats = sg.get("stats", {})
            group = "hitting"
            break
        elif sg["group"] == "pitching":
            stats = sg.get("stats", {})
            group = "pitching"
            break

    # Recent game log
    recent_games = []
    notables = []
    try:
        game_log = statsapi.player_stat_data(player_id, type="gameLog")
        if game_log.get("stats"):
            gl_stats = game_log["stats"][0].get("stats", {})
            # The gameLog type returns the most recent game stats
            if gl_stats:
                recent_games.append({"type": "latest", "stats": gl_stats})
    except Exception:
        pass

    # Get recent games from schedule for context
    try:
        if info.get("current_team"):
            teams = statsapi.lookup_team(info["current_team"])
            if teams:
                team_id = teams[0]["id"]
                schedule = statsapi.schedule(team=team_id)
                final = [g for g in schedule if g["status"] == "Final"]
                for g in final[-5:]:
                    home = g.get("home_id") == team_id
                    recent_games.append({
                        "date": g["game_date"],
                        "opponent": g["away_name"] if home else g["home_name"],
                        "score": f"{g.get('home_score',0)}-{g.get('away_score',0)}" if home else f"{g.get('away_score',0)}-{g.get('home_score',0)}",
                        "won": (home and g.get("home_score",0) > g.get("away_score",0)) or (not home and g.get("away_score",0) > g.get("home_score",0)),
                    })
    except Exception:
        pass

    # Anomaly check with historical record comparisons
    t = get_thresholds()
    anomalies = []
    comparisons = []  # Historical records to compare against
    games = int(stats.get("gamesPlayed", 0))

    # Historical single-season records
    RECORDS = {
        "hr": {"record": 73, "holder": "Barry Bonds (2001)", "notable": [
            {"val": 62, "holder": "Aaron Judge (2022)"},
            {"val": 61, "holder": "Roger Maris (1961)"},
        ]},
        "avg": {"record": 0.406, "holder": "Ted Williams (1941)", "notable": [
            {"val": 0.394, "holder": "Tony Gwynn (1994)"},
            {"val": 0.390, "holder": "George Brett (1980)"},
        ]},
        "hits": {"record": 262, "holder": "Ichiro Suzuki (2004)", "notable": [
            {"val": 257, "holder": "George Sisler (1920)"},
        ]},
        "rbi": {"record": 191, "holder": "Hack Wilson (1930)", "notable": [
            {"val": 165, "holder": "Manny Ramirez (1999)"},
        ]},
        "sb": {"record": 130, "holder": "Rickey Henderson (1982)", "notable": [
            {"val": 110, "holder": "Vince Coleman (1985)"},
        ]},
        "era": {"record": 1.12, "holder": "Bob Gibson (1968)", "notable": [
            {"val": 1.56, "holder": "Dwight Gooden (1985)"},
            {"val": 1.74, "holder": "Pedro Martinez (2000)"},
        ]},
        "k_season": {"record": 383, "holder": "Nolan Ryan (1973)", "notable": [
            {"val": 372, "holder": "Sandy Koufax (1965)"},
        ]},
        "wins": {"record": 27, "holder": "Steve Carlton (1972)", "notable": [
            {"val": 24, "holder": "Justin Verlander (2011)"},
        ]},
    }

    if games > 20 and group == "hitting":
        bat_season = t.get("batting_season", {})
        avg = float(stats.get("avg", "0"))
        hr = int(stats.get("homeRuns", 0))
        hr_pace = (hr / games) * 162
        hits_pace = (int(stats.get("hits", 0)) / games) * 162
        rbi_pace = (int(stats.get("rbi", 0)) / games) * 162
        sb_pace = (int(stats.get("stolenBases", 0)) / games) * 162

        if avg >= bat_season.get("avg_alltime", 0.37):
            nugget = "No one has finished above .400 since Ted Williams in 1941" if avg >= 0.400 else f"Last player to finish above .{int(avg*1000)}: Tony Gwynn (.394 in 1994)"
            anomalies.append({"msg": f"Batting .{int(avg*1000)} — ALL-TIME TERRITORY", "level": "alltime", "nugget": nugget})
            comparisons.append({"stat": "AVG", "current": f".{int(avg*1000)}", "record": f".406", "holder": RECORDS["avg"]["holder"], "pct": round(avg / 0.406 * 100)})
        elif avg >= bat_season.get("avg_anomalous", 0.33):
            nugget = "Only 5 players have hit .340+ in a season since 2000"
            anomalies.append({"msg": f"Batting .{int(avg*1000)} — elite", "level": "alert", "nugget": nugget})
            comparisons.append({"stat": "AVG", "current": f".{int(avg*1000)}", "record": ".406", "holder": RECORDS["avg"]["holder"], "pct": round(avg / 0.406 * 100)})

        if hr_pace >= bat_season.get("hr_pace_alltime", 52):
            if hr_pace >= 62:
                nugget = f"Would surpass Aaron Judge's 62 (2022) — only Bonds (73), McGwire (70, 65), and Sosa (66, 64, 63) have hit more"
            else:
                nugget = f"Only 7 players in MLB history have hit 55+ in a season"
            anomalies.append({"msg": f"On pace for {int(hr_pace)} HRs — RECORD PACE", "level": "alltime", "nugget": nugget})
            comparisons.append({"stat": "HR Pace", "current": str(int(hr_pace)), "record": "73", "holder": RECORDS["hr"]["holder"], "pct": round(hr_pace / 73 * 100)})
            for n in RECORDS["hr"]["notable"]:
                comparisons.append({"stat": "", "current": "", "record": str(n["val"]), "holder": n["holder"], "pct": round(hr_pace / n["val"] * 100)})
        elif hr_pace >= bat_season.get("hr_pace_anomalous", 39):
            nugget = f"A 40+ HR season has only happened {'{'}~30 times since 2010{'}'}"
            anomalies.append({"msg": f"On pace for {int(hr_pace)} HRs", "level": "alert", "nugget": nugget})
            comparisons.append({"stat": "HR Pace", "current": str(int(hr_pace)), "record": "73", "holder": RECORDS["hr"]["holder"], "pct": round(hr_pace / 73 * 100)})

        if rbi_pace >= 130:
            if rbi_pace >= 160:
                nugget = "Hasn't been done since Manny Ramirez drove in 165 in 1999"
            else:
                nugget = "Last 140+ RBI season: Albert Pujols (2006)"
            anomalies.append({"msg": f"On pace for {int(rbi_pace)} RBI", "level": "alert", "nugget": nugget})
            comparisons.append({"stat": "RBI Pace", "current": str(int(rbi_pace)), "record": "191", "holder": RECORDS["rbi"]["holder"], "pct": round(rbi_pace / 191 * 100)})

        if hits_pace >= 220:
            comparisons.append({"stat": "Hits Pace", "current": str(int(hits_pace)), "record": "262", "holder": RECORDS["hits"]["holder"], "pct": round(hits_pace / 262 * 100)})
            if hits_pace >= 240:
                anomalies.append({"msg": f"On pace for {int(hits_pace)} hits — approaching Ichiro territory", "level": "alltime", "nugget": "Only Ichiro (262 in 2004) and George Sisler (257 in 1920) have reached 240+"})

        if sb_pace >= 50:
            comparisons.append({"stat": "SB Pace", "current": str(int(sb_pace)), "record": "130", "holder": RECORDS["sb"]["holder"], "pct": round(sb_pace / 130 * 100)})
            if sb_pace >= 80:
                anomalies.append({"msg": f"On pace for {int(sb_pace)} SB — historic speed", "level": "alltime", "nugget": "Only Rickey Henderson (130, 108) and Vince Coleman (110, 107, 109) have stolen 80+ in a season"})
            elif sb_pace >= 50:
                anomalies.append({"msg": f"On pace for {int(sb_pace)} SB", "level": "alert", "nugget": "The stolen base leader has averaged ~45 since 2015"})

        # OPS anomaly
        ops = float(stats.get("ops", "0") or "0")
        if ops >= 1.100:
            anomalies.append({"msg": f"{ops:.3f} OPS — ALL-TIME TERRITORY", "level": "alltime", "nugget": "Only Bonds, Ruth, Williams, and Gehrig have posted a full-season OPS above 1.100"})
        elif ops >= 1.000:
            anomalies.append({"msg": f"{ops:.3f} OPS — elite", "level": "alert", "nugget": "Fewer than 5 players per season typically finish above 1.000 OPS"})

    elif games > 5 and group == "pitching":
        pitch_season = t.get("pitching_season", {})
        era = float(stats.get("era", "99"))
        k = int(stats.get("strikeOuts", 0))
        k_pace = (k / games) * 162 if games else 0
        w = int(stats.get("wins", 0))
        w_pace = (w / games) * 162 if games else 0

        if era <= pitch_season.get("era_alltime", 1.8):
            nugget = "Last sub-2.00 ERA season: Jacob deGrom (1.70 in 2018). Last sub-1.50: Dwight Gooden (1.53 in 1985)"
            anomalies.append({"msg": f"{era:.2f} ERA — ALL-TIME TERRITORY", "level": "alltime", "nugget": nugget})
            comparisons.append({"stat": "ERA", "current": f"{era:.2f}", "record": "1.12", "holder": RECORDS["era"]["holder"], "pct": round((1 - era/4.50) / (1 - 1.12/4.50) * 100)})
            for n in RECORDS["era"]["notable"]:
                comparisons.append({"stat": "", "current": "", "record": f"{n['val']:.2f}", "holder": n["holder"], "pct": 0})
        elif era <= pitch_season.get("era_anomalous", 2.5):
            anomalies.append({"msg": f"{era:.2f} ERA — elite", "level": "alert", "nugget": "Typically only 2-3 qualified starters finish below 2.50 each season"})
            comparisons.append({"stat": "ERA", "current": f"{era:.2f}", "record": "1.12", "holder": RECORDS["era"]["holder"], "pct": round((1 - era/4.50) / (1 - 1.12/4.50) * 100)})

        if k_pace >= 250:
            comparisons.append({"stat": "K Pace", "current": str(int(k_pace)), "record": "383", "holder": RECORDS["k_season"]["holder"], "pct": round(k_pace / 383 * 100)})
            if k_pace >= 300:
                anomalies.append({"msg": f"On pace for {int(k_pace)} K — historic strikeout rate", "level": "alltime", "nugget": "Only Nolan Ryan (383), Sandy Koufax (382), and Randy Johnson (372) have reached 300+ K in a season"})
            else:
                anomalies.append({"msg": f"On pace for {int(k_pace)} K", "level": "alert", "nugget": "A 250+ K season is an ace-level achievement — happens ~5 times per year"})

        # WHIP check
        whip = float(stats.get("whip", "99") or "99")
        if whip <= 0.85 and games > 8:
            anomalies.append({"msg": f"{whip:.2f} WHIP — ALL-TIME TERRITORY", "level": "alltime", "nugget": "The lowest full-season WHIP ever: Pedro Martinez (0.737 in 2000)"})
        elif whip <= 1.00 and games > 8:
            anomalies.append({"msg": f"{whip:.2f} WHIP — elite", "level": "alert", "nugget": "Sub-1.00 WHIP is historically rare — only ~20 qualified seasons ever"})

        # K/9 check
        k9 = float(stats.get("strikeoutsPer9Inn", "0") or "0")
        if k9 >= 13.0:
            anomalies.append({"msg": f"{k9:.1f} K/9 — historic dominance", "level": "alltime", "nugget": "The single-season K/9 record: Shane Bieber (14.2 in 2020, 60-game season). Full season: Gerrit Cole (13.8 in 2019)"})
        elif k9 >= 11.0:
            anomalies.append({"msg": f"{k9:.1f} K/9 — elite", "level": "alert", "nugget": "11+ K/9 puts you in the top 1% of all starting pitchers historically"})

        # Win pace
        if w_pace >= 22 and games > 10:
            anomalies.append({"msg": f"On pace for {int(w_pace)} wins", "level": "alert", "nugget": "Last 20+ win season: Justin Verlander (21 in 2011). Hasn't been common since the 1990s"})
            comparisons.append({"stat": "Win Pace", "current": str(int(w_pace)), "record": "27", "holder": RECORDS["wins"]["holder"], "pct": round(w_pace / 27 * 100)})

    return jsonify({
        "name": info.get("first_name", "") + " " + info.get("last_name", ""),
        "position": info.get("position", ""),
        "team": info.get("current_team", ""),
        "stats": stats,
        "anomalies": anomalies,
        "comparisons": comparisons,
        "recent_games": recent_games[1:] if len(recent_games) > 1 else [],
        "last_game": recent_games[0].get("stats", {}) if recent_games and recent_games[0].get("type") == "latest" else {},
    })


@app.route("/api/player/<int:player_id>/career")
def player_career(player_id):
    """Get career stats for a player."""
    info = statsapi.player_stat_data(player_id, type="career")
    stats = {}
    for sg in info.get("stats", []):
        if sg["group"] in ("hitting", "pitching"):
            stats = sg.get("stats", {})
            break
    return jsonify({
        "name": info.get("first_name", "") + " " + info.get("last_name", ""),
        "position": info.get("position", ""),
        "stats": stats,
    })


@app.route("/api/player/<int:player_id>/yearByYear")
def player_year_by_year(player_id):
    """Get year-by-year historical stats."""
    info = statsapi.player_stat_data(player_id, type="yearByYear")
    seasons = []
    for sg in info.get("stats", []):
        if sg["group"] in ("hitting", "pitching"):
            s = sg.get("stats", {})
            if s:
                s["season"] = sg.get("season", "")
                seasons.append(s)
    return jsonify({
        "name": info.get("first_name", "") + " " + info.get("last_name", ""),
        "position": info.get("position", ""),
        "team": info.get("current_team", ""),
        "seasons": seasons,
    })


@app.route("/api/player/<int:player_id>/live")
def player_live(player_id):
    """Get player's current live game stats."""
    info = statsapi.player_stat_data(player_id, type="season")
    name = info.get("first_name", "") + " " + info.get("last_name", "")
    position = info.get("position", "")
    team_name = info.get("current_team", "")

    result = {"name": name, "position": position, "team": team_name, "playing": False, "game": None, "player_stats": {}, "next_game": ""}

    try:
        teams = statsapi.lookup_team(team_name)
        if not teams:
            return jsonify(result)
        team_id = teams[0]["id"]
        schedule = statsapi.schedule(team=team_id)

        # Find live game
        live_game = None
        for g in schedule:
            if g["status"] == "In Progress":
                live_game = g
                break

        if not live_game:
            # Find next upcoming
            upcoming = [g for g in schedule if g["status"] not in ("Final", "In Progress")]
            if upcoming:
                result["next_game"] = f"Next: {upcoming[0]['away_name']} @ {upcoming[0]['home_name']} — {upcoming[0]['game_date']}"
            return jsonify(result)

        result["playing"] = True
        result["game"] = {
            "game_id": live_game["game_id"],
            "away": live_game["away_name"],
            "home": live_game["home_name"],
            "away_score": live_game.get("away_score", 0),
            "home_score": live_game.get("home_score", 0),
            "inning": live_game.get("current_inning", ""),
            "inning_state": live_game.get("inning_state", ""),
        }

        # Get player's game stats from boxscore
        try:
            box = statsapi.boxscore_data(live_game["game_id"])
            # Search both teams for the player
            for side in ["away", "home"]:
                batters = box.get(side + "Batters", [])
                for batter_id in batters:
                    if batter_id == player_id:
                        player_box = box.get(side + "BattingTotals", {}) if batter_id == "totals" else None
                        # Get individual batter stats
                        batter_data = box.get(side + "Batters", {})
                        break
                pitchers = box.get(side + "Pitchers", [])
                for pitcher_id in pitchers:
                    if pitcher_id == player_id:
                        break

            # Try gameLog for today's stats
            game_log = statsapi.player_stat_data(player_id, type="gameLog")
            if game_log.get("stats"):
                gl = game_log["stats"][0].get("stats", {})
                if gl:
                    result["player_stats"] = gl
        except Exception:
            pass

    except Exception:
        pass

    return jsonify(result)


@app.route("/api/player/<int:player_id>/statcast")
def player_statcast(player_id):
    """Get Statcast advanced metrics via pybaseball."""
    try:
        from pybaseball import statcast_batter, statcast_pitcher, playerid_reverse_lookup
        import pandas as pd

        # Lookup the player's MLB key to get their MLBAM ID (same as player_id)
        # statcast uses the same MLB ID
        from datetime import timedelta
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")

        # Determine if batter or pitcher
        info = statsapi.player_stat_data(player_id, type="season")
        position = info.get("position", "")

        if position == "P":
            df = statcast_pitcher(start, end, player_id)
        else:
            df = statcast_batter(start, end, player_id)

        if df is None or df.empty:
            return jsonify({"metrics": {}, "available": False})

        metrics = {}
        if position != "P":
            # Batter Statcast metrics
            batted = df[df["launch_speed"].notna()]
            if not batted.empty:
                metrics["avg_exit_velo"] = round(batted["launch_speed"].mean(), 1)
                metrics["max_exit_velo"] = round(batted["launch_speed"].max(), 1)
                metrics["avg_launch_angle"] = round(batted["launch_angle"].mean(), 1)
                metrics["barrel_pct"] = round((batted["launch_speed_angle"].eq(6).sum() / len(batted)) * 100, 1) if "launch_speed_angle" in batted.columns else None
                metrics["hard_hit_pct"] = round((batted["launch_speed"] >= 95).sum() / len(batted) * 100, 1)
            if "bat_speed" in df.columns:
                bat_speed = df["bat_speed"].dropna()
                if not bat_speed.empty:
                    metrics["avg_bat_speed"] = round(bat_speed.mean(), 1)
                    metrics["max_bat_speed"] = round(bat_speed.max(), 1)
            if "sprint_speed" in df.columns:
                sprint = df["sprint_speed"].dropna()
                if not sprint.empty:
                    metrics["sprint_speed"] = round(sprint.mean(), 1)
            # xBA, xSLG if available
            if "estimated_ba_using_speedangle" in df.columns:
                xba = df["estimated_ba_using_speedangle"].dropna()
                if not xba.empty:
                    metrics["xBA"] = round(xba.mean(), 3)
            if "estimated_slg_using_speedangle" in df.columns:
                xslg = df["estimated_slg_using_speedangle"].dropna()
                if not xslg.empty:
                    metrics["xSLG"] = round(xslg.mean(), 3)
            metrics["total_batted_balls"] = len(batted)
        else:
            # Pitcher Statcast metrics
            if "release_speed" in df.columns:
                velo = df["release_speed"].dropna()
                if not velo.empty:
                    metrics["avg_velo"] = round(velo.mean(), 1)
                    metrics["max_velo"] = round(velo.max(), 1)
            if "release_spin_rate" in df.columns:
                spin = df["release_spin_rate"].dropna()
                if not spin.empty:
                    metrics["avg_spin_rate"] = int(spin.mean())
            batted = df[df["launch_speed"].notna()]
            if not batted.empty:
                metrics["avg_exit_velo_against"] = round(batted["launch_speed"].mean(), 1)
                metrics["hard_hit_pct_against"] = round((batted["launch_speed"] >= 95).sum() / len(batted) * 100, 1)
            if "estimated_ba_using_speedangle" in df.columns:
                xba = df["estimated_ba_using_speedangle"].dropna()
                if not xba.empty:
                    metrics["xBA_against"] = round(xba.mean(), 3)
            # Pitch mix
            if "pitch_type" in df.columns:
                mix = df["pitch_type"].value_counts(normalize=True).head(5).to_dict()
                metrics["pitch_mix"] = {k: round(v * 100, 1) for k, v in mix.items()}
            metrics["total_pitches"] = len(df)

        return jsonify({"metrics": metrics, "available": True})
    except Exception as e:
        return jsonify({"metrics": {}, "available": False, "error": str(e)})


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
