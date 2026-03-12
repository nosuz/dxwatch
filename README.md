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

## Required folders

- logs
- data

```bash
mkdir logs data
```

## Build Container

```bash
docker compose build
# build and run in background
# docker compose up -d --build
```

## Transfer Docker Image

### extract image

```bash
docker save pskreporter-app:latest -o app.tar
tar zcvf ~/pskreporter_image.tgz app.tar compose.yaml README.md
```

### transfer image

```bash
scp pskreporter.tar user@server:/tmp/
```

### install image

```bash
docker load -i pskreporter.tar
```

## start image

```bash
docker compose up -d
```

`-d`が無いとフォアグラウンドで実行される。

## stop image

```bash
docker compose down
```

## Insert or Update DX-pedition data

```bash
# Single expedition
echo '[{"callsign":"3Y0K","entity_name":"Bouvet Island","start_dt":"2026-03-01","end_dt":"2026-03-18"}]' > /tmp/dx.json
python dxpedition_cli.py /tmp/dx.json
kill -USR1 $(pgrep -f server.py)

# Custom DB path
python dxpedition_cli.py dx.json --db /path/to/data/spots.db
```
