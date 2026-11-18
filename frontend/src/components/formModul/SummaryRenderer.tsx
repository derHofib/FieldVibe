// Read-only Zusammenfassungs-Ansicht einer form_submission. Root-Felder
// werden als Label/Wert-Liste dargestellt; eine Wiederholgruppe wird
// automatisch als Tabelle gerendert (Spalten = Gruppenfelder, Zeilen =
// values[group_key]) -- das ist die "automatisch aus einer Wiederholgruppe
// erzeugte Tabelle in der Summary-Ansicht" aus den Abnahmekriterien. Numerische
// Spalten bekommen zusaetzlich eine Summenzeile (einfache Aggregation, siehe
// Migrationsplan Schritt 9).
import { Check, X } from "lucide-react";
import { useMemo } from "react";

import { applyRules } from "../../utils/formLogicEngine";
import { grenzwertHinweis } from "../../utils/formular";
import { FotoPlanBild } from "./FotoPlanBild";
import type { FormField, FormGroup, FormLogicRule, FormPresentationElement, FotoPlanWert } from "../../types";

interface SummaryRendererProps {
  fields: FormField[];
  groups: FormGroup[];
  rules: FormLogicRule[];
  // Aktuell ungenutzt (siehe Kommentar unten bei rootFelder) -- bleibt Teil
  // der Props, damit die Aufrufstelle dieselben View-Daten wie beim
  // CaptureRenderer durchreichen kann, ohne zwei unterschiedliche Signaturen
  // zu pflegen.
  elements: FormPresentationElement[];
  values: Record<string, unknown>;
  viewId?: string | null;
}

interface DateiWert {
  url: string;
}

function istDatei(wert: unknown): wert is DateiWert {
  return typeof wert === "object" && wert !== null && typeof (wert as DateiWert).url === "string";
}

/** Wert eines Feldes in der Zusammenfassung: Ja/Nein mit Symbol (Farbe allein
 * traegt die Aussage nicht), Zahlen mit Grenzwert-Markierung, Fotos und
 * Unterschriften als Bild statt "Datei hinterlegt". */
function WertAnzeige({ feld, wert }: { feld: FormField; wert: unknown }) {
  if (feld.feld_typ === "ja_nein" && typeof wert === "boolean") {
    return wert ? (
      <span className="inline-flex items-center gap-1 text-label">
        <Check size={14} strokeWidth={2.5} className="text-st-erledigt" aria-hidden="true" /> Ja
      </span>
    ) : (
      <span className="inline-flex items-center gap-1 text-label">
        <X size={14} strokeWidth={2.5} className="text-st-fehlt" aria-hidden="true" /> Nein
      </span>
    );
  }
  if (feld.feld_typ === "foto" && istDatei(wert)) {
    return <img src={wert.url} alt={feld.label.de ?? feld.key} className="h-16 w-20 rounded-[var(--radius-ap-sm)] object-cover" />;
  }
  if (feld.feld_typ === "unterschrift" && istDatei(wert)) {
    return (
      <img
        src={wert.url}
        alt={`Unterschrift: ${feld.label.de ?? feld.key}`}
        className="h-14 rounded-[var(--radius-ap-sm)] border border-sep bg-white object-contain"
      />
    );
  }
  const hinweis = feld.feld_typ === "zahl" ? grenzwertHinweis(feld.validation, wert) : null;
  if (hinweis) {
    return (
      <span className="font-semibold text-st-fehlt">
        {formatWert(feld, wert)} <span className="text-sekundaer">{hinweis}</span>
      </span>
    );
  }
  return <>{formatWert(feld, wert)}</>;
}

function formatWert(feld: FormField, wert: unknown): string {
  if (wert === null || wert === undefined || wert === "") return "—";
  if (feld.feld_typ === "ja_nein") return wert ? "Ja" : "Nein";
  if (Array.isArray(wert)) return wert.join(", ");
  if (feld.feld_typ === "gps" && typeof wert === "object") {
    const gps = wert as { lat: number; lng: number };
    return `${gps.lat.toFixed(6)}, ${gps.lng.toFixed(6)}`;
  }
  if (feld.feld_typ === "adresse" && typeof wert === "object") {
    const adresse = wert as { strasse?: string; plz?: string; ort?: string };
    return [adresse.strasse, [adresse.plz, adresse.ort].filter(Boolean).join(" ")].filter(Boolean).join(", ") || "—";
  }
  if (feld.feld_typ === "betrag" && (typeof wert === "number" || typeof wert === "string")) {
    return `${Number(wert).toFixed(2)} €`;
  }
  if (typeof wert === "object" && wert !== null && "url" in wert) {
    const datei = wert as { filename?: string | null };
    return feld.feld_typ === "datei" ? datei.filename || "Datei hinterlegt" : "Datei hinterlegt";
  }
  if (feld.feld_typ === "foto_plan") {
    return (wert as FotoPlanWert)?.foto ? "Foto hinterlegt" : "—";
  }
  return String(wert);
}

