// Typed API client for the VARSHA Weather AI FastAPI backend.
//
// Every value displayed by the dashboard comes from these calls. The client
// surfaces FastAPI error payloads ({error, message, hint} or pydantic lists)
// as readable ApiError objects so the UI never shows raw stack traces.

import { API_BASE_URL } from "./constants";
import type {
  AuditLogsResponse,
  BacktestParams,
  BacktestResponse,
  DataSummaryResponse,
  DistrictListResponse,
  ForecastExplainResponse,
  ForecastParams,
  ForecastResponse,
  HealthResponse,
  ModelReportResponse,
  ModelStatusResponse,
  OverrideCreateBody,
  OverrideCreateResponse,
  SimulateFailureBody,
  SimulateFailureResponse,
} from "@/types/api";

export class ApiError extends Error {
  status: number;
  code?: string;
  hint?: string;

  constructor(status: number, message: string, code?: string, hint?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.hint = hint;
  }
}

function parseErrorPayload(status: number, body: unknown): ApiError {
  let message = `Request failed (HTTP ${status}).`;
  let code: string | undefined;
  let hint: string | undefined;
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") {
    message = detail;
  } else if (Array.isArray(detail)) {
    const parts = detail
      .map((e) => (e as { msg?: string } | null)?.msg)
      .filter((m): m is string => Boolean(m));
    if (parts.length) message = parts.join("; ");
  } else if (typeof detail === "object" && detail !== null) {
    const d = detail as { message?: string; error?: string; hint?: string };
    if (d.message) message = d.message;
    code = d.error;
    hint = d.hint;
  }
  return new ApiError(status, message, code, hint);
}

/** URLSearchParams builder that skips empty/undefined values. */
export function buildQuery(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 25000,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        0,
        `The backend did not respond within ${Math.round(timeoutMs / 1000)}s at ${API_BASE_URL}.`,
        "timeout",
      );
    }
    throw new ApiError(
      0,
      `Cannot reach the backend at ${API_BASE_URL}. Is the FastAPI server running on port 8001?`,
      "network",
    );
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    throw parseErrorPayload(res.status, body);
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

export const api = {
  health: () => request<HealthResponse>("/health", {}, 5000),

  districts: () => request<DistrictListResponse>("/districts"),

  dataSummary: () => request<DataSummaryResponse>("/data/summary"),

  forecast: (params: ForecastParams) =>
    request<ForecastResponse>(
      `/forecast${buildQuery({ ...params, simulate_failure_source: params.simulate_failure_source ?? undefined })}`,
    ),

  explain: (params: ForecastParams) =>
    request<ForecastExplainResponse>(
      `/forecast/explain${buildQuery({ ...params, simulate_failure_source: params.simulate_failure_source ?? undefined })}`,
    ),

  simulateSourceFailure: (body: SimulateFailureBody) =>
    request<SimulateFailureResponse>(
      "/forecast/simulate-source-failure",
      { method: "POST", body: JSON.stringify(body) },
    ),

  backtest: (params: BacktestParams) =>
    request<BacktestResponse>(`/backtest${buildQuery(params)}`, {}, 60000),

  /** Fetch the backend-generated CSV and trigger a local file download. */
  downloadBacktestCsv: async (params: BacktestParams): Promise<void> => {
    const url = `${API_BASE_URL}/backtest/report${buildQuery({ ...params, format: "csv" })}`;
    let res: Response;
    try {
      res = await fetch(url, { cache: "no-store" });
    } catch {
      throw new ApiError(0, `Cannot reach the backend at ${API_BASE_URL} to download the report.`, "network");
    }
    if (!res.ok) {
      let body: unknown;
      try {
        body = await res.json();
      } catch {
        body = null;
      }
      throw parseErrorPayload(res.status, body);
    }
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `varsha-backtest-${params.district}-${params.lead_hours}h-${params.start_date}_${params.end_date}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  },

  modelStatus: () => request<ModelStatusResponse>("/model/status"),

  modelReport: (leadHours?: number) =>
    request<ModelReportResponse>(
      `/model/report${leadHours !== undefined ? `?lead_hours=${leadHours}` : ""}`,
    ),

  trainModel: (leadHours: number, forceRetrain = false) =>
    request<ModelReportResponse>(
      "/model/train",
      { method: "POST", body: JSON.stringify({ lead_hours: leadHours, force_retrain: forceRetrain }) },
      120000,
    ),

  auditLogs: (limit = 50) =>
    request<AuditLogsResponse>(`/audit-logs?limit=${limit}`),

  createOverride: (body: OverrideCreateBody) =>
    request<OverrideCreateResponse>(
      "/overrides",
      { method: "POST", body: JSON.stringify(body) },
    ),
};