"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

interface ErrorStateProps {
  title?: string;
  message: string;
  code?: string;
  hint?: string;
  onRetry?: () => void;
}

export default function ErrorState({
  title = "This section could not be loaded",
  message,
  code,
  hint,
  onRetry,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50/70 px-4 py-3"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden="true" />
      <div className="min-w-0">
        <p className="text-sm font-semibold text-red-800">{title}</p>
        <p className="mt-0.5 text-sm text-red-700">{message}</p>
        {code ? (
          <p className="mt-1 font-mono text-xs text-slate-500">error code: {code}</p>
        ) : null}
        {hint ? (
          <p className="mt-0.5 text-xs text-slate-500">{hint}</p>
        ) : null}
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-red-300 bg-white px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Retry
          </button>
        ) : null}
      </div>
    </div>
  );
}