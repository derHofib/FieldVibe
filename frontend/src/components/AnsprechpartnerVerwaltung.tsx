import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import type { Ansprechpartner, Eskalationsstufe } from "../types";

const ESKALATIONSSTUFE_LABEL: Record<Eskalationsstufe, string> = {
  1: "Stufe 1 – Erstkontakt",
  2: "Stufe 2 – Eskalation",
  3: "Stufe 3 – Geschäftsleitung/Notfall",
};

function leerFormular(): Omit<Ansprechpartner, "id"> {
  return { name: "", position: "", telefon: "", email: "", operativ: false, eskalationsstufe: null, notiz: "" };
}

function AnsprechpartnerForm({
  eintrag,
  onSpeichern,
  onAbbrechen,
  speichernLaeuft,
}: {
  eintrag: Omit<Ansprechpartner, "id">;
  onSpeichern: (eintrag: Omit<Ansprechpartner, "id">) => void;
  onAbbrechen: () => void;
  speichernLaeuft: boolean;
}) {
  const [form, setForm] = useState(eintrag);

  return (
    <div className="space-y-2 border border-ind-line-2 p-3">
      <input
        autoFocus
        value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })}
        placeholder="Name *"
        className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
      />
      <input
        value={form.position ?? ""}
        onChange={(e) => setForm({ ...form, position: e.target.value })}
        placeholder="Position (z.B. Geschäftsführer, Hausmeister)"
        className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          value={form.telefon ?? ""}
          onChange={(e) => setForm({ ...form, telefon: e.target.value })}
          placeholder="Telefon"
          className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
        />
        <input
          type="email"
          value={form.email ?? ""}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          placeholder="E-Mail"
          className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
        />
      </div>
      <select
        value={form.eskalationsstufe ?? ""}
        onChange={(e) =>
          setForm({ ...form, eskalationsstufe: e.target.value ? (Number(e.target.value) as Eskalationsstufe) : null })
        }
        className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
      >
        <option value="">Keine Eskalationsstufe</option>
        {([1, 2, 3] as Eskalationsstufe[]).map((stufe) => (
          <option key={stufe} value={stufe}>
            {ESKALATIONSSTUFE_LABEL[stufe]}
          </option>
        ))}
      </select>
      <label className="btn-touch flex items-center gap-2 text-sm text-ind-ink-2">
        <input
          type="checkbox"
          checked={form.operativ}
          onChange={(e) => setForm({ ...form, operativ: e.target.checked })}
        />
        Operativer Ansprechpartner (Tagesgeschäft)
      </label>
      <div className="flex gap-2">
        <button
          disabled={!form.name.trim() || speichernLaeuft}
          onClick={() => onSpeichern(form)}
          className="btn-touch flex-1 rounded-md btn-industry btn-industry-primary py-2 text-sm font-medium disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={onAbbrechen}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

/** Verwaltung einer Ansprechpartner-Liste (Anlegen/Bearbeiten/Entfernen,
 * Eskalationsstufe + operativ als Kategorisierung) -- von Kunde UND Partner
 * genutzt, die beide dieselbe JSONB-Liste am eigenen Datensatz halten (siehe
 * app/schemas/kontakt.py). onSpeichern schreibt die komplette naechste Liste
 * (die Entitaet selbst bleibt Sache des Aufrufers, z.B. kundenApi.update
 * oder partnerApi.update) und stoesst bei Erfolg das Schliessen der
 * Anlegen-/Bearbeiten-Formulare an. */
export function AnsprechpartnerVerwaltung({
  liste,
  kannVerwalten,
  onSpeichern,
}: {
  liste: Ansprechpartner[];
  kannVerwalten: boolean;
  onSpeichern: (naechsteListe: Ansprechpartner[]) => Promise<unknown>;
}) {
  const [neuAnlegen, setNeuAnlegen] = useState(false);
  const [bearbeitenId, setBearbeitenId] = useState<string | null>(null);

  const speichernMutation = useMutation({
    mutationFn: onSpeichern,
    onSuccess: () => {
      setNeuAnlegen(false);
      setBearbeitenId(null);
    },
  });

  function hinzufuegen(eintrag: Omit<Ansprechpartner, "id">) {
    speichernMutation.mutate([...liste, { ...eintrag, id: crypto.randomUUID() }]);
  }

  function aktualisieren(id: string, eintrag: Omit<Ansprechpartner, "id">) {
    speichernMutation.mutate(liste.map((a) => (a.id === id ? { ...eintrag, id } : a)));
  }

  function entfernen(id: string) {
    speichernMutation.mutate(liste.filter((a) => a.id !== id));
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ind-ink-3">Ansprechpartner</h2>
        {kannVerwalten && !neuAnlegen && (
          <button onClick={() => setNeuAnlegen(true)} className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400">
            + Neu
          </button>
        )}
      </div>

      {liste.length === 0 && !neuAnlegen && (
        <p className="text-sm text-ind-ink-3">Noch keine Ansprechpartner hinterlegt.</p>
      )}

      <div className="space-y-2">
        {liste.map((a) =>
          bearbeitenId === a.id ? (
            <AnsprechpartnerForm
              key={a.id}
              eintrag={a}
              onSpeichern={(eintrag) => aktualisieren(a.id, eintrag)}
              onAbbrechen={() => setBearbeitenId(null)}
              speichernLaeuft={speichernMutation.isPending}
            />
          ) : (
            <div
              key={a.id}
              className="border border-ind-line bg-ind-bg p-3"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-medium text-ind-ink">{a.name}</div>
                  {a.position && <div className="text-xs text-ind-ink-3">{a.position}</div>}
                </div>
                <div className="flex gap-1">
                  {a.operativ && (
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-500/15 dark:text-blue-300">
                      Operativ
                    </span>
                  )}
                  {a.eskalationsstufe && (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
                      Stufe {a.eskalationsstufe}
                    </span>
                  )}
                </div>
              </div>
              {(a.telefon || a.email) && (
                <div className="mt-1 text-xs text-ind-ink-3">
                  {[a.telefon, a.email].filter(Boolean).join(" · ")}
                </div>
              )}
              {a.notiz && <p className="mt-1 text-xs text-ind-ink-3">{a.notiz}</p>}
              {kannVerwalten && (
                <div className="mt-2 flex gap-3">
                  <button
                    onClick={() => setBearbeitenId(a.id)}
                    className="btn-touch text-xs text-blue-700 underline dark:text-blue-400"
                  >
                    Bearbeiten
                  </button>
                  <button
                    onClick={() => entfernen(a.id)}
                    disabled={speichernMutation.isPending}
                    className="btn-touch text-xs text-red-700 underline disabled:opacity-50 dark:text-red-400"
                  >
                    Entfernen
                  </button>
                </div>
              )}
            </div>
          )
        )}

        {neuAnlegen && kannVerwalten && (
          <AnsprechpartnerForm
            eintrag={leerFormular()}
            onSpeichern={hinzufuegen}
            onAbbrechen={() => setNeuAnlegen(false)}
            speichernLaeuft={speichernMutation.isPending}
          />
        )}
      </div>
    </div>
  );
}
