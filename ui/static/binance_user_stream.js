// ui/static/binance_user_stream.js

let _userStreamWS = null;
let _userStreamReconnectTimer = null;

let _reconnectDelayMs = 1500;
let _streamStartedOnce = false;
let _keepaliveTimer = null;

function appendWsLog(line) {
  const el = document.getElementById("wsLog");
  if (!el) return;
  const ts = new Date().toLocaleTimeString();
  el.textContent = `[${ts}] ${line}\n` + el.textContent;
}

function clearWsLog() {
  const el = document.getElementById("wsLog");
  if (!el) return;
  el.textContent = "";
}

function stopKeepalive() {
  if (_keepaliveTimer) {
    clearInterval(_keepaliveTimer);
    _keepaliveTimer = null;
  }
}

function startKeepalive(env = "testnet") {
  stopKeepalive();
  _keepaliveTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/binance/user-stream/keepalive?env=${encodeURIComponent(env)}`, {
        method: "POST",
        cache: "no-store",
      });
      const data = await res.json();
      if (data?.ok) appendWsLog(`Keepalive OK (${env})`);
      else appendWsLog(`Keepalive error: ${data?.error || "unknown"}`);
    } catch (e) {
      appendWsLog("Keepalive failed: fetch_failed");
    }
  }, 25 * 60 * 1000);
}

async function ensureBinanceUserStreamStarted(env = "testnet") {
  try {
    const res = await fetch(`/api/binance/user-stream/start?env=${encodeURIComponent(env)}`, {
      method: "POST",
      cache: "no-store",
    });
    const data = await res.json();

    if (data.ok) {
      appendWsLog(`User stream started (${env})`);
      return true;
    }
    appendWsLog(`User stream start error: ${data.error || "unknown"}`);
    return false;
  } catch (e) {
    appendWsLog("User stream start failed: fetch_failed");
    return false;
  }
}

function closeUserStreamWS() {
  if (_userStreamReconnectTimer) {
    clearTimeout(_userStreamReconnectTimer);
    _userStreamReconnectTimer = null;
  }
  if (_userStreamWS) {
    try { _userStreamWS.close(); } catch (e) {}
    _userStreamWS = null;
  }
}

function connectUserStreamWS(env = "testnet") {
  closeUserStreamWS();
  if (typeof setConnDot === "function") setConnDot("pending");

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/binance/user-stream?env=${encodeURIComponent(env)}`;

  appendWsLog(`Connecting WS: ${url}`);
  _userStreamWS = new WebSocket(url);

  _userStreamWS.onopen = () => {
    appendWsLog("WS connected");
    _reconnectDelayMs = 1500;
  };

  _userStreamWS.onmessage = (ev) => {
    // log raw only if it's short
    // appendWsLog(`RAW: ${String(ev.data).slice(0, 200)}`);

    let msg;
    try { msg = JSON.parse(ev.data); }
    catch (e) {
      appendWsLog(`WS non-json: ${String(ev.data).slice(0, 200)}`);
      return;
    }

    if (msg.type === "hello") {
      appendWsLog(`HELLO: ${msg.msg || "ok"}`);
      return;
    }

    if (msg.type === "status") {
      const connected = !!msg.connected;
      const phase = msg.phase ? ` (${msg.phase})` : "";
      appendWsLog(`Status: ${connected ? "connected" : "not connected"} (${msg.env || env})${phase}`);
      if (typeof setConnDot === "function") setConnDot(connected ? "ok" : "fail");
      return;
    }

    if (msg.type === "error") {
      appendWsLog(`WS error: ${msg.error || "unknown"}`);
      if (typeof setConnDot === "function") setConnDot("fail");
      return;
    }

    if (msg.type === "binance_event") {
      const data = msg.data || {};
      const eventType = data.e || data.eventType || "unknown_event";
      appendWsLog(`Event: ${eventType}`);
      if (typeof setConnDot === "function") setConnDot("ok");

      if (eventType === "outboundAccountPosition" || eventType === "balanceUpdate") {
        setTimeout(() => {
          if (typeof loadBalances === "function") loadBalances();
        }, 400);
      }
      return;
    }

    appendWsLog(`WS message: ${JSON.stringify(msg).slice(0, 220)}`);
  };

  _userStreamWS.onclose = (ev) => {
    appendWsLog(`WS closed (code=${ev.code}, reason="${ev.reason || ""}") -> reconnect in ${Math.round(_reconnectDelayMs / 1000)}s`);
    if (typeof setConnDot === "function") setConnDot("fail");

    _userStreamReconnectTimer = setTimeout(() => {
      startBinanceUserStreamLive(env);
    }, _reconnectDelayMs);

    _reconnectDelayMs = Math.min(_reconnectDelayMs * 1.6, 20000);
  };

  _userStreamWS.onerror = () => {
    appendWsLog("WS error (socket)");
    if (typeof setConnDot === "function") setConnDot("fail");
  };
}

async function startBinanceUserStreamLive(env = "testnet") {
  if (typeof setConnDot === "function") setConnDot("pending");

  if (!_streamStartedOnce) {
    const ok = await ensureBinanceUserStreamStarted(env);
    if (!ok) {
      if (typeof setConnDot === "function") setConnDot("fail");
      stopKeepalive();
      closeUserStreamWS();
      return;
    }
    _streamStartedOnce = true;
    startKeepalive(env);
  }

  connectUserStreamWS(env);
}

function stopBinanceUserStream() {
  stopKeepalive();
  closeUserStreamWS();
  _streamStartedOnce = false;
  _reconnectDelayMs = 1500;
}

document.addEventListener("DOMContentLoaded", async () => {
  const isDashboard = document.getElementById("exchangeForm") && document.getElementById("balBody");
  if (!isDashboard) return;

  try {
    const res = await fetch("/api/active-exchange", { cache: "no-store" });
    const data = await res.json();
    if (data.active === "binance:testnet") {
      startBinanceUserStreamLive("testnet");
    }
  } catch (e) {
    // ignore
  }
});