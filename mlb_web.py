"""MLB Favorites Dashboard - Flask Web App (mobile-friendly)."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

import statsapi
from flask import Flask, render_template, jsonify, request

from mlb_notifications import NotificationChecker
from mlb_thresholds import get_thresholds
from mlb_comparisons import get_season_comparisons

# Simple TTL cache for API responses
_cache = {}
_cache_lock = Lock()

def _cached(key, fn, ttl_seconds=30):
    """Return cached result if fresh, otherwise call fn and cache it."""
    now = datetime.now()
    with _cache_lock:
        if key in _cache:
            val, ts = _cache[key]
            if (now - ts).total_seconds() < ttl_seconds:
                return val
    result = fn()
    with _cache_lock:
        _cache[key] = (result, now)
    return result

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))

FAVORITES_FILE = Path(__file__).parent / "mlb_favorites.json"
LAST_RUN_FILE = Path(__file__).parent / "mlb_last_run.json"

# All 30 MLB team IDs
ALL_TEAM_IDS = [108,109,110,111,112,113,114,115,116,117,118,119,120,121,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,158]

def _build_team_rotation_global(team_id):
    """Fetch season-long starter history for a team. Cached 6hrs."""
    def _fetch():
        today = datetime.now()
        start = f"03/20/{today.year}"
        end = today.strftime("%m/%d/%Y")
        sched = statsapi.schedule(team=team_id, start_date=start, end_date=end)
        finals = sorted([x for x in sched if x["status"] == "Final"], key=lambda x: x["game_date"])
        starter_history = []
        for fg in finals:
            try:
                gd = statsapi.get("game", {"gamePk": fg["game_id"]})
                side = "home" if fg.get("home_id") == team_id else "away"
                box = gd["liveData"]["boxscore"]["teams"][side]
                pitchers = box.get("pitchers", [])
                if pitchers:
                    pid = pitchers[0]
                    pdata = box.get("players", {}).get(f"ID{pid}", {})
                    name = pdata.get("person", {}).get("fullName", "")
                    if name:
                        starter_history.append(name)
            except Exception:
                continue
        return starter_history
    return _cached(f"rotation_{team_id}", _fetch, ttl_seconds=21600)

def _warm_rotation_cache():
    """Background task: pre-cache rotation data for all 30 teams, repeat every 6hrs."""
    import time
    time.sleep(5)  # let the app finish starting
    while True:
        for tid in ALL_TEAM_IDS:
            try:
                _build_team_rotation_global(tid)
            except Exception:
                pass
        time.sleep(21600)  # sleep 6 hours then refresh

# Start background cache warming on app load
import threading
threading.Thread(target=_warm_rotation_cache, daemon=True).start()


def _get_player_rankings(player_name, group, team_id=None):
    """Find a player's current MLB/league rankings across key stats."""
    # AL teams by ID
    AL_TEAMS = {133,134,136,137,138,139,140,141,142,143,144,145,147,158,110}
    NL_TEAMS = {109,112,113,114,115,116,117,118,119,120,121,135,143,146,158}
    league_id = 103 if team_id in AL_TEAMS else 104 if team_id in NL_TEAMS else None
    league_label = "AL" if league_id == 103 else "NL" if league_id == 104 else "MLB"
    last_name = player_name.split()[-1]

    rankings = []
    if group == "hitting":
        cats = [("homeRuns", "HR"), ("battingAverage", "AVG"), ("onBasePlusSlugging", "OPS"),
                ("stolenBases", "SB"), ("rbi", "RBI"), ("runs", "R")]
    else:
        cats = [("earnedRunAverage", "ERA"), ("strikeouts", "K"),
                ("wins", "W"), ("walksAndHitsPerInningPitched", "WHIP")]
    try:
        for cat, label in cats:
            r = statsapi.league_leaders(cat, season=datetime.now().year, limit=30,
                                        statGroup=group, leagueId=league_id)
            if not r:
                continue
            for line in r.strip().split('\n'):
                if last_name in line and line.strip() and not line.startswith('Rank'):
                    parts = line.strip().split()
                    try:
                        rank = int(parts[0])
                    except ValueError:
                        continue
                    val = parts[-1]
                    if rank <= 15:
                        rankings.append({"stat": label, "rank": rank, "value": val, "league": league_label})
                    break
        # Also check MLB-wide #1 for crown
        for cat, label in cats:
            r = statsapi.league_leaders(cat, season=datetime.now().year, limit=1, statGroup=group)
            if not r:
                continue
            for line in r.strip().split('\n'):
                if last_name in line and line.strip() and not line.startswith('Rank'):
                    # This player leads all of MLB
                    existing = next((x for x in rankings if x['stat'] == label), None)
                    if existing:
                        existing['mlb_leader'] = True
                    else:
                        parts = line.strip().split()
                        val = parts[-1]
                        rankings.append({"stat": label, "rank": 1, "value": val, "league": "MLB", "mlb_leader": True})
                    break
    except Exception:
        pass
    return sorted(rankings, key=lambda x: x["rank"])


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
    # Try exact lookup first
    results = statsapi.lookup_player(q)
    if results:
        teams_data = {t["id"]: t["name"] for t in _cached("all_teams", lambda: statsapi.get("teams", {"sportIds": 1})["teams"], ttl_seconds=86400)}
        return jsonify([{
            "id": p["id"],
            "name": p["fullName"],
            "team": teams_data.get(p.get("currentTeam", {}).get("id"), "Free Agent")
        } for p in results[:10]])
    # Fuzzy fallback using pybaseball
    from pybaseball import playerid_lookup
    parts = q.strip().split(maxsplit=1)
    last = parts[-1]
    first = parts[0] if len(parts) > 1 else None
    try:
        df = playerid_lookup(last, first, fuzzy=True)
        if df.empty:
            return jsonify([])
        matches = []
        for _, row in df.head(10).iterrows():
            mlbam = int(row["key_mlbam"]) if row.get("key_mlbam") else None
            if not mlbam:
                continue
            name = f"{row['name_first'].title()} {row['name_last'].title()}"
            # Try to get current team from statsapi
            team = "Free Agent"
            try:
                info = statsapi.lookup_player(str(mlbam))
                if info:
                    tid = info[0].get("currentTeam", {}).get("id")
                    if tid:
                        team = _cached("all_teams", lambda: statsapi.get("teams", {"sportIds": 1})["teams"], ttl_seconds=86400)
                        team = next((t["name"] for t in team if t["id"] == tid), "Free Agent")
            except Exception:
                pass
            matches.append({"id": mlbam, "name": name, "team": team})
        return jsonify(matches)
    except Exception:
        return jsonify([])


@app.route("/api/search/team")
def search_team():
    q = request.args.get("q", "")
    if not q:
        return jsonify([])
    results = statsapi.lookup_team(q)
    if results:
        return jsonify([{"id": t["id"], "name": t["name"]} for t in results[:10]])
    # Fuzzy fallback — match against all MLB teams
    from difflib import get_close_matches
    all_teams = _cached("all_teams", lambda: statsapi.get("teams", {"sportIds": 1})["teams"], ttl_seconds=86400)
    names = {t["name"]: t for t in all_teams}
    # Also index by abbreviation and short name
    for t in all_teams:
        names[t.get("abbreviation", "")] = t
        names[t.get("shortName", "")] = t
        names[t.get("teamName", "")] = t
    matches = get_close_matches(q, names.keys(), n=5, cutoff=0.4)
    seen = set()
    out = []
    for m in matches:
        t = names[m]
        if t["id"] not in seen:
            seen.add(t["id"])
            out.append({"id": t["id"], "name": t["name"]})
    return jsonify(out)


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


@app.route("/api/league-averages")
def league_averages():
    """Get current season league averages for stat grading."""
    def _fetch():
        import requests as req
        r = req.get("https://statsapi.mlb.com/api/v1/teams/stats?season=2026&sportIds=1&group=hitting&stats=season&gameType=R", timeout=5).json()
        splits = r["stats"][0]["splits"]
        n = len(splits)
        gp = sum(int(s["stat"].get("gamesPlayed", 0)) for s in splits) / n
        r2 = req.get("https://statsapi.mlb.com/api/v1/teams/stats?season=2026&sportIds=1&group=pitching&stats=season&gameType=R", timeout=5).json()
        psplits = r2["stats"][0]["splits"]
        return {
            "games_per_team": round(gp),
            "avg": round(sum(float(s["stat"].get("avg", "0")) for s in splits) / n, 3),
            "obp": round(sum(float(s["stat"].get("obp", "0")) for s in splits) / n, 3),
            "slg": round(sum(float(s["stat"].get("slg", "0")) for s in splits) / n, 3),
            "ops": round(sum(float(s["stat"].get("ops", "0")) for s in splits) / n, 3),
            "hr_per_player": round(sum(int(s["stat"].get("homeRuns", 0)) for s in splits) / n / 9, 1),
            "rbi_per_player": round(sum(int(s["stat"].get("rbi", 0)) for s in splits) / n / 9, 1),
            "sb_per_player": round(sum(int(s["stat"].get("stolenBases", 0)) for s in splits) / n / 9, 1),
            "era": round(sum(float(s["stat"].get("era", "0")) for s in psplits) / n, 2),
            "whip": round(sum(float(s["stat"].get("whip", "0")) for s in psplits) / n, 2),
            "k9": round(sum(float(s["stat"].get("strikeoutsPer9Inn", "0")) for s in psplits) / n, 1),
            "bb9": round(sum(float(s["stat"].get("walksPer9Inn", "0")) for s in psplits) / n, 1),
        }
    try:
        data = _cached("league_averages", _fetch, ttl_seconds=3600)
        return jsonify(data)
    except Exception:
        return jsonify({"avg": .245, "obp": .320, "slg": .400, "ops": .720, "era": 4.10, "whip": 1.30, "k9": 8.5, "hr_per_player": 5, "rbi_per_player": 19, "sb_per_player": 3, "games_per_team": 40})


@app.route("/api/live/demo")
def live_games_demo():
    """Demo endpoint to preview live game cards."""
    return jsonify({
        "live": [
            {"away": "Baltimore Orioles", "home": "New York Yankees", "away_id": 110, "home_id": 147,
             "away_score": 4, "home_score": 3, "status": "In Progress", "inning": 7, "inning_state": "Top",
             "fav": True, "game_id": 999001, "game_time": "", "balls": 2, "strikes": 1, "outs": 1},
            {"away": "Los Angeles Dodgers", "home": "San Francisco Giants", "away_id": 119, "home_id": 137,
             "away_score": 1, "home_score": 1, "status": "In Progress", "inning": 3, "inning_state": "Bottom",
             "fav": False, "game_id": 999002, "game_time": "", "balls": 0, "strikes": 2, "outs": 2},
            {"away": "Houston Astros", "home": "Texas Rangers", "away_id": 117, "home_id": 140,
             "away_score": 6, "home_score": 0, "status": "In Progress", "inning": 5, "inning_state": "Top",
             "fav": False, "game_id": 999003, "game_time": "", "balls": 3, "strikes": 0, "outs": 0},
        ],
        "upcoming": [
            {"away": "Chicago Cubs", "home": "St. Louis Cardinals", "away_id": 112, "home_id": 138,
             "away_score": 0, "home_score": 0, "status": "Scheduled", "inning": "", "inning_state": "",
             "fav": False, "game_id": None, "game_time": "2026-05-11T23:10:00Z"},
        ],
        "final": [
            {"away": "Detroit Tigers", "home": "Kansas City Royals", "away_id": 116, "home_id": 118,
             "away_score": 6, "home_score": 3, "status": "Final", "inning": "", "inning_state": "",
             "fav": False, "game_id": 824113, "game_time": ""},
        ],
    })


@app.route("/api/live")
def live_games():
    games = statsapi.schedule()
    fav_ids = {t["id"] for t in load_favorites().get("teams", [])}
    result = {"live": [], "upcoming": [], "final": []}
    for g in games:
        entry = {
            "away": g["away_name"], "home": g["home_name"],
            "away_id": g.get("away_id"), "home_id": g.get("home_id"),
            "away_score": g.get("away_score", 0), "home_score": g.get("home_score", 0),
            "status": g["status"], "inning": g.get("current_inning", ""),
            "inning_state": g.get("inning_state", ""),
            "fav": g.get("home_id") in fav_ids or g.get("away_id") in fav_ids,
            "game_id": g.get("game_id"),
            "game_time": g.get("game_datetime", ""),
        }
        if g["status"] == "In Progress":
            try:
                import requests as req
                ls = req.get(f"https://statsapi.mlb.com/api/v1/game/{g['game_id']}/linescore").json()
                entry["balls"] = ls.get("balls", 0)
                entry["strikes"] = ls.get("strikes", 0)
                entry["outs"] = ls.get("outs", 0)
            except Exception:
                entry["balls"] = entry["strikes"] = entry["outs"] = 0
            result["live"].append(entry)
        elif g["status"] in ("Final", "Game Over", "Completed Early"):
            entry["innings"] = g.get("current_inning", 9)
            result["final"].append(entry)
        else:
            result["upcoming"].append(entry)
    return jsonify(result)


