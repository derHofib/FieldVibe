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
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-stone-800 dark:text-stone-500">
        <Icon size={20} strokeWidth={1.75} />
      </span>
      <p className="max-w-xs text-sm text-slate-400 dark:text-stone-500">{text}</p>
    </div>
  );
}
