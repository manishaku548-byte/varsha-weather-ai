"use client";

import { Database, Info } from "lucide-react";

interface DataModeBannerProps {
  dataMode?: string;
  dataLabel?: string;
  disclaimer?: string;
}

export default function DataModeBanner({
  dataMode,
  dataLabel,
  disclaimer,
}: DataModeBannerProps) {
  const label =
    dataLabel ?? "Synthetic Development Dataset - Not Operational Weather Data";
  const clause =
    disclaimer ??
    "Decision-Support Prototype - Not an Official Weather Warning.";

  return (
    <div
      role="status"
      className="border-b border-amber-200 bg-amber-50/80"
      data-testid="data-mode-banner"
    >
      <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 sm:px-6">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber-900">
          <Database className="h-4 w-4" aria-hidden="true" />
          {label}
          {dataMode ? <span className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[10px]">mode: {dataMode}</span> : null}
        </span>
        <span className="inline-flex items-center gap-1.5 text-xs text-amber-800">
          <Info className="h-3.5 w-3.5" aria-hidden="true" />
          {clause}
        </span>
        <span className="text-xs italic text-amber-700">
          Results shown here are calculated on a synthetic development dataset and
          are not operational weather forecasts.
        </span>
      </div>
    </div>
  );
}