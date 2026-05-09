export interface ApiResult<T> {
  payload: T;
  requestId: string;
}

export async function jsonFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const response = await fetch(path, {
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init.headers || {}),
    },
    ...init,
  });
  const requestId = response.headers.get("X-Request-Id") || response.headers.get("x-request-id") || "";
  let payload: T | null = null;
  try {
    payload = (await response.json()) as T;
  } catch (error) {
    if (response.ok) throw error;
  }
  if (!response.ok) {
    const message = payload && typeof payload === "object" && "error" in payload ? String((payload as Record<string, unknown>).error) : `HTTP ${response.status}`;
    throw new Error(requestId ? `${message} (${requestId})` : message);
  }
  return { payload: payload as T, requestId };
}
