// ui/static/dashboard.js

let _currentActiveExchangeId = null;

async function loadActiveExchangeAndList() {
  const sel = document.getElementById("exchange_id");
  const err = document.getElementById("exErr");
  const label = document.getElementById("activeExchangeLabel");

  if (err) setVisible(err, false);
  if (!sel) return null;

  sel.innerHTML = "";

  try {
    const res = await fetch("/api/active-exchange", { cache: "no-store" });
    const data = await res.json();

    if (data.error || !data.items || !data.items.length) {
      if (err) {
        err.textContent = "No configured exchanges found.";
        setVisible(err, true);
      }
      if (label) label.textContent = "—";
      setConnDot("fail");
      sel.innerHTML = `<option value="">(none)</option>`;
      _currentActiveExchangeId = null;
      return null;
    }

    sel.innerHTML = data.items.map(i => `<option value="${i.id}">${i.label}</option>`).join("");
    sel.value = data.active || data.items[0].id;

    const activeItem = data.items.find(i => i.id === sel.value);
    if (label) label.textContent = activeItem ? activeItem.label : sel.value;

    // remember current active
    _currentActiveExchangeId = sel.value;

    return data;

  } catch (e) {
    if (err) {
      err.textContent = "Failed to load exchanges.";
      setVisible(err, true);
    }
    if (label) label.textContent = "—";
    setConnDot("fail");
    sel.innerHTML = `<option value="">(error)</option>`;
    _currentActiveExchangeId = null;
    return null;
  }
}

async function setActiveExchange(exchangeId) {
  setConnDot("pending");

  const body = new URLSearchParams();
  body.set("exchange_id", exchangeId);

  const res = await fetch("/api/active-exchange", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString()
  });

  const data = await res.json();
  return !!data.ok;
}

async function loadBalances() {
  const body = document.getElementById("balBody");
  const err = document.getElementById("balErr");

  if (err) setVisible(err, false);
  if (!body) return;

  setConnDot("pending");

  body.innerHTML = `
    <tr><td colspan="3" style="color: var(--muted);">Checking connection...</td></tr>
  `;

  try {
    const res = await fetch("/api/balances", { cache: "no-store" });
    const data = await res.json();

    if (data.error) throw new Error(data.error);

    const rows = data.balances || [];
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="3" style="color: var(--muted);">No balances</td></tr>`;
      setConnDot("ok");
      return;
    }

    body.innerHTML = rows.map(r => `
      <tr>
        <td>${r.asset ?? ""}</td>
        <td>${fmtNum(r.free)}</td>
        <td>${fmtNum(r.locked)}</td>
      </tr>
    `).join("");

    setConnDot("ok");
  } catch (e) {
    if (err) {
      err.textContent = "Connection failed.";
      setVisible(err, true);
    }
    body.innerHTML = `<tr><td colspan="3" style="color: var(--muted);">No data</td></tr>`;
    setConnDot("fail");
  }
}

function emitActiveExchangeChanged(activeId) {
  document.dispatchEvent(
    new CustomEvent("accubot:active-exchange-changed", { detail: { active: activeId } })
  );
}

// init dashboard
async function initDashboard() {
  setConnDot("pending");

  await loadActiveExchangeAndList();

  // notify others (WS manager) what active exchange is on first load
  if (_currentActiveExchangeId) {
    emitActiveExchangeChanged(_currentActiveExchangeId);
  }

  await loadBalances();

  const form = document.getElementById("exchangeForm");
  if (form) {
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();

      const sel = document.getElementById("exchange_id");
      if (!sel?.value) return;

      // if user picked the same exchange, do nothing
      if (_currentActiveExchangeId === sel.value) return;

      const ok = await setActiveExchange(sel.value);
      if (ok) {
        _currentActiveExchangeId = sel.value;

        const label = document.getElementById("activeExchangeLabel");
        if (label) label.textContent = sel.options[sel.selectedIndex]?.text || sel.value;

        emitActiveExchangeChanged(sel.value);

        await loadBalances();
      }
    });
  }
}

// auto-run if dashboard elements exist
document.addEventListener("DOMContentLoaded", () => {
  const hasDashboard = document.getElementById("exchangeForm") && document.getElementById("balBody");
  if (hasDashboard) initDashboard();
});