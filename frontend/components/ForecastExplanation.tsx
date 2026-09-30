"use client";

import { Lightbulb, RefreshCw } from "lucide-react";
import Badge from "./Badge";
import EmptyState from "./EmptyState";
import ErrorState from "./ErrorState";
import LoadingState from "./LoadingState";
import SectionCard from "./SectionCard";
import { FALLBACK_LABEL, ML_SOURCE_LABEL, RISK_META } from "@/lib/constants";
import { fmtConfidence, fmtFractionPct, fmtMm, fmtWeight } from "@/lib/formatters";
import type { ForecastExplainResponse } from "@/types/api";

interface ForecastExplanationProps {
  explain: ForecastExplainResponse | null;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
}

export default function ForecastExplanation({
  explain,
  loading,
  error,
  onRetry,
}: ForecastExplanationProps) {
  return (
    <SectionCard
      title="Why this forecast?"
      subtitle="Backend-generated explanation from GET /forecast/explain"
      icon={<Lightbulb className="h-4 w-4" aria-hidden="true" />}
      actions={
        error ? (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Retry
          </button>
        ) : undefined
      }
    >
      {loading ? (
        <LoadingState lines={5} label="Loading the backend explanation…" />
      ) : error ? (
        <ErrorState
          title="Explanation unavailable"
          message={error.message}
          hint="The dashboard never fabricates explanations — this text comes from GET /forecast/explain only."
          onRetry={onRetry}
        />
      ) : !explain ? (
        <EmptyState
          title="No explanation yet"
          message="Run a forecast first and the backend explanation will appear here."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <blockquote className="border-l-4 border-teal-600 pl-3 text-sm font-medium leading-relaxed text-navy-900">
              {explain.headline}
            </blockquote>

            <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {explain.why_this_forecast_title}
            </h3>
            <ul className="mt-2 space-y-1.5">
              {explain.why_this_forecast.map((bullet, index) => (
                <li key={index} className="flex gap-2 text-xs leading-relaxed text-slate-600">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-600" aria-hidden="true" />
                  {bullet}
                </li>
              ))}
            </ul>

            <div className="mt-4 rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2 text-xs text-slate-600">
              <span className="font-semibold text-navy-800">Source health:</span>{" "}
              {explain.source_health_note}
            </div>
            <div className="mt-2 rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2 text-xs text-slate-600">
              <span className="font-semibold text-navy-800">Fallback:</span>{" "}
              <Badge
                tone={explain.fallback_mode === "normal" ? "emerald" : explain.fallback_mode === "degraded" ? "amber" : "red"}
              >
                {FALLBACK_LABEL[explain.fallback_mode] ?? explain.fallback_mode}
              </Badge>{" "}
              {explain.fallback_note}
            </div>

            {explain.ml_model?.source_label ? (
              <div className="mt-2 rounded-md border border-teal-200 bg-teal-50/60 px-3 py-2 text-xs text-teal-900">
                <span className="font-semibold">AI source:</span>{" "}
                {ML_SOURCE_LABEL[String(explain.ml_model.source_label)]}
                {explain.ml_model.model_version ? ` · ${String(explain.ml_model.model_version)}` : ""}
              </div>
            ) : null}
          </div>

          <div className="lg:col-span-2">
            <div className="rounded-md border border-slate-200 bg-slate-50/60 p-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
                Top weighted source
              </p>
              <p className="mt-1 text-sm font-semibold text-navy-800">
                {explain.top_weighted_source.display_name}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                Weight {fmtWeight(explain.top_weighted_source.weight)} · corrected{" "}
                {fmtMm(explain.top_weighted_source.corrected_forecast_mm)}
              </p>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
                {explain.top_weighted_source.reason}
              </p>
            </div>

            <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-slate-500">Final rainfall</dt>
                <dd className="font-semibold text-navy-800">{fmtMm(explain.final_rainfall_mm)}</dd>
              </div>
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-slate-500">Confidence</dt>
                <dd className="font-semibold text-navy-800">{fmtConfidence(explain.confidence.score)}</dd>
              </div>
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-slate-500">Regime</dt>
                <dd className="font-semibold text-navy-800">{explain.regime.label}</dd>
              </div>
              <div className="rounded-md border border-slate-200 px-2.5 py-2">
                <dt className="text-slate-500">Risk</dt>
                <dd className={`font-semibold ${RISK_META[explain.risk.risk_level]?.text ?? "text-navy-800"}`}>
                  {explain.risk.risk_level}
                </dd>
              </div>
            </dl>

            <p className="mt-3 text-[11px] text-slate-500">
              Regime confidence {fmtFractionPct(explain.regime.confidence)} · rule
              version {explain.regime.rule_version}
            </p>
            <p className="mt-2 text-[11px] leading-relaxed text-amber-800">⚠ {explain.disclaimer}</p>
          </div>
        </div>
      )}
    </SectionCard>
  );
}