@app.route("/api/upcoming")
def upcoming_games():
    """Get all scheduled games for the next 2 weeks."""
    from datetime import date
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=13)
    games = statsapi.schedule(start_date=start.strftime("%m/%d/%Y"), end_date=end.strftime("%m/%d/%Y"))
    fav_ids = {t["id"] for t in load_favorites().get("teams", [])}
    result = []
    for g in games:
        if g["status"] in ("Final", "In Progress"):
            continue
        result.append({
            "away": g["away_name"], "home": g["home_name"],
            "away_id": g.get("away_id"), "home_id": g.get("home_id"),
            "game_time": g.get("game_datetime", ""),
            "game_date": g.get("game_date", ""),
            "fav": g.get("home_id") in fav_ids or g.get("away_id") in fav_ids,
            "game_id": g.get("game_id"),
        })
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

    upcoming = []
    for g in schedule:
        if g["status"] not in ("Final", "In Progress"):
            home = g.get("home_id") == team_id
            upcoming.append({
                "date": g.get("game_date", ""),
                "game_time": g.get("game_datetime", ""),
                "opponent": g["away_name"] if home else g["home_name"],
                "opponent_id": g.get("away_id") if home else g.get("home_id"),
                "home": home,
            })

    return jsonify({"record": record, "recent": recent, "live": live, "upcoming": upcoming})


@app.route("/api/team/<int:team_id>/roster")
def team_roster(team_id):
    """Get team roster grouped by position, plus lineup if available."""
    data = _cached(f"roster_{team_id}",
                   lambda: statsapi.get("team_roster", {"teamId": team_id}), ttl_seconds=300)
    roster = []
    for p in data.get("roster", []):
        roster.append({
            "id": p["person"]["id"],
            "name": p["person"]["fullName"],
            "pos": p["position"]["abbreviation"],
            "number": p.get("jerseyNumber", ""),
            "type": p["position"]["type"],
        })

    # Try to get lineup from today's game
    lineup = []
    try:
        schedule = _cached(f"team_schedule_{team_id}",
                           lambda: statsapi.schedule(team=team_id), ttl_seconds=120)
        game = None
        for g in schedule:
            if g["status"] in ("In Progress", "Pre-Game", "Warmup", "Scheduled"):
                game = g
                break
        if not game:
            # Use most recent final game for "last lineup"
            finals = [g for g in schedule if g["status"] == "Final"]
            if finals:
                game = finals[-1]
        if game:
            gd = statsapi.get("game", {"gamePk": game["game_id"]})
            home = game.get("home_id") == team_id
            side = "home" if home else "away"
            box = gd.get("liveData", {}).get("boxscore", {}).get("teams", {}).get(side, {})
            order = box.get("battingOrder", [])
            players = box.get("players", {})
            for pid in order:
                pdata = players.get(f"ID{pid}", {})
                person = pdata.get("person", {})
                pos = pdata.get("position", {})
                lineup.append({
                    "id": pid,
                    "name": person.get("fullName", ""),
                    "pos": pos.get("abbreviation", ""),
                })
    except Exception:
        pass

    return jsonify({"roster": roster, "lineup": lineup})


