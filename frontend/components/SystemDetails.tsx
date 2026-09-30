"use client";

import type { ReactNode } from "react";
import { ChevronDown, Server } from "lucide-react";
import { useState } from "react";
import Badge from "./Badge";
import SectionCard from "./SectionCard";
import { SCENARIOS, STATUS_META, type ScenarioId } from "@/lib/constants";
import { fmtCount, fmtDate } from "@/lib/formatters";
import type {
  DataSummaryResponse,
  ForecastResponse,
  HealthResponse,
  ModelStatusResponse,
} from "@/types/api";

interface SystemDetailsProps {
  health: HealthResponse | null;
  summary: DataSummaryResponse | null;
  modelStatus: ModelStatusResponse | null;
  forecast: ForecastResponse | null;
  selection: { districtId: string; date: string; lead: number };
  scenario: ScenarioId;
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5">
      <dt className="shrink-0 text-xs text-slate-500">{label}</dt>
      <dd className="min-w-0 text-right text-xs font-medium text-navy-800">{value}</dd>
    </div>
  );
}

export default function SystemDetails({
  health,
  summary,
  modelStatus,
  forecast,
  selection,
  scenario,
}: SystemDetailsProps) {
  const [open, setOpen] = useState(false);

  return (
    <SectionCard
      title="System Details"
      subtitle="Versions, data mode, model state and current request"
      icon={<Server className="h-4 w-4" aria-hidden="true" />}
      actions={
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
          {open ? "Collapse" : "Expand"}
        </button>
      }
    >
      <dl className="grid gap-x-8 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Service & dataset
          </h3>
          <Row label="Version" value={health?.version ?? "N/A"} />
          <Row label="Phase" value={health?.phase ?? "N/A"} />
          <Row label="Problem statement" value={health?.problem_statement_id ?? "N/A"} />
          <Row label="Data mode" value={health?.data_mode ?? summary?.data_mode ?? "N/A"} />
          <Row
            label="Dataset range"
            value={
              summary?.first_valid_date && summary.last_valid_date
                ? `${fmtDate(summary.first_valid_date)} → ${fmtDate(summary.last_valid_date)}`
                : "N/A"
            }
          />
          <Row
            label="Records (obs / fcst)"
            value={
              summary
                ? `${fmtCount(summary.total_observation_records)} / ${fmtCount(summary.total_forecast_records)}`
                : "N/A"
            }
          />
        </div>

        <div>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Blending & model
          </h3>
          <Row label="Algorithm version" value={forecast?.algorithm_version ?? "N/A"} />
          <Row label="Config version" value={forecast?.config_version ?? "N/A"} />
          <Row
            label="Model inference ready"
            value={modelStatus ? (modelStatus.inference_ready ? "Yes" : "No (fallback)") : "N/A"}
          />
          <Row label="Model version" value={modelStatus?.model_version ?? "N/A"} />
          <Row
            label="Trained leads"
            value={
              modelStatus?.trained_lead_hours?.length
                ? modelStatus.trained_lead_hours.map((lead) => `${lead}h`).join(", ")
                : "None"
            }
          />
          <Row
            label="Fallback status"
            value={modelStatus?.fallback_status?.label ?? "N/A"}
          />
        </div>

        <div>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Current request
          </h3>
          <Row label="District" value={selection.districtId || "—"} />
          <Row label="Valid date" value={selection.date ? fmtDate(selection.date) : "—"} />
          <Row label="Lead time" value={`${selection.lead}h`} />
          <Row
            label="Scenario"
            value={SCENARIOS.find((item) => item.id === scenario)?.label ?? scenario}
          />
        </div>
      </dl>

      {open ? (
        <div className="mt-4 border-t border-slate-100 pt-4">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Source health (GET /data/summary)
          </h3>
          {summary && summary.source_health.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                    <th scope="col" className="py-1.5 pr-3 font-medium">Source</th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">Status</th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">Window (days)</th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">Records</th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">Unavailable</th>
                    <th scope="col" className="py-1.5 font-medium">Note</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.source_health.map((source) => {
                    const meta = STATUS_META[source.status] ?? STATUS_META.Unavailable;
                    return (
                      <tr key={source.source_id} className="border-b border-slate-100">
                        <td className="py-1.5 pr-3 font-medium text-navy-800">{source.source_id}</td>
                        <td className="py-1.5 pr-3">
                          <Badge className={meta.className}>{meta.label}</Badge>
                        </td>
                        <td className="py-1.5 pr-3 font-mono">{source.window_days}</td>
                        <td className="py-1.5 pr-3 font-mono">{source.records_in_window}</td>
                        <td className="py-1.5 pr-3 font-mono">{source.unavailable_ratio.toFixed(3)}</td>
                        <td className="py-1.5">{source.note}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-slate-500">No source health data returned.</p>
          )}
          <p className="mt-4 text-[11px] leading-relaxed text-slate-500">
            {health?.disclaimer ?? summary?.disclaimer ?? ""}
          </p>
        </div>
      ) : null}
    </SectionCard>
  );
}