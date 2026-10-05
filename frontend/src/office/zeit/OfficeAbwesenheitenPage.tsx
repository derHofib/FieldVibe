import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CalendarDays, ClipboardList, Plus, Settings2 } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { abwesenheitenApi, usersApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { useAuth } from "../../context/AuthContext";
import type { AbwesenheitArt, AbwesenheitStatus } from "../../types";
import {
  ABWESENHEIT_ART_LABEL,
  ABWESENHEIT_STATUS_LABEL,
  formatTage,
  kalenderRaster,
  offeneAntraege,
} from "../../utils/abwesenheit";
import { istModulAktiv } from "../../utils/module";
import { monatsGrenzen, toDateInput } from "../../utils/zeiterfassung";
import { AnsichtUmschalter, Karte, SeitenKopf } from "../OfficeUi";
import { AbwesenheitSheet } from "./AbwesenheitSheet";
import { AbwesenheitZeile, UrlaubskontoKacheln } from "./AbwesenheitUi";

type Tab = "offen" | "kalender" | "alle" | "anspruch";

const WOCHENTAG_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

// Kategorie, nicht Status: die Art wird ueber die Tone-Token unterschieden,
// zusaetzlich traegt jede Zelle einen Buchstaben (Farbe allein reicht nicht).
const ART_ZELLE: Record<AbwesenheitArt, { klasse: string; kuerzel: string }> = {
  urlaub: { klasse: "bg-tone-sky/25", kuerzel: "U" },
  krankheit: { klasse: "bg-tone-rose/25", kuerzel: "K" },
  freizeitausgleich: { klasse: "bg-tone-amber/25", kuerzel: "F" },
};

function fehlerText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Fehler";
}

export function OfficeAbwesenheitenPage() {
  const { currentUser } = useAuth();
  const [tab, setTab] = useState<Tab>("offen");
  const [eintragen, setEintragen] = useState(false);
  const queryClient = useQueryClient();

  if (!istModulAktiv(currentUser, "zeiterfassung") || !currentUser?.darf_abwesenheiten_verwalten) {
    return <EmptyState icon={CalendarCheck} text="Dafür fehlt die Berechtigung „Abwesenheiten verwalten“." />;
  }

  return (
    <div className="space-y-4">
      <SeitenKopf titel="Abwesenheiten">
        <AnsichtUmschalter
          wert={tab}
          onWechsel={setTab}
          optionen={[
            { wert: "offen", label: "Offene Anträge", icon: ClipboardList },
            { wert: "kalender", label: "Kalender", icon: CalendarDays },
            { wert: "alle", label: "Alle Anträge", icon: CalendarCheck },
            { wert: "anspruch", label: "Urlaubsanspruch", icon: Settings2 },
          ]}
        />
        <button type="button" onClick={() => setEintragen(true)} className="btn-ap btn-ap-primary inline-flex items-center gap-1 px-3 py-1.5">
          <Plus size={14} strokeWidth={2} aria-hidden="true" /> Eintragen
        </button>
      </SeitenKopf>

      {tab === "offen" && <OffeneAntraege />}
      {tab === "kalender" && <KalenderAnsicht />}
      {tab === "alle" && <AlleAntraege />}
      {tab === "anspruch" && <AnspruchAbschnitt />}

      {eintragen && (
        <AbwesenheitSheet
          onClose={() => setEintragen(false)}
          onGespeichert={() => {
            setEintragen(false);
            void queryClient.invalidateQueries({ queryKey: ["abwesenheiten"] });
          }}
        />
      )}
    </div>
  );
}

function useAntragAktionen() {
  const queryClient = useQueryClient();
  const [fehler, setFehler] = useState<string | null>(null);
  const optionen = {
    onSuccess: () => {
      setFehler(null);
      void queryClient.invalidateQueries({ queryKey: ["abwesenheiten"] });
      void queryClient.invalidateQueries({ queryKey: ["arbeitszeit-saldo"] });
      void queryClient.invalidateQueries({ queryKey: ["zeiterfassung-monat"] });
    },
    onError: (err: unknown) => setFehler(fehlerText(err)),
  };
  const genehmigen = useMutation({ mutationFn: (id: string) => abwesenheitenApi.genehmigen(id), ...optionen });
  const ablehnen = useMutation({
    mutationFn: ({ id, antwort }: { id: string; antwort: string }) => abwesenheitenApi.ablehnen(id, antwort.trim()),
    ...optionen,
  });
  const stornieren = useMutation({ mutationFn: (id: string) => abwesenheitenApi.zurueckziehen(id), ...optionen });
  return { genehmigen, ablehnen, stornieren, fehler, ausstehend: genehmigen.isPending || ablehnen.isPending || stornieren.isPending };
}