@app.route("/api/player/<int:player_id>")
def player_stats(player_id):
    info = _cached(f"player_season_{player_id}",
                   lambda: statsapi.player_stat_data(player_id, type="season"), ttl_seconds=60)
    stats = {}
    group = ""
    pitching_stats = {}
    is_two_way = info.get("position", "") == "TWP"
    is_pitcher = info.get("position", "") == "P"
    preferred = "pitching" if is_pitcher else "hitting"
    fallback = "hitting" if is_pitcher else "pitching"

    if is_two_way:
        # Get both hitting and pitching stats
        for sg in info.get("stats", []):
            if sg["group"] == "hitting" and sg.get("stats", {}).get("gamesPlayed", 0):
                stats = sg.get("stats", {})
                group = "hitting"
            elif sg["group"] == "pitching" and sg.get("stats", {}).get("gamesPlayed", 0):
                pitching_stats = sg.get("stats", {})
    else:
        for sg in info.get("stats", []):
            if sg["group"] == preferred:
                stats = sg.get("stats", {})
                group = preferred
                break
        if not stats:
            for sg in info.get("stats", []):
                if sg["group"] == fallback:
                    stats = sg.get("stats", {})
                    group = fallback
                    break

    # Fetch game log and schedule in parallel
    recent_games = []
    notables = []

    def _fetch_game_log():
        try:
            return _cached(f"player_gamelog_{player_id}",
                           lambda: statsapi.player_stat_data(player_id, type="gameLog"), ttl_seconds=60)
        except Exception:
            return None

    def _fetch_schedule():
        try:
            if info.get("current_team"):
                teams = statsapi.lookup_team(info["current_team"])
                if teams:
                    team_id = teams[0]["id"]
                    return _cached(f"team_schedule_{team_id}",
                                   lambda: statsapi.schedule(team=team_id), ttl_seconds=120)
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=2) as ex:
        gl_future = ex.submit(_fetch_game_log)
        sched_future = ex.submit(_fetch_schedule)
        game_log = gl_future.result()
        schedule = sched_future.result()

    if game_log and game_log.get("stats"):
        gl_stats = game_log["stats"][0].get("stats", {})
        if gl_stats:
            recent_games.append({"type": "latest", "stats": gl_stats})

    if schedule:
        team_id = None
        if info.get("current_team"):
            teams = _cached(f"lookup_team_{info['current_team']}",
                            lambda: statsapi.lookup_team(info["current_team"]), ttl_seconds=300)
            if teams:
                team_id = teams[0]["id"]
        if team_id:
            final = [g for g in schedule if g["status"] == "Final"]
            for g in final[-5:]:
                home = g.get("home_id") == team_id
                recent_games.append({
                    "date": g["game_date"],
                    "opponent": g["away_name"] if home else g["home_name"],
                    "score": f"{g.get('home_score',0)}-{g.get('away_score',0)}" if home else f"{g.get('away_score',0)}-{g.get('home_score',0)}",
                    "won": (home and g.get("home_score",0) > g.get("away_score",0)) or (not home and g.get("away_score",0) > g.get("home_score",0)),
                })

    # Anomaly check with historical record comparisons
    t = get_thresholds()
    anomalies = []
    comparisons = []  # Historical records to compare against
    games = int(stats.get("gamesPlayed", 0))

    # Dynamic archetype-based comparisons
    anomalies, comparisons = get_season_comparisons(stats, group, games, t)

    # Always generate 2-3 insights regardless of anomaly thresholds
    insights = []
    if games > 5 and group == "hitting":
        hr = int(stats.get("homeRuns", 0))
        hits = int(stats.get("hits", 0))
        rbi = int(stats.get("rbi", 0))
        sb = int(stats.get("stolenBases", 0))
        bb = int(stats.get("baseOnBalls", 0))
        pa = int(stats.get("plateAppearances", 1) or 1)
        avg = float(stats.get("avg", "0") or "0")
        ops = float(stats.get("ops", "0") or "0")
        slg = float(stats.get("slg", "0") or "0")
        obp = float(stats.get("obp", "0") or "0")
        k_rate = int(stats.get("strikeOuts", 0)) / pa * 100
        bb_rate = bb / pa * 100
        hr_pace = (hr / games) * 162
        hr_per_pa = hr / pa if pa else 0
        ab_per_hr = float(stats.get("atBatsPerHomeRun", "0") or "0")

        # Games-played context
        if hr >= 10:
            insights.append({"msg": f"{hr} HR in {games} games ({hr/games:.2f}/game)", "nugget": f"At this rate through {games} games, that's a {int(hr_pace)}-HR season. {'Elite power pace' if hr_pace >= 40 else 'Solid production'}"})
        elif hr_pace >= 20:
            insights.append({"msg": f"HR pace: {int(hr_pace)} over 162 games ({games} G played)", "nugget": f"Averaging a HR every {ab_per_hr:.0f} AB" if ab_per_hr > 0 else ""})

        # Per-PA efficiency
        if hr_per_pa >= 0.05:
            insights.append({"msg": f"HR on {hr_per_pa*100:.1f}% of PA — elite power frequency", "nugget": "The best power hitters typically homer on 4-6% of plate appearances"})

        # OPS context with games played
        if ops >= 0.900:
            insights.append({"msg": f"{ops:.3f} OPS through {games} games — All-Star caliber", "nugget": f"OBP {obp:.3f} + SLG {slg:.3f}. Top-15 in baseball territory"})
        elif ops >= 0.750:
            insights.append({"msg": f"{ops:.3f} OPS ({obp:.3f} OBP + {slg:.3f} SLG)", "nugget": "League average OPS is .710-.720"})
        else:
            insights.append({"msg": f"{ops:.3f} OPS through {games} games", "nugget": f"League average is .710-.720. {'Small sample — could normalize' if games < 25 else 'Sustained slump'}"})

        # K/BB ratio
        k = int(stats.get("strikeOuts", 0))
        if bb > 0:
            k_bb = k / bb
            if k_bb <= 1.5 and pa >= 50:
                insights.append({"msg": f"{k_bb:.1f} K/BB ratio — elite discipline", "nugget": f"{k} K vs {bb} BB in {pa} PA. Only the best plate-discipline hitters stay below 2.0"})
            elif k_bb >= 4.0 and pa >= 50:
                insights.append({"msg": f"{k_bb:.1f} K/BB ratio — aggressive approach", "nugget": f"{k} K vs {bb} BB. Striking out 4x more than walking is swing-heavy"})

        # Speed context
        if sb >= 5:
            cs = int(stats.get("caughtStealing", 0))
            success_rate = sb / (sb + cs) * 100 if (sb + cs) > 0 else 100
            insights.append({"msg": f"{sb} SB in {games} games ({success_rate:.0f}% success)", "nugget": f"{'Elite efficiency' if success_rate >= 85 else 'Aggressive on the bases'} — pace for {int((sb/games)*162)} over a full season"})

        # AVG with games context
        if avg >= .300 and games >= 20:
            insights.append({"msg": f"Batting .{int(avg*1000)} through {games} games", "nugget": "Only ~10-15 qualified hitters finish above .300 each year"})
        elif avg < .220 and games >= 20:
            insights.append({"msg": f"Batting .{int(avg*1000)} through {games} games", "nugget": f"{'Still early — could recover' if games < 40 else 'Extended slump territory'}"})

    elif games > 3 and group == "pitching":
        era = float(stats.get("era", "99") or "99")
        k = int(stats.get("strikeOuts", 0))
        k9 = float(stats.get("strikeoutsPer9Inn", "0") or "0")
        whip = float(stats.get("whip", "99") or "99")
        bb9 = float(stats.get("walksPer9Inn", "0") or "0")
        ip = float(stats.get("inningsPitched", "0") or "0")
        gs = int(stats.get("gamesStarted", 0))
        w = int(stats.get("wins", 0))
        l = int(stats.get("losses", 0))

        # IP/start context
        if gs > 0:
            ip_per_start = ip / gs
            insights.append({"msg": f"{era:.2f} ERA over {ip:.0f} IP ({gs} starts, {ip_per_start:.1f} IP/start)", "nugget": f"{'Deep into games — workhorse' if ip_per_start >= 6.0 else 'Moderate workload'} — league avg is ~5.3 IP/start"})
        else:
            insights.append({"msg": f"{era:.2f} ERA over {ip:.0f} IP in {games} appearances", "nugget": "League average ERA is around 4.00-4.20"})

        # K per game context
        if gs > 0 and k > 0:
            k_per_start = k / gs
            insights.append({"msg": f"{k} K in {gs} starts ({k_per_start:.1f} K/start)", "nugget": f"{'Dominant strikeout stuff' if k_per_start >= 8 else 'Solid' if k_per_start >= 6 else 'Contact-oriented'} — {k9:.1f} K/9 rate"})

        # WHIP with context
        if whip <= 1.20:
            insights.append({"msg": f"{whip:.2f} WHIP through {games} games", "nugget": f"{'Elite traffic control' if whip <= 1.0 else 'Above average'} — allowing {whip*9:.1f} baserunners per 9 IP"})
        elif whip >= 1.40:
            insights.append({"msg": f"{whip:.2f} WHIP — {whip*9:.1f} baserunners per 9 IP", "nugget": "League average WHIP is ~1.30. Above 1.40 means constant pressure"})

        # W-L with context
        if (w + l) >= 3:
            insights.append({"msg": f"{w}-{l} record, {era:.2f} ERA in {ip:.0f} IP", "nugget": "Wins don't always reflect performance" if era <= 3.50 and w < l else ""})

    # Take top 4 insights (prefer ones not already covered by anomalies)
    anomaly_msgs = {a["msg"] for a in anomalies}
    insights = [i for i in insights if i["msg"] not in anomaly_msgs][:4]

    # Bad stat anomalies — severity scaled by sample size
    red_flags = []
    if games > 15 and group == "hitting":
        avg = float(stats.get("avg", "0") or "0")
        ops = float(stats.get("ops", "0") or "0")
        k_rate = int(stats.get("strikeOuts", 0)) / max(int(stats.get("plateAppearances", 1) or 1), 1) * 100
        hr = int(stats.get("homeRuns", 0))
        hr_pace = (hr / games) * 162
        early = games < 30
        mid = 30 <= games < 60

        if avg <= .180:
            if early:
                red_flags.append({"msg": f"Batting .{int(avg*1000)} through {games} games — ugly start", "level": "bad", "nugget": "Still early. Eugenio Suarez hit .168 through April 2022 and finished .236. Plenty of time to recover"})
            elif mid:
                red_flags.append({"msg": f"Batting .{int(avg*1000)} through {games} games — growing concern", "level": "terrible", "nugget": "Getting harder to recover. Chris Davis hit .168 for a full season in 2018 — the worst ever by a qualifier"})
            else:
                red_flags.append({"msg": f"Batting .{int(avg*1000)} through {games} games — historically bad", "level": "terrible", "nugget": "At this point, this is who they are this year. Chris Davis (.168 in 2018) and Rob Deer (.179 in 1991) are the only comparables"})
        elif avg <= .200:
            if early:
                red_flags.append({"msg": f"Batting .{int(avg*1000)} through {games} games — slow start", "level": "caution", "nugget": "Mendoza Line territory, but many hitters recover from sub-.200 Aprils. Joey Gallo hit .160 in April 2021 and finished .199 with 38 HR"})
            elif mid:
                red_flags.append({"msg": f"Batting .{int(avg*1000)} through {games} games — Mendoza Line", "level": "bad", "nugget": "Named after Mario Mendoza (.200). Recovery is possible but requires a sustained hot streak"})
            else:
                red_flags.append({"msg": f"Batting .{int(avg*1000)} through {games} games — below the Mendoza Line", "level": "terrible", "nugget": "Sub-.200 over 60+ games is replacement-level. Very few players recover to league average from here"})
        elif avg <= .220 and games >= 30:
            if mid:
                red_flags.append({"msg": f"Batting .{int(avg*1000)} through {games} games — below average", "level": "caution", "nugget": "MLB average is .245-.250. A hot 2-week stretch could bring this up 20+ points"})
            else:
                red_flags.append({"msg": f"Batting .{int(avg*1000)} through {games} games — well below average", "level": "bad", "nugget": "Sub-.220 over 60+ games is typically a career-worst season"})

        if ops <= .550:
            if early:
                red_flags.append({"msg": f"{ops:.3f} OPS through {games} games — ice cold", "level": "bad", "nugget": "Extremely low but small sample. A couple multi-hit games can move OPS significantly early on"})
            elif mid:
                red_flags.append({"msg": f"{ops:.3f} OPS through {games} games — replacement level", "level": "terrible", "nugget": "Sub-.600 OPS over 30+ games is minor-league caliber production"})
            else:
                red_flags.append({"msg": f"{ops:.3f} OPS through {games} games — historically bad", "level": "terrible", "nugget": "Chris Davis posted .539 OPS in 2018. This is bench/DFA territory"})
        elif ops <= .650 and games >= 30:
            if mid:
                red_flags.append({"msg": f"{ops:.3f} OPS through {games} games — below average", "level": "caution", "nugget": "League average OPS is .710-.720. Power surge or hot streak could fix this"})
            else:
                red_flags.append({"msg": f"{ops:.3f} OPS through {games} games — well below average", "level": "bad", "nugget": "Sub-.650 OPS over 60+ games is bottom-10 in baseball"})

        if k_rate >= 35:
            if early:
                red_flags.append({"msg": f"{k_rate:.1f}% K rate through {games} games — lots of swing-and-miss", "level": "caution", "nugget": "High early K rates often stabilize as hitters see more pitches. But 35%+ is extreme even short-term"})
            else:
                red_flags.append({"msg": f"{k_rate:.1f}% K rate through {games} games — extreme", "level": "terrible", "nugget": "Patrick Wisdom (35.8% in 2022) is the full-season record. This is nearly unhittable territory"})
        elif k_rate >= 30 and games > 20:
            if early:
                red_flags.append({"msg": f"{k_rate:.1f}% K rate through {games} games — high", "level": "caution", "nugget": "30%+ K rate is concerning but can come down. League average is 22-23%"})
            else:
                red_flags.append({"msg": f"{k_rate:.1f}% K rate through {games} games — swing-and-miss problem", "level": "bad", "nugget": "Striking out 30%+ makes it very hard to be productive. Only elite power (Judge, Gallo) can offset it"})

        if hr_pace <= 5 and games > 40 and int(stats.get("plateAppearances", 0)) > 200:
            red_flags.append({"msg": f"On pace for {int(hr_pace)} HR through {games} games — no power", "level": "bad", "nugget": "For a full-time player, single-digit HR pace suggests a mechanical issue or decline"})

    elif games > 5 and group == "pitching":
        era = float(stats.get("era", "99") or "99")
        whip = float(stats.get("whip", "99") or "99")
        bb9 = float(stats.get("walksPer9Inn", "0") or "0")
        hr9 = float(stats.get("homeRunsPer9", "0") or "0")
        ip = float(stats.get("inningsPitched", "0") or "0")
        early_p = ip < 30
        mid_p = 30 <= ip < 80

        if era >= 6.00:
            if early_p:
                red_flags.append({"msg": f"{era:.2f} ERA through {ip:.0f} IP — rough start", "level": "caution", "nugget": "ERA is volatile in small samples. One bad outing can inflate it massively. A few clean starts will bring it down fast"})
            elif mid_p:
                red_flags.append({"msg": f"{era:.2f} ERA through {ip:.0f} IP — major concern", "level": "bad", "nugget": "Getting harder to bring down. At 50+ IP, ERA starts to stabilize. Demotion risk if this continues"})
            else:
                red_flags.append({"msg": f"{era:.2f} ERA through {ip:.0f} IP — historically bad", "level": "terrible", "nugget": "A 6.00+ ERA over 80+ IP is demotion/DFA territory. The worst qualified ERA: Les Sweetland (7.71 in 1930)"})
        elif era >= 5.00:
            if early_p:
                red_flags.append({"msg": f"{era:.2f} ERA through {ip:.0f} IP — elevated", "level": "caution", "nugget": "Still early. Many aces have 5.00+ ERAs in April and finish under 3.50. One blowup skews everything"})
            else:
                red_flags.append({"msg": f"{era:.2f} ERA through {ip:.0f} IP — below average", "level": "bad", "nugget": "League average ERA is 4.00-4.20. A 5.00+ ERA over 30+ IP is back-of-rotation or worse"})

        if whip >= 1.60:
            if early_p:
                red_flags.append({"msg": f"{whip:.2f} WHIP through {ip:.0f} IP — too much traffic", "level": "caution", "nugget": "WHIP stabilizes slower than ERA. A few clean outings can drop this significantly"})
            else:
                red_flags.append({"msg": f"{whip:.2f} WHIP through {ip:.0f} IP — too many baserunners", "level": "terrible", "nugget": "Nearly 2 baserunners per inning over 30+ IP is unsustainable for any role"})
        elif whip >= 1.40 and ip >= 20:
            red_flags.append({"msg": f"{whip:.2f} WHIP through {ip:.0f} IP — below average", "level": "caution" if early_p else "bad", "nugget": "League average WHIP is ~1.30. Above 1.40 puts constant pressure on the defense"})

        if bb9 >= 5.0 and ip >= 15:
            if early_p:
                red_flags.append({"msg": f"{bb9:.1f} BB/9 through {ip:.0f} IP — control issues", "level": "caution", "nugget": "Walk rates can be noisy early. But 5+ BB/9 suggests mechanical or confidence issues"})
            else:
                red_flags.append({"msg": f"{bb9:.1f} BB/9 through {ip:.0f} IP — severe control problems", "level": "terrible", "nugget": "Walking 5+ per 9 over 30+ IP is historically bad. Very few pitchers sustain a rotation spot with this"})
        elif bb9 >= 4.0 and ip >= 20:
            red_flags.append({"msg": f"{bb9:.1f} BB/9 through {ip:.0f} IP — poor command", "level": "caution" if early_p else "bad", "nugget": "League average is ~3.2 BB/9. Walking 4+ per 9 makes it hard to pitch deep into games"})

        if hr9 >= 2.0 and ip >= 20:
            if early_p:
                red_flags.append({"msg": f"{hr9:.1f} HR/9 through {ip:.0f} IP — home run prone", "level": "caution", "nugget": "HR/9 is the most volatile pitching stat early on. A couple solo shots in short outings inflate this"})
            else:
                red_flags.append({"msg": f"{hr9:.1f} HR/9 through {ip:.0f} IP — giving up too many long balls", "level": "terrible", "nugget": "2+ HR/9 over 30+ IP is extreme. The worst qualified HR/9 seasons are around 2.1"})
        elif hr9 >= 1.5 and ip >= 30:
            red_flags.append({"msg": f"{hr9:.1f} HR/9 through {ip:.0f} IP — elevated HR rate", "level": "bad", "nugget": "League average is ~1.2 HR/9. Above 1.5 means the ball is leaving the yard too often"})

    # Get player's league rankings
    player_name = info.get("first_name", "") + " " + info.get("last_name", "")
    team_id_for_rank = None
    try:
        teams = statsapi.lookup_team(info.get("current_team", ""))
        if teams:
            team_id_for_rank = teams[0].get("id")
    except Exception:
        pass
    rankings = _get_player_rankings(player_name, group, team_id_for_rank) if games > 10 else []

    # Sort red flags: least severe first
    _severity = {"caution": 0, "bad": 1, "terrible": 2}
    red_flags.sort(key=lambda x: _severity.get(x["level"], 1))

    return jsonify({
        "name": player_name,
        "position": info.get("position", ""),
        "team": info.get("current_team", ""),
        "stats": stats,
        "pitching_stats": pitching_stats,
        "is_two_way": is_two_way,
        "anomalies": anomalies,
        "red_flags": red_flags,
        "insights": insights,
        "comparisons": comparisons,
        "rankings": rankings,
        "recent_games": recent_games[1:] if len(recent_games) > 1 else [],
        "last_game": recent_games[0].get("stats", {}) if recent_games and recent_games[0].get("type") == "latest" else {},
    })


