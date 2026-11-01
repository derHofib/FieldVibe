import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api/client";
import { arbeitszeitApi, usersApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SearchableSelect } from "../../components/SearchableSelect";
import { useAuth } from "../../context/AuthContext";
import { SOLL_WOCHENTAG_FELDER, type ArbeitszeitSoll, type Bundesland, type SollWochentagFeld } from "../../types";
import { BUNDESLAND_LABEL, parseStunden, sollWochensumme, stundenFuerApi } from "../../utils/arbeitszeit";
import { formatStundenAlsHHMM } from "../../utils/duration";
import { istModulAktiv } from "../../utils/module";
import { toDateInput } from "../../utils/zeiterfassung";
import { Karte, SeitenKopf } from "../OfficeUi";

const WOCHENTAG_LABEL: Record<SollWochentagFeld, string> = {
  stunden_mo: "Mo",
  stunden_di: "Di",
  stunden_mi: "Mi",
  stunden_do: "Do",
  stunden_fr: "Fr",
  stunden_sa: "Sa",
  stunden_so: "So",
};

const FELD_KLASSE =
  "w-full rounded-[var(--radius-ap-input)] border border-sep bg-card px-2.5 py-1.5 text-sm text-label";

function fehlerText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Fehler";
}

function formatDatum(iso: string): string {
  const [j, m, t] = iso.split("-");
  return `${t}.${m}.${j}`;
}

export function OfficeArbeitszeitEinstellungenPage() {
  const { currentUser } = useAuth();

  if (!currentUser?.darf_abwesenheiten_verwalten || !istModulAktiv(currentUser, "zeiterfassung")) {
    return <EmptyState icon={Clock} text="Dafür fehlt das Recht „Abwesenheiten verwalten“." />;
  }

  return (
    <div className="space-y-4">
      <Link to="/einstellungen" className="text-sm font-medium text-tint-text hover:underline">
        ← Zurück zu Einstellungen
      </Link>
      <SeitenKopf titel="Arbeitszeit" />
      <BundeslandAbschnitt />
      <FeiertageAbschnitt />
      <SollAbschnitt />
    </div>
  );
}

// Eigener Query-Key, damit der Feiertage-Abschnitt den aktuellen Stand kennt,
// ohne dass beide Abschnitte Props durchreichen müssen.
const BUNDESLAND_KEY = ["arbeitszeit-bundesland"];

function BundeslandAbschnitt() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: BUNDESLAND_KEY, queryFn: arbeitszeitApi.bundesland });
  const [hinweis, setHinweis] = useState(false);

  const mutation = useMutation({
    mutationFn: (wert: Bundesland | null) => arbeitszeitApi.bundeslandSetzen(wert),
    onSuccess: () => {
      setHinweis(true);
      void queryClient.invalidateQueries({ queryKey: BUNDESLAND_KEY });
    },
  });

  return (
    <Karte className="space-y-3 p-4">
      <h2 className="text-base font-semibold text-label">Bundesland</h2>
      <p className="text-sm text-label2">
        Bestimmt, welche gesetzlichen Feiertage beim Generieren entstehen. Ohne Bundesland entstehen nur die
        bundesweiten Feiertage.
      </p>
      <select
        aria-label="Bundesland"
        className={`${FELD_KLASSE} max-w-xs`}
        disabled={isLoading || mutation.isPending}
        value={data?.bundesland ?? ""}
        onChange={(e) => mutation.mutate((e.target.value || null) as Bundesland | null)}
      >
        <option value="">Nicht gesetzt</option>
        {(Object.keys(BUNDESLAND_LABEL) as Bundesland[]).map((k) => (
          <option key={k} value={k}>
            {BUNDESLAND_LABEL[k]}
          </option>
        ))}
      </select>
      {mutation.isError && <p className="text-sm text-st-fehlt">{fehlerText(mutation.error)}</p>}
      {hinweis && !mutation.isError && (
        <p className="text-sm text-label2">
          Gespeichert. Bereits angelegte Feiertage bleiben unverändert und müssen bei einem Wechsel des
          Bundeslands manuell bereinigt werden.
        </p>
      )}
    </Karte>
  );
}

