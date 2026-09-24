import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  icon: Icon,
  text,
  action,
  className = "",
}: {
  icon: LucideIcon;
  text: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col items-center gap-2 py-8 text-center ${className}`}>
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-fill text-label2">
        <Icon size={20} strokeWidth={2} aria-hidden="true" />
      </span>
      <p className="max-w-xs text-sm text-label2">{text}</p>
      {action}
    </div>
  );
}
