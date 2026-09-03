const DATA_URL = "data/opportunities.json";

const els = {
  updated: document.getElementById("updated"),
  sideFilter: document.getElementById("sideFilter"),
  maxNoPrice: document.getElementById("maxNoPrice"),
  maxYesPct: document.getElementById("maxYesPct"),
  minEdge: document.getElementById("minEdge"),
  minLiq: document.getElementById("minLiq"),
  cityFilter: document.getElementById("cityFilter"),
  dateFilter: document.getElementById("dateFilter"),
  kindFilter: document.getElementById("kindFilter"),
  resultCount: document.getElementById("resultCount"),
  hintText: document.getElementById("hintText"),
  oppBody: document.getElementById("oppBody"),
};

let rows = [];

function pct(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function cents(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(1)}¢`;
}

function fmtEdge(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(1)}¢`;
}

function fmtMoney(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function toWinPerDollar(buyPrice) {
  if (buyPrice == null || buyPrice <= 0) return "—";
  return `$${(1 / buyPrice).toFixed(2)}`;
}

function marketYes(row) {
  if (row.yesPrice != null) return row.yesPrice;
  if (row.bestAsk != null) return row.bestAsk;
  return null;
}

function fillSelect(select, values, allLabel) {
  const current = select.value;
  select.innerHTML = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = allLabel;
  select.appendChild(all);
  for (const value of values) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    select.appendChild(opt);
  }
  if ([...select.options].some((o) => o.value === current)) {
    select.value = current;
  }
}

function updateHint() {
  const side = els.sideFilter.value;
  if (side === "NO") {
    els.hintText.textContent =
      "Buy No edge = model P(not bucket) − Buy No price (≈ 1 − YES bid). Filter for low YES % with No at max price or cheaper — like Shanghai 28°C at ~95¢.";
  } else if (side === "YES") {
    els.hintText.textContent =
      "Buy Yes edge = model P(bucket) − Buy Yes price. Positive means the model is higher than the market ask.";
  } else {
    els.hintText.textContent =
      "Showing both sides. Edge is vs the selected buy price for that side.";
  }
}

function filteredRows() {
  const side = els.sideFilter.value;
  const maxNo = Number(els.maxNoPrice.value);
  const maxYes = Number(els.maxYesPct.value) / 100;
  const minEdge = Number(els.minEdge.value) || 0;
  const minLiq = Number(els.minLiq.value) || 0;
  const city = els.cityFilter.value;
  const date = els.dateFilter.value;
  const kind = els.kindFilter.value;

  return rows
    .filter((row) => {
      const rowSide = row.side || "YES";
      if (side && rowSide !== side) return false;
      if ((row.edge ?? 0) < minEdge) return false;
      if ((row.liquidity ?? 0) < minLiq) return false;
      if (city && row.city !== city) return false;
      if (date && row.date !== date) return false;
      if (kind && row.kind !== kind) return false;

      if (rowSide === "NO") {
        const buy = row.buyPrice ?? row.noPrice;
        if (Number.isFinite(maxNo) && buy != null && buy > maxNo) return false;
        const mYes = marketYes(row);
        if (Number.isFinite(maxYes) && mYes != null && mYes > maxYes) return false;
      }
      return true;
    })
    .sort((a, b) => (b.edge ?? 0) - (a.edge ?? 0));
}

function render() {
  updateHint();
  const visible = filteredRows();
  els.resultCount.textContent = `${visible.length} opportunities`;

  if (!visible.length) {
    els.oppBody.innerHTML =
      '<tr><td colspan="13" class="empty">No rows match the current filters.</td></tr>';
    return;
  }

  const html = visible
    .map((row) => {
      const side = row.side || "YES";
      const edge = row.edge ?? 0;
      const buy = row.buyPrice ?? (side === "NO" ? row.noPrice : row.bestAsk ?? row.yesPrice);
      const hot = edge >= 0.05 && (row.liquidity ?? 0) >= 100;
      const edgeClass = edge >= 0 ? "edge-pos" : "edge-neg";
      const rowClass = hot ? (side === "NO" ? "hot-no" : "hot") : "";
      const mean =
        row.forecastMean != null
          ? `${row.forecastMean.toFixed(1)}°${row.unit || ""}`
          : "—";
      return `<tr class="${rowClass}">
        <td><span class="side-pill side-${side.toLowerCase()}">${side}</span></td>
        <td>${escapeHtml(row.city)}</td>
        <td>${escapeHtml(row.date)}</td>
        <td><span class="kind-pill kind-${escapeHtml(row.kind)}">${escapeHtml(row.kind)}</span></td>
        <td>${escapeHtml(row.bucket)}</td>
        <td>${pct(row.modelProb)}</td>
        <td>${pct(marketYes(row))}</td>
        <td>${cents(buy)}</td>
        <td class="${edgeClass}">${fmtEdge(edge)}</td>
        <td>${toWinPerDollar(buy)}</td>
        <td>${fmtMoney(row.liquidity)}</td>
        <td>${escapeHtml(mean)}</td>
        <td><a class="market-link" href="${escapeAttr(row.url)}" target="_blank" rel="noopener noreferrer">Open</a></td>
      </tr>`;
    })
    .join("");

  els.oppBody.innerHTML = html;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("'", "&#39;");
}

async function load() {
  try {
    const bust = Date.now();
    const res = await fetch(`${DATA_URL}?t=${bust}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    rows = Array.isArray(data.opportunities) ? data.opportunities : [];

    // Back-compat: old snapshots without side are YES rows
    rows = rows.map((r) => ({ ...r, side: r.side || "YES" }));

    const cities = [...new Set(rows.map((r) => r.city).filter(Boolean))].sort();
    const dates = [...new Set(rows.map((r) => r.date).filter(Boolean))].sort();
    fillSelect(els.cityFilter, cities, "All cities");
    fillSelect(els.dateFilter, dates, "All dates");

    const generatedAt = data.generatedAt
      ? new Date(data.generatedAt).toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        })
      : "unknown";
    const stats = data.stats || {};
    const noCount = rows.filter((r) => r.side === "NO").length;
    els.updated.textContent = `Updated ${generatedAt} · ${rows.length} rows (${noCount} Buy No) · ${stats.eventsScored ?? "—"} events`;
    render();
  } catch (err) {
    console.error(err);
    els.updated.textContent = "Failed to load data snapshot.";
    els.oppBody.innerHTML =
      '<tr><td colspan="13" class="empty">Could not load data/opportunities.json. Run <code>python scripts/refresh.py</code> locally or wait for the Actions refresh.</td></tr>';
  }
}

const filterEls = [
  els.sideFilter,
  els.maxNoPrice,
  els.maxYesPct,
  els.minEdge,
  els.minLiq,
  els.cityFilter,
  els.dateFilter,
  els.kindFilter,
];
for (const el of filterEls) {
  el.addEventListener("input", render);
  el.addEventListener("change", render);
}

load();
