import type { EffektivRead, RechteRegistry } from "../../types/organigramm";
import { aktionLabel, scopeLabel } from "./darstellung";
import { aktionsSpalten, bereichKennt, herkunftTexte, schluessel, type HerkunftAufloeser } from "./rechteMatrix";

const KURZ: Record<string, string> = {
  account_typ: "Vorlage",
  position_override: "Position",
  user_override: "Nutzer",
};

/** Read-only-Matrix effektiver Rechte (Scope + Herkunft) -- Grundlage von "Anzeigen als ...". */
export function EffektiveRechteTabelle({
  registry,
  daten,
  aufloeser,
}: {
  registry: RechteRegistry;
  daten: EffektivRead;
  aufloeser: HerkunftAufloeser;
}) {
  const spalten = aktionsSpalten(registry);
  const rechte = new Map(daten.rechte.map((r) => [schluessel(r.bereich, r.aktion), r]));
  const verweigert = new Map(daten.verweigert.map((v) => [schluessel(v.bereich, v.aktion), v]));

  return (
    <div className="overflow-x-auto rounded-[12px] bg-cell">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Effektive Rechte je Bereich und Aktion</caption>
        <thead className="text-xs text-label2">
          <tr>
            <th scope="col" className="px-3 py-2">
              Bereich
            </th>
            {spalten.map((a) => (
              <th key={a} scope="col" className="px-2 py-2 font-medium">
                {aktionLabel(a)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-sep">
          {registry.bereiche.map((b) => (
            <tr key={b.key}>
              <th scope="row" className="px-3 py-2 text-left font-medium text-label">
                {b.label}
              </th>
              {spalten.map((a) => {
                if (!bereichKennt(registry, b.key, a)) {
                  return (
                    <td key={a} className="px-2 py-2 text-label3">
                      –
                    </td>
                  );
                }
                const key = schluessel(b.key, a);
                const r = rechte.get(key);
                const v = verweigert.get(key);
                if (daten.alle_rechte) {
                  return (
                    <td key={a} className="px-2 py-2 text-st-erledigt" title={`Rolle „${daten.rolle}“ hat alle Rechte`}>
                      <span className="text-[13px] font-medium">{scopeLabel("mandant")}</span>
                    </td>
                  );
                }
                if (r) {
                  const texte = herkunftTexte(r.herkunft, aufloeser);
                  const kurz = [...new Set(r.herkunft.map((h) => KURZ[h.art] ?? h.art))].join(" + ");
                  return (
                    <td key={a} className="px-2 py-1.5" title={texte.join("\n")}>
                      <span className="block text-[13px] font-medium text-st-erledigt">{scopeLabel(r.scope)}</span>
                      <span className="block text-[10px] text-label2">{kurz}</span>
                    </td>
                  );
                }
                if (v) {
                  return (
                    <td key={a} className="px-2 py-1.5" title={herkunftTexte(v.herkunft, aufloeser).join("\n")}>
                      <span className="block text-[13px] font-medium text-st-fehlt">Verweigert</span>
                    </td>
                  );
                }
                return (
                  <td key={a} className="px-2 py-2 text-label3">
                    –
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