@app.route("/api/player/<int:player_id>/career")
def player_career(player_id):
    """Get career stats for a player with career-context anomalies."""
    info = _cached(f"player_career_{player_id}",
                   lambda: statsapi.player_stat_data(player_id, type="career"), ttl_seconds=3600)
    stats = {}
    group = ""
    is_pitcher = info.get("position", "") == "P"
    preferred = "pitching" if is_pitcher else "hitting"
    fallback = "hitting" if is_pitcher else "pitching"
    for sg in info.get("stats", []):
        if sg["group"] == preferred:
            stats = sg.get("stats", {})
            group = preferred
            break
    if not stats:
        for sg in info.get("stats", []):
            if sg["group"] == fallback:
                stats = sg.get("stats", {})
                group = fallback
                break

    anomalies = []
    comparisons = []

    # Career all-time records for context
    CAREER_RECORDS = {
        "hr": {"record": 762, "holder": "Barry Bonds", "notable": [
            {"val": 755, "holder": "Hank Aaron"}, {"val": 714, "holder": "Babe Ruth"},
            {"val": 660, "holder": "Willie Mays"}, {"val": 500, "holder": "500 HR Club"},
        ]},
        "hits": {"record": 4256, "holder": "Pete Rose", "notable": [
            {"val": 3771, "holder": "Hank Aaron"}, {"val": 3000, "holder": "3000 Hit Club"},
        ]},
        "rbi": {"record": 2297, "holder": "Hank Aaron", "notable": [
            {"val": 2214, "holder": "Babe Ruth"}, {"val": 1996, "holder": "Cap Anson"},
        ]},
        "sb": {"record": 1406, "holder": "Rickey Henderson", "notable": [
            {"val": 938, "holder": "Lou Brock"}, {"val": 500, "holder": "500 SB Club"},
        ]},
        "avg": {"record": .367, "holder": "Ty Cobb", "notable": [
            {"val": .358, "holder": "Rogers Hornsby"}, {"val": .345, "holder": "Ted Williams"},
        ]},
        "wins": {"record": 511, "holder": "Cy Young", "notable": [
            {"val": 417, "holder": "Walter Johnson"}, {"val": 373, "holder": "Grover Alexander"},
            {"val": 300, "holder": "300 Win Club"},
        ]},
        "k_pitch": {"record": 5714, "holder": "Nolan Ryan", "notable": [
            {"val": 4875, "holder": "Randy Johnson"}, {"val": 3000, "holder": "3000 K Club"},
        ]},
        "era": {"record": 1.82, "holder": "Ed Walsh", "notable": [
            {"val": 2.13, "holder": "Christy Mathewson"}, {"val": 2.17, "holder": "Walter Johnson"},
        ]},
        "shutouts": {"record": 110, "holder": "Walter Johnson", "notable": [
            {"val": 90, "holder": "Grover Alexander"}, {"val": 79, "holder": "Christy Mathewson"},
        ]},
    }

    if group == "hitting":
        hr = int(stats.get("homeRuns", 0))
        hits = int(stats.get("hits", 0))
        rbi = int(stats.get("rbi", 0))
        sb = int(stats.get("stolenBases", 0))
        avg = float(stats.get("avg", "0") or "0")
        ops = float(stats.get("ops", "0") or "0")
        games = int(stats.get("gamesPlayed", 0))

        if hr >= 500:
            anomalies.append({"msg": f"{hr} career HR — 500 HR Club", "level": "alltime", "nugget": "Only 28 players in MLB history have hit 500+ career home runs"})
        elif hr >= 400:
            anomalies.append({"msg": f"{hr} career HR — elite power", "level": "alert", "nugget": "Fewer than 60 players have reached 400 career HR"})
        if hr >= 300:
            comparisons.append({"stat": "Career HR", "current": str(hr), "record": "762", "holder": CAREER_RECORDS["hr"]["holder"], "pct": round(hr / 762 * 100)})

        if hits >= 3000:
            anomalies.append({"msg": f"{hits} career hits — 3000 Hit Club", "level": "alltime", "nugget": "Only 33 players have reached 3,000 career hits"})
        elif hits >= 2500:
            anomalies.append({"msg": f"{hits} career hits — approaching 3000", "level": "alert", "nugget": "3,000 hits is a near-automatic Hall of Fame induction"})
        if hits >= 2000:
            comparisons.append({"stat": "Career Hits", "current": str(hits), "record": "4256", "holder": CAREER_RECORDS["hits"]["holder"], "pct": round(hits / 4256 * 100)})

        if rbi >= 1500:
            anomalies.append({"msg": f"{rbi} career RBI — all-time elite", "level": "alltime", "nugget": "Fewer than 30 players have driven in 1,500+ runs"})
        elif rbi >= 1000:
            anomalies.append({"msg": f"{rbi} career RBI", "level": "alert", "nugget": "1,000 career RBI is a benchmark for sustained run production"})

        if sb >= 500:
            anomalies.append({"msg": f"{sb} career SB — all-time speed", "level": "alltime", "nugget": "Only 15 players have stolen 500+ bases in their career"})
        elif sb >= 300:
            anomalies.append({"msg": f"{sb} career SB — elite baserunner", "level": "alert", "nugget": "300+ career SB puts you among the fastest players ever"})
        if sb >= 200:
            comparisons.append({"stat": "Career SB", "current": str(sb), "record": "1406", "holder": CAREER_RECORDS["sb"]["holder"], "pct": round(sb / 1406 * 100)})

        if avg >= .330 and games >= 500:
            anomalies.append({"msg": f".{int(avg*1000)} career AVG — all-time great", "level": "alltime", "nugget": "Only Ty Cobb (.367), Rogers Hornsby (.358), and Joe Jackson (.356) have career averages above .350"})
        elif avg >= .300 and games >= 500:
            anomalies.append({"msg": f".{int(avg*1000)} career AVG — .300 career hitter", "level": "alert", "nugget": "A .300+ career average is increasingly rare in the modern era"})

        if ops >= 1.000 and games >= 500:
            anomalies.append({"msg": f"{ops:.3f} career OPS — inner circle", "level": "alltime", "nugget": "Only Babe Ruth (1.164), Ted Williams (1.116), and Lou Gehrig (1.080) have career OPS above 1.000"})
        elif ops >= .900 and games >= 500:
            anomalies.append({"msg": f"{ops:.3f} career OPS — Hall of Fame caliber", "level": "alert", "nugget": "A .900+ career OPS is typical of Hall of Fame hitters"})

    elif group == "pitching":
        wins = int(stats.get("wins", 0))
        ks = int(stats.get("strikeOuts", 0))
        era = float(stats.get("era", "99") or "99")
        shutouts = int(stats.get("shutouts", 0))
        ip = float(stats.get("inningsPitched", "0").replace(",", "") or "0")
        whip = float(stats.get("whip", "99") or "99")
        games = int(stats.get("gamesPlayed", 0))

        if wins >= 300:
            anomalies.append({"msg": f"{wins} career wins — 300 Win Club", "level": "alltime", "nugget": "Only 24 pitchers have won 300+ games. Likely never to be reached again in the modern era"})
        elif wins >= 200:
            anomalies.append({"msg": f"{wins} career wins", "level": "alert", "nugget": "200 wins was once a Hall of Fame benchmark — increasingly rare with modern usage"})
        if wins >= 150:
            comparisons.append({"stat": "Career W", "current": str(wins), "record": "511", "holder": CAREER_RECORDS["wins"]["holder"], "pct": round(wins / 511 * 100)})

        if ks >= 3000:
            anomalies.append({"msg": f"{ks} career K — 3000 Strikeout Club", "level": "alltime", "nugget": "Only 18 pitchers have struck out 3,000+ batters"})
        elif ks >= 2000:
            anomalies.append({"msg": f"{ks} career K — elite strikeout pitcher", "level": "alert", "nugget": "2,000+ career strikeouts marks a dominant career"})
        if ks >= 1500:
            comparisons.append({"stat": "Career K", "current": str(ks), "record": "5714", "holder": CAREER_RECORDS["k_pitch"]["holder"], "pct": round(ks / 5714 * 100)})

        if era <= 2.50 and ip >= 1000:
            anomalies.append({"msg": f"{era:.2f} career ERA — all-time elite", "level": "alltime", "nugget": "A sub-2.50 career ERA over 1000+ IP is dead-ball era territory"})
        elif era <= 3.00 and ip >= 1000:
            anomalies.append({"msg": f"{era:.2f} career ERA — dominant", "level": "alert", "nugget": "A sub-3.00 career ERA is Hall of Fame caliber in any era"})

        if shutouts >= 50:
            anomalies.append({"msg": f"{shutouts} career shutouts — all-time great", "level": "alltime", "nugget": f"Walter Johnson holds the record with 110. Only 10 pitchers have 50+"})
            comparisons.append({"stat": "Shutouts", "current": str(shutouts), "record": "110", "holder": CAREER_RECORDS["shutouts"]["holder"], "pct": round(shutouts / 110 * 100)})

        if whip <= 1.10 and ip >= 1000:
            anomalies.append({"msg": f"{whip:.2f} career WHIP — elite", "level": "alltime", "nugget": "A career WHIP under 1.10 over 1000+ IP is historically rare"})

    # HOF pace comparisons — compare to greats at the same point in their career
    pace_comps = []
    try:
        yby_info = _cached(f"player_yby_{player_id}",
                           lambda: statsapi.player_stat_data(player_id, type="yearByYear"), ttl_seconds=3600)
        seasons_played = sum(1 for sg in yby_info.get("stats", []) if sg["group"] in ("hitting", "pitching") and sg.get("stats", {}).get("gamesPlayed"))
    except Exception:
        seasons_played = 0

    if seasons_played >= 2:
        # HOF cumulative stats through N seasons (curated data)
        HOF_PACE_HITTING = {
            "Barry Bonds": {3: {"hr": 84, "hits": 463}, 5: {"hr": 149, "hits": 828}, 7: {"hr": 227, "hits": 1183}, 10: {"hr": 374, "hits": 1679}, 15: {"hr": 567, "hits": 2252}},
            "Hank Aaron": {3: {"hr": 69, "hits": 533}, 5: {"hr": 140, "hits": 959}, 7: {"hr": 219, "hits": 1397}, 10: {"hr": 342, "hits": 1963}, 15: {"hr": 510, "hits": 2860}},
            "Willie Mays": {3: {"hr": 71, "hits": 432}, 5: {"hr": 152, "hits": 822}, 7: {"hr": 250, "hits": 1191}, 10: {"hr": 388, "hits": 1702}, 15: {"hr": 545, "hits": 2340}},
            "Babe Ruth": {3: {"hr": 13, "hits": 209}, 5: {"hr": 103, "hits": 518}, 7: {"hr": 224, "hits": 862}, 10: {"hr": 399, "hits": 1321}, 15: {"hr": 611, "hits": 1860}},
            "Mickey Mantle": {3: {"hr": 52, "hits": 404}, 5: {"hr": 131, "hits": 707}, 7: {"hr": 209, "hits": 1001}, 10: {"hr": 353, "hits": 1420}, 15: {"hr": 496, "hits": 1866}},
            "Ted Williams": {3: {"hr": 68, "hits": 537}, 5: {"hr": 127, "hits": 893}, 7: {"hr": 176, "hits": 1196}, 10: {"hr": 298, "hits": 1633}, 15: {"hr": 421, "hits": 2153}},
            "Mike Trout": {3: {"hr": 71, "hits": 413}, 5: {"hr": 152, "hits": 738}, 7: {"hr": 219, "hits": 1012}, 10: {"hr": 310, "hits": 1324}},
            "Ken Griffey Jr.": {3: {"hr": 49, "hits": 417}, 5: {"hr": 132, "hits": 764}, 7: {"hr": 220, "hits": 1099}, 10: {"hr": 382, "hits": 1535}, 15: {"hr": 501, "hits": 2033}},
            "Albert Pujols": {3: {"hr": 114, "hits": 555}, 5: {"hr": 201, "hits": 975}, 7: {"hr": 282, "hits": 1354}, 10: {"hr": 408, "hits": 1900}, 15: {"hr": 560, "hits": 2519}},
        }
        HOF_PACE_PITCHING = {
            "Nolan Ryan": {3: {"k": 639, "wins": 42}, 5: {"k": 1079, "wins": 74}, 7: {"k": 1574, "wins": 113}, 10: {"k": 2243, "wins": 171}, 15: {"k": 3284, "wins": 234}},
            "Randy Johnson": {3: {"k": 308, "wins": 22}, 5: {"k": 734, "wins": 56}, 7: {"k": 1236, "wins": 97}, 10: {"k": 2060, "wins": 152}, 15: {"k": 3122, "wins": 230}},
            "Pedro Martinez": {3: {"k": 369, "wins": 30}, 5: {"k": 734, "wins": 65}, 7: {"k": 1239, "wins": 107}, 10: {"k": 1761, "wins": 148}},
            "Greg Maddux": {3: {"k": 377, "wins": 36}, 5: {"k": 640, "wins": 70}, 7: {"k": 1014, "wins": 114}, 10: {"k": 1535, "wins": 176}, 15: {"k": 2216, "wins": 263}},
            "Clayton Kershaw": {3: {"k": 434, "wins": 28}, 5: {"k": 809, "wins": 61}, 7: {"k": 1238, "wins": 98}, 10: {"k": 1774, "wins": 144}},
            "Sandy Koufax": {3: {"k": 269, "wins": 17}, 5: {"k": 573, "wins": 44}, 7: {"k": 1063, "wins": 79}, 10: {"k": 1713, "wins": 129}},
            "Bob Gibson": {3: {"k": 325, "wins": 24}, 5: {"k": 639, "wins": 60}, 7: {"k": 1030, "wins": 97}, 10: {"k": 1614, "wins": 148}},
            "Walter Johnson": {3: {"k": 498, "wins": 57}, 5: {"k": 893, "wins": 107}, 7: {"k": 1324, "wins": 157}, 10: {"k": 1838, "wins": 226}, 15: {"k": 2563, "wins": 327}},
        }

        if group == "hitting":
            hr = int(stats.get("homeRuns", 0))
            hits = int(stats.get("hits", 0))
            for name, data in HOF_PACE_HITTING.items():
                # Find closest season bracket
                bracket = None
                for n in sorted(data.keys()):
                    if seasons_played <= n:
                        bracket = n
                        break
                if not bracket:
                    bracket = max(data.keys())
                if seasons_played > bracket + 2:
                    continue
                hof_hr = data[bracket]["hr"]
                hof_hits = data[bracket]["hits"]
                # Only show if player is within striking distance or ahead
                if hr >= hof_hr * 0.75:
                    diff = hr - hof_hr
                    direction = "ahead of" if diff > 0 else "behind"
                    pace_comps.append({
                        "player": name,
                        "stat": "HR",
                        "current": hr,
                        "hof_val": hof_hr,
                        "through": f"Through {seasons_played} seasons",
                        "bracket": bracket,
                        "diff": abs(diff),
                        "ahead": diff >= 0,
                    })
                if hits >= hof_hits * 0.75:
                    diff = hits - hof_hits
                    pace_comps.append({
                        "player": name,
                        "stat": "Hits",
                        "current": hits,
                        "hof_val": hof_hits,
                        "through": f"Through {seasons_played} seasons",
                        "bracket": bracket,
                        "diff": abs(diff),
                        "ahead": diff >= 0,
                    })
        elif group == "pitching":
            ks = int(stats.get("strikeOuts", 0))
            wins = int(stats.get("wins", 0))
            for name, data in HOF_PACE_PITCHING.items():
                bracket = None
                for n in sorted(data.keys()):
                    if seasons_played <= n:
                        bracket = n
                        break
                if not bracket:
                    bracket = max(data.keys())
                if seasons_played > bracket + 2:
                    continue
                hof_k = data[bracket]["k"]
                hof_w = data[bracket]["wins"]
                if ks >= hof_k * 0.75:
                    diff = ks - hof_k
                    pace_comps.append({
                        "player": name,
                        "stat": "K",
                        "current": ks,
                        "hof_val": hof_k,
                        "through": f"Through {seasons_played} seasons",
                        "bracket": bracket,
                        "diff": abs(diff),
                        "ahead": diff >= 0,
                    })
                if wins >= hof_w * 0.75:
                    diff = wins - hof_w
                    pace_comps.append({
                        "player": name,
                        "stat": "W",
                        "current": wins,
                        "hof_val": hof_w,
                        "through": f"Through {seasons_played} seasons",
                        "bracket": bracket,
                        "diff": abs(diff),
                        "ahead": diff >= 0,
                    })

        # Sort: ahead first, then by closest comparison
        pace_comps.sort(key=lambda x: (not x["ahead"], x["diff"]))
        pace_comps = pace_comps[:6]  # Top 6 most relevant

    # Career milestones checklist — top 10 achievements with context
    milestones = []
    if group == "hitting":
        hr = int(stats.get("homeRuns", 0))
        hits = int(stats.get("hits", 0))
        rbi = int(stats.get("rbi", 0))
        runs = int(stats.get("runs", 0))
        sb = int(stats.get("stolenBases", 0))
        doubles = int(stats.get("doubles", 0))
        bb = int(stats.get("baseOnBalls", 0))
        games = int(stats.get("gamesPlayed", 0))
        avg = float(stats.get("avg", "0") or "0")
        tb = int(stats.get("totalBases", 0))

        hr_milestones = [(700, "700 HR — only Bonds (762), Aaron (755), Ruth (714) have done it"),
                         (600, "600 HR — inner circle power, only 9 players ever"),
                         (500, "500 HR Club — automatic Hall of Fame territory"),
                         (400, "400 HR — elite career power, ~55 players all-time"),
                         (300, "300 HR — franchise-caliber slugger"),
                         (200, "200 HR — established power hitter"),
                         (100, "100 HR — crossed triple digits")]
        for thresh, desc in hr_milestones:
            if hr >= thresh:
                note = f"in {seasons_played} seasons" if seasons_played else ""
                speed = ""
                if seasons_played and thresh >= 100:
                    pace = thresh / seasons_played if seasons_played else 0
                    if thresh == 500 and seasons_played <= 14: speed = " — faster than average (typically takes 16-18 seasons)"
                    elif thresh == 300 and seasons_played <= 9: speed = " — ahead of most HOFers at this point"
                    elif thresh == 100 and seasons_played <= 3: speed = " — blazing fast start"
                milestones.append({"stat": f"⚾ {desc}", "note": f"Reached {note}{speed}"})
                break

        hit_milestones = [(3000, "3,000 Hits — only 33 players in history, near-certain HOF"),
                          (2500, "2,500 Hits — on the doorstep of 3,000"),
                          (2000, "2,000 Hits — sustained excellence over a long career"),
                          (1500, "1,500 Hits — established veteran"),
                          (1000, "1,000 Hits — four-digit hit club")]
        for thresh, desc in hit_milestones:
            if hits >= thresh:
                speed = ""
                if seasons_played:
                    if thresh == 2000 and seasons_played <= 12: speed = " — faster than most HOFers"
                    elif thresh == 1000 and seasons_played <= 6: speed = " — elite hit accumulation rate"
                milestones.append({"stat": f"🎯 {desc}", "note": f"Reached in {seasons_played} seasons{speed}" if seasons_played else ""})
                break

        rbi_milestones = [(1500, "1,500 RBI — all-time run producer, fewer than 30 ever"),
                          (1000, "1,000 RBI — elite career production"),
                          (500, "500 RBI — significant career milestone")]
        for thresh, desc in rbi_milestones:
            if rbi >= thresh:
                speed = ""
                if seasons_played and thresh == 1000 and seasons_played <= 12: speed = " — ahead of pace for most greats"
                milestones.append({"stat": f"💪 {desc}", "note": f"Reached in {seasons_played} seasons{speed}" if seasons_played else ""})
                break

        if runs >= 1500:
            milestones.append({"stat": "🏃 1,500 Runs Scored — all-time elite", "note": "Fewer than 30 players have scored 1,500+ runs"})
        elif runs >= 1000:
            milestones.append({"stat": "🏃 1,000 Runs Scored — consistent producer", "note": f"In {seasons_played} seasons" if seasons_played else ""})

        if sb >= 500:
            milestones.append({"stat": "💨 500 SB — all-time speed legend", "note": "Only 15 players have stolen 500+ bases"})
        elif sb >= 300:
            milestones.append({"stat": "💨 300 SB — elite career baserunner", "note": f"In {seasons_played} seasons" if seasons_played else ""})
        elif sb >= 100:
            milestones.append({"stat": "💨 100 SB — significant speed weapon", "note": ""})

        if doubles >= 600:
            milestones.append({"stat": "2️⃣ 600 Doubles — all-time doubles leader territory", "note": "Only Tris Speaker (792) and Pete Rose (746) have more than 650"})
        elif doubles >= 400:
            milestones.append({"stat": "2️⃣ 400 Doubles — gap-to-gap excellence", "note": "Fewer than 100 players have reached 400 career doubles"})

        if bb >= 1500:
            milestones.append({"stat": "👁️ 1,500 Walks — all-time plate discipline", "note": "Only Bonds, Henderson, Ruth, and a handful of others"})
        elif bb >= 1000:
            milestones.append({"stat": "👁️ 1,000 Walks — elite eye at the plate", "note": ""})

        if avg >= .320 and games >= 1000:
            milestones.append({"stat": f"📊 .{int(avg*1000)} Career AVG over {games} games", "note": "Maintaining .320+ over a full career is historically rare"})
        elif avg >= .300 and games >= 500:
            milestones.append({"stat": f"📊 .{int(avg*1000)} Career AVG — .300 career hitter", "note": "Increasingly rare in the modern era"})

        if tb >= 5000:
            milestones.append({"stat": "🔥 5,000 Total Bases — all-time accumulation", "note": "Only Aaron (6,856), Musial (6,134), Mays (6,066) and a few others"})
        elif tb >= 3000:
            milestones.append({"stat": "🔥 3,000 Total Bases — sustained power + contact", "note": ""})

    elif group == "pitching":
        wins = int(stats.get("wins", 0))
        ks = int(stats.get("strikeOuts", 0))
        ip = float(stats.get("inningsPitched", "0").replace(",", "") or "0")
        saves = int(stats.get("saves", 0))
        shutouts = int(stats.get("shutouts", 0))
        cg = int(stats.get("completeGames", 0))
        era = float(stats.get("era", "99") or "99")
        games = int(stats.get("gamesPlayed", 0))

        k_milestones = [(4000, "4,000 K — only Nolan Ryan (5,714) and Randy Johnson (4,875)"),
                        (3000, "3,000 K Club — only 18 pitchers in history"),
                        (2000, "2,000 K — dominant career strikeout pitcher"),
                        (1000, "1,000 K — established strikeout arm")]
        for thresh, desc in k_milestones:
            if ks >= thresh:
                speed = ""
                if seasons_played:
                    if thresh == 3000 and seasons_played <= 15: speed = " — faster than most who reached it"
                    elif thresh == 1000 and seasons_played <= 5: speed = " — elite K rate early in career"
                milestones.append({"stat": f"🔥 {desc}", "note": f"Reached in {seasons_played} seasons{speed}" if seasons_played else ""})
                break

        win_milestones = [(300, "300 Wins — only 24 pitchers ever, likely unreachable today"),
                          (200, "200 Wins — once the HOF standard for pitchers"),
                          (100, "100 Wins — established starter")]
        for thresh, desc in win_milestones:
            if wins >= thresh:
                speed = ""
                if seasons_played and thresh == 200 and seasons_played <= 13: speed = " — ahead of typical pace"
                milestones.append({"stat": f"🏆 {desc}", "note": f"Reached in {seasons_played} seasons{speed}" if seasons_played else ""})
                break

        if saves >= 400:
            milestones.append({"stat": "💾 400 Saves — all-time closer elite", "note": "Only Rivera (652), Hoffman (601), Lee Smith (478), and a few others"})
        elif saves >= 200:
            milestones.append({"stat": "💾 200 Saves — established closer", "note": ""})

        if shutouts >= 40:
            milestones.append({"stat": f"🚫 {shutouts} Shutouts — all-time dominance", "note": "Extremely rare in the modern era"})
        elif shutouts >= 20:
            milestones.append({"stat": f"🚫 {shutouts} Shutouts — significant career total", "note": ""})

        if cg >= 100:
            milestones.append({"stat": f"💪 {cg} Complete Games — workhorse era", "note": "100+ CG is virtually impossible in modern baseball"})
        elif cg >= 30:
            milestones.append({"stat": f"💪 {cg} Complete Games", "note": "Rare in the modern bullpen era"})

        if ip >= 3000:
            milestones.append({"stat": "📏 3,000+ Innings Pitched — iron man durability", "note": "Fewer than 100 pitchers have thrown 3,000+ career IP"})
        elif ip >= 2000:
            milestones.append({"stat": "📏 2,000+ Innings Pitched — sustained workhorse", "note": ""})

        if era <= 3.00 and ip >= 1500:
            milestones.append({"stat": f"📊 {era:.2f} Career ERA over {int(ip)} IP", "note": "Sub-3.00 career ERA with 1500+ IP is Hall of Fame caliber"})
        elif era <= 3.50 and ip >= 1000:
            milestones.append({"stat": f"📊 {era:.2f} Career ERA over {int(ip)} IP", "note": "Consistently above-average over a long career"})

    milestones = milestones[:10]

    # Career red flags — historically bad career stats
    red_flags = []
    if group == "hitting":
        games = int(stats.get("gamesPlayed", 0))
        avg = float(stats.get("avg", "0") or "0")
        ops = float(stats.get("ops", "0") or "0")
        ks = int(stats.get("strikeOuts", 0))
        hr = int(stats.get("homeRuns", 0))
        pa = int(stats.get("plateAppearances", 0) or 0)
        k_rate = (ks / pa * 100) if pa > 0 else 0

        if avg <= .230 and games >= 500:
            red_flags.append({"msg": f".{int(avg*1000)} career AVG over {games} games", "level": "bad", "nugget": "A sub-.230 career average over 500+ games is well below the typical starter threshold"})
        if ops <= .680 and games >= 500:
            red_flags.append({"msg": f"{ops:.3f} career OPS — below average for a career", "level": "bad", "nugget": "A career OPS below .700 over 500+ games suggests a defense-first or bench player profile"})
        if k_rate >= 28 and pa >= 2000:
            red_flags.append({"msg": f"{k_rate:.1f}% career K rate — historically high", "level": "bad", "nugget": "Career K rates above 28% are among the highest ever. Adam Dunn (32.0%) and Mark Reynolds (31.5%) are the all-time leaders"})
        if ks >= 2000:
            red_flags.append({"msg": f"{ks} career strikeouts", "level": "bad", "nugget": f"Reggie Jackson holds the career record with 2,597 K. High strikeouts don't preclude greatness but show swing-and-miss"})
        elif ks >= 1500 and games < 1500:
            red_flags.append({"msg": f"{ks} K in only {games} games — high K accumulation", "level": "bad", "nugget": "Accumulating strikeouts faster than games played is an extreme whiff rate"})

    elif group == "pitching":
        era = float(stats.get("era", "99") or "99")
        ip = float(stats.get("inningsPitched", "0").replace(",", "") or "0")
        whip = float(stats.get("whip", "99") or "99")
        wins = int(stats.get("wins", 0))
        losses = int(stats.get("losses", 0))
        hr_allowed = int(stats.get("homeRuns", 0))

        if era >= 4.50 and ip >= 1000:
            red_flags.append({"msg": f"{era:.2f} career ERA over {int(ip)} IP", "level": "bad", "nugget": "A career ERA above 4.50 over 1000+ IP suggests a back-of-rotation or long-relief career"})
        if whip >= 1.40 and ip >= 1000:
            red_flags.append({"msg": f"{whip:.2f} career WHIP — too many baserunners", "level": "bad", "nugget": "A career WHIP above 1.40 means constant traffic on the bases"})
        if losses >= 200:
            red_flags.append({"msg": f"{losses} career losses", "level": "bad", "nugget": f"Only pitchers with very long careers accumulate 200+ losses. Nolan Ryan (292) and Gaylord Perry (265) lead all-time"})
        if wins > 0 and losses > 0 and (wins / (wins + losses)) < .450 and (wins + losses) >= 200:
            pct = wins / (wins + losses)
            red_flags.append({"msg": f".{int(pct*1000)} career win percentage", "level": "bad", "nugget": "A sub-.450 win% over 200+ decisions often reflects pitching for bad teams or inconsistency"})

    _severity = {"caution": 0, "bad": 1, "terrible": 2}
    red_flags.sort(key=lambda x: _severity.get(x["level"], 1))

    return jsonify({
        "name": info.get("first_name", "") + " " + info.get("last_name", ""),
        "position": info.get("position", ""),
        "stats": stats,
        "anomalies": anomalies,
        "red_flags": red_flags,
        "comparisons": comparisons,
        "pace_comps": pace_comps,
        "seasons_played": seasons_played,
        "milestones": milestones,
    })


