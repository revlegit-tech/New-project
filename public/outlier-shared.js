export const OUTLIER_MODULE_VERSION = "phase8-modular-v1";

export const MARKETS = [
  ["", "All"],
  ["batter_total_bases", "Batter Bases"],
  ["batter_hits", "Batter Hits"],
  ["batter_home_runs", "Home Runs"],
  ["pitcher_strikeouts", "Pitcher Ks"],
  ["pitcher_hits_allowed", "Hits Allowed"],
  ["pitcher_earned_runs", "Earned Runs"],
  ["team_total_runs", "Team Runs"],
  ["team_first_to_score", "Team First"],
];

export const MODULES = {
  today: { label: "Today", module: "board", primary: true },
  props: { label: "Props", module: "board", primary: true },
  games: { label: "Games", module: "board", primary: true },
  picks: { label: "My Picks", module: "picks" },
  models: { label: "Model Room", module: "model-room" },
  health: { label: "Data Health", module: "model-room" },
  admin: { label: "Admin", module: "admin", devOnly: true },
};

export function qs(selector, root = document) {
  return root.querySelector(selector);
}

export function qsa(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

export function text(value, fallback = "--") {
  const raw = value === null || value === undefined ? "" : String(value).trim();
  return raw || fallback;
}

export function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function percent(value, fallback = "--") {
  const parsed = number(value, NaN);
  return Number.isFinite(parsed) ? `${parsed.toFixed(parsed % 1 ? 1 : 0)}%` : fallback;
}

export function signedPercent(value) {
  const parsed = number(value, NaN);
  if (!Number.isFinite(parsed)) return "--";
  return `${parsed >= 0 ? "+" : ""}${parsed.toFixed(1)}%`;
}

export function formatOdds(value) {
  const raw = text(value, "");
  if (!raw) return "--";
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  return parsed > 0 ? `+${parsed}` : String(parsed);
}

export function todayIso() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

export function createElement(tagName, options = {}, children = []) {
  const element = document.createElement(tagName);
  if (options.className) element.className = options.className;
  if (options.id) element.id = options.id;
  if (options.text !== undefined) element.textContent = text(options.text, "");
  if (options.title) element.title = text(options.title, "");
  if (options.type) element.type = options.type;
  if (options.value !== undefined) element.value = String(options.value);
  if (options.placeholder) element.placeholder = options.placeholder;
  if (options.name) element.name = options.name;
  if (options.dataset) {
    Object.entries(options.dataset).forEach(([key, value]) => {
      element.dataset[key] = String(value);
    });
  }
  if (options.attrs) {
    Object.entries(options.attrs).forEach(([key, value]) => {
      if (value !== false && value !== null && value !== undefined) {
        element.setAttribute(key, String(value));
      }
    });
  }
  const list = Array.isArray(children) ? children : [children];
  list.filter(Boolean).forEach((child) => {
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  });
  return element;
}

export function button(label, options = {}) {
  return createElement("button", {
    className: options.className || "ob-chip",
    type: "button",
    text: label,
    dataset: options.dataset,
    attrs: options.attrs,
  });
}

export function replaceChildren(target, children = []) {
  if (!target) return;
  target.replaceChildren(...children.filter(Boolean));
}

export function dispatch(name, detail = {}) {
  document.dispatchEvent(new CustomEvent(name, { detail }));
}

export function listen(name, handler) {
  document.addEventListener(name, handler);
  return () => document.removeEventListener(name, handler);
}

export async function jsonFetch(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  const requestId = response.headers.get("X-Request-Id") || "";
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    if (response.ok) throw error;
  }
  if (!response.ok) {
    const message = payload && payload.error ? payload.error : `HTTP ${response.status}`;
    const error = new Error(requestId ? `${message} (${requestId})` : message);
    error.status = response.status;
    error.requestId = requestId;
    throw error;
  }
  return { payload, requestId };
}

export function normalizeRows(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.rows)) return payload.rows;
  if (Array.isArray(payload?.data?.rows)) return payload.data.rows;
  if (Array.isArray(payload?.board)) return payload.board;
  return [];
}

export function propLabel(row) {
  const side = text(row?.side || row?.rawLabel || row?.pickSide, "");
  const line = text(row?.line || row?.propLine, "");
  const market = text(row?.marketDisplay || row?.market || row?.propType, "Prop");
  return [side, line, market].filter(Boolean).join(" ");
}

export function rowKey(row) {
  return [
    row?.player || row?.playerName || row?.team || "unknown",
    row?.market || row?.marketDisplay || "market",
    row?.line || "line",
    row?.rawLabel || row?.side || "side",
  ].map((part) => String(part).toLowerCase().replace(/\s+/g, "-")).join("|");
}

export function renderStatePanel(title, copy, tone = "partial") {
  const panel = createElement("section", { className: `ob-state ob-state-${tone}` });
  panel.append(
    createElement("p", { className: "ob-kicker", text: tone === "bad" ? "Missing Data" : "Research Only" }),
    createElement("h2", { text: title }),
    createElement("p", { text: copy })
  );
  return panel;
}
