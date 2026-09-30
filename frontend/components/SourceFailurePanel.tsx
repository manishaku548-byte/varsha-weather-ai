"use client";

import { useCallback, useEffect, useState } from "react";
import { FlaskConical, RotateCcw } from "lucide-react";
import Badge from "./Badge";
import EmptyState from "./EmptyState";
import ErrorState from "./ErrorState";
import LoadingState from "./LoadingState";
import SectionCard from "./SectionCard";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useApi";
import { FAILURE_SOURCE_ALIAS, FALLBACK_LABEL, SOURCE_DISPLAY } from "@/lib/constants";
import { fmtConfidence, fmtMm, fmtWeight } from "@/lib/formatters";
import type { SimulateFailureResponse } from "@/types/api";

type FailureAlias = "nwp" | "ensemble" | "ai";

const FAILURE_ACTIONS: { alias: FailureAlias; label: string }[] = [
  { alias: "nwp", label: "Simulate NWP Failure" },
  { alias: "ensemble", label: "Simulate Ensemble Failure" },
  { alias: "ai", label: "Simulate AI Failure" },
];

interface SourceFailurePanelProps {
  districtId: string;
  date: string;
  lead: number;
}

function SummaryCard({
  title,
  summary,
  titleTone,
}: {
  title: string;
  summary: SimulateFailureResponse["normal"];
  titleTone: "emerald" | "amber";
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/60 p-3 text-xs">
      <Badge tone={titleTone}>{title}</Badge>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
        <div>
          <dt className="text-slate-500">Final rainfall</dt>
          <dd className="font-mono font-semibold text-navy-800">{fmtMm(summary.final_rainfall_mm)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Confidence</dt>
          <dd className="font-mono font-semibold text-navy-800">
            {fmtConfidence(summary.confidence_score)} · {summary.confidence_label}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Fallback mode</dt>
          <dd className="font-semibold text-navy-800">{FALLBACK_LABEL[summary.fallback_mode] ?? summary.fallback_mode}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Regime</dt>
          <dd className="font-semibold text-navy-800">{summary.regime}</dd>
        </div>
      </dl>
      <div className="mt-2 space-y-1">
        {Object.entries(summary.weights).map(([sourceId, weight]) => (
          <div key={sourceId} className="flex items-center justify-between">
            <span className="text-slate-500">{SOURCE_DISPLAY[sourceId]?.short ?? sourceId}</span>
            <span className="font-mono">{fmtWeight(weight)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SourceFailurePanel({ districtId, date, lead }: SourceFailurePanelProps) {
  const [confirmAlias, setConfirmAlias] = useState<FailureAlias | null>(null);
  const [lastAttempt, setLastAttempt] = useState<FailureAlias | null>(null);
  const { data, error, status, exec, reset } = useAsync<SimulateFailureResponse>();

  const confirmAction = FAILURE_ACTIONS.find((a) => a.alias === confirmAlias);

  // Clear simulation results + confirm state when the forecast point changes,
  // so a district/date/lead switch never shows stale before/after numbers.
  useEffect(() => {
    reset();
    setConfirmAlias(null);
    setLastAttempt(null);
  }, [districtId, date, lead, reset]);

  const runSimulation = useCallback(
    (alias: FailureAlias) => {
      setConfirmAlias(null);
      setLastAttempt(alias);
      void exec(() =>
        api.simulateSourceFailure({
          district: districtId,
          date,
          lead_hours: lead,
          failed_source: alias,
        }),
      );
    },
    [districtId, date, lead, exec],
  );

  return (
    <SectionCard
      title="Source Failure Simulation"
      subtitle="Resilience test — does the blend degrade gracefully?"
      icon={<FlaskConical className="h-4 w-4" aria-hidden="true" />}
      actions={
        data ? (
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Reset
          </button>
        ) : undefined
      }
    >
      <div className="flex flex-wrap gap-2">
        {FAILURE_ACTIONS.map((action) => (
          <button
            key={action.alias}
            type="button"
            onClick={() => setConfirmAlias(action.alias)}
            disabled={status === "loading"}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-amber-400 hover:bg-amber-50 disabled:opacity-50"
          >
            {action.label}
          </button>
        ))}
      </div>

      {confirmAlias && confirmAction ? (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-label="Confirm source failure simulation"
          className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-4 py-3"
        >
          <p className="text-sm text-amber-900">
            This demonstration temporarily excludes{" "}
            <span className="font-semibold">
              {FAILURE_SOURCE_ALIAS[confirmAlias]} ({SOURCE_DISPLAY[FAILURE_SOURCE_ALIAS[confirmAlias]]?.full})
            </span>{" "}
            from the prototype calculation. Continue?
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => runSimulation(confirmAlias)}
              className="rounded-md bg-amber-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-800"
            >
              Continue
            </button>
            <button
              type="button"
              onClick={() => setConfirmAlias(null)}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {status === "loading" ? (
        <div className="mt-4">
          <LoadingState lines={3} label="Running normal vs degraded comparison…" />
        </div>
      ) : error ? (
        <div className="mt-4">
          <ErrorState
            title="Simulation failed"
            message={error.message}
            onRetry={
              lastAttempt
                ? () => runSimulation(lastAttempt)
                : undefined
            }
          />
        </div>
      ) : data ? (
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <SummaryCard title="Before (Normal)" summary={data.normal} titleTone="emerald" />
            <SummaryCard title={`After (${data.failed_source} failed)`} summary={data.degraded} titleTone="amber" />
          </div>

          <div className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2 text-xs text-slate-600">
            <span className="font-semibold text-navy-800">Changes:</span> rainfall{" "}
            <span className="font-mono">{data.rainfall_change_mm >= 0 ? "+" : ""}{data.rainfall_change_mm.toFixed(2)} mm</span>
            {" · "}confidence{" "}
            <span className="font-mono">{data.confidence_change.normal.toFixed(0)} → {data.confidence_change.degraded.toFixed(0)}</span>
            {" · "}fallback mode{" "}
            <span className="font-mono">
              {FALLBACK_LABEL[data.fallback_mode_change.normal]} → {FALLBACK_LABEL[data.fallback_mode_change.degraded]}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-xs">
              <caption className="sr-only">Source weight changes between the normal and degraded run.</caption>
              <thead>
                <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
                  <th scope="col" className="py-1.5 pr-3 font-medium">Source</th>
                  <th scope="col" className="py-1.5 pr-3 font-medium">Weight before</th>
                  <th scope="col" className="py-1.5 pr-3 font-medium">Weight after</th>
                  <th scope="col" className="py-1.5 pr-3 font-medium">Delta</th>
                  <th scope="col" className="py-1.5 font-medium">Trust before → after</th>
                </tr>
              </thead>
              <tbody>
                {data.weight_changes.map((change) => (
                  <tr key={change.source_id} className="border-b border-slate-100">
                    <td className="py-1.5 pr-3 font-medium text-navy-800">{change.display_name}</td>
                    <td className="py-1.5 pr-3 font-mono">{fmtWeight(change.weight_before)}</td>
                    <td className="py-1.5 pr-3 font-mono">{fmtWeight(change.weight_after)}</td>
                    <td className="py-1.5 pr-3 font-mono">
                      <span className={change.delta >= 0 ? "text-teal-700" : "text-amber-700"}>
                        {change.delta >= 0 ? "+" : ""}{(change.delta * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-1.5 font-mono">
                      {change.trust_score_before.toFixed(2)} → {change.trust_score_after.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Backend explanation</h3>
            <ul className="mt-1.5 space-y-1">
              {data.explanation.map((line, index) => (
                <li key={index} className="flex gap-1.5 text-xs text-slate-600">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-teal-600" aria-hidden="true" />
                  {line}
                </li>
              ))}
            </ul>
          </div>

          <p className="text-[11px] text-slate-500">
            This simulation never mutates the base dataset or the normal forecast
            calculation — it only runs the same engine twice with one source excluded.
          </p>
        </div>
      ) : (
        <div className="mt-4">
          <EmptyState
            title="No simulation run yet"
            message="Pick a source above to compare the normal blend against a degraded blend on the current selection."
          />
        </div>
      )}
    </SectionCard>
  );
}