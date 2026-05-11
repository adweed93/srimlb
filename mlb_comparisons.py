"""Dynamic player archetype detection and historical comparisons.

Instead of comparing every player to the same fixed records, this module:
1. Identifies what a player is good at (power, contact, speed, discipline, etc.)
2. Only shows comparisons relevant to their strengths
3. Uses archetype-specific historical counterparts verified from MLB API
"""

from mlb_records import get_records


def _get_record(key, field="record"):
    """Get a verified record value, with hardcoded fallback."""
    r = get_records()
    return r.get(key, {}).get(field)


# Archetype-specific comps are now pulled from get_records() at runtime
# These fallback dicts are only used if the cache fails
POWER_COMPS = None  # Loaded dynamically
CONTACT_COMPS = None
SPEED_COMPS = None
DISCIPLINE_COMPS = None
STRIKEOUT_PITCHER_COMPS = None
CONTROL_PITCHER_COMPS = None


def _comps():
    """Get all comparison data from verified records."""
    r = get_records()
    return {
        "power": {
            "hr": r.get("hr", {"record": 73, "holder": "Barry Bonds (2001)", "notable": []}),
            "rbi": r.get("rbi", {"record": 191, "holder": "Hack Wilson (1930)", "notable": []}),
            "slg": r.get("slg", {"record": .863, "holder": "Barry Bonds (2001)", "notable": []}),
        },
        "contact": {
            "avg": r.get("avg", {"record": .406, "holder": "Ted Williams (1941)", "notable": []}),
            "hits": r.get("hits", {"record": 262, "holder": "Ichiro Suzuki (2004)", "notable": []}),
            "doubles": r.get("doubles", {"record": 67, "holder": "Earl Webb (1931)", "notable": []}),
        },
        "speed": {
            "sb": r.get("sb", {"record": 130, "holder": "Rickey Henderson (1982)", "notable": []}),
        },
        "discipline": {
            "obp": r.get("obp", {"record": .609, "holder": "Barry Bonds (2004)", "notable": []}),
            "bb": {"record": 232, "holder": "Barry Bonds (2004)", "notable": [
                {"val": 170, "holder": "Babe Ruth (1923)"}, {"val": 148, "holder": "Ted Williams (1947)"}]},
        },
        "strikeout_pitch": {
            "k_season": r.get("k_season", {"record": 383, "holder": "Nolan Ryan (1973)", "notable": []}),
            "k9": r.get("k9", {"record": 13.41, "holder": "Chris Sale (2017)", "notable": []}),
        },
        "control_pitch": {
            "era": r.get("era", {"record": 1.12, "holder": "Bob Gibson (1968)", "notable": []}),
            "whip": r.get("whip", {"record": 0.737, "holder": "Pedro Martinez (2000)", "notable": []}),
            "wins": r.get("wins", {"record": 27, "holder": "Steve Carlton (1972)", "notable": []}),
        },
    }


def detect_hitter_archetype(stats, games):
    """Score a hitter's strengths and return their archetypes (can be multiple)."""
    archetypes = []
    hr = int(stats.get("homeRuns", 0))
    hits = int(stats.get("hits", 0))
    sb = int(stats.get("stolenBases", 0))
    bb = int(stats.get("baseOnBalls", 0))
    pa = int(stats.get("plateAppearances", 1) or 1)
    avg = float(stats.get("avg", "0") or "0")
    slg = float(stats.get("slg", "0") or "0")
    obp = float(stats.get("obp", "0") or "0")
    k_rate = int(stats.get("strikeOuts", 0)) / pa * 100 if pa else 0
    bb_rate = bb / pa * 100 if pa else 0

    hr_pace = (hr / games) * 162
    sb_pace = (sb / games) * 162
    hits_pace = (hits / games) * 162

    # Power: high HR pace or high SLG
    if hr_pace >= 30 or slg >= .500:
        archetypes.append("power")
    # Contact: high AVG or high hit pace, low K rate
    if avg >= .290 or (hits_pace >= 180 and k_rate <= 20):
        archetypes.append("contact")
    # Speed: high SB pace
    if sb_pace >= 25:
        archetypes.append("speed")
    # Discipline: high BB rate or OBP
    if bb_rate >= 12 or obp >= .380:
        archetypes.append("discipline")

    # If nothing stands out, pick their best trait
    if not archetypes:
        scores = {"power": hr_pace / 40, "contact": avg / .300, "speed": sb_pace / 30, "discipline": bb_rate / 12}
        archetypes.append(max(scores, key=scores.get))

    return archetypes


