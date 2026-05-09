export interface BoardRow {
  [key: string]: unknown;
  id?: string;
  date?: string;
  player?: string;
  playerName?: string;
  team?: string;
  opponent?: string;
  away?: string;
  home?: string;
  market?: string;
  marketDisplay?: string;
  rawLabel?: string;
  side?: string;
  line?: number | string;
  propLine?: number | string;
  americanOdds?: number | string;
  odds?: number | string;
  finalEdgePercent?: number | string;
  edge?: number | string;
  edgePercent?: number | string;
  modelProbability?: number | string;
  impliedProbability?: number | string;
  confidence?: string;
  readiness?: string;
  readinessLabel?: string;
}
