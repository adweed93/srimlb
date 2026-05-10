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
