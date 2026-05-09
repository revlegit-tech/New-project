import { h } from "../../shared/components/dom";
import { formatOdds, percent, signedPercent, text } from "../../shared/formatting";
import { marketLabel } from "../../shared/markets/markets";
import { rowFreshnessLabel, rowFreshnessTone } from "../trust";
import {
  edgeTone,
  edgeValue,
  matchup,
  OutlierBoardRow,
  readiness,
  readinessTone,
  rowImpliedProbability,
  rowLine,
  rowMarketKey,
  rowModelProbability,
  rowOdds,
  rowPlayer,
} from "./utils";

export const BOARD_COLUMNS = ["Player", "Market", "Line", "Odds", "Model", "Implied", "Edge", "Readiness", "Fresh"] as const;

export interface BoardRowRenderOptions {
  index: number;
  selectedIndex: number;
  freshnessFallback: string;
}

export function renderBoardHeader(): HTMLTableSectionElement {
  return h("thead", {}, [h("tr", {}, BOARD_COLUMNS.map((label) => h("th", { text: label })))]);
}

export function renderBoardRow(row: OutlierBoardRow, options: BoardRowRenderOptions): HTMLTableRowElement {
  return h("tr", {
    className: options.index === options.selectedIndex ? "is-selected" : "",
    dataset: { rowIndex: String(options.index) },
    attrs: { tabindex: "0", "aria-selected": options.index === options.selectedIndex ? "true" : "false" },
  }, [
    h("td", {}, [h("div", { className: "ob-player" }, [h("strong", { text: rowPlayer(row) }), h("span", { text: matchup(row) })])]),
    h("td", { text: marketLabel(rowMarketKey(row)) }),
    h("td", { text: text(rowLine(row)) }),
    h("td", { text: formatOdds(rowOdds(row)) }),
    h("td", { text: percent(rowModelProbability(row)) }),
    h("td", { text: percent(rowImpliedProbability(row)) }),
    h("td", {}, [h("span", { className: `ob-pill ${edgeTone(row)}`, text: signedPercent(edgeValue(row)) })]),
    h("td", {}, [h("span", { className: `ob-pill ${readinessTone(row)}`, text: readiness(row) })]),
    h("td", {}, [h("span", { className: `ob-pill ${rowFreshnessTone(row)}`, text: rowFreshnessLabel(row, options.freshnessFallback) })]),
  ]);
}
