import { createElement, replaceChildren, renderStatePanel, listen } from "/outlier-shared.js";

let mounted = false;

export async function mount() {
  if (mounted) return;
  mounted = true;
  listen("outlier:view", (event) => {
    if (event.detail.module === "admin") renderAdminQuarantine();
  });
}

function renderAdminQuarantine() {
  const host = document.getElementById("outlierWorkspace");
  if (!host) return;
  replaceChildren(host, [
    createElement("section", { className: "ob-admin-module" }, [
      createElement("div", { className: "ob-section-heading" }, [
        createElement("div", {}, [createElement("p", { className: "ob-kicker", text: "Quarantined" }), createElement("h2", { text: "Admin workflows are not product UI" })]),
      ]),
      renderStatePanel(
        "Workflow quarantine active",
        "Sync, training, backfill, grading, and cache-repair actions must remain behind CLI, scheduler, or authenticated admin boundaries. They are intentionally not executable from the betting shell.",
        "partial"
      ),
      createElement("ul", { className: "ob-admin-list" }, [
        createElement("li", { text: "Weather, Savant, odds-movement, umpire, and platoon sync jobs" }),
        createElement("li", { text: "Model refresh, training, grading, and season-cache backfills" }),
        createElement("li", { text: "Any workflow that writes files, calls paid APIs, or mutates bankroll/pick state" }),
      ]),
    ]),
  ]);
}

export const __testHooks = { renderAdminQuarantine };
