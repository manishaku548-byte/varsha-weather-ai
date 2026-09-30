"use client";

import { useEffect, useRef, useState } from "react";
import { ClipboardSignature, X } from "lucide-react";
import { RISK_META } from "@/lib/constants";
import { fmtDate } from "@/lib/formatters";
import type { RiskLevel } from "@/types/api";

export interface OverrideSelection {
  districtId: string;
  districtName: string;
  date: string;
  lead: number;
}

interface OverrideModalProps {
  open: boolean;
  selection: OverrideSelection;
  systemRisk: string | null;
  submitting: boolean;
  error: Error | null;
  onSubmit: (payload: {
    district: string;
    date: string;
    lead_hours: number;
    selected_risk_level: RiskLevel;
    reason: string;
    reviewer_name: string | null;
    role: "forecaster" | "administrator";
  }) => void;
  onClose: () => void;
}

const RISK_LEVELS: RiskLevel[] = ["Low", "Moderate", "High", "Critical"];

export default function OverrideModal({
  open,
  selection,
  systemRisk,
  submitting,
  error,
  onSubmit,
  onClose,
}: OverrideModalProps) {
  const [selectedRisk, setSelectedRisk] = useState<RiskLevel>("Moderate");
  const [reason, setReason] = useState("");
  const [reviewerName, setReviewerName] = useState("");
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setSelectedRisk("Moderate");
      setReason("");
      setReviewerName("");
      setTimeout(() => reasonRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const dialogEl = dialogRef.current;
      if (!dialogEl) return;
      const focusables = dialogEl.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const canSubmit = reason.trim().length > 0 && !submitting;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-900/40 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        ref={dialogRef}
        aria-modal="true"
        aria-labelledby="override-title"
        className="w-full max-w-lg rounded-lg border border-slate-200 bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-navy-50 text-teal-700">
              <ClipboardSignature className="h-4 w-4" aria-hidden="true" />
            </span>
            <div>
              <h2 id="override-title" className="text-sm font-semibold text-navy-800">
                Expert Review — Record Override
              </h2>
              <p className="text-xs text-slate-500">
                Prototype local review log — not an official authorization record.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close override dialog"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        <div className="space-y-3 px-4 py-4">
          <div className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2 text-xs text-slate-600">
            <span className="font-semibold text-navy-800">Forecast point:</span>{" "}
            {selection.districtName} · {fmtDate(selection.date)} · {selection.lead}h lead
            {systemRisk ? (
              <>
                {" · "}System risk:{" "}
                <span className={`font-semibold ${RISK_META[systemRisk]?.text ?? ""}`}>
                  {systemRisk}
                </span>
              </>
            ) : null}
          </div>

          <div>
            <label htmlFor="override-risk" className="mb-1 block text-xs font-medium text-slate-600">
              Selected risk level (override decision)
            </label>
            <div className="flex flex-wrap gap-2">
              {RISK_LEVELS.map((level) => (
                <button
                  key={level}
                  type="button"
                  onClick={() => setSelectedRisk(level)}
                  aria-pressed={selectedRisk === level}
                  className={`rounded-md border px-3 py-1.5 text-xs font-medium ${
                    selectedRisk === level
                      ? RISK_META[level].badge + " ring-2 ring-teal-500/40"
                      : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
            {selectedRisk === systemRisk ? (
              <p className="mt-1 text-[11px] text-slate-500">
                Same as the system decision — an override is stored, but nothing changes.
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="override-reason" className="mb-1 block text-xs font-medium text-slate-600">
              Review / override reason <span className="text-red-600">*</span>
            </label>
            <textarea
              ref={reasonRef}
              id="override-reason"
              rows={3}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Mandatory plain-language reason for the override…"
              className="w-full rounded-md border border-slate-300 px-2.5 py-2 text-sm text-navy-800 shadow-sm focus:border-teal-600"
            />
            <p className="mt-0.5 text-[11px] text-slate-500">
              {reason.trim().length === 0
                ? "A non-empty reason is required (SRS FR-OVR-02)."
                : `${reason.trim().length} characters`}
            </p>
          </div>

          <div>
            <label htmlFor="override-reviewer" className="mb-1 block text-xs font-medium text-slate-600">
              Reviewer display name (optional)
            </label>
            <input
              id="override-reviewer"
              type="text"
              value={reviewerName}
              onChange={(event) => setReviewerName(event.target.value)}
              placeholder="e.g. A. Kumar"
              className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm text-navy-800 shadow-sm focus:border-teal-600"
            />
          </div>

          {error ? (
            <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error.message}
            </p>
          ) : null}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-slate-100 px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() =>
              onSubmit({
                district: selection.districtId,
                date: selection.date,
                lead_hours: selection.lead,
                selected_risk_level: selectedRisk,
                reason: reason.trim(),
                reviewer_name: reviewerName.trim() || null,
                role: "forecaster",
              })
            }
            disabled={!canSubmit}
            className="rounded-md bg-teal-700 px-4 py-1.5 text-xs font-semibold text-white hover:bg-teal-800 disabled:opacity-50"
          >
            {submitting ? "Saving…" : "Save Override"}
          </button>
        </footer>
      </div>
    </div>
  );
}