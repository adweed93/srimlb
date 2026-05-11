# ScriMLB Local Hosting Setup - May 11, 2026

## Current State
- App is LIVE at https://scrimlb.com
- Running locally on Windows (no Docker yet - enabling virtualization in BIOS)
- Domain: scrimlb.com (bought on GoDaddy, nameservers pointed to Cloudflare)

## How to Start the App (2 terminals needed)

### Terminal 1 - Flask App:
```powershell
cd C:\Users\Austin\srimlb
& "C:\Users\Austin\AppData\Local\Programs\Python\Python314\python.exe" mlb_web.py
```

### Terminal 2 - Cloudflare Tunnel:
```powershell
cloudflared.exe tunnel run --token eyJhIjoiN2Y0YzBmNTQ2ODIyZjZlNDE3MDA1NGM0ZWI1ZjNiYWQiLCJ0IjoiZDA1YTFhOTctODhjYi00NjVmLWE2ZjctNGQxZTg2MjVkMWU1IiwicyI6Ik56WTNNV0l5TkRJdE9HVTNZUzAwWTJJeUxUZzFOR010TVdVd05qTmtOekE1T1RJNCJ9
```

## Cloudflare Tunnel Config
- Tunnel name: scrimlb
- Tunnel ID: d05a1a97-88cb-465f-a6f7-4d1e8625d1e5
- Published route: scrimlb.com -> http://localhost:5000
- DNS: CNAME @ -> d05a1a97-88cb-465f-a6f7-4d1e8625d1e5.cfargotunnel.com (proxied)

## Python Setup
- `python` command points to: C:\Users\Austin\AppData\Local\Python\pythoncore-3.14-64\python.exe (no packages)
- `pip` installs to: C:\Users\Austin\AppData\Local\Programs\Python\Python314\ (has all packages)
- Must use full path to run app

## Docker Status
- Docker Desktop installed but needs virtualization enabled in BIOS
- User is restarting PC to enable Intel VT-x / AMD-V in BIOS
- Dockerfile and docker-compose.yml already created in srimlb/
- If Docker works after BIOS change, can switch to: docker compose up --build
- Tunnel route is set to localhost:5000, so running app in Docker with -p 5000:5000 works without changing tunnel config

## Files Created This Session
- C:\Users\Austin\srimlb\Dockerfile
- C:\Users\Austin\srimlb\docker-compose.yml
- C:\Users\Austin\srimlb\.dockerignore

## Bug Fixed This Session
- iOS Safari bottom nav detaching on scroll - added translateZ(0) and viewport-fit=cover
