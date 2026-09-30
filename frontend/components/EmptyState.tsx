import { Inbox } from "lucide-react";

interface EmptyStateProps {
  title?: string;
  message?: string;
}

export default function EmptyState({
  title = "No data to display",
  message,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center">
      <Inbox className="h-6 w-6 text-slate-400" aria-hidden="true" />
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {message ? (
        <p className="max-w-md text-xs leading-relaxed text-slate-500">{message}</p>
      ) : null}
    </div>
  );
}