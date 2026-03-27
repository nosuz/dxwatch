# DXWatch server

Sample site: [DX watch](https://dx-watch.jp)

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
tar cvf dxwatch_image.tar dxwatch.tar compose.yaml README.md
```

### transfer image

```bash
scp dxwatch_image.tar user@server:/tmp/
```

### install image

```bash
mkdir -p dxwatch/data
cd dxwatch

tar xf /tmp/dxwatch_image.tar
docker load -i dxwatch.tar
```

## Control Docker Container

### start container

```bash
docker compose up -d web
```

`-d`が無いとフォアグラウンドで実行される。

### stop container

```bash
docker compose down
```

### get into container

```bash
 docker exec -it  <CONTAINER ID or NAME> /bin/bash
 ```

## Update DX-pedition data

Make a Excel (xlsx) or CSV (Comma Separated Value) file that have following columns.

```csv
callsign,entity_name,dxcc,grid,start_dt,end_dt,url,notes
```

Place this file under `data` folder.

Restart `server.py` or send `SIGHUP` to the container. The server import the DX-pedition data and replace the database.

```bash
docker compose kill -s HUP web
```

## Export DX-pedition data

```bash
docker compose run --rm export
```

## Make propagation movie

### Make snapshots

```bash
docker compose run --rm snapshot
```

### Make a movie

```bash
docker compose run --rm make_movie
```
