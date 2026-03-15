/* SharedWorker — holds MQTT connections and buffers spots across page navigations */
'use strict';

importScripts('https://unpkg.com/mqtt/dist/mqtt.min.js');

const BUFFER_MS = 900 * 1000;  // 15 min

let mqttClient = null;
let currentMycall = '';
let spotBuffer = [];  // { data: {…raw mqtt payload + _ts}, ts: ms }
const ports = new Set();

function pruneBuffer() {
  const cutoff = Date.now() - BUFFER_MS;
  spotBuffer = spotBuffer.filter(function (s) { return s.ts >= cutoff; });
}

function broadcast(msg) {
  for (const port of ports) {
    try { port.postMessage(msg); } catch (e) { ports.delete(port); }
  }
}

function connectMqtt(mycall) {
  if (mqttClient) {
    try { mqttClient.end(true); } catch (e) {}
    mqttClient = null;
  }
  currentMycall = mycall;
  broadcast({ type: 'status', text: 'connecting to MQTT...' });

  const c = mqtt.connect('wss://mqtt.pskreporter.info:1886', {
    keepalive: 60,
    reconnectPeriod: 5000,
    clean: true,
  });
  mqttClient = c;

  c.on('connect', function () {
    console.log('[mqtt-worker] MQTT connected, mycall=' + mycall);
    broadcast({ type: 'status', text: 'MQTT connected' });
    c.subscribe('pskr/filter/v2/+/+/' + mycall + '/#');
    c.subscribe('pskr/filter/v2/+/+/+/' + mycall + '/#');
  });

  c.on('message', function (topic, payload) {
    try {
      const data = JSON.parse(payload.toString());
      data._ts = Date.now();
      pruneBuffer();
      spotBuffer.push({ data: data, ts: data._ts });
      broadcast({ type: 'spot', spot: data });
    } catch (e) {}
  });

  c.on('error', function (err) {
    console.error('[mqtt-worker] MQTT error:', err);
    broadcast({ type: 'status', text: 'MQTT error: ' + (err && err.message) });
  });

  c.on('close', function () {
    console.log('[mqtt-worker] MQTT connection closed, mycall=' + mycall);
    broadcast({ type: 'status', text: 'MQTT disconnected' });
  });
}

function disconnectMqtt() {
  if (mqttClient) {
    try { mqttClient.end(true); } catch (e) {}
    mqttClient = null;
  }
  currentMycall = '';
  spotBuffer = [];
}

self.onconnect = function (event) {
  const port = event.ports[0];
  ports.add(port);

  port.onmessage = function (e) {
    const msg = e.data;
    if (!msg || !msg.type) return;

    if (msg.type === 'setMycall') {
      const newCall = (msg.mycall || '').toUpperCase();
      if (newCall !== currentMycall) {
        spotBuffer = [];
        connectMqtt(newCall);
      }
      pruneBuffer();
      port.postMessage({ type: 'replay', spots: spotBuffer.map(function (s) { return s.data; }) });
    } else if (msg.type === 'clearMycall') {
      disconnectMqtt();
    }
    // 'ping' messages keep the port alive; no action needed
  };
};
