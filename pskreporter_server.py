
# pip install fastapi paho-mqtt uvicorn[standard]

import json
import asyncio
import random
import time
import threading
import sqlite3
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
import paho.mqtt.client as mqtt
import uvicorn

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop, mqtt_client

    # ===== startup =====
    main_loop = asyncio.get_running_loop()

    db_init()

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(BROKER, PORT)
    mqtt_client.loop_start()

    hb_task = asyncio.create_task(heartbeat_task())

    yield

    # ===== shutdown =====
    hb_task.cancel()

    if mqtt_client is not None:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

    if _db is not None:
        with _db_lock:
            _db.close()

app = FastAPI(lifespan=lifespan)

# ==========================
# MQTT設定（PSKReporter）
# ==========================
BROKER = "mqtt.pskreporter.info"
PORT = 1883

# 1) 日本発 -> 世界で受信されたレポート（受信者=rlを表示）
TOPIC_FROM_JP = "pskr/filter/v2/+/FT8/+/+/+/+/339/+"
# 2) 日本で受信されたレポート（送信者=slを表示）
TOPIC_TO_JP = "pskr/filter/v2/+/FT8/+/+/+/+/+/339"

# 3) JQ3IKNの送信を受信したレポート（受信地=rlを表示）
TOPIC_JQ3IKN = "pskr/filter/v2/+/+/JQ3IKN/#"

# ==========================
# SQLite（直近3分保持）
# ==========================
DB_PATH = "spots.db"
KEEP_SEC = 180  # 3分

_db: sqlite3.Connection | None = None
_db_lock = threading.Lock()

# WebSocket clients: ws -> {"ready": bool, "mode": "from_jp"|"to_jp"}
clients: Dict[WebSocket, Dict[str, Any]] = {}

# FastAPIのイベントループ参照（MQTTスレッドから安全に投げるため）
main_loop: asyncio.AbstractEventLoop | None = None

# MQTT client
mqtt_client: mqtt.Client | None = None

# ==========================
# Heartbeat
# ==========================
HB_INTERVAL = 10  # 秒（heartbeat送信間隔）
last_mqtt_ts_from_jp = 0.0
last_mqtt_ts_to_jp = 0.0
last_mqtt_ts_jq3ikn = 0.0


# ==========================
# Maidenhead → 緯度経度変換
# ==========================
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
    """locatorが4桁の場合だけ位置をランダムにずらす"""
    locator = locator.strip().upper()
    if len(locator) == 4:
        lat += random.uniform(-0.5, 0.5)   # 緯度 ±0.5°
        lon += random.uniform(-1.0, 1.0)   # 経度 ±1°
    return lat, lon


# ==========================
# SQLite helper
# ==========================
def db_init():
    global _db
    _db = sqlite3.connect(DB_PATH, check_same_thread=False)
    with _db_lock:
        _db.execute("""
            CREATE TABLE IF NOT EXISTS spots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                payload TEXT NOT NULL
            )
        """)
        _db.execute("CREATE INDEX IF NOT EXISTS idx_spots_ts ON spots(ts)")
        _db.commit()


def db_insert(payload: str):
    """payload(JSON文字列)を保存し、古いデータを削除"""
    assert _db is not None
    now = time.time()
    cutoff = now - KEEP_SEC
    with _db_lock:
        _db.execute("INSERT INTO spots(ts, payload) VALUES(?, ?)",
                    (now, payload))
        _db.execute("DELETE FROM spots WHERE ts < ?", (cutoff,))
        _db.commit()


def db_select_recent(mode: str | None = None) -> list[str]:
    """直近3分の payload を古い順に返す。modeがあればそのmodeだけ返す。"""
    assert _db is not None
    now = time.time()
    cutoff = now - KEEP_SEC
    with _db_lock:
        cur = _db.execute(
            "SELECT payload FROM spots WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,)
        )
        rows = [row[0] for row in cur.fetchall()]

    if mode is None:
        return rows

    filtered: list[str] = []
    for p in rows:
        try:
            obj = json.loads(p)
            if obj.get("type") == "spot" and obj.get("mode") == mode:
                filtered.append(p)
        except Exception:
            pass
    return filtered


# ==========================
# Topic → mode判定
# ==========================
def mode_from_topic(topic: str) -> str | None:
    parts = topic.split("/")

    # 特定コールのレポート（優先）
    # 例: pskr/filter/v2/+/+/JQ3IKN/...
    if "JQ3IKN" in parts:
        return "jq3ikn"

    # .../339/<something> なら「from_jp」
    if len(parts) >= 2 and parts[-2] == "339":
        return "from_jp"
    # .../<something>/339 なら「to_jp」
    if len(parts) >= 1 and parts[-1] == "339":
        return "to_jp"
    return None


def should_forward_spot(mode: str, ra: int | None, sa: int | None) -> bool:
    """ブラウザへ送る段階で国内通信（日本→日本）を除外する。
    - from_jp: ra==339（受信地が日本）を除外
    - to_jp:   sa==339（送信地が日本）を除外
    - jq3ikn:  フィルタしない
    """
    if mode == "from_jp":
        return ra != 339
    if mode == "to_jp":
        return sa != 339
    return True


def should_forward_local_spot(mode: str, ra: int | None, sa: int | None) -> bool:
    """/local 用: 国内(JP→JP)のみ表示"""
    if mode == "from_jp":
        return ra == 339
    if mode == "to_jp":
        return sa == 339
    return False


def _norm_call(s: str | None) -> str:
    return (s or "").strip().upper()


def should_forward_mydx_spot(mode: str, sc: str | None, rc: str | None, mycall: str) -> bool:
    """/my_dx 用フィルタ:
    - mode=from_jp（日本発）: 送信者コール(sc)がmycallと一致
    - mode=to_jp（日本で受信）: 受信者コール(rc)がmycallと一致
    """
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


