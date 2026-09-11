// Rein darstellende Ansicht eines foto_plan-Werts (Foto + platzierte
// Symbole/Leitungen), ohne jede Bearbeitungs-Interaktion -- von
// SummaryRenderer und CaptureRenderer/FormFieldRenderer (readOnly) sowie
// spaeter dem PDF-Export gemeinsam genutzt, damit die Overlay-Logik nur an
// einer Stelle gepflegt wird.
import { useQuery } from "@tanstack/react-query";

import { planSymboleApi } from "../../api/endpoints";
import type { FotoPlanWert } from "../../types";

export function FotoPlanBild({ wert }: { wert: FotoPlanWert }) {
  const { data: alleSymbole } = useQuery({
    queryKey: ["plan-symbole"],
    queryFn: () => planSymboleApi.list(),
  });
  const symbolNachId = new Map((alleSymbole ?? []).map((s) => [s.id, s]));

  if (!wert.foto) return null;

  return (
    <div className="relative w-full overflow-hidden rounded-md border border-slate-200 bg-white dark:border-stone-700">
      <img src={wert.foto.url} alt="" className="block w-full" />
      <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full">
        {wert.markierungen.map((m, i) =>
          m.art === "linie" ? (
            <polyline
              key={i}
              points={m.punkte.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke={m.farbe}
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
          ) : null,
        )}
      </svg>
      {wert.markierungen.map((m, i) =>
        m.art === "symbol" ? (
          <img
            key={i}
            src={symbolNachId.get(m.symbol_id)?.url}
            alt=""
            style={{ left: `${m.x * 100}%`, top: `${m.y * 100}%`, transform: `translate(-50%, -50%) rotate(${m.winkel}deg)` }}
            className="absolute h-8 w-8 object-contain drop-shadow"
          />
        ) : null,
      )}
    </div>
  );
}
