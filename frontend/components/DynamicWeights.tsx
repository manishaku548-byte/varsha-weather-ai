"use client";

import { Scale } from "lucide-react";
import SectionCard from "./SectionCard";
import { SOURCE_DISPLAY, SOURCE_ORDER, STATUS_META } from "@/lib/constants";
import { fmtWeight } from "@/lib/formatters";
import type { ForecastResponse } from "@/types/api";

interface DynamicWeightsProps {
  forecast: ForecastResponse | null;
}

export default function DynamicWeights({ forecast }: DynamicWeightsProps) {
  if (!forecast) return null;

  const healthById = new Map(forecast.source_health.map((h) => [h.source_id, h]));

  return (
    <SectionCard
      title="Dynamic Source Weights"
      subtitle="Dynamic Trust Engine output (weights sum to 1.0)"
      icon={<Scale className="h-4 w-4" aria-hidden="true" />}
    >
      <p className="mb-4 text-xs leading-relaxed text-slate-500">
        Weights change according to historical skill, recent performance, data
        quality, forecast agreement, regime and lead time. Every value below is
        the backend&apos;s Dynamic Trust Engine output.
      </p>

      <div className="space-y-4">
        {SOURCE_ORDER.map((sourceId) => {
          const source = forecast.sources.find((s) => s.source_id === sourceId);
          if (!source) return null;
          const meta = SOURCE_DISPLAY[sourceId];
          const health = healthById.get(sourceId);
          const healthMeta = STATUS_META[health?.status ?? source.status] ?? STATUS_META.Unavailable;
          const pct = Math.max(0, Math.min(100, (source.weight ?? 0) * 100));

          return (
            <div key={sourceId}>
              <div className="flex items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-flex h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: meta?.color ?? "#64748b" }}
                    aria-hidden="true"
                  />
                  <span className="font-semibold text-navy-800">
                    {meta?.short ?? sourceId}
                  </span>
                  <span className="hidden text-slate-400 sm:inline">{meta?.full}</span>
                  <span className={`rounded border px-1.5 py-0.5 text-[10px] ${healthMeta.className}`}>
                    {healthMeta.label}
                  </span>
                </div>
                <span className="font-mono font-semibold text-navy-800">
                  {fmtWeight(source.weight)}
                </span>
              </div>
              <div
                className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-slate-100"
                role="img"
                aria-label={`${meta?.short ?? sourceId} weight ${pct.toFixed(1)} percent`}
              >
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${pct}%`, backgroundColor: meta?.color ?? "#64748b" }}
                />
              </div>
              <p
                className="mt-1 text-[11px] leading-relaxed text-slate-500"
                title={source.trust.reason}
              >
                {source.trust.reason}
              </p>
            </div>
          );
        })}
      </div>

      {forecast.blend.unavailable_sources.length > 0 ? (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Not contributing this point: {forecast.blend.unavailable_sources.join(", ")}.
          {" "}{forecast.blend.fallback_note}
        </div>
      ) : null}

      <p className="mt-4 text-[11px] text-slate-400">
        Formula: {forecast.blend.formula}
      </p>
    </SectionCard>
  );
}