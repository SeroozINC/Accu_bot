// ui/static/app.js

function fmtNum(x) {
  if (x == null) return "0";
  const n = Number(x);
  if (!isFinite(n)) return "0";
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function setVisible(el, visible) {
  if (!el) return;
  el.style.display = visible ? "block" : "none";
}

// Connection indicator helper (expects CSS classes: conn-dot pending/green/red)
function setConnDot(state) {
  const dot = document.getElementById("exchangeStatus");
  if (!dot) return;

  dot.classList.remove("green", "red", "pending");

  if (state === "ok") {
    dot.classList.add("green");
    dot.title = "Connected";
  } else if (state === "fail") {
    dot.classList.add("red");
    dot.title = "Not connected";
  } else {
    dot.classList.add("pending");
    dot.title = "Checking...";
  }
}