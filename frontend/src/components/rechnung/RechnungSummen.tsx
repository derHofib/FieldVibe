import type { Rechnung } from "../../types";
import { steuergruppeLabel, zeigeSteuergruppen } from "../../utils/steuer";

/** Summenblock der Rechnung. Eine einzige Gruppe ohne Hinweis bleibt bei
 * Netto/Brutto; mehrere Gruppen (oder ein Steuerhinweis) werden je Gruppe mit
 * Netto, Steuer und Hinweistext aufgeschlüsselt. */
export function RechnungSummen({ rechnung }: { rechnung: Rechnung }) {
  const gruppen = rechnung.steuergruppen ?? [];

  if (!zeigeSteuergruppen(gruppen)) {
    return (
      <div className="mt-3 text-right text-sm">
        <div className="text-label2">Netto: {rechnung.betrag_netto} EUR</div>
        <div className="font-semibold text-label">Brutto: {rechnung.betrag_brutto} EUR</div>
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-2 text-sm" data-testid="steuergruppen">
      <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 gap-y-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-label2">Steuergruppe</span>
        <span className="text-right text-[11px] font-semibold uppercase tracking-wide text-label2">Netto</span>
        <span className="text-right text-[11px] font-semibold uppercase tracking-wide text-label2">Steuer</span>
        {gruppen.map((g) => {
          const hinweise = g.hinweise?.length ? g.hinweise : g.hinweis ? [g.hinweis] : [];
          return (
            <div key={`${g.kategorie}-${g.satz}`} className="col-span-3 grid grid-cols-subgrid">
              <span className="text-label">{steuergruppeLabel(g)}</span>
              <span className="text-right tabular-nums text-label">{g.netto} EUR</span>
              <span className="text-right tabular-nums text-label">{g.steuer} EUR</span>
              {hinweise.map((h) => (
                <p key={h} className="col-span-3 mt-0.5 text-xs text-label2">
                  {h}
                </p>
              ))}
            </div>
          );
        })}
      </div>
      <div className="space-y-0.5 border-t-[0.5px] border-sep pt-2 text-right">
        <div className="text-label2">Netto: {rechnung.betrag_netto} EUR</div>
        <div className="text-label2">Steuer: {rechnung.betrag_steuer ?? "0.00"} EUR</div>
        <div className="font-semibold text-label">Brutto: {rechnung.betrag_brutto} EUR</div>
      </div>
    </div>
  );
}
