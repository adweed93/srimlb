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
