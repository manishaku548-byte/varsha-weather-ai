"use client";

import { CalendarClock, Play, SlidersHorizontal } from "lucide-react";
import Badge from "./Badge";
import { LEAD_OPTIONS, SCENARIOS, type ScenarioId } from "@/lib/constants";
import { fmtDate } from "@/lib/formatters";
import type { DataSummaryResponse, District } from "@/types/api";

export interface ForecastSelection {
  districtId: string;
  date: string;
  lead: number;
}

interface ForecastControlsProps {
  districts: District[] | null;
  summary: DataSummaryResponse | null;
  selection: ForecastSelection;
  scenario: ScenarioId;
  loading: boolean;
  onSelectionChange: (patch: Partial<ForecastSelection>) => void;
  onScenarioChange: (scenario: ScenarioId) => void;
  onRun: () => void;
}

const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-navy-800 shadow-sm focus:border-teal-600";

export default function ForecastControls({
  districts,
  summary,
  selection,
  scenario,
  loading,
  onSelectionChange,
  onScenarioChange,
  onRun,
}: ForecastControlsProps) {
  const minDate = summary?.first_valid_date ?? undefined;
  const maxDate = summary?.last_valid_date ?? undefined;
  const canRun = Boolean(
    selection.districtId && selection.date && districts?.length && summary,
  );

  return (
    <section
      aria-label="Forecast controls"
      className="rounded-lg border border-slate-200 bg-white shadow-panel print:hidden"
    >
      <div className="flex flex-wrap items-center gap-4 px-4 py-3.5 sm:px-5">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-navy-50 text-teal-700">
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
        </span>

        <div className="min-w-[160px] flex-1 sm:max-w-[240px]">
          <label htmlFor="district-select" className="mb-1 block text-[11px] font-medium text-slate-500">
            District (from GET /districts)
          </label>
          <select
            id="district-select"
            value={selection.districtId}
            disabled={!districts?.length}
            onChange={(event) => onSelectionChange({ districtId: event.target.value })}
            className={inputClass}
          >
            {!districts?.length ? <option value="">Loading districts…</option> : null}
            {districts?.map((district) => (
              <option key={district.district_id} value={district.district_id}>
                {district.district_name}
              </option>
            ))}
          </select>
        </div>

        <div className="min-w-[160px] flex-1 sm:max-w-[220px]">
          <label htmlFor="valid-date" className="mb-1 block text-[11px] font-medium text-slate-500">
            Valid date (dataset range)
          </label>
          <input
            id="valid-date"
            type="date"
            value={selection.date}
            min={minDate}
            max={maxDate}
            onChange={(event) => {
              if (event.target.value) onSelectionChange({ date: event.target.value });
            }}
            className={inputClass}
          />
        </div>

        <div className="min-w-[130px] flex-1 sm:max-w-[170px]">
          <label htmlFor="lead-select" className="mb-1 block text-[11px] font-medium text-slate-500">
            Lead time
          </label>
          <select
            id="lead-select"
            value={selection.lead}
            onChange={(event) => onSelectionChange({ lead: Number(event.target.value) })}
            className={inputClass}
          >
            {LEAD_OPTIONS.map((lead) => (
              <option key={lead} value={lead}>
                {lead}h forecast
              </option>
            ))}
          </select>
        </div>

        <div className="min-w-[180px] flex-1 sm:max-w-[260px]">
          <label htmlFor="scenario-select" className="mb-1 block text-[11px] font-medium text-slate-500">
            Quick scenario
          </label>
          <select
            id="scenario-select"
            value={scenario}
            onChange={(event) => onScenarioChange(event.target.value as ScenarioId)}
            className={inputClass}
          >
            {SCENARIOS.map((item) => (
              <option key={item.id} value={item.id} title={item.description}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col items-end gap-1">
          <button
            type="button"
            onClick={onRun}
            disabled={!canRun || loading}
            className="inline-flex items-center gap-2 rounded-md bg-teal-700 px-4 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            {loading ? "Running…" : "Run Forecast"}
          </button>
          <span className="hidden text-[11px] text-slate-400 sm:inline">
            Data mode: {summary?.data_mode ?? "…"} · {summary ? fmtDate(selection.date) : "…"}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 px-4 py-2 sm:px-5">
        <CalendarClock className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
        <span className="text-xs text-slate-500">
          Selected valid date: <span className="font-medium text-navy-800">{fmtDate(selection.date)}</span>
          {" · "}
          Lead: <span className="font-medium text-navy-800">{selection.lead}h</span>
          {" · "}
          Available range: {fmtDate(minDate)} → {fmtDate(maxDate)}
        </span>
        {scenario !== "normal" ? (
          <Badge tone="amber">
            Failure scenario active:{" "}
            {SCENARIOS.find((item) => item.id === scenario)?.label ?? scenario}
          </Badge>
        ) : null}
      </div>
    </section>
  );
}