# ==========================
# WebSocket配信
# ==========================
async def broadcast(message: str):
    """spotはmode一致のクライアントだけに送る。hbは全クライアントへ。"""
    dead: list[WebSocket] = []
    is_hb = False
    msg_mode: str | None = None
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
                # spot: mode一致 + ra/saフィルタ
                if msg_mode is None:
                    continue
                if info.get("mode") != msg_mode:
                    continue
                if info.get("local"):
                    if not should_forward_local_spot(msg_mode, obj.get("ra"), obj.get("sa")):
                        continue
                else:
                    if not should_forward_spot(msg_mode, obj.get("ra"), obj.get("sa")):
                        continue
                mycall = info.get("mycall", "")
                if mycall:
                    if not should_forward_mydx_spot(msg_mode, obj.get("sc"), obj.get("rc"), mycall):
                        continue
                await ws.send_text(message)

        except Exception:
            dead.append(ws)

    for ws in dead:
        clients.pop(ws, None)


# ==========================
# Heartbeat task
# ==========================
async def heartbeat_task():
    while True:
        hb = json.dumps({
            "type": "hb",
            "ts": time.time(),
            "last_mqtt_ts_from_jp": last_mqtt_ts_from_jp,
            "last_mqtt_ts_to_jp": last_mqtt_ts_to_jp,
            "last_mqtt_ts_jq3ikn": last_mqtt_ts_jq3ikn,
        })
        await broadcast(hb)
        await asyncio.sleep(HB_INTERVAL)


# ==========================
# MQTTコールバック（別スレッド）
# ==========================
def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected:", reason_code)
    client.subscribe(TOPIC_FROM_JP)
    client.subscribe(TOPIC_TO_JP)
    client.subscribe(TOPIC_JQ3IKN)
    print("Subscribed:", TOPIC_FROM_JP)
    print("Subscribed:", TOPIC_TO_JP)
    print("Subscribed:", TOPIC_JQ3IKN)


def on_message(client, userdata, msg):
    global last_mqtt_ts_from_jp, last_mqtt_ts_to_jp, last_mqtt_ts_jq3ikn
    try:
        mode = mode_from_topic(msg.topic)
        if mode is None:
            return

        data = json.loads(msg.payload.decode())

        rl = data.get("rl")
        sl = data.get("sl")

        sc = data.get("sc")
        rc = data.get("rc")

        # 両方の座標を計算（あれば）
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

        # 表示する点（marker）と、相手（peer）を切替
        if mode == "from_jp":
            # 日本発 → 受信地(rl)をマーカーに、送信地(sl)を相手に
            if rl_lat is None or rl_lon is None:
                return
            marker_lat, marker_lon = rl_lat, rl_lon
            peer_lat, peer_lon = sl_lat, sl_lon
            last_mqtt_ts_from_jp = time.time()
        elif mode == "to_jp":
            # 日本で受信 → 送信地(sl)をマーカーに、受信地(rl)を相手に
            if sl_lat is None or sl_lon is None:
                return
            marker_lat, marker_lon = sl_lat, sl_lon
            peer_lat, peer_lon = rl_lat, rl_lon
            last_mqtt_ts_to_jp = time.time()
        else:
            # JQ3IKN レポート → 受信地(rl)をマーカーに（相手は送信地(sl)）
            if rl_lat is None or rl_lon is None:
                return
            marker_lat, marker_lon = rl_lat, rl_lon
            peer_lat, peer_lon = sl_lat, sl_lon
            last_mqtt_ts_jq3ikn = time.time()

        now = time.time()

        send_data = json.dumps({
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
            "ts": now
        })

        # SQLiteに保存（3分保持）
        db_insert(send_data)

        # FastAPIのイベントループへ安全に投げてブロードキャスト
        if main_loop is not None:
            main_loop.call_soon_threadsafe(
                asyncio.create_task, broadcast(send_data))

    except Exception as e:
        print("Error:", e)


# ==========================
# WebSocket（接続時に過去3分送信→ライブ）
# ==========================


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # modeはクエリで受け取る（デフォルト: from_jp）
    mode = websocket.query_params.get("mode", "from_jp")
    if mode not in ("from_jp", "to_jp", "jq3ikn"):
        mode = "from_jp"

    # まず clients に登録（ready=Falseでライブ配信対象外）
    local = websocket.query_params.get("local") == "1"
    mycall = websocket.query_params.get("mycall", "").strip().upper()
    clients[websocket] = {"ready": False,
                          "mode": mode, "local": local, "mycall": mycall}

    try:
        # 1) 直近3分（このmodeだけ）を先に送る
        history = db_select_recent(mode=mode)
        for payload in history:
            try:
                obj = json.loads(payload)
                if obj.get("type") == "spot":
                    if local:
                        if not should_forward_local_spot(mode, obj.get("ra"), obj.get("sa")):
                            continue
                    else:
                        if not should_forward_spot(mode, obj.get("ra"), obj.get("sa")):
                            continue

                    mycall = clients[websocket].get("mycall", "")
                    if mycall:
                        if not should_forward_mydx_spot(mode, obj.get("sc"), obj.get("rc"), mycall):
                            continue
            except Exception:
                pass
            await websocket.send_text(payload)

        # 2) 履歴送信が終わったらライブ配信対象へ
        clients[websocket]["ready"] = True

        # 3) 接続維持（クライアントからの受信は捨てる）
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        clients.pop(websocket, None)


# ==========================
# HTML + Leaflet
# ==========================
@app.get("/dx", response_class=HTMLResponse)
def index_dx():
    return r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>PSKReporter Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<script src="https://unpkg.com/@joergdietrich/leaflet.terminator/L.Terminator.js"></script>
<style>
html, body { height: 100%; margin: 0; display: flex; flex-direction: column; }

#topbar {
  height: 50px;
  display: flex;
  flex-direction: row;
}

#legend {
  flex: 1;
  background:#f0f0f0;
  display:flex;
  align-items:center;
  padding:5px 10px;
  font-family:sans-serif;
  overflow-x:auto;
}

#status {
  min-width: 360px;
  background:#222;
  color:#fff;
  font-family:sans-serif;
  font-size:12px;
  padding:5px 10px;
  display:flex;
  align-items:center;
  justify-content:flex-end;
  white-space: nowrap;
  gap: 8px;
}