function OffeneAntraege() {
  const { data, isLoading } = useQuery({
    queryKey: ["abwesenheiten", "offen"],
    queryFn: () => abwesenheitenApi.liste({ alle: true, nur_offene: true }),
  });
  const aktionen = useAntragAktionen();
  const [ablehnenId, setAblehnenId] = useState<string | null>(null);
  const [antwort, setAntwort] = useState("");
  const liste = useMemo(() => offeneAntraege(data ?? []), [data]);

  if (isLoading) return <p className="text-sm text-label2">Lädt…</p>;
  if (liste.length === 0) return <EmptyState icon={ClipboardList} text="Keine offenen Anträge." />;

  return (
    <div className="space-y-2">
      <Karte className="p-1">
        <ul className="divide-y divide-sep">
          {liste.map((a) => (
            <div key={a.id}>
              <AbwesenheitZeile a={a} mitName>
                <button
                  type="button"
                  className="btn-ap btn-ap-primary px-3 py-1"
                  disabled={aktionen.ausstehend}
                  onClick={() => aktionen.genehmigen.mutate(a.id)}
                >
                  Genehmigen
                </button>
                <button
                  type="button"
                  className="btn-ap px-3 py-1 text-st-fehlt"
                  disabled={aktionen.ausstehend}
                  onClick={() => {
                    setAblehnenId(ablehnenId === a.id ? null : a.id);
                    setAntwort("");
                  }}
                >
                  Ablehnen
                </button>
              </AbwesenheitZeile>
              {ablehnenId === a.id && (
                <form
                  className="flex flex-wrap items-center gap-2 px-3 pb-2"
                  onSubmit={(e: FormEvent) => {
                    e.preventDefault();
                    aktionen.ablehnen.mutate({ id: a.id, antwort }, { onSuccess: () => setAblehnenId(null) });
                  }}
                >
                  <input
                    className="field-ap max-w-md flex-1"
                    placeholder="Antwort an den Mitarbeiter (optional)"
                    maxLength={2000}
                    value={antwort}
                    onChange={(e) => setAntwort(e.target.value)}
                    aria-label="Antwort"
                  />
                  <button type="submit" className="btn-ap px-3 py-1 text-st-fehlt" disabled={aktionen.ausstehend}>
                    Ablehnung senden
                  </button>
                </form>
              )}
            </div>
          ))}
        </ul>
      </Karte>
      {aktionen.fehler && <p className="text-sm text-st-fehlt">{aktionen.fehler}</p>}
    </div>
  );
}