@app.route("/api/player/<int:player_id>/yearByYear")
def player_year_by_year(player_id):
    """Get year-by-year historical stats with standout season flags."""
    info = _cached(f"player_yby_{player_id}",
                   lambda: statsapi.player_stat_data(player_id, type="yearByYear"), ttl_seconds=3600)
    is_pitcher = info.get("position", "") == "P"
    preferred = "pitching" if is_pitcher else "hitting"
    group = preferred

    # Use raw API to get team info per season
    seasons = []
    try:
        raw = statsapi.get("person", {"personId": player_id, "hydrate": f"stats(group={preferred},type=yearByYear,sportId=1)"})
        splits = raw.get("people", [{}])[0].get("stats", [{}])[0].get("splits", [])
        for sp in splits:
            s = sp.get("stat", {})
            if s and s.get("gamesPlayed"):
                s["season"] = sp.get("season", "")
                s["team"] = sp.get("team", {}).get("name", "")
                s["team_id"] = sp.get("team", {}).get("id", "")
                seasons.append(s)
    except Exception:
        # Fallback to statsapi wrapper
        for sg in info.get("stats", []):
            if sg["group"] == preferred:
                s = sg.get("stats", {})
                if s:
                    s["season"] = sg.get("season", "")
                    s["team"] = sg.get("team", "") or ""
                    s["team_id"] = sg.get("team_id", "") or ""
                    seasons.append(s)

    # Sort chronologically and assign unique keys for mid-season trades
    seasons = sorted(seasons, key=lambda x: (x.get("season", ""), x.get("team", "")))
    for i, s in enumerate(seasons):
        s["_key"] = f"{s.get('season', '')}_{i}"

    # Flag standout seasons
    anomalies = []
    red_flag_seasons = []
    for s in seasons:
        yr = s.get("season", "")
        flags = []
        bad_flags = []
        if group == "hitting":
            games = int(s.get("gamesPlayed", 0))
            if games < 50:
                continue
            hr = int(s.get("homeRuns", 0))
            avg = float(s.get("avg", "0") or "0")
            ops = float(s.get("ops", "0") or "0")
            hits = int(s.get("hits", 0))
            rbi = int(s.get("rbi", 0))
            sb = int(s.get("stolenBases", 0))
            pa = int(s.get("plateAppearances", 0) or s.get("atBats", 0) or 0)
            ks = int(s.get("strikeOuts", 0))
            k_rate = (ks / pa * 100) if pa > 0 else 0
            if hr >= 50:
                flags.append({"msg": f"{hr} HR in {yr} — 50-HR season", "level": "alltime", "nugget": "Only ~30 50-HR seasons in MLB history"})
            elif hr >= 40:
                flags.append({"msg": f"{hr} HR in {yr} — elite power season", "level": "alert", "nugget": "A 40-HR season is a top-10 power finish most years"})
            if avg >= .350 and games >= 100:
                flags.append({"msg": f".{int(avg*1000)} AVG in {yr} — historic", "level": "alltime", "nugget": "Fewer than 5 players have hit .350+ in a season since 2000"})
            elif avg >= .320 and games >= 100:
                flags.append({"msg": f".{int(avg*1000)} AVG in {yr} — batting title contender", "level": "alert", "nugget": "Typically wins or contends for the batting title"})
            if ops >= 1.050 and games >= 100:
                flags.append({"msg": f"{ops:.3f} OPS in {yr} — MVP-caliber", "level": "alltime", "nugget": "A 1.050+ OPS season is top-5 in baseball that year"})
            elif ops >= .950 and games >= 100:
                flags.append({"msg": f"{ops:.3f} OPS in {yr} — All-Star level", "level": "alert", "nugget": "A .950+ OPS is typically top-15 in the league"})
            if hits >= 220:
                flags.append({"msg": f"{hits} hits in {yr} — 220+ hit season", "level": "alltime", "nugget": "Only ~50 220-hit seasons in modern history"})
            if rbi >= 140:
                flags.append({"msg": f"{rbi} RBI in {yr} — dominant run producer", "level": "alltime", "nugget": "140+ RBI hasn't happened since the early 2000s"})
            if sb >= 60:
                flags.append({"msg": f"{sb} SB in {yr} — elite speed season", "level": "alltime", "nugget": "60+ SB in a season is historically rare"})
            # Bad season flags
            if avg <= .200 and games >= 80:
                bad_flags.append({"msg": f".{int(avg*1000)} AVG in {yr} — Mendoza Line", "level": "bad", "nugget": "Chris Davis hit .168 in 2018 — the worst ever for a qualified hitter"})
            elif avg <= .220 and games >= 80:
                bad_flags.append({"msg": f".{int(avg*1000)} AVG in {yr} — rough season", "level": "bad", "nugget": "Sub-.220 over a full season is replacement-level offense"})
            if ops <= .600 and games >= 80:
                bad_flags.append({"msg": f"{ops:.3f} OPS in {yr} — replacement level", "level": "terrible", "nugget": "Sub-.600 OPS is among the worst offensive seasons for a regular"})
            elif ops <= .650 and games >= 80:
                bad_flags.append({"msg": f"{ops:.3f} OPS in {yr} — well below average", "level": "bad", "nugget": "League average OPS is .710-.720"})
            if k_rate >= 35 and pa >= 200:
                bad_flags.append({"msg": f"{k_rate:.1f}% K rate in {yr} — extreme", "level": "terrible", "nugget": "Among the highest single-season K rates in MLB history"})
            elif k_rate >= 30 and pa >= 200:
                bad_flags.append({"msg": f"{k_rate:.1f}% K rate in {yr} — high strikeouts", "level": "bad", "nugget": "30%+ K rate makes sustained production very difficult"})
        elif group == "pitching":
            games = int(s.get("gamesPlayed", 0))
            if games < 10:
                continue
            era = float(s.get("era", "99") or "99")
            ks = int(s.get("strikeOuts", 0))
            wins = int(s.get("wins", 0))
            losses = int(s.get("losses", 0))
            ip = float(s.get("inningsPitched", "0").replace(",", "") or "0")
            whip = float(s.get("whip", "99") or "99")
            bb9 = float(s.get("walksPer9Inn", "0") or "0")
            if era <= 2.00 and ip >= 100:
                flags.append({"msg": f"{era:.2f} ERA in {yr} — historic", "level": "alltime", "nugget": "A sub-2.00 ERA over 100+ IP is Cy Young-lock territory"})
            elif era <= 2.80 and ip >= 100:
                flags.append({"msg": f"{era:.2f} ERA in {yr} — ace season", "level": "alert", "nugget": "Sub-2.80 ERA typically finishes top-5 in Cy Young voting"})
            if ks >= 300:
                flags.append({"msg": f"{ks} K in {yr} — 300-K season", "level": "alltime", "nugget": "Only 18 300-K seasons in MLB history"})
            elif ks >= 250:
                flags.append({"msg": f"{ks} K in {yr} — dominant strikeout season", "level": "alert", "nugget": "250+ K is an ace-level achievement"})
            if wins >= 20:
                flags.append({"msg": f"{wins} wins in {yr} — 20-win season", "level": "alert", "nugget": "20-win seasons have become extremely rare in the modern era"})
            if whip <= 0.95 and ip >= 100:
                flags.append({"msg": f"{whip:.2f} WHIP in {yr} — historic control", "level": "alltime", "nugget": "Sub-0.95 WHIP over 100+ IP is all-time elite"})
            # Bad season flags
            if era >= 6.00 and ip >= 50:
                bad_flags.append({"msg": f"{era:.2f} ERA in {yr} — terrible", "level": "terrible", "nugget": "A 6.00+ ERA over 50+ IP is demotion-worthy. Worst qualified ever: Les Sweetland (7.71 in 1930)"})
            elif era >= 5.00 and ip >= 80:
                bad_flags.append({"msg": f"{era:.2f} ERA in {yr} — rough season", "level": "bad", "nugget": "A 5.00+ ERA is back-of-rotation or worse"})
            if whip >= 1.60 and ip >= 50:
                bad_flags.append({"msg": f"{whip:.2f} WHIP in {yr} — too many baserunners", "level": "terrible", "nugget": "Nearly 2 baserunners per inning is unsustainable"})
            elif whip >= 1.40 and ip >= 80:
                bad_flags.append({"msg": f"{whip:.2f} WHIP in {yr} — below average", "level": "bad", "nugget": "League average WHIP is ~1.30"})
            if bb9 >= 5.0 and ip >= 50:
                bad_flags.append({"msg": f"{bb9:.1f} BB/9 in {yr} — severe control issues", "level": "terrible", "nugget": "Walking 5+ per 9 innings is historically bad command"})
            if losses >= 15 and wins < 10:
                bad_flags.append({"msg": f"{wins}-{losses} record in {yr}", "level": "bad", "nugget": "A 15+ loss season with fewer than 10 wins is a rough year"})
        if flags:
            anomalies.append({"season": yr, "_key": s.get("_key", ""), "flags": flags})
        if bad_flags:
            red_flag_seasons.append({"season": yr, "_key": s.get("_key", ""), "flags": bad_flags})

    return jsonify({
        "name": info.get("first_name", "") + " " + info.get("last_name", ""),
        "position": info.get("position", ""),
        "team": info.get("current_team", ""),
        "seasons": seasons,
        "anomalies": anomalies,
        "red_flags": red_flag_seasons,
    })


