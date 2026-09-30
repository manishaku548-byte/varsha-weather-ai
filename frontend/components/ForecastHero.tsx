"use client";

import { useState, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  CalendarRange,
  Check,
  Clock,
  CloudRain,
  Copy,
  ShieldAlert,
  ShieldCheck,
  Waves,
} from "lucide-react";
import Badge from "./Badge";
import ErrorState from "./ErrorState";
import LoadingState from "./LoadingState";
import { FALLBACK_LABEL, ML_SOURCE_LABEL, RISK_META } from "@/lib/constants";
import { fmtConfidence, fmtDate, fmtFractionPct, fmtMm } from "@/lib/formatters";
import type { ForecastResponse } from "@/types/api";

const RISK_ICONS: Record<string, ReactNode> = {
  Low: <ShieldCheck className="h-5 w-5" aria-hidden="true" />,
  Moderate: <ShieldAlert className="h-5 w-5" aria-hidden="true" />,
  High: <AlertTriangle className="h-5 w-5" aria-hidden="true" />,
  Critical: <AlertTriangle className="h-5 w-5" aria-hidden="true" />,
};

function StatTile({
  icon,
  label,
  value,
  sub,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold text-navy-800">{value}</div>
      {sub ? <div className="text-[11px] text-slate-500">{sub}</div> : null}
    </div>
  );
}

interface ForecastHeroProps {
  forecast: ForecastResponse | null;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
}

