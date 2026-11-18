/** Fortschrittsbalken mit "x / y erledigt" (Auftrag in Projekt-Ansicht und Vorgang-Tab).
 * Der Balken ist rein dekorativ, die Zahl steht immer als Text daneben. */
export function Fortschritt({ erledigt, gesamt, breit = false }: { erledigt: number; gesamt: number; breit?: boolean }) {
  const anteil = gesamt > 0 ? Math.min(100, Math.round((erledigt / gesamt) * 100)) : 0;
  return (
    <span className="inline-flex items-center gap-2 text-sekundaer text-label2 whitespace-nowrap">
      <span aria-hidden="true" className={`h-1.5 overflow-hidden rounded-full bg-fill2 ${breit ? "w-32" : "w-16"}`}>
        <span className="block h-full rounded-full bg-st-erledigt-dot" style={{ width: `${anteil}%` }} />
      </span>
      {erledigt} / {gesamt} erledigt
    </span>
  );
}
