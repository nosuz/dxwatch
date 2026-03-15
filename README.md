# Refactored DXWatch server

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

## Limitations

- **`/my_dx` SharedWorker browser support**: The `/my_dx` page uses a `SharedWorker` to keep MQTT connections alive while navigating between pages. `SharedWorker` is not supported in Firefox private/incognito windows or most mobile browsers (iOS Safari, Android Chrome). In unsupported environments the MQTT connection will disconnect on navigation and spots received while away will be lost.

## Debugging socket

The opening and closing logs are shown in `chrome://inspect/#workers`.

## Required folders

- data

```bash
mkdir data
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
docker save dxwatch:latest -o dxwatch.tar
tar zcvf dxwatch_image.tgz dxwatch.tar compose.yaml README.md
```

### transfer image

```bash
scp dxwatch.tar user@server:/tmp/
```

### install image

```bash
docker load -i dxwatch.tar
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

## get into container

```bash
 docker exec -it  <CONTAINER ID or NAME> /bin/bash
 ```

## Export DX-pedition data

```bash
docker compose run --rm export
# restart server to update connections
```

## Insert or Update DX-pedition data

Make a Excel (xlsx) file that have following columns.

```csv
callsign, entity_name, dxcc, grid, start_dt, end_dt, url, notes
```

if the data have an `id` column, the matching rows will be replaced.

```bash
docker compose run --rm import
# restart server to update connections
```

## `dx.json` template

```json
[
    {"callsign":"","entity_name":"","start_dt":"YYYY-MM-DD","end_dt":"YYYY-MM-DD"}
]
```
