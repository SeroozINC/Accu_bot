// ui/static/prices_ticker.js

function fmtPrice(x) {
  if (x == null) return "—";
  return Number(x).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function fmtPct(x) {
  if (x == null) return "—";
  const n = Number(x);
  if (!isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function setPct(el, val) {
  if (!el) return;
  el.textContent = fmtPct(val);
  el.classList.remove("up", "down");
  if (val == null) return;
  if (Number(val) > 0) el.classList.add("up");
  else if (Number(val) < 0) el.classList.add("down");
}

async function refreshPrices() {
  try {
    const res = await fetch("/api/prices", { cache: "no-store" });
    const data = await res.json();

    const btc = document.getElementById("btc");
    const eth = document.getElementById("eth");
    const btc24 = document.getElementById("btc24");
    const eth24 = document.getElementById("eth24");
    const src = document.getElementById("src");

    if (btc) btc.textContent = fmtPrice(data.btc_usd);
    if (eth) eth.textContent = fmtPrice(data.eth_usd);
    setPct(btc24, data.btc_24h);
    setPct(eth24, data.eth_24h);

    if (src) {
      const s = data.source ? `${data.source} ${data.convert ?? ""}`.trim() : "";
      src.textContent = s || "—";
    }
  } catch (e) {
    // silent fail (no UI crash)
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Avoid errors on pages without ticker elements
  if (!document.getElementById("ticker")) return;
  refreshPrices();
  setInterval(refreshPrices, 10000);
});