#modeSelect { font-size: 12px; }

.legend-item { display:flex; align-items:center; margin-right:15px; }
.legend-color { width:20px; height:20px; margin-right:5px; }

#map { flex: 1; }
.grid-label { font-size:10px; color: #444; font-weight:bold; text-align:center; }

.leaflet-twilight-overlay { pointer-events:none; }
</style>
</head>
<body>
<div id="topbar">
  <div id="legend"></div>
  <div id="status">
    <a href="/dx" style="color:#0ff; margin-right:10px; text-decoration:none;">DX</a>
    <a href="/local" style="color:#aaa; margin-right:15px; text-decoration:none;">LOCAL</a>

    <select id="modeSelect">
      <option value="from_jp">JP→World (marker=RL)</option>
      <option value="to_jp">World→JP (marker=SL)</option>
    </select>
    <span id="statusText">status: initializing...</span>
  </div>
</div>

<div id="map"></div>

<script>
// ==========================
// 地図初期化
// ==========================
var map = L.map('map').setView([0, 0], 3);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { noWrap: true }).addTo(map);
map.setMaxBounds([[-90, -200], [90, 200]]);

// ==========================
// 昼夜（terminator）レイヤ
// ==========================
// var terminator = L.terminator().addTo(map);
var terminator = L.terminator({ fillOpacity: 0.15 }).addTo(map);

// 1分ごとに更新（地球は動くので）
setInterval(function() {
  terminator.setTime(new Date());
}, 60 * 1000);

// ==========================
// 凡例
// ==========================
var color_map = {
  160: '#800000',
  80:  '#FF4500',
  60:  '#FF8C00',
  40:  'red',
  30:  'orange',
  20:  'yellow',
  17:  '#ADFF2F',
  15:  'green',
  12:  'cyan',
  10:  'blue',
  6:   '#4B0082'
};

var legendDiv = document.getElementById("legend");
for (var key in color_map) {
  var item = document.createElement("div");
  item.className = "legend-item";

  var colorBox = document.createElement("div");
  colorBox.className = "legend-color";
  colorBox.style.backgroundColor = color_map[key];

  var label = document.createElement("span");
  label.textContent = key + "m";

  item.appendChild(colorBox);
  item.appendChild(label);
  legendDiv.appendChild(item);
}

// ==========================
// グリッド描画
// ==========================
var gridLayers = L.layerGroup().addTo(map);

function drawGrid() {
  gridLayers.clearLayers();

  var zoom = map.getZoom();
  var latStep, lonStep, labelDigits;

  if (zoom < 6) {
    latStep = 10;
    lonStep = 20;
    labelDigits = 2;
  } else {
    latStep = 1;
    lonStep = 2;
    labelDigits = 4;
  }

  var bounds = map.getBounds();
  var latStart = Math.floor(bounds.getSouth() / latStep) * latStep;
  var latEnd   = Math.ceil(bounds.getNorth() / latStep) * latStep;
  var lonStart = Math.floor(bounds.getWest() / lonStep) * lonStep;
  var lonEnd   = Math.ceil(bounds.getEast() / lonStep) * lonStep;

  // 経度を -180〜180 に制限（中心が180を超えないように lonEnd を調整）
  lonStart = Math.max(lonStart, -180);
  lonEnd   = Math.min(lonEnd, 180 - lonStep);

  for (var lat = latStart; lat <= latEnd; lat += latStep) {
    for (var lon = lonStart; lon <= lonEnd; lon += lonStep) {
      var centerLat = lat + latStep/2;
      var centerLon = lon + lonStep/2;

      L.rectangle([[lat, lon],[lat+latStep, lon+lonStep]], {
        color: "#888",
        weight: 1,
        fillOpacity: 0
      }).addTo(gridLayers);

      var locator = latlon_to_maidenhead(centerLat, centerLon);
      locator = locator.substring(0,labelDigits);

      L.marker([centerLat, centerLon], {
        icon: L.divIcon({
          className: 'grid-label',
          iconSize: null,
          iconAnchor: [10, 10],
          html: `<span style="font-size:20px; color: rgba(255,0,0,0.5); font-weight:bold;">${locator}</span>`
        })
      }).addTo(gridLayers);
    }
  }
}

function latlon_to_maidenhead(lat, lon) {
  lat += 90;
  lon += 180;
  var A = 'A'.charCodeAt(0);
  var L1 = String.fromCharCode(A + Math.floor(lon/20));
  var L2 = String.fromCharCode(A + Math.floor(lat/10));
  var lon_rem = lon % 20;
  var lat_rem = lat % 10;
  var N1 = Math.floor(lon_rem/2);
  var N2 = Math.floor(lat_rem/1);
  var lon_rem2 = lon_rem % 2;
  var lat_rem2 = lat_rem % 1;
  var L3 = String.fromCharCode(A + Math.floor(lon_rem2*12.0));
  var L4 = String.fromCharCode(A + Math.floor(lat_rem2*24.0));
  return L1+L2+N1+N2+L3+L4;
}

drawGrid();
map.on('zoomend', drawGrid);
map.on('moveend', drawGrid);

// ==========================
// WebSocket + markers
// ==========================
var statusEl = document.getElementById("statusText");
var modeSelect = document.getElementById("modeSelect");
var currentMode = modeSelect.value;

var markers = [];
var ws = null;

var lastHb = 0;
var lastData = 0;
var lastMqttTsFrom = 0;
var lastMqttTsTo = 0;

function clearAll() {
  markers.forEach(function(m){ map.removeLayer(m.marker); });
  markers = [];
}

function cleanupMarkers() {
  var now = Date.now();
  markers = markers.filter(function(m) {
    if (now - m.timestamp > 180000) {
      map.removeLayer(m.marker);
      return false;
    }
    return true;
  });
}
setInterval(cleanupMarkers, 10000);