export default function ForecastHero({
  forecast,
  loading,
  error,
  onRetry,
}: ForecastHeroProps) {
  const [copied, setCopied] = useState(false);

  if (loading) {
    return (
      <section aria-label="VARSHA blended rainfall" className="rounded-lg border border-slate-200 bg-white p-5 shadow-panel">
        <LoadingState lines={5} label="Computing the blended forecast on the backend…" />
      </section>
    );
  }

  if (error) {
    return (
      <section aria-label="VARSHA blended rainfall" className="rounded-lg border border-slate-200 bg-white p-5 shadow-panel">
        <ErrorState
          title="Forecast is unavailable"
          message={error.message}
          onRetry={onRetry}
        />
      </section>
    );
  }

  if (!forecast) {
    return null;
  }

  const risk = forecast.risk;
  const riskMeta = RISK_META[risk.risk_level] ?? RISK_META.Low;
  const regime = forecast.weather_regime;
  const confidence = forecast.confidence;
  const ml = forecast.ml_model ?? {};

  const mlLabel = ml.source_label ? ML_SOURCE_LABEL[String(ml.source_label)] : undefined;

  const copySummary = (): void => {
    const lines = [
      "VARSHA Weather AI - Decision-Support Prototype",
      `District: ${forecast.district.district_name}`,
      `Valid date: ${forecast.valid_date} · ${forecast.lead_hours}h lead`,
      `Final rainfall: ${forecast.blend.final_rainfall_mm.toFixed(1)} mm`,
      `Risk level: ${risk.risk_level}`,
      `Weather regime: ${regime.label}`,
      `Confidence: ${confidence.score} / 100 (${confidence.label} band)`,
      `Fallback mode: ${FALLBACK_LABEL[forecast.fallback_mode] ?? forecast.fallback_mode}`,
      mlLabel ? `AI source: ${mlLabel}` : null,
      ml.model_version ? `Model version: ${String(ml.model_version)}` : null,
      confidence.uncertainty_lower_mm !== null && confidence.uncertainty_upper_mm !== null
        ? `Uncertainty range: ${fmtMm(confidence.uncertainty_lower_mm)} - ${fmtMm(confidence.uncertainty_upper_mm)} mm`
        : null,
      `Sources contributing: ${forecast.blend.available_source_count}/3`,
      "",
      forecast.disclaimer,
      "Synthetic Development Dataset - Development/Testing Only - Not an Official Weather Warning.",
    ].filter((line): line is string => Boolean(line));
    const text = lines.join("\n");

    const fallback = () => {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    };

    navigator.clipboard.writeText(text).catch(fallback);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section aria-label="VARSHA blended rainfall" className="rounded-lg border border-slate-200 bg-white shadow-panel">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-navy-50 text-teal-700">
            <CloudRain className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-navy-800">VARSHA Blended Rainfall</h2>
            <p className="text-xs text-slate-500">
              {forecast.district.district_name} · valid {fmtDate(forecast.valid_date)} · {forecast.lead_hours}h lead
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            tone={forecast.fallback_mode === "normal" ? "emerald" : forecast.fallback_mode === "degraded" ? "amber" : "red"}
            title={forecast.blend.fallback_note}
          >
            {FALLBACK_LABEL[forecast.fallback_mode] ?? forecast.fallback_mode}
          </Badge>
          <button
            type="button"
            onClick={copySummary}
            aria-label="Copy forecast summary"
            title="Copy the backend-returned forecast values plus disclaimer to the clipboard"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 print:hidden"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
            ) : (
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {copied ? "Copied" : "Copy Summary"}
          </button>
        </div>
      </header>

      <div className="grid gap-4 px-4 py-4 sm:grid-cols-5 sm:px-5">
        <div className="sm:col-span-2">
          <div className="flex items-end gap-2">
            <span className="text-5xl font-bold tracking-tight text-navy-900">
              {forecast.blend.final_rainfall_mm.toFixed(1)}
            </span>
            <span className="pb-1.5 text-sm font-medium text-slate-500">mm</span>
          </div>
          <div className="mt-3 space-y-1 text-xs text-slate-500">
            <p className="flex items-center gap-1.5">
              <CalendarRange className="h-3.5 w-3.5" aria-hidden="true" />
              {fmtDate(forecast.validity_start)} → {fmtDate(forecast.validity_end)}
            </p>
            <p className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" aria-hidden="true" />
              Issue {fmtDate(forecast.issue_time)} · valid date {fmtDate(forecast.valid_date)}
            </p>
            <p className="flex items-center gap-1.5">
              <Activity className="h-3.5 w-3.5" aria-hidden="true" />
              Sources contributing: {forecast.blend.available_source_count}/3
            </p>
          </div>

          {mlLabel ? (
            <div className="mt-3 rounded-md border border-teal-200 bg-teal-50/60 px-3 py-2 text-xs text-teal-900">
              <span className="font-semibold">AI source:</span> {mlLabel}
              {ml.model_version ? (
                <span className="text-teal-800"> · {String(ml.model_version)}</span>
              ) : null}
              {ml.model_inference_available === false ? (
                <span className="mt-0.5 block text-teal-800">
                  Model inference unavailable — the disclosed precomputed fallback source is used.
                </span>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="grid grid-cols-2 gap-3 sm:col-span-3">
          <StatTile
            icon={<span className={`h-2.5 w-2.5 rounded-full ${riskMeta.dot}`} aria-hidden="true" />}
            label="Risk level"
            value={
              <span className={`inline-flex items-center gap-1.5 ${riskMeta.text}`}>
                {RISK_ICONS[risk.risk_level] ?? null}
                {risk.risk_level}
                {risk.escalated ? <Badge tone="amber">escalated</Badge> : null}
              </span>
            }
            sub={risk.event_type}
          />
          <StatTile
            icon={<Waves className="h-3.5 w-3.5" aria-hidden="true" />}
            label="Weather regime"
            value={regime.label}
            sub={`Regime confidence ${fmtFractionPct(regime.confidence)}`}
          />
          <StatTile
            icon={<Activity className="h-3.5 w-3.5" aria-hidden="true" />}
            label="Confidence"
            value={fmtConfidence(confidence.score)}
            sub={`${confidence.label} band`}
          />
          <StatTile
            icon={<AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />}
            label="Uncertainty range"
            value={
              confidence.uncertainty_lower_mm !== null &&
              confidence.uncertainty_upper_mm !== null
                ? `${fmtMm(confidence.uncertainty_lower_mm)} – ${fmtMm(confidence.uncertainty_upper_mm)}`
                : "N/A"
            }
            sub={
              confidence.uncertainty_half_width_mm !== null
                ? `Half-width ${fmtMm(confidence.uncertainty_half_width_mm)} · ${confidence.uncertainty_basis}`
                : confidence.uncertainty_basis || undefined
            }
          />
        </div>
      </div>

      <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-2.5 sm:px-5">
        <p className="text-xs leading-relaxed text-slate-600">
          <span className="font-medium text-navy-800">Fallback note:</span> {forecast.blend.fallback_note}
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-amber-800">
          ⚠ {forecast.disclaimer}
        </p>
      </div>
    </section>
  );
}