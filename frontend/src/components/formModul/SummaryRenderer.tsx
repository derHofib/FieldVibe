// Read-only Zusammenfassungs-Ansicht einer form_submission. Root-Felder
// werden als Label/Wert-Liste dargestellt; eine Wiederholgruppe wird
// automatisch als Tabelle gerendert (Spalten = Gruppenfelder, Zeilen =
// values[group_key]) -- das ist die "automatisch aus einer Wiederholgruppe
// erzeugte Tabelle in der Summary-Ansicht" aus den Abnahmekriterien. Numerische
// Spalten bekommen zusaetzlich eine Summenzeile (einfache Aggregation, siehe
// Migrationsplan Schritt 9).
import { useMemo } from "react";

import { applyRules } from "../../utils/formLogicEngine";
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
              <div key={feld.id} className="space-y-1.5 border-b border-ind-line py-1.5">
                <span className="block text-sm text-ind-ink-3">{feld.label.de ?? feld.key}</span>
                {wert?.foto ? <FotoPlanBild wert={wert} /> : <span className="text-sm font-medium text-ind-ink">—</span>}
              </div>
            );
          }
          return (
            <div key={feld.id} className="flex items-baseline justify-between gap-4 border-b border-ind-line py-1.5">
              <span className="text-sm text-ind-ink-3">{feld.label.de ?? feld.key}</span>
              <span className="text-right text-sm font-medium text-ind-ink">{formatWert(feld, values[feld.key])}</span>
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
              <h3 className="mb-1.5 text-base font-semibold text-ind-ink">{gruppe.label.de ?? gruppe.key}</h3>
              {gruppenFelder.map((feld) => {
                if (feld.feld_typ === "foto_plan") {
                  const wert = zeile[feld.key] as FotoPlanWert | undefined;
                  return (
                    <div key={feld.id} className="space-y-1.5 border-b border-ind-line py-1.5">
                      <span className="block text-sm text-ind-ink-3">{feld.label.de ?? feld.key}</span>
                      {wert?.foto ? <FotoPlanBild wert={wert} /> : <span className="text-sm font-medium text-ind-ink">—</span>}
                    </div>
                  );
                }
                return (
                  <div key={feld.id} className="flex items-baseline justify-between gap-4 border-b border-ind-line py-1.5">
                    <span className="text-sm text-ind-ink-3">{feld.label.de ?? feld.key}</span>
                    <span className="text-right text-sm font-medium text-ind-ink">{formatWert(feld, zeile[feld.key])}</span>
                  </div>
                );
              })}
            </div>
          );
        }

        return (
          <div key={gruppe.id}>
            <h3 className="mb-1.5 text-base font-semibold text-ind-ink">{gruppe.label.de ?? gruppe.key}</h3>
            {zeilen.length === 0 ? (
              <p className="text-sm text-ind-ink-3">Keine Einträge.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-ind-line-2 text-left text-xs font-medium uppercase text-ind-ink-3">
                      {gruppenFelder.map((f) => (
                        <th key={f.id} className="py-1.5 pr-3">
                          {f.label.de ?? f.key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {zeilen.map((zeile, index) => (
                      <tr key={index} className="border-b border-ind-line">
                        {gruppenFelder.map((f) => (
                          <td key={f.id} className="py-1.5 pr-3 text-ind-ink">
                            {formatWert(f, zeile[f.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {numerischeSpalten.length > 0 && (
                      <tr className="font-semibold text-ind-ink">
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
