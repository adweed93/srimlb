# MLB Dashboard Project Summary - May 10, 2026

## User
- GitHub: adweed93
- Email: ausdweed@gmail.com
- Favorites: Baltimore Orioles (ID: 110), Gunnar Henderson (ID: 683002), Cal Raleigh (ID: 663728)

## What We Built

### 1. MLB MCP Server Setup
- Cloned etweisberg/mlb-mcp to C:\Users\Austin\mlb-mcp
- Installed uv (C:\Users\Austin\.local\bin\uv.exe) and all dependencies
- Python venv: C:\Users\Austin\mlb-mcp\.venv\Scripts\python.exe
- Provides: statsapi, pybaseball, statcast, fangraphs, baseball reference

### 2. Desktop App (tkinter)
- File: C:\Users\Austin\mlb_dashboard.py
- Features: favorites sidebar, live games (30s refresh), player/team dashboards, notifications with gold all-time alerts, startup synopsis after 6+ hours away
- Run: C:\Users\Austin\mlb-mcp\.venv\Scripts\python.exe C:\Users\Austin\mlb_dashboard.py

### 3. Web App (Flask) - Deployed to Render
- Local files: C:\Users\Austin\srimlb\
- GitHub: https://github.com/adweed93/srimlb
- Live URL: https://srimlb.onrender.com
- Free tier on Render (auto-deploys from GitHub)

### 4. Web App Features
- ESPN/theScore-inspired dark UI with bottom tab navigation
- 5 tabs: Scores, Search, Favorites, Stats, Alerts
- Live scoreboard with 30s auto-refresh, favorite team starring
- Player search (any MLB player)
- Player dashboard with 4 filter views:
  - 2026 Season (full stats: slash line, counting, discipline/speed for batters; core, batted ball, efficiency for pitchers)
  - Career totals
  - Year by Year history
  - Statcast (exit velo, bat speed, launch angle, barrel%, hard hit%, sprint speed, xBA, xSLG, pitch velo, spin rate, pitch mix)
- Anomaly detection with historical nuggets (e.g., "hasn't been done since X player in Y season")
- Historical record comparisons with progress bars (HR, AVG, Hits, RBI, SB, ERA, K, Wins)
- Last game stats with green highlights for standout performances
- Recent team game log with W/L badges
- Gold (alltime) vs blue (alert) anomaly styling
- Team dashboard: record, division rank, GB, live game status, recent results

### 5. Notifications System
- File: C:\Users\Austin\srimlb\mlb_notifications.py
- Checks every 60s for anomalous performances
- Tracks seen events to avoid duplicates (mlb_notifications.json)
- Categories: alert (blue) and alltime (gold)

### 6. Dynamic Thresholds
- File: C:\Users\Austin\srimlb\mlb_thresholds.py
- Refreshes daily from current season MLB Stats API league leaders
- Falls back to pybaseball (FanGraphs) or hardcoded values
- Cached in mlb_thresholds_cache.json

### 7. Kiro Agent: baseball-guru
- Config: C:\Users\Austin\.kiro\agents\baseball-guru.json
- Prompt: C:\Users\Austin\.kiro\prompts\baseball-guru.txt
- Keyboard shortcut: Ctrl+Shift+B
- Connected to mlb-mcp MCP server
- Switch with: /agent baseball-guru

### 8. Infrastructure
- flyctl installed at C:\Users\Austin\.fly\bin\flyctl.exe (Fly.io app was deleted - switched to Render)
- GitHub CLI installed and authenticated as adweed93
- Render: free Hobby plan, auto-deploys on push to master

## Key Technical Details
- The app calls MLB Stats API directly via the statsapi Python library (free, no tokens)
- pybaseball provides Statcast data from Baseball Savant
- No MCP server is used at runtime - it's all direct API calls
- Favorites persist in mlb_favorites.json (shared between desktop and web app locally)
- Thresholds computed from real data: 99th percentile = anomalous, 99.9th = all-time

## Current Season Context (as of May 10, 2026)
- Gunnar Henderson: .204 AVG, .683 OPS, 9 HR in 39 games (slumping)
- Adley Rutschman: .318 AVG, .966 OPS, 5 HR, 9 2B in 24 games (hot)
- Orioles: 18-21, 3rd in AL East
- Yankees 26-14, Rays 25-13 lead AL East
- 2025 HR leaders used for thresholds: Cal Raleigh 60, Schwarber 56, Ohtani 55, Judge 53