function connectWS(mode) {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  var proto = (location.protocol === "https:") ? "wss://" : "ws://";
  ws = new WebSocket(proto + location.host + "/ws?mode=" + encodeURIComponent(mode));

  ws.onopen = function() {
    statusEl.textContent = "status: websocket connected";
  };
  ws.onclose = function() {
    statusEl.textContent = "status: websocket closed";
  };
  ws.onerror = function() {
    statusEl.textContent = "status: websocket error";
  };

  ws.onmessage = function(event) {
    var data = JSON.parse(event.data);

    if (data.type === "hb") {
      lastHb = Date.now();
      if (typeof data.last_mqtt_ts_from_jp === "number" && data.last_mqtt_ts_from_jp > 0) {
        lastMqttTsFrom = data.last_mqtt_ts_from_jp * 1000;
      }
      if (typeof data.last_mqtt_ts_to_jp === "number" && data.last_mqtt_ts_to_jp > 0) {
        lastMqttTsTo = data.last_mqtt_ts_to_jp * 1000;
      }
      return;
    }

    if (data.type !== "spot") return;
    // サーバ側でmodeフィルタ済みだが念のため
    if (data.mode && data.mode !== currentMode) return;

    lastData = Date.now();

    var b_value = parseInt((data.b || "").replace("m",""));
    var color = color_map[b_value] || 'gray';

    var lat = data.lat;
    var lon = data.lon;
    var timestamp = (typeof data.ts === "number") ? data.ts * 1000 : Date.now();

    var marker = L.circleMarker([lat, lon], {
      radius: 8,
      color: color,
      fillColor: color,
      fillOpacity: 0.8
    }).addTo(map);

    markers.push({marker: marker, timestamp: timestamp});
    cleanupMarkers();
  };
}

function disconnectWS() {
  if (!ws) return;
  try { ws.close(1000, "switch or hidden"); } catch (e) {}
  ws = null;
}

// ステータス表示更新
setInterval(function() {
  var now = Date.now();
  var hbStale = (now - lastHb > 30000);
  var mqttTs = (currentMode === "from_jp") ? lastMqttTsFrom : ((currentMode === "to_jp") ? lastMqttTsTo : lastMqttTsJq);
  var mqttStale = mqttTs ? (now - mqttTs > 30000) : true;
  var dataStale = (now - lastData > 30000);

  if (hbStale) {
    statusEl.textContent = "status: websocket down (no heartbeat)";
  } else if (mqttStale) {
    statusEl.textContent = "status: websocket ok, but no new MQTT data";
  } else if (dataStale) {
    statusEl.textContent = "status: websocket ok, but no spot messages";
  } else {
    statusEl.textContent = "status: receiving";
  }
}, 1000);

// モード切替：その瞬間に全削除→WS切断→WS再接続（過去3分をそのモードだけ再描画）
modeSelect.addEventListener("change", function() {
  currentMode = modeSelect.value;
  lastData = 0; // ステータスが「古い」判定にならないようリセット
  clearAll();
  disconnectWS();
  connectWS(currentMode);
});

if (!document.hidden) connectWS(currentMode);

