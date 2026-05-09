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

export function marketLabel(key: string | undefined | null): string {
  if (!key) return "Prop";
  return MARKETS.find((market) => market.key === key)?.label || String(key).replace(/_/g, " ");
}