## Future Ideas
- Add team search (currently only player search in the Search tab)
- Add player comparison view (side by side)
- Add spray charts / heat maps from Statcast data
- Add fantasy baseball projections
- Add game-day notifications via push (would need a service worker)

## Session: May 10, 2026 (Morning)

### Bug Fix: Live Tab Hijacking Player Dashboard
- **Problem**: When viewing a player's stat dashboard (Season, Career, etc.), the page would auto-switch to the Live tab every 15 seconds
- **Root Cause**: `_liveRefreshTimer` from the Live filter view was never cleared when switching to other filter tabs. It kept firing `renderPlayerLive()` which overwrote the stats panel content.
- **Fix** (in `templates/dashboard.html`):
  - `loadPlayerFilter()` now clears `_liveRefreshTimer` when switching to any non-live filter
  - `loadPlayer()` clears all three timers (`_liveRefreshTimer`, `_teamRefreshTimer`, `_boxRefreshTimer`) on entry
  - `loadTeam()` and `loadBoxScore()` also clear all other timers
  - All refresh interval callbacks now guard with `if (document.querySelector('#stats.active'))` so they only update when the stats panel is visible
- **Commit**: `302bdce`

### Performance: Faster Player Dashboard Loading
- **Problem**: Player dashboard was slow due to 3-4 sequential MLB Stats API calls
- **Fix** (in `mlb_web.py`):
  - Added `ThreadPoolExecutor` to run game log fetch and team schedule fetch in parallel
  - Added in-memory TTL cache (`_cached()` helper):
    - Player season stats: 60s TTL
    - Player game log: 60s TTL
    - Team schedule: 120s TTL
    - Team lookup: 300s TTL
  - Repeat visits within cache window are instant; first load is ~2x faster from parallelism
- **Commit**: `53ec387`

### Feature: Team Roster & Lineup
- **Added** `/api/team/<id>/roster` endpoint in `mlb_web.py`
  - Returns full active roster grouped by position type (Pitcher, Catcher, Infielder, Outfielder)
  - Returns batting lineup from current or most recent game
  - Uses `statsapi.get("team_roster")` for structured roster data
  - Uses game boxscore `battingOrder` for lineup
