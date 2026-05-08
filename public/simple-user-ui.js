(() => {
  const MARKETS = [
    ["batter_hits", "Batter Hits"],
    ["batter_hits_alt", "Batter Hits Ladder"],
    ["batter_total_bases", "Batter Total Bases"],
    ["batter_total_bases_alt", "Batter Total Bases Ladder"],
    ["batter_home_runs", "Batter Home Runs"],
    ["batter_home_runs_alt", "Batter Home Runs Alt"],
    ["pitcher_strikeouts", "Pitcher Strikeouts"],
    ["pitcher_strikeouts_alt", "Pitcher Strikeouts Ladder"],
    ["pitcher_hits_allowed", "Pitcher Hits Allowed"],
    ["pitcher_hits_allowed_alt", "Pitcher Hits Allowed Ladder"],
    ["pitcher_earned_runs", "Pitcher Earned Runs"],
    ["pitcher_earned_runs_alt", "Pitcher Earned Runs Ladder"],
    ["moneyline", "Moneyline"],
    ["moneyline_first_five", "Moneyline First Five"],
    ["run_line", "Run Line"],
    ["run_line_first_five", "Run Line First Five"],
    ["run_line_first_inning", "Run Line First Inning"],
    ["game_total_runs", "Game Total Runs"],
    ["first_five_total_runs", "First Five Total Runs"],
    ["first_inning_total_runs", "First Inning Total Runs"],
    ["team_total_runs", "Team Total Runs"],
    ["team_first_to_score", "Team First To Score"],
  ];

  const TEAM_GAME_MARKETS = new Set([
    "moneyline",
    "moneyline_first_five",
    "run_line",
    "run_line_first_five",
    "run_line_first_inning",
    "game_total_runs",
    "first_five_total_runs",
    "first_inning_total_runs",
    "team_total_runs",
    "team_first_to_score",
  ]);

  const $ = (selector) => document.querySelector(selector);

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function clean(value) {
    return String(value ?? "").trim();
  }

  function display(value, fallback = "Not available") {
    const text = clean(value);
    return text ? text : fallback;
  }

  function displayPct(value, fallback = "Not available") {
    const text = clean(value);
    return text ? `${text}%` : fallback;
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
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`Endpoint returned non-JSON. Status ${response.status}. First text: ${text.slice(0, 160)}`);
    }

    if (!response.ok) throw new Error(payload.error || `Request failed ${response.status}`);
    return payload;
  }

  function signed(value) {
    const n = Number(value || 0);
    return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
  }

  function marketLabel(value) {
    const found = MARKETS.find(([key]) => key === value);
    return found ? found[1] : value;
  }

  function playerboardMarketLabel(row) {
    const display = clean(row && row.marketDisplay);
    if (display) return display;
    return marketLabel(row && row.market);
  }


  function recClass(value) {
    const text = String(value || "").toLowerCase();
    if (text.includes("strong")) return "strong";
    if (text.includes("positive")) return "positive";
    if (text.includes("avoid")) return "avoid";
    return "neutral";
  }


  function ensurePlayerboardReadabilityStyles() {
    if (document.getElementById("playerboardReadabilityStyles")) return;

    const style = document.createElement("style");
    style.id = "playerboardReadabilityStyles";
    style.textContent = `
      :root {
        --bp-ink: #0f172a;
        --bp-muted: #64748b;
        --bp-border: rgba(148, 163, 184, 0.24);
        --bp-primary: #2563eb;
        --bp-primary-dark: #1d4ed8;
        --bp-green-bg: #dcfce7;
        --bp-green-text: #166534;
        --bp-card-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
        --bp-soft-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
      }

      body {
        background:
          radial-gradient(circle at top, rgba(59, 130, 246, 0.08), transparent 34rem),
          linear-gradient(180deg, #f8fbff 0%, #eef4ff 100%);
      }

      .muse-app {
        width: min(1180px, calc(100vw - 40px));
        margin-inline: auto;
      }

      .muse-shell,
      .muse-top-playerboard,
      .muse-result {
        border: 1px solid var(--bp-border);
        border-radius: 28px;
        box-shadow: var(--bp-card-shadow);
        background: rgba(255, 255, 255, 0.94);
        backdrop-filter: blur(12px);
      }

      .muse-shell {
        padding: 34px;
      }

      .muse-brand {
        gap: 18px;
        margin-bottom: 26px;
      }

      .muse-brand h1 {
        font-size: clamp(2rem, 3vw, 2.75rem);
        letter-spacing: -0.045em;
        line-height: 0.96;
        color: var(--bp-ink);
      }

      .muse-brand p,
      .muse-top-playerboard p {
        color: var(--bp-muted);
        font-size: 0.95rem;
      }

      .muse-logo {
        border-radius: 18px;
        box-shadow: 0 12px 24px rgba(15, 23, 42, 0.18);
      }

      .muse-search-row,
      .muse-prop-controls,
      .muse-top-playerboard-controls {
        gap: 14px;
      }

      .muse-search-box input,
      .muse-date,
      .muse-prop-controls input,
      .muse-prop-controls select,
      .muse-top-playerboard-controls input,
      .muse-top-playerboard-controls select {
        min-height: 46px;
        border-radius: 16px;
        border: 1px solid rgba(148, 163, 184, 0.32);
        background: rgba(255, 255, 255, 0.96);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
      }

      .muse-prop-controls label,
      .muse-top-playerboard-controls label {
        color: #475569;
        font-size: 0.75rem;
        font-weight: 800;
        letter-spacing: 0.02em;
      }

      .muse-actions button,
      .muse-secondary,
      .muse-board-actions button,
      #topPlayerboardLoad {
        border-radius: 15px;
        font-weight: 800;
      }

      .muse-actions button:not(.muse-secondary),
      #topPlayerboardLoad {
        background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%);
        box-shadow: 0 12px 24px rgba(37, 99, 235, 0.24);
      }

      .muse-secondary {
        background: #eef4ff;
        color: #1d4ed8;
        border: 1px solid #c7d7fe;
        box-shadow: none;
      }

      .muse-top-playerboard {
        margin-top: 28px;
        padding: 28px;
      }

      .muse-top-playerboard-head h2 {
        font-size: clamp(1.55rem, 2.2vw, 2rem);
        letter-spacing: -0.04em;
        color: var(--bp-ink);
      }

      .muse-top-playerboard-controls {
        display: grid;
        grid-template-columns: minmax(240px, 1fr) minmax(160px, 220px) minmax(120px, 160px);
        align-items: end;
        margin-top: 18px;
      }

      .muse-status {
        color: var(--bp-muted);
        font-size: 0.9rem;
      }

      .muse-playerboard-count {
        margin: 14px 0 10px;
        color: var(--bp-muted);
        text-align: center;
        font-size: 0.9rem;
      }

      .muse-playerboard-table-wrap {
        width: 100%;
        overflow-x: auto;
        border-radius: 18px;
        border: 1px solid rgba(148, 163, 184, 0.22);
        background: #ffffff;
        box-shadow: var(--bp-soft-shadow);
      }

      .muse-playerboard-table {
        width: 100%;
        min-width: 1020px;
        table-layout: fixed;
        border-collapse: separate;
        border-spacing: 0;
      }

      .muse-playerboard-table th {
        padding: 12px 14px;
        background: #f8fafc;
        color: #475569;
        font-size: 0.72rem;
        font-weight: 900;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        border-bottom: 1px solid rgba(148, 163, 184, 0.22);
        white-space: nowrap;
      }

      .muse-playerboard-table td {
        padding: 14px;
        vertical-align: middle;
        border-bottom: 1px solid rgba(226, 232, 240, 0.9);
        color: #172033;
        font-size: 0.9rem;
      }

      .muse-playerboard-table tbody tr:hover {
        background: #f8fbff;
      }

      .muse-playerboard-table .pb-player {
        width: 240px;
      }

      .pb-player-main {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .pb-player-main strong {
        color: var(--bp-ink);
        font-size: 0.95rem;
        letter-spacing: -0.015em;
      }

      .pb-player-main span,
      .pb-market-main span {
        color: var(--bp-muted);
        font-size: 0.78rem;
      }

      .muse-playerboard-table .pb-market {
        width: 250px;
      }

      .pb-market-main {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }

      .pb-market-main strong {
        color: #1e293b;
        font-size: 0.88rem;
      }

      .muse-playerboard-table .pb-line,
      .muse-playerboard-table .pb-prob,
      .muse-playerboard-table .pb-edge,
      .muse-playerboard-table .pb-conf,
      .muse-playerboard-table .pb-odds {
        width: 110px;
        text-align: right;
        white-space: nowrap;
      }

      .muse-playerboard-table .pb-rec {
        width: 150px;
      }

      .muse-playerboard-table .pb-actions {
        width: 132px;
      }

      .pb-pill {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 28px;
        padding: 6px 10px;
        border-radius: 999px;
        font-weight: 900;
        font-size: 0.78rem;
        line-height: 1;
        white-space: nowrap;
      }

      .pb-pill.edge {
        background: var(--bp-green-bg);
        color: var(--bp-green-text);
      }

      .pb-pill.prob {
        background: #eef4ff;
        color: #1d4ed8;
      }

      .pb-pill.conf {
        background: #f1f5f9;
        color: #334155;
      }

      .pb-pill.odds {
        background: #fff7ed;
        color: #9a3412;
        font-variant-numeric: tabular-nums;
      }

      .pb-rec-text {
        display: inline-block;
        max-width: 140px;
        color: #334155;
        font-size: 0.8rem;
        line-height: 1.25;
        overflow-wrap: anywhere;
      }

      .muse-board-actions {
        display: flex;
        gap: 7px;
        justify-content: flex-end;
        flex-wrap: nowrap;
      }

      .muse-board-actions button {
        min-height: 32px;
        padding: 7px 10px;
        font-size: 0.76rem;
        line-height: 1;
        box-shadow: none;
      }

      .muse-result {
        margin-top: 30px;
        overflow: hidden;
      }

      .muse-result:not(.empty) {
        padding: 0;
      }

      .muse-result .muse-empty {
        padding: 34px;
      }

      .muse-tab {
        border-radius: 12px;
      }

      .muse-mini-metric,
      .muse-overview-stat-grid > div,
      .muse-stat-grid > div {
        border-radius: 16px;
        background: #f8fafc;
        border: 1px solid rgba(226, 232, 240, 0.82);
      }






      /* Premium form and matchup polish v6 */
      .muse-search-row {
        display: grid;
        grid-template-columns: minmax(320px, 1fr) minmax(150px, 190px) auto;
        align-items: center;
        margin-top: 22px;
      }

      .muse-search-box {
        position: relative;
      }

      .muse-search-box input {
        width: 100%;
        padding-left: 22px;
        padding-right: 22px;
        font-size: 1rem;
        font-weight: 850;
        color: var(--bp-ink);
      }

      .muse-date {
        font-weight: 850;
        color: var(--bp-ink);
      }

      #simpleAutofill {
        min-height: 46px;
        padding-inline: 20px;
      }

      .muse-autofill-summary {
        margin-top: 16px;
        padding: 16px 18px;
        border-radius: 18px;
        border: 1px solid rgba(148, 163, 184, 0.18);
        background:
          radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), transparent 18rem),
          linear-gradient(180deg, #f8fbff 0%, #f1f5f9 100%);
        color: #334155;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.82);
      }

      .muse-autofill-summary strong {
        display: block;
        color: var(--bp-ink);
        font-size: 0.95rem;
        font-weight: 950;
        letter-spacing: -0.015em;
        margin-bottom: 5px;
      }

      .muse-autofill-summary span {
        display: block;
        color: #475569;
        font-size: 0.9rem;
        font-weight: 650;
      }

      .muse-prop-controls {
        display: grid;
        grid-template-columns: minmax(180px, 1.3fr) minmax(90px, 0.55fr) minmax(100px, 0.65fr) minmax(88px, 0.55fr) minmax(88px, 0.55fr) minmax(160px, 1fr);
        align-items: end;
        margin-top: 16px;
      }

      .muse-prop-controls label,
      .muse-top-playerboard-controls label {
        display: grid;
        gap: 6px;
      }

      .muse-prop-controls input,
      .muse-prop-controls select {
        color: var(--bp-ink);
        font-weight: 850;
      }

      .muse-search-box input:focus,
      .muse-date:focus,
      .muse-prop-controls input:focus,
      .muse-prop-controls select:focus,
      .muse-top-playerboard-controls input:focus,
      .muse-top-playerboard-controls select:focus {
        outline: none;
        border-color: rgba(37, 99, 235, 0.52);
        box-shadow:
          0 0 0 4px rgba(37, 99, 235, 0.10),
          inset 0 1px 0 rgba(255, 255, 255, 0.92);
      }

      .muse-actions {
        margin-top: 22px;
        gap: 12px;
      }

      .muse-actions button {
        min-height: 52px;
        padding-inline: 30px;
      }

      #simpleAnalyze {
        min-width: 170px;
      }

      #simpleSave {
        min-width: 170px;
      }

      #simpleSave:disabled {
        opacity: 0.55;
        cursor: not-allowed;
        filter: grayscale(0.2);
      }

      #simpleStatus {
        margin-top: 12px;
        min-height: 22px;
        font-weight: 700;
      }

      @media (max-width: 900px) {
        .muse-search-row {
          grid-template-columns: 1fr;
        }

        .muse-prop-controls {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .muse-actions {
          display: grid;
          grid-template-columns: 1fr;
        }

        .muse-actions button,
        #simpleAnalyze,
        #simpleSave {
          width: 100%;
          min-width: 0;
        }
      }

      @media (max-width: 560px) {
        .muse-prop-controls {
          grid-template-columns: 1fr;
        }
      }

      /* Premium live app status strip v5 */
      .muse-live-status-strip {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
        margin: 0 0 18px;
      }

      .muse-live-status-item {
        display: flex;
        align-items: center;
        gap: 10px;
        min-height: 52px;
        padding: 11px 13px;
        border-radius: 18px;
        border: 1px solid rgba(148, 163, 184, 0.22);
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
        min-width: 0;
      }

      .muse-live-dot {
        width: 10px;
        height: 10px;
        flex: 0 0 auto;
        border-radius: 999px;
        background: #22c55e;
        box-shadow: 0 0 0 5px rgba(34, 197, 94, 0.12);
      }

      .muse-live-status-item.warn .muse-live-dot {
        background: #f59e0b;
        box-shadow: 0 0 0 5px rgba(245, 158, 11, 0.14);
      }

      .muse-live-status-item.bad .muse-live-dot {
        background: #ef4444;
        box-shadow: 0 0 0 5px rgba(239, 68, 68, 0.13);
      }

      .muse-live-status-copy {
        min-width: 0;
      }

      .muse-live-status-copy strong {
        display: block;
        color: var(--bp-ink);
        font-size: 0.82rem;
        font-weight: 950;
        letter-spacing: -0.01em;
      }

      .muse-live-status-copy span {
        display: block;
        margin-top: 2px;
        color: var(--bp-muted);
        font-size: 0.74rem;
        font-weight: 750;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
      }

      @media (max-width: 900px) {
        .muse-live-status-strip {
          grid-template-columns: 1fr;
        }
      }

      /* Premium navigation/page shell polish v4 */
      header,
      nav,
      .sidebar,
      .app-sidebar,
      .muse-sidebar,
      .top-nav,
      .app-nav {
        border-color: rgba(148, 163, 184, 0.22) !important;
      }

      nav a,
      nav button,
      .sidebar a,
      .sidebar button,
      .app-sidebar a,
      .app-sidebar button,
      .muse-sidebar a,
      .muse-sidebar button,
      .top-nav a,
      .top-nav button,
      .app-nav a,
      .app-nav button {
        border-radius: 14px !important;
        transition: background 160ms ease, color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
      }

      nav a:hover,
      nav button:hover,
      .sidebar a:hover,
      .sidebar button:hover,
      .app-sidebar a:hover,
      .app-sidebar button:hover,
      .muse-sidebar a:hover,
      .muse-sidebar button:hover,
      .top-nav a:hover,
      .top-nav button:hover,
      .app-nav a:hover,
      .app-nav button:hover {
        background: #eef4ff !important;
        color: #1d4ed8 !important;
        transform: translateY(-1px);
      }

      nav a.active,
      nav button.active,
      nav [aria-current="page"],
      .sidebar a.active,
      .sidebar button.active,
      .app-sidebar a.active,
      .app-sidebar button.active,
      .muse-sidebar a.active,
      .muse-sidebar button.active,
      .top-nav a.active,
      .top-nav button.active,
      .app-nav a.active,
      .app-nav button.active {
        background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        box-shadow: 0 12px 24px rgba(37, 99, 235, 0.22) !important;
      }

      main,
      .app-main,
      .main-content,
      .container {
        padding-top: 24px;
      }

      .muse-app::before {
        content: "Premium MLB prop analytics";
        display: inline-flex;
        align-items: center;
        min-height: 30px;
        margin: 0 0 14px 4px;
        padding: 7px 12px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid rgba(148, 163, 184, 0.22);
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.045);
        color: #475569;
        font-size: 0.76rem;
        font-weight: 900;
        letter-spacing: 0.05em;
        text-transform: uppercase;
      }

      .muse-brand {
        position: relative;
      }

      .muse-brand::after {
        content: "Live board | Matchup context | Model edge";
        display: inline-flex;
        align-items: center;
        width: fit-content;
        margin-top: 10px;
        padding: 7px 11px;
        border-radius: 999px;
        background: rgba(248, 250, 252, 0.92);
        border: 1px solid rgba(226, 232, 240, 0.92);
        color: #64748b;
        font-size: 0.72rem;
        font-weight: 850;
        letter-spacing: 0.01em;
        white-space: nowrap;
      }

      .muse-shell,
      .muse-top-playerboard,
      .muse-result {
        position: relative;
      }

      .muse-shell::before,
      .muse-top-playerboard::before,
      .muse-result::before {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: inherit;
        pointer-events: none;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
      }

      @media (max-width: 900px) {
        .muse-app::before {
          margin-left: 0;
        }

        .muse-brand::after {
          font-size: 0.72rem;
        }
      }

      /* Premium ranked Playerboard card/list view v3 */
      .muse-playerboard-card-list {
        display: grid;
        gap: 14px;
        margin-top: 14px;
      }

      .muse-playerboard-pick-card {
        display: grid;
        grid-template-columns: 48px minmax(0, 1fr) auto;
        gap: 16px;
        align-items: center;
        padding: 18px;
        border-radius: 22px;
        border: 1px solid rgba(148, 163, 184, 0.22);
        background:
          radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), transparent 18rem),
          linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
        transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
      }

      .muse-playerboard-pick-card:hover {
        transform: translateY(-1px);
        border-color: rgba(37, 99, 235, 0.28);
        box-shadow: 0 18px 42px rgba(15, 23, 42, 0.09);
      }

      .muse-playerboard-pick-card.top-three {
        border-color: rgba(37, 99, 235, 0.32);
        box-shadow: 0 18px 44px rgba(37, 99, 235, 0.10);
      }

      .pb-rank {
        width: 42px;
        height: 42px;
        display: grid;
        place-items: center;
        border-radius: 15px;
        background: #eef4ff;
        color: #1d4ed8;
        font-weight: 950;
        font-size: 0.92rem;
        box-shadow: inset 0 0 0 1px #c7d7fe;
      }

      .top-three .pb-rank {
        background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        box-shadow: 0 10px 20px rgba(37, 99, 235, 0.22);
      }

      .pb-card-main {
        min-width: 0;
      }

      .pb-card-title-row {
        display: flex;
        gap: 10px;
        align-items: baseline;
        flex-wrap: wrap;
      }

      .pb-card-title {
        color: var(--bp-ink);
        font-size: 1rem;
        font-weight: 950;
        letter-spacing: -0.025em;
      }

      .pb-card-subtitle {
        color: var(--bp-muted);
        font-size: 0.82rem;
        font-weight: 700;
      }

      .pb-card-market {
        margin-top: 7px;
        color: #334155;
        font-size: 0.9rem;
        font-weight: 850;
      }

      .pb-card-market span {
        color: var(--bp-muted);
        font-weight: 750;
      }

      .pb-card-read {
        margin-top: 7px;
        max-width: 680px;
        color: #475569;
        font-size: 0.82rem;
        line-height: 1.4;
      }

      .pb-card-metrics {
        display: flex;
        gap: 8px;
        align-items: center;
        justify-content: flex-end;
        flex-wrap: wrap;
        min-width: 340px;
      }

      .pb-card-actions {
        display: flex;
        gap: 8px;
        justify-content: flex-end;
        width: 100%;
        margin-top: 10px;
      }

      .pb-card-actions button {
        min-height: 34px;
        padding: 8px 12px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 900;
      }

      .pb-card-right {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
      }

      .pb-pill.edge.negative {
        background: #fee2e2;
        color: #991b1b;
      }

      .pb-pill.edge.neutral {
        background: #f1f5f9;
        color: #334155;
      }

      .pb-pill.conf.high {
        background: #dcfce7;
        color: #166534;
      }

      .pb-pill.conf.medium {
        background: #fef3c7;
        color: #92400e;
      }

      .pb-pill.conf.low {
        background: #f1f5f9;
        color: #475569;
      }

      @media (max-width: 900px) {
        .muse-playerboard-pick-card {
          grid-template-columns: 42px minmax(0, 1fr);
        }

        .pb-card-right {
          grid-column: 1 / -1;
          align-items: stretch;
        }

        .pb-card-metrics,
        .pb-card-actions {
          justify-content: flex-start;
          min-width: 0;
        }
      }

      /* Premium analysis/result polish v2 */
      .muse-result {
        border-radius: 28px;
        box-shadow: var(--bp-card-shadow);
        background: rgba(255, 255, 255, 0.94);
      }

      .muse-result.empty {
        min-height: 220px;
        display: grid;
        place-items: center;
      }

      .muse-empty,
      .muse-empty-mini {
        color: var(--bp-muted);
        text-align: center;
      }

      .muse-empty h2 {
        color: var(--bp-ink);
        letter-spacing: -0.035em;
        font-size: clamp(1.45rem, 2vw, 2rem);
        margin-bottom: 8px;
      }

      .muse-empty p {
        color: var(--bp-muted);
        max-width: 620px;
        margin-inline: auto;
      }

      .muse-result-card,
      .muse-analysis-card,
      .muse-prop-card,
      .muse-overview,
      .muse-overview-card {
        border-radius: 24px;
        border: 1px solid rgba(148, 163, 184, 0.20);
        background: rgba(255, 255, 255, 0.96);
        box-shadow: var(--bp-soft-shadow);
      }

      .muse-result-header,
      .muse-analysis-header,
      .muse-prop-header,
      .muse-overview-header {
        padding: 26px 28px 18px;
        border-bottom: 1px solid rgba(226, 232, 240, 0.88);
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
      }

      .muse-result-header h2,
      .muse-analysis-header h2,
      .muse-prop-header h2,
      .muse-overview-header h2 {
        color: var(--bp-ink);
        letter-spacing: -0.04em;
        font-size: clamp(1.45rem, 2.2vw, 2.15rem);
        line-height: 1;
      }

      .muse-result-header p,
      .muse-analysis-header p,
      .muse-prop-header p,
      .muse-overview-header p {
        color: var(--bp-muted);
        margin-top: 8px;
      }

      .muse-tabs,
      .muse-tab-row,
      .muse-tabbar {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        padding: 14px;
        background: #f8fafc;
        border-bottom: 1px solid rgba(226, 232, 240, 0.9);
      }

      .muse-tab {
        min-height: 38px;
        padding: 9px 13px;
        border-radius: 999px;
        border: 1px solid transparent;
        background: transparent;
        color: #475569;
        font-weight: 800;
        font-size: 0.82rem;
        transition: all 160ms ease;
      }

      .muse-tab:hover {
        background: #eef4ff;
        color: var(--bp-primary-dark);
      }

      .muse-tab.active,
      .muse-tab[aria-selected="true"] {
        background: #ffffff;
        color: var(--bp-primary-dark);
        border-color: #c7d7fe;
        box-shadow: 0 8px 18px rgba(37, 99, 235, 0.10);
      }

      .muse-metric-grid,
      .muse-mini-grid,
      .muse-overview-stat-grid,
      .muse-stat-grid {
        gap: 12px;
      }

      .muse-mini-metric,
      .muse-overview-stat-grid > div,
      .muse-stat-grid > div {
        padding: 14px;
        min-height: 78px;
        border-radius: 18px;
        background:
          linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        border: 1px solid rgba(226, 232, 240, 0.9);
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.035);
      }

      .muse-mini-metric span,
      .muse-overview-stat-grid span,
      .muse-stat-grid span {
        color: var(--bp-muted);
        font-size: 0.72rem;
        font-weight: 900;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }

      .muse-mini-metric strong,
      .muse-overview-stat-grid strong,
      .muse-stat-grid strong {
        color: var(--bp-ink);
        font-size: 1.08rem;
        letter-spacing: -0.025em;
      }

      .muse-mini-metric em {
        color: var(--bp-muted);
        font-style: normal;
        font-size: 0.75rem;
      }

      .muse-edge-card,
      .muse-prob-card,
      .muse-summary-card {
        border-radius: 22px;
        background:
          radial-gradient(circle at top right, rgba(59, 130, 246, 0.10), transparent 16rem),
          #ffffff;
        border: 1px solid rgba(148, 163, 184, 0.20);
        box-shadow: var(--bp-soft-shadow);
      }

      .muse-edge-read,
      .muse-overview-reads li,
      .muse-statcast-read li {
        color: #334155;
        line-height: 1.5;
      }

      .muse-overview-reads,
      .muse-statcast-read ul {
        display: grid;
        gap: 8px;
      }

      .muse-overview-reads li,
      .muse-statcast-read li {
        padding: 10px 12px;
        border-radius: 14px;
        background: #f8fafc;
        border: 1px solid rgba(226, 232, 240, 0.8);
      }

      .muse-recent-stack,
      .muse-statcast-layout {
        gap: 16px;
      }

      .muse-statline,
      .muse-statcast-card {
        border-radius: 22px;
        border: 1px solid rgba(148, 163, 184, 0.20);
        background: #ffffff;
        box-shadow: var(--bp-soft-shadow);
        padding: 20px;
      }

      .muse-statline h3,
      .muse-statcast-card h3 {
        color: var(--bp-ink);
        letter-spacing: -0.025em;
        margin-bottom: 14px;
      }

      .muse-log-table-wrap {
        border-radius: 18px;
        border: 1px solid rgba(148, 163, 184, 0.22);
        box-shadow: var(--bp-soft-shadow);
        overflow: auto;
        background: #ffffff;
      }

      .muse-log-table {
        border-collapse: separate;
        border-spacing: 0;
      }

      .muse-log-table th {
        background: #f8fafc;
        color: #475569;
        font-size: 0.72rem;
        font-weight: 900;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        border-bottom: 1px solid rgba(148, 163, 184, 0.22);
      }

      .muse-log-table td {
        border-bottom: 1px solid rgba(226, 232, 240, 0.85);
      }

      .muse-log-table tbody tr:hover {
        background: #f8fbff;
      }

      @media (max-width: 900px) {
        .muse-result-header,
        .muse-analysis-header,
        .muse-prop-header,
        .muse-overview-header {
          padding: 20px;
        }

        .muse-tabs,
        .muse-tab-row,
        .muse-tabbar {
          padding: 10px;
        }
      }

      @media (max-width: 900px) {
        .muse-app {
          width: min(100%, calc(100vw - 20px));
        }

        .muse-shell,
        .muse-top-playerboard {
          padding: 20px;
          border-radius: 22px;
        }

        .muse-top-playerboard-controls {
          grid-template-columns: 1fr;
        }

        .muse-playerboard-table {
          min-width: 900px;
        }

        .muse-playerboard-table .pb-player {
          width: 210px;
        }

        .muse-playerboard-table .pb-market {
          width: 220px;
        }
      }
    `;

    document.head.appendChild(style);
  }



  function createShell() {
    ensurePlayerboardReadabilityStyles();
    if ($("#simplePropApp")) return;

    const main = $("main") || $(".app-main") || $(".container") || $(".main-content") || document.body;

    const section = document.createElement("section");
    section.id = "simplePropApp";
    section.className = "muse-app";
    section.innerHTML = `
      <div class="muse-shell">
        <div class="muse-brand">
          <div class="muse-logo">BP</div>
          <div>
            <h1>Baseball Prop Predictor</h1>
            <p>Search a player, team, or matchup and date. Player props and team/game markets use the same board, edge, and confidence workflow.</p>
          </div>
        </div>


        <div id="museLiveStatusStrip" class="muse-live-status-strip" aria-live="polite">
          <div class="muse-live-status-item warn">
            <div class="muse-live-dot"></div>
            <div class="muse-live-status-copy">
              <strong>Playerboard</strong>
              <span>Loading latest board status...</span>
            </div>
          </div>
          <div class="muse-live-status-item warn">
            <div class="muse-live-dot"></div>
            <div class="muse-live-status-copy">
              <strong>Grading</strong>
              <span>Loading grading summary...</span>
            </div>
          </div>
          <div class="muse-live-status-item warn">
            <div class="muse-live-dot"></div>
            <div class="muse-live-status-copy">
              <strong>Workflows</strong>
              <span>Loading automation status...</span>
            </div>
          </div>
        </div>

        <div class="muse-search-row">
          <div class="muse-search-box">
            <input id="simplePlayer" list="simplePlayerSuggestions" type="text" placeholder="Search a player or team, like Aaron Judge, NYY, or NYY vs BAL" autocomplete="off" />
            <datalist id="simplePlayerSuggestions"></datalist>
          </div>
          <input id="simpleDate" class="muse-date" type="date" />
          <button id="simpleAutofill" type="button" class="muse-secondary">Find Matchup</button>
        </div>

        <div id="simpleAutofillSummary" class="muse-autofill-summary">
          Enter a player, team, or matchup and date to auto-fill context.
        </div>

        <div class="muse-prop-controls">
          <label>
            Market
            <select id="simpleMarket">
              ${MARKETS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
            </select>
          </label>
          <label>
            Line
            <input id="simpleLine" type="number" step="0.5" value="1.5" />
          </label>
          <label>
            Odds
            <input id="simpleOdds" type="number" value="-110" />
          </label>
          <label>
            Team
            <input id="simpleTeam" type="text" placeholder="Auto" maxlength="3" />
          </label>
          <label>
            Opponent
            <input id="simpleOpponent" type="text" placeholder="Auto" maxlength="3" />
          </label>
          <label>
            Pitcher
            <input id="simplePitcher" type="text" placeholder="Auto" />
          </label>
        </div>

        <div class="muse-actions">
          <button id="simpleAnalyze" type="button">Analyze</button>
          <button id="simpleSave" type="button" class="muse-secondary" disabled>Save Pick</button>
        </div>

        <div id="simpleStatus" class="muse-status">Ready.</div>
      </div>


      <section id="topPlayerboard" class="muse-top-playerboard">
        <div class="muse-top-playerboard-head">
          <div>
            <h2>Today's Playerboard</h2>
            <p>Rank saved PropLine props by model edge for the selected date and market.</p>
          </div>
          <div class="muse-top-playerboard-actions">
            <button id="topPlayerboardLoad" type="button" class="muse-secondary">Load Board</button>
          </div>
        </div>

        <div class="muse-top-playerboard-controls">
          <label>
            Board Market
            <select id="topPlayerboardMarket">
              <option value="">All markets</option>
              ${MARKETS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
            </select>
          </label>
          <label>
            Sort By
            <select id="topPlayerboardSort">
              <option value="edge_desc" selected>Highest Edge %</option>
              <option value="prob_desc">Highest Probability</option>
              <option value="edge_asc">Lowest Edge %</option>
              <option value="prob_asc">Lowest Probability</option>
            </select>
          </label>
          <label>
            Min Edge %
            <input id="topPlayerboardMinEdge" type="number" step="0.5" value="0" />
          </label>
          <label>
            Search
            <input id="topPlayerboardSearch" type="search" placeholder="Player, team, market" autocomplete="off" />
          </label>
          <label>
            Team
            <input id="topPlayerboardTeam" type="search" placeholder="Any team" autocomplete="off" maxlength="3" />
          </label>
          <label>
            Book
            <input id="topPlayerboardBook" type="search" placeholder="Any book" autocomplete="off" />
          </label>
          <label>
            Readiness
            <select id="topPlayerboardReadiness">
              <option value="">All readiness</option>
              <option value="production">Production-ready</option>
              <option value="experimental">Experimental / candidate</option>
              <option value="research">Research only</option>
              <option value="not_ready">No model / not ready</option>
            </select>
          </label>
          <label>
            Confidence
            <select id="topPlayerboardConfidence">
              <option value="">All confidence</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low / research</option>
            </select>
          </label>
        </div>

        <div id="topPlayerboardStatus" class="muse-status">Board has not loaded yet.</div>
        <div id="topPlayerboardResults"></div>
      </section>

      <div id="simpleResult" class="muse-result empty">
        <div class="muse-empty">
          <h2>Fast prop analysis appears here.</h2>
          <p>Try: Aaron Judge ? 2026-05-03 ? Total Bases ? line 1.5</p>
        </div>
      </div>
    `;

    main.insertBefore(section, main.firstChild);

    $("#simpleDate").value = today();

    $("#simplePlayer").addEventListener("input", debounce(loadSuggestions, 220));
    $("#simplePlayer").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        autofill();
      }
    });

    $("#simpleDate").addEventListener("change", () => {
      if ($("#simplePlayer").value.trim()) autofill();
    });

    $("#simpleAutofill").addEventListener("click", autofill);
    $("#simpleAnalyze").addEventListener("click", analyze);
    $("#simpleSave").addEventListener("click", savePrediction);
    $("#topPlayerboardLoad")?.addEventListener("click", loadTopPlayerboard);

    $("#topPlayerboardSort")?.addEventListener("change", () => {
      topPlayerboardPage = 1;
      renderTopPlayerboardPage();
    });

    $("#topPlayerboardMinEdge")?.addEventListener("input", debounce(() => {
      topPlayerboardPage = 1;
      renderTopPlayerboardPage();
    }, 150));

    ["#topPlayerboardSearch", "#topPlayerboardTeam", "#topPlayerboardBook"].forEach((selector) => {
      $(selector)?.addEventListener("input", debounce(() => {
        topPlayerboardPage = 1;
        renderTopPlayerboardPage();
      }, 150));
    });

    ["#topPlayerboardReadiness", "#topPlayerboardConfidence", "#topPlayerboardMarket"].forEach((selector) => {
      $(selector)?.addEventListener("change", () => {
        topPlayerboardPage = 1;
        renderTopPlayerboardPage();
      });
    });

    $("#topPlayerboardResults")?.addEventListener("click", (event) => {
      if (event.target.closest("[data-playerboard-prev]")) {
        topPlayerboardPage -= 1;
        renderTopPlayerboardPage();
      }

      if (event.target.closest("[data-playerboard-next]")) {
        topPlayerboardPage += 1;
        renderTopPlayerboardPage();
      }
    });

    loadAppStatus();

    hideWorkflowNoise();
  }


  function statusClass(ok, exists = true) {
    if (!exists) return "warn";
    return ok ? "" : "bad";
  }

  function setLiveStatusCard(index, kind, title, detail) {
    const strip = $("#museLiveStatusStrip");
    const card = strip?.children?.[index];
    if (!card) return;

    card.className = `muse-live-status-item ${kind || ""}`.trim();
    const strong = card.querySelector("strong");
    const span = card.querySelector("span");

    if (strong) strong.textContent = title;
    if (span) span.textContent = detail;
  }

  async function loadAppStatus() {
    try {
      const payload = await getJson("/api/app/status?season=2026");
      const pb = payload.playerboard || {};
      const grading = payload.grading || {};
      const workflows = payload.workflows || {};

      setLiveStatusCard(
        0,
        statusClass(pb.ok, true),
        "Playerboard",
        `${pb.date || "--"} ? ${pb.rowsLoaded ?? 0} rows ? ${pb.badShiftedRows ?? 0} shifted`
      );

      setLiveStatusCard(
        1,
        statusClass(grading.ok, true),
        "Grading",
        `${grading.date || "--"} ? ${grading.gradedBacktestRowsForDate ?? 0}/${grading.backtestRowsForDate ?? 0} graded`
      );

      const weekly = workflows.weeklyRepair || {};
      const daily = workflows.dailyHealth || {};
      const workflowOk = workflows.ok && (weekly.exists || daily.exists);

      setLiveStatusCard(
        2,
        statusClass(workflowOk, weekly.exists || daily.exists),
        "Workflows",
        `Daily ${daily.date || "--"} ? Repair ${weekly.date || "--"}`
      );
    } catch (error) {
      console.error(error);
      setLiveStatusCard(0, "warn", "Playerboard", "Status unavailable");
      setLiveStatusCard(1, "warn", "Grading", "Status unavailable");
      setLiveStatusCard(2, "warn", "Workflows", "Status unavailable");
    }
  }


  function debounce(fn, wait) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  }

  async function loadSuggestions() {
    const q = $("#simplePlayer").value.trim();
    const list = $("#simplePlayerSuggestions");
    if (!q || q.length < 2) return;

    try {
      const payload = await getJson(`/api/player/search?season=2026&q=${encodeURIComponent(q)}&limit=8`);
      list.innerHTML = (payload.players || [])
        .map((p) => {
          const role = p.kind === "player" ? "Player" : String(p.kind || "Player").replace(/^./, (c) => c.toUpperCase());
          const label = [p.team, role].filter(Boolean).join(" • ");
          return `<option value="${escapeHtml(p.player)}">${escapeHtml(label)}</option>`;
        })
        .join("");
    } catch {
      // Suggestions should never block the app.
    }
  }

  function readForm() {
    return {
      season: "2026",
      date: $("#simpleDate").value || today(),
      market: $("#simpleMarket").value || "batter_total_bases",
      player: $("#simplePlayer").value.trim(),
      team: $("#simpleTeam").value.trim().toUpperCase(),
      opponent: $("#simpleOpponent").value.trim().toUpperCase(),
      pitcher: $("#simplePitcher").value.trim(),
      line: $("#simpleLine").value || "1.5",
      american_odds: $("#simpleOdds").value || "-110",
    };
  }

  function setStatus(text) {
    $("#simpleStatus").textContent = text;
  }

  function queryString(form) {
    return new URLSearchParams(form).toString();
  }

  function validate(form, requireMatchup = true) {
    const missing = [];
    if (!form.player) missing.push("player");
    if (!form.date) missing.push("date");
    if (requireMatchup) {
      if (!form.team) missing.push("team");
      if (!form.opponent) missing.push("opponent");
    }
    if (missing.length) throw new Error(`Missing ${missing.join(", ")}.`);
  }

  function applyAutofill(payload) {
    const previousMarket = $("#simpleMarket").value;

    $("#simplePlayer").value = payload.player || $("#simplePlayer").value;
    $("#simpleTeam").value = payload.team || "";
    $("#simpleOpponent").value = payload.opponent || "";
    $("#simplePitcher").value = payload.pitcher || "";

    if (payload.defaultMarket) {
      const currentIsPitcher = previousMarket.startsWith("pitcher");
      const nextIsPitcher = payload.defaultMarket.startsWith("pitcher");
      const currentIsTeam = TEAM_GAME_MARKETS.has(previousMarket);
      const nextIsTeam = TEAM_GAME_MARKETS.has(payload.defaultMarket);

      // Keep user's selected market when role type matches. Change only when switching between player/pitcher/team modes.
      if (currentIsPitcher !== nextIsPitcher || currentIsTeam !== nextIsTeam) {
        $("#simpleMarket").value = payload.defaultMarket;
      }
    }

    window.__lastAutofill = payload;

    const roleLabel = payload.role === "team" ? "Team / Matchup" : String(payload.role || "player").replace(/^./, (c) => c.toUpperCase());
    const matchupLine = payload.summary || `${payload.player} matchup found`;
    const details = [
      roleLabel,
      payload.team ? `Team ${payload.team}` : "",
      payload.opponent ? `Opponent ${payload.opponent}` : "",
      payload.pitcher ? `Pitcher ${payload.pitcher}` : "",
    ].filter(Boolean).join(" ? ");

    $("#simpleAutofillSummary").innerHTML = `
      <strong>${escapeHtml(matchupLine)}</strong>
      <span>${escapeHtml(details)}</span>
    `;
  }

  async function autofill() {
    const form = readForm();
    validate(form, false);

    setStatus("Finding matchup...");

    const payload = await getJson(
      `/api/player/autofill?season=2026&date=${encodeURIComponent(form.date)}&player=${encodeURIComponent(form.player)}&role=auto`
    );

    if (!payload.foundGame) {
      $("#simpleAutofillSummary").innerHTML = `
        <strong>No matchup found.</strong>
        <span>${escapeHtml(payload.message || "Try a different date.")}</span>
      `;
      setStatus("No matchup found.");
      return payload;
    }

    applyAutofill(payload);
    setStatus("Matchup auto-filled.");
    return payload;
  }

  function reasons(payload) {
    const out = [];

    if (Number(payload.cachedStatsAdjustmentPercent || 0)) out.push(["Stats", signed(payload.cachedStatsAdjustmentPercent)]);
    if (Number(payload.savantAdjustmentPercent || 0)) out.push(["Savant", signed(payload.savantAdjustmentPercent)]);
    if (Number(payload.weatherAdjustmentPercent || 0)) out.push(["Weather", signed(payload.weatherAdjustmentPercent)]);
    if (Number(payload.oddsMovementAdjustmentPercent || 0)) out.push(["Odds movement", signed(payload.oddsMovementAdjustmentPercent)]);

    return out;
  }

  function pill(label, value) {
    return `<div><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></div>`;
  }

  function tabButton(name, active = false) {
    return `<button type="button" class="muse-tab ${active ? "active" : ""}" data-tab="${escapeHtml(name)}">${escapeHtml(name)}</button>`;
  }


  function statLine(title, stats) {
    const pairs = Object.entries(stats || {}).slice(0, 8);
    if (!pairs.length) return `<div class="muse-statline"><h3>${escapeHtml(title)}</h3><p>No data available.</p></div>`;

    return `
      <div class="muse-statline">
        <h3>${escapeHtml(title)}</h3>
        <div class="muse-stat-grid">
          ${pairs.map(([key, value]) => `
            <div>
              <span>${escapeHtml(key)}</span>
              <strong>${escapeHtml(value)}</strong>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }

  function renderRecentForm(payload) {
    const profile = payload.playerProfile || {};
    const recent = profile.recent || {};
    const role = profile.role || "batter";
    const trends = recent.propTrends || {};

    const batterPick = (obj) => ({
      G: obj.games,
      H: obj.hits,
      TB: obj.totalBases,
      HR: obj.homeRuns,
      RBI: obj.rbi,
      BB: obj.walks,
      SO: obj.strikeouts,
      AVG: obj.avg,
      SLG: obj.slg,
      "H/G": obj.hitsPerGame,
      "TB/G": obj.totalBasesPerGame,
    });

    const pitcherPick = (obj) => ({
      G: obj.games,
      IP: obj.inningsPitched,
      K: obj.strikeOuts,
      H: obj.hits,
      ER: obj.earnedRuns,
      BB: obj.walks,
      HR: obj.homeRuns,
      "K/G": obj.strikeoutsPerGame,
      ERA: obj.eraEstimate,
    });

    const trendCards = role === "pitcher"
      ? {
          "K > 4.5 last 5": `${trends.last5?.strikeoutsOver4_5 ?? 0}/${trends.last5?.games ?? 0}`,
          "K > 5.5 last 5": `${trends.last5?.strikeoutsOver5_5 ?? 0}/${trends.last5?.games ?? 0}`,
          "H allowed > 4.5 last 5": `${trends.last5?.hitsAllowedOver4_5 ?? 0}/${trends.last5?.games ?? 0}`,
          "ER > 2.5 last 5": `${trends.last5?.earnedRunsOver2_5 ?? 0}/${trends.last5?.games ?? 0}`,
          "K > 4.5 last 10": `${trends.last10?.strikeoutsOver4_5 ?? 0}/${trends.last10?.games ?? 0}`,
          "K > 5.5 last 10": `${trends.last10?.strikeoutsOver5_5 ?? 0}/${trends.last10?.games ?? 0}`,
        }
      : {
          "Hit last 5": `${trends.last5?.hitGames ?? 0}/${trends.last5?.games ?? 0}`,
          "TB > 1.5 last 5": `${trends.last5?.totalBasesOver1_5 ?? 0}/${trends.last5?.games ?? 0}`,
          "HR last 5": `${trends.last5?.homeRunGames ?? 0}/${trends.last5?.games ?? 0}`,
          "Walk last 5": `${trends.last5?.walkGames ?? 0}/${trends.last5?.games ?? 0}`,
          "SO last 5": `${trends.last5?.strikeoutGames ?? 0}/${trends.last5?.games ?? 0}`,
          "Hit last 10": `${trends.last10?.hitGames ?? 0}/${trends.last10?.games ?? 0}`,
          "TB > 1.5 last 10": `${trends.last10?.totalBasesOver1_5 ?? 0}/${trends.last10?.games ?? 0}`,
          "HR last 10": `${trends.last10?.homeRunGames ?? 0}/${trends.last10?.games ?? 0}`,
        };

    const pick = role === "pitcher" ? pitcherPick : batterPick;

    return `
      <div class="muse-recent-stack">
        ${statLine("Prop Trends", trendCards)}
        ${statLine("Last 5 Games", pick(recent.last5 || {}))}
        ${statLine("Last 10 Games", pick(recent.last10 || {}))}
        ${statLine("Season", pick(recent.season || {}))}
      </div>
    `;
  }

  function renderGameLogs(payload) {
    const profile = payload.playerProfile || {};
    const logs = profile.gameLogs || [];
    const role = profile.role || "batter";

    if (!logs.length) {
      return `<div class="muse-empty-mini">No game logs available for this player.</div>`;
    }

    const columns = role === "pitcher"
      ? ["date", "opponent", "inningsPitched", "strikeOuts", "hits", "earnedRuns", "walks", "homeRuns", "pitches"]
      : ["date", "opponent", "ab", "hits", "totalBases", "homeRuns", "rbi", "walks", "strikeouts", "runs"];

    return `
      <div class="muse-log-table-wrap">
        <table class="muse-log-table">
          <thead>
            <tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr>
          </thead>
          <tbody>
            ${logs.map((row) => `
              <tr>${columns.map((c) => `<td>${escapeHtml(row[c] ?? "")}</td>`).join("")}</tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }



  function numberValue(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function firstNonEmptyObject(...items) {
    for (const item of items) {
      if (item && typeof item === "object" && Object.keys(item).length > 0) {
        return item;
      }
    }
    return {};
  }

  function statcastSignal(payload) {
    const profile = payload.playerProfile || {};
    const savant = payload.savantContext || {};

    const batter = firstNonEmptyObject(
      savant.batter,
      profile.role === "batter" ? profile.savant : {}
    );

    const pitcher = firstNonEmptyObject(
      savant.pitcher,
      profile.opposingPitcherSavant,
      profile.role === "pitcher" ? profile.savant : {}
    );

    const barrel = numberValue(batter.barrelRate);
    const hardHit = numberValue(batter.hardHitRate);
    const xslg = numberValue(batter.avgXSLG);
    const xwoba = numberValue(batter.avgXWOBA);
    const whiff = numberValue(pitcher.whiffRate);
    const barrelAllowed = numberValue(pitcher.barrelRateAllowed);
    const xwobaAllowed = numberValue(pitcher.avgXWOBAAllowed);

    const notes = [];

    if (barrel >= 12 || hardHit >= 48 || xslg >= 0.5) {
      notes.push("Power quality is strong for extra-base/HR markets.");
    } else if (barrel > 0 || hardHit > 0 || xslg > 0) {
      notes.push("Power quality is moderate based on current Savant sample.");
    } else {
      notes.push("Power quality is not available yet.");
    }

    if (xwoba >= 0.36) {
      notes.push("Overall contact quality is strong.");
    } else if (xwoba > 0) {
      notes.push("Overall contact quality is available but not a major boost.");
    }

    if (whiff >= 28) {
      notes.push("Pitcher whiff profile supports strikeout upside.");
    } else if (whiff > 0) {
      notes.push("Pitcher whiff profile is not strongly elevated.");
    }

    if (barrelAllowed >= 10 || xwobaAllowed >= 0.35) {
      notes.push("Pitcher allows damage risk, which can support hitter props.");
    } else if (barrelAllowed > 0 || xwobaAllowed > 0) {
      notes.push("Pitcher damage profile is available but not a major boost.");
    }

    return notes;
  }

  function metricCard(label, value, sub = "") {
    return `
      <div class="muse-mini-metric">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(display(value))}</strong>
        ${sub ? `<em>${escapeHtml(sub)}</em>` : ""}
      </div>
    `;
  }

  function renderStatcast(payload) {
    const profile = payload.playerProfile || {};
    const savant = payload.savantContext || {};

    const batter = firstNonEmptyObject(
      savant.batter,
      profile.role === "batter" ? profile.savant : {}
    );

    const pitcher = firstNonEmptyObject(
      savant.pitcher,
      profile.opposingPitcherSavant,
      profile.role === "pitcher" ? profile.savant : {}
    );

    const patchedPayload = {
      ...payload,
      savantContext: {
        ...(payload.savantContext || {}),
        batter,
        pitcher,
      },
    };

    const notes = statcastSignal(patchedPayload);

    return `
      <div class="muse-statcast-layout">
        <div class="muse-statcast-card">
          <h3>Batter Quality</h3>
          <div class="muse-mini-grid">
            ${metricCard("Avg EV", batter.avgExitVelocity)}
            ${metricCard("Max EV", batter.maxExitVelocity)}
            ${metricCard("Barrel %", displayPct(batter.barrelRate))}
            ${metricCard("Hard-hit %", displayPct(batter.hardHitRate))}
            ${metricCard("Sweet Spot %", displayPct(batter.sweetSpotRate))}
            ${metricCard("xBA", batter.avgXBA)}
            ${metricCard("xSLG", batter.avgXSLG)}
            ${metricCard("xwOBA", batter.avgXWOBA)}
          </div>
        </div>

        <div class="muse-statcast-card">
          <h3>Pitcher Quality</h3>
          <div class="muse-mini-grid">
            ${metricCard("Whiff %", displayPct(pitcher.whiffRate))}
            ${metricCard("CSW %", displayPct(pitcher.cswRate))}
            ${metricCard("EV allowed", pitcher.avgExitVelocityAllowed)}
            ${metricCard("Barrel allowed %", displayPct(pitcher.barrelRateAllowed))}
            ${metricCard("Hard-hit allowed %", displayPct(pitcher.hardHitRateAllowed))}
            ${metricCard("xBA allowed", pitcher.avgXBAAllowed)}
            ${metricCard("xSLG allowed", pitcher.avgXSLGAllowed)}
            ${metricCard("xwOBA allowed", pitcher.avgXWOBAAllowed)}
          </div>
        </div>

        <div class="muse-statcast-card muse-statcast-read">
          <h3>Prop Read</h3>
          <ul>
            ${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}
          </ul>
        </div>
      </div>
    `;
  }



  function shortRole(value) {
    const role = String(value || "").toLowerCase();
    if (role === "pitcher") return "Pitcher";
    if (role === "batter") return "Batter";
    return "Player";
  }

  function latestLog(profile) {
    const logs = profile.gameLogs || [];
    return logs.length ? logs[0] : {};
  }

  function compactSeasonStats(profile) {
    const role = profile.role || "batter";
    const season = profile.recent?.season || {};

    if (role === "pitcher") {
      return {
        G: season.games,
        IP: season.inningsPitched,
        K: season.strikeOuts,
        H: season.hits,
        ER: season.earnedRuns,
        BB: season.walks,
        HR: season.homeRuns,
        "K/G": season.strikeoutsPerGame,
        ERA: season.eraEstimate,
      };
    }

    return {
      G: season.games,
      H: season.hits,
      TB: season.totalBases,
      HR: season.homeRuns,
      RBI: season.rbi,
      BB: season.walks,
      SO: season.strikeouts,
      AVG: season.avg,
      SLG: season.slg,
    };
  }

  function compactLatestGame(profile) {
    const role = profile.role || "batter";
    const game = latestLog(profile);

    if (!Object.keys(game).length) {
      return { Status: "No recent game log available" };
    }

    if (role === "pitcher") {
      return {
        Date: game.date,
        Opp: game.opponent,
        IP: game.inningsPitched,
        K: game.strikeOuts,
        H: game.hits,
        ER: game.earnedRuns,
        BB: game.walks,
        HR: game.homeRuns,
      };
    }

    return {
      Date: game.date,
      Opp: game.opponent,
      AB: game.ab,
      H: game.hits,
      TB: game.totalBases,
      HR: game.homeRuns,
      RBI: game.rbi,
      BB: game.walks,
      SO: game.strikeouts,
    };
  }

  function overviewPropReads(payload) {
    const profile = payload.playerProfile || {};
    const role = profile.role || "batter";
    const trends = profile.recent?.propTrends || {};
    const last5 = trends.last5 || {};
    const last10 = trends.last10 || {};
    const reads = [];

    if (role === "pitcher") {
      reads.push(`K > 4.5 in ${last5.strikeoutsOver4_5 ?? 0}/${last5.games ?? 0} last 5`);
      reads.push(`K > 5.5 in ${last5.strikeoutsOver5_5 ?? 0}/${last5.games ?? 0} last 5`);
      reads.push(`Hits allowed > 4.5 in ${last10.hitsAllowedOver4_5 ?? 0}/${last10.games ?? 0} last 10`);
    } else {
      reads.push(`Hit in ${last5.hitGames ?? 0}/${last5.games ?? 0} last 5`);
      reads.push(`TB > 1.5 in ${last5.totalBasesOver1_5 ?? 0}/${last5.games ?? 0} last 5`);
      reads.push(`HR in ${last10.homeRunGames ?? 0}/${last10.games ?? 0} last 10`);
    }

    if (Number(payload.savantAdjustmentPercent || 0) > 0) {
      reads.push(`Savant supports this prop: ${signed(payload.savantAdjustmentPercent)}`);
    } else if (Number(payload.savantAdjustmentPercent || 0) < 0) {
      reads.push(`Savant leans against this prop: ${signed(payload.savantAdjustmentPercent)}`);
    }

    if (Number(payload.weatherAdjustmentPercent || 0) > 0) {
      reads.push(`Weather gives a small boost: ${signed(payload.weatherAdjustmentPercent)}`);
    } else if (Number(payload.weatherAdjustmentPercent || 0) < 0) {
      reads.push(`Weather slightly lowers confidence: ${signed(payload.weatherAdjustmentPercent)}`);
    }

    return reads;
  }

  function miniStatList(stats) {
    return `
      <div class="muse-overview-stat-grid">
        ${Object.entries(stats || {}).map(([key, value]) => `
          <div>
            <span>${escapeHtml(key)}</span>
            <strong>${escapeHtml(display(value, "0"))}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }


  function isTeamGameMarket(market) {
    return TEAM_GAME_MARKETS.has(String(market || ""));
  }

  function matchupTitle(payload) {
    if (isTeamGameMarket(payload.market)) {
      if (payload.team && payload.opponent) return `${payload.team} vs ${payload.opponent}`;
      return payload.player || "Team/Game Market";
    }
    return payload.player || "Player Prop";
  }

  function marketSideText(payload) {
    const side = clean(payload.rawLabel);
    const market = String(payload.market || "");
    const line = clean(payload.line);
    if (market === "moneyline" || market === "moneyline_first_five" || market === "team_first_to_score") {
      return side || payload.team || "Win";
    }
    if (market === "run_line" || market === "run_line_first_five" || market === "run_line_first_inning") {
      return `${payload.team || side} ${line ? line : ""}`.trim();
    }
    if (side && line) return `${side} ${line}`;
    if (line) return `Over ${line}`;
    return side || "Market";
  }

  function compactTeamStats(payload) {
    const ctx = payload.cachedContexts || {};
    const team = ctx.team || {};
    const opponent = ctx.opponent || {};
    return {
      "Team R/G": team.runsPerGame,
      "Team RA/G": team.runsAllowedPerGame,
      "Opp R/G": opponent.runsPerGame,
      "Opp RA/G": opponent.runsAllowedPerGame,
      "Team H/G": team.hitsPerGame,
      "Opp H/G": opponent.hitsPerGame,
      "Team K/G": team.strikeoutsPerGame,
      "Opp K/G": opponent.strikeoutsPerGame,
    };
  }

  function teamQuickReads(payload) {
    const ctx = payload.cachedContexts || {};
    const team = ctx.team || {};
    const opponent = ctx.opponent || {};
    const reads = [];
    if (team.runsPerGame || opponent.runsAllowedPerGame) {
      reads.push(`${payload.team} offense: ${display(team.runsPerGame, "--")} R/G vs ${payload.opponent} allowing ${display(opponent.runsAllowedPerGame, "--")} R/G`);
    }
    if (team.runsAllowedPerGame || opponent.runsPerGame) {
      reads.push(`${payload.team} run prevention: ${display(team.runsAllowedPerGame, "--")} RA/G; ${payload.opponent} offense: ${display(opponent.runsPerGame, "--")} R/G`);
    }
    if (Number(payload.weatherAdjustmentPercent || 0)) reads.push(`Weather adjustment: ${signed(payload.weatherAdjustmentPercent)}`);
    if (Number(payload.oddsMovementAdjustmentPercent || 0)) reads.push(`Market movement adjustment: ${signed(payload.oddsMovementAdjustmentPercent)}`);
    if (!reads.length) reads.push("Team/game context loaded; deeper model features will improve as historical team-prop training grows.");
    return reads;
  }

  function renderOverview(payload) {
    const profile = payload.playerProfile || {};
    const game = profile.gameContext || {};
    const weather = payload.weatherContext || {};
    const teamMode = isTeamGameMarket(payload.market) || profile.role === "team";
    const role = teamMode ? "Team / Matchup" : shortRole(profile.role);
    const seasonStats = teamMode ? compactTeamStats(payload) : compactSeasonStats(profile);
    const latest = teamMode ? { Market: marketLabel(payload.market), Side: marketSideText(payload), Odds: payload.americanOdds } : compactLatestGame(profile);
    const reads = teamMode ? teamQuickReads(payload) : overviewPropReads(payload);

    return `
      <div class="muse-overview-layout">
        <div class="muse-overview-hero-card">
          <div>
            <h3>${escapeHtml(matchupTitle(payload))}</h3>
            <p>${escapeHtml(role)} - ${escapeHtml(marketLabel(payload.market))} • ${escapeHtml(marketSideText(payload))}</p>
          </div>
          <div class="muse-overview-pill">${escapeHtml(display(payload.recommendation))}</div>
        </div>

        <div class="muse-overview-card">
          <h3>Game Context</h3>
          <div class="muse-overview-lines">
            <p><b>Matchup:</b> ${escapeHtml(display(game.away || payload.opponent))} @ ${escapeHtml(display(game.home || payload.team))}</p>
            <p><b>Venue:</b> ${escapeHtml(display(game.venue || weather.venue))}</p>
            <p><b>Team:</b> ${escapeHtml(display(payload.team))}</p>
            <p><b>Opponent:</b> ${escapeHtml(display(payload.opponent))}</p>
            ${teamMode ? "" : `<p><b>Pitcher:</b> ${escapeHtml(display(payload.pitcher))}</p>`}
          </div>
        </div>

        <div class="muse-overview-card">
          <h3>2026 Season</h3>
          ${miniStatList(seasonStats)}
        </div>

        <div class="muse-overview-card">
          <h3>Latest Game</h3>
          ${miniStatList(latest)}
        </div>

        <div class="muse-overview-card muse-overview-wide">
          <h3>Quick Prop Reads</h3>
          <ul class="muse-overview-reads">
            ${reads.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
          </ul>
        </div>
      </div>
    `;
  }



  function renderAdjustmentCards(payload) {
    const adjustments = [
      ["Stats", payload.cachedStatsAdjustmentPercent, "Cached player, team, and matchup stats"],
      ["Savant", payload.savantAdjustmentPercent, "Statcast quality metrics"],
      ["Weather", payload.weatherAdjustmentPercent, "Park and weather conditions"],
      ["Odds Movement", payload.oddsMovementAdjustmentPercent, "Self-stored PropLine line movement"],
    ];

    return `
      <div class="muse-adjustment-grid">
        ${adjustments.map(([label, value, note]) => `
          <div class="muse-adjustment-card">
            <span>${escapeHtml(label)}</span>
            <strong class="${Number(value || 0) >= 0 ? "positive" : "negative"}">${signed(value)}</strong>
            <p>${escapeHtml(note)}</p>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderPropEdge(payload) {
    const oddsMovement = payload.oddsMovementContext || {};
    const missing = payload.missingData || [];
    const dataUsed = payload.dataUsed || [];

    const edge = Number(payload.finalEdgePercent || 0);
    let edgeRead = "No clear model edge.";
    if (edge >= 5) edgeRead = "Strong positive edge by current model thresholds.";
    else if (edge >= 2) edgeRead = "Positive edge, but not a strong edge.";
    else if (edge <= -2) edgeRead = "Model leans away from this prop.";

    return `
      <div class="muse-prop-edge-layout">
        <div class="muse-prop-edge-card muse-prop-edge-main">
          <h3>Prop Edge</h3>
          <div class="muse-prop-edge-big">
            <div>
              <span>Model probability</span>
              <strong>${escapeHtml(displayPct(payload.finalProbabilityPercent))}</strong>
            </div>
            <div>
              <span>Sportsbook implied</span>
              <strong>${escapeHtml(displayPct(payload.sportsbookImpliedPercent))}</strong>
            </div>
            <div>
              <span>Edge</span>
              <strong>${signed(payload.finalEdgePercent)}</strong>
            </div>
          </div>
          <p class="muse-edge-read">${escapeHtml(edgeRead)}</p>
        </div>

        <div class="muse-prop-edge-card">
          <h3>Adjustment Breakdown</h3>
          ${renderAdjustmentCards(payload)}
        </div>

        <div class="muse-prop-edge-card">
          <h3>Odds Context</h3>
          <div class="muse-overview-lines">
            <p><b>Line:</b> ${escapeHtml(display(payload.line))}</p>
            <p><b>American odds:</b> ${escapeHtml(display(payload.americanOdds))}</p>
            <p><b>Odds snapshots:</b> ${escapeHtml(display(oddsMovement.snapshots))}</p>
            <p><b>Movement:</b> ${escapeHtml(display(oddsMovement.movementSummary, "No matching movement yet"))}</p>
          </div>
        </div>

        <div class="muse-prop-edge-card">
          <h3>Data Used</h3>
          ${
            dataUsed.length
              ? `<ul class="muse-check-list">${dataUsed.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
              : "<p>No data-used list returned.</p>"
          }
        </div>

        <div class="muse-prop-edge-card">
          <h3>Data Gaps</h3>
          ${
            missing.length
              ? `<ul class="muse-warning-list">${missing.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
              : "<p>No major data gaps.</p>"
          }
        </div>
      </div>
    `;
  }




  const PLAYERBOARD_PAGE_SIZE = 10;
  let topPlayerboardRows = [];
  let topPlayerboardPage = 1;
  let topPlayerboardMeta = {};

  function numericValue(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n : 0;
  }

  function sortPlayerboardRows(rows, sortMode) {
    const sorted = [...rows];

    sorted.sort((a, b) => {
      const edgeA = numericValue(a.edgePercent || a.finalEdgePercent);
      const edgeB = numericValue(b.edgePercent || b.finalEdgePercent);
      const probA = numericValue(a.modelProbabilityPercent || a.finalProbabilityPercent);
      const probB = numericValue(b.modelProbabilityPercent || b.finalProbabilityPercent);

      if (sortMode === "prob_desc") return probB - probA;
      if (sortMode === "prob_asc") return probA - probB;
      if (sortMode === "edge_asc") return edgeA - edgeB;

      return edgeB - edgeA;
    });

    return sorted;
  }

  function currentPlayerboardRows() {
    const minEdge = Number($("#topPlayerboardMinEdge")?.value || 0);
    const sortMode = $("#topPlayerboardSort")?.value || "edge_desc";
    const search = clean($("#topPlayerboardSearch")?.value).toLowerCase();
    const team = clean($("#topPlayerboardTeam")?.value).toLowerCase();
    const book = clean($("#topPlayerboardBook")?.value).toLowerCase();
    const readiness = clean($("#topPlayerboardReadiness")?.value).toLowerCase();
    const confidence = clean($("#topPlayerboardConfidence")?.value).toLowerCase();
    const selectedMarket = clean($("#topPlayerboardMarket")?.value).toLowerCase();

    const filtered = topPlayerboardRows.filter((row) => {
      const edgeValue = row.edgePercent || row.finalEdgePercent || 0;
      const haystack = [row.player, row.team, row.opponent, row.market, row.marketDisplay, row.book, row.decisionLabel]
        .map((value) => clean(value).toLowerCase())
        .join(" ");
      const rowTeam = clean(row.team).toLowerCase();
      const rowOpponent = clean(row.opponent).toLowerCase();
      const rowBook = clean(row.book).toLowerCase();
      const rowReadiness = `${clean(row.readinessLabel)} ${clean(row.productionStatus)}`.toLowerCase();
      const rowConfidence = clean(row.confidence).toLowerCase();
      const rowMarket = clean(row.market).toLowerCase();

      if (Number(edgeValue || 0) < minEdge) return false;
      if (selectedMarket && rowMarket !== selectedMarket) return false;
      if (search && !haystack.includes(search)) return false;
      if (team && !rowTeam.includes(team) && !rowOpponent.includes(team)) return false;
      if (book && !rowBook.includes(book)) return false;
      if (readiness) {
        if (readiness === "production" && !row.canShowConfidentPick && !rowReadiness.includes("production")) return false;
        if (readiness === "experimental" && !rowReadiness.includes("experimental") && !rowReadiness.includes("candidate")) return false;
        if (readiness === "research" && !rowReadiness.includes("research")) return false;
        if (readiness === "not_ready" && !rowReadiness.includes("not") && !rowReadiness.includes("missing") && !rowReadiness.includes("disabled")) return false;
      }
      if (confidence) {
        if (confidence === "low" && !rowConfidence.includes("low") && !rowConfidence.includes("research")) return false;
        if (confidence !== "low" && !rowConfidence.includes(confidence)) return false;
      }
      return true;
    });

    return sortPlayerboardRows(filtered, sortMode);
  }

  function renderTopPlayerboardPage() {
    const resultBox = $("#topPlayerboardResults");
    const statusBox = $("#topPlayerboardStatus");
    if (!resultBox) return;

    const rows = currentPlayerboardRows();
    const totalPages = Math.max(1, Math.ceil(rows.length / PLAYERBOARD_PAGE_SIZE));

    if (topPlayerboardPage > totalPages) topPlayerboardPage = totalPages;
    if (topPlayerboardPage < 1) topPlayerboardPage = 1;

    const start = (topPlayerboardPage - 1) * PLAYERBOARD_PAGE_SIZE;
    const pageRows = rows.slice(start, start + PLAYERBOARD_PAGE_SIZE);

    resultBox.innerHTML = `
      ${renderPlayerboardTable(pageRows)}
      ${renderPlayerboardPager(rows.length, topPlayerboardPage, totalPages)}
    `;

    if (statusBox) {
      const startLabel = rows.length ? start + 1 : 0;
      const endLabel = Math.min(start + PLAYERBOARD_PAGE_SIZE, rows.length);
      const cacheText = topPlayerboardMeta.cacheHit ? " Saved snapshot, no rebuild." : "";
      const sourceMessage = !rows.length && topPlayerboardMeta.message ? ` ${topPlayerboardMeta.message}` : "";
      statusBox.textContent = `Showing ${startLabel}-${endLabel} of ${rows.length} props. Page ${topPlayerboardPage} of ${totalPages}.${cacheText}${sourceMessage}`;
    }
  }

  function renderPlayerboardPager(totalRows, page, totalPages) {
    if (!totalRows) return "";

    return `
      <div class="muse-playerboard-pager">
        <button type="button" data-playerboard-prev ${page <= 1 ? "disabled" : ""}>Previous</button>
        <span>Page ${page} of ${totalPages}</span>
        <button type="button" data-playerboard-next ${page >= totalPages ? "disabled" : ""}>Next</button>
      </div>
    `;
  }


  function boardButtonForm(button) {
    return {
      season: "2026",
      date: $("#simpleDate")?.value || today(),
      market: button.dataset.market || "batter_total_bases",
      player: button.dataset.player || "",
      team: button.dataset.team || "",
      opponent: button.dataset.opponent || "",
      pitcher: button.dataset.pitcher || "",
      line: button.dataset.line || "1.5",
      american_odds: button.dataset.odds || "-110",
    };
  }

  async function trackFromBoardButton(button) {
    const form = boardButtonForm(button);

    if (!form.player || !form.market || !form.team || !form.opponent) {
      setStatus("Could not track pick: missing player, market, team, or opponent.");
      return;
    }

    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = "Saving...";

    try {
      let payload;
      if (window.MlbMyPicks?.createPickFromButton) {
        button.disabled = false;
        payload = await window.MlbMyPicks.createPickFromButton(button);
      } else {
        payload = await getJson("/api/my-picks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            date: form.date,
            player: form.player,
            market: form.market,
            team: form.team,
            opponent: form.opponent,
            line: form.line,
            americanOdds: form.american_odds,
            book: button.dataset.book || "Best available",
            decisionLabel: button.dataset.decision || "Watchlist",
            readinessLabel: button.dataset.readiness || "Research only",
            confidence: button.dataset.confidence || "Research",
            modelProbabilityPercent: button.dataset.probability || "",
            impliedProbabilityPercent: button.dataset.implied || "",
            edgePercent: button.dataset.edge || "",
            latestGradedDate: button.dataset.latestGraded || "",
            suggestedStake: button.dataset.suggestedStake || "Research only",
            source: "edge_board",
            status: "Watching",
            stakeUnits: 0,
          }),
        });
      }
      const pickId = payload.pick?.id || payload.predictionId || "saved";
      setStatus(`Tracked pick: ${form.player} (${pickId}).`);
      button.textContent = "Tracked";
      button.classList.add("is-tracked");
      document.dispatchEvent(new CustomEvent("my-picks:changed", { detail: payload }));
    } catch (error) {
      console.error(error);
      setStatus(`Track failed: ${error.message}`);
      button.textContent = oldText;
      button.disabled = false;
    }
  }


  function fillFromBoardButton(button) {
    const form = boardButtonForm(button);

    $("#simplePlayer").value = form.player;
    $("#simpleMarket").value = form.market;
    $("#simpleTeam").value = form.team;
    $("#simpleOpponent").value = form.opponent;
    $("#simplePitcher").value = form.pitcher;
    $("#simpleLine").value = form.line;
    $("#simpleOdds").value = form.american_odds;

    setStatus(`Loaded ${form.player} from Playerboard.`);
    document.getElementById("simplePropApp")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function loadTopPlayerboard() {
    const date = $("#simpleDate")?.value || today();
    const market = $("#topPlayerboardMarket")?.value || "";
    const statusBox = $("#topPlayerboardStatus");
    const resultBox = $("#topPlayerboardResults");

    try {
      if (statusBox) statusBox.textContent = "Loading Playerboard...";
      if (resultBox) resultBox.innerHTML = "";

      const board = await getJson(
        `/api/edge-board?season=2026&date=${encodeURIComponent(date)}&market=${encodeURIComponent(market)}&limit=500&buildIfMissing=1`
      );

      topPlayerboardRows = board.rows || board.top || [];
      topPlayerboardPage = 1;
      topPlayerboardMeta = board;

      renderTopPlayerboardPage();

      if (statusBox) {
        const savedText = board.saved?.rowsSaved ? ` Saved ${board.saved.rowsSaved} rows for ML/backtesting.` : "";
        const cacheText = board.cacheHit ? " Saved snapshot, no rebuild." : "";
        const rows = currentPlayerboardRows();
        const endLabel = Math.min(PLAYERBOARD_PAGE_SIZE, rows.length);
        const emptyText = !rows.length && board.message ? ` ${board.message}` : "";
        const source = board.source || {};
        const trust = board.trust || {};
        const confidence = board.dataConfidence ? ` Data confidence: ${board.dataConfidence}.` : "";
        statusBox.textContent = `Showing ${rows.length ? 1 : 0}-${endLabel} of ${rows.length} props from ${source.cardsBuilt || board.cardsBuilt || 0} ranked props. ${trust.banner || "Research Mode"}.${confidence}${cacheText}${savedText}${emptyText}`;
      }
    } catch (error) {
      console.error(error);
      topPlayerboardRows = [];
      topPlayerboardPage = 1;
      topPlayerboardMeta = {};
      if (statusBox) statusBox.textContent = `Playerboard failed: ${error.message}`;
      if (resultBox) resultBox.innerHTML = `<div class="muse-empty-mini">Could not load Playerboard: ${escapeHtml(error.message)}</div>`;
    }
  }

  async function loadPlayerboardForCurrentSearch() {
    const form = readForm();
    const market = form.market || "";
    const resultBox = document.querySelector('[data-playerboard-results]');
    const statusBox = document.querySelector('[data-playerboard-status]');

    if (!resultBox) return;

    try {
      if (statusBox) statusBox.textContent = "Loading today's board...";
      const board = await getJson(
        `/api/playerboard?season=2026&date=${encodeURIComponent(form.date)}&market=${encodeURIComponent(market)}&limit=30&buildIfMissing=1`
      );

      resultBox.innerHTML = renderPlayerboardTable(board.top || []);
      if (statusBox) {
        const cacheText = board.cacheHit ? " Loaded from saved snapshot." : "";
        const emptyText = !(board.top || []).length && board.message ? ` ${board.message}` : "";
        statusBox.textContent = `${board.cardsBuilt || 0} props ranked from ${board.propsLoaded || 0} saved props.${cacheText}${emptyText}`;
      }
    } catch (error) {
      console.error(error);
      resultBox.innerHTML = `<div class="muse-empty-mini">Could not load Playerboard: ${escapeHtml(error.message)}</div>`;
      if (statusBox) statusBox.textContent = "Playerboard failed.";
    }
  }

  function renderPlayerboardTable(rows) {
    if (!rows || !rows.length) {
      return `<div class="muse-empty-mini">No ranked props found for this date/market/filter set yet. Check saved odds, data health, or relax readiness and edge filters.</div>`;
    }

    const edgeClass = (value) => {
      const n = Number(value || 0);
      if (n >= 5) return "edge";
      if (n <= 0) return "edge negative";
      return "edge neutral";
    };

    const confidenceClass = (value) => {
      const text = String(value || "").toLowerCase();
      if (text.includes("high")) return "conf high";
      if (text.includes("medium")) return "conf medium";
      return "conf low";
    };

    const decisionClass = (value) => {
      const text = String(value || "").toLowerCase();
      if (text.includes("potential")) return "decision-positive";
      if (text.includes("lean")) return "decision-lean";
      if (text.includes("watch")) return "decision-watch";
      return "decision-muted";
    };

    return `
      <div class="muse-playerboard-card-list edge-board-card-list">
        ${rows.map((row, index) => {
          const marketText = playerboardMarketLabel(row);
          const decision = row.decisionLabel || "No bet";
          const readiness = row.readinessLabel || "Research only";
          const reasons = Array.isArray(row.reasons) && row.reasons.length ? row.reasons : [row.recommendation || "Model-ranked opportunity from saved board."];
          const warnings = Array.isArray(row.trustWarnings) ? row.trustWarnings : [];
          const matchup = [row.team, row.opponent].filter(Boolean).join(" vs ");
          const gameMeta = [matchup, row.gameTime].filter(Boolean).join(" · ");
          const pitcherText = row.pitcher ? `Pitcher: ${row.pitcher}` : "";
          const subLine = [gameMeta, pitcherText].filter(Boolean).join(" · ");
          const lineText = clean(row.line);
          const oddsText = clean(row.americanOdds);
          const edgeValue = row.edgePercent || row.finalEdgePercent;
          const probabilityValue = row.modelProbabilityPercent || row.finalProbabilityPercent;
          const impliedValue = row.impliedProbabilityPercent;
          const rank = row.rank || index + 1;

          return `
            <article class="muse-playerboard-pick-card edge-board-pick-card ${rank <= 3 ? "top-three" : ""}">
              <div class="pb-rank">#${rank}</div>

              <div class="pb-card-main">
                <div class="pb-card-title-row">
                  <span class="edge-decision-badge ${decisionClass(decision)}">${escapeHtml(decision)}</span>
                  <span class="edge-readiness-badge">${escapeHtml(readiness)}</span>
                </div>

                <div class="pb-card-title-row edge-title-row">
                  <div class="pb-card-title" title="${escapeHtml(row.player)}">${escapeHtml(row.player || "Unknown player")}</div>
                  <div class="pb-card-subtitle">${escapeHtml(subLine || "Matchup unavailable")}</div>
                </div>

                <div class="pb-card-market" title="${escapeHtml(marketText)}">
                  ${escapeHtml(marketText)} <span>· Line ${escapeHtml(lineText || "--")} · ${escapeHtml(row.book || "Best available")}</span>
                </div>

                <ul class="edge-board-reasons">
                  ${reasons.slice(0, 3).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}
                </ul>

                ${warnings.length ? `<div class="edge-warning-line">${escapeHtml(warnings[0])}${warnings.length > 1 ? ` +${warnings.length - 1} more warning${warnings.length > 2 ? "s" : ""}` : ""}</div>` : ""}
              </div>

              <div class="pb-card-right">
                <div class="pb-card-metrics">
                  <span class="pb-pill prob" title="Model probability">${escapeHtml(probabilityValue || "--")}%</span>
                  <span class="pb-pill ${edgeClass(edgeValue)}" title="Model edge">${signed(edgeValue)}</span>
                  <span class="pb-pill conf ${confidenceClass(row.confidence).replace("conf ", "")}" title="Confidence">${escapeHtml(row.confidence || "Research")}</span>
                  <span class="pb-pill odds" title="American odds">${escapeHtml(oddsText || "--")}</span>
                  ${impliedValue ? `<span class="pb-pill implied" title="Book implied probability">${escapeHtml(impliedValue)}% implied</span>` : ""}
                </div>

                <div class="edge-board-trust-mini">
                  <span>${escapeHtml(row.trainingRows || 0)} training rows</span>
                  <span>${escapeHtml(row.latestGradedDate || "No graded slate")}</span>
                  <span>${escapeHtml(row.suggestedStake || "Research only")}</span>
                </div>

                <div class="pb-card-actions">
                  <button type="button" class="muse-fill-prop"
                    data-player="${escapeHtml(row.player)}"
                    data-market="${escapeHtml(row.market)}"
                    data-team="${escapeHtml(row.team)}"
                    data-opponent="${escapeHtml(row.opponent)}"
                    data-pitcher="${escapeHtml(row.pitcher || "") }"
                    data-line="${escapeHtml(row.line)}"
                    data-odds="${escapeHtml(row.americanOdds)}">
                    Use
                  </button>
                  <button type="button" class="muse-track-prop"
                    data-player="${escapeHtml(row.player)}"
                    data-market="${escapeHtml(row.market)}"
                    data-team="${escapeHtml(row.team)}"
                    data-opponent="${escapeHtml(row.opponent)}"
                    data-pitcher="${escapeHtml(row.pitcher || "") }"
                    data-line="${escapeHtml(row.line)}"
                    data-odds="${escapeHtml(row.americanOdds)}"
                    data-book="${escapeHtml(row.book)}"
                    data-market-display="${escapeHtml(marketText)}"
                    data-decision="${escapeHtml(decision)}"
                    data-readiness="${escapeHtml(readiness)}"
                    data-confidence="${escapeHtml(row.confidence || "Research") }"
                    data-probability="${escapeHtml(probabilityValue || "") }"
                    data-implied="${escapeHtml(impliedValue || "") }"
                    data-edge="${escapeHtml(edgeValue || "") }"
                    data-latest-graded="${escapeHtml(row.latestGradedDate || "") }"
                    data-suggested-stake="${escapeHtml(row.suggestedStake || "Research only") }">
                    Track
                  </button>
                  <button type="button" class="ghost-button" data-prop-detail-open
                    data-prop-id="${escapeHtml(row.id || "") }"
                    data-date="${escapeHtml(row.date || "") }"
                    data-player="${escapeHtml(row.player)}"
                    data-market="${escapeHtml(row.market)}"
                    data-team="${escapeHtml(row.team)}"
                    data-opponent="${escapeHtml(row.opponent)}"
                    data-line="${escapeHtml(row.line)}"
                    data-odds="${escapeHtml(row.americanOdds)}"
                    data-book="${escapeHtml(row.book)}"
                    data-decision="${escapeHtml(decision)}"
                    data-readiness="${escapeHtml(readiness)}"
                    data-confidence="${escapeHtml(row.confidence || "Research") }">
                    Detail
                  </button>
                  <button type="button" class="ghost-button" data-model-card-open="${escapeHtml(row.market)}">Model Card</button>
                </div>
              </div>
            </article>
          `;
        }).join("")}
      </div>
    `;
  }



  function renderPlayerboard(payload) {
    return `
      <div class="muse-playerboard-card">
        <div class="muse-playerboard-head">
          <div>
            <h3>Today's Playerboard</h3>
            <p>Ranks saved PropLine props by model edge using the same Unified Prop Card logic.</p>
          </div>
          <button type="button" class="muse-secondary" data-load-playerboard>Load Board</button>
        </div>
        <div class="muse-status" data-playerboard-status>Choose a date and market, then load the board.</div>
        <div data-playerboard-results></div>
      </div>
    `;
  }


  function renderTabs(payload) {
    const weather = payload.weatherContext || {};
    const savant = payload.savantContext || {};
    const batter = savant.batter || {};
    const pitcher = savant.pitcher || {};
    const oddsMovement = payload.oddsMovementContext || {};
    const allData = payload.allData || {};
    const cached = payload.cachedContexts || {};

    return `
      <div class="muse-tabs">
        ${tabButton("Overview", true)}
        ${tabButton("Playerboard")}
        ${tabButton("Prop Edge")}
        ${tabButton("Recent Form")}
        ${tabButton("Statcast")}
        ${tabButton("Game Logs")}
      </div>

      <div class="muse-tab-panels">
        <section class="muse-tab-panel active" data-panel="Overview">
          ${renderOverview(payload)}
        </section>


        <section class="muse-tab-panel" data-panel="Playerboard">
          ${renderPlayerboard(payload)}
        </section>

        <section class="muse-tab-panel" data-panel="Prop Edge">
          ${renderPropEdge(payload)}
        </section>

        <section class="muse-tab-panel" data-panel="Recent Form">
          ${renderRecentForm(payload)}
        </section>

        <section class="muse-tab-panel" data-panel="Statcast">
          ${renderStatcast(payload)}
        </section>

        <section class="muse-tab-panel" data-panel="Game Logs">
          ${renderGameLogs(payload)}
        </section>
      </div>
    `;
  }

  function bindTabs(root) {
    root.querySelector("[data-load-playerboard]")?.addEventListener("click", loadPlayerboardForCurrentSearch);

    root.addEventListener("click", (event) => {
      const trackButton = event.target.closest(".muse-track-prop");
      if (trackButton) {
        trackFromBoardButton(trackButton);
        return;
      }

      const button = event.target.closest(".muse-fill-prop");
      if (!button) return;

      fillFromBoardButton(button);
    });

    root.querySelectorAll(".muse-tab").forEach((button) => {
      button.addEventListener("click", () => {
        const tab = button.dataset.tab;

        root.querySelectorAll(".muse-tab").forEach((b) => b.classList.remove("active"));
        root.querySelectorAll(".muse-tab-panel").forEach((p) => p.classList.remove("active"));

        button.classList.add("active");
        root.querySelector(`.muse-tab-panel[data-panel="${CSS.escape(tab)}"]`)?.classList.add("active");
      });
    });
  }

  function renderResult(payload) {
    const result = $("#simpleResult");
    const reasonRows = reasons(payload);
    const cls = recClass(payload.recommendation);
    const activeForm = readForm();

    result.className = "muse-result";
    result.innerHTML = `
      <div class="muse-answer-card">
        <div class="muse-answer-header">
          <div>
            <h2>${escapeHtml(matchupTitle(payload))}</h2>
            <p>${escapeHtml(marketLabel(payload.market))} • ${escapeHtml(marketSideText(payload))} • ${escapeHtml(payload.team)} vs ${escapeHtml(payload.opponent)}</p>
          </div>
          <div class="muse-pill ${cls}">${escapeHtml(payload.recommendation)}</div>
        </div>

        <div class="muse-big-answer">
          <div>
            <span>Projected probability</span>
            <strong>${escapeHtml(payload.finalProbabilityPercent)}%</strong>
          </div>
          <div>
            <span>Edge</span>
            <strong>${signed(payload.finalEdgePercent)}</strong>
          </div>
          <div>
            <span>Confidence</span>
            <strong>${escapeHtml(payload.confidence)}</strong>
          </div>
        </div>

        <div class="muse-short-explain">
          ${
            reasonRows.length
              ? reasonRows.map(([name, value]) => pill(name, value)).join("")
              : pill("Baseline", "No major adjustment")
          }
        </div>

        ${renderTabs(payload)}
      </div>
    `;

    bindTabs(result);
  }

  async function analyze() {
    try {
      let form = readForm();

      if (!form.team || !form.opponent) {
        await autofill();
        form = readForm();
      }

      validate(form, true);
      setStatus("Analyzing...");

      const payload = await getJson(`/api/unified-prop-card/predict?${queryString(form)}`);

      // Safety fix: if API returns a different matchup than the current autofilled form,
      // rerun once using the visible form values. This prevents stale result/form mismatch.
      const visible = readForm();
      let finalPayload = payload;

      if (
        payload.team !== visible.team ||
        payload.opponent !== visible.opponent ||
        clean(payload.pitcher) !== clean(visible.pitcher)
      ) {
        finalPayload = await getJson(`/api/unified-prop-card/predict?${queryString(visible)}`);
        window.__lastSimplePropQuery = visible;
      } else {
        window.__lastSimplePropQuery = form;
      }

      if (isTeamGameMarket(visible.market)) {
        finalPayload.playerProfile = { role: "team", gameContext: finalPayload.allData?.contexts?.game || {} };
      } else {
        try {
          finalPayload.playerProfile = await getJson(
            `/api/player/profile?season=2026&date=${encodeURIComponent(visible.date)}&player=${encodeURIComponent(visible.player)}`
          );
        } catch (profileError) {
          finalPayload.playerProfile = { error: profileError.message };
        }
      }

      renderResult(finalPayload);

      $("#simpleSave").disabled = false;
      setStatus("Analysis complete.");
    } catch (error) {
      console.error(error);
      setStatus(error.message);
      $("#simpleResult").className = "muse-result empty";
      $("#simpleResult").innerHTML = `<div class="muse-empty error"><h2>Could not analyze</h2><p>${escapeHtml(error.message)}</p></div>`;
    }
  }

  async function savePrediction() {
    try {
      const form = window.__lastSimplePropQuery || readForm();
      validate(form, true);
      setStatus("Saving pick...");

      const payload = await getJson(`/api/predictions/save?${queryString(form)}`, { method: "POST" });
      setStatus(`Saved pick ${payload.predictionId}.`);
    } catch (error) {
      console.error(error);
      setStatus(`Save failed: ${error.message}`);
    }
  }

  function hideWorkflowNoise() {
    document.body.classList.add("muse-mode");

    const advanced = $("#workflowAdvanced");
    const data = $("#workflowData");
    const dashboard = $("#workflowDashboard");
    const predictor = $("#workflowPredictor");

    [advanced, data, dashboard, predictor].forEach((section) => {
      if (!section) return;
      section.classList.add("muse-secondary-workflow");
    });

    const jump = $("#workflowJumpNav");
    if (jump) jump.classList.add("muse-jump-muted");
  }

  function init() {
    createShell();

    document.addEventListener("click", (event) => {
      const trackButton = event.target.closest(".muse-track-prop");
      if (trackButton) {
        trackFromBoardButton(trackButton);
        return;
      }

      const button = event.target.closest(".muse-fill-prop");
      if (!button) return;
      fillFromBoardButton(button);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

