import { todayIso } from "../../shared/formatting";

export function createInitialOutlierState() {
  return {
    rows: [] as any[],
    filteredRows: [] as any[],
    selectedIndex: -1,
    market: "",
    query: "",
    side: "",
    date: todayIso(),
    density: "standard",
    loading: false,
    status: null as any,
    exposure: null as any,
    requestId: "",
  };
}
