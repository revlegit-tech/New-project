export type Sport = "MLB" | "NBA" | "NHL" | "Soccer" | "WNBA" | "NCAAFB";
export type MarketScope = "player" | "team" | "game";

export interface MarketDefinition {
  key: string;
  label: string;
  sport: Sport;
  scope: MarketScope;
  defaultLineDisplay: string;
  modelReady: boolean;
  enabled: boolean;
  productionUi: boolean;
  description: string;
}

export const MARKETS: MarketDefinition[] = [
  {
    key: "batter_hits",
    label: "Batter Hits",
    sport: "MLB",
    scope: "player",
    defaultLineDisplay: "0.5+ hits",
    modelReady: true,
    enabled: true,
    productionUi: true,
    description: "Batter hit props with model and recent-form context.",
  },
  {
    key: "batter_total_bases",
    label: "Batter Total Bases",
    sport: "MLB",
    scope: "player",
    defaultLineDisplay: "1.5+ bases",
    modelReady: true,
    enabled: true,
    productionUi: true,
    description: "Total bases research for hitters.",
  },
  {
    key: "batter_home_runs",
    label: "Batter Home Runs",
    sport: "MLB",
    scope: "player",
    defaultLineDisplay: "0.5 HR",
    modelReady: false,
    enabled: true,
    productionUi: true,
    description: "Research-only HR surface until model readiness is promoted.",
  },
  {
    key: "pitcher_strikeouts",
    label: "Pitcher Strikeouts",
    sport: "MLB",
    scope: "player",
    defaultLineDisplay: "4.5 Ks",
    modelReady: true,
    enabled: true,
    productionUi: true,
    description: "Pitcher strikeout props with workload and opponent context.",
  },
  {
    key: "pitcher_hits_allowed",
    label: "Pitcher Hits Allowed",
    sport: "MLB",
    scope: "player",
    defaultLineDisplay: "5.5 hits",
    modelReady: false,
    enabled: true,
    productionUi: true,
    description: "Research-only pitcher contact prevention market.",
  },
  {
    key: "pitcher_earned_runs",
    label: "Pitcher Earned Runs",
    sport: "MLB",
    scope: "player",
    defaultLineDisplay: "2.5 ER",
    modelReady: false,
    enabled: true,
    productionUi: true,
    description: "Research-only run prevention market.",
  },
  {
    key: "team_total_runs",
    label: "Team Total Runs",
    sport: "MLB",
    scope: "team",
    defaultLineDisplay: "4.5 runs",
    modelReady: false,
    enabled: true,
    productionUi: true,
    description: "Team run total market; visible as research-only until backed by model cards.",
  },
  {
    key: "team_first_to_score",
    label: "Team First To Score",
    sport: "MLB",
    scope: "team",
    defaultLineDisplay: "first score",
    modelReady: false,
    enabled: true,
    productionUi: true,
    description: "Team first-score market; research-only trust state.",
  },
];

export const PRODUCTION_MARKETS = MARKETS.filter((market) => market.enabled && market.productionUi);

export const MARKET_SELECT_OPTIONS = [
  { key: "", label: "All MLB markets", modelReady: false },
  ...PRODUCTION_MARKETS.map((market) => ({ key: market.key, label: market.label, modelReady: market.modelReady })),
];

export interface RegistryMarket {
  marketKey: string;
  displayName: string;
  category: string;
  propType: string;
  sideType: string;
  hasOdds: boolean;
  hasModel: boolean;
  hasAltLines: boolean;
  rowCount: number;
  quoteCount: number;
  availableBooks: string[];
  supportedInBoard: boolean;
  supportedInReport: boolean;
  supportedInModel: boolean;
  modelStatus: string;
  warning?: string;
  badges?: string[];
  hidden?: boolean;
  hiddenReason?: string;
  missingModelMarket?: boolean;
  modelUnavailable?: boolean;
}

export interface RegistryMarketGroup {
  key: string;
  label: string;
  rowCount: number;
  quoteCount: number;
  markets: RegistryMarket[];
}

export interface MarketRegistryPayload {
  markets: RegistryMarket[];
  groups: RegistryMarketGroup[];
  marketCoverage?: any;
  coverage?: any;
}

export function fallbackMarketGroups(): RegistryMarketGroup[] {
  return [
    { key: "all", label: "All Markets", rowCount: 0, quoteCount: 0, markets: [] },
    {
      key: "batter",
      label: "Batter Props",
      rowCount: 0,
      quoteCount: 0,
      markets: MARKET_SELECT_OPTIONS.filter((item) => item.key.startsWith("batter_")).map((item) => fallbackRegistryMarket(item.key, item.label)),
    },
    {
      key: "pitcher",
      label: "Pitcher Props",
      rowCount: 0,
      quoteCount: 0,
      markets: MARKET_SELECT_OPTIONS.filter((item) => item.key.startsWith("pitcher_")).map((item) => fallbackRegistryMarket(item.key, item.label)),
    },
    {
      key: "team",
      label: "Team Markets",
      rowCount: 0,
      quoteCount: 0,
      markets: MARKET_SELECT_OPTIONS.filter((item) => item.key.startsWith("team_")).map((item) => fallbackRegistryMarket(item.key, item.label)),
    },
  ];
}

function fallbackRegistryMarket(key: string, label: string): RegistryMarket {
  const modelReady = Boolean(MARKETS.find((market) => market.key === key)?.modelReady);
  return {
    marketKey: key,
    displayName: label,
    category: key.startsWith("pitcher_") ? "pitcher" : key.startsWith("team_") ? "team" : "batter",
    propType: key.startsWith("team_") ? "team" : "player",
    sideType: "over_under",
    hasOdds: false,
    hasModel: modelReady,
    hasAltLines: key.endsWith("_alt"),
    rowCount: 0,
    quoteCount: 0,
    availableBooks: [],
    supportedInBoard: true,
    supportedInReport: true,
    supportedInModel: modelReady,
    modelStatus: modelReady ? "missing_model" : "model_unavailable",
    badges: modelReady ? ["Modeled"] : [],
  };
}

export function marketLabel(key: string | undefined | null): string {
  if (!key) return "Prop";
  return MARKETS.find((market) => market.key === key)?.label || String(key).replace(/_/g, " ");
}
