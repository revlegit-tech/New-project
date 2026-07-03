import { h } from "../../shared/components/dom";
import { formatOdds, percent, signedPercent, text } from "../../shared/formatting";
import { marketLabel } from "../../shared/markets/markets";
import { badgeToneClass, rowActionability, rowAttributionChip, rowBoardTrustSurface, rowFreshness, rowModelEdge, rowPropIdentity, rowReadiness, rowTrustChips } from "../trust";
import {
  matchup,
  OutlierBoardRow,
  rowBestBook,
  rowBestImpliedProbability,
  rowBestOdds,
  rowQuoteCount,
  rowLine,
  rowMarketKey,
  rowPlayer,
  rowSelectedBook,
  rowSelectedImpliedProbability,
  rowSelectedOdds,
} from "./utils";

export const BOARD_COLUMNS = [
  { key: "player", label: "Player" },
  { key: "market", label: "Market" },
  { key: "line", label: "Line" },
  { key: "americanOdds", label: "Odds" },
  { key: "modelProbabilityPercent", label: "Model" },
  { key: "impliedProbability", label: "Implied" },
  { key: "edgePercent", label: "Edge" },
  { key: "trustTier", label: "Trust" },
  { key: "calibrationStatus", label: "Cal" },
  { key: "probabilityGuardrailStatus", label: "Guard" },
  { key: "contextReadinessStatus", label: "Context" },
  { key: "unscoredReason", label: "Reason" },
  { key: "marketCapabilityStatus", label: "Capability" },
  { key: "readiness", label: "Readiness" },
  { key: "freshness", label: "Fresh" },
  { key: "action", label: "Action" },
] as const;

export interface BoardRowRenderOptions {
  index: number;
  selectedIndex: number;
  freshnessFallback: string;
  sportsbook: string;
}

export function renderBoardHeader(sortBy = "", sortDir: "asc" | "desc" = "desc"): HTMLTableSectionElement {
  return h("thead", {}, [h("tr", {}, BOARD_COLUMNS.map((column) => {
    const active = sortBy === column.key;
    const suffix = active ? (sortDir === "asc" ? " up" : " down") : "";
    return h("th", {}, [
      h("button", {
        className: `ob-sort-button${active ? " is-active" : ""}`,
        type: "button",
        text: `${column.label}${suffix}`,
        dataset: { sort: column.key },
        attrs: { "aria-sort": active ? (sortDir === "asc" ? "ascending" : "descending") : "none" },
      }),
    ]);
  }))]);
}

export function renderBoardRow(row: OutlierBoardRow, options: BoardRowRenderOptions): HTMLTableRowElement {
  const identity = rowPropIdentity(row);
  const modelEdge = rowModelEdge(row);
  const readiness = rowReadiness(row);
  const freshness = rowFreshness(row, options.freshnessFallback);
  const actionability = rowActionability(row);
  const attributionChip = rowAttributionChip(row);
  const boardTrust = rowBoardTrustSurface(row);
  const trustChips = rowTrustChips(row).filter((chip) => !attributionChip || chip.label !== attributionChip.label);
  const prioritizedChips = attributionChip ? [attributionChip, ...trustChips] : trustChips;
  const chips = prioritizedChips.slice(0, 6);
  const market = rowMarketKey(row) || identity.market;
  const sideLine = [identity.side, text(rowLine(row), "")].filter(Boolean).join(" ");
  const isExperimental = readiness.label.toLowerCase().includes("experimental") || readiness.status.includes("experimental");
  const isResearch = actionability.label.toLowerCase().includes("research");
  const researchTooltip = "Experimental model output. Research only. No staking recommendation.";
  return h("tr", {
    className: options.index === options.selectedIndex ? "is-selected" : "",
    dataset: { rowIndex: String(options.index), actionability: actionability.status, readiness: readiness.status, freshness: freshness.status },
    attrs: { tabindex: "0", "aria-selected": options.index === options.selectedIndex ? "true" : "false" },
  }, [
    h("td", { className: "ob-cell-player" }, [
      h("div", { className: "ob-player" }, [
        h("strong", { text: rowPlayer(row) }),
        h("span", { text: matchup(row) }),
        h("em", { text: [marketLabel(market), sideLine].filter(Boolean).join(" / ") }),
        h("div", { className: "ob-chip-row" }, chips.map((chip) => h("span", { className: `ob-pill ob-pill-mini ${badgeToneClass(chip.tone)}`, attrs: { title: chip.title }, text: chip.label }))),
      ]),
    ]),
    h("td", { text: marketLabel(market) }),
    h("td", { text: text(rowLine(row)) }),
    h("td", {}, [renderOddsCell(row, options.sportsbook)]),
    h("td", { text: percent(modelEdge.modelProbabilityPercent) }),
    h("td", { text: percent(modelEdge.impliedProbabilityPercent) }),
    h("td", {}, [h("span", { className: `ob-pill ob-pill-edge ${badgeToneClass(modelEdge.tone)}`, text: signedPercent(modelEdge.edgePercent) })]),
    ...boardTrust.chips.map((chip) => h("td", {}, [h("span", { className: `ob-pill ob-pill-mini ${badgeToneClass(chip.tone)}`, attrs: { title: chip.title }, text: chip.label })])),
    h("td", {}, [h("span", { className: `ob-pill ${badgeToneClass(readiness.tone)}${isExperimental ? " ob-pill-experimental" : ""}`, attrs: { title: isExperimental ? researchTooltip : readiness.warnings[0] || readiness.status }, text: readiness.label })]),
    h("td", {}, [h("span", { className: `ob-pill ${badgeToneClass(freshness.tone)}`, attrs: { title: freshness.source || freshness.status }, text: freshness.label })]),
    h("td", {}, [h("span", { className: `ob-pill ob-pill-action ${badgeToneClass(actionability.tone)}${isResearch ? " ob-pill-research" : ""}`, attrs: { title: isResearch ? researchTooltip : actionability.suggestedStake }, text: actionability.label })]),
  ]);
}

function renderOddsCell(row: OutlierBoardRow, sportsbook: string): HTMLElement {
  const bestMode = !sportsbook;
  const book = bestMode ? rowBestBook(row) : sportsbook;
  const odds = bestMode ? rowBestOdds(row) : rowSelectedOdds(row);
  const implied = bestMode ? rowBestImpliedProbability(row) : rowSelectedImpliedProbability(row);
  const status = String(row.selectedBookQuoteStatus || "").toLowerCase();
  const quoteCount = rowQuoteCount(row);
  const bestBook = rowBestBook(row);
  const bestOdds = rowBestOdds(row);
  const hasSelectedQuote = odds !== null && odds !== undefined && odds !== "" && !status.includes("no_quote");

  if (!bestMode && !hasSelectedQuote) {
    return h("div", { className: "ob-odds-cell is-missing" }, [
      h("strong", { text: `${book}: No quote` }),
      h("span", { text: bestBook ? `Best ${bestBook} ${formatOdds(bestOdds)}` : "No best quote" }),
    ]);
  }

  return h("div", { className: "ob-odds-cell" }, [
    h("strong", { text: [book || "Best available", formatOdds(odds)].filter(Boolean).join(" ") }),
    h("span", { text: [percent(implied), quoteCount ? `${quoteCount} books` : ""].filter(Boolean).join(" / ") }),
    !bestMode && bestBook && bestBook !== book ? h("em", { text: `Best ${bestBook} ${formatOdds(bestOdds)}` }) : h("em", { text: "" }),
  ]);
}