def detect_pitcher_archetype(stats, games):
    """Score a pitcher's strengths."""
    archetypes = []
    era = float(stats.get("era", "99") or "99")
    k = int(stats.get("strikeOuts", 0))
    whip = float(stats.get("whip", "99") or "99")
    k9 = float(stats.get("strikeoutsPer9Inn", "0") or "0")
    bb9 = float(stats.get("walksPer9Inn", "99") or "99")

    if k9 >= 9.5 or (k / max(games, 1)) >= 6:
        archetypes.append("strikeout")
    if era <= 3.20 or whip <= 1.10:
        archetypes.append("control")
    if bb9 <= 2.0 and games > 5:
        archetypes.append("control")

    if not archetypes:
        archetypes.append("strikeout" if k9 >= 8 else "control")

    return list(set(archetypes))


def get_season_comparisons(stats, group, games, thresholds=None):
    """Generate dynamic anomalies and comparisons based on player archetype."""
    anomalies = []
    comparisons = []

    if games <= 20:
        return anomalies, comparisons

    c = _comps()
    POWER_COMPS = c["power"]
    CONTACT_COMPS = c["contact"]
    SPEED_COMPS = c["speed"]
    DISCIPLINE_COMPS = c["discipline"]
    STRIKEOUT_PITCHER_COMPS = c["strikeout_pitch"]
    CONTROL_PITCHER_COMPS = c["control_pitch"]

    if group == "hitting":
        archetypes = detect_hitter_archetype(stats, games)
        hr = int(stats.get("homeRuns", 0))
        avg = float(stats.get("avg", "0") or "0")
        sb = int(stats.get("stolenBases", 0))
        bb = int(stats.get("baseOnBalls", 0))
        hits = int(stats.get("hits", 0))
        doubles = int(stats.get("doubles", 0))
        slg = float(stats.get("slg", "0") or "0")
        obp = float(stats.get("obp", "0") or "0")
        ops = float(stats.get("ops", "0") or "0")
        rbi = int(stats.get("rbi", 0))
        pa = int(stats.get("plateAppearances", 1) or 1)

        hr_pace = (hr / games) * 162
        hits_pace = (hits / games) * 162
        rbi_pace = (rbi / games) * 162
        sb_pace = (sb / games) * 162
        doubles_pace = (doubles / games) * 162
        bb_pace = (bb / games) * 162


        # --- POWER archetype ---
        if "power" in archetypes:
            if hr_pace >= 55:
                nugget = f"Would surpass Aaron Judge's 62 (2022)" if hr_pace >= 62 else "Only 7 players in MLB history have hit 55+ in a season"
                anomalies.append({"msg": f"On pace for {int(hr_pace)} HRs — RECORD PACE", "level": "alltime", "nugget": nugget})
            elif hr_pace >= 40:
                anomalies.append({"msg": f"On pace for {int(hr_pace)} HRs", "level": "alert", "nugget": "A 40+ HR season has only happened ~30 times since 2010"})
            if hr_pace >= 35:
                hr_rec = POWER_COMPS["hr"]
                comparisons.append({"stat": "HR Pace", "current": str(int(hr_pace)), "record": str(hr_rec["record"]), "holder": hr_rec["holder"], "pct": round(hr_pace / hr_rec["record"] * 100)})
                for n in hr_rec.get("notable", []):
                    if hr_pace >= n["val"] * 0.6:
                        comparisons.append({"stat": "", "current": "", "record": str(n["val"]), "holder": n["holder"], "pct": round(hr_pace / n["val"] * 100)})
                        break

            if rbi_pace >= 140:
                nugget = "Hasn't been done since Manny Ramirez drove in 165 in 1999" if rbi_pace >= 160 else "Last 140+ RBI season: Albert Pujols (2006)"
                anomalies.append({"msg": f"On pace for {int(rbi_pace)} RBI", "level": "alltime" if rbi_pace >= 160 else "alert", "nugget": nugget})
                rbi_rec = POWER_COMPS["rbi"]
                comparisons.append({"stat": "RBI Pace", "current": str(int(rbi_pace)), "record": str(rbi_rec["record"]), "holder": rbi_rec["holder"], "pct": round(rbi_pace / rbi_rec["record"] * 100)})

            if slg >= .650:
                anomalies.append({"msg": f"{slg:.3f} SLG — historic power", "level": "alltime", "nugget": "Only Bonds, Ruth, and Williams have posted .700+ SLG in a full season"})
                slg_rec = POWER_COMPS["slg"]
                comparisons.append({"stat": "SLG", "current": f"{slg:.3f}", "record": f"{slg_rec['record']:.3f}", "holder": slg_rec["holder"], "pct": round(slg / slg_rec["record"] * 100)})
            elif slg >= .580:
                anomalies.append({"msg": f"{slg:.3f} SLG — elite power", "level": "alert", "nugget": "A .580+ SLG typically ranks top-5 in baseball"})

        # --- CONTACT archetype ---
        if "contact" in archetypes:
            if avg >= .370:
                nugget = "No one has finished above .400 since Ted Williams in 1941" if avg >= 0.400 else "Last .370+ season: Tony Gwynn (.394 in 1994)"
                anomalies.append({"msg": f"Batting .{int(avg*1000)} — ALL-TIME TERRITORY", "level": "alltime", "nugget": nugget})
            elif avg >= .330:
                anomalies.append({"msg": f"Batting .{int(avg*1000)} — elite contact", "level": "alert", "nugget": "Only 5 players have hit .340+ in a season since 2000"})
            if avg >= .310:
                avg_rec = CONTACT_COMPS["avg"]
                comparisons.append({"stat": "AVG", "current": f".{int(avg*1000)}", "record": f".{int(avg_rec['record']*1000)}", "holder": avg_rec["holder"], "pct": round(avg / avg_rec["record"] * 100)})
                for n in avg_rec.get("notable", []):
                    if avg >= n["val"] * 0.85:
                        comparisons.append({"stat": "", "current": "", "record": f".{int(n['val']*1000)}", "holder": n["holder"], "pct": round(avg / n["val"] * 100)})
                        break

            if hits_pace >= 220:
                if hits_pace >= 240:
                    anomalies.append({"msg": f"On pace for {int(hits_pace)} hits — Ichiro territory", "level": "alltime", "nugget": "Only Ichiro (262) and George Sisler (257) have reached 240+"})
                else:
                    anomalies.append({"msg": f"On pace for {int(hits_pace)} hits", "level": "alert", "nugget": "A 220+ hit season is rare — happens maybe once every 2-3 years"})
                hits_rec = CONTACT_COMPS["hits"]
                comparisons.append({"stat": "Hits Pace", "current": str(int(hits_pace)), "record": str(hits_rec["record"]), "holder": hits_rec["holder"], "pct": round(hits_pace / hits_rec["record"] * 100)})

            if doubles_pace >= 50:
                anomalies.append({"msg": f"On pace for {int(doubles_pace)} doubles", "level": "alert", "nugget": "50+ doubles is a rare gap-power achievement — last done by Freddie Freeman (2023)"})
                dbl_rec = CONTACT_COMPS["doubles"]
                comparisons.append({"stat": "2B Pace", "current": str(int(doubles_pace)), "record": str(dbl_rec["record"]), "holder": dbl_rec["holder"], "pct": round(doubles_pace / dbl_rec["record"] * 100)})

        # --- SPEED archetype ---
        if "speed" in archetypes:
            if sb_pace >= 80:
                anomalies.append({"msg": f"On pace for {int(sb_pace)} SB — historic speed", "level": "alltime", "nugget": "Only Henderson (130, 108) and Vince Coleman (110, 107, 109) have stolen 80+ in a season"})
            elif sb_pace >= 50:
                anomalies.append({"msg": f"On pace for {int(sb_pace)} SB", "level": "alert", "nugget": "The stolen base leader has averaged ~45 since 2015"})
            if sb_pace >= 30:
                sb_rec = SPEED_COMPS["sb"]
                comparisons.append({"stat": "SB Pace", "current": str(int(sb_pace)), "record": str(sb_rec["record"]), "holder": sb_rec["holder"], "pct": round(sb_pace / sb_rec["record"] * 100)})
                for n in sb_rec.get("notable", []):
                    if sb_pace >= n["val"] * 0.5:
                        comparisons.append({"stat": "", "current": "", "record": str(n["val"]), "holder": n["holder"], "pct": round(sb_pace / n["val"] * 100)})
                        break

        # --- DISCIPLINE archetype ---
        if "discipline" in archetypes:
            if obp >= .450:
                anomalies.append({"msg": f"{obp:.3f} OBP — ALL-TIME TERRITORY", "level": "alltime", "nugget": "Only Bonds, Williams, and Ruth have posted .450+ OBP in a full season (modern era)"})
                obp_rec = DISCIPLINE_COMPS["obp"]
                comparisons.append({"stat": "OBP", "current": f"{obp:.3f}", "record": f"{obp_rec['record']:.3f}", "holder": obp_rec["holder"], "pct": round(obp / obp_rec["record"] * 100)})
            elif obp >= .400:
                anomalies.append({"msg": f"{obp:.3f} OBP — elite plate discipline", "level": "alert", "nugget": "Fewer than 5 players per year finish above .400 OBP"})
                obp_rec = DISCIPLINE_COMPS["obp"]
                comparisons.append({"stat": "OBP", "current": f"{obp:.3f}", "record": f"{obp_rec['record']:.3f}", "holder": obp_rec["holder"], "pct": round(obp / obp_rec["record"] * 100)})

            if bb_pace >= 100:
                anomalies.append({"msg": f"On pace for {int(bb_pace)} walks", "level": "alert", "nugget": "100+ walks in a season is elite — only ~5 players do it per year"})
                bb_rec = DISCIPLINE_COMPS["bb"]
                comparisons.append({"stat": "BB Pace", "current": str(int(bb_pace)), "record": str(bb_rec["record"]), "holder": bb_rec["holder"], "pct": round(bb_pace / bb_rec["record"] * 100)})

        # --- Universal OPS check (all archetypes) ---
        if ops >= 1.100:
            anomalies.append({"msg": f"{ops:.3f} OPS — ALL-TIME TERRITORY", "level": "alltime", "nugget": "Only Bonds, Ruth, Williams, and Gehrig have posted a full-season OPS above 1.100"})
        elif ops >= 1.000:
            anomalies.append({"msg": f"{ops:.3f} OPS — elite", "level": "alert", "nugget": "Fewer than 5 players per season typically finish above 1.000 OPS"})

    elif group == "pitching" and games > 5:
        archetypes = detect_pitcher_archetype(stats, games)
        era = float(stats.get("era", "99") or "99")
        k = int(stats.get("strikeOuts", 0))
        whip = float(stats.get("whip", "99") or "99")
        k9 = float(stats.get("strikeoutsPer9Inn", "0") or "0")
        w = int(stats.get("wins", 0))
        k_pace = (k / games) * 162
        w_pace = (w / games) * 162

        # --- STRIKEOUT pitcher ---
        if "strikeout" in archetypes:
            if k_pace >= 300:
                anomalies.append({"msg": f"On pace for {int(k_pace)} K — historic", "level": "alltime", "nugget": "Only Ryan (383), Koufax (382), and R. Johnson (372) have reached 300+ K"})
            elif k_pace >= 250:
                anomalies.append({"msg": f"On pace for {int(k_pace)} K", "level": "alert", "nugget": "A 250+ K season is ace-level — happens ~5 times per year"})
            if k_pace >= 200:
                k_rec = STRIKEOUT_PITCHER_COMPS["k_season"]
                comparisons.append({"stat": "K Pace", "current": str(int(k_pace)), "record": str(k_rec["record"]), "holder": k_rec["holder"], "pct": round(k_pace / k_rec["record"] * 100)})
                for n in k_rec.get("notable", []):
                    if k_pace >= n["val"] * 0.7:
                        comparisons.append({"stat": "", "current": "", "record": str(n["val"]), "holder": n["holder"], "pct": round(k_pace / n["val"] * 100)})
                        break

            if k9 >= 13.0:
                anomalies.append({"msg": f"{k9:.1f} K/9 — historic dominance", "level": "alltime", "nugget": "Full-season K/9 record: Gerrit Cole (13.8 in 2019)"})
                k9_rec = STRIKEOUT_PITCHER_COMPS["k9"]
                comparisons.append({"stat": "K/9", "current": f"{k9:.1f}", "record": f"{k9_rec['record']:.1f}", "holder": k9_rec["holder"], "pct": round(k9 / k9_rec["record"] * 100)})
            elif k9 >= 11.0:
                anomalies.append({"msg": f"{k9:.1f} K/9 — elite", "level": "alert", "nugget": "11+ K/9 puts you in the top 1% of all starters historically"})

        # --- CONTROL pitcher ---
        if "control" in archetypes:
            if era <= 1.80:
                anomalies.append({"msg": f"{era:.2f} ERA — ALL-TIME TERRITORY", "level": "alltime", "nugget": "Last sub-2.00 ERA: Jacob deGrom (1.70 in 2018)"})
            elif era <= 2.50:
                anomalies.append({"msg": f"{era:.2f} ERA — elite", "level": "alert", "nugget": "Only 2-3 qualified starters finish below 2.50 each season"})
            if era <= 3.00:
                era_rec = CONTROL_PITCHER_COMPS["era"]
                comparisons.append({"stat": "ERA", "current": f"{era:.2f}", "record": f"{era_rec['record']:.2f}", "holder": era_rec["holder"], "pct": round((1 - era/4.50) / (1 - era_rec["record"]/4.50) * 100)})
                for n in era_rec.get("notable", []):
                    if era <= n["val"] * 1.5:
                        comparisons.append({"stat": "", "current": "", "record": f"{n['val']:.2f}", "holder": n["holder"], "pct": 0})
                        break

            if whip <= 0.85 and games > 8:
                anomalies.append({"msg": f"{whip:.2f} WHIP — ALL-TIME TERRITORY", "level": "alltime", "nugget": "Lowest full-season WHIP: Pedro Martinez (0.737 in 2000)"})
                whip_rec = CONTROL_PITCHER_COMPS["whip"]
                comparisons.append({"stat": "WHIP", "current": f"{whip:.3f}", "record": f"{whip_rec['record']:.3f}", "holder": whip_rec["holder"], "pct": round((1.50 - whip) / (1.50 - whip_rec["record"]) * 100)})
            elif whip <= 1.00 and games > 8:
                anomalies.append({"msg": f"{whip:.2f} WHIP — elite", "level": "alert", "nugget": "Sub-1.00 WHIP is historically rare — only ~20 qualified seasons ever"})

            if w_pace >= 22 and games > 10:
                anomalies.append({"msg": f"On pace for {int(w_pace)} wins", "level": "alert", "nugget": "Last 20+ win season: Justin Verlander (21 in 2011)"})
                win_rec = CONTROL_PITCHER_COMPS["wins"]
                comparisons.append({"stat": "Win Pace", "current": str(int(w_pace)), "record": str(win_rec["record"]), "holder": win_rec["holder"], "pct": round(w_pace / win_rec["record"] * 100)})

    return anomalies, comparisons