document.addEventListener("visibilitychange", function() {
  if (document.hidden) {
    disconnectWS();
  } else {
    clearAll();
    disconnectWS();
    connectWS(currentMode);
  }
});
</script>
</body>
</html>
"""


@app.get("/jq3ikn", response_class=HTMLResponse)
def index_jq3ikn():
    return r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>PSKReporter Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<script src="https://unpkg.com/@joergdietrich/leaflet.terminator/L.Terminator.js"></script>
<style>
html, body { height: 100%; margin: 0; display: flex; flex-direction: column; }

#topbar {
  height: 50px;
  display: flex;
  flex-direction: row;
}

#legend {
  flex: 1;
  background:#f0f0f0;
  display:flex;
  align-items:center;
  padding:5px 10px;
  font-family:sans-serif;
  overflow-x:auto;
}

#status {
  min-width: 360px;
  background:#222;
  color:#fff;
  font-family:sans-serif;
  font-size:12px;
  padding:5px 10px;
  display:flex;
  align-items:center;
  justify-content:flex-end;
  white-space: nowrap;
  gap: 8px;
}

#modeSelect { font-size: 12px; }

.legend-item { display:flex; align-items:center; margin-right:15px; }
.legend-color { width:20px; height:20px; margin-right:5px; }

#map { flex: 1; }
.grid-label { font-size:10px; color: #444; font-weight:bold; text-align:center; }

.leaflet-twilight-overlay { pointer-events:none; }
</style>
</head>
<body>
<div id="topbar">
  <div id="legend"></div>
  <div id="status">
    <a href="/dx" style="color:#aaa; margin-right:10px; text-decoration:none;">DX</a>
    <a href="/local" style="color:#aaa; margin-right:15px; text-decoration:none;">LOCAL</a>

    <span style="color:#aaa;">JQ3IKN</span>
    <span id="statusText">status: initializing...</span>
  </div>
</div>

<div id="map"></div>

<script>
// ==========================
// 地図初期化
// ==========================
var map = L.map('map').setView([0, 0], 3);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { noWrap: true }).addTo(map);
map.setMaxBounds([[-90, -180], [90, 180]]);

// ==========================
// 昼夜（terminator）レイヤ
// ==========================
// var terminator = L.terminator().addTo(map);
var terminator = L.terminator({ fillOpacity: 0.15 }).addTo(map);

// 1分ごとに更新（地球は動くので）
setInterval(function() {
  terminator.setTime(new Date());
}, 60 * 1000);

// ==========================
// 凡例
// ==========================
var color_map = {
  160: '#800000',
  80:  '#FF4500',
  60:  '#FF8C00',
  40:  'red',
  30:  'orange',
  20:  'yellow',
  17:  '#ADFF2F',
  15:  'green',
  12:  'cyan',
  10:  'blue',
  6:   '#4B0082'
};

var legendDiv = document.getElementById("legend");
for (var key in color_map) {
  var item = document.createElement("div");
  item.className = "legend-item";

  var colorBox = document.createElement("div");
  colorBox.className = "legend-color";
  colorBox.style.backgroundColor = color_map[key];

  var label = document.createElement("span");
  label.textContent = key + "m";

  item.appendChild(colorBox);
  item.appendChild(label);
  legendDiv.appendChild(item);
}

// ==========================
// グリッド描画
// ==========================
var gridLayers = L.layerGroup().addTo(map);

function drawGrid() {
  gridLayers.clearLayers();

  var zoom = map.getZoom();
  var latStep, lonStep, labelDigits;

  if (zoom < 6) {
    latStep = 10;
    lonStep = 20;
    labelDigits = 2;
  } else {
    latStep = 1;
    lonStep = 2;
    labelDigits = 4;
  }

  var bounds = map.getBounds();
  var latStart = Math.floor(bounds.getSouth() / latStep) * latStep;
  var latEnd   = Math.ceil(bounds.getNorth() / latStep) * latStep;
  var lonStart = Math.floor(bounds.getWest() / lonStep) * lonStep;
  var lonEnd   = Math.ceil(bounds.getEast() / lonStep) * lonStep;

  // 経度を -180〜180 に制限（中心が180を超えないように lonEnd を調整）
  lonStart = Math.max(lonStart, -180);
  lonEnd   = Math.min(lonEnd, 180 - lonStep);

  for (var lat = latStart; lat <= latEnd; lat += latStep) {
    for (var lon = lonStart; lon <= lonEnd; lon += lonStep) {
      var centerLat = lat + latStep/2;
      var centerLon = lon + lonStep/2;

      L.rectangle([[lat, lon],[lat+latStep, lon+lonStep]], {
        color: "#888",
        weight: 1,
        fillOpacity: 0
      }).addTo(gridLayers);

      var locator = latlon_to_maidenhead(centerLat, centerLon);
      locator = locator.substring(0,labelDigits);

      L.marker([centerLat, centerLon], {
        icon: L.divIcon({
          className: 'grid-label',
          iconSize: null,
          iconAnchor: [10, 10],
          html: `<span style="font-size:20px; color: rgba(255,0,0,0.5); font-weight:bold;">${locator}</span>`
        })
      }).addTo(gridLayers);
    }
  }
}

function latlon_to_maidenhead(lat, lon) {
  lat += 90;
  lon += 180;
  var A = 'A'.charCodeAt(0);
  var L1 = String.fromCharCode(A + Math.floor(lon/20));
  var L2 = String.fromCharCode(A + Math.floor(lat/10));
  var lon_rem = lon % 20;
  var lat_rem = lat % 10;
  var N1 = Math.floor(lon_rem/2);
  var N2 = Math.floor(lat_rem/1);
  var lon_rem2 = lon_rem % 2;
  var lat_rem2 = lat_rem % 1;
  var L3 = String.fromCharCode(A + Math.floor(lon_rem2*12.0));
  var L4 = String.fromCharCode(A + Math.floor(lat_rem2*24.0));
  return L1+L2+N1+N2+L3+L4;
}

drawGrid();
map.on('zoomend', drawGrid);
map.on('moveend', drawGrid);

// ==========================
// WebSocket + markers
// ==========================
var statusEl = document.getElementById("statusText");
var currentMode = "jq3ikn";

var markers = [];
var ws = null;

var lastHb = 0;
var lastData = 0;
var lastMqttTsFrom = 0;
var lastMqttTsTo = 0;
var lastMqttTsJq = 0;

function clearAll() {
  markers.forEach(function(m){ map.removeLayer(m.marker); });
  markers = [];
}

function cleanupMarkers() {
  var now = Date.now();
  markers = markers.filter(function(m) {
    if (now - m.timestamp > 180000) {
      map.removeLayer(m.marker);
      return false;
    }
    return true;
  });
}
setInterval(cleanupMarkers, 10000);

function connectWS(mode) {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  var proto = (location.protocol === "https:") ? "wss://" : "ws://";
  ws = new WebSocket(proto + location.host + "/ws?mode=" + encodeURIComponent(mode));

  ws.onopen = function() {
    statusEl.textContent = "status: websocket connected";
  };
  ws.onclose = function() {
    statusEl.textContent = "status: websocket closed";
  };
  ws.onerror = function() {
    statusEl.textContent = "status: websocket error";
  };

  ws.onmessage = function(event) {
    var data = JSON.parse(event.data);

    if (data.type === "hb") {
      lastHb = Date.now();
      if (typeof data.last_mqtt_ts_from_jp === "number" && data.last_mqtt_ts_from_jp > 0) {
        lastMqttTsFrom = data.last_mqtt_ts_from_jp * 1000;
      }
      if (typeof data.last_mqtt_ts_to_jp === "number" && data.last_mqtt_ts_to_jp > 0) {
        lastMqttTsTo = data.last_mqtt_ts_to_jp * 1000;
      }
      if (typeof data.last_mqtt_ts_jq3ikn === "number" && data.last_mqtt_ts_jq3ikn > 0) {
        lastMqttTsJq = data.last_mqtt_ts_jq3ikn * 1000;
      }
      return;
    }

    if (data.type !== "spot") return;
    // サーバ側でmodeフィルタ済みだが念のため
    if (data.mode && data.mode !== currentMode) return;

    lastData = Date.now();

    var b_value = parseInt((data.b || "").replace("m",""));
    var color = color_map[b_value] || 'gray';

    var lat = data.lat;
    var lon = data.lon;
    var timestamp = (typeof data.ts === "number") ? data.ts * 1000 : Date.now();

    var marker = L.circleMarker([lat, lon], {
      radius: 8,
      color: color,
      fillColor: color,
      fillOpacity: 0.8
    }).addTo(map);

    markers.push({marker: marker, timestamp: timestamp});
    cleanupMarkers();
  };
}

function disconnectWS() {
  if (!ws) return;
  try { ws.close(1000, "switch or hidden"); } catch (e) {}
  ws = null;
}

// ステータス表示更新
setInterval(function() {
  var now = Date.now();
  var hbStale = (now - lastHb > 30000);
  var mqttTs = (currentMode === "from_jp") ? lastMqttTsFrom : ((currentMode === "to_jp") ? lastMqttTsTo : lastMqttTsJq);
  var mqttStale = mqttTs ? (now - mqttTs > 30000) : true;
  var dataStale = (now - lastData > 30000);

  if (hbStale) {
    statusEl.textContent = "status: websocket down (no heartbeat)";
  } else if (mqttStale) {
    statusEl.textContent = "status: websocket ok, but no new MQTT data";
  } else if (dataStale) {
    statusEl.textContent = "status: websocket ok, but no spot messages";
  } else {
    statusEl.textContent = "status: receiving";
  }
}, 1000);


if (!document.hidden) connectWS(currentMode);

document.addEventListener("visibilitychange", function() {
  if (document.hidden) {
    disconnectWS();
  } else {
    clearAll();
    disconnectWS();
    connectWS(currentMode);
  }
});
</script>
</body>
</html>
"""


