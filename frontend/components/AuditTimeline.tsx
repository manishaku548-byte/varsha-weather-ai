"use client";

import { ArrowRight, History, RefreshCw } from "lucide-react";
import Badge from "./Badge";
import EmptyState from "./EmptyState";
import ErrorState from "./ErrorState";
import LoadingState from "./LoadingState";
import SectionCard from "./SectionCard";
import { REVIEW_NOTE, RISK_META } from "@/lib/constants";
import { fmtDate, fmtDateTime, fmtMm } from "@/lib/formatters";
import type { AuditLogEntry } from "@/types/api";

interface AuditTimelineProps {
  entries: AuditLogEntry[] | null;
  loading: boolean;
  error: Error | null;
  onRefresh: () => void;
}

function OverrideEntry({ entry }: { entry: AuditLogEntry }) {
  const originalMeta = RISK_META[entry.original_risk_level ?? ""];
  const overrideMeta = RISK_META[entry.overridden_risk_level ?? ""];
  return (
    <li className="relative border-l-2 border-teal-200 pl-4 pb-4 last:pb-0">
      <span className="absolute -left-[7px] top-1 h-3 w-3 rounded-full border-2 border-teal-600 bg-white" aria-hidden="true" />
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span className={`font-semibold ${originalMeta?.text ?? "text-slate-700"}`}>
          {entry.original_risk_level ?? "N/A"}
        </span>
        <ArrowRight className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
        <span className={`font-semibold ${overrideMeta?.text ?? "text-slate-700"}`}>
          {entry.overridden_risk_level ?? "N/A"}
        </span>
        <Badge tone="navy">
          {entry.district_name ?? entry.district_id ?? "—"} ·{" "}
          {entry.valid_date ? fmtDate(entry.valid_date) : "—"} · {entry.lead_hours ?? "—"}h
        </Badge>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-slate-600">{entry.reason}</p>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
        <span>
          Reviewer: <span className="font-medium text-navy-800">{entry.actor}</span> ({entry.role})
        </span>
        {entry.original_forecast_mm !== null ? (
          <span>Original rainfall: {fmtMm(entry.original_forecast_mm)}</span>
        ) : null}
        <span>{fmtDateTime(entry.created_at)}</span>
      </div>
    </li>
  );
}

function SystemEntry({ entry }: { entry: AuditLogEntry }) {
  return (
    <li className="relative border-l-2 border-slate-200 pl-4 pb-4 last:pb-0">
      <span className="absolute -left-[7px] top-1 h-3 w-3 rounded-full border-2 border-slate-400 bg-white" aria-hidden="true" />
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold text-slate-700">{entry.action ?? "system event"}</span>
        <Badge tone="neutral">system</Badge>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
        <span>
          Actor: <span className="font-medium text-navy-800">{entry.actor}</span> ({entry.role})
        </span>
        <span>{fmtDateTime(entry.created_at)}</span>
      </div>
    </li>
  );
}

export default function AuditTimeline({
  entries,
  loading,
  error,
  onRefresh,
}: AuditTimelineProps) {
  return (
    <SectionCard
      title="Expert Review & Audit Timeline"
      subtitle={REVIEW_NOTE}
      icon={<History className="h-4 w-4" aria-hidden="true" />}
      actions={
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Refresh
        </button>
      }
    >
      {loading ? (
        <LoadingState lines={3} label="Loading the local review timeline…" />
      ) : error ? (
        <ErrorState
          title="Audit timeline unavailable"
          message={error.message}
          onRetry={onRefresh}
        />
      ) : !entries || entries.length === 0 ? (
        <EmptyState
          title="No overrides recorded yet"
          message="Overrides submitted in the Expert Review dialog appear here with the original system decision, reviewer and mandatory reason."
        />
      ) : (
        <ol className="space-y-4" aria-label="Audit timeline entries">
          {entries.map((entry) =>
            entry.kind === "override" ? (
              <OverrideEntry key={`override-${entry.id}`} entry={entry} />
            ) : (
              <SystemEntry key={`system-${entry.id}`} entry={entry} />
            ),
          )}
        </ol>
      )}
    </SectionCard>
  );
}