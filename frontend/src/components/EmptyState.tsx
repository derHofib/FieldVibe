import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  icon: Icon,
  text,
  className = "",
}: {
  icon: LucideIcon;
  text: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col items-center gap-2 py-8 text-center ${className}`}>
      <span className="flex h-11 w-11 items-center justify-center border border-ind-line text-ind-ink-2">
        <Icon size={20} strokeWidth={1.75} />
      </span>
      <p className="max-w-xs text-sm text-ind-ink-3">{text}</p>
    </div>
  );
}
