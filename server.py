# pip install fastapi paho-mqtt uvicorn[standard]

import sys
import json
import asyncio
import random
import time
import threading
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import paho.mqtt.client as mqtt
import uvicorn

from contextlib import asynccontextmanager

BASE_DIR = Path(__file__).resolve().parent
PAGES_DIR = BASE_DIR / "pages"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DATA_DIR / "spots.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop, mqtt_client

    main_loop = asyncio.get_running_loop()
    db_init()
    sync_dxpedition_subscriptions()  # loads active callsigns; MQTT not yet connected

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(BROKER, PORT)
    mqtt_client.loop_start()

    hb_task = asyncio.create_task(heartbeat_task())
    sync_task = asyncio.create_task(daily_sync_task())

    yield

    hb_task.cancel()
    sync_task.cancel()

    if mqtt_client is not None:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

    if _db is not None:
        with _db_lock:
            _db.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ==========================
# MQTT設定（PSKReporter）
# ==========================
BROKER = "mqtt.pskreporter.info"
PORT = 1883

TOPIC_FROM_JP = "pskr/filter/v2/+/FT8/+/+/+/+/339/+"
TOPIC_TO_JP = "pskr/filter/v2/+/FT8/+/+/+/+/+/339"
TOPIC_JQ3IKN = "pskr/filter/v2/+/+/JQ3IKN/#"

# ==========================
# SQLite（直近15分保持）
# ==========================
KEEP_SEC = 900

_db: sqlite3.Connection | None = None
_db_lock = threading.Lock()

clients: Dict[WebSocket, Dict[str, Any]] = {}
main_loop: asyncio.AbstractEventLoop | None = None
mqtt_client: mqtt.Client | None = None

HB_INTERVAL = 10
last_mqtt_ts_from_jp = 0.0
last_mqtt_ts_to_jp = 0.0
last_mqtt_ts_jq3ikn = 0.0
last_mqtt_ts_dxpedition = 0.0

dxpedition_subscribed_callsigns: set[str] = set()


def maidenhead_to_latlon(locator: str):
    locator = locator.strip().upper()
    lon = (ord(locator[0]) - ord('A')) * 20 - 180
    lat = (ord(locator[1]) - ord('A')) * 10 - 90
    lon += int(locator[2]) * 2
    lat += int(locator[3]) * 1
    lon_size = 2
    lat_size = 1
    if len(locator) >= 6:
        lon += (ord(locator[4]) - ord('A')) * (5 / 60)
        lat += (ord(locator[5]) - ord('A')) * (2.5 / 60)
        lon_size = 5 / 60
        lat_size = 2.5 / 60
    lon += lon_size / 2
    lat += lat_size / 2
    return lat, lon


def apply_blur(lat, lon, locator: str):
    locator = locator.strip().upper()
    if len(locator) == 4:
        lat += random.uniform(-0.5, 0.5)
        lon += random.uniform(-1.0, 1.0)
    return lat, lon


