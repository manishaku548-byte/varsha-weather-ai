import { Skeleton } from "./Skeleton";

interface LoadingStateProps {
  lines?: number;
  label?: string;
}

export default function LoadingState({ lines = 4, label = "Loading data from the backend…" }: LoadingStateProps) {
  return (
    <div aria-busy="true" aria-label={label} className="space-y-3" role="status">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={i === 0 ? "h-4 w-2/3" : "h-4"} />
      ))}
    </div>
  );
}