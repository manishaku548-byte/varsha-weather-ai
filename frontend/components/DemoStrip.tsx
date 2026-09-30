"use client";

import { ClipboardList, Wand2 } from "lucide-react";
import { DEMO_SCENARIO } from "@/lib/constants";
import { fmtDate } from "@/lib/formatters";

/**
 * Low visual-weight demo aid: a suggested 3-minute flow and a "Load Demo
 * Scenario" button. The button only selects EXISTING dashboard inputs
 * (district / date / lead / scenario) — it never injects values, bypasses the
 * backend or alters any calculation. The normal debounced forecast run then
 * fetches the scenario values live from the backend API.
 */

const DEMO_STEPS = [
  "Forecast",
  "Why this forecast?",
  "Backtest",
  "Source failure",
  "Expert override",
] as const;

interface DemoStripProps {
  onLoadDemo: () => void;
  disabled?: boolean;
}

export default function DemoStrip({ onLoadDemo, disabled }: DemoStripProps) {
  return (
    <section
      aria-label="Suggested 3-minute demo flow"
      className="rounded-lg border border-teal-200 bg-teal-50/40 shadow-panel print:hidden"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 sm:px-5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-teal-900">
            <ClipboardList className="h-3.5 w-3.5" aria-hidden="true" />
            Suggested 3-minute demo flow
          </span>
          <ol className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-600">
            {DEMO_STEPS.map((step, index) => (
              <li key={step} className="inline-flex items-center gap-1.5">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-teal-700 text-[9px] font-bold text-white">
                  {index + 1}
                </span>
                {step}
                {index < DEMO_STEPS.length - 1 ? (
                  <span aria-hidden="true" className="text-slate-400">
                    →
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="hidden text-[11px] text-slate-500 md:inline">
            Demo point: {DEMO_SCENARIO.districtName} · {fmtDate(DEMO_SCENARIO.date)} ·{" "}
            {DEMO_SCENARIO.lead}h — values are read live from the backend.
          </span>
          <button
            type="button"
            onClick={onLoadDemo}
            disabled={disabled}
            title={`Set ${DEMO_SCENARIO.districtName}, ${DEMO_SCENARIO.date}, ${DEMO_SCENARIO.lead}h and run the normal forecast API call`}
            className="inline-flex items-center gap-1.5 rounded-md border border-teal-300 bg-white px-3 py-1.5 text-xs font-semibold text-teal-800 shadow-sm hover:bg-teal-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Wand2 className="h-3.5 w-3.5" aria-hidden="true" />
            Load Demo Scenario
          </button>
        </div>
      </div>
    </section>
  );
}