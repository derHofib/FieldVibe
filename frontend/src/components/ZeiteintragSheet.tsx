import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { zeiterfassungApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import type { Zeiterfassung, ZeiterfassungKategorie } from "../types";
import { BUCHUNGSSTATUS_LABEL, buchungsstatusGesperrt, buchungsstatusZuToken } from "../utils/zeiterfassung";
import { StatusPille } from "./apple/StatusPille";
import { Sheet } from "./apple/Sheet";

// Lokale Kopie von toLocalInputValue aus VorgangDetailPage.tsx -- dort eine
// seiten-lokale Hilfsfunktion, kein geteiltes Modul (siehe dortiger
// Kommentar zu WOCHENTAGE fuer dasselbe Vorgehen).
function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatZeitpunkt(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", { timeZone: "Europe/Berlin", dateStyle: "medium", timeStyle: "short" });
}

// "auftrag" bewusst mit eigenem Label hier (anders als
// ZEITERFASSUNG_KATEGORIE_LABEL in utils/zeiterfassung.ts, das dafuer
// bewusst kein Label hat -- dort steht sonst die Vorgangsnummer). In diesem
// Sheet befinden wir uns immer schon im Kontext eines Vorgangs.
const KATEGORIE_OPTIONEN: { wert: ZeiterfassungKategorie; label: string }[] = [
  { wert: "auftrag", label: "Auftrag (dieser Vorgang)" },
  { wert: "fahrzeit", label: "Fahrzeit" },
  { wert: "verwaltung", label: "Verwaltung" },
  { wert: "schulung", label: "Schulung" },
  { wert: "pause", label: "Pause" },
  { wert: "urlaub", label: "Urlaub" },
  { wert: "krankheit", label: "Krankheit" },
  { wert: "sonstiges", label: "Sonstiges" },
];

const AKTION_LABEL: Record<string, string> = {
  angelegt: "Angelegt",
  geaendert: "Geändert",
  geloescht: "Gelöscht",
  wiederhergestellt: "Wiederhergestellt",
  vorgemerkt: "Zur Buchung vorgemerkt",
  vormerkung_zurueckgezogen: "Vormerkung zurückgezogen",
  gebucht: "Gebucht",
  buchung_storniert: "Buchung storniert",
  abgerechnet: "Abgerechnet",
};

const FORM_ID = "zeiteintrag-formular";

/** Sheet zum Anlegen ("+ Zeit nachtragen") oder Bearbeiten eines bereits
 * beendeten Zeiterfassungs-Eintrags an einem Vorgang (Stufe 1+2, siehe
 * docs/konzepte/ZEITERFASSUNG.md). Laufende Timer laufen nie hier durch --
 * die Zeit-Tab-Liste zeigt ohnehin nur Eintraege mit gesetztem ende_at.
 * Ab Buchungsstatus "vorgemerkt" ist der Eintrag nur noch lesbar (siehe
 * Konzept 6.2) -- das Sheet zeigt dann Status + Verlauf statt des Formulars. */
export function ZeiteintragSheet({
  offen,
  onClose,
  vorgangId,
  eintrag,
  onGespeichert,
}: {
  offen: boolean;
  onClose: () => void;
  vorgangId: string;
  eintrag?: Zeiterfassung | null;
  onGespeichert: () => void;
}) {
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const istBearbeiten = !!eintrag;
  const istFremd = !!eintrag && eintrag.techniker_id !== currentUser?.id;
  const gesperrt = !!eintrag && buchungsstatusGesperrt(eintrag.buchungsstatus);
  const [reiter, setReiter] = useState<"details" | "verlauf">("details");

  const jetzt = new Date();
  const vorEinerStunde = new Date(jetzt.getTime() - 60 * 60 * 1000);

  const [kategorie, setKategorie] = useState<ZeiterfassungKategorie>(eintrag?.kategorie ?? "auftrag");
  const [taetigkeit, setTaetigkeit] = useState(eintrag?.taetigkeit ?? "");
  const [startAt, setStartAt] = useState(
    toLocalInputValue(eintrag ? new Date(eintrag.start_at) : vorEinerStunde),
  );
  const [endeAt, setEndeAt] = useState(
    toLocalInputValue(eintrag?.ende_at ? new Date(eintrag.ende_at) : jetzt),
  );
  const [abrechenbar, setAbrechenbar] = useState(
    eintrag?.abrechenbar ?? kategorie === "auftrag",
  );
  const [grund, setGrund] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: verlauf } = useQuery({
    queryKey: ["zeiterfassung-verlauf", eintrag?.id],
    queryFn: () => zeiterfassungApi.verlauf(eintrag!.id),
    enabled: !!eintrag && reiter === "verlauf",
  });

  function invalidateUndSchliessen() {
    queryClient.invalidateQueries({ queryKey: ["zeiterfassung", vorgangId] });
    queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
    onGespeichert();
    onClose();
  }

  const anlegenMutation = useMutation({
    mutationFn: () =>
      zeiterfassungApi.manuellErfassen({
        vorgang_id: vorgangId,
        kategorie,
        start_at: new Date(startAt).toISOString(),
        ende_at: new Date(endeAt).toISOString(),
        taetigkeit,
        abrechenbar,
      }),
    onSuccess: invalidateUndSchliessen,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  const aktualisierenMutation = useMutation({
    mutationFn: () =>
      zeiterfassungApi.aktualisieren(eintrag!.id, {
        kategorie,
        start_at: new Date(startAt).toISOString(),
        ende_at: new Date(endeAt).toISOString(),
        taetigkeit,
        abrechenbar,
        ...(istFremd ? { grund } : {}),
      }),
    onSuccess: invalidateUndSchliessen,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  const loeschenMutation = useMutation({
    mutationFn: () => zeiterfassungApi.loeschen(eintrag!.id, istFremd ? grund : undefined),
    onSuccess: invalidateUndSchliessen,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  const zurueckziehenMutation = useMutation({
    mutationFn: () => zeiterfassungApi.vormerkungZurueckziehen([eintrag!.id]),
    onSuccess: invalidateUndSchliessen,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  const speichertGerade = anlegenMutation.isPending || aktualisierenMutation.isPending;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (new Date(endeAt) <= new Date(startAt)) {
      setError("Ende muss nach dem Start liegen");
      return;
    }
    if (istFremd && !grund.trim()) {
      setError("Grund ist beim Bearbeiten eines fremden Eintrags Pflicht");
      return;
    }
    if (istBearbeiten) {
      aktualisierenMutation.mutate();
    } else {
      anlegenMutation.mutate();
    }
  }

  const reiterButtons = istBearbeiten ? (
    <div className="flex border-b border-sep px-4">
      {(["details", "verlauf"] as const).map((r) => (
        <button
          key={r}
          type="button"
          onClick={() => setReiter(r)}
          className={`btn-touch px-3 py-2 text-sm font-medium ${
            reiter === r ? "border-b-2 border-tint text-tint-text" : "text-label2"
          }`}
        >
          {r === "details" ? "Details" : "Verlauf"}
        </button>
      ))}
    </div>
  ) : null;

  return (
    <Sheet
      offen={offen}
      onClose={onClose}
      titel={istBearbeiten ? "Zeit bearbeiten" : "Zeit nachtragen"}
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint">
          {gesperrt || reiter === "verlauf" ? "Schließen" : "Abbrechen"}
        </button>
      }
      rechts={
        !gesperrt && reiter === "details" ? (
          <button
            type="submit"
            form={FORM_ID}
            disabled={speichertGerade}
            className="text-[17px] font-semibold text-tint disabled:opacity-40"
          >
            Speichern
          </button>
        ) : undefined
      }
    >
      {reiterButtons}

      {reiter === "verlauf" && istBearbeiten ? (
        <div className="space-y-3 p-4">
          {!verlauf ? (
            <p className="text-sm text-label2">Lädt…</p>
          ) : verlauf.length === 0 ? (
            <p className="text-sm text-label2">Noch keine Einträge im Verlauf.</p>
          ) : (
            verlauf.map((v) => (
              <div key={v.id} className="border-b border-sep pb-2 text-sm last:border-0">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-label">{AKTION_LABEL[v.aktion] ?? v.aktion}</span>
                  <span className="text-xs text-label2">{formatZeitpunkt(v.geaendert_am)}</span>
                </div>
                {v.feld && (
                  <p className="text-xs text-label2">
                    {v.feld}: {String(v.alter_wert ?? "—")} → {String(v.neuer_wert ?? "—")}
                  </p>
                )}
                {v.grund && <p className="mt-0.5 text-xs italic text-label2">Grund: {v.grund}</p>}
              </div>
            ))
          )}
        </div>
      ) : gesperrt && eintrag ? (
        <div className="space-y-4 p-4">
          <StatusPille
            status={buchungsstatusZuToken(eintrag.buchungsstatus)}
            label={BUCHUNGSSTATUS_LABEL[eintrag.buchungsstatus]}
          />
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-label2">Tätigkeit</dt>
              <dd className="text-label">{eintrag.taetigkeit || "—"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-label2">Von–Bis</dt>
              <dd className="text-label">
                {formatZeitpunkt(eintrag.start_at)} – {eintrag.ende_at ? formatZeitpunkt(eintrag.ende_at) : "—"}
              </dd>
            </div>
            {eintrag.gebucht_am && (
              <div className="flex justify-between">
                <dt className="text-label2">Gebucht am</dt>
                <dd className="text-label">{formatZeitpunkt(eintrag.gebucht_am)}</dd>
              </div>
            )}
            {eintrag.vorgemerkt_am && (
              <div className="flex justify-between">
                <dt className="text-label2">Vorgemerkt am</dt>
                <dd className="text-label">{formatZeitpunkt(eintrag.vorgemerkt_am)}</dd>
              </div>
            )}
          </dl>
          <p className="flex items-center gap-1.5 text-xs text-label2">
            <Lock size={13} strokeWidth={2} />
            {eintrag.buchungsstatus === "vorgemerkt"
              ? "Zur Buchung vorgemerkt — erst zurückziehen, um zu bearbeiten."
              : eintrag.buchungsstatus === "gebucht"
                ? "Gebucht — für alle unveränderbar, erst die Buchung stornieren."
                : "Abgerechnet — endgültig gesperrt."}
          </p>
          {eintrag.buchungsstatus === "vorgemerkt" && (
            <button
              type="button"
              onClick={() => zurueckziehenMutation.mutate()}
              disabled={zurueckziehenMutation.isPending}
              className="btn-touch btn-ap w-full text-sm"
            >
              Vormerkung zurückziehen
            </button>
          )}
          {error && <p className="text-sm text-st-fehlt">{error}</p>}
        </div>
      ) : (
        <form id={FORM_ID} onSubmit={handleSubmit} className="space-y-4 p-4">
          {error && <p className="text-sm text-st-fehlt">{error}</p>}

          <div>
            <label className="mb-1 block text-xs font-medium text-label2">Kategorie</label>
            <select
              value={kategorie}
              onChange={(e) => setKategorie(e.target.value as ZeiterfassungKategorie)}
              className="field-ap"
            >
              {KATEGORIE_OPTIONEN.map((opt) => (
                <option key={opt.wert} value={opt.wert}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-label2">Tätigkeit</label>
            <input
              value={taetigkeit}
              onChange={(e) => setTaetigkeit(e.target.value)}
              placeholder="Was wurde gemacht?"
              className="field-ap"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-label2">Start</label>
              <input
                type="datetime-local"
                value={startAt}
                onChange={(e) => setStartAt(e.target.value)}
                className="field-ap"
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-label2">Ende</label>
              <input
                type="datetime-local"
                value={endeAt}
                onChange={(e) => setEndeAt(e.target.value)}
                className="field-ap"
                required
              />
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm text-label">
            <input
              type="checkbox"
              checked={abrechenbar}
              onChange={(e) => setAbrechenbar(e.target.checked)}
              className="h-4 w-4"
            />
            Abrechenbar
          </label>

          {istFremd && (
            <div>
              <label className="mb-1 block text-xs font-medium text-label2">
                Grund (Pflicht bei fremden Einträgen)
              </label>
              <input
                value={grund}
                onChange={(e) => setGrund(e.target.value)}
                placeholder="z. B. Techniker vergaß Tätigkeit"
                className="field-ap"
              />
            </div>
          )}

          {istBearbeiten && (
            <button
              type="button"
              onClick={() => {
                if (window.confirm("Zeiteintrag wirklich löschen?")) {
                  loeschenMutation.mutate();
                }
              }}
              disabled={loeschenMutation.isPending || (istFremd && !grund.trim())}
              title={istFremd && !grund.trim() ? "Grund eintragen, um einen fremden Eintrag zu löschen" : undefined}
              className="btn-touch text-sm font-medium text-st-fehlt disabled:opacity-50"
            >
              Eintrag löschen
            </button>
          )}
        </form>
      )}
    </Sheet>
  );
}
