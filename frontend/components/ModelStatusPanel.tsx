"use client";

import { useCallback, useState } from "react";
import { Brain, RefreshCw } from "lucide-react";
import Badge from "./Badge";
import EmptyState from "./EmptyState";
import ErrorState from "./ErrorState";
import LoadingState from "./LoadingState";
import SectionCard from "./SectionCard";
import { api } from "@/lib/api";
import { fmtDateTime, fmtMetric } from "@/lib/formatters";
import { LEAD_OPTIONS } from "@/lib/constants";
import type { ModelReportResponse, ModelStatusResponse } from "@/types/api";

function perLeadStatus(lead: number): string {
  return String(lead).padStart(2, "0") + "h";
}

interface ModelStatusPanelProps {
  status: ModelStatusResponse | null;
  report: ModelReportResponse | null;
  statusLoading: boolean;
  reportLoading: boolean;
  statusError: Error | null;
  reportError: Error | null;
  selectedLead: number;
  canTrain: boolean;
  onRefresh: () => void;
}

export default function ModelStatusPanel({
  status,
  report,
  statusLoading,
  reportLoading,
  statusError,
  reportError,
  selectedLead,
  canTrain,
  onRefresh,
}: ModelStatusPanelProps) {
  const [training, setTraining] = useState(false);
  const [trainError, setTrainError] = useState<Error | null>(null);

  const handleTrain = useCallback(async () => {
    setTraining(true);
    setTrainError(null);
    try {
      await api.trainModel(selectedLead, false);
      onRefresh();
    } catch (err) {
      setTrainError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setTraining(false);
    }
  }, [selectedLead, onRefresh]);

  return (
    <SectionCard
      title="Model Status"
      subtitle="Phase 4 local rainfall-correction model (synthetic-development results)"
      icon={<Brain className="h-4 w-4" aria-hidden="true" />}
      actions={
        <button
          type="button"
          onClick={onRefresh}
          disabled={statusLoading || reportLoading}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Refresh
        </button>
      }
    >
      {statusLoading ? (
        <LoadingState lines={4} label="Reading model status…" />
      ) : statusError ? (
        <ErrorState
          title="Model status unavailable"
          message={statusError.message}
          onRetry={onRefresh}
        />
      ) : !status ? (
        <EmptyState title="No model status yet" />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge tone={status.inference_ready ? "emerald" : "amber"}>
              {status.inference_ready ? "Inference ready" : "Inference not ready"}
            </Badge>
            <Badge tone={status.fallback_status.active ? "amber" : "teal"}>
              {status.fallback_status.label}
            </Badge>
            {status.trained_lead_hours.length > 0 ? (
              <Badge tone="navy">Trained: {status.trained_lead_hours.map(perLeadStatus).join(", ")}</Badge>
            ) : (
              <Badge tone="neutral">No artifacts trained yet</Badge>
            )}
          </div>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-4">
            <div>
              <dt className="text-slate-500">Model version</dt>
              <dd className="font-mono font-medium text-navy-800">{status.model_version ?? "N/A"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Last training</dt>
              <dd className="font-medium text-navy-800">{fmtDateTime(status.last_training_time)}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-slate-500">Models directory</dt>
              <dd className="truncate font-mono text-navy-800" title={status.models_dir}>{status.models_dir}</dd>
            </div>
          </dl>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-xs">
              <caption className="sr-only">Per-lead model artifact state.</caption>
              <thead>
                <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                  <th scope="col" className="py-2 pr-3 font-medium">Lead</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Artifact</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Selected model</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Held-out test MAE (mm)</th>
                  <th scope="col" className="py-2 font-medium">Inference</th>
                </tr>
              </thead>
              <tbody>
                {LEAD_OPTIONS.map((lead) => {
                  const row = status.per_lead?.[String(lead)];
                  return (
                    <tr key={lead} className="border-b border-slate-100">
                      <td className="py-2 pr-3 font-semibold text-navy-800">{perLeadStatus(lead)}</td>
                      <td className="py-2 pr-3">{row?.artifact_exists ? "Present" : "Missing"}</td>
                      <td className="py-2 pr-3 font-mono">{row?.selected_model ?? "—"}</td>
                      <td className="py-2 pr-3 font-mono">
                        {row?.held_out_test_mae_mm !== null && row?.held_out_test_mae_mm !== undefined
                          ? fmtMetric(row.held_out_test_mae_mm, 3)
                          : "—"}
                      </td>
                      <td className="py-2">
                        <Badge tone={row?.inference_ready ? "emerald" : "neutral"}>
                          {row?.inference_ready ? "Ready" : "Fallback"}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2 text-xs text-slate-600">
            <span className="font-semibold text-navy-800">Fallback status:</span>{" "}
            {status.fallback_status.reason}
            <p className="mt-1 text-[11px] text-slate-500">{status.note}</p>
          </div>

          {canTrain ? (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleTrain}
                disabled={training}
                className="inline-flex items-center gap-1.5 rounded-md bg-navy-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-navy-700 disabled:opacity-50"
              >
                {training ? "Training…" : `Train model (${selectedLead}h)`}
              </button>
              {trainError ? (
                <span className="text-xs text-red-600">{trainError.message}</span>
              ) : (
                <span className="text-[11px] text-slate-500">
                  Admin-only demo action → POST /model/train (never runs at startup).
                </span>
              )}
            </div>
          ) : null}

          {reportLoading ? (
            <LoadingState lines={3} label="Reading the saved model report…" />
          ) : reportError ? (
            <ErrorState
              title="Model report unavailable"
              message={reportError.message}
              hint="Train the model first via POST /model/train."
            />
          ) : report ? (
            <div className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2.5 text-xs">
              <p className="font-semibold text-navy-800">
                Latest report ({report.lead_hours}h) — {report.status}
              </p>
              {report.selected_model ? (
                <p className="mt-1 text-slate-600">
                  Selected model: <span className="font-mono font-medium">{report.selected_model}</span>
                  {" · "}Validation-MAE rationale: {report.selection_rationale}
                </p>
              ) : null}
              {report.held_out_test_metrics ? (
                <p className="mt-1 text-slate-600">
                  Held-out test: MAE {fmtMetric(report.held_out_test_metrics.mae_mm, 3)} mm · RMSE{" "}
                  {fmtMetric(report.held_out_test_metrics.rmse_mm, 3)} mm · bias{" "}
                  {fmtMetric(report.held_out_test_metrics.mean_bias_error_mm, 3)} mm · n=
                  {report.held_out_test_metrics.sample_count ?? "—"}
                </p>
              ) : null}
              {report.honesty?.summary_sentences?.length ? (
                <ul className="mt-1 space-y-0.5 text-slate-500">
                  {report.honesty.summary_sentences.map((sentence, index) => (
                    <li key={index}>· {sentence}</li>
                  ))}
                </ul>
              ) : null}
              {report.honesty?.ml_worse_than_baseline ? (
                <p className="mt-1 font-medium text-amber-700">
                  The backend reports this lead&apos;s model is worse than a baseline —
                  the fallback source remains active and this is disclosed honestly.
                </p>
              ) : null}
              <p className="mt-1.5 text-[11px] text-slate-500">
                {report.disclaimer}
              </p>
            </div>
          ) : null}
        </div>
      )}
    </SectionCard>
  );
}