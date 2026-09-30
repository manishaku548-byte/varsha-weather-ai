import type { ReactNode } from "react";

interface SectionCardProps {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
}

export default function SectionCard({
  title,
  subtitle,
  icon,
  actions,
  children,
  className = "",
  testId,
}: SectionCardProps) {
  return (
    <section
      aria-label={title}
      data-testid={testId}
      className={`rounded-lg border border-slate-200 bg-white shadow-panel ${className}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2.5">
          {icon ? (
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-navy-50 text-teal-700">
              {icon}
            </span>
          ) : null}
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-navy-800">
              {title}
            </h2>
            {subtitle ? (
              <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
            ) : null}
          </div>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </header>
      <div className="px-4 py-4 sm:px-5">{children}</div>
    </section>
  );
}