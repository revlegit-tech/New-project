import { createElement, jsonFetch, replaceChildren, text, renderStatePanel, listen, formatOdds } from "/outlier-shared.js";

let mounted = false;

export async function mount() {
  if (mounted) return;
  mounted = true;
  listen("outlier:view", (event) => {
    if (event.detail.module === "picks") renderPicks();
  });
}

async function renderPicks() {
  const host = document.getElementById("outlierWorkspace");
  if (!host) return;
  replaceChildren(host, [renderStatePanel("Loading picks", "Fetching tracked positions and bankroll exposure.", "partial")]);
  try {
    const { payload, requestId } = await jsonFetch("/api/my-picks");
    const picks = Array.isArray(payload?.picks) ? payload.picks : [];
    const exposure = payload?.exposure || {};
    replaceChildren(host, [
      createElement("section", { className: "ob-picks-module" }, [
        createElement("div", { className: "ob-section-heading" }, [
          createElement("div", {}, [createElement("p", { className: "ob-kicker", text: "Portfolio" }), createElement("h2", { text: "My Picks & Exposure" })]),
          createElement("span", { className: "ob-board-meta", text: requestId || "Protected mutation surface" }),
        ]),
        exposureCards(exposure),
        picks.length ? pickList(picks) : renderStatePanel("No tracked picks", "Saved picks will appear here after a protected mutation request succeeds.", "partial"),
      ]),
    ]);
  } catch (error) {
    replaceChildren(host, [renderStatePanel("Picks unavailable", text(error?.message, "Protected picks endpoint is unavailable."), "bad")]);
  }
}

function exposureCards(exposure) {
  return createElement("dl", { className: "ob-metric-cards" }, [
    ["Open risk", exposure.openRisk || exposure.totalRisk || "--"],
    ["Open positions", exposure.openCount || exposure.count || 0],
    ["Mode", "Protected"],
  ].map(([label, value]) => createElement("div", { className: "ob-metric-card" }, [createElement("dt", { text: label }), createElement("dd", { text: text(value) })])));
}

function pickList(picks) {
  return createElement("div", { className: "ob-pick-list" }, picks.map((pick) => createElement("article", { className: "ob-pick-card" }, [
    createElement("p", { className: "ob-kicker", text: text(pick.status, "Tracked") }),
    createElement("h3", { text: text(pick.player || pick.team || pick.market, "Pick") }),
    createElement("p", { text: [pick.side, pick.line, pick.market].filter(Boolean).join(" ") }),
    createElement("p", { text: `Odds ${formatOdds(pick.odds || pick.americanOdds)}` }),
  ])));
}

export const __testHooks = { exposureCards, pickList };
