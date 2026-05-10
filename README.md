# ⚾ MLB Dashboard

A real-time MLB stats dashboard with anomaly detection, historical comparisons, and Statcast integration. Built with Flask and deployed on Render.

**Live:** https://srimlb.onrender.com

## Features

### 📊 Live Scoreboard
- Real-time scores for all MLB games with 30-second auto-refresh
- Favorite teams highlighted with star badges
- Live game indicators with inning state

### 🔍 Fuzzy Player & Team Search
- Search any MLB player (active or historical) with typo tolerance
- Falls back to pybaseball fuzzy matching when exact search fails
- Team search with fuzzy matching against names, abbreviations, and short names

### 👤 Player Dashboard (4 Views)

#### Season (Current Year)
- Full stat dashboard: slash line, counting stats, discipline & speed (batters) or core, batted ball, efficiency (pitchers)
- **🔥 Anomalies**: Flags elite performances with historical context (e.g., "On pace for 55 HR — only 7 players in history have hit 55+")
- **🚩 Red Flags**: Flags historically bad stats (e.g., ".195 AVG — Mendoza Line territory")
- Historical record comparisons with progress bars (vs. Bonds, Ruth, Gibson, etc.)
- Contextual insights with nuggets explaining significance
- Last game stats with green highlights for standout performances

#### Career Totals
- Aggregate career statistics
- **🔥 Anomalies**: Career milestone alerts (500 HR Club, 3000 Hits, 300 Wins, etc.)
- **🚩 Red Flags**: Career-level concerns (sub-.230 AVG, 28%+ K rate, etc.)
- **vs. All-Time Career Records**: Progress bars comparing to all-time leaders
- **HOF Pace Check**: Compares stats to Hall of Famers at the same career point (e.g., "Through 5 seasons: +12 HR ahead of Willie Mays")
- **Career Milestones ✓**: Checklist of up to 10 best achievements with context on how quickly they were reached

#### Year by Year
- Season-by-season historical stats with dropdown selector
- **🔥 Anomalies**: Flags standout individual seasons (50-HR, .350+ AVG, sub-2.00 ERA, 300-K)
- **🚩 Red Flags**: Flags bad individual seasons (.200 AVG, 6.00+ ERA, 35%+ K rate)

#### ⚡ Statcast
- Exit velocity (avg/max), launch angle, barrel%, hard hit%
- Bat speed, sprint speed
- xBA, xSLG (expected stats)
- Pitcher: velocity, spin rate, pitch mix breakdown, exit velo against

### 🏟️ Team Dashboard
- Record, division rank, games back
- Live game status when playing
- Recent game log with W/L badges
- Full active roster grouped by position
- Batting lineup from most recent game

### 🔔 Notifications
- Background anomaly detection for favorited players and teams
- Two tiers: 🔥 Alert (elite) and 👑 All-Time (historic territory)
- Win/loss streak detection for teams
- Deduplication to avoid repeat alerts

### 🎨 UI: "Neon Dugout" Theme
- True black background with electric green accents
- Monospace stat values (SF Mono/Fira Code)
- Gold glow for all-time records, red/orange for red flags
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

**Hitters**: Barry Bonds, Hank Aaron, Willie Mays, Babe Ruth, Mickey Mantle, Ted Williams, Mike Trout, Ken Griffey Jr., Albert Pujols

**Pitchers**: Nolan Ryan, Randy Johnson, Pedro Martinez, Greg Maddux, Clayton Kershaw, Sandy Koufax, Bob Gibson, Walter Johnson

**Bad-stat references**: Chris Davis (.168 in 2018), Mario Mendoza (.200 line), Adam Dunn (32% K rate), Les Sweetland (7.71 ERA in 1930), Tommy Byrne (8.4 BB/9 in 1950)
