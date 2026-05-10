import { clear, h } from "../../shared/components/dom";
import { createVirtualWindow, DEFAULT_BOARD_OVERSCAN_ROWS, DEFAULT_BOARD_ROW_HEIGHT, isIndexInWindow, VirtualWindow } from "./virtualized";
import { BOARD_COLUMNS, renderBoardHeader, renderBoardRow } from "./BoardRow";
import { OutlierBoardRow } from "./utils";

export interface BoardTableRenderOptions {
  host: HTMLElement | null;
  rows: OutlierBoardRow[];
  selectedIndex: number;
  freshnessFallback: string;
  resetScroll?: boolean;
  rowHeight?: number;
  overscanRows?: number;
}

export interface BoardTableRenderResult {
  rowCount: number;
  renderedCount: number;
  startIndex: number;
  endIndex: number;
  totalHeight: number;
}

const controllers = new WeakMap<HTMLElement, BoardTableController>();

export function renderBoardTable(options: BoardTableRenderOptions): BoardTableRenderResult {
  if (!options.host) {
    return { rowCount: 0, renderedCount: 0, startIndex: 0, endIndex: 0, totalHeight: 0 };
  }
  let controller = controllers.get(options.host);
  if (!controller) {
    controller = new BoardTableController(options.host);
    controllers.set(options.host, controller);
  }
  return controller.update(options);
}

export function destroyBoardTable(host: HTMLElement | null): void {
  if (!host) return;
  const controller = controllers.get(host);
  controller?.destroy();
  controllers.delete(host);
}

class BoardTableController {
  private rows: OutlierBoardRow[] = [];
  private selectedIndex = -1;
  private freshnessFallback = "Research";
  private rowHeight = DEFAULT_BOARD_ROW_HEIGHT;
  private overscanRows = DEFAULT_BOARD_OVERSCAN_ROWS;
  private table: HTMLTableElement | null = null;
  private tbody: HTMLTableSectionElement | null = null;
  private raf = 0;
  private lastWindow: VirtualWindow = createVirtualWindow({ rowCount: 0, scrollTop: 0, viewportHeight: 0 });

  constructor(private readonly host: HTMLElement) {
    this.host.classList.add("is-virtualized");
    this.host.tabIndex = 0;
    this.host.setAttribute("role", "region");
    this.host.setAttribute("aria-label", "Scrollable outlier board");
    this.host.addEventListener("scroll", this.onScroll, { passive: true });
  }

  update(options: BoardTableRenderOptions): BoardTableRenderResult {
    this.rows = options.rows;
    this.selectedIndex = options.selectedIndex;
    this.freshnessFallback = options.freshnessFallback;
    this.rowHeight = options.rowHeight ?? DEFAULT_BOARD_ROW_HEIGHT;
    this.overscanRows = options.overscanRows ?? DEFAULT_BOARD_OVERSCAN_ROWS;
    this.host.style.setProperty("--ob-row-height", `${this.rowHeight}px`);

    if (!this.rows.length) {
      this.table = null;
      this.tbody = null;
      clear(this.host, [h("div", { className: "ob-empty" }, [h("strong", { text: "No props match these filters" }), h("span", { text: "Adjust market, side, date, or search." })])]);
      this.lastWindow = createVirtualWindow({ rowCount: 0, scrollTop: 0, viewportHeight: 0, rowHeight: this.rowHeight, overscanRows: this.overscanRows });
      return this.result();
    }

    this.ensureDom();
    if (options.resetScroll) this.host.scrollTop = 0;
    this.ensureSelectedRowVisible();
    this.paint();
    this.focusSelectedRow();
    return this.result();
  }

  destroy(): void {
    this.host.removeEventListener("scroll", this.onScroll);
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  private ensureDom(): void {
    if (this.table && this.tbody && this.table.isConnected) return;
    this.tbody = document.createElement("tbody");
    this.table = h("table", { className: "ob-table ob-virtual-table", attrs: { "aria-label": "Outlier board", "aria-rowcount": String(this.rows.length) } }, [renderBoardHeader(), this.tbody]);
    clear(this.host, [this.table]);
  }

  private ensureSelectedRowVisible(): void {
    if (this.selectedIndex < 0 || this.selectedIndex >= this.rows.length) return;
    const window = this.computeWindow();
    if (isIndexInWindow(this.selectedIndex, window)) return;

    const viewportHeight = this.host.clientHeight || this.rowHeight * 12;
    const rowTop = this.selectedIndex * this.rowHeight;
    const rowBottom = rowTop + this.rowHeight;
    if (rowTop < this.host.scrollTop) {
      this.host.scrollTop = Math.max(0, rowTop - this.rowHeight * 2);
    } else if (rowBottom > this.host.scrollTop + viewportHeight) {
      this.host.scrollTop = Math.max(0, rowBottom - viewportHeight + this.rowHeight * 2);
    }
  }

  private computeWindow(): VirtualWindow {
    return createVirtualWindow({
      rowCount: this.rows.length,
      scrollTop: this.host.scrollTop,
      viewportHeight: this.host.clientHeight,
      rowHeight: this.rowHeight,
      overscanRows: this.overscanRows,
    });
  }

  private paint(): void {
    if (!this.tbody || !this.table) return;
    this.table.setAttribute("aria-rowcount", String(this.rows.length));
    const window = this.computeWindow();
    this.lastWindow = window;
    const children: HTMLElement[] = [];
    if (window.offsetTop > 0) children.push(spacerRow(window.offsetTop));
    for (let index = window.startIndex; index < window.endIndex; index += 1) {
      children.push(renderBoardRow(this.rows[index], { index, selectedIndex: this.selectedIndex, freshnessFallback: this.freshnessFallback }));
    }
    if (window.offsetBottom > 0) children.push(spacerRow(window.offsetBottom));
    this.tbody.replaceChildren(...children);
  }

  private onScroll = (): void => {
    if (this.raf) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      this.paint();
    });
  };

  private focusSelectedRow(): void {
    if (this.selectedIndex < 0) return;
    const active = document.activeElement;
    if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement || active instanceof HTMLSelectElement) return;
    this.tbody?.querySelector<HTMLElement>(`[data-row-index="${this.selectedIndex}"]`)?.focus({ preventScroll: true });
  }

  private result(): BoardTableRenderResult {
    return {
      rowCount: this.rows.length,
      renderedCount: this.lastWindow.visibleCount,
      startIndex: this.lastWindow.startIndex,
      endIndex: this.lastWindow.endIndex,
      totalHeight: this.lastWindow.totalHeight,
    };
  }
}

function spacerRow(height: number): HTMLTableRowElement {
  const row = document.createElement("tr");
  row.className = "ob-virtual-spacer";
  row.setAttribute("aria-hidden", "true");
  const cell = document.createElement("td");
  cell.colSpan = BOARD_COLUMNS.length;
  cell.style.height = `${Math.max(0, height)}px`;
  cell.style.padding = "0";
  cell.style.border = "0";
  row.append(cell);
  return row;
}
