"use client";

import type { ReactNode } from "react";
import { CloudRain, RefreshCw, ShieldCheck, Wifi, WifiOff } from "lucide-react";
import Badge from "./Badge";
import { ROLE_OPTIONS, type Role } from "@/lib/constants";

export type HealthState = "checking" | "connected" | "reconnecting" | "offline";

function healthLabel(state: HealthState): { text: string; tone: "emerald" | "amber" | "red" | "neutral"; icon: ReactNode } {
  switch (state) {
    case "connected":
      return { text: "Connected", tone: "emerald", icon: <Wifi className="h-3.5 w-3.5" aria-hidden="true" /> };
    case "reconnecting":
      return { text: "Reconnecting", tone: "amber", icon: <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> };
    case "checking":
      return { text: "Checking", tone: "neutral", icon: <Wifi className="h-3.5 w-3.5" aria-hidden="true" /> };
    default:
      return { text: "Offline", tone: "red", icon: <WifiOff className="h-3.5 w-3.5" aria-hidden="true" /> };
  }
}

function modelModeLabel(mode: "trained" | "fallback" | "unavailable"): {
  text: string;
  tone: "emerald" | "amber" | "red";
} {
  switch (mode) {
    case "trained":
      return { text: "Trained Local-Correction Model", tone: "emerald" };
    case "fallback":
      return { text: "Fallback AI Source", tone: "amber" };
    default:
      return { text: "Model Unavailable", tone: "red" };
  }
}

interface AppHeaderProps {
  health: { dataMode?: string; dataLabel?: string } | null;
  healthState: HealthState;
  modelMode: "trained" | "fallback" | "unavailable";
  role: Role;
  onRoleChange: (role: Role) => void;
  onRetryHealth: () => void;
}

export default function AppHeader({
  health,
  healthState,
  modelMode,
  role,
  onRoleChange,
  onRetryHealth,
}: AppHeaderProps) {
  const healthBadge = healthLabel(healthState);
  const modelBadge = modelModeLabel(modelMode);

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur print:hidden">
      <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-navy-800 text-teal-300">
            <CloudRain className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-navy-900">
                VARSHA Weather AI
              </h1>
              <Badge tone="navy">SIH26081</Badge>
            </div>
            <p className="text-[11px] font-medium leading-4 text-slate-500">
              Verified Adaptive Regime-aware Skill-weighted Hybrid Analytics
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="teal">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Decision-Support Prototype
          </Badge>
          {health?.dataMode ? (
            <Badge tone="navy" title={health.dataLabel ?? undefined}>
              Synthetic Development Dataset
            </Badge>
          ) : null}
          <Badge tone={modelBadge.tone} title="Phase 4 model readiness from GET /model/status">
            {modelBadge.text}
          </Badge>
          <button
            type="button"
            onClick={onRetryHealth}
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-[11px] font-medium text-slate-700 hover:bg-slate-100"
            title="Backend /health - retry the connection check"
          >
            {healthBadge.icon}
            {healthBadge.text}
          </button>
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="role-select" className="text-[11px] font-medium text-slate-500">
            Local demo role
          </label>
          <select
            id="role-select"
            value={role}
            onChange={(event) => onRoleChange(event.target.value as Role)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-navy-800"
          >
            {ROLE_OPTIONS.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </header>
  );
}