export function SummaryRenderer({ fields, groups, rules, values, viewId = null }: SummaryRendererProps) {
  const { states } = useMemo(
    () =>
      applyRules({
        fields: fields.map((f) => ({ key: f.key, group_key: f.group_key })),
        groups: groups.map((g) => ({ key: g.key })),
        rules,
        values,
        viewId,
      }),
    [fields, groups, rules, values, viewId],
  );

  // Abschnitts-Ueberschriften (heading-Elemente) werden hier bewusst nicht
  // interleaved dargestellt -- form_fields.reihenfolge und
  // form_presentation_elements.reihenfolge sind zwei unabhaengige
  // Zaehler je Tabelle, eine verlaessliche Zuordnung "diese Ueberschrift
  // gehoert vor jenes Feld" gibt es ohne einen gemeinsamen Sortier-Schluessel
  // nicht. Der CaptureRenderer kann das (dort ist die Reihenfolge aus dem
  // Backfill noch die urspruenglich geteilte Zaehlung), die Summary-Ansicht
  // zeigt Root-Felder einfach als flache Liste.
  const rootFelder = fields.filter((f) => f.group_key === null).sort((a, b) => a.reihenfolge - b.reihenfolge);

  return (
    <div className="space-y-4">
      <div>
        {rootFelder.map((feld) => {
          const state = states.get(feld.key);
          if (state && !state.visible) return null;
          if (feld.feld_typ === "foto_plan") {
            const wert = values[feld.key] as FotoPlanWert | undefined;
            return (
              <div key={feld.id} className="space-y-1.5 border-b border-sep py-1.5">
                <span className="block text-sekundaer text-label2">{feld.label.de ?? feld.key}</span>
                {wert?.foto ? <FotoPlanBild wert={wert} /> : <span className="text-fliess font-medium text-label">—</span>}
              </div>
            );
          }
          return (
            <div key={feld.id} className="flex items-baseline justify-between gap-4 border-b border-sep py-1.5">
              <span className="text-sekundaer text-label2">{feld.label.de ?? feld.key}</span>
              <span className="text-right text-fliess font-medium text-label"><WertAnzeige feld={feld} wert={values[feld.key]} /></span>
            </div>
          );
        })}
      </div>

      {groups.map((gruppe) => {
        const gruppenState = states.get(gruppe.key);
        if (gruppenState && !gruppenState.visible) return null;
        const gruppenFelder = fields.filter((f) => f.group_key === gruppe.key).sort((a, b) => a.reihenfolge - b.reihenfolge);
        const zeilen = Array.isArray(values[gruppe.key]) ? (values[gruppe.key] as Record<string, unknown>[]) : [];
        const numerischeSpalten = gruppenFelder.filter((f) => f.feld_typ === "zahl");

        // Abschnitt (repeatable=false): flache Label/Wert-Liste wie Root-
        // Felder statt einer Tabelle -- eine Tabelle mit nur einer Zeile
        // waere hier nur unnoetiger Overhead.
        if (!gruppe.repeatable) {
          const zeile = zeilen[0] ?? {};
          return (
            <div key={gruppe.id}>
              <h3 className="mb-1.5 text-zeile font-semibold text-label">{gruppe.label.de ?? gruppe.key}</h3>
              {gruppenFelder.map((feld) => {
                if (feld.feld_typ === "foto_plan") {
                  const wert = zeile[feld.key] as FotoPlanWert | undefined;
                  return (
                    <div key={feld.id} className="space-y-1.5 border-b border-sep py-1.5">
                      <span className="block text-sekundaer text-label2">{feld.label.de ?? feld.key}</span>
                      {wert?.foto ? <FotoPlanBild wert={wert} /> : <span className="text-fliess font-medium text-label">—</span>}
                    </div>
                  );
                }
                return (
                  <div key={feld.id} className="flex items-baseline justify-between gap-4 border-b border-sep py-1.5">
                    <span className="text-sekundaer text-label2">{feld.label.de ?? feld.key}</span>
                    <span className="text-right text-fliess font-medium text-label"><WertAnzeige feld={feld} wert={zeile[feld.key]} /></span>
                  </div>
                );
              })}
            </div>
          );
        }

        return (
          <div key={gruppe.id}>
            <h3 className="mb-1.5 text-zeile font-semibold text-label">{gruppe.label.de ?? gruppe.key}</h3>
            {zeilen.length === 0 ? (
              <p className="text-sekundaer text-label2">Keine Einträge.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-fliess">
                  <thead>
                    <tr className="border-b border-sepstrong text-left text-meta font-medium tracking-wide uppercase text-label2">
                      {gruppenFelder.map((f) => (
                        <th key={f.id} className="py-1.5 pr-3">
                          {f.label.de ?? f.key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {zeilen.map((zeile, index) => (
                      <tr key={index} className="border-b border-sep">
                        {gruppenFelder.map((f) => (
                          <td key={f.id} className="py-1.5 pr-3 text-label">
                            <WertAnzeige feld={f} wert={zeile[f.key]} />
                          </td>
                        ))}
                      </tr>
                    ))}
                    {numerischeSpalten.length > 0 && (
                      <tr className="font-semibold text-label">
                        {gruppenFelder.map((f) => {
                          if (!numerischeSpalten.includes(f)) return <td key={f.id} className="py-1.5 pr-3" />;
                          const summe = zeilen.reduce((acc, z) => acc + (Number(z[f.key]) || 0), 0);
                          return (
                            <td key={f.id} className="py-1.5 pr-3">
                              Σ {summe}
                            </td>
                          );
                        })}
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
