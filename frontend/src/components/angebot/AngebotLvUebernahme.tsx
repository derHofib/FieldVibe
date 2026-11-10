import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { angeboteApi, leistungsverzeichnisApi, leistungsverzeichnisseApi } from "../../api/endpoints";
import { Sheet } from "../apple/Sheet";
import { FehlerMeldung } from "../Hinweiskasten";

const FORM_ID = "angebot-lv-uebernahme";

/** Mehrfachübernahme aus dem Leistungsverzeichnis: Hauptpunkte/Einzelpositionen
 * anhaken, Menge setzen, übernehmen. Ein Hauptpunkt bringt seine Unterpunkte
 * mit und wird im Angebot zum Titel (Gliederung). Die Aufteilung in Lohn/
 * Material und den Preis-Snapshot macht das Backend. */
export function AngebotLvUebernahme({
  angebotId,
  kundeId,
  onClose,
}: {
  angebotId: string;
  kundeId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [mengen, setMengen] = useState<Record<string, string>>({});
  const [mitGliederung, setMitGliederung] = useState(true);
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: positionen, isLoading } = useQuery({
    queryKey: ["leistungsverzeichnis", kundeId],
    queryFn: () => leistungsverzeichnisApi.list(kundeId),
  });
  const { data: lvs } = useQuery({ queryKey: ["leistungsverzeichnisse"], queryFn: leistungsverzeichnisseApi.list });

  const gruppen = new Map<string, NonNullable<typeof positionen>>();
  for (const p of positionen ?? []) {
    gruppen.set(p.leistungsverzeichnis_id, [...(gruppen.get(p.leistungsverzeichnis_id) ?? []), p]);
  }

  // Backend nimmt je Aufruf genau ein LV; mehrere LVs gehen nacheinander.
  const uebernehmen = useMutation({
    meta: { erfolg: "Übernommen" },
    mutationFn: async () => {
      for (const [lvId, liste] of gruppen) {
        const eintraege = liste
          .filter((p) => mengen[p.id] !== undefined)
          .map((p) => ({ lv_position_id: p.id, menge: (mengen[p.id] || "1").replace(",", ".") }));
        if (eintraege.length > 0) {
          await angeboteApi.positionenAusLv(angebotId, { lv_id: lvId, eintraege, mit_gliederung: mitGliederung });
        }
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["angebot", angebotId] });
      queryClient.invalidateQueries({ queryKey: ["angebote"] });
      onClose();
    },
    onError: (err) =>
      setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  const anzahl = Object.keys(mengen).length;
  const ungueltig = Object.values(mengen).some((m) => {
    const n = Number(m.replace(",", "."));
    return m.trim() === "" || Number.isNaN(n) || n <= 0;
  });

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Aus Leistungsverzeichnis"
      vollbild
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form={FORM_ID}
          disabled={anzahl === 0 || ungueltig || uebernehmen.isPending}
          className="text-[17px] font-semibold text-tint disabled:opacity-40"
        >
          Übernehmen{anzahl > 0 ? ` (${anzahl})` : ""}
        </button>
      }
    >
      <form
        id={FORM_ID}
        onSubmit={(e) => {
          e.preventDefault();
          setFehler(null);
          uebernehmen.mutate();
        }}
        className="space-y-4 p-4"
      >
        {fehler && <FehlerMeldung meldung={fehler} alsKasten />}
        {isLoading && <p className="text-sm text-label2">Lädt…</p>}
        {!isLoading && gruppen.size === 0 && (
          <p className="text-sm text-label2">Für diesen Kunden gibt es keine Leistungsverzeichnis-Positionen.</p>
        )}

        <label className="flex items-center gap-2 text-sm text-label">
          <input type="checkbox" checked={mitGliederung} onChange={(e) => setMitGliederung(e.target.checked)} />
          Hauptpunkte als Titel übernehmen (Gliederung)
        </label>

        {[...gruppen].map(([lvId, liste]) => (
          <section key={lvId}>
            <h3 className="mb-1 text-xs font-semibold uppercase text-label2">
              {lvs?.find((l) => l.id === lvId)?.name ?? "Leistungsverzeichnis"}
            </h3>
            <ul className="divide-y-[0.5px] divide-sep">
              {liste.map((p) => {
                const aktiv = mengen[p.id] !== undefined;
                const lohn = Number(p.lohn_gesamt) > 0;
                const material = Number(p.material_gesamt) > 0;
                return (
                  <li key={p.id} className="flex items-center gap-3 py-2">
                    <input
                      type="checkbox"
                      aria-label={`${p.bezeichnung} übernehmen`}
                      checked={aktiv}
                      onChange={(e) => {
                        const rest = { ...mengen };
                        if (e.target.checked) rest[p.id] = "1";
                        else delete rest[p.id];
                        setMengen(rest);
                      }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-label">{p.bezeichnung}</div>
                      <div className="text-xs text-label2">
                        {p.einzelpreis} €/{p.einheit}
                        {(lohn || material) && ` · Lohn ${p.lohn_gesamt} € · Material ${p.material_gesamt} €`}
                      </div>
                    </div>
                    {aktiv && (
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        inputMode="decimal"
                        aria-label={`Menge ${p.bezeichnung}`}
                        value={mengen[p.id]}
                        onChange={(e) => setMengen({ ...mengen, [p.id]: e.target.value })}
                        className="field-ap w-20 shrink-0"
                      />
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </form>
    </Sheet>
  );
}