def db_init():
    global _db
    _db = sqlite3.connect(DB_PATH, check_same_thread=False)
    _db.row_factory = sqlite3.Row
    with _db_lock:
        _db.execute(
            """
            CREATE TABLE IF NOT EXISTS spots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        _db.execute("CREATE INDEX IF NOT EXISTS idx_spots_ts ON spots(ts)")
        _db.execute(
            """
            CREATE TABLE IF NOT EXISTS dxpedition (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                callsign    TEXT    NOT NULL,
                entity_name TEXT,
                dxcc        INTEGER,
                grid        TEXT,
                start_dt    TEXT,
                end_dt      TEXT,
                url         TEXT,
                notes       TEXT,
                created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
            """
        )
        _db.execute(
            "CREATE INDEX IF NOT EXISTS idx_dxpedition_callsign ON dxpedition(callsign)")
        _db.execute(
            "CREATE INDEX IF NOT EXISTS idx_dxpedition_dxcc ON dxpedition(dxcc)")
        _db.execute(
            "CREATE INDEX IF NOT EXISTS idx_dxpedition_dates ON dxpedition(start_dt, end_dt)")
        _db.commit()


def get_active_dxpeditions() -> list[dict]:
    assert _db is not None
    with _db_lock:
        cur = _db.execute(
            """
            SELECT * FROM dxpedition
            WHERE (start_dt IS NULL OR start_dt <= date('now'))
              AND (end_dt   IS NULL OR end_dt   >= date('now'))
            ORDER BY callsign ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def sync_dxpedition_subscriptions():
    global dxpedition_subscribed_callsigns
    active = {row["callsign"].upper().replace('/', '%2F')
              for row in get_active_dxpeditions()}
    if mqtt_client is not None:
        for cs in dxpedition_subscribed_callsigns - active:
            mqtt_client.unsubscribe(f"pskr/filter/v2/+/+/{cs}/#")
            print("Unsubscribed: %s", f"pskr/filter/v2/+/+/{cs}/#")
        for cs in active - dxpedition_subscribed_callsigns:
            mqtt_client.subscribe(f"pskr/filter/v2/+/+/{cs}/#")
            print("Subscribed: %s", f"pskr/filter/v2/+/+/{cs}/#")
    dxpedition_subscribed_callsigns = active


def db_insert(payload: str):
    assert _db is not None
    now = time.time()
    cutoff = now - KEEP_SEC
    with _db_lock:
        _db.execute("INSERT INTO spots(ts, payload) VALUES(?, ?)",
                    (now, payload))
        _db.execute("DELETE FROM spots WHERE ts < ?", (cutoff,))
        _db.commit()


def db_select_recent(mode: str | None = None, dxcall: str | None = None) -> list[str]:
    assert _db is not None
    now = time.time()
    cutoff = now - KEEP_SEC
    with _db_lock:
        cur = _db.execute(
            "SELECT payload FROM spots WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        )
        rows = [row[0] for row in cur.fetchall()]

    if mode is None:
        return rows

    filtered: list[str] = []
    for payload in rows:
        try:
            obj = json.loads(payload)
            if obj.get("type") == "spot" and obj.get("mode") == mode:
                if mode == "dxpedition" and dxcall and obj.get("dxcall", "") != dxcall:
                    continue
                filtered.append(payload)
        except Exception:
            pass
    return filtered


def mode_from_topic(topic: str) -> str | None:
    parts = topic.split("/")
    # Check dxpedition first (callsign at position 5)
    if len(parts) > 5 and parts[5] in dxpedition_subscribed_callsigns:
        return "dxpedition"
    if "JQ3IKN" in parts:
        return "jq3ikn"
    if len(parts) >= 2 and parts[-2] == "339":
        return "from_jp"
    if len(parts) >= 1 and parts[-1] == "339":
        return "to_jp"
    return None


def should_forward_spot(mode: str, ra: int | None, sa: int | None) -> bool:
    if mode == "from_jp":
        return ra != 339
    if mode == "to_jp":
        return sa != 339
    return True


def should_forward_local_spot(mode: str, ra: int | None, sa: int | None) -> bool:
    if mode == "from_jp":
        return ra == 339
    if mode == "to_jp":
        return sa == 339
    return False


def _norm_call(value: str | None) -> str:
    return (value or "").strip().upper()


def should_forward_mydx_spot(mode: str, sc: str | None, rc: str | None, mycall: str) -> bool:
    mycall = _norm_call(mycall)
    if not mycall:
        return True

    sc = _norm_call(sc)
    rc = _norm_call(rc)

    if mode == "from_jp":
        return sc == mycall
    if mode == "to_jp":
        return rc == mycall
    return False


async def broadcast(message: str):
    dead: list[WebSocket] = []
    is_hb = False
    msg_mode: str | None = None
    obj: dict[str, Any] = {}
    try:
        obj = json.loads(message)
        if obj.get("type") == "hb":
            is_hb = True
        elif obj.get("type") == "spot":
            msg_mode = obj.get("mode")
    except Exception:
        pass

    for ws, info in list(clients.items()):
        if not info.get("ready", False):
            continue
        try:
            if is_hb:
                await ws.send_text(message)
            else:
                if msg_mode is None:
                    continue
                if info.get("mode") != msg_mode:
                    continue
                if msg_mode == "dxpedition":
                    client_dxcall = info.get("dxcall", "")
                    if client_dxcall and client_dxcall != obj.get("dxcall", ""):
                        continue
                elif info.get("local"):
                    if not should_forward_local_spot(msg_mode, obj.get("ra"), obj.get("sa")):
                        continue
                else:
                    if not should_forward_spot(msg_mode, obj.get("ra"), obj.get("sa")):
                        continue
                mycall = info.get("mycall", "")
                if mycall and not should_forward_mydx_spot(msg_mode, obj.get("sc"), obj.get("rc"), mycall):
                    continue
                await ws.send_text(message)
        except Exception:
            dead.append(ws)

    for ws in dead:
        clients.pop(ws, None)


async def daily_sync_task():
    while True:
        now = datetime.now(timezone.utc)
        next_midnight = (now + timedelta(days=1)).replace(hour=0,
                                                          minute=0, second=0, microsecond=0)
        await asyncio.sleep((next_midnight - now).total_seconds())
        sync_dxpedition_subscriptions()


async def heartbeat_task():
    while True:
        hb = json.dumps(
            {
                "type": "hb",
                "ts": time.time(),
                "last_mqtt_ts_from_jp": last_mqtt_ts_from_jp,
                "last_mqtt_ts_to_jp": last_mqtt_ts_to_jp,
                "last_mqtt_ts_jq3ikn": last_mqtt_ts_jq3ikn,
                "last_mqtt_ts_dxpedition": last_mqtt_ts_dxpedition,
            }
        )
        await broadcast(hb)
        await asyncio.sleep(HB_INTERVAL)


def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected: %s", reason_code)
    client.subscribe(TOPIC_FROM_JP)
    client.subscribe(TOPIC_TO_JP)
    client.subscribe(TOPIC_JQ3IKN)
    for cs in dxpedition_subscribed_callsigns:
        client.subscribe(f"pskr/filter/v2/+/+/{cs}/#")
        print("Subscribed: %s", f"pskr/filter/v2/+/+/{cs}/#")
    print("Subscribed: %s", TOPIC_FROM_JP)
    print("Subscribed: %s", TOPIC_TO_JP)
    print("Subscribed: %s", TOPIC_JQ3IKN)


def on_message(client, userdata, msg):
    global last_mqtt_ts_from_jp, last_mqtt_ts_to_jp, last_mqtt_ts_jq3ikn, last_mqtt_ts_dxpedition
    try:
        mode = mode_from_topic(msg.topic)
        if mode is None:
            return

        data = json.loads(msg.payload.decode())
        rl = data.get("rl")
        sl = data.get("sl")
        sc = data.get("sc")
        rc = data.get("rc")

        rl_lat = rl_lon = None
        if rl:
            rl_lat, rl_lon = maidenhead_to_latlon(rl)
            rl_lat, rl_lon = apply_blur(rl_lat, rl_lon, rl)

        sl_lat = sl_lon = None
        if sl:
            try:
                sl_lat, sl_lon = maidenhead_to_latlon(sl)
                sl_lat, sl_lon = apply_blur(sl_lat, sl_lon, sl)
            except Exception:
                pass

        dxcall = None
        if mode == "from_jp":
            if rl_lat is None or rl_lon is None:
                return
            marker_lat, marker_lon = rl_lat, rl_lon
            peer_lat, peer_lon = sl_lat, sl_lon
            last_mqtt_ts_from_jp = time.time()
        elif mode == "to_jp":
            if sl_lat is None or sl_lon is None:
                return
            marker_lat, marker_lon = sl_lat, sl_lon
            peer_lat, peer_lon = rl_lat, rl_lon
            last_mqtt_ts_to_jp = time.time()
        elif mode == "jq3ikn":
            if rl_lat is None or rl_lon is None:
                return
            marker_lat, marker_lon = rl_lat, rl_lon
            peer_lat, peer_lon = sl_lat, sl_lon
            last_mqtt_ts_jq3ikn = time.time()
        elif mode == "dxpedition":
            if rl_lat is None or rl_lon is None:
                return
            marker_lat, marker_lon = rl_lat, rl_lon
            peer_lat, peer_lon = sl_lat, sl_lon
            parts = msg.topic.split("/")
            dxcall = parts[5].upper() if len(parts) > 5 else None
            last_mqtt_ts_dxpedition = time.time()
        else:
            return

        send_data = json.dumps(
            {
                "type": "spot",
                "mode": mode,
                "lat": marker_lat,
                "lon": marker_lon,
                "peer_lat": peer_lat,
                "peer_lon": peer_lon,
                "b": data.get("b", ""),
                "ra": data.get("ra"),
                "sa": data.get("sa"),
                "sc": sc,
                "rc": rc,
                "dxcall": dxcall,
                "ts": time.time(),
            }
        )

        db_insert(send_data)

        if main_loop is not None:
            main_loop.call_soon_threadsafe(
                asyncio.create_task, broadcast(send_data))

    except Exception as exc:
        print("Error: %s", exc)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    mode = websocket.query_params.get("mode", "from_jp")
    if mode not in ("from_jp", "to_jp", "jq3ikn", "dxpedition"):
        mode = "from_jp"

    local = websocket.query_params.get("local") == "1"
    mycall = websocket.query_params.get("mycall", "").strip().upper()
    dxcall = websocket.query_params.get("dxcall", "").strip().upper()
    clients[websocket] = {"ready": False,
                          "mode": mode, "local": local, "mycall": mycall, "dxcall": dxcall}

    try:
        history = db_select_recent(
            mode=mode,
            dxcall=dxcall if mode == "dxpedition" else None,
        )
        for payload in history:
            try:
                obj = json.loads(payload)
                if obj.get("type") == "spot":
                    if mode != "dxpedition":
                        if local:
                            if not should_forward_local_spot(mode, obj.get("ra"), obj.get("sa")):
                                continue
                        else:
                            if not should_forward_spot(mode, obj.get("ra"), obj.get("sa")):
                                continue
                        mycall_val = clients[websocket].get("mycall", "")
                        if mycall_val and not should_forward_mydx_spot(mode, obj.get("sc"), obj.get("rc"), mycall_val):
                            continue
            except Exception:
                pass
            await websocket.send_text(payload)

        clients[websocket]["ready"] = True

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        clients.pop(websocket, None)


@app.get("/api/dxpeditions")
def api_list_dxpeditions():
    return get_active_dxpeditions()


def page_response(name: str) -> FileResponse:
    return FileResponse(PAGES_DIR / name)


@app.get("/dx")
def index_dx():
    return page_response("app.html")


@app.get("/jq3ikn")
def index_jq3ikn():
    return page_response("app.html")


@app.get("/local")
def index_local():
    return page_response("app.html")


@app.get("/my_dx")
def index_my_dx():
    return page_response("app.html")


@app.get("/dxpedition")
def index_dxpedition():
    return page_response("app.html")


@app.get("/")
def redirect_root():
    return RedirectResponse(url="/dx", status_code=307)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
