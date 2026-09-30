"use client";

import { BarChart3, DatabaseZap } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Badge from "./Badge";
import EmptyState from "./EmptyState";
import SectionCard from "./SectionCard";
import { ML_SOURCE_LABEL, SOURCE_DISPLAY, SOURCE_ORDER, STATUS_META } from "@/lib/constants";
import { fmtMm, fmtWeight } from "@/lib/formatters";
import type { ForecastResponse } from "@/types/api";

interface SourceComparisonProps {
  forecast: ForecastResponse | null;
}

export default function SourceComparison({ forecast }: SourceComparisonProps) {
  if (!forecast) return null;

  const healthById = new Map(forecast.source_health.map((h) => [h.source_id, h]));
  const contributionById = new Map(
    forecast.blend.contributions.map((c) => [c.source_id, c]),
  );

  const chartData = SOURCE_ORDER.map((sourceId) => {
    const source = forecast.sources.find((s) => s.source_id === sourceId);
    const meta = SOURCE_DISPLAY[sourceId];
    return {
      name: meta?.short ?? sourceId,
      raw: source?.raw_forecast_mm ?? null,
      corrected: source?.corrected_forecast_mm ?? null,
    };
  });

  const summaryRows = SOURCE_ORDER.map((sourceId) => {
    const source = forecast.sources.find((s) => s.source_id === sourceId);
    if (!source) return null;
    const health = healthById.get(sourceId);
    const healthMeta = STATUS_META[health?.status ?? source.status] ?? STATUS_META.Unavailable;
    const contribution = contributionById.get(sourceId);
    const isAi = sourceId === "ai_local_v1";
    const mlLabel = isAi && source.source_label ? ML_SOURCE_LABEL[source.source_label] : undefined;
    return { source, healthMeta, contribution, mlLabel };
  }).filter((row): row is NonNullable<typeof row> => row !== null);

  return (
    <SectionCard
      title="Source Comparison"
      subtitle="Raw vs bias-corrected predictions from GET /forecast"
      icon={<BarChart3 className="h-4 w-4" aria-hidden="true" />}
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-xs">
          <caption className="sr-only">
            NWP, Ensemble and AI Local Correction predictions with their weights,
            health and correction status, all from the backend forecast response.
          </caption>
          <thead>
            <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
              <th scope="col" className="py-2 pr-3 font-medium">Source</th>
              <th scope="col" className="py-2 pr-3 font-medium">Health</th>
              <th scope="col" className="py-2 pr-3 font-medium">Raw (mm)</th>
              <th scope="col" className="py-2 pr-3 font-medium">Corrected (mm)</th>
              <th scope="col" className="py-2 pr-3 font-medium">Weight</th>
              <th scope="col" className="py-2 font-medium">Contribution (mm)</th>
            </tr>
          </thead>
          <tbody>
            {summaryRows.map(({ source, healthMeta, contribution, mlLabel }) => (
              <tr key={source.source_id} className="border-b border-slate-100 align-top">
                <td className="py-2 pr-3">
                  <div className="font-semibold text-navy-800">
                    {SOURCE_DISPLAY[source.source_id]?.full ?? source.display_name}
                  </div>
                  {mlLabel ? (
                    <div
                      className={`mt-0.5 text-[11px] font-medium ${
                        source.model_inference_available
                          ? "text-emerald-700"
                          : "text-amber-700"
                      }`}
                    >
                      {mlLabel}
                      {!source.model_inference_available && source.model_inference_reason
                        ? ` — ${source.model_inference_reason}`
                        : ""}
                    </div>
                  ) : null}
                  {!source.available ? (
                    <div className="mt-0.5 text-[11px] text-red-600">
                      {source.unavailable_reason ?? "Source not contributing"}
                    </div>
                  ) : null}
                </td>
                <td className="py-2 pr-3">
                  <Badge className={healthMeta.className}>{healthMeta.label}</Badge>
                </td>
                <td className="py-2 pr-3 font-mono text-slate-700">
                  {source.raw_forecast_mm !== null ? source.raw_forecast_mm.toFixed(1) : "N/A"}
                </td>
                <td className="py-2 pr-3 font-mono text-slate-700">
                  {source.corrected_forecast_mm !== null
                    ? source.corrected_forecast_mm.toFixed(1)
                    : "N/A"}
                </td>
                <td className="py-2 pr-3 font-mono text-slate-700">
                  {fmtWeight(source.weight)}
                </td>
                <td className="py-2 font-mono text-slate-700">
                  {contribution ? `${fmtMm(contribution.contribution_mm)}` : "N/A"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 h-[220px] w-full" aria-label="Source predictions bar chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#334155" }} />
            <YAxis
              tick={{ fontSize: 11, fill: "#64748b" }}
              label={{ value: "mm", angle: -90, position: "insideLeft", style: { fontSize: 10, fill: "#64748b" } }}
            />
            <Tooltip
              formatter={(value, name) => [
                typeof value === "number" ? `${value.toFixed(1)} mm` : "N/A",
                name === "raw" ? "Raw prediction" : "Bias-corrected",
              ]}
              contentStyle={{ fontSize: 12, borderRadius: 6, borderColor: "#e2e8f0" }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <ReferenceLine
              y={forecast.blend.final_rainfall_mm}
              stroke="#0f2e52"
              strokeDasharray="4 4"
              label={{
                value: `VARSHA blend ${forecast.blend.final_rainfall_mm.toFixed(1)} mm`,
                position: "insideTopRight",
                style: { fontSize: 11, fill: "#0f2e52" },
              }}
            />
            <Bar dataKey="raw" fill="#b3cce8" radius={[3, 3, 0, 0]} />
            <Bar dataKey="corrected" fill="#0d9488" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {forecast.sources.length === 0 ? (
        <EmptyState
          title="No source data returned"
          message="The backend returned no source rows for this point. Check the forecast request."
        />
      ) : null}

      <p className="mt-3 flex items-start gap-1.5 text-[11px] text-slate-500">
        <DatabaseZap className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        Values marked N/A are missing or unavailable in the backend response —
        they are never replaced with a fabricated zero.
      </p>
    </SectionCard>
  );
}