- **Added** `loadTeamRoster()` in `dashboard.html`
  - Loads async after main team data (doesn't block initial render)
  - Shows numbered batting order (1-9) with player photos
  - Shows full roster grouped by position with jersey numbers
  - All players are clickable → loads their full stat dashboard
- **Commit**: `76f0c38`

### Restyle: "Neon Dugout" Theme
- True black background (`#000`) with dark charcoal cards (`#111`)
- Electric green (`#00ff87`) primary accent — stat numbers, active nav, buttons
- Hot pink (`#ff006e`) for alerts/live indicators
- Bright gold (`#ffbe0b`) for all-time records
- Monospace font (`SF Mono`/`Fira Code`) for all stat values and timestamps
- Sharp corners (6px border-radius) instead of rounded cards
- Uppercase labels with tight letter-spacing throughout
- Neon glow effects: text-shadow on active nav, box-shadow on W/L badges, progress bar glow
- Search input gets green glow on focus
- **Commit**: `ae54d5d`

### Feature: Fuzzy Search for Players and Teams
- **Player search** (`/api/search/player`): Now tries `statsapi.lookup_player()` first, falls back to `pybaseball.playerid_lookup(fuzzy=True)` for typo tolerance (e.g., "Otta" → "Ohtani")
- **Team search** (`/api/search/team`): Now tries `statsapi.lookup_team()` first, falls back to `difflib.get_close_matches()` against all MLB team names, abbreviations, and short names
- **Commits**: `11af303`, `48cb781`

### Feature: Anomalies & Comparisons on Career and Year-by-Year Views
- **Career view** now includes:
  - Anomaly banners for career milestones (500 HR Club, 3000 Hits, 300 Wins, career .300+ AVG, sub-3.00 ERA, etc.)
  - Progress bars comparing career totals against all-time records (e.g., "Career HR: 555 — 73% of Barry Bonds' 762")
- **Year-by-year view** now includes:
  - Per-season flags when selecting a standout year (50-HR, .350+ AVG, sub-2.00 ERA, 300-K, 20-win seasons)
  - Each flag has a contextual nugget explaining historical significance
- All thresholds are time-frame-appropriate (career vs single-season benchmarks)
- **Commit**: `48bb236`

### Feature: HOF Career-Pace Comparisons
- Career view shows "HOF Pace Check" section comparing player's stats to Hall of Famers at the same career point
- Curated cumulative data for 9 hitters (Bonds, Aaron, Mays, Ruth, Mantle, Williams, Trout, Griffey Jr., Pujols) and 8 pitchers (Ryan, R. Johnson, Pedro, Maddux, Kershaw, Koufax, Gibson, W. Johnson)
- Bracket-matched at 3/5/7/10/15 seasons — young players get compared to where greats were at that same stage
- Shows green (ahead) or blue (behind) with exact differential
- Only shows comparisons where player is within 75% of the HOF great's pace
- **Commit**: `7ddc323`

### Feature: Career Milestones Checklist
- Career view shows up to 10 best career milestones with ✓ checkmarks
- Hitter milestones: HR (100-700), Hits (1000-3000), RBI (500-1500), Runs (1000-1500), SB (100-500), Doubles (400-600), Walks (1000-1500), Career AVG (.300+/.320+), Total Bases (3000-5000)
- Pitcher milestones: K (1000-4000), Wins (100-300), Saves (200-400), Shutouts (20-40), CG (30-100), IP (2000-3000), Career ERA
- Notes when milestones were reached quickly (e.g., "Reached in 5 seasons — blazing fast start")
- **Commit**: `4f77705`

### Feature: Red Flags Section (Bad Stats with Historical Comparisons)
- Added a separate "🚩 Red Flags" section alongside "🔥 Anomalies" on all three views (Season, Career, Year-by-Year)
- **Season red flags**: sub-.200 AVG, sub-.600 OPS, 35%+ K rate, 6.00+ ERA, 1.60+ WHIP, 5.0+ BB/9, 2.0+ HR/9
- **Career red flags**: sub-.230 career AVG, sub-.680 OPS, 28%+ career K rate, 2000+ career K, 4.50+ ERA, 1.40+ WHIP, sub-.450 win%, 200+ losses
- **Year-by-year red flags**: same single-season thresholds applied per year
- Each red flag includes historical comparison nuggets (e.g., "Chris Davis hit .168 in 2018 — the worst ever for a qualified hitter")
- Two severity levels: `terrible` (🚨 red) and `bad` (⚠️ orange) with distinct CSS styling
- **Commits**: `3738c61`, `909aab9`, `ccf2b4c`


### Bugfix: Pitcher Stats Showing Batting Data
- **Problem**: Pitchers were displaying their batting stats instead of pitching stats on all views
- **Root Cause**: `statsapi.player_stat_data()` returns both hitting and pitching stat groups. Code checked `hitting` first with a `break`, so pitchers always got batting stats.
- **Fix**: All three endpoints (season, career, yearByYear) now check `info.get("position") == "P"` and prioritize the `pitching` group, with `hitting` as fallback
- **Commit**: `39d58da`

### Bugfix: Year-by-Year Duplicate/Unordered Seasons
- **Problem**: Dropdown had duplicate years and out-of-order entries
- **Root Cause**: Mid-season trades create multiple entries per year; API doesn't guarantee order
- **Fix**: Seasons sorted chronologically; mid-season trade splits kept separate with unique `_key` identifiers
- **Commits**: `bb20aed`, `1d5c743`

### Enhancement: Pitcher Stat Dashboard (4 Sections)
- Expanded pitcher layout to match batter dashboard depth:
  - **Core**: ERA, W-L, WHIP, IP, G, GS, W%, ER
  - **Strikeouts & Walks**: K, BB, K/BB, K/9, BB/9, HBP
  - **Batted Ball**: H, HR, BAA, OBP Against, H/9, HR/9
  - **Durability & Extras**: CG, SHO, SV, HLD, WP, BF
- Applied to both the season view inline rendering and the shared `buildStatDashboard()` function (career + yearByYear)
- **Commit**: `d65f831`

### Enhancement: Year-by-Year Team Context
- Dropdown now shows team name per entry: `2022 — Los Angeles Angels`
- Mid-season trades show as separate selectable entries
- Team logo (from mlbstatic.com) displays in the stat header per selection
- Anomalies and red flags keyed to specific team entry (not just year)
- **Commits**: `506b6c5`, `1d5c743`

### Feature: README.md
- Full project documentation added to GitHub
- Covers all features, tech stack, project structure, how to run locally, dependencies, and historical comparison data sources
- **Commit**: `e468470`


### Feature: Upcoming Games on Scores Page
- Scores page now shows "Coming Up Next" — the next 3 upcoming games from future days with date and game time
- "📅 See All Upcoming (2 Weeks)" button expands to full 14-day schedule grouped by date
- Each upcoming game card shows team logos, names, date, and local game time
- Favorite teams get ★ FAV badge
- New `/api/upcoming` endpoint returns all scheduled games for next 14 days
- **Commit**: `088418a`

### Feature: Upcoming Games on Team Page
- Team page now has "Upcoming Games" section showing next 3 games with opponent logo, home/away, date, and time
- "Show All X Games ▼" button expands to reveal full upcoming schedule
- Each entry: vs/@ badge, opponent name, date, time, opponent team logo
- **Commit**: `602de7a`


### Bugfix: Box Score Endpoint Returning Empty Data
- **Problem**: Clicking any game to view its box score showed empty tables — no batters or pitchers displayed
- **Root Cause**: `statsapi.boxscore_data()` returns `awayBatters`/`homeBatters`/`awayPitchers`/`homePitchers` as a list of dicts (with a header row where `personId=0`). The code incorrectly treated them as a list of player IDs and tried to look them up in a separate dict (which didn't exist), so every lookup returned `None`.
- **Fix**: Iterate the list directly, skip entries where `personId == 0` (header rows), and read stats from each dict in the list.
- **Commit**: `475fb1b`


### Enhancement: Live Diamond & Strike Zone in Box Score
- Box score view now shows a **live diamond graphic** with runner positions (lit green when occupied) for in-progress games
- **Ball/Strike/Out indicators** (colored dots: green=balls, red=strikes, orange=outs)
- **Current matchup** displayed: batter name vs pitcher name, inning/half
- **Strike zone SVG** showing all pitches from the current at-bat with color coding:
  - Red = called strike, Orange = swinging strike, Green = ball, Blue = in play
  - Last pitch highlighted with white border and larger dot
  - 9-zone grid overlay for reference
  - Pitch speed and call description below the zone
- Only appears for live games (gracefully hidden for final games via try/catch)
- Uses existing `/api/game/<id>/live` endpoint (MLB live feed API)
- Auto-refreshes with the 15s box score timer
- **Commit**: `3451c20`


## Session: May 10, 2026 (Night)

### Bugfix: Live Diamond & Strike Zone Not Showing
- **Problem**: The diamond/strike zone never appeared on live games
- **Root Cause**: Backend used `statsdata.mlb.com` (doesn't resolve) instead of `statsapi.mlb.com`
- **Fix**: Changed URL in `/api/game/<id>/live` endpoint
- **Commit**: `eaeb3ba`

### Feature: Demo Mode for Diamond + Strike Zone
- Added `/api/game/demo/live` and `/api/game/demo/boxscore` endpoints with fake data
- Small gold "⚾ Demo" button on Scores tab top-right to preview the full box score view
- Shows: Orioles vs Yankees, runners on 1st/2nd, Gunnar vs Cole, 5 pitches plotted
- **Commit**: `9a62255`

### Enhancement: Pitch Velocity & Type in Strike Zone
- Backend now sends `speed` and `type` (pitch type code) for each pitch
- Strike zone dots are numbered (1, 2, 3...)
- Pitch sequence log below zone shows: pitch number, type (FF/SL/CH), velocity, result
- Last pitch bolded in the log
- **Commit**: `33b1219`

### Feature: Defense Tab
- New "🧤 Defense" filter tab on player dashboard (for all players)
- `/api/player/<id>/fielding` endpoint returns season + career fielding stats split by position
- Each position card shows: FLD%, G, GS, TC, E, TE (Core) and PO, A, DP, RF/G, RF/9 (Range & Plays)
- DH entries filtered out, green highlights on .980+ FLD% and 0 errors
- **Commit**: `75f09ca`

### Enhancement: Dynamic Archetype-Based Comparisons
- **New file**: `mlb_comparisons.py` — replaces fixed RECORDS dict with archetype detection
- Hitter archetypes: power (HR pace/SLG), contact (AVG/hit pace), speed (SB pace), discipline (BB%/OBP)
- Pitcher archetypes: strikeout (K/9), control (ERA/WHIP)
- Players can have multiple archetypes — only shows comparisons relevant to their strengths
- A speed guy gets compared to Henderson/Coleman, a power hitter to Bonds/Judge
- **Commit**: `f19e85a`

### Enhancement: API-Verified Historical Records
- **New file**: `mlb_records.py` — fetches verified records from MLB Stats API
- Queries `league_leaders` for record-setting seasons (2001 HR, 1968 ERA, 1973 K, 2004 Hits, etc.)
- Cached in `mlb_records_cache.json`, refreshes weekly
- Hardcoded fallbacks for pre-1960 stats where API is unreliable (AVG .406, RBI 191, etc.)
- **Commit**: `8949021`

### Bugfix: Player Live Tab Broken
- **Problem**: Live tab never showed player's in-game stats, and "next game" was always empty
- **Root Cause 1**: Boxscore parsing iterated `awayBatters` as IDs instead of dicts with `personId`
- **Root Cause 2**: `statsapi.schedule(team=id)` only returns today's games — no future lookup
- **Fix**: Correct boxscore parsing (same fix as box score endpoint), look ahead 7 days for next game
- **Commit**: `a41b879`

### Enhancement: League Rankings
- New "📊 League Rankings" section on season dashboard
- `_get_player_rankings()` helper queries `league_leaders` for top-30 in player's league (AL/NL)
- Shows stats where player ranks top-15 with medals: 🥇 1st, 🥈 2nd, 🥉 3rd
- AL teams determined by hardcoded team ID set
- **Commit**: `d8d9d45`

### Enhancement: Games-Played-Based Insights
- Insights now include per-game rates and games-played context instead of generic statements
- Examples: "9 HR in 40 games (0.23/game)", "4.3 K/BB ratio — 56 K vs 13 BB", "5 SB (83% success)"
- Sample size awareness: "Small sample — could normalize" vs "Sustained slump"
- Pitchers: IP/start, K/start, baserunners per 9 IP, W-L context
- Shows 4 insights instead of 3
- **Commit**: `d8d9d45`

### Enhancement: Prefetch Favorites on Page Load
- Client-side `_playerCache` with 60s TTL
- 500ms after page load, fetches `/api/player/<id>` for first 5 favorite players in background
- `loadPlayer()` checks cache first — instant render if prefetched
- **Commit**: `dcc3582`

### UI: Live Tab First + Medals on Stat Cells
- Live tab moved to leftmost position in filter tabs
- Stat cells show medal emoji (🥇🥈🥉) next to the value if player is top-3 in their league
- Works for: AVG, OPS, HR, R, RBI, SB (hitters) and ERA, W-L, WHIP, K (pitchers)
- **Commits**: `ce21e2a`, `a6d6938`

### Architecture Notes
- Historical records: hybrid approach — API-verified where reliable, hardcoded for pre-1960
- Dynamic thresholds (`mlb_thresholds.py`): calibrated from current season leaders, refreshed daily
- Rankings: live queries to `league_leaders` with `leagueId` for AL/NL specificity
- Performance: prefetch + client cache + server TTL cache = near-instant repeat visits
- All comparison data flows: `mlb_records.py` → `mlb_comparisons.py` → `mlb_web.py` → frontend


## Session: May 11, 2026 (Late Night continued)

### Feature: Game Preview Page
- Clicking any upcoming game card opens a full preview page
- `/api/game/<id>/preview` endpoint returns: probable pitchers with season stats, projected lineups (from last game), series history (last 60 days), injuries (IL data), weather (WeatherAPI), odds (ESPN/DraftKings)
- All players in preview are clickable → opens their dashboard
- Series history shows win/loss record and individual game scores (clickable for box scores)
- **Commits**: `9a55f3b`, `8dfd18c`, `c376ae2`

### Feature: Live Scores BSO Tracker
- Scores page shows Ball/Strike/Out colored dots for live games (green/red/orange)
- Game times shown for upcoming/scheduled games (local time format)
- Backend fetches linescore for live games to get B/S/O data
- **Commit**: `03449db`

### Feature: Scores Page Navigation Tabs
- Three tabs at top: **Past | Today | Upcoming**
- Past: All final games from last 2 weeks grouped by date
- Today: Live games (with BSO), upcoming today, finals, coming up next preview
- Upcoming: Full 2-week future schedule grouped by date
- Auto-refresh paused when viewing Past or Upcoming (prevents overwriting)
- Coming Up Next at top when no live games, at bottom when live games active
- Upcoming data cached client-side with 10-min TTL
- **Commits**: `b48ddda`, `cf84905`, `924becb`, `bc0587d`, `a9da745`

### Feature: Two-Way Player Support
- Detects `TWP` position (e.g., Ohtani) and returns both hitting + pitching stats
- Frontend shows both stat blocks: full hitter layout + pitching section below with divider
- **Commit**: `e2dfb3d`

### Feature: Color-Graded Stats
- All stat values colored on a 6-tier gradient: 🔴 terrible → 🟠 bad → 🟡 average → 🟢 good → 🟢 elite → 🔵 legendary (blue glow)
- Uses **real 2026 MLB league averages** fetched from API (`/api/league-averages`, cached 1hr)
- Rate stats (AVG, OPS, ERA, etc.) graded as % above/below league average
- Counting stats (HR, RBI, SB, etc.) scaled by context: season (mid-year), full (162G), career
- Reversed stats handled: ERA, WHIP, BB/9, K (batters), H/9, HR/9, BAA, AB/HR
- Applied to all tabs: Season, Career, Year-by-Year, Defense
- **Commits**: `6dd221f`, `16d1dcb`, `d823ed6`, `5ce6640`, `47d1456`, `0a3cf5c`, `e1559e0`, `0e57bd9`, `552cf84`

### Feature: Star/Favorite Button on Player Dashboard
- Gold ☆ button in player header to add player to favorites
- **Commit**: `8940d53`

### Enhancement: Sample-Size-Aware Red Flags
- Three severity tiers based on games played: `caution` (<30G), `bad` (30-60G), `terrible` (60+G)
- Early-season flags include recovery context ("Eugenio Suárez hit .168 through April 2022 and finished .236")
- New `caution` CSS level: yellow/amber styling with 📉 icon
- Pitchers scaled by IP instead of games
- Red flags sorted least-to-most severe (top to bottom)
- **Commit**: `fcb31f4`

### Enhancement: Defense Tab Insights & Red Flags
- Insights: FLD% context, error-free streaks, range factor, DP production, multi-position versatility
- Red flags: sub-.950 FLD%, high error rates
- **Commit**: `c1331e1`

### Enhancement: Clickable Players in Box Score
- All batter and pitcher names in box scores are clickable → opens their player dashboard
- **Commit**: `7b2211b`

### Enhancement: Refresh Rate
- Live scores, player Live tab, and box score refresh every 6 seconds (was 15)
- Team page stays at 15s
- **Commit**: `353df46`

### Bugfix: Year-by-Year Team Names
- Was showing "Unknown" because `statsapi.player_stat_data()` doesn't include team info
- Fixed by using raw API (`statsapi.get("person", ...)`) which includes `team.name` in splits
- **Commit**: `7d4f50d`

### Bugfix: Past 2 Weeks Button
- Auto-refresh was overwriting history view every 6 seconds
- Added `_viewingHistory` flag to pause refresh when viewing non-today content
- **Commit**: `b48ddda`

### Bugfix: Back to Scores Button on Game Preview
- Preview opens on stats panel but back button needed to switch to scores panel
- **Commit**: `c376ae2`

### UI: Page Title
- Changed from "MLB Dashboard" to "ScriMLB"
- **Commit**: `7d4f50d`

### Removed: Demo Mode
- Removed demo button and demo endpoints (no longer needed after live diamond fix confirmed)
- **Commit**: `696da7d`

### External APIs Integrated
- **WeatherAPI** (key: set as WEATHER_API_KEY env var on Render) — game day weather for outdoor stadiums
- **ESPN Odds** (free, no key) — moneyline + over/under from DraftKings via ESPN scoreboard API
- **MLB Injuries** (free) — IL status from roster API for both teams in preview

### Known Issues (to fix later)
- **Favorites not persisting**: Render's ephemeral filesystem wipes `mlb_favorites.json` on redeploy/restart. Solution: migrate to browser localStorage.
- **Render cold starts**: Free tier spins down after 15min inactivity. Solution: UptimeRobot ping or upgrade to Starter ($7/mo).

### Architecture Notes
- League averages: fetched from MLB teams/stats API, cached 1hr server-side + client memory
- Color grading: computed client-side from real league averages with percentage-based thresholds
- Game preview: parallel data from schedule, roster, boxscore, ESPN, WeatherAPI
- Scores nav: `_viewingHistory` flag controls auto-refresh behavior
- `_upcomingCache` + `_upcomingCacheTs` for 10-min client cache of upcoming games


### Enhancement: Crown for MLB Leaders
- Rankings now check MLB-wide #1 in addition to league (AL/NL) top-15
- 👑 Crown icon (blue highlight) for #1 in all of MLB
- 🥇🥈🥉 Medals for #1/#2/#3 in their league
- Crown appears both in Rankings section and next to stat value on dashboard
- **Commit**: `1dc1375`

### Fix: Counting Stat Color Thresholds
- League leaders (like CJ Abrams #1 RBI) were only showing green, not blue
- Problem: multipliers too conservative — average included bench/part-time players
- Lowered elite/legendary thresholds for RBI, R, H so league leaders reach top tiers
- RBI through 40G: elite=32+, legendary=38+ (was 38/53)
- **Commit**: `4567f39`

### Enhancement: Star/Favorite Button
- Gold ☆ button on player dashboard header to quick-add to favorites
- **Commit**: `8940d53`


## Session: May 11, 2026 (Early Morning)

### Bugfix: Box Score Auto-Refresh Resetting At-Bat Position
- **Problem**: Auto-refresh replaced entire `stats-content` innerHTML every 6s, destroying at-bat scroller state and scroll position
- **Fix**: Refactored `renderBoxScore` to build stable container divs (`box-linescore`, `box-diamond`, `ab-strike-zone`, `box-tables`). New `refreshBoxScoreData()` only updates those containers without touching the at-bat section.
- **Commit**: `a302ace`

### Feature: At-Bat Left/Right Navigation with Strike Zone Sync
- Replaced horizontal scroll at-bat cards with ◀ / ▶ buttons and a counter ("3 / 47")
- Defaults to the most recent (last) at-bat on load
- Strike zone renders from the currently selected at-bat's pitch_sequence data
- Backend updated: pitch_sequence now includes x/y coordinates (pX/pZ) and removed 6-pitch limit
- **Commit**: `a302ace`

### Feature: Pitch-by-Pitch Animation on At-Bat Change
- When navigating to a new at-bat, pitches animate into the strike zone one at a time (400ms gap)
- Ball/Strike/Out indicators update with each pitch (using actual count at that point)
- Diamond shows previous at-bat's runners, then updates to current at-bat's result after last pitch
- Backend now returns per-pitch `balls`, `strikes`, `outs` count and end-of-AB `runners` state
- **Commit**: `11c4a2a`

### Bugfix: Live Game Compatibility for At-Bat Animation
- `refreshBoxScoreData` no longer clobbers diamond/strike zone if animation is in progress
- Diamond only updates from live feed when user is on latest at-bat AND no animation running
- New at-bats auto-advance and animate; browsing past at-bats is undisturbed by refresh
- **Commit**: `c9b82e8`

### Bugfix: No Auto-Refresh for Past Games
- Box score auto-refresh timer only starts if `/api/game/{id}/live` confirms game is in progress
- Final/past games load once with no polling
- **Commit**: `72b31cb`

### UI: Fixed Layout Sizes on Box Score Page
- All sections locked to fixed dimensions to prevent layout shift during animation/refresh:
  - Linescore: `min-height:60px`
  - Diamond: `min-width:120px; min-height:180px`
  - Strike zone: fixed `height:320px` with `overflow:hidden`
  - Pitch sequence log: fixed `height:150px` (max 10 pitches visible)
  - At-bat card area: `min-height:160px`
- **Commit**: `6c9aa91`

### UI: Fixed Pitcher Preview Layout on Future Games
- Replaced `stat-row`/`stat-cell` classes (3-col grid, oversized) with inline 5-column grid
- Stats use 16px font, align properly in a single row (ERA, W-L, WHIP, K, IP)
- Removed `flex-wrap` and `min-width:140px` so pitchers stay side-by-side
- **Commit**: `d95373f`

### UI: Collapsed Injury List on Game Preview
- Shows only first 3 injuries per team with count badge
- "Show X more…" toggle expands/collapses the rest
- **Commit**: `47d8505`

### Infra: Switched Git Remote to HTTPS + Credential Manager
- Remote changed from `git@github.com:` (SSH) to `https://github.com/` (HTTPS)
- `git config --global credential.helper manager` (Windows Credential Manager)
- **Commit**: N/A (config change)


## Session: May 11, 2026 (Afternoon)

### Infra: Docker Working + Auto-Deploy
- **Fixed Docker Desktop**: WSL2 had no Linux distro installed; ran `wsl --install Ubuntu`, restarted Docker Desktop
- **docker-compose.yml** updated: Cloudflare tunnel baked in with token in command, `network_mode: "service:web"` so tunnel reaches Flask via localhost, `restart: unless-stopped` on both services
- **Renamed project folder**: `srimlb` → `scrimlb` (containers now `scrimlb-web-1`, `scrimlb-tunnel-1`)
- **Desktop shortcut**: `ScriMLB.lnk` on desktop runs `docker compose up -d` with Docker icon
- **Deploy script**: `deploy.ps1` does `git push origin master` + `docker compose up --build -d`
- **PowerShell profile**: `deploy` function available globally in new terminals
- **Execution policy**: Set via registry `HKCU` for RemoteSigned
- **Commits**: `9df2044`, `7c39cc0`

### Bugfix: Upcoming Today Games Not Linking to Preview
- Games in "Upcoming Today" section now call `loadGamePreview()` on click
- **Commit**: `9df2044`

### UI: Removed "Coming Up Next" Section from Today Tab
- Redundant with the Upcoming tab; Today page now just shows Live → Upcoming Today → Final
- **Commit**: `7c39cc0`

### UI: Cleaner Pitcher Layout on Game Preview
- Replaced cluttered 5-column centered grid with horizontal cards (photo left, stats right)
- Stacked vertically, one per row — much better on mobile
- **Commit**: `7c39cc0`

### Feature: Predicted Lineups & Pitchers
- Backend predicts pitcher from rotation pattern when probable pitcher not announced
- Backend uses last game's lineup when official lineup not posted
- Orange "PREDICTED" badge on predicted pitchers and lineups
- Official lineups/pitchers show without badge
- Fixed `statsapi.schedule(team=id)` to use 14-day date range (bare call only returns current series)
- **Commit**: `7c39cc0`

### Bugfix: Pitch Animation Replay Loop
- Pitches no longer replay every 6s refresh on the most recent at-bat
- Tracking vars (`_lastAnimatedAbIndex`, `_lastAnimatedPitchCount`) set immediately when animation starts
- Refresh only re-renders if pitch count actually changed
- New pitches in live games only animate the new pitch, not all previous ones
- **Commits**: `7c39cc0`, `e82b429`

### UI: Box Score Mobile Redesign
- Diamond (60px SVG) + Strike Zone side-by-side in compact row
- Removed pitch log from inside strike zone (was causing 3-col clutter)
- Added pitch sequence log as fixed 80px scrollable section below
- BSO dots shrunk to 5px, single line with `white-space:nowrap`
- Strike zone always renders frame (no layout shift during animation)
- Batter/pitcher matchup moved to its own row above diamond/zone
- Fixed `renderDiamond` refresh overwriting compact diamond with oversized version
- Score display below diamond (shows previous AB's score, updates after animation)
- **Commits**: `e82b429`, `8965790`

### UI: Pitch Sequence Improvements
- All MLB pitch codes handled: `*B`, `D`, `E`, `H`, `M`, `O`, `T`
- Colors: Red = strike (called/swinging/foul on <2 strikes), Yellow = foul on 2 strikes, Green = ball/HBP, Blue = in play
- "In play" shows actual event name (Flyout, Single, etc.) instead of generic "Play"
- Grid layout (12px/24px/32px/auto columns) centered in container
- Monospace font, no truncation
- **Commit**: `8965790`

### Feature: Inning Navigation in At-Bat Play-by-Play
- Two-row grid: ▲1 ▲2 ▲3... above ▼1 ▼2 ▼3... (aligned columns, 20px grid)
- Tap to jump to first at-bat of that inning half
- Current inning highlighted in green/bold as you navigate
- Positioned below the at-bat card
- **Commit**: `8965790`

### Feature: Score Tracking Per At-Bat
- Backend returns `away_score`, `home_score`, `away_abbr`, `home_abbr` per at-bat (from `result` not `about`)
- Score shows below BSO in diamond, updates only after animation completes
- **Commit**: `8965790`

### UI: Linescore Table Redesign
- Replaced `<pre>` text with proper HTML table with grid borders
- 3-panel layout: fixed team names (left), scrollable innings (middle), fixed R/H/E (right)
- Consistent 26px row heights for alignment
- Scrollbar only under innings section
- **Commits**: `8965790`, `9c051a9`, `1e89b75`, `e93e78d`

### Feature: Extra Innings Indicator
- Final games show `Final/10`, `Final/11` etc. when >9 innings
- Applied to both Today tab and Past tab
- **Commit**: `7ddf847`

### UI: Past Tab Date Formatting
- Dates now show as "Sun, May 10" instead of "2026-05-10"
- **Commit**: `6b27efb`

### UI: Navigation Improvements
- Back button returns to source tab (Today/Past/Upcoming) with scroll position
- Previews and box scores render in Scores panel (no tab switching)
- Smooth transitions without chaotic tab flipping
- **Commit**: `b7c285e`

### Current Docker Setup
- Start: `docker compose up -d` from `C:\Users\Austin\scrimlb`
- Or double-click ScriMLB desktop shortcut
- Or type `deploy` in any new PowerShell (pushes + rebuilds)
- Tunnel auto-connects to scrimlb.com via Cloudflare
- Both services restart automatically after reboot (if Docker Desktop starts)

### Known Issues
- Weather not showing on game previews (WEATHER_API_KEY not set in Docker env)
- Favorites still use JSON file (ephemeral in Docker without volume — currently mounted)
