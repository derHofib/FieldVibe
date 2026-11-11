import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { AnlegenPanel } from "./AnlegenPanel";
import { useBestaetigung } from "./ConfirmDialog";
import { Feld, FELD_KLASSE, NEU_BUTTON_KLASSE } from "./FormularFeld";
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
  speichernLaeuft,
}: {
  eintrag: Omit<Ansprechpartner, "id">;
  onSpeichern: (eintrag: Omit<Ansprechpartner, "id">) => void;
  speichernLaeuft: boolean;
}) {
  const [form, setForm] = useState(eintrag);
  const [nameFehler, setNameFehler] = useState<string | null>(null);

  return (
    <form
      noValidate
      className="space-y-3 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!form.name.trim()) {
          setNameFehler("Bitte einen Namen eingeben.");
          return;
        }
        setNameFehler(null);
        onSpeichern(form);
      }}
    >
      <Feld label="Name" pflicht fehler={nameFehler}>
        {(p) => <input {...p} autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={FELD_KLASSE} />}
      </Feld>
      <Feld label="Position">
        {(p) => (
          <input
            {...p}
            value={form.position ?? ""}
            onChange={(e) => setForm({ ...form, position: e.target.value })}
            placeholder="z.B. Geschäftsführer, Hausmeister"
            className={FELD_KLASSE}
          />
        )}
      </Feld>
      <div className="grid grid-cols-2 gap-3">
        <Feld label="Telefon">
          {(p) => <input {...p} value={form.telefon ?? ""} onChange={(e) => setForm({ ...form, telefon: e.target.value })} className={FELD_KLASSE} />}
        </Feld>
        <Feld label="E-Mail">
          {(p) => <input {...p} type="email" value={form.email ?? ""} onChange={(e) => setForm({ ...form, email: e.target.value })} className={FELD_KLASSE} />}
        </Feld>
      </div>
      <Feld label="Eskalationsstufe">
        {(p) => (
          <select
            {...p}
            value={form.eskalationsstufe ?? ""}
            onChange={(e) =>
              setForm({ ...form, eskalationsstufe: e.target.value ? (Number(e.target.value) as Eskalationsstufe) : null })
            }
            className={FELD_KLASSE}
          >
            <option value="">Keine Eskalationsstufe</option>
            {([1, 2, 3] as Eskalationsstufe[]).map((stufe) => (
              <option key={stufe} value={stufe}>
                {ESKALATIONSSTUFE_LABEL[stufe]}
              </option>
            ))}
          </select>
        )}
      </Feld>
      <label className="btn-touch flex items-center gap-2 text-sm text-label">
        <input type="checkbox" checked={form.operativ} onChange={(e) => setForm({ ...form, operativ: e.target.checked })} />
        Operativer Ansprechpartner (Tagesgeschäft)
      </label>
      <button type="submit" disabled={speichernLaeuft} className="btn-touch btn-ap-primary w-full rounded-md py-2 text-sm font-medium">
        Speichern
      </button>
    </form>
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
  const bestaetigen = useBestaetigung();
  const [neuAnlegen, setNeuAnlegen] = useState(false);
  const [bearbeitenId, setBearbeitenId] = useState<string | null>(null);

  const speichernMutation = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: onSpeichern,
    onSuccess: () => {
      setNeuAnlegen(false);
      setBearbeitenId(null);
    },
  });

  const bearbeiten = liste.find((a) => a.id === bearbeitenId) ?? null;

  function hinzufuegen(eintrag: Omit<Ansprechpartner, "id">) {
    speichernMutation.mutate([...liste, { ...eintrag, id: crypto.randomUUID() }]);
  }

  function aktualisieren(id: string, eintrag: Omit<Ansprechpartner, "id">) {
    speichernMutation.mutate(liste.map((a) => (a.id === id ? { ...eintrag, id } : a)));
  }

  async function entfernen(a: Ansprechpartner) {
    if (!(await bestaetigen({ titel: `${a.name} als Ansprechpartner entfernen?`, bestaetigenLabel: "Entfernen" }))) return;
    speichernMutation.mutate(liste.filter((x) => x.id !== a.id));
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-label2">Ansprechpartner</h2>
        {kannVerwalten && (
          <button onClick={() => setNeuAnlegen(true)} className={NEU_BUTTON_KLASSE}>
            + Neuer Ansprechpartner
          </button>
        )}
      </div>

      {liste.length === 0 && (
        <p className="text-sm text-label2">Noch keine Ansprechpartner hinterlegt.</p>
      )}

      <div className="space-y-2">
        {liste.map((a) => (
            <div
              key={a.id}
              className="card-ap p-3"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-medium text-label">{a.name}</div>
                  {a.position && <div className="text-xs text-label2">{a.position}</div>}
                </div>
                <div className="flex gap-1">
                  {a.operativ && (
                    <span className="rounded-full bg-tintbg px-2 py-0.5 text-xs font-medium text-tint ">
                      Operativ
                    </span>
                  )}
                  {a.eskalationsstufe && (
                    <span className="rounded-full bg-st-arbeit-bg px-2 py-0.5 text-xs font-medium text-st-arbeit ">
                      Stufe {a.eskalationsstufe}
                    </span>
                  )}
                </div>
              </div>
              {(a.telefon || a.email) && (
                <div className="mt-1 text-xs text-label2">
                  {[a.telefon, a.email].filter(Boolean).join(" · ")}
                </div>
              )}
              {a.notiz && <p className="mt-1 text-xs text-label2">{a.notiz}</p>}
              {kannVerwalten && (
                <div className="mt-2 flex gap-3">
                  <button
                    onClick={() => setBearbeitenId(a.id)}
                    className="btn-touch text-xs text-tint underline "
                  >
                    Bearbeiten
                  </button>
                  <button
                    onClick={() => void entfernen(a)}
                    disabled={speichernMutation.isPending}
                    className="btn-touch text-xs text-st-fehlt underline disabled:opacity-50 "
                  >
                    Entfernen
                  </button>
                </div>
              )}
            </div>
        ))}
      </div>

      <AnlegenPanel offen={neuAnlegen && kannVerwalten} titel="Neuer Ansprechpartner" onClose={() => setNeuAnlegen(false)}>
        <AnsprechpartnerForm eintrag={leerFormular()} onSpeichern={hinzufuegen} speichernLaeuft={speichernMutation.isPending} />
      </AnlegenPanel>
      {bearbeiten && (
        <AnlegenPanel offen titel="Ansprechpartner bearbeiten" onClose={() => setBearbeitenId(null)}>
          <AnsprechpartnerForm
            key={bearbeiten.id}
            eintrag={bearbeiten}
            onSpeichern={(eintrag) => aktualisieren(bearbeiten.id, eintrag)}
            speichernLaeuft={speichernMutation.isPending}
          />
        </AnlegenPanel>
      )}
    </div>
  );
}
