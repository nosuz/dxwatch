# Refactored PSKReporter server

## Structure

- `server.py`: FastAPI server and WebSocket backend
- `pages/*.html`: per-page HTML files
- `static/cookies.js`: cookie helpers for `/my_dx`
- `static/map-ui.js`: band legend and shared color table
- `static/map-grid.js`: Maidenhead grid drawing
- `static/map-core.js`: Leaflet map creation and terminator setup
- `static/ws-client.js`: shared WebSocket / marker logic
- `static/page-init.js`: page bootstrap and UI wiring
- `static/app.css`: shared CSS

## Notes

- `/my_dx` now also shows grid lines and grid labels.
- Common JavaScript was split by responsibility so each file is shorter and easier to modify.
