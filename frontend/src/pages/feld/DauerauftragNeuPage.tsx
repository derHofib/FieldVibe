import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { anlagenApi, dauerauftraegeApi, kundenApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import type { DauerauftragModus, Leistungstyp, VorgangAbrechnungsart } from "../../types";

const LEISTUNGSTYPEN: { value: Leistungstyp; label: string }[] = [
  { value: "wartung", label: "Wartung" },
  { value: "pruefung", label: "Prüfung" },
  { value: "stoerung", label: "Störung" },
  { value: "installation", label: "Installation" },
  { value: "beratung", label: "Beratung" },
  { value: "planung", label: "Planung" },
];

const ABRECHNUNGSARTEN: { value: VorgangAbrechnungsart; label: string }[] = [
  { value: "wartungsvertrag", label: "Wartungsvertrag" },
  { value: "aufwand", label: "Nach Aufwand" },
  { value: "pauschale", label: "Pauschale" },
  { value: "festpreis", label: "Festpreis" },
  { value: "gewaehrleistung", label: "Gewährleistung" },
];

export function DauerauftragNeuPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const vorausgewaehlterKundeId = searchParams.get("kunde_id") ?? "";

  const [kundeId, setKundeId] = useState(vorausgewaehlterKundeId);
  const [anlageIds, setAnlageIds] = useState<string[]>([]);
  const [titel, setTitel] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [leistungstyp, setLeistungstyp] = useState<Leistungstyp>("wartung");
  const [abrechnungsart, setAbrechnungsart] = useState<VorgangAbrechnungsart>("wartungsvertrag");
  const [intervallTage, setIntervallTage] = useState("7");
  const [naechsteFaelligkeit, setNaechsteFaelligkeit] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [modus, setModus] = useState<DauerauftragModus>("rollierend");
  const [toleranzFrueh, setToleranzFrueh] = useState("");
  const [toleranzSpaet, setToleranzSpaet] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });
  const { data: anlagenListe } = useQuery({
    queryKey: ["anlagen", kundeId],
    queryFn: () => anlagenApi.list(kundeId),
    enabled: !!kundeId,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      dauerauftraegeApi.create({
        kunde_id: kundeId,
        anlage_ids: anlageIds.length > 0 ? anlageIds : undefined,
        titel,
        beschreibung: beschreibung || undefined,
        abrechnungsart,
        leistungstyp,
        intervall_tage: Number(intervallTage),
        naechste_faelligkeit_am: naechsteFaelligkeit,
        modus,
        toleranz_frueh_tage: toleranzFrueh ? Number(toleranzFrueh) : undefined,
        toleranz_spaet_tage: toleranzSpaet ? Number(toleranzSpaet) : undefined,
      }),
    onSuccess: (dauerauftrag) => navigate(`/dauerauftraege/${dauerauftrag.id}`),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Fehler"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!kundeId) {
      setError("Bitte einen Kunden auswählen");
      return;
    }
    if (!titel.trim()) {
      setError("Bitte einen Titel eingeben");
      return;
    }
    if (Number(intervallTage) < 1) {
      setError("Intervall muss mindestens 1 Tag sein");
      return;
    }
    createMutation.mutate();
  }

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-ind-ink-3">
        ← Zurück
      </button>
      <h1 className="text-lg font-bold text-ind-ink">Neuer Dauer-Auftrag</h1>
      <p className="text-sm text-ind-ink-3">
        Erzeugt automatisch einen neuen Vorgang, sobald das eingestellte Intervall ab dem Abschluss
        des jeweils letzten erzeugten Vorgangs erreicht ist.
      </p>

      <form
        onSubmit={handleSubmit}
        className="space-y-3 border border-ind-line bg-ind-bg p-4"
      >
        <div>
          <label className="mb-1 block text-sm font-medium text-ind-ink-2">Kunde</label>
          <select
            value={kundeId}
            onChange={(e) => {
              setKundeId(e.target.value);
              setAnlageIds([]);
            }}
            className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
          >
            <option value="">Bitte wählen…</option>
            {kunden?.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name} ({k.kundennummer})
              </option>
            ))}
          </select>
        </div>

        {kundeId && (
          <div>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">
              Anlagen (optional, mehrfach möglich)
            </label>
            <p className="mb-1 text-xs text-ind-ink-3">
              Keine Anlage ausgewählt: der Dauer-Auftrag gilt direkt für den Kunden. Mehrere Anlagen
              ausgewählt: ein Buendel, das für jede Anlage einen eigenen, unabhängig laufenden Zyklus
              anlegt -- statt einen Dauer-Auftrag je Anlage anlegen zu müssen.
            </p>
            {!anlagenListe || anlagenListe.length === 0 ? (
              <p className="text-sm text-ind-ink-3">Keine Anlagen für diesen Kunden vorhanden.</p>
            ) : (
              <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-slate-200 p-2 dark:border-stone-800">
                {anlagenListe.map((a) => (
                  <label
                    key={a.id}
                    className="flex items-center gap-2 py-1 text-sm text-ind-ink-2"
                  >
                    <input
                      type="checkbox"
                      checked={anlageIds.includes(a.id)}
                      onChange={(e) =>
                        setAnlageIds((prev) =>
                          e.target.checked ? [...prev, a.id] : prev.filter((id) => id !== a.id)
                        )
                      }
                    />
                    {a.bezeichnung}
                  </label>
                ))}
              </div>
            )}
          </div>
        )}

        <div>
          <label className="mb-1 block text-sm font-medium text-ind-ink-2">Titel</label>
          <input
            required
            value={titel}
            onChange={(e) => setTitel(e.target.value)}
            placeholder="z.B. Monatliche Wartung Lüftungsanlage"
            className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-ind-ink-2">Beschreibung</label>
          <textarea
            value={beschreibung}
            onChange={(e) => setBeschreibung(e.target.value)}
            rows={3}
            className="w-full resize-none border border-ind-line bg-transparent p-2 text-ind-ink"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">Leistungstyp</label>
            <select
              value={leistungstyp}
              onChange={(e) => setLeistungstyp(e.target.value as Leistungstyp)}
              className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
            >
              {LEISTUNGSTYPEN.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">Abrechnungsart</label>
            <select
              value={abrechnungsart}
              onChange={(e) => setAbrechnungsart(e.target.value as VorgangAbrechnungsart)}
              className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
            >
              {ABRECHNUNGSARTEN.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">
              Intervall (Tage)
            </label>
            <input
              type="number"
              min={1}
              required
              value={intervallTage}
              onChange={(e) => setIntervallTage(e.target.value)}
              className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">
              Erste Fälligkeit
            </label>
            <input
              type="date"
              required
              value={naechsteFaelligkeit}
              onChange={(e) => setNaechsteFaelligkeit(e.target.value)}
              className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
            />
          </div>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-ind-ink-2">
            Wann wird die nächste Fälligkeit berechnet?
          </label>
          <select
            value={modus}
            onChange={(e) => setModus(e.target.value as DauerauftragModus)}
            className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
          >
            <option value="rollierend">
              Rollierend -- ab dem tatsächlichen Abschlussdatum (empfohlen)
            </option>
            <option value="fest">Fest -- ab dem ursprünglich geplanten Termin</option>
          </select>
          <p className="mt-1 text-xs text-ind-ink-3">
            {modus === "rollierend"
              ? "Wird ein Vorgang früher oder später abgeschlossen, verschiebt sich die nächste Fälligkeit entsprechend mit."
              : "Der Kalenderrhythmus bleibt fest, unabhängig davon, wann tatsächlich abgeschlossen wird."}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">
              Toleranz zu früh (Tage)
            </label>
            <input
              type="number"
              min={0}
              value={toleranzFrueh}
              onChange={(e) => setToleranzFrueh(e.target.value)}
              placeholder="kein Limit"
              className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ind-ink-2">
              Toleranz zu spät (Tage)
            </label>
            <input
              type="number"
              min={0}
              value={toleranzSpaet}
              onChange={(e) => setToleranzSpaet(e.target.value)}
              placeholder="kein Limit"
              className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
            />
          </div>
        </div>
        <p className="-mt-2 text-xs text-ind-ink-3">
          Wird außerhalb dieser Toleranz abgeschlossen, entsteht dazu nur ein Hinweis im
          Vorgangs-Chat -- der Abschluss selbst wird nie blockiert.
        </p>

        {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch w-full rounded-md btn-industry btn-industry-primary py-2 font-medium disabled:opacity-50"
        >
          Dauer-Auftrag anlegen
        </button>
      </form>
    </div>
  );
}
