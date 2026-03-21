# DXWatch server

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
mkdir dxwatch
cd dxwatch
mkdir data

tar xf
docker load -i dxwatch.tar
```

## start image

```bash
docker compose up -d web
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

## Update DX-pedition data

Make a Excel (xlsx) or CSV (Comma Separated Value) file that have following columns.

```csv
callsign,entity_name,dxcc,grid,start_dt,end_dt,url,notes
```

Place this file under data folder.

Restart `server.py`. The server import the DX-pedition data and replace the database. Sending `SIGHUP` can also update the database.

```bash
docker compose kill -s HUP web
```
