
(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const today = () => new Date().toISOString().slice(0, 10);

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function withActionHeader(options = {}) {
    const next = { ...options };
    if (String(next.method || "GET").toUpperCase() === "POST") {
      const headers = new Headers(next.headers || {});
      headers.set("X-Baseball-Prop-Action", "1");
      next.headers = headers;
    }
    return next;
  }

  async function getJson(path, options = {}) {
    const response = await fetch(path, withActionHeader(options));
    const text = await response.text();
    let payload;
    try { payload = text ? JSON.parse(text) : {}; }
    catch { throw new Error(`Endpoint returned non-JSON. Status ${response.status}. First bytes: ${text.slice(0, 160)}`); }
    if (!response.ok) throw new Error(payload.error || payload.message || `Request failed: ${response.status}`);
    return payload;
  }

  const css = `
    @keyframes bpui-shimmer { 0% { background-position: -320px 0; } 100% { background-position: 320px 0; } }
    .bpui-skeleton { height: 14px; border-radius: 6px; margin: 8px 0; background: linear-gradient(90deg, var(--line) 25%, var(--field) 50%, var(--line) 75%); background-size: 640px 100%; animation: bpui-shimmer 1.2s ease infinite; }
    .bpui-skeleton.short { width: 48%; } .bpui-skeleton.medium { width: 72%; } .bpui-skeleton.long { width: 94%; }
    .bpui-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .bpui-table th, .bpui-table td { border-bottom: 1px solid var(--line); padding: 6px; text-align: left; vertical-align: top; }
    .bpui-table th { color: var(--muted); font-weight: 700; }
    .bpui-pill { display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--line); border-radius: 999px; padding: 2px 7px; margin: 2px; background: var(--card); }
    .bpui-success { color: var(--accent); font-weight: 700; } .bpui-error { color: #b91c1c; font-weight: 700; } .bpui-loading { color: var(--muted); font-style: italic; }
  `;
  if (!document.getElementById("bpui-styles")) {
    const style = document.createElement("style");
    style.id = "bpui-styles";
    style.textContent = css;
    document.head.appendChild(style);
  }

  function setLoading(btn, status, out, message) {
    if (btn) { btn.disabled = true; btn.dataset.originalText = btn.textContent; btn.textContent = "Loading…"; }
    if (status) { status.className = "model-note bpui-loading"; status.textContent = message; }
    if (out) out.innerHTML = '<div class="bpui-skeleton long"></div><div class="bpui-skeleton medium"></div><div class="bpui-skeleton short"></div><div class="bpui-skeleton long"></div>';
  }
  function clearLoading(btn) { if (btn) { btn.disabled = false; btn.textContent = btn.dataset.originalText || btn.textContent; delete btn.dataset.originalText; } }
  function setError(status, out, error) { if (status) { status.className = "model-note bpui-error"; status.textContent = `Error: ${error.message}`; } if (out) out.textContent = `Failed\n\n${error.message}`; }
  function setSuccess(status, message) { if (status) { status.className = "model-note bpui-success"; status.textContent = message; } }
  const odds = (value) => value == null || value === "" ? "--" : (Number(value) > 0 ? `+${Number(value)}` : String(Number(value)));
  const prob = (value) => value == null || value === "" ? "--" : `${(Number(value) * 100).toFixed(1)}%`;

  function renderGameContext(payload) {
    const games = payload.games || [];
    if (!games.length) return `<div>No game context found for ${escapeHtml(payload.date)}. Run OddsPapi backfill or choose a cached date.</div>`;
    return games.map((game) => {
      const favorite = game.moneyline?.favorite || {};
      const underdog = game.moneyline?.underdog || {};
      const markets = (game.marketsAvailable || []).map((m) => `<span class="bpui-pill">${escapeHtml(m.replaceAll("_", " "))}</span>`).join("");
      const totals = (game.gameTotals || []).slice(0, 4).map((row) => `${escapeHtml(row.bookmaker)} ${escapeHtml(row.outcomeName)} ${escapeHtml(row.line)} ${odds(row.americanOdds)}`).join("<br>");
      const firstInning = (game.firstInningTotals || []).slice(0, 4).map((row) => `${escapeHtml(row.bookmaker)} ${escapeHtml(row.outcomeName)} ${escapeHtml(row.line)} ${odds(row.americanOdds)}`).join("<br>");
      return `<section style="margin-bottom:14px; padding-bottom:12px; border-bottom:1px solid var(--line);">
        <strong>${escapeHtml((game.teams || []).join(" vs "))}</strong><br>
        <span class="model-note">Fixture ${escapeHtml(game.fixtureId)} · ${escapeHtml(game.startTime || game.date)}</span>
        <div>${markets}</div>
        <table class="bpui-table"><tbody>
          <tr><th>Favorite</th><td>${escapeHtml(favorite.team || "--")} ${odds(favorite.avgAmericanOdds)} (${prob(favorite.avgImpliedProbability)})</td></tr>
          <tr><th>Underdog</th><td>${escapeHtml(underdog.team || "--")} ${odds(underdog.avgAmericanOdds)} (${prob(underdog.avgImpliedProbability)})</td></tr>
          <tr><th>Game O/U</th><td>${totals || "--"}</td></tr>
          <tr><th>1st Inning O/U</th><td>${firstInning || "--"}</td></tr>
          <tr><th>Lineup status</th><td>${escapeHtml(game.lineupStatus?.note || "--")}</td></tr>
        </tbody></table>
      </section>`;
    }).join("");
  }

  function renderMarketRows(payload) {
    const rows = payload.rows || [];
    if (!rows.length) return `<div>No rows found. Try another date, market, team, or bookmaker.</div><pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
    return `<table class="bpui-table"><thead><tr><th>Date</th><th>Book</th><th>Market</th><th>Team</th><th>Line</th><th>Side</th><th>Odds</th><th>Imp%</th></tr></thead><tbody>${rows.map((row) => `
      <tr><td>${escapeHtml(row.date)}</td><td>${escapeHtml(row.bookmaker)}</td><td>${escapeHtml(row.marketLabel || row.market)}</td><td>${escapeHtml(row.team || "--")}${row.opponent ? ` vs ${escapeHtml(row.opponent)}` : ""}</td><td>${escapeHtml(row.line ?? "--")}</td><td>${escapeHtml(row.outcomeName || "--")}</td><td>${odds(row.americanOdds)}</td><td>${prob(row.impliedProbability)}</td></tr>
    `).join("")}</tbody></table>`;
  }

  function initGameContext() {
    const btn = $("#gameContextLoadButton");
    if (!btn) return;
    const date = $("#gameContextDate");
    const team = $("#gameContextTeam");
    const status = $("#gameContextStatus");
    const out = $("#gameContextOutput");
    if (date && !date.value) date.value = today();
    btn.addEventListener("click", async () => {
      const qs = new URLSearchParams({ season: "2026", date: date?.value || today(), team: team?.value || "", limit: "100" });
      setLoading(btn, status, out, "Loading lineup, game context, and market signals…");
      try {
        const payload = await getJson(`/api/game-context?${qs.toString()}`);
        setSuccess(status, `Loaded ${payload.gameCount || 0} game contexts from ${payload.sourceFiles?.length || 0} OddsPapi cache file(s).`);
        out.innerHTML = renderGameContext(payload);
      } catch (error) { setError(status, out, error); }
      finally { clearLoading(btn); }
    });
  }

  function initOddsSignals() {
    const btn = $("#oddsSignalsLoadButton");
    if (!btn) return;
    const date = $("#oddsSignalsDate");
    const market = $("#oddsSignalsMarket");
    const team = $("#oddsSignalsTeam");
    const book = $("#oddsSignalsBook");
    const contextDate = $("#gameContextDate");
    const contextTeam = $("#gameContextTeam");
    const status = $("#oddsSignalsStatus");
    const out = $("#oddsSignalsOutput");
    if (date && !date.value) date.value = today();
    btn.addEventListener("click", async () => {
      const selectedDate = date?.value || contextDate?.value || today();
      const selectedTeam = team?.value || contextTeam?.value || "";
      const qs = new URLSearchParams({ season: "2026", date: selectedDate, market: market?.value || "", team: selectedTeam, bookmaker: book?.value || "", limit: "300" });
      setLoading(btn, status, out, "Loading latest pregame market rows…");
      try {
        const payload = await getJson(`/api/odds-market-signals?${qs.toString()}`);
        setSuccess(status, `Loaded ${payload.returnedRows} of ${payload.rowCount} matching market rows.`);
        out.innerHTML = renderMarketRows(payload);
      } catch (error) { setError(status, out, error); }
      finally { clearLoading(btn); }
    });
  }



  async function renderMainBoardMarkets() {
    const mode = document.querySelector("#boardMode")?.value;
    const head = document.querySelector("#playerBoardHead");
    const body = document.querySelector("#playerRows");
    const search = document.querySelector("#search")?.value || "";
    if (mode !== "markets" || !head || !body) return;
    head.innerHTML = `<tr><th>Market</th><th>Team/Game</th><th>Book</th><th>Line</th><th>Side</th><th>Odds</th><th>Imp%</th><th>Date</th></tr>`;
    body.innerHTML = `<tr><td colspan="8"><div class="bpui-skeleton long"></div><div class="bpui-skeleton medium"></div></td></tr>`;
    try {
      const date = document.querySelector("#simpleDate")?.value || today();
      const qs = new URLSearchParams({ season: "2026", date, q: search, limit: "250" });
      const payload = await getJson(`/api/team-props?${qs.toString()}`);
      const rows = payload.rows || [];
      if (!rows.length) {
        body.innerHTML = `<tr><td colspan="8">No cached game/team market rows found for ${escapeHtml(date)}.</td></tr>`;
        return;
      }
      body.innerHTML = rows.map((row) => `<tr>
        <td>${escapeHtml(row.marketLabel || row.market)}</td>
        <td>${escapeHtml(row.team || "Game")}${row.opponent ? ` vs ${escapeHtml(row.opponent)}` : ""}</td>
        <td>${escapeHtml(row.bookmaker || "--")}</td>
        <td>${escapeHtml(row.line ?? "--")}</td>
        <td>${escapeHtml(row.outcomeName || "--")}</td>
        <td>${odds(row.americanOdds)}</td>
        <td>${prob(row.impliedProbability)}</td>
        <td>${escapeHtml(row.date || "--")}</td>
      </tr>`).join("");
    } catch (error) {
      body.innerHTML = `<tr><td colspan="8">Team/Game Markets failed: ${escapeHtml(error.message)}</td></tr>`;
    }
  }

  function initMainBoardMarkets() {
    const mode = document.querySelector("#boardMode");
    if (!mode) return;
    if (![...mode.options].some((option) => option.value === "markets")) {
      const option = document.createElement("option");
      option.value = "markets";
      option.textContent = "Team/Game Markets";
      mode.appendChild(option);
    }
    const searchInput = document.querySelector("#search");
    const syncSearchPlaceholder = () => {
      if (!searchInput) return;
      searchInput.placeholder = mode.value === "markets" ? "Search teams, markets, books" : "Search players";
    };
    const rerender = () => { syncSearchPlaceholder(); setTimeout(renderMainBoardMarkets, 0); };
    mode.addEventListener("change", rerender);
    searchInput?.addEventListener("input", rerender);
    document.querySelector("#simpleDate")?.addEventListener("change", rerender);
    syncSearchPlaceholder();
  }

  function init() {
    initGameContext();
    initOddsSignals();
    initMainBoardMarkets();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
