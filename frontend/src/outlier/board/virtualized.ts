export const DEFAULT_BOARD_ROW_HEIGHT = 58;
export const DEFAULT_BOARD_OVERSCAN_ROWS = 10;

export interface VirtualWindowInput {
  rowCount: number;
  scrollTop: number;
  viewportHeight: number;
  rowHeight?: number;
  overscanRows?: number;
}

export interface VirtualWindow {
  startIndex: number;
  endIndex: number;
  visibleCount: number;
  offsetTop: number;
  offsetBottom: number;
  rowHeight: number;
  totalHeight: number;
}

export function createVirtualWindow(input: VirtualWindowInput): VirtualWindow {
  const rowCount = Math.max(0, Math.floor(input.rowCount));
  const rowHeight = Math.max(1, input.rowHeight ?? DEFAULT_BOARD_ROW_HEIGHT);
  const overscanRows = Math.max(0, Math.floor(input.overscanRows ?? DEFAULT_BOARD_OVERSCAN_ROWS));
  const viewportHeight = Math.max(rowHeight, input.viewportHeight || rowHeight * 12);
  const scrollTop = Math.max(0, input.scrollTop || 0);

  if (rowCount === 0) {
    return { startIndex: 0, endIndex: 0, visibleCount: 0, offsetTop: 0, offsetBottom: 0, rowHeight, totalHeight: 0 };
  }

  const firstVisible = Math.floor(scrollTop / rowHeight);
  const visibleCapacity = Math.ceil(viewportHeight / rowHeight);
  const startIndex = Math.max(0, firstVisible - overscanRows);
  const endIndex = Math.min(rowCount, firstVisible + visibleCapacity + overscanRows + 1);
  const visibleCount = Math.max(0, endIndex - startIndex);
  const offsetTop = startIndex * rowHeight;
  const offsetBottom = Math.max(0, (rowCount - endIndex) * rowHeight);

  return {
    startIndex,
    endIndex,
    visibleCount,
    offsetTop,
    offsetBottom,
    rowHeight,
    totalHeight: rowCount * rowHeight,
  };
}

export function isIndexInWindow(index: number, window: VirtualWindow): boolean {
  return index >= window.startIndex && index < window.endIndex;
}
