"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CloudRain, WifiOff } from "lucide-react";
import AppHeader, { type HealthState } from "@/components/AppHeader";
import AuditTimeline from "@/components/AuditTimeline";
import DataModeBanner from "@/components/DataModeBanner";
import DemoStrip from "@/components/DemoStrip";
import DistrictMap from "@/components/DistrictMap";
import DynamicWeights from "@/components/DynamicWeights";
import ErrorState from "@/components/ErrorState";
import ForecastControls, { type ForecastSelection } from "@/components/ForecastControls";
import ForecastExplanation from "@/components/ForecastExplanation";
import ForecastHero from "@/components/ForecastHero";
import ModelStatusPanel from "@/components/ModelStatusPanel";
import OverrideModal from "@/components/OverrideModal";
import RiskGuidance from "@/components/RiskGuidance";
import SourceComparison from "@/components/SourceComparison";
import SourceFailurePanel from "@/components/SourceFailurePanel";
import SystemDetails from "@/components/SystemDetails";
import ValidationPanel from "@/components/ValidationPanel";
import { api } from "@/lib/api";
import {
  API_BASE_URL,
  DEMO_SCENARIO,
  FOOTER_LINE,
  type Role,
  type ScenarioId,
} from "@/lib/constants";
import { useAsync } from "@/lib/useApi";
import type {
  AuditLogsResponse,
  DataSummaryResponse,
  District,
  ForecastExplainResponse,
  ForecastResponse,
  HealthResponse,
  ModelReportResponse,
  ModelStatusResponse,
  OverrideCreateResponse,
} from "@/types/api";