@app.route("/api/player/<int:player_id>/live")
def player_live(player_id):
    """Get player's current live game stats."""
    info = _cached(f"player_season_{player_id}",
                   lambda: statsapi.player_stat_data(player_id, type="season"), ttl_seconds=60)
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
            # Find next upcoming game (look ahead 7 days)
            upcoming = [g for g in schedule if g["status"] not in ("Final", "In Progress")]
            if not upcoming:
                try:
                    from datetime import date
                    start = date.today() + timedelta(days=1)
                    end = start + timedelta(days=6)
                    future = statsapi.schedule(team=team_id, start_date=start.strftime("%m/%d/%Y"), end_date=end.strftime("%m/%d/%Y"))
                    upcoming = [g for g in future if g["status"] not in ("Final", "In Progress")]
                except Exception:
                    pass
            if upcoming:
                g = upcoming[0]
                result["next_game"] = f"Next: {g['away_name']} @ {g['home_name']} — {g['game_date']}"
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
            player_stats = {}
            for side in ["away", "home"]:
                for b in box.get(f"{side}Batters", []):
                    if b.get("personId") == player_id:
                        player_stats = {
                            "atBats": b.get("ab", "0"),
                            "runs": b.get("r", "0"),
                            "hits": b.get("h", "0"),
                            "rbi": b.get("rbi", "0"),
                            "baseOnBalls": b.get("bb", "0"),
                            "strikeOuts": b.get("k", "0"),
                            "homeRuns": b.get("hr", "0"),
                            "avg": b.get("avg", ""),
                        }
                        break
                for p in box.get(f"{side}Pitchers", []):
                    if p.get("personId") == player_id:
                        player_stats = {
                            "inningsPitched": p.get("ip", "0"),
                            "hits": p.get("h", "0"),
                            "runs": p.get("r", "0"),
                            "earnedRuns": p.get("er", "0"),
                            "baseOnBalls": p.get("bb", "0"),
                            "strikeOuts": p.get("k", "0"),
                            "homeRuns": p.get("hr", "0"),
                            "era": p.get("era", ""),
                        }
                        break
                if player_stats:
                    break
            if player_stats:
                result["player_stats"] = player_stats
        except Exception:
            pass

    except Exception:
        pass

    return jsonify(result)


@app.route("/api/games/history")
def games_history():
    """Get all games from the past 14 days."""
    all_games = []
    for days_ago in range(14):
        date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        try:
            games = statsapi.schedule(date=date)
            for g in games:
                if g["status"] in ("Final", "Game Over", "Completed Early"):
                    all_games.append({
                        "game_id": g.get("game_id"),
                        "date": g["game_date"],
                        "away": g["away_name"], "home": g["home_name"],
                        "away_id": g.get("away_id"), "home_id": g.get("home_id"),
                        "away_score": g.get("away_score", 0),
                        "home_score": g.get("home_score", 0),
                        "innings": g.get("current_inning", 9),
                    })
        except Exception:
            continue
    return jsonify(all_games)


