/* Dedicated Worker — holds a WebSocket connection and buffers spots while paused */
'use strict';

const BUFFER_MS = 900 * 1000;  // 15 min — matches mydx server buffer

const MAX_RETRIES = 10;
const RECONNECT_BASE_MS = 5000;
const RECONNECT_MAX_MS = 60000;

let ws = null;
let connectUrl = null;
let buffer = [];
let paused = false;
let reconnectTimer = null;
let stopReconnect = false;  // set when server signals unavailable
let retryCount = 0;

function pruneBuffer() {
  var cutoff = Date.now() - BUFFER_MS;
  buffer = buffer.filter(function (d) { return (d.ts || 0) * 1000 >= cutoff; });
}

setInterval(pruneBuffer, 60000);

function clearReconnectTimer() {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function scheduleReconnect() {
  if (retryCount >= MAX_RETRIES) {
    console.warn('[ws-worker] max retries (' + MAX_RETRIES + ') reached, giving up');
    self.postMessage({ type: 'status', text: 'websocket reconnect failed (max retries)' });
    return;
  }
  clearReconnectTimer();
  var exp = Math.min(RECONNECT_BASE_MS * Math.pow(2, retryCount), RECONNECT_MAX_MS);
  var jitter = Math.random() * exp * 0.5;
  var delay = Math.round(exp * 0.5 + jitter);
  retryCount++;
  console.log('[ws-worker] reconnecting in ' + delay + 'ms (attempt ' + retryCount + '/' + MAX_RETRIES + ')...');
  reconnectTimer = setTimeout(function () {
    reconnectTimer = null;
    if (connectUrl) doConnect();
  }, delay);
}

function doConnect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  ws = new WebSocket(connectUrl);

  ws.onopen = function () {
    clearReconnectTimer();
    retryCount = 0;
    // Server will replay last 180s from SQLite — discard any stale buffer
    buffer = [];
    console.log('[ws-worker] connected:', connectUrl);
    self.postMessage({ type: 'status', text: 'websocket connected' });
  };

  ws.onclose = function (event) {
    console.log('[ws-worker] closed: code=' + event.code + ' reason=' + (event.reason || '(none)'));
    self.postMessage({ type: 'status', text: 'websocket closed' });
    if (connectUrl && !stopReconnect) scheduleReconnect();
  };

  ws.onerror = function () {
    console.error('[ws-worker] error');
    self.postMessage({ type: 'status', text: 'websocket error' });
  };

  ws.onmessage = function (event) {
    var data;
    try { data = JSON.parse(event.data); } catch (e) { return; }
    // Always forward heartbeats immediately — never buffer them
    if (data.type === 'hb') {
      self.postMessage(data);
      return;
    }
    if (paused) {
      buffer.push(data);
    } else {
      self.postMessage(data);
    }
  };
}

self.onmessage = function (e) {
  var msg = e.data;
  if (!msg || !msg.type) return;

  if (msg.type === 'connect') {
    connectUrl = msg.url;
    buffer = [];
    paused = false;
    stopReconnect = false;
    retryCount = 0;
    clearReconnectTimer();
    if (ws) {
      try { ws.close(1000, 'reconnect'); } catch (_) {}
      ws = null;
    }
    doConnect();

  } else if (msg.type === 'stopReconnect') {
    stopReconnect = true;
    connectUrl = null;
    clearReconnectTimer();
    if (ws) {
      try { ws.close(1000, 'unavailable'); } catch (_) {}
      ws = null;
    }
    buffer = [];

  } else if (msg.type === 'disconnect') {
    connectUrl = null;
    stopReconnect = false;
    clearReconnectTimer();
    if (ws) {
      try { ws.close(1000, 'disconnect'); } catch (_) {}
      ws = null;
    }
    buffer = [];
    paused = false;

  } else if (msg.type === 'pause') {
    console.log('[ws-worker] paused, buffering spots');
    paused = true;

  } else if (msg.type === 'resume') {
    paused = false;
    pruneBuffer();
    var buffered = buffer.splice(0);
    console.log('[ws-worker] resumed, flushing ' + buffered.length + ' buffered spot(s) (within 3min)');
    for (var i = 0; i < buffered.length; i++) {
      self.postMessage(buffered[i]);
    }
    // If WS dropped while paused, reconnect (server replay will fill the gap)
    if (connectUrl && (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING)) {
      doConnect();
    }
  }
};
