import { jsonFetch } from "../../shared/api/client";
import {
  MlModelsStatusResponse,
  ProductionGatesResponse,
  ShadowFreshnessResponse,
  ShadowReadinessResponse,
  ShadowSummaryResponse,
} from "../types/modelAudit";

function marketQuery(market?: string): string {
  const params = new URLSearchParams();
  if (market) params.set("market", market);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function getMlModelsStatus(): Promise<MlModelsStatusResponse> {
  const { payload } = await jsonFetch<MlModelsStatusResponse>("/api/ml-models/status");
  return payload;
}

export async function getShadowSummary(market?: string): Promise<ShadowSummaryResponse> {
  const { payload } = await jsonFetch<ShadowSummaryResponse>(`/api/ml-models/shadow-summary${marketQuery(market)}`);
  return payload;
}

export async function getShadowReadiness(market?: string): Promise<ShadowReadinessResponse> {
  const { payload } = await jsonFetch<ShadowReadinessResponse>(`/api/ml-models/shadow-readiness${marketQuery(market)}`);
  return payload;
}

export async function getShadowFreshness(market?: string): Promise<ShadowFreshnessResponse> {
  const { payload } = await jsonFetch<ShadowFreshnessResponse>(`/api/ml-models/shadow-freshness${marketQuery(market)}`);
  return payload;
}

export async function getProductionGates(market?: string): Promise<ProductionGatesResponse> {
  const { payload } = await jsonFetch<ProductionGatesResponse>(`/api/ml-models/production-gates${marketQuery(market)}`);
  return payload;
}