@app.route("/api/game/<int:game_id>/preview")
def game_preview(game_id):
    """Preview an upcoming game: probable pitchers, projected lineups, series history."""
    try:
        # Get game info
        game_data = statsapi.schedule(game_id=game_id)
        if not game_data:
            return jsonify({"available": False})
        g = game_data[0]
        away_id = g.get("away_id")
        home_id = g.get("home_id")

        # Probable pitchers with season stats
        def pitcher_info(name, predicted=False):
            if not name:
                return None
            try:
                players = _cached(f"lookup_{name}", lambda: statsapi.lookup_player(name), ttl_seconds=86400)
                if players:
                    pid = players[0]["id"]
                    d = _cached(f"pitcher_season_{pid}", lambda: statsapi.player_stat_data(pid, type="season", group="pitching"), ttl_seconds=300)
                    st = {}
                    for sg in d.get("stats", []):
                        if sg["group"] == "pitching":
                            st = sg.get("stats", {})
                            break
                    return {"id": pid, "name": name, "era": st.get("era", "---"), "wins": st.get("wins", 0),
                            "losses": st.get("losses", 0), "whip": st.get("whip", "---"),
                            "k": st.get("strikeOuts", 0), "ip": st.get("inningsPitched", "0"), "predicted": predicted}
            except Exception:
                pass
            return {"id": 0, "name": name, "era": "---", "wins": 0, "losses": 0, "whip": "---", "k": 0, "ip": "0", "predicted": predicted}

        def _build_team_rotation(team_id):
            """Fetch season-long starter history for a team. Cached 6hrs."""
            return _build_team_rotation_global(team_id)

        def predict_pitcher(team_id, game_date_str=None, exclude=None):
            """Predict next starter by projecting the rotation order forward."""
            try:
                exclude = exclude or []
                target_date = datetime.strptime(game_date_str, "%Y-%m-%d").date() if game_date_str else datetime.now().date()
                starter_history = _build_team_rotation(team_id)
                if not starter_history:
                    return None
                # Append announced starters for upcoming games before target
                end = target_date.strftime("%m/%d/%Y")
                sched = statsapi.schedule(team=team_id, start_date=datetime.now().strftime("%m/%d/%Y"), end_date=end)
                upcoming = sorted(
                    [x for x in sched if x["status"] != "Final" and x.get("game_date", "") <= game_date_str],
                    key=lambda x: x["game_date"]
                )
                extended_history = list(starter_history)
                for ug in upcoming:
                    side_key = "away_probable_pitcher" if ug.get("away_id") == team_id else "home_probable_pitcher"
                    announced = ug.get(side_key)
                    if announced:
                        extended_history.append(announced)
                # Identify true rotation members (3+ starts season-long), filter spot starters
                from collections import Counter
                start_counts = Counter(starter_history)
                rotation_members = {name for name, count in start_counts.items() if count >= 3}
                # Fallback: if fewer than 4 qualify, lower to 2+ starts
                if len(rotation_members) < 4:
                    rotation_members = {name for name, count in start_counts.items() if count >= 2}
                # Filter out players not on active roster (IL, optioned, etc.) BEFORE building order
                def _get_active_pitchers(tid):
                    def _fetch():
                        try:
                            rd = statsapi.get("team_roster", {"teamId": tid, "rosterType": "active"})
                            names = set()
                            for p in rd.get("roster", []):
                                if p.get("position", {}).get("abbreviation") == "P" or p.get("position", {}).get("type") == "Pitcher":
                                    names.add(p.get("person", {}).get("fullName", ""))
                            return names
                        except Exception:
                            return set()
                    return _cached(f"active_pitchers_{tid}", _fetch, ttl_seconds=3600)
                active_pitchers = _get_active_pitchers(team_id)
                if active_pitchers:
                    rotation_members = {n for n in rotation_members if n in active_pitchers}
                if not rotation_members:
                    return None
                # Build rotation order from the last full cycle of active rotation members
                recent_rotation_sequence = []
                for name in reversed(extended_history):
                    if name in rotation_members:
                        recent_rotation_sequence.append(name)
                    if len(recent_rotation_sequence) >= len(rotation_members):
                        break
                # This gives us [most_recent, ..., oldest_in_cycle], reverse for forward order
                recent_rotation_sequence.reverse()
                # Deduplicate while preserving order (in case of back-to-back by same pitcher)
                rotation = []
                for name in recent_rotation_sequence:
                    if name not in rotation:
                        rotation.append(name)
                if not rotation:
                    return None
                # Count only unannounced games between last known starter and target
                last_announced_date = ""
                for ug in reversed(upcoming):
                    side_key = "away_probable_pitcher" if ug.get("away_id") == team_id else "home_probable_pitcher"
                    if ug.get(side_key):
                        last_announced_date = ug["game_date"]
                        break
                games_ahead = len([x for x in upcoming
                                   if x.get("game_date", "") <= game_date_str
                                   and x.get("game_date", "") > last_announced_date])
                if games_ahead < 1:
                    games_ahead = 1
                # Find last rotation member who started
                last_starter = None
                for name in reversed(extended_history):
                    if name in rotation_members:
                        last_starter = name
                        break
                if not last_starter:
                    last_starter = rotation[0]
                try:
                    last_idx = rotation.index(last_starter)
                except ValueError:
                    last_idx = 0
                predicted_idx = (last_idx + games_ahead) % len(rotation)
                predicted = rotation[predicted_idx]
                if predicted in exclude:
                    predicted_idx = (predicted_idx + 1) % len(rotation)
                    predicted = rotation[predicted_idx]
                return predicted
            except Exception:
                pass
            return None

        away_pitcher = pitcher_info(g.get("away_probable_pitcher"))
        home_pitcher = pitcher_info(g.get("home_probable_pitcher"))

        # If no official pitcher, predict one (using game date and excluding known starters)
        game_date_str = g.get("game_date")
        # Collect known pitchers to exclude from predictions for the other side
        exclude_away = []
        exclude_home = []
        if g.get("away_probable_pitcher"):
            exclude_away.append(g["away_probable_pitcher"])
        if g.get("home_probable_pitcher"):
            exclude_home.append(g["home_probable_pitcher"])

        if not away_pitcher:
            predicted_name = predict_pitcher(away_id, game_date_str, exclude_away)
            if predicted_name:
                away_pitcher = pitcher_info(predicted_name, predicted=True)
                exclude_away.append(predicted_name)
        if not home_pitcher:
            predicted_name = predict_pitcher(home_id, game_date_str, exclude_home)
            if predicted_name:
                home_pitcher = pitcher_info(predicted_name, predicted=True)

        # Recent lineups from last game
        def get_lineup(team_id):
            def _fetch():
                try:
                    start = (datetime.now() - timedelta(days=14)).strftime("%m/%d/%Y")
                    end = datetime.now().strftime("%m/%d/%Y")
                    sched = statsapi.schedule(team=team_id, start_date=start, end_date=end)
                    finals = [x for x in sched if x["status"] == "Final"]
                    if not finals:
                        return ([], True)
                    gd = statsapi.get("game", {"gamePk": finals[-1]["game_id"]})
                    side = "home" if finals[-1].get("home_id") == team_id else "away"
                    box = gd["liveData"]["boxscore"]["teams"][side]
                    order = box.get("battingOrder", [])
                    players = box.get("players", {})
                    lineup = []
                    for pid in order[:9]:
                        p = players.get(f"ID{pid}", {})
                        lineup.append({"id": pid, "name": p.get("person", {}).get("fullName", "?"),
                                       "pos": p.get("position", {}).get("abbreviation", "?")})
                    return (lineup, True)
                except Exception:
                    return ([], True)
            return _cached(f"lineup_{team_id}", _fetch, ttl_seconds=300)

        # Check if official lineup is posted (game has battingOrder in live feed)
        def get_official_lineup(team_id, game_id, is_home):
            try:
                gd = _cached(f"game_feed_{game_id}", lambda: statsapi.get("game", {"gamePk": game_id}), ttl_seconds=60)
                side = "home" if is_home else "away"
                box = gd["liveData"]["boxscore"]["teams"][side]
                order = box.get("battingOrder", [])
                if order:
                    players = box.get("players", {})
                    lineup = []
                    for pid in order[:9]:
                        p = players.get(f"ID{pid}", {})
                        lineup.append({"id": pid, "name": p.get("person", {}).get("fullName", "?"),
                                       "pos": p.get("position", {}).get("abbreviation", "?")})
                    return lineup, False  # official
            except Exception:
                pass
            return None, True

        # Injuries (IL players for both teams)
        def get_injuries(team_id):
            def _fetch():
                try:
                    roster = statsapi.get("team_roster", {"teamId": team_id, "rosterType": "fullRoster"})
                    il = []
                    for p in roster.get("roster", []):
                        code = p.get("status", {}).get("code", "")
                        if code in ("D7", "D10", "D15", "D60", "ILF", "RA"):
                            il.append({"name": p["person"]["fullName"], "status": p["status"]["description"]})
                    return il
                except Exception:
                    return []
            return _cached(f"injuries_{team_id}", _fetch, ttl_seconds=1800)

        # Run independent data fetches in parallel
        with ThreadPoolExecutor(max_workers=6) as ex:
            fut_away_lineup = ex.submit(get_lineup, away_id)
            fut_home_lineup = ex.submit(get_lineup, home_id)
            fut_away_injuries = ex.submit(get_injuries, away_id)
            fut_home_injuries = ex.submit(get_injuries, home_id)
            fut_official_away = ex.submit(get_official_lineup, away_id, game_id, False)
            fut_official_home = ex.submit(get_official_lineup, home_id, game_id, True)

        away_official, away_off_pred = fut_official_away.result()
        home_official, home_off_pred = fut_official_home.result()
        if away_official is not None:
            away_lineup, away_lineup_predicted = away_official, away_off_pred
        else:
            away_lineup, away_lineup_predicted = fut_away_lineup.result()
        if home_official is not None:
            home_lineup, home_lineup_predicted = home_official, home_off_pred
        else:
            home_lineup, home_lineup_predicted = fut_home_lineup.result()

        away_injuries = fut_away_injuries.result()
        home_injuries = fut_home_injuries.result()

        # Series history (last 60 days between these teams) — cached 1hr
        def _get_series():
            try:
                start = (datetime.now() - timedelta(days=60)).strftime("%m/%d/%Y")
                end = datetime.now().strftime("%m/%d/%Y")
                matchups = statsapi.schedule(team=away_id, opponent=home_id, start_date=start, end_date=end)
                return [{"date": m["game_date"], "away": m["away_name"], "home": m["home_name"],
                         "away_score": m.get("away_score", 0), "home_score": m.get("home_score", 0),
                         "game_id": m.get("game_id")} for m in matchups if m["status"] == "Final"]
            except Exception:
                return []
        series = _cached(f"series_{away_id}_{home_id}", _get_series, ttl_seconds=3600)

        # Weather (requires WEATHER_API_KEY env var)
        weather = None
        import os
        weather_key = os.environ.get("WEATHER_API_KEY")
        if weather_key and g.get("venue_name"):
            try:
                import requests as req
                wr = req.get(f"http://api.weatherapi.com/v1/forecast.json?key={weather_key}&q={g['venue_name']}&days=1&aqi=no", timeout=3).json()
                fc = wr.get("forecast", {}).get("forecastday", [{}])[0].get("day", {})
                weather = {"temp_f": fc.get("avgtemp_f"), "condition": fc.get("condition", {}).get("text", ""),
                           "wind_mph": fc.get("maxwind_mph"), "precip_in": fc.get("totalprecip_in", 0)}
            except Exception:
                pass

        # Odds from ESPN (free, no key needed)
        odds = None
        try:
            import requests as req
            game_date = g.get("game_date", "").replace("-", "")
            espn = req.get(f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={game_date}", timeout=3).json()
            away_name = g["away_name"].split()[-1].lower()
            for ev in espn.get("events", []):
                comp = ev.get("competitions", [{}])[0]
                teams = [c.get("team", {}).get("displayName", "").lower() for c in comp.get("competitors", [])]
                if any(away_name in t for t in teams):
                    ev_odds = comp.get("odds", [])
                    if ev_odds:
                        o = ev_odds[0]
                        odds = {"provider": o.get("provider", {}).get("name", ""), "details": o.get("details", ""),
                                "over_under": o.get("overUnder"), "spread": o.get("spread")}
                    break
        except Exception:
            pass

        return jsonify({
            "available": True,
            "away": g["away_name"], "home": g["home_name"],
            "away_id": away_id, "home_id": home_id,
            "game_time": g.get("game_datetime", ""),
            "venue": g.get("venue_name", ""),
            "away_pitcher": away_pitcher,
            "home_pitcher": home_pitcher,
            "away_lineup": away_lineup,
            "home_lineup": home_lineup,
            "away_lineup_predicted": away_lineup_predicted,
            "home_lineup_predicted": home_lineup_predicted,
            "series": series,
            "away_injuries": away_injuries,
            "home_injuries": home_injuries,
            "weather": weather,
            "odds": odds,
        })
    except Exception as e:
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/game/<int:game_id>/boxscore")
def game_boxscore(game_id):
    """Full in-app box score: linescore + batting/pitching lines."""
    try:
        box = statsapi.boxscore_data(game_id)
        away_team = box.get("teamInfo", {}).get("away", {}).get("teamName", "Away")
        home_team = box.get("teamInfo", {}).get("home", {}).get("teamName", "Home")
        away_id = box.get("teamInfo", {}).get("away", {}).get("id", 0)
        home_id = box.get("teamInfo", {}).get("home", {}).get("id", 0)

        # Batting lines
        def parse_batters(side):
            batters = []
            for b in box.get(f"{side}Batters", []):
                if b.get("personId", 0) == 0:
                    continue
                batters.append({
                    "id": b["personId"],
                    "name": b.get("name", ""),
                    "pos": b.get("position", ""),
                    "ab": b.get("ab", ""),
                    "r": b.get("r", ""),
                    "h": b.get("h", ""),
                    "rbi": b.get("rbi", ""),
                    "bb": b.get("bb", ""),
                    "k": b.get("k", ""),
                    "avg": b.get("avg", ""),
                })
            return batters

        # Pitching lines
        def parse_pitchers(side):
            pitchers = []
            for p in box.get(f"{side}Pitchers", []):
                if p.get("personId", 0) == 0:
                    continue
                pitchers.append({
                    "id": p["personId"],
                    "name": p.get("name", ""),
                    "ip": p.get("ip", ""),
                    "h": p.get("h", ""),
                    "r": p.get("r", ""),
                    "er": p.get("er", ""),
                    "bb": p.get("bb", ""),
                    "k": p.get("k", ""),
                    "era": p.get("era", ""),
                })
            return pitchers

        # Linescore
        linescore = statsapi.linescore(game_id)
        # Structured linescore for table rendering
        gd = statsapi.get("game", {"gamePk": game_id})
        ls_data = gd.get("liveData", {}).get("linescore", {})
        innings = ls_data.get("innings", [])
        ls_teams = ls_data.get("teams", {})
        linescore_table = {
            "innings": [{"num": inn["num"], "away": inn.get("away", {}).get("runs", ""), "home": inn.get("home", {}).get("runs", "")} for inn in innings],
            "away": {"r": ls_teams.get("away", {}).get("runs", 0), "h": ls_teams.get("away", {}).get("hits", 0), "e": ls_teams.get("away", {}).get("errors", 0)},
            "home": {"r": ls_teams.get("home", {}).get("runs", 0), "h": ls_teams.get("home", {}).get("hits", 0), "e": ls_teams.get("home", {}).get("errors", 0)},
        }

        return jsonify({
            "available": True,
            "away_team": away_team, "home_team": home_team,
            "away_id": away_id, "home_id": home_id,
            "away_batters": parse_batters("away"),
            "home_batters": parse_batters("home"),
            "away_pitchers": parse_pitchers("away"),
            "home_pitchers": parse_pitchers("home"),
            "linescore": linescore,
            "linescore_table": linescore_table,
        })
    except Exception as e:
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/game/<int:game_id>/plays")
def game_plays(game_id):
    """Return at-bat play-by-play data for horizontal scrolling."""
    try:
        import requests as req
        feed = req.get(f"https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live").json()
        all_plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
        gd = feed.get("gameData", {})
        away_abbr = gd.get("teams", {}).get("away", {}).get("abbreviation", "AWY")
        home_abbr = gd.get("teams", {}).get("home", {}).get("abbreviation", "HME")
        at_bats = []
        current_bases = {"first": False, "second": False, "third": False}
        prev_half_inning = None
        for play in all_plays:
            result = play.get("result", {})
            about = play.get("about", {})
            matchup = play.get("matchup", {})
            if not result.get("description"):
                continue
            if not about.get("isComplete", False):
                continue
            # Reset bases on new half-inning
            half_inning_key = f"{about.get('halfInning','')}{about.get('inning',0)}"
            if half_inning_key != prev_half_inning:
                current_bases = {"first": False, "second": False, "third": False}
                prev_half_inning = half_inning_key
            events = play.get("playEvents", [])
            pitches = []
            for ev in events:
                if ev.get("isPitch"):
                    pd = ev.get("pitchData", {})
                    coords = pd.get("coordinates", {})
                    ct = ev.get("count", {})
                    pitches.append({
                        "x": coords.get("pX", 0),
                        "y": coords.get("pZ", 0),
                        "speed": pd.get("startSpeed", 0),
                        "type": ev.get("details", {}).get("type", {}).get("code", ""),
                        "call": ev.get("details", {}).get("call", {}).get("code", ""),
                        "balls": ct.get("balls", 0),
                        "strikes": ct.get("strikes", 0),
                        "outs": ct.get("outs", 0),
                    })
            # Runners at end of at-bat — track base state across the half-inning
            play_runners = play.get("runners", [])
            # Determine which bases were vacated or occupied by runners in this play
            bases_vacated = set()
            bases_occupied = set()
            for pr in play_runners:
                start_base = pr.get("movement", {}).get("start", "")
                end_base = pr.get("movement", {}).get("end", "")
                if start_base in ("1B", "2B", "3B"):
                    bases_vacated.add(start_base)
                if end_base in ("1B", "2B", "3B"):
                    bases_occupied.add(end_base)
            # Start from previous base state, remove vacated, add occupied
            end_bases = dict(current_bases)
            for b in bases_vacated:
                key = {"1B": "first", "2B": "second", "3B": "third"}[b]
                end_bases[key] = False
            for b in bases_occupied:
                key = {"1B": "first", "2B": "second", "3B": "third"}[b]
                end_bases[key] = True
            current_bases = dict(end_bases)
            at_bats.append({
                "inning": about.get("inning", 0),
                "half": about.get("halfInning", ""),
                "batter": matchup.get("batter", {}).get("fullName", ""),
                "batter_id": matchup.get("batter", {}).get("id", 0),
                "bat_side": matchup.get("batSide", {}).get("code", "R"),
                "pitcher": matchup.get("pitcher", {}).get("fullName", ""),
                "pitcher_id": matchup.get("pitcher", {}).get("id", 0),
                "event": result.get("event", ""),
                "description": result.get("description", ""),
                "rbi": result.get("rbi", 0),
                "pitches": len(pitches),
                "pitch_sequence": pitches,
                "runners": end_bases,
                "away_score": result.get("awayScore", 0),
                "home_score": result.get("homeScore", 0),
                "away_abbr": away_abbr,
                "home_abbr": home_abbr,
            })
        return jsonify({"plays": at_bats})
    except Exception as e:
        return jsonify({"plays": [], "error": str(e)})


@app.route("/api/game/<int:game_id>/live")
def game_live_feed(game_id):
    """Get live game feed with runners, count, and last pitch location."""
    try:
        import requests as req
        feed = req.get(f"https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live").json()
        game_status = feed.get("gameData", {}).get("status", {}).get("abstractGameState", "")
        if game_status == "Final":
            return jsonify({"available": False})
        linescore = feed.get("liveData", {}).get("linescore", {})
        plays = feed.get("liveData", {}).get("plays", {})

        # Runners
        offense = linescore.get("offense", {})
        runners = {
            "first": bool(offense.get("first")),
            "second": bool(offense.get("second")),
            "third": bool(offense.get("third")),
        }

        # Count
        count = {
            "balls": linescore.get("balls", 0),
            "strikes": linescore.get("strikes", 0),
            "outs": linescore.get("outs", 0),
        }

        # Current batter/pitcher
        batter_obj = offense.get("batter", {})
        batter = batter_obj.get("fullName", "")
        batter_id = batter_obj.get("id", 0)
        bat_side = plays.get("currentPlay", {}).get("matchup", {}).get("batSide", {}).get("code", "R")
        pitcher_info = linescore.get("defense", {}).get("pitcher", {})
        pitcher = pitcher_info.get("fullName", "")
        pitcher_id = pitcher_info.get("id", 0)

        # Batter's game stats from boxscore
        batter_stats = {}
        if batter_id:
            try:
                box_players = feed.get("liveData", {}).get("boxscore", {}).get("teams", {})
                for side in ("away", "home"):
                    p_data = box_players.get(side, {}).get("players", {}).get(f"ID{batter_id}", {})
                    if p_data:
                        bs = p_data.get("stats", {}).get("batting", {})
                        if bs:
                            batter_stats = {
                                "ab": bs.get("atBats", 0), "h": bs.get("hits", 0),
                                "r": bs.get("runs", 0), "rbi": bs.get("rbi", 0),
                                "hr": bs.get("homeRuns", 0), "bb": bs.get("baseOnBalls", 0),
                                "k": bs.get("strikeOuts", 0), "avg": bs.get("avg", ""),
                            }
                            break
            except Exception:
                pass

        # Last pitch location
        last_pitch = {}
        current_play = plays.get("currentPlay", {})
        play_events = current_play.get("playEvents", [])
        if play_events:
            last_event = play_events[-1]
            pitch_data = last_event.get("pitchData", {})
            coords = pitch_data.get("coordinates", {})
            last_pitch = {
                "x": coords.get("pX", 0),  # horizontal (-1.5 to 1.5 ft from center)
                "y": coords.get("pZ", 0),  # vertical (height in feet)
                "type": last_event.get("details", {}).get("type", {}).get("code", ""),
                "speed": last_event.get("pitchData", {}).get("startSpeed", 0),
                "description": last_event.get("details", {}).get("description", ""),
                "call": last_event.get("details", {}).get("call", {}).get("description", ""),
            }

        # Recent pitches for the at-bat
        pitches = []
        for ev in play_events:
            if ev.get("isPitch"):
                pd = ev.get("pitchData", {})
                c = pd.get("coordinates", {})
                ct = ev.get("count", {})
                pitches.append({
                    "x": c.get("pX", 0),
                    "y": c.get("pZ", 0),
                    "call": ev.get("details", {}).get("call", {}).get("code", ""),
                    "type": ev.get("details", {}).get("type", {}).get("code", ""),
                    "speed": pd.get("startSpeed", 0),
                    "strikes": ct.get("strikes", 0),
                    "balls": ct.get("balls", 0),
                })

        # Inning info
        inning = linescore.get("currentInning", 0)
        inning_half = linescore.get("inningHalf", "")

        # Score
        ls_teams = linescore.get("teams", {})
        away_score = ls_teams.get("away", {}).get("runs", 0)
        home_score = ls_teams.get("home", {}).get("runs", 0)
        game_teams = feed.get("gameData", {}).get("teams", {})
        away_abbr = game_teams.get("away", {}).get("abbreviation", "AWY")
        home_abbr = game_teams.get("home", {}).get("abbreviation", "HME")

        return jsonify({
            "available": True,
            "runners": runners,
            "count": count,
            "batter": batter,
            "batter_id": batter_id,
            "bat_side": bat_side,
            "pitcher": pitcher,
            "pitcher_id": pitcher_id,
            "batter_stats": batter_stats,
            "inning": inning,
            "inning_half": inning_half,
            "last_pitch": last_pitch,
            "pitches": pitches[-10:],
            "away_score": away_score,
            "home_score": home_score,
            "away_abbr": away_abbr,
            "home_abbr": home_abbr,
        })
    except Exception as e:
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/player/<int:player_id>/fielding")
def player_fielding(player_id):
    """Get fielding stats (season + career) split by position."""
    try:
        season = statsapi.player_stat_data(player_id, group="fielding", type="season")
        career = statsapi.player_stat_data(player_id, group="fielding", type="career")
        def parse(entries):
            out = []
            for s in entries:
                st = s.get("stats", {})
                pos = st.get("position", {})
                if pos.get("abbreviation") == "DH" or int(st.get("gamesPlayed", 0)) == 0:
                    continue
                out.append({
                    "position": pos.get("name", ""),
                    "pos_abbr": pos.get("abbreviation", ""),
                    "games": st.get("gamesPlayed", 0),
                    "gs": st.get("gamesStarted", 0),
                    "innings": st.get("innings", "0"),
                    "fielding_pct": st.get("fielding", ".000"),
                    "putouts": st.get("putOuts", 0),
                    "assists": st.get("assists", 0),
                    "errors": st.get("errors", 0),
                    "dp": st.get("doublePlays", 0),
                    "chances": st.get("chances", 0),
                    "rf_game": st.get("rangeFactorPerGame", "0"),
                    "rf_9": st.get("rangeFactorPer9Inn", "0"),
                    "throwing_errors": st.get("throwingErrors", 0),
                })
            return out
        return jsonify({
            "season": parse(season.get("stats", [])),
            "career": parse(career.get("stats", [])),
        })
    except Exception as e:
        return jsonify({"season": [], "career": [], "error": str(e)})


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