function FeiertageAbschnitt() {
  const queryClient = useQueryClient();
  const [jahr, setJahr] = useState(new Date().getFullYear());
  const [datum, setDatum] = useState("");
  const [bezeichnung, setBezeichnung] = useState("");
  const [meldung, setMeldung] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: bundesland } = useQuery({ queryKey: BUNDESLAND_KEY, queryFn: arbeitszeitApi.bundesland });
  const { data: feiertage, isLoading } = useQuery({
    queryKey: ["arbeitszeit-feiertage", jahr],
    queryFn: () => arbeitszeitApi.feiertage(jahr),
  });

  function neuLaden() {
    void queryClient.invalidateQueries({ queryKey: ["arbeitszeit-feiertage"] });
    void queryClient.invalidateQueries({ queryKey: ["arbeitszeit-saldo"] });
  }

  const generieren = useMutation({
    mutationFn: () => arbeitszeitApi.feiertageGenerieren(jahr),
    onSuccess: (erg) => {
      setFehler(null);
      setMeldung(`${erg.angelegt} angelegt, ${erg.uebersprungen} bereits vorhanden.`);
      neuLaden();
    },
    onError: (err) => setFehler(fehlerText(err)),
  });

  const anlegen = useMutation({
    mutationFn: () => arbeitszeitApi.feiertagAnlegen({ datum, bezeichnung: bezeichnung.trim() }),
    onSuccess: () => {
      setFehler(null);
      setMeldung(null);
      setDatum("");
      setBezeichnung("");
      neuLaden();
    },
    onError: (err) =>
      setFehler(
        err instanceof ApiError && err.status === 409 ? "Für dieses Datum gibt es schon einen Feiertag." : fehlerText(err),
      ),
  });

  const loeschen = useMutation({
    mutationFn: (id: string) => arbeitszeitApi.feiertagLoeschen(id),
    onSuccess: () => {
      setFehler(null);
      neuLaden();
    },
    onError: (err) => setFehler(fehlerText(err)),
  });

  function handleGenerieren() {
    if (
      bundesland &&
      bundesland.bundesland === null &&
      !window.confirm(
        "Es ist kein Bundesland gesetzt. Es entstehen nur die bundesweiten Feiertage. Trotzdem generieren?",
      )
    ) {
      return;
    }
    setMeldung(null);
    generieren.mutate();
  }

  function handleAnlegen(e: FormEvent) {
    e.preventDefault();
    if (!datum || !bezeichnung.trim()) return;
    anlegen.mutate();
  }

  return (
    <Karte className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-label">Feiertage</h2>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ap px-3 py-1.5" onClick={() => setJahr((j) => j - 1)} aria-label="Vorheriges Jahr">
            ←
          </button>
          <span className="w-12 text-center text-sm font-semibold tabular-nums text-label">{jahr}</span>
          <button type="button" className="btn-ap px-3 py-1.5" onClick={() => setJahr((j) => j + 1)} aria-label="Nächstes Jahr">
            →
          </button>
        </div>
      </div>

      {bundesland && bundesland.bundesland === null && (
        <p className="rounded-[var(--radius-ap-md)] bg-st-wartet-bg px-3 py-2 text-sm text-st-wartet">
          Kein Bundesland gesetzt: Beim Generieren entstehen nur bundesweite Feiertage.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-ap btn-ap-primary px-3 py-1.5"
          onClick={handleGenerieren}
          disabled={generieren.isPending}
        >
          Feiertage {jahr} generieren
        </button>
        {meldung && <span className="text-sm text-label2">{meldung}</span>}
      </div>

      {isLoading ? (
        <p className="text-sm text-label2">Lädt…</p>
      ) : feiertage && feiertage.length > 0 ? (
        <ul className="divide-y divide-sep">
          {feiertage.map((f) => (
            <li key={f.id} className="flex items-center gap-3 py-2 text-sm">
              <span className="w-24 tabular-nums text-label2">{formatDatum(f.datum)}</span>
              <span className="min-w-0 flex-1 truncate text-label">{f.bezeichnung}</span>
              <button
                type="button"
                className="btn-ap-toolbar text-st-fehlt"
                aria-label={`${f.bezeichnung} löschen`}
                disabled={loeschen.isPending}
                onClick={() => loeschen.mutate(f.id)}
              >
                <Trash2 size={15} strokeWidth={1.5} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-label2">Für {jahr} sind keine Feiertage hinterlegt.</p>
      )}

      <form onSubmit={handleAnlegen} className="flex flex-wrap items-end gap-2 border-t border-sep pt-3">
        <label className="text-xs font-medium text-label2">
          Datum
          <input type="date" className={`${FELD_KLASSE} mt-1 w-40`} value={datum} onChange={(e) => setDatum(e.target.value)} required />
        </label>
        <label className="min-w-48 flex-1 text-xs font-medium text-label2">
          Bezeichnung
          <input
            type="text"
            maxLength={200}
            className={`${FELD_KLASSE} mt-1`}
            value={bezeichnung}
            onChange={(e) => setBezeichnung(e.target.value)}
            placeholder="z. B. Betriebsferien"
            required
          />
        </label>
        <button type="submit" className="btn-ap px-3 py-1.5" disabled={anlegen.isPending}>
          Hinzufügen
        </button>
      </form>
      {fehler && <p className="text-sm text-st-fehlt">{fehler}</p>}
    </Karte>
  );
}

type SollFormular = Record<SollWochentagFeld, string> & { gueltig_ab: string };

function leeresFormular(vorlage?: ArbeitszeitSoll): SollFormular {
  const f = { gueltig_ab: toDateInput(new Date()) } as SollFormular;
  for (const feld of SOLL_WOCHENTAG_FELDER) f[feld] = vorlage ? String(parseStunden(vorlage[feld])) : "0";
  return f;
}

function SollAbschnitt() {
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const [userId, setUserId] = useState(currentUser?.id ?? "");
  const [form, setForm] = useState<SollFormular>(() => leeresFormular());
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: users } = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl });
  const { data: historie, isLoading } = useQuery({
    queryKey: ["arbeitszeit-soll", userId],
    queryFn: () => arbeitszeitApi.soll(userId),
    enabled: !!userId,
  });

  // Beim Mitarbeiterwechsel mit dem zuletzt gültigen Soll vorbelegen: meist
  // ändert sich nur ein Tag.
  useEffect(() => {
    if (historie) setForm(leeresFormular(historie[0]));
  }, [historie, userId]);

  const speichern = useMutation({
    mutationFn: () =>
      arbeitszeitApi.sollSetzen(userId, {
        gueltig_ab: form.gueltig_ab,
        ...(Object.fromEntries(
          SOLL_WOCHENTAG_FELDER.map((f) => [f, stundenFuerApi(form[f])]),
        ) as Record<SollWochentagFeld, string>),
      }),
    onSuccess: () => {
      setFehler(null);
      void queryClient.invalidateQueries({ queryKey: ["arbeitszeit-soll", userId] });
      void queryClient.invalidateQueries({ queryKey: ["arbeitszeit-saldo"] });
    },
    onError: (err) => setFehler(fehlerText(err)),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!userId || !form.gueltig_ab) return;
    speichern.mutate();
  }

  const summe = sollWochensumme(form);

  return (
    <Karte className="space-y-3 p-4">
      <h2 className="text-base font-semibold text-label">Soll-Zeit je Mitarbeiter</h2>
      <p className="text-sm text-label2">
        Eine Zeile gilt ab ihrem Datum bis zur nächsten. Änderungen wirken nie rückwirkend; eine Zeile mit gleichem
        Datum wird ersetzt.
      </p>
      <div className="max-w-xs">
        <SearchableSelect
          value={userId}
          onChange={setUserId}
          placeholder="Mitarbeiter wählen…"
          options={(users ?? []).map((u) => ({ value: u.id, label: u.name }))}
        />
      </div>

      {userId && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-label2">
                  <th className="py-1 pr-3 font-medium">Gültig ab</th>
                  {SOLL_WOCHENTAG_FELDER.map((f) => (
                    <th key={f} className="py-1 pr-2 text-right font-medium">
                      {WOCHENTAG_LABEL[f]}
                    </th>
                  ))}
                  <th className="py-1 text-right font-medium">Woche</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={9} className="py-2 text-label2">
                      Lädt…
                    </td>
                  </tr>
                ) : historie && historie.length > 0 ? (
                  historie.map((z) => (
                    <tr key={z.id} className="border-t border-sep">
                      <td className="py-1.5 pr-3 tabular-nums text-label">{formatDatum(z.gueltig_ab)}</td>
                      {SOLL_WOCHENTAG_FELDER.map((f) => (
                        <td key={f} className="py-1.5 pr-2 text-right tabular-nums text-label">
                          {formatStundenAlsHHMM(parseStunden(z[f]))}
                        </td>
                      ))}
                      <td className="py-1.5 text-right font-medium tabular-nums text-label">
                        {formatStundenAlsHHMM(sollWochensumme(z))}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={9} className="py-2 text-label2">
                      Noch kein Soll hinterlegt.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3 border-t border-sep pt-3">
            <h3 className="text-sm font-semibold text-label">Neue Zeile</h3>
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs font-medium text-label2">
                Gültig ab
                <input
                  type="date"
                  className={`${FELD_KLASSE} mt-1 w-40`}
                  value={form.gueltig_ab}
                  onChange={(e) => setForm({ ...form, gueltig_ab: e.target.value })}
                  required
                />
              </label>
              {SOLL_WOCHENTAG_FELDER.map((f) => (
                <label key={f} className="text-xs font-medium text-label2">
                  {WOCHENTAG_LABEL[f]}
                  <input
                    type="text"
                    inputMode="decimal"
                    className={`${FELD_KLASSE} mt-1 w-16 text-right tabular-nums`}
                    value={form[f]}
                    onChange={(e) => setForm({ ...form, [f]: e.target.value })}
                  />
                </label>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button type="submit" className="btn-ap btn-ap-primary px-3 py-1.5" disabled={speichern.isPending}>
                Speichern
              </button>
              <span className="text-sm text-label2">
                Summe je Woche: <span className="font-semibold tabular-nums text-label">{formatStundenAlsHHMM(summe)} Std.</span>
              </span>
            </div>
            {fehler && <p className="text-sm text-st-fehlt">{fehler}</p>}
          </form>
        </>
      )}
    </Karte>
  );
}
