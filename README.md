# ⚾ MLB Dashboard

A real-time MLB stats dashboard with anomaly detection, historical comparisons, and Statcast integration. Built with Flask and deployed on Render.

**Live:** https://srimlb.onrender.com

## Features

### 📊 Live Scoreboard
- Real-time scores for all MLB games with 15-second auto-refresh
- Favorite teams highlighted with ★ FAV badges
- Live game indicators with inning state
- **Coming Up Next**: Preview of next 3 upcoming games with dates and game times
- **See All Upcoming (2 Weeks)**: Expandable full 14-day schedule grouped by date
- **Past 2 Weeks**: Browse historical results with tap-to-view box scores

### 🔍 Fuzzy Player & Team Search
- Search any MLB player (active or historical) with typo tolerance
- Falls back to pybaseball fuzzy matching when exact search fails
- Team search with fuzzy matching against names, abbreviations, and short names

### 👤 Player Dashboard (5 Views)

#### Season (Current Year)
- Full stat dashboard:
  - **Batters**: Slash line (AVG/OBP/SLG/OPS/BABIP/AB-HR), Counting (G/PA/H/2B/3B/HR/R/RBI/TB), Discipline & Speed (BB/K/HBP/SB/CS/GIDP)
  - **Pitchers**: Core (ERA/W-L/WHIP/IP/G/GS/W%/ER), Strikeouts & Walks (K/BB/K-BB/K9/BB9/HBP), Batted Ball (H/HR/BAA/OBP-Agst/H9/HR9), Durability & Extras (CG/SHO/SV/HLD/WP/BF)
- **🔥 Anomalies**: Flags elite performances with historical context
- **🚩 Red Flags**: Flags historically bad stats with comparisons to worst seasons ever
- Historical record comparisons with progress bars (vs. Bonds, Ruth, Gibson, etc.)
- Contextual insights with nuggets explaining significance
- Last game stats with green highlights for standout performances

#### Career Totals
- Aggregate career statistics (full 4-section layout for both batters and pitchers)
- **🔥 Anomalies**: Career milestone alerts (500 HR Club, 3000 Hits, 300 Wins, 3000 K Club, etc.)
- **🚩 Red Flags**: Career-level concerns (sub-.230 AVG, 28%+ K rate, 4.50+ ERA, sub-.450 W%, etc.)
- **vs. All-Time Career Records**: Progress bars comparing to all-time leaders
- **HOF Pace Check**: Compares stats to Hall of Famers at the same career point (e.g., "Through 5 seasons: +12 HR ahead of Willie Mays")
- **Career Milestones ✓**: Checklist of up to 10 best achievements with context on how quickly they were reached

#### Year by Year
- Season-by-season historical stats with dropdown selector
- **Team logo and name** displayed per season — changes when selecting different years
- **Mid-season trade splits** shown as separate entries (e.g., "2023 — Phillies" and "2023 — Dodgers")
- Chronologically sorted, no duplicates
- **🔥 Anomalies**: Flags standout individual seasons (50-HR, .350+ AVG, sub-2.00 ERA, 300-K)
- **🚩 Red Flags**: Flags bad individual seasons (.200 AVG, 6.00+ ERA, 35%+ K rate, 5.0+ BB/9)

#### ⚡ Statcast
- Exit velocity (avg/max), launch angle, barrel%, hard hit%
- Bat speed, sprint speed
- xBA, xSLG (expected stats)
- Pitcher: velocity, spin rate, pitch mix breakdown, exit velo against

#### 🔴 Live Game
- Real-time game status with auto-refresh (15s)
- Player's in-game stats
- Diamond visualization and strike zone

### 🏟️ Team Dashboard
- Record, division rank, games back
- Live game status when playing (with box score link)
- Recent game log (last 7) with W/L badges and box score links
- **Upcoming Games**: Next 3 games with opponent logo, home/away, date, and time — expandable to show full schedule
- Full active roster grouped by position (Pitcher, Catcher, Infielder, Outfielder)
- Batting lineup from most recent game
- All players clickable → loads their stat dashboard

### 🔔 Notifications
- Background anomaly detection for favorited players and teams
- Two tiers: 🔥 Alert (elite) and 👑 All-Time (historic territory)
- Win/loss streak detection for teams
- Blowout game detection
- Deduplication to avoid repeat alerts

### 🎨 UI: "Neon Dugout" Theme
- True black background with electric green accents
- Hot pink for live indicators, bright gold for all-time records
- Red/orange for red flags (two severity levels)
- Monospace stat values (SF Mono/Fira Code)
- Neon glow effects on active elements
- Mobile-first responsive design with bottom tab navigation

## Tech Stack

- **Backend**: Flask (Python)
- **Data Sources**: MLB Stats API (via `statsapi`), Baseball Savant (via `pybaseball`)
- **Deployment**: Render (free tier, auto-deploys from GitHub)
- **No API keys required** — all data sources are free/public

## Project Structure

```
srimlb/
├── mlb_web.py              # Flask app — all routes and API logic
├── mlb_notifications.py    # Background anomaly detection engine
├── mlb_thresholds.py       # Dynamic thresholds from league data
├── mlb_favorites.json      # Persisted user favorites
├── templates/
│   └── dashboard.html      # Single-page app (HTML/CSS/JS)
├── requirements.txt        # Python dependencies
├── SESSION_SUMMARY.md      # Development session notes
└── README.md
```

## Running Locally

```bash
pip install -r requirements.txt
python mlb_web.py
```

Open http://localhost:5000

## Dependencies

- `flask` — Web framework
- `MLB-StatsAPI` — MLB Stats API wrapper
- `pybaseball` — Statcast, FanGraphs, Baseball Reference data
- `numpy` — Required by pybaseball
- `gunicorn` — Production WSGI server (Render)

## Historical Comparisons

The dashboard compares players against curated data for:

**Hitters (HOF Pace)**: Barry Bonds, Hank Aaron, Willie Mays, Babe Ruth, Mickey Mantle, Ted Williams, Mike Trout, Ken Griffey Jr., Albert Pujols

**Pitchers (HOF Pace)**: Nolan Ryan, Randy Johnson, Pedro Martinez, Greg Maddux, Clayton Kershaw, Sandy Koufax, Bob Gibson, Walter Johnson

**Bad-stat references**: Chris Davis (.168 in 2018), Mario Mendoza (.200 line), Adam Dunn (32% K rate), Les Sweetland (7.71 ERA in 1930), Tommy Byrne (8.4 BB/9 in 1950)

**Career Records**: HR (762 Bonds), Hits (4256 Rose), RBI (2297 Aaron), SB (1406 Henderson), Wins (511 Cy Young), K (5714 Ryan), Shutouts (110 W. Johnson)
