import { h } from "../../shared/components/dom";
import { formatOdds, percent, signedPercent, text } from "../../shared/formatting";
import { marketLabel } from "../../shared/markets/markets";
import { badgeToneClass, rowActionability, rowFreshness, rowModelEdge, rowPropIdentity, rowReadiness } from "../trust";
import {
  matchup,
  OutlierBoardRow,
  rowLine,
  rowMarketKey,
  rowOdds,
  rowPlayer,
} from "./utils";

export const BOARD_COLUMNS = ["Player", "Market", "Line", "Odds", "Model", "Implied", "Edge", "Readiness", "Fresh", "Action"] as const;

export interface BoardRowRenderOptions {
  index: number;
  selectedIndex: number;
  freshnessFallback: string;
}

export function renderBoardHeader(): HTMLTableSectionElement {
  return h("thead", {}, [h("tr", {}, BOARD_COLUMNS.map((label) => h("th", { text: label })))]);
}

export function renderBoardRow(row: OutlierBoardRow, options: BoardRowRenderOptions): HTMLTableRowElement {
  const identity = rowPropIdentity(row);
  const modelEdge = rowModelEdge(row);
  const readiness = rowReadiness(row);
  const freshness = rowFreshness(row, options.freshnessFallback);
  const actionability = rowActionability(row);
  const market = rowMarketKey(row) || identity.market;
  const sideLine = [identity.side, text(rowLine(row), "")].filter(Boolean).join(" ");
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
      ]),
    ]),
    h("td", { text: marketLabel(market) }),
    h("td", { text: text(rowLine(row)) }),
    h("td", { text: formatOdds(rowOdds(row)) }),
    h("td", { text: percent(modelEdge.modelProbabilityPercent) }),
    h("td", { text: percent(modelEdge.impliedProbabilityPercent) }),
    h("td", {}, [h("span", { className: `ob-pill ob-pill-edge ${badgeToneClass(modelEdge.tone)}`, text: signedPercent(modelEdge.edgePercent) })]),
    h("td", {}, [h("span", { className: `ob-pill ${badgeToneClass(readiness.tone)}`, attrs: { title: readiness.warnings[0] || readiness.status }, text: readiness.label })]),
    h("td", {}, [h("span", { className: `ob-pill ${badgeToneClass(freshness.tone)}`, attrs: { title: freshness.source || freshness.status }, text: freshness.label })]),
    h("td", {}, [h("span", { className: `ob-pill ob-pill-action ${badgeToneClass(actionability.tone)}`, attrs: { title: actionability.suggestedStake }, text: actionability.label })]),
  ]);
}