function KalenderAnsicht() {
  const heute = new Date();
  const [jahr, setJahr] = useState(heute.getFullYear());
  const [monat0, setMonat0] = useState(heute.getMonth());
  const { von, bis } = monatsGrenzen(jahr, monat0);
  const heuteTag = toDateInput(heute);

  const { data, isLoading, error } = useQuery({
    queryKey: ["abwesenheiten", "kalender", von, bis],
    queryFn: () => abwesenheitenApi.kalender(von, bis),
  });
  const { tage, zeilen } = useMemo(() => kalenderRaster(data ?? [], jahr, monat0), [data, jahr, monat0]);

  function wechseln(delta: number) {
    const d = new Date(jahr, monat0 + delta, 1);
    setJahr(d.getFullYear());
    setMonat0(d.getMonth());
  }
  const monatsName = new Date(jahr, monat0, 1).toLocaleDateString("de-DE", { month: "long", year: "numeric" });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => wechseln(-1)} className="btn-ap px-3 py-1.5">
          ← Monat
        </button>
        <span className="min-w-36 text-center text-sm font-semibold text-label">{monatsName}</span>
        <button type="button" onClick={() => wechseln(1)} className="btn-ap px-3 py-1.5">
          Monat →
        </button>
        <span className="ml-auto flex flex-wrap gap-3 text-xs text-label2">
          {(Object.keys(ART_ZELLE) as AbwesenheitArt[]).map((art) => (
            <span key={art} className="inline-flex items-center gap-1">
              <span className={`inline-block h-4 w-4 rounded-[4px] text-center text-[10px] font-semibold leading-4 text-label ${ART_ZELLE[art].klasse}`}>
                {ART_ZELLE[art].kuerzel}
              </span>
              {ABWESENHEIT_ART_LABEL[art]}
            </span>
          ))}
        </span>
      </div>
      {isLoading ? (
        <p className="text-sm text-label2">Lädt…</p>
      ) : error ? (
        <p className="text-sm text-st-fehlt">{fehlerText(error)}</p>
      ) : zeilen.length === 0 ? (
        <EmptyState icon={CalendarDays} text="In diesem Monat gibt es keine genehmigten Abwesenheiten." />
      ) : (
        <Karte className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full border-separate border-spacing-0 text-xs">
              <thead>
                <tr>
                  <th scope="col" className="sticky left-0 z-10 bg-card px-3 py-2 text-left font-medium text-label2">
                    Mitarbeiter
                  </th>
                  {tage.map((t) => (
                    <th
                      key={t.tag}
                      scope="col"
                      className={`min-w-7 px-0.5 py-1 text-center font-medium tabular-nums ${
                        t.tag === heuteTag ? "bg-tintbg text-label" : t.istWochenende ? "bg-fill text-label2" : "text-label2"
                      }`}
                    >
                      <div>{WOCHENTAG_KURZ[t.wochentag]}</div>
                      <div>{t.tagNr}</div>
                    </th>
                  ))}
                  <th scope="col" className="px-3 py-2 text-right font-medium text-label2">
                    Tage
                  </th>
                </tr>
              </thead>
              <tbody>
                {zeilen.map((z) => (
                  <tr key={z.user_id}>
                    <th scope="row" className="sticky left-0 z-10 whitespace-nowrap bg-card px-3 py-1.5 text-left text-sm font-medium text-label">
                      {z.user_name}
                    </th>
                    {tage.map((t) => {
                      const zelle = z.zellen.get(t.tag);
                      return (
                        <td key={t.tag} className={`p-0.5 text-center ${t.istWochenende ? "bg-fill" : ""}`}>
                          {zelle && (
                            <span
                              title={`${ABWESENHEIT_ART_LABEL[zelle.art]}${zelle.halb ? " (halber Tag)" : ""}`}
                              className={`block rounded-[4px] py-1 text-[11px] font-semibold text-label ${ART_ZELLE[zelle.art].klasse}`}
                            >
                              {ART_ZELLE[zelle.art].kuerzel}
                              {zelle.halb && "½"}
                            </span>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-3 text-right tabular-nums text-label">{formatTage(z.tage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Karte>
      )}
    </div>
  );
}

function AlleAntraege() {
  const [jahr, setJahr] = useState(new Date().getFullYear());
  const [status, setStatus] = useState<AbwesenheitStatus | "">("");
  const { data, isLoading } = useQuery({
    queryKey: ["abwesenheiten", "alle", jahr, status],
    queryFn: () =>
      abwesenheitenApi.liste({ alle: true, von: `${jahr}-01-01`, bis: `${jahr}-12-31`, status: status || undefined }),
  });
  const aktionen = useAntragAktionen();

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs font-medium text-label2">
          Jahr
          <input
            type="number"
            className="mt-1 block w-24 rounded-[var(--radius-ap-input)] border border-sep bg-card px-2.5 py-1.5 text-sm tabular-nums text-label"
            value={jahr}
            min={2000}
            max={2100}
            onChange={(e) => setJahr(Number(e.target.value) || jahr)}
          />
        </label>
        <label className="text-xs font-medium text-label2">
          Status
          <select
            className="mt-1 block rounded-[var(--radius-ap-input)] border border-sep bg-card px-2.5 py-1.5 text-sm text-label"
            value={status}
            onChange={(e) => setStatus(e.target.value as AbwesenheitStatus | "")}
          >
            <option value="">Alle</option>
            {(Object.keys(ABWESENHEIT_STATUS_LABEL) as AbwesenheitStatus[]).map((s) => (
              <option key={s} value={s}>
                {ABWESENHEIT_STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
      </div>
      {isLoading ? (
        <p className="text-sm text-label2">Lädt…</p>
      ) : !data || data.length === 0 ? (
        <EmptyState icon={CalendarCheck} text="Keine Anträge im gewählten Zeitraum." />
      ) : (
        <Karte className="p-1">
          <ul className="divide-y divide-sep">
            {data.map((a) => (
              <AbwesenheitZeile key={a.id} a={a} mitName>
                {(a.status === "genehmigt" || a.status === "offen") && (
                  <button
                    type="button"
                    className="text-sm font-medium text-st-fehlt disabled:opacity-50"
                    disabled={aktionen.ausstehend}
                    onClick={() => {
                      if (a.status === "offen" || window.confirm("Genehmigte Abwesenheit stornieren? Die automatisch erzeugten Zeiteinträge werden entfernt.")) {
                        aktionen.stornieren.mutate(a.id);
                      }
                    }}
                  >
                    {a.status === "genehmigt" ? "Stornieren" : "Zurückziehen"}
                  </button>
                )}
              </AbwesenheitZeile>
            ))}
          </ul>
        </Karte>
      )}
      {aktionen.fehler && <p className="text-sm text-st-fehlt">{aktionen.fehler}</p>}
    </div>
  );
}

function AnspruchAbschnitt() {
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const [userId, setUserId] = useState(currentUser?.id ?? "");
  const [jahr, setJahr] = useState(new Date().getFullYear());
  const [tage, setTage] = useState("");
  const [rest, setRest] = useState("");
  const [verfall, setVerfall] = useState("");
  const [meldung, setMeldung] = useState<{ fehler: boolean; text: string } | null>(null);

  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  const { data: konto, isLoading } = useQuery({
    queryKey: ["abwesenheiten", "konto", userId, jahr],
    queryFn: () => abwesenheitenApi.konto({ user_id: userId, jahr }),
    enabled: !!userId,
  });

  // Formular folgt dem geladenen Konto (Mitarbeiter-/Jahreswechsel, Speichern).
  useEffect(() => {
    if (!konto) return;
    setTage(formatTage(konto.anspruch).replace(",", "."));
    setRest(formatTage(konto.resturlaub).replace(",", "."));
    setVerfall(konto.resturlaub_verfaellt_am ?? "");
  }, [konto]);

  const speichern = useMutation({
    mutationFn: () =>
      abwesenheitenApi.anspruchSetzen(userId, jahr, {
        tage: tage.trim().replace(",", ".") || "0",
        resturlaub_tage: rest.trim().replace(",", ".") || "0",
        resturlaub_verfaellt_am: verfall || null,
      }),
    onSuccess: () => {
      setMeldung({ fehler: false, text: "Gespeichert." });
      void queryClient.invalidateQueries({ queryKey: ["abwesenheiten", "konto"] });
    },
    onError: (err) => setMeldung({ fehler: true, text: fehlerText(err) }),
  });

  return (
    <div className="space-y-4">
      <Karte className="space-y-3 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs font-medium text-label2">
            Mitarbeiter
            <select
              className="field-ap mt-1 min-w-48"
              value={userId}
              onChange={(e) => {
                setUserId(e.target.value);
                setMeldung(null);
              }}
            >
              {(users ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-label2">
            Jahr
            <input
              type="number"
              className="field-ap mt-1 w-24 tabular-nums"
              value={jahr}
              min={2000}
              max={2100}
              onChange={(e) => {
                setJahr(Number(e.target.value) || jahr);
                setMeldung(null);
              }}
            />
          </label>
        </div>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setMeldung(null);
            speichern.mutate();
          }}
        >
          <label className="text-xs font-medium text-label2">
            Anspruch (Tage)
            <input className="field-ap mt-1 w-28 text-right tabular-nums" inputMode="decimal" value={tage} onChange={(e) => setTage(e.target.value)} />
          </label>
          <label className="text-xs font-medium text-label2">
            Resturlaub (Tage)
            <input className="field-ap mt-1 w-28 text-right tabular-nums" inputMode="decimal" value={rest} onChange={(e) => setRest(e.target.value)} />
          </label>
          <label className="text-xs font-medium text-label2">
            Resturlaub verfällt am
            <input type="date" className="field-ap mt-1 w-44" value={verfall} onChange={(e) => setVerfall(e.target.value)} />
          </label>
          <button type="submit" className="btn-ap btn-ap-primary px-3 py-1.5" disabled={speichern.isPending || !userId}>
            Speichern
          </button>
        </form>
        {meldung && (
          <p role={meldung.fehler ? "alert" : "status"} className={`text-sm ${meldung.fehler ? "text-st-fehlt" : "text-label2"}`}>
            {meldung.text}
          </p>
        )}
      </Karte>
      {isLoading ? <p className="text-sm text-label2">Lädt…</p> : konto && <UrlaubskontoKacheln konto={konto} />}
    </div>
  );
}
