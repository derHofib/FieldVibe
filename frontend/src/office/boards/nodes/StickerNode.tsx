import { useReactFlow, type NodeProps } from "@xyflow/react";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Clock,
  Droplet,
  Fan,
  Flame,
  Hammer,
  Info,
  type LucideIcon,
  PlugZap,
  Ruler,
  ShieldAlert,
  Star,
  ThermometerSun,
  Wrench,
  Zap,
} from "lucide-react";
import { useState } from "react";

import type { BoardNode, StickerDaten } from "../types";

// Kuratiert statt frei waehlbar (kein Icon-Suchfeld) -- passend zum
// Handwerks-Alltag: Gewerke, Warnhinweise, Status. Reihenfolge = Reihenfolge
// im Auswahlraster.
export const STICKER_ICONS: Record<string, LucideIcon> = {
  Wrench,
  Zap,
  Flame,
  Droplet,
  PlugZap,
  Fan,
  ThermometerSun,
  Hammer,
  Ruler,
  AlertTriangle,
  ShieldAlert,
  CheckCircle2,
  Clock,
  Camera,
  Star,
  Info,
};

function IconAuswahl({ onWaehlen }: { onWaehlen: (icon: string) => void }) {
  return (
    <div className="nodrag grid grid-cols-4 gap-1 rounded-xl border border-slate-100 bg-white p-2 shadow-xl dark:border-stone-800 dark:bg-stone-900">
      {Object.entries(STICKER_ICONS).map(([name, Icon]) => (
        <button
          key={name}
          onClick={() => onWaehlen(name)}
          title={name}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
        >
          <Icon size={16} strokeWidth={2} />
        </button>
      ))}
    </div>
  );
}

export function StickerNode({ id, data, selected }: NodeProps<BoardNode>) {
  const { updateNodeData } = useReactFlow();
  const { icon } = data as StickerDaten;
  const [zeigeAuswahl, setZeigeAuswahl] = useState(!icon);

  const Icon = STICKER_ICONS[icon];

  return (
    <div className="relative">
      <button
        onClick={() => setZeigeAuswahl((v) => !v)}
        className={`flex h-11 w-11 items-center justify-center rounded-2xl border-2 border-white bg-linear-to-br from-cyan-500 to-blue-600 text-white shadow-lg dark:border-stone-900 ${
          selected ? "ring-2 ring-blue-500 ring-offset-2" : ""
        }`}
      >
        {Icon ? <Icon size={20} strokeWidth={2} /> : <span className="text-[10px] font-bold">?</span>}
      </button>
      {zeigeAuswahl && (
        <div className="absolute top-12 left-1/2 z-10 -translate-x-1/2">
          <IconAuswahl
            onWaehlen={(gewaehlt) => {
              updateNodeData(id, { icon: gewaehlt });
              setZeigeAuswahl(false);
            }}
          />
        </div>
      )}
    </div>
  );
}
