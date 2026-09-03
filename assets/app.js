const DATA_URL = "data/opportunities.json";

const els = {
  updated: document.getElementById("updated"),
  minEdge: document.getElementById("minEdge"),
  minLiq: document.getElementById("minLiq"),
  cityFilter: document.getElementById("cityFilter"),
  dateFilter: document.getElementById("dateFilter"),
  kindFilter: document.getElementById("kindFilter"),
  resultCount: document.getElementById("resultCount"),
  oppBody: document.getElementById("oppBody"),
};

let rows = [];

function pct(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
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

function marketPrice(row) {
  if (row.bestAsk != null) return row.bestAsk;
  return row.yesPrice;
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

function filteredRows() {
  const minEdge = Number(els.minEdge.value) || 0;
  const minLiq = Number(els.minLiq.value) || 0;
  const city = els.cityFilter.value;
  const date = els.dateFilter.value;
  const kind = els.kindFilter.value;

  return rows.filter((row) => {
    if (Math.abs(row.edge ?? 0) < minEdge) return false;
    if ((row.liquidity ?? 0) < minLiq) return false;
    if (city && row.city !== city) return false;
    if (date && row.date !== date) return false;
    if (kind && row.kind !== kind) return false;
    return true;
  });
}

function render() {
  const visible = filteredRows();
  els.resultCount.textContent = `${visible.length} opportunities`;

  if (!visible.length) {
    els.oppBody.innerHTML =
      '<tr><td colspan="10" class="empty">No rows match the current filters.</td></tr>';
    return;
  }

  const html = visible
    .map((row) => {
      const edge = row.edge ?? 0;
      const hot = Math.abs(edge) >= 0.08 && (row.liquidity ?? 0) >= 200;
      const edgeClass = edge >= 0 ? "edge-pos" : "edge-neg";
      const rowClass = hot ? (edge >= 0 ? "hot" : "cold") : "";
      const mean =
        row.forecastMean != null
          ? `${row.forecastMean.toFixed(1)}°${row.unit || ""}`
          : "—";
      return `<tr class="${rowClass}">
        <td>${escapeHtml(row.city)}</td>
        <td>${escapeHtml(row.date)}</td>
        <td><span class="kind-pill kind-${escapeHtml(row.kind)}">${escapeHtml(row.kind)}</span></td>
        <td>${escapeHtml(row.bucket)}</td>
        <td>${pct(row.modelProb)}</td>
        <td>${pct(marketPrice(row))}</td>
        <td class="${edgeClass}">${fmtEdge(edge)}</td>
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
    els.updated.textContent = `Updated ${generatedAt} · ${rows.length} scored buckets · ${stats.eventsScored ?? "—"} events`;
    render();
  } catch (err) {
    console.error(err);
    els.updated.textContent = "Failed to load data snapshot.";
    els.oppBody.innerHTML =
      '<tr><td colspan="10" class="empty">Could not load data/opportunities.json. Run <code>python scripts/refresh.py</code> locally or wait for the Actions refresh.</td></tr>';
  }
}

for (const el of [els.minEdge, els.minLiq, els.cityFilter, els.dateFilter, els.kindFilter]) {
  el.addEventListener("input", render);
  el.addEventListener("change", render);
}

load();