@app.get("/local", response_class=HTMLResponse)
def index_local():
    return r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>PSKReporter Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<script src="https://unpkg.com/@joergdietrich/leaflet.terminator/L.Terminator.js"></script>
<style>
html, body { height: 100%; margin: 0; display: flex; flex-direction: column; }

#topbar {
  height: 50px;
  display: flex;
  flex-direction: row;
}

#legend {
  flex: 1;
  background:#f0f0f0;
  display:flex;
  align-items:center;
  padding:5px 10px;
  font-family:sans-serif;
  overflow-x:auto;
}

#status {
  min-width: 360px;
  background:#222;
  color:#fff;
  font-family:sans-serif;
  font-size:12px;
  padding:5px 10px;
  display:flex;
  align-items:center;
  justify-content:flex-end;
  white-space: nowrap;
  gap: 8px;
}

#modeSelect { font-size: 12px; }

.legend-item { display:flex; align-items:center; margin-right:15px; }
.legend-color { width:20px; height:20px; margin-right:5px; }

#map { flex: 1; }
.grid-label { font-size:10px; color: #444; font-weight:bold; text-align:center; }

.leaflet-twilight-overlay { pointer-events:none; }
</style>
</head>
<body>
<div id="topbar">
  <div id="legend"></div>
  <div id="status">
    <a href="/dx" style="color:#aaa; margin-right:10px; text-decoration:none;">DX</a>
    <a href="/local" style="color:#0ff; margin-right:15px; text-decoration:none;">LOCAL</a>

    <span style="color:#aaa;">JP↔JP (marker=RL)</span>
    <select id="modeSelect" style="display:none;">
      <option value="from_jp">JP→World (marker=RL)</option>
      <option value="to_jp">World→JP (marker=SL)</option>
    </select>
    <span id="statusText">status: initializing...</span>
  </div>
</div>

<div id="map"></div>

<script>
// ==========================
// 地図初期化
// ==========================
var map = L.map('map').setView([36.2, 138.2], 5);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { noWrap: true }).addTo(map);
map.setMaxBounds([[20.0, 122.0], [46.5, 154.0]]);
map.setMinZoom(4);
map.setMaxZoom(10);

// ==========================
// 昼夜（terminator）レイヤ
// ==========================
// var terminator = L.terminator().addTo(map);
var terminator = L.terminator({ fillOpacity: 0.15 }).addTo(map);

// 1分ごとに更新（地球は動くので）
setInterval(function() {
  terminator.setTime(new Date());
}, 60 * 1000);

// ==========================
// 凡例
// ==========================
var color_map = {
  160: '#800000',
  80:  '#FF4500',
  60:  '#FF8C00',
  40:  'red',
  30:  'orange',
  20:  'yellow',
  17:  '#ADFF2F',
  15:  'green',
  12:  'cyan',
  10:  'blue',
  6:   '#4B0082'
};

var legendDiv = document.getElementById("legend");
for (var key in color_map) {
  var item = document.createElement("div");
  item.className = "legend-item";

  var colorBox = document.createElement("div");
  colorBox.className = "legend-color";
  colorBox.style.backgroundColor = color_map[key];

  var label = document.createElement("span");
  label.textContent = key + "m";

  item.appendChild(colorBox);
  item.appendChild(label);
  legendDiv.appendChild(item);
}

// ==========================
// グリッド描画
// ==========================
var gridLayers = L.layerGroup().addTo(map);

function drawGrid() {
  gridLayers.clearLayers();

  var zoom = map.getZoom();
  var latStep, lonStep, labelDigits;

  if (zoom < 6) {
    latStep = 10;
    lonStep = 20;
    labelDigits = 2;
  } else {
    latStep = 1;
    lonStep = 2;
    labelDigits = 4;
  }

  var bounds = map.getBounds();
  var latStart = Math.floor(bounds.getSouth() / latStep) * latStep;
  var latEnd   = Math.ceil(bounds.getNorth() / latStep) * latStep;
  var lonStart = Math.floor(bounds.getWest() / lonStep) * lonStep;
  var lonEnd   = Math.ceil(bounds.getEast() / lonStep) * lonStep;

  // 経度を -180〜180 に制限（中心が180を超えないように lonEnd を調整）
  lonStart = Math.max(lonStart, -180);
  lonEnd   = Math.min(lonEnd, 180 - lonStep);

  for (var lat = latStart; lat <= latEnd; lat += latStep) {
    for (var lon = lonStart; lon <= lonEnd; lon += lonStep) {
      var centerLat = lat + latStep/2;
      var centerLon = lon + lonStep/2;

      L.rectangle([[lat, lon],[lat+latStep, lon+lonStep]], {
        color: "#888",
        weight: 1,
        fillOpacity: 0
      }).addTo(gridLayers);

      var locator = latlon_to_maidenhead(centerLat, centerLon);
      locator = locator.substring(0,labelDigits);

      L.marker([centerLat, centerLon], {
        icon: L.divIcon({
          className: 'grid-label',
          iconSize: null,
          iconAnchor: [10, 10],
          html: `<span style="font-size:20px; color: rgba(255,0,0,0.5); font-weight:bold;">${locator}</span>`
        })
      }).addTo(gridLayers);
    }
  }
}