export default function DashboardPage() {
  const [role, setRole] = useState<Role>("forecaster");

  // Meta state (districts, summary, health).
  const [districts, setDistricts] = useState<District[] | null>(null);
  const [summary, setSummary] = useState<DataSummaryResponse | null>(null);
  const [metaError, setMetaError] = useState<Error | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthState, setHealthState] = useState<HealthState>("checking");

  // Selection and scenario.
  const [selection, setSelection] = useState<ForecastSelection>({
    districtId: "",
    date: "",
    lead: 24,
  });
  const [scenario, setScenario] = useState<ScenarioId>("normal");

  // Forecast + explanation (backend computed).
  const forecastAsync = useAsync<ForecastResponse>();
  const explainAsync = useAsync<ForecastExplainResponse>();

  // Model status + per-lead report.
  const modelAsync = useAsync<ModelStatusResponse>();
  const reportAsync = useAsync<ModelReportResponse>();

  // Audit timeline.
  const auditAsync = useAsync<AuditLogsResponse>();

  // Override dialog.
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideSubmitting, setOverrideSubmitting] = useState(false);
  const [overrideError, setOverrideError] = useState<Error | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initializedRef = useRef(false);

  const checkHealth = useCallback(async () => {
    try {
      const result = await api.health();
      setHealth(result);
      setHealthState("connected");
    } catch {
      setHealthState((previous) => (previous === "connected" ? "reconnecting" : "offline"));
    }
  }, []);

  const loadMeta = useCallback(async () => {
    setMetaLoading(true);
    setMetaError(null);
    try {
      const [districtResponse, summaryResponse, healthResponse] = await Promise.all([
        api.districts(),
        api.dataSummary(),
        api.health(),
      ]);
      setDistricts(districtResponse.districts);
      setSummary(summaryResponse);
      setHealth(healthResponse);
      setHealthState("connected");

      // Safe defaults derived only from backend-provided data.
      const firstDistrict = districtResponse.districts[0]?.district_id ?? "";
      const safeDate = summaryResponse.last_valid_date ?? summaryResponse.first_valid_date ?? "";
      setSelection((previous) => ({
        ...previous,
        districtId: previous.districtId || firstDistrict,
        date: previous.date || safeDate,
      }));
      initializedRef.current = true;
    } catch (err) {
      setMetaError(err instanceof Error ? err : new Error(String(err)));
      await checkHealth();
    } finally {
      setMetaLoading(false);
    }
  }, [checkHealth]);

  // Health polling (every 20 seconds).
  useEffect(() => {
    void checkHealth();
    const timer = setInterval(() => void checkHealth(), 20000);
    return () => clearInterval(timer);
  }, [checkHealth]);

  // Initial meta load.
  useEffect(() => {
    void loadMeta();
  }, [loadMeta]);

  // Load model status + audit timeline on mount.
  useEffect(() => {
    void modelAsync.exec(() => api.modelStatus());
    void auditAsync.exec(() => api.auditLogs(50));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const failureSource = scenario === "normal" ? null : scenario;

  const runForecast = useCallback(() => {
    if (!selection.districtId || !selection.date) return;
    const params = {
      district: selection.districtId,
      date: selection.date,
      lead_hours: selection.lead,
      simulate_failure_source: failureSource,
    };
    void forecastAsync.exec(() => api.forecast(params));
    void explainAsync.exec(() => api.explain(params));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection.districtId, selection.date, selection.lead, failureSource]);

  // Auto-run whenever the (valid) selection or scenario changes, debounced.
  useEffect(() => {
    if (!initializedRef.current) return;
    if (!selection.districtId || !selection.date) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runForecast(), 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [selection.districtId, selection.date, selection.lead, scenario, runForecast]);

  // Load the model report for the selected lead.
  useEffect(() => {
    if (selection.lead) void reportAsync.exec(() => api.modelReport(selection.lead));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection.lead]);

  const refreshModel = useCallback(() => {
    void modelAsync.exec(() => api.modelStatus());
    if (selection.lead) void reportAsync.exec(() => api.modelReport(selection.lead));
  }, [selection.lead, modelAsync, reportAsync]);

  const handleRoleChange = useCallback((nextRole: Role) => {
    setRole(nextRole);
    if (nextRole === "viewer") setOverrideOpen(false);
  }, []);

  const loadDemoScenario = useCallback(() => {
    if (!initializedRef.current) return;
    setScenario(DEMO_SCENARIO.scenario);
    setSelection((previous) => ({
      ...previous,
      districtId: DEMO_SCENARIO.districtId,
      date: DEMO_SCENARIO.date,
      lead: DEMO_SCENARIO.lead,
    }));
  }, []);

  const handleOverrideSubmit = useCallback(
    (payload: {
      district: string;
      date: string;
      lead_hours: number;
      selected_risk_level: "Low" | "Moderate" | "High" | "Critical";
      reason: string;
      reviewer_name: string | null;
      role: "forecaster" | "administrator";
    }) => {
      setOverrideSubmitting(true);
      setOverrideError(null);
      void api
        .createOverride({ ...payload, role: role === "administrator" ? "administrator" : "forecaster" })
        .then((response: OverrideCreateResponse) => {
          setOverrideSubmitting(false);
          setOverrideOpen(false);
          void auditAsync.exec(() => api.auditLogs(50));
          return response;
        })
        .catch((err: Error) => {
          setOverrideSubmitting(false);
          setOverrideError(err);
        });
    },
    [role, auditAsync],
  );

  const offline = healthState === "offline";
  const forecastLoading = forecastAsync.status === "loading";
  const modelMode: "trained" | "fallback" | "unavailable" = modelAsync.data?.inference_ready
    ? "trained"
    : modelAsync.data !== null
      ? "fallback"
      : modelAsync.error
        ? "unavailable"
        : modelAsync.status === "loading" || modelAsync.status === "idle"
          ? "fallback"
          : "fallback";

  const selectedDistrictName =
    districts?.find((district) => district.district_id === selection.districtId)
      ?.district_name ?? selection.districtId;

  const showReviewSection = role !== "viewer";

  return (
    <div className="min-h-screen">
      <AppHeader
        health={
          health ? { dataMode: health.data_mode, dataLabel: health.data_label } : null
        }
        healthState={healthState}
        modelMode={modelMode}
        role={role}
        onRoleChange={handleRoleChange}
        onRetryHealth={() => void checkHealth()}
      />

      <DataModeBanner
        dataMode={summary?.data_mode ?? health?.data_mode}
        dataLabel={summary?.data_label ?? health?.data_label}
        disclaimer={summary?.disclaimer ?? health?.disclaimer}
      />

      <main className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 px-4 py-5 sm:px-6">
        {offline ? (
          <div
            role="alert"
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3"
          >
            <div className="flex items-center gap-2 text-sm text-red-800">
              <WifiOff className="h-4 w-4" aria-hidden="true" />
              <span>
                <span className="font-semibold">Backend unavailable.</span> The API at{" "}
                <code className="font-mono">{API_BASE_URL}</code> is not responding. Start it
                with the Phase 5 startup command and retry.
              </span>
            </div>
            <button
              type="button"
              onClick={() => void checkHealth()}
              className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100"
            >
              Retry connection
            </button>
          </div>
        ) : null}

        {metaError && !summary ? (
          <ErrorState
            title="Initial data could not be loaded"
            message={metaError.message}
            code={metaError instanceof Error ? "meta" : undefined}
            onRetry={() => void loadMeta()}
          />
        ) : null}

        <ForecastControls
          districts={districts}
          summary={summary}
          selection={selection}
          scenario={scenario}
          loading={forecastLoading}
          onSelectionChange={(patch) => setSelection((previous) => ({ ...previous, ...patch }))}
          onScenarioChange={(next) => setScenario(next)}
          onRun={() => {
            if (debounceRef.current) clearTimeout(debounceRef.current);
            runForecast();
          }}
        />

        <DemoStrip
          onLoadDemo={loadDemoScenario}
          disabled={metaLoading || Boolean(metaError)}
        />

        <div className="grid gap-5 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <ForecastHero
              forecast={forecastAsync.data}
              loading={forecastLoading}
              error={forecastAsync.error}
              onRetry={() => runForecast()}
            />
          </div>
          <div className="lg:col-span-2">
            <RiskGuidance
              risk={forecastAsync.data?.risk ?? null}
              loading={forecastLoading}
            />
          </div>
        </div>

        <div className="grid gap-5 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <SourceComparison forecast={forecastAsync.data} />
          </div>
          <div className="lg:col-span-2">
            <DynamicWeights forecast={forecastAsync.data} />
          </div>
        </div>

        <ForecastExplanation
          explain={explainAsync.data}
          loading={explainAsync.status === "loading"}
          error={explainAsync.error}
          onRetry={() => runForecast()}
        />

        <section
          aria-label="District map"
          className="rounded-lg border border-slate-200 bg-white shadow-panel print:hidden"
        >
          <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3 sm:px-5">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-navy-50 text-teal-700">
                <CloudRain className="h-4 w-4" aria-hidden="true" />
              </span>
              <div>
                <h2 className="text-sm font-semibold tracking-tight text-navy-800">
                  District Overview Map
                </h2>
                <p className="text-xs text-slate-500">
                  Coordinates from GET /districts — click a marker to select it
                </p>
              </div>
            </div>
          </header>
          <div className="px-4 py-4 sm:px-5">
            {districts && districts.length > 0 ? (
              <DistrictMap
                districts={districts}
                selectedDistrictId={selection.districtId || null}
                selectedRiskLabel={
                  forecastAsync.data && !forecastLoading ? forecastAsync.data.risk.risk_level : null
                }
                onSelectDistrict={(districtId) =>
                  setSelection((previous) => ({ ...previous, districtId }))
                }
              />
            ) : metaLoading ? (
              <p className="text-sm text-slate-500">Loading districts…</p>
            ) : (
              <ErrorState
                title="Districts could not be loaded"
                message="GET /districts did not return district coordinates."
                onRetry={() => void loadMeta()}
              />
            )}
          </div>
        </section>

        <ValidationPanel
          districtId={selection.districtId}
          leadHours={selection.lead}
          summary={summary}
        />

        <div className="grid gap-5 lg:grid-cols-2 print:hidden">
          <ModelStatusPanel
            status={modelAsync.data}
            report={reportAsync.data}
            statusLoading={modelAsync.status === "loading"}
            reportLoading={reportAsync.status === "loading"}
            statusError={modelAsync.error}
            reportError={reportAsync.error}
            selectedLead={selection.lead}
            canTrain={role === "administrator"}
            onRefresh={refreshModel}
          />
          <SourceFailurePanel
            districtId={selection.districtId}
            date={selection.date}
            lead={selection.lead}
          />
        </div>

        {showReviewSection ? (
          <div className="rounded-lg border border-slate-200 bg-white shadow-panel print:hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5">
              <div>
                <h2 className="text-sm font-semibold tracking-tight text-navy-800">
                  Expert Review
                </h2>
                <p className="text-xs text-slate-500">
                  Override the system risk decision for the current forecast point (reason mandatory)
                </p>
              </div>
              <button
                type="button"
                disabled={!forecastAsync.data || Boolean(overrideOpen)}
                onClick={() => setOverrideOpen(true)}
                className="inline-flex items-center rounded-md bg-navy-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-navy-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Record Expert Override
              </button>
            </div>
            <div className="px-4 py-4 sm:px-5">
              <AuditTimeline
                entries={auditAsync.data?.entries ?? null}
                loading={auditAsync.status === "loading"}
                error={auditAsync.error}
                onRefresh={() => void auditAsync.exec(() => api.auditLogs(50))}
              />
            </div>
          </div>
        ) : null}

        <div className="print:hidden">
          <SystemDetails
            health={health}
            summary={summary}
            modelStatus={modelAsync.data}
            forecast={forecastAsync.data}
            selection={selection}
            scenario={scenario}
          />
        </div>
      </main>

      <OverrideModal
        open={overrideOpen}
        selection={{
          districtId: selection.districtId,
          districtName: selectedDistrictName,
          date: selection.date,
          lead: selection.lead,
        }}
        systemRisk={forecastAsync.data?.risk.risk_level ?? null}
        submitting={overrideSubmitting}
        error={overrideError}
        onSubmit={handleOverrideSubmit}
        onClose={() => setOverrideOpen(false)}
      />

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center justify-between gap-2 px-4 py-3 text-[11px] text-slate-500 sm:px-6">
          <span>{FOOTER_LINE}</span>
          <span className="font-mono">
            backend: {API_BASE_URL} · SIH26081 prototype v0.5.0
          </span>
        </div>
      </footer>
    </div>
  );
}