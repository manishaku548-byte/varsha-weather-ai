"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ClipboardCheck, Download, RefreshCw } from "lucide-react";
import Badge from "./Badge";
import EmptyState from "./EmptyState";
import ErrorState from "./ErrorState";
import LoadingState from "./LoadingState";
import SectionCard from "./SectionCard";
import { useAsync } from "@/lib/useApi";
import { api } from "@/lib/api";
import { RESULT_METHODS } from "@/lib/constants";
import { addDays, clampDate, fmtMetric } from "@/lib/formatters";
import type { BacktestResponse, DataSummaryResponse } from "@/types/api";

interface ValidationPanelProps {
  districtId: string;
  leadHours: number;
  summary: DataSummaryResponse | null;
}

const inputClass =
  "rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-navy-800 shadow-sm focus:border-teal-600";

export default function ValidationPanel({
  districtId,
  leadHours,
  summary,
}: ValidationPanelProps) {
  const fallbackStart = useMemo(
    () => (summary?.first_valid_date ? addDays(summary.first_valid_date, 14) : ""),
    [summary?.first_valid_date],
  );
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const { data, error, status, exec } = useAsync<BacktestResponse>();

  useEffect(() => {
    if (summary?.first_valid_date && summary.last_valid_date && !startDate) {
      setStartDate(clampDate(fallbackStart, summary.first_valid_date, summary.last_valid_date));
      setEndDate(summary.last_valid_date);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary]);

  const runBacktest = useCallback(() => {
    if (!startDate || !endDate || !districtId) return;
    void exec(() =>
      api.backtest({
        district: districtId,
        lead_hours: leadHours,
        start_date: startDate,
        end_date: endDate,
      }),
    );
  }, [districtId, leadHours, startDate, endDate, exec]);

  const downloadCsv = useCallback(async () => {
    try {
      await api.downloadBacktestCsv({
        district: districtId,
        lead_hours: leadHours,
        start_date: startDate,
        end_date: endDate,
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    }
  }, [districtId, leadHours, startDate, endDate]);

  const bestByMae = data?.comparison_summary.best_method_by_metric?.mae ?? null;

  return (
    <SectionCard
      title="Historical Validation"
      subtitle="Chronological walk-forward backtest — synthetic development evaluation"
      icon={<ClipboardCheck className="h-4 w-4" aria-hidden="true" />}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="date"
            aria-label="Validation start date"
            value={startDate}
            min={summary?.first_valid_date ?? undefined}
            max={endDate || undefined}
            onChange={(e) => setStartDate(e.target.value)}
            className={inputClass}
          />
          <span className="text-xs text-slate-400">→</span>
          <input
            type="date"
            aria-label="Validation end date"
            value={endDate}
            min={startDate || undefined}
            max={summary?.last_valid_date ?? undefined}
            onChange={(e) => setEndDate(e.target.value)}
            className={inputClass}
          />
          <button
            type="button"
            onClick={runBacktest}
            disabled={!startDate || !endDate || status === "loading"}
            className="inline-flex items-center gap-1.5 rounded-md bg-teal-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-teal-800 disabled:opacity-50"
          >
            {status === "loading" ? "Running…" : "Run Backtest"}
          </button>
          <button
            type="button"
            onClick={downloadCsv}
            disabled={!data || status === "loading"}
            title="Download the backend-generated CSV report"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            Download CSV Report
          </button>
        </div>
      }
    >
      {status === "loading" ? (
        <LoadingState lines={6} label="Running the walk-forward backtest…" />
      ) : error ? (
        <ErrorState
          title="Backtest could not run"
          message={error.message}
          onRetry={runBacktest}
        />
      ) : !data ? (
        <EmptyState
          title="No validation run yet"
          message="Pick a date range inside the dataset and press Run Backtest. The backend walks forward day by day using only strictly-prior records."
        />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge tone="navy">{data.request.district_id} · {data.request.lead_hours}h</Badge>
            <Badge tone="neutral">
              Evaluated {data.evaluation_summary.evaluated_dates} of {data.evaluation_summary.total_requested_dates} dates
            </Badge>
            {data.evaluation_summary.skipped_dates > 0 ? (
              <Badge tone={data.evaluation_summary.sufficient_sample_warning ? "amber" : "neutral"}>
                Skipped {data.evaluation_summary.skipped_dates}
              </Badge>
            ) : null}
            {data.evaluation_summary.sufficient_sample_warning ? (
              <span className="text-amber-700">{data.evaluation_summary.sufficient_sample_warning}</span>
            ) : null}
          </div>

          {Object.keys(data.evaluation_summary.skipped_reason_counts ?? {}).length > 0 ? (
            <p className="text-[11px] text-slate-500">
              Skip reasons:{" "}
              {Object.entries(data.evaluation_summary.skipped_reason_counts)
                .map(([reason, count]) => `${reason} (${count})`)
                .join(", ")}
            </p>
          ) : null}

          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-xs">
              <caption className="sr-only">
                Five forecasting methods evaluated on the synthetic dataset: MAE,
                RMSE, bias, precision, recall, F1, false-alarm rate, sample and
                event counts.
              </caption>
              <thead>
                <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                  <th scope="col" className="py-2 pr-3 font-medium">Method</th>
                  <th scope="col" className="py-2 pr-3 font-medium">MAE (mm)</th>
                  <th scope="col" className="py-2 pr-3 font-medium">RMSE (mm)</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Bias (mm)</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Precision</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Recall</th>
                  <th scope="col" className="py-2 pr-3 font-medium">F1</th>
                  <th scope="col" className="py-2 pr-3 font-medium">FAR</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Samples</th>
                  <th scope="col" className="py-2 font-medium">Events</th>
                </tr>
              </thead>
              <tbody>
                {RESULT_METHODS.map((method) => {
                  const evaluation = data.methods[method.key as keyof typeof data.methods];
                  const regression = evaluation?.regression_metrics;
                  const event = evaluation?.event_metrics;
                  const isVarshaBest = bestByMae === "varsha_dynamic_blend" && method.key === "varsha_dynamic_blend";
                  return (
                    <tr
                      key={method.key}
                      className={`border-b border-slate-100 ${
                        isVarshaBest ? "bg-teal-50/50" : ""
                      }`}
                    >
                      <td className="py-2 pr-3 font-semibold text-navy-800">
                        {method.label}
                        {isVarshaBest ? (
                          <Badge tone="teal" className="ml-2">lowest MAE*</Badge>
                        ) : null}
                      </td>
                      <td className="py-2 pr-3 font-mono">{fmtMetric(regression?.mae_mm, 2)}</td>
                      <td className="py-2 pr-3 font-mono">{fmtMetric(regression?.rmse_mm, 2)}</td>
                      <td className="py-2 pr-3 font-mono">{fmtMetric(regression?.mean_bias_error_mm, 2)}</td>
                      <td className="py-2 pr-3 font-mono">{fmtMetric(event?.precision, 3)}</td>
                      <td className="py-2 pr-3 font-mono">{fmtMetric(event?.recall, 3)}</td>
                      <td className="py-2 pr-3 font-mono">{fmtMetric(event?.f1_score, 3)}</td>
                      <td className="py-2 pr-3 font-mono">{fmtMetric(event?.false_alarm_rate, 3)}</td>
                      <td className="py-2 pr-3 font-mono">{regression?.sample_count ?? "N/A"}</td>
                      <td className="py-2 font-mono">{event?.event_count ?? "N/A"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {data.comparison_summary.outcome_summary.length > 0 ? (
            <div className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2 text-xs text-slate-600">
              <span className="font-semibold text-navy-800">Backend comparison summary:</span>
              <ul className="mt-1 space-y-1">
                {data.comparison_summary.outcome_summary.map((line, index) => (
                  <li key={index} className="flex gap-1.5">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-teal-600" aria-hidden="true" />
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {bestByMae === "varsha_dynamic_blend" ? (
            <p className="text-[11px] text-slate-500">
              * VARSHA Dynamic Blend is marked only because the backend comparison
              summary reports it as the lowest-MAE method for this run — the
              dashboard never decides winners itself.
            </p>
          ) : null}

          {data.limitations.length > 0 ? (
            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Evaluation notes
              </h3>
              <ul className="mt-1 list-inside list-disc space-y-0.5 text-[11px] text-slate-500">
                {data.limitations.map((limitation, index) => (
                  <li key={index}>{limitation}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-[11px] text-slate-500">
            <span>
              Report files: {data.report_files.csv} · {data.report_files.json}
            </span>
            <button
              type="button"
              onClick={runBacktest}
              className="inline-flex items-center gap-1.5 text-teal-700 hover:underline"
            >
              <RefreshCw className="h-3 w-3" aria-hidden="true" /> Re-run
            </button>
          </div>

          <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-800">
            ⚠ {data.disclaimer} These metrics describe performance on the loaded
            synthetic development dataset only — they are not operational
            accuracy figures.
          </p>
        </div>
      )}
    </SectionCard>
  );
}