function latlon_to_maidenhead(lat, lon) {
  lat += 90;
  lon += 180;
  var A = 'A'.charCodeAt(0);
  var L1 = String.fromCharCode(A + Math.floor(lon/20));
  var L2 = String.fromCharCode(A + Math.floor(lat/10));
  var lon_rem = lon % 20;
  var lat_rem = lat % 10;
  var N1 = Math.floor(lon_rem/2);
  var N2 = Math.floor(lat_rem/1);
  var lon_rem2 = lon_rem % 2;
  var lat_rem2 = lat_rem % 1;
  var L3 = String.fromCharCode(A + Math.floor(lon_rem2*12.0));
  var L4 = String.fromCharCode(A + Math.floor(lat_rem2*24.0));
  return L1+L2+N1+N2+L3+L4;
}

drawGrid();
map.on('zoomend', drawGrid);
map.on('moveend', drawGrid);

// ==========================
// WebSocket + markers
// ==========================
var statusEl = document.getElementById("statusText");
var modeSelect = document.getElementById("modeSelect");
var currentMode = modeSelect.value;
var isLocal = true;

var markers = [];
var ws = null;

var lastHb = 0;
var lastData = 0;
var lastMqttTsFrom = 0;
var lastMqttTsTo = 0;

function clearAll() {
  markers.forEach(function(m){ map.removeLayer(m.marker); });
  markers = [];
}

function cleanupMarkers() {
  var now = Date.now();
  markers = markers.filter(function(m) {
    if (now - m.timestamp > 180000) {
      map.removeLayer(m.marker);
      return false;
    }
    return true;
  });
}
setInterval(cleanupMarkers, 10000);

function connectWS(mode) {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  var proto = (location.protocol === "https:") ? "wss://" : "ws://";
  ws = new WebSocket(proto + location.host + "/ws?mode=" + encodeURIComponent(mode) + "&local=1");

  ws.onopen = function() {
    statusEl.textContent = "status: websocket connected";
  };
  ws.onclose = function() {
    statusEl.textContent = "status: websocket closed";
  };
  ws.onerror = function() {
    statusEl.textContent = "status: websocket error";
  };

  ws.onmessage = function(event) {
    var data = JSON.parse(event.data);

    if (data.type === "hb") {
      lastHb = Date.now();
      if (typeof data.last_mqtt_ts_from_jp === "number" && data.last_mqtt_ts_from_jp > 0) {
        lastMqttTsFrom = data.last_mqtt_ts_from_jp * 1000;
      }
      if (typeof data.last_mqtt_ts_to_jp === "number" && data.last_mqtt_ts_to_jp > 0) {
        lastMqttTsTo = data.last_mqtt_ts_to_jp * 1000;
      }
      return;
    }

    if (data.type !== "spot") return;
    // サーバ側でmodeフィルタ済みだが念のため
    if (data.mode && data.mode !== currentMode) return;

    lastData = Date.now();

    var b_value = parseInt((data.b || "").replace("m",""));
    var color = color_map[b_value] || 'gray';

    var lat = data.lat;
    var lon = data.lon;
    var timestamp = (typeof data.ts === "number") ? data.ts * 1000 : Date.now();

    var marker = L.circleMarker([lat, lon], {
      radius: 8,
      color: color,
      fillColor: color,
      fillOpacity: 0.8
    }).addTo(map);

    markers.push({marker: marker, timestamp: timestamp});
    cleanupMarkers();
  };
}

function disconnectWS() {
  if (!ws) return;
  try { ws.close(1000, "switch or hidden"); } catch (e) {}
  ws = null;
}

// ステータス表示更新
setInterval(function() {
  var now = Date.now();
  var hbStale = (now - lastHb > 30000);
  var mqttTs = (currentMode === "from_jp") ? lastMqttTsFrom : ((currentMode === "to_jp") ? lastMqttTsTo : lastMqttTsJq);
  var mqttStale = mqttTs ? (now - mqttTs > 30000) : true;
  var dataStale = (now - lastData > 30000);

  if (hbStale) {
    statusEl.textContent = "status: websocket down (no heartbeat)";
  } else if (mqttStale) {
    statusEl.textContent = "status: websocket ok, but no new MQTT data";
  } else if (dataStale) {
    statusEl.textContent = "status: websocket ok, but no spot messages";
  } else {
    statusEl.textContent = "status: receiving";
  }
}, 1000);

// モード切替：その瞬間に全削除→WS切断→WS再接続（過去3分をそのモードだけ再描画）
modeSelect.addEventListener("change", function() {
  currentMode = modeSelect.value;
  lastData = 0; // ステータスが「古い」判定にならないようリセット
  clearAll();
  disconnectWS();
  connectWS(currentMode);
});

if (!document.hidden) connectWS(currentMode);

