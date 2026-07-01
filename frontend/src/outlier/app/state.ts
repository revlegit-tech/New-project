import { todayIso } from "../../shared/formatting";
import { DensityMode } from "./density";

export function createInitialOutlierState() {
  return {
    rows: [] as any[],
    filteredRows: [] as any[],
    selectedIndex: -1,
    market: "",
    actionLabel: "",
    marketCapabilityStatus: "",
    modelProductionEligible: "",
    productionStatus: "",
    calibrationStatus: "",
    backtestStatus: "",
    freshnessStatus: "",
    missingDataOnly: false,
    trustedMarketsOnly: false,
    query: "",
    side: "",
    date: todayIso(),
    density: "compact" as DensityMode,
    loading: false,
    status: null as any,
    boardFreshness: null as any,
    boardTrust: null as any,
    marketRegistry: null as any,
    marketCoverage: null as any,
    exposure: null as any,
    requestId: "",
  };
}
