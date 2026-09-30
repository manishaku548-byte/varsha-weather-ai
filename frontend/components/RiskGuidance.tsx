"use client";

import type { ReactNode } from "react";
import {
  AlertTriangle,
  CalendarRange,
  CheckCircle2,
  ClipboardList,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import Badge from "./Badge";
import EmptyState from "./EmptyState";
import { RISK_META } from "@/lib/constants";
import { fmtConfidence, fmtDate, fmtMm } from "@/lib/formatters";
import type { RiskInfo } from "@/types/api";

const RISK_ICONS: Record<string, ReactNode> = {
  Low: <ShieldCheck className="h-5 w-5" aria-hidden="true" />,
  Moderate: <ShieldAlert className="h-5 w-5" aria-hidden="true" />,
  High: <TriangleAlert className="h-5 w-5" aria-hidden="true" />,
  Critical: <AlertTriangle className="h-5 w-5" aria-hidden="true" />,
};

interface RiskGuidanceProps {
  risk: RiskInfo | null;
  loading?: boolean;
}

export default function RiskGuidance({ risk, loading }: RiskGuidanceProps) {
  if (loading) {
    return (
      <section aria-label="Risk guidance" className="rounded-lg border border-slate-200 bg-white p-5 shadow-panel">
        <p className="text-sm text-slate-500">Loading risk guidance…</p>
      </section>
    );
  }

  if (!risk) {
    return (
      <section aria-label="Risk guidance" className="rounded-lg border border-slate-200 bg-white p-5 shadow-panel">
        <EmptyState
          title="Risk guidance unavailable"
          message="Run a forecast first; the risk level comes from GET /forecast."
        />
      </section>
    );
  }

  const meta = RISK_META[risk.risk_level] ?? RISK_META.Low;

  return (
    <section aria-label="Risk guidance" className="rounded-lg border border-slate-200 bg-white shadow-panel">
      <header className="flex items-center gap-2.5 border-b border-slate-100 px-4 py-3 sm:px-5">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-navy-50 text-teal-700">
          <ShieldAlert className="h-4 w-4" aria-hidden="true" />
        </span>
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-navy-800">Risk Guidance</h2>
          <p className="text-xs text-slate-500">{risk.event_type}</p>
        </div>
      </header>

      <div className="space-y-4 px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 ${meta.badge}`}>
            {RISK_ICONS[risk.risk_level] ?? null}
            <span className="text-lg font-bold">{risk.risk_level}</span>
          </div>
          {risk.escalated ? (
            <Badge tone="amber">Escalated by Heavy-Rain Risk regime</Badge>
          ) : null}
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <div>
            <dt className="text-slate-500">Predicted rainfall</dt>
            <dd className="font-semibold text-navy-800">{fmtMm(risk.predicted_rainfall_mm)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Confidence</dt>
            <dd className="font-semibold text-navy-800">
              {fmtConfidence(risk.confidence_score)} · {risk.confidence_label}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Regime</dt>
            <dd className="font-semibold text-navy-800">{risk.regime}</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1 text-slate-500">
              <CalendarRange className="h-3 w-3" aria-hidden="true" /> Valid period
            </dt>
            <dd className="font-semibold text-navy-800">
              {fmtDate(risk.validity_start)} → {fmtDate(risk.validity_end)}
            </dd>
          </div>
        </dl>

        <div>
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-slate-600">
            <ClipboardList className="h-3.5 w-3.5" aria-hidden="true" />
            Reasons (from backend)
          </h3>
          <ul className="mt-1.5 space-y-1">
            {risk.reasons.map((reason, index) => (
              <li key={index} className="flex gap-1.5 text-xs text-slate-600">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-teal-600" aria-hidden="true" />
                {reason}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-slate-600">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
            Non-binding preparedness actions
          </h3>
          <ul className="mt-1.5 space-y-1">
            {risk.preparedness_actions.map((action, index) => (
              <li key={index} className="flex gap-1.5 text-xs text-slate-600">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-navy-400" aria-hidden="true" />
                {action}
              </li>
            ))}
          </ul>
        </div>

        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-800">
          ⚠ {risk.disclaimer}
        </p>
      </div>
    </section>
  );
}