document.addEventListener("visibilitychange", function() {
  if (document.hidden) {
    disconnectWS();
  } else {
    clearAll();
    disconnectWS();
    connectWS(currentMode);
  }
});
</script>
</body>
</html>
"""


# ==========================
# /my_dx (My Callsign Filter)
# ==========================
@app.get("/my_dx", response_class=HTMLResponse)
def index_my_dx():
    return r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>PSKReporter MyDX</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<style>
html, body { height: 100%; margin: 0; display: flex; flex-direction: column; }
#topbar { height: 50px; display:flex; flex-direction:row; }
#legend {
  flex: 1;
  background:#f0f0f0;
  display:flex;
  align-items:center;
  padding:5px 10px;
  font-family:sans-serif;
  overflow-x:auto;
}
#status {
  min-width: 560px;
  background:#222;
  color:#fff;
  font-family:sans-serif;
  font-size:12px;
  padding:5px 10px;
  display:flex;
  align-items:center;
  justify-content:flex-end;
  white-space: nowrap;
  gap: 8px;
}
#modeSelect { font-size: 12px; }
#mycallInput { font-size: 12px; width: 120px; }
#saveBtn { font-size: 12px; }
.legend-item { display:flex; align-items:center; margin-right:15px; }
.legend-color { width:20px; height:20px; margin-right:5px; }
#map { flex: 1; }
</style>
</head>
<body>
<div id="topbar">
  <div id="legend"></div>
  <div id="status">
    <a href="/dx" style="color:#aaa; margin-right:10px; text-decoration:none;">DX</a>
    <a href="/local" style="color:#aaa; margin-right:10px; text-decoration:none;">LOCAL</a>
    <a href="/my_dx" style="color:#0ff; margin-right:15px; text-decoration:none;">MY DX</a>

    <select id="modeSelect">
      <option value="from_jp">JP→World (match Sender Callsign)</option>
      <option value="to_jp">World→JP (match Receiver Callsign)</option>
    </select>

    <span style="color:#aaa;">MyCall:</span>
    <input id="mycallInput" placeholder="e.g. JQ3IKN" />
    <button id="saveBtn">Save</button>

    <span id="statusText">status: initializing...</span>
  </div>
</div>

<div id="map"></div>

<script>
function getCookie(name) {
  const m = document.cookie.match(
    new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()\[\]\/+^])/g, '\\$1') + '=([^;]*)')
  );
  return m ? decodeURIComponent(m[1]) : "";
}
function setCookie(name, value, days) {
  const maxAge = days ? ('; max-age=' + (days*24*60*60)) : '';
  document.cookie = name + '=' + encodeURIComponent(value) + maxAge + '; path=/; samesite=lax';
}

// map
var map = L.map('map',{
  minZoom: 3
}).setView([20, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { noWrap: true }).addTo(map);
map.setMaxBounds([[-90, -200], [90, 200]]);

// legend (band colors)
var color_map = {
  160: '#800000', 80:'#FF4500', 60:'#FF8C00', 40:'red', 30:'orange',
  20:'yellow', 17:'#ADFF2F', 15:'green', 12:'cyan', 10:'blue', 6:'#4B0082'
};
var legendDiv = document.getElementById("legend");
for (var key in color_map) {
  var item = document.createElement("div");
  item.className = "legend-item";
  var colorBox = document.createElement("div");
  colorBox.className = "legend-color";
  colorBox.style.backgroundColor = color_map[key];
  var label = document.createElement("span");
  label.textContent = key + "m";
  item.appendChild(colorBox);
  item.appendChild(label);
  legendDiv.appendChild(item);
}

var statusEl = document.getElementById("statusText");
var modeSelect = document.getElementById("modeSelect");
var mycallInput = document.getElementById("mycallInput");
var saveBtn = document.getElementById("saveBtn");

var COOKIE_KEY = "pskr_mycall";
var currentMode = modeSelect.value;
var mycall = (getCookie(COOKIE_KEY) || "").trim().toUpperCase();
mycallInput.value = mycall;

var markers = [];
var ws = null;

function clearAll() {
  markers.forEach(function(m){ map.removeLayer(m.marker); });
  markers = [];
}
function cleanupMarkers() {
  var now = Date.now();
  markers = markers.filter(function(m) {
    if (now - m.timestamp > 180000) {
      map.removeLayer(m.marker);
      return false;
    }
    return true;
  });
}
setInterval(cleanupMarkers, 10000);

function connectWS() {
  if (!mycall) {
    statusEl.textContent = "status: enter your callsign";
    return;
  }
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

  var proto = (location.protocol === "https:") ? "wss://" : "ws://";
  var url = proto + location.host + "/ws?mode=" + encodeURIComponent(currentMode)
          + "&mycall=" + encodeURIComponent(mycall);
  ws = new WebSocket(url);

  ws.onopen = function() { statusEl.textContent = "status: websocket connected"; };
  ws.onclose = function() { statusEl.textContent = "status: websocket closed"; };
  ws.onerror = function() { statusEl.textContent = "status: websocket error"; };

  ws.onmessage = function(event) {
    var data = JSON.parse(event.data);
    if (data.type !== "spot") return;
    if (data.mode && data.mode !== currentMode) return;

    var b_value = parseInt((data.b || "").replace("m",""));
    var color = color_map[b_value] || 'gray';
    var lat = data.lat;
    var lon = data.lon;
    var timestamp = (typeof data.ts === "number") ? data.ts * 1000 : Date.now();

    var marker = L.circleMarker([lat, lon], {
      radius: 8, color: color, fillColor: color, fillOpacity: 0.8
    }).addTo(map);

    markers.push({marker: marker, timestamp: timestamp});
    cleanupMarkers();
  };
}

function disconnectWS() {
  if (!ws) return;
  try { ws.close(1000, "switch or hidden"); } catch (e) {}
  ws = null;
}

function applyMyCall(newCall) {
  mycall = (newCall || "").trim().toUpperCase();
  mycallInput.value = mycall;
  if (!mycall) {
    setCookie(COOKIE_KEY, "", 0);
    clearAll();
    disconnectWS();
    statusEl.textContent = "status: enter your callsign";
    return;
  }
  setCookie(COOKIE_KEY, mycall, 365);
  clearAll();
  disconnectWS();
  connectWS();
}

saveBtn.addEventListener("click", function() { applyMyCall(mycallInput.value); });
mycallInput.addEventListener("keydown", function(e) { if (e.key === "Enter") applyMyCall(mycallInput.value); });

modeSelect.addEventListener("change", function() {
  currentMode = modeSelect.value;
  clearAll();
  disconnectWS();
  connectWS();
});

if (!mycall) {
  statusEl.textContent = "status: enter your callsign";
  mycallInput.focus();
} else {
  if (!document.hidden) connectWS();
}

document.addEventListener("visibilitychange", function() {
  if (document.hidden) disconnectWS();
  else {
    clearAll();
    disconnectWS();
    connectWS();
  }
});
</script>
</body>
</html>
"""


@app.get("/")
def redirect_root():
    return RedirectResponse(url="/dx", status_code=307)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
