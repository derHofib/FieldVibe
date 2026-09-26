import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Hourglass } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { auftraegeApi, kundenApi, projekteApi, usersApi, zeiterfassungApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SearchableSelect } from "../../components/SearchableSelect";
import { ZeiteintragSheet } from "../../components/ZeiteintragSheet";
import { StatusPille } from "../../components/apple/StatusPille";
import { useAuth } from "../../context/AuthContext";
import type { Zeiterfassung, ZeiterfassungBuchungsstatus } from "../../types";
import { formatSekundenAlsHHMM } from "../../utils/duration";
import {
  BUCHUNGSSTATUS_LABEL,
  ZEITERFASSUNG_KATEGORIE_LABEL,
  buchungsstatusZuToken,
  formatUhrzeit,
} from "../../utils/zeiterfassung";

const BUCHUNGSSTATUS_OPTIONEN: ZeiterfassungBuchungsstatus[] = ["vermerkt", "vorgemerkt", "gebucht", "abgerechnet"];

interface Gruppe {
  key: string;
  vorgangId: string | null;
  vorgangsnummer: string | null;
  kategorieLabel: string | null;
  kontext: string | null;
  eintraege: Zeiterfassung[];
}

function gruppenBilden(
  eintraege: Zeiterfassung[],
  kunden: { id: string; name: string }[] | undefined,
  auftraege: { id: string; titel: string }[] | undefined,
  projekte: { id: string; name: string }[] | undefined,
): Gruppe[] {
  const map = new Map<string, Gruppe>();
  for (const e of eintraege) {
    const key = e.vorgang_id ?? `kategorie:${e.kategorie}`;
    let gruppe = map.get(key);
    if (!gruppe) {
      const kontextTeile = [
        e.vorgang_kunde_id ? kunden?.find((k) => k.id === e.vorgang_kunde_id)?.name : undefined,
        e.vorgang_auftrag_id ? auftraege?.find((a) => a.id === e.vorgang_auftrag_id)?.titel : undefined,
        e.vorgang_projekt_id ? projekte?.find((p) => p.id === e.vorgang_projekt_id)?.name : undefined,
      ].filter((teil): teil is string => !!teil);
      gruppe = {
        key,
        vorgangId: e.vorgang_id,
        vorgangsnummer: e.vorgangsnummer,
        kategorieLabel: e.vorgang_id ? null : (ZEITERFASSUNG_KATEGORIE_LABEL[e.kategorie] ?? e.kategorie),
        kontext: kontextTeile.length > 0 ? kontextTeile.join(" · ") : null,
        eintraege: [],
      };
      map.set(key, gruppe);
    }
    gruppe.eintraege.push(e);
  }
  return [...map.values()].sort((a, b) => (a.vorgangsnummer ?? a.kategorieLabel ?? "").localeCompare(b.vorgangsnummer ?? b.kategorieLabel ?? ""));
}

function gruppenSumme(gruppe: Gruppe): number {
  return gruppe.eintraege.reduce(
    (summe, e) => summe + (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000,
    0,
  );
}

/** Zentrale Seite fuer Buchungsberechtigte: mandantenweite Sicht auf zur
 * Buchung anstehende Zeiteintraege (Filter + Sammel-Aktionsleiste wie im
 * Zeit-Tab von VorgangDetailPage.tsx, hier ueber alle Vorgaenge hinweg
 * statt nur den aktuellen) plus laufende Timer mit der Moeglichkeit,
 * einen fremden Timer zu beenden (siehe docs/konzepte/ZEITERFASSUNG.md
 * Abschnitt 7.1/7.3, darf_zeiten_buchen in types/index.ts). Reiht sich per
 * navSeiten.ts in Feld-App und Office ein. */
export function ZeitenBuchenPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const darfZeitenBuchen = !!currentUser?.darf_zeiten_buchen;

  const [technikerId, setTechnikerId] = useState("");
  const [von, setVon] = useState("");
  const [bis, setBis] = useState("");
  const [kundeId, setKundeId] = useState("");
  const [auftragId, setAuftragId] = useState("");
  const [projektId, setProjektId] = useState("");
  const [vermerktAelterAlsTage, setVermerktAelterAlsTage] = useState("");
  const [buchungsstatus, setBuchungsstatus] = useState<ZeiterfassungBuchungsstatus | "">("vorgemerkt");

  const [ausgewaehlteIds, setAusgewaehlteIds] = useState<Set<string>>(new Set());
  const [stornierenModus, setStornierenModus] = useState(false);
  const [stornierenGrund, setStornierenGrund] = useState("");
  const [sheetEintrag, setSheetEintrag] = useState<Zeiterfassung | null>(null);
  const [beendenId, setBeendenId] = useState<string | null>(null);
  const [beendenGrund, setBeendenGrund] = useState("");
  const [aktionsFehler, setAktionsFehler] = useState<string | null>(null);
  const meldeAktionsFehler = (err: unknown) =>
    setAktionsFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.");

  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list, enabled: darfZeitenBuchen });
  const techniker = (users ?? []).filter((u) => u.nur_zugewiesene_kunden);
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list(), enabled: darfZeitenBuchen });
  const { data: auftraege } = useQuery({ queryKey: ["auftraege"], queryFn: () => auftraegeApi.list(), enabled: darfZeitenBuchen });
  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list(), enabled: darfZeitenBuchen });

  const { data: eintraege, isLoading } = useQuery({
    queryKey: [
      "zeiterfassung-buchen-liste",
      technikerId,
      von,
      bis,
      kundeId,
      auftragId,
      projektId,
      vermerktAelterAlsTage,
      buchungsstatus,
    ],
    queryFn: () =>
      zeiterfassungApi.listFuerZeitraum({
        techniker_id: technikerId || undefined,
        von: von || undefined,
        bis: bis || undefined,
        kunde_id: kundeId || undefined,
        auftrag_id: auftragId || undefined,
        projekt_id: projektId || undefined,
        vermerkt_aelter_als_tage: vermerktAelterAlsTage ? Number(vermerktAelterAlsTage) : undefined,
        buchungsstatus: buchungsstatus || undefined,
      }),
    enabled: darfZeitenBuchen,
  });

  const { data: laufendeTimer } = useQuery({
    queryKey: ["zeiterfassung-buchen-laufend"],
    queryFn: () => zeiterfassungApi.listFuerZeitraum({ laufend: true }),
    enabled: darfZeitenBuchen,
  });

  function nachBuchungsaktionAufraeumen() {
    queryClient.invalidateQueries({ queryKey: ["zeiterfassung-buchen-liste"] });
    queryClient.invalidateQueries({ queryKey: ["zeiterfassung-vorgemerkt-anzahl"] });
    setAusgewaehlteIds(new Set());
    setStornierenModus(false);
    setStornierenGrund("");
  }
  const vormerkenMutation = useMutation({
    mutationFn: (ids: string[]) => zeiterfassungApi.vormerken(ids),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });
  const zurueckziehenMutation = useMutation({
    mutationFn: (ids: string[]) => zeiterfassungApi.vormerkungZurueckziehen(ids),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });
  const buchenMutation = useMutation({
    mutationFn: (ids: string[]) => zeiterfassungApi.buchen(ids),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });
  const stornierenMutation = useMutation({
    mutationFn: () => zeiterfassungApi.buchungStornieren([...ausgewaehlteIds], stornierenGrund),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });
  const stopMutation = useMutation({
    mutationFn: ({ id, grund }: { id: string; grund?: string }) =>
      zeiterfassungApi.stop(id, grund ? { grund } : undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-buchen-laufend"] });
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
      setBeendenId(null);
      setBeendenGrund("");
    },
    onError: meldeAktionsFehler,
  });

  if (!darfZeitenBuchen) {
    return <EmptyState icon={Hourglass} text="Keine Berechtigung für diese Seite." />;
  }

  // Laufende Eintraege (ende_at noch nicht gesetzt) gehoeren in den Abschnitt
  // "Laufende Timer" unten, nicht in die buchbare Liste -- analog zum
  // Zeit-Tab in VorgangDetailPage.tsx.
  const buchbareEintraege = (eintraege ?? []).filter((e) => e.ende_at);
  const gruppen = gruppenBilden(buchbareEintraege, kunden, auftraege, projekte);

  function kannZeitAuswaehlen(e: Zeiterfassung): boolean {
    return e.buchungsstatus !== "abgerechnet";
  }
  const ausgewaehlteEintraege = buchbareEintraege.filter((e) => ausgewaehlteIds.has(e.id));
  const ausgewaehlterStatus = ausgewaehlteEintraege[0]?.buchungsstatus ?? null;
  function zeitCheckboxToggeln(e: Zeiterfassung) {
    setAusgewaehlteIds((bisherige) => {
      const neu = new Set(bisherige);
      if (neu.has(e.id)) {
        neu.delete(e.id);
      } else {
        if (ausgewaehlterStatus && e.buchungsstatus !== ausgewaehlterStatus) neu.clear();
        neu.add(e.id);
      }
      return neu;
    });
  }
  function handleBuchen() {
    const stunden = formatSekundenAlsHHMM(
      ausgewaehlteEintraege.reduce(
        (summe, e) => summe + (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000,
        0,
      ),
    );
    if (
      window.confirm(
        `${ausgewaehlteEintraege.length} Eintrag/Einträge mit insgesamt ${stunden} Std. buchen? Gebuchte Einträge kannst du danach nicht mehr ändern.`,
      )
    ) {
      buchenMutation.mutate([...ausgewaehlteIds]);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="flex items-center gap-2 text-lg font-bold text-label">
        <Hourglass size={19} strokeWidth={2} className="text-tint" />
        Zeiten buchen
      </h1>

      {aktionsFehler && <p className="text-sm text-st-fehlt">{aktionsFehler}</p>}

      <div className="card-ap grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-label2">Techniker</label>
          <select value={technikerId} onChange={(e) => setTechnikerId(e.target.value)} className="field-ap">
            <option value="">Alle</option>
            {techniker.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-label2">Status</label>
          <select
            value={buchungsstatus}
            onChange={(e) => setBuchungsstatus(e.target.value as ZeiterfassungBuchungsstatus | "")}
            className="field-ap"
          >
            <option value="">Alle</option>
            {BUCHUNGSSTATUS_OPTIONEN.map((s) => (
              <option key={s} value={s}>
                {BUCHUNGSSTATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-label2">Vermerkt älter als (Tage)</label>
          <input
            type="number"
            min="0"
            inputMode="numeric"
            value={vermerktAelterAlsTage}
            onChange={(e) => setVermerktAelterAlsTage(e.target.value)}
            placeholder="z. B. 3"
            className="field-ap"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-label2">Von</label>
          <input type="date" value={von} onChange={(e) => setVon(e.target.value)} className="field-ap" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-label2">Bis</label>
          <input type="date" value={bis} onChange={(e) => setBis(e.target.value)} className="field-ap" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-label2">Kunde</label>
          <SearchableSelect
            value={kundeId}
            onChange={setKundeId}
            placeholder="Alle"
            options={(kunden ?? []).map((k) => ({ value: k.id, label: k.name }))}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-label2">Auftrag</label>
          <SearchableSelect
            value={auftragId}
            onChange={setAuftragId}
            placeholder="Alle"
            options={(auftraege ?? []).map((a) => ({ value: a.id, label: a.titel }))}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-label2">Projekt</label>
          <SearchableSelect
            value={projektId}
            onChange={setProjektId}
            placeholder="Alle"
            options={(projekte ?? []).map((p) => ({ value: p.id, label: p.name }))}
          />
        </div>
      </div>

      <div className="card-ap p-3">
        {isLoading ? (
          <p className="text-sm text-label2">Lädt…</p>
        ) : gruppen.length === 0 ? (
          <EmptyState icon={Hourglass} text="Keine Zeiteinträge für diese Filter." />
        ) : (
          <div className="space-y-3">
            {gruppen.map((gruppe) => (
              <div key={gruppe.key}>
                <div className="flex items-center justify-between gap-2 border-b border-sep pb-1.5">
                  <div className="min-w-0">
                    {gruppe.vorgangId ? (
                      <button
                        onClick={() => navigate(`/vorgaenge/${gruppe.vorgangId}`)}
                        className="truncate text-sm font-semibold text-tint hover:underline"
                      >
                        {gruppe.vorgangsnummer ?? "Vorgang"}
                      </button>
                    ) : (
                      <span className="truncate text-sm font-semibold text-label">{gruppe.kategorieLabel}</span>
                    )}
                    {gruppe.kontext && <p className="truncate text-xs text-label2">{gruppe.kontext}</p>}
                  </div>
                  <span className="shrink-0 text-xs font-medium text-label2">
                    {formatSekundenAlsHHMM(gruppenSumme(gruppe))} Std.
                  </span>
                </div>
                <div className="space-y-1 pt-1.5">
                  {gruppe.eintraege.map((e) => {
                    const dauerSekunden = (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000;
                    return (
                      <div key={e.id} className="flex items-center gap-2">
                        {kannZeitAuswaehlen(e) && (
                          <input
                            type="checkbox"
                            checked={ausgewaehlteIds.has(e.id)}
                            onChange={() => zeitCheckboxToggeln(e)}
                            className="btn-touch h-4 w-4 shrink-0"
                          />
                        )}
                        <button
                          onClick={() => setSheetEintrag(e)}
                          className="btn-touch flex min-w-0 flex-1 items-center justify-between gap-2 text-left text-xs text-label2 hover:bg-fill"
                        >
                          <span className="min-w-0 truncate">
                            {users?.find((u) => u.id === e.techniker_id)?.name ?? "—"}
                            {" · "}
                            {e.taetigkeit || "—"}
                            {" · "}
                            {new Date(e.start_at).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin" })}
                          </span>
                          <span className="flex shrink-0 items-center gap-2">
                            <span className="font-medium text-label">
                              {formatSekundenAlsHHMM(dauerSekunden)} Std.
                              {e.km && <span className="ml-1 font-normal text-label2">· {e.km} km</span>}
                            </span>
                            <StatusPille
                              status={buchungsstatusZuToken(e.buchungsstatus)}
                              label={BUCHUNGSSTATUS_LABEL[e.buchungsstatus]}
                            />
                          </span>
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {ausgewaehlteIds.size > 0 && (
          <div className="mt-3 border-t border-sep pt-2">
            {stornierenModus ? (
              <div className="flex items-center gap-2">
                <input
                  autoFocus
                  value={stornierenGrund}
                  onChange={(e) => setStornierenGrund(e.target.value)}
                  placeholder="Grund für die Stornierung"
                  className="field-ap flex-1 text-sm"
                />
                <button
                  onClick={() => stornierenMutation.mutate()}
                  disabled={!stornierenGrund.trim() || stornierenMutation.isPending}
                  className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-xs disabled:opacity-40"
                >
                  Bestätigen
                </button>
                <button
                  onClick={() => setStornierenModus(false)}
                  className="btn-touch shrink-0 px-2 py-1.5 text-xs text-label2"
                >
                  Abbrechen
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-label2">{ausgewaehlteIds.size} ausgewählt</span>
                {ausgewaehlterStatus === "vermerkt" && (
                  <button
                    onClick={() => vormerkenMutation.mutate([...ausgewaehlteIds])}
                    disabled={vormerkenMutation.isPending}
                    className="btn-touch border border-sepstrong px-3 py-1.5 text-xs font-medium text-label hover:bg-fill"
                  >
                    Zur Buchung vormerken
                  </button>
                )}
                {(ausgewaehlterStatus === "vermerkt" || ausgewaehlterStatus === "vorgemerkt") && (
                  <button
                    onClick={handleBuchen}
                    disabled={buchenMutation.isPending}
                    className="btn-touch btn-ap-primary px-3 py-1.5 text-xs"
                  >
                    Buchen
                  </button>
                )}
                {ausgewaehlterStatus === "vorgemerkt" && (
                  <button
                    onClick={() => zurueckziehenMutation.mutate([...ausgewaehlteIds])}
                    disabled={zurueckziehenMutation.isPending}
                    className="btn-touch border border-sepstrong px-3 py-1.5 text-xs font-medium text-label hover:bg-fill"
                  >
                    Zurückziehen
                  </button>
                )}
                {ausgewaehlterStatus === "gebucht" && (
                  <button
                    onClick={() => setStornierenModus(true)}
                    className="btn-touch border border-sepstrong px-3 py-1.5 text-xs font-medium text-label hover:bg-fill"
                  >
                    Buchung stornieren
                  </button>
                )}
                <button
                  onClick={() => setAusgewaehlteIds(new Set())}
                  className="btn-touch px-2 py-1.5 text-xs text-label2"
                >
                  Auswahl aufheben
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="card-ap p-3">
        <h2 className="mb-2 flex items-center gap-1.5 font-heading text-sm font-semibold uppercase tracking-wide text-label">
          <Clock size={15} strokeWidth={2} />
          Laufende Timer
        </h2>
        {!laufendeTimer || laufendeTimer.length === 0 ? (
          <p className="text-sm text-label2">Kein Timer läuft gerade.</p>
        ) : (
          <div className="space-y-1">
            {laufendeTimer.map((t) => {
              const technikerName = users?.find((u) => u.id === t.techniker_id)?.name ?? "—";
              const istFremd = t.techniker_id !== currentUser?.id;
              return (
                <div key={t.id} className="flex items-center justify-between gap-2 border-b border-sep py-2 text-sm last:border-0">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-label">{technikerName}</p>
                    <p className="truncate text-xs text-label2">
                      {t.vorgangsnummer ?? ZEITERFASSUNG_KATEGORIE_LABEL[t.kategorie] ?? t.kategorie}
                      {" · seit "}
                      {formatUhrzeit(t.start_at)}
                    </p>
                  </div>
                  {beendenId === t.id ? (
                    <div className="flex shrink-0 items-center gap-1.5">
                      <input
                        autoFocus
                        value={beendenGrund}
                        onChange={(e) => setBeendenGrund(e.target.value)}
                        placeholder="Grund"
                        className="field-ap w-28 text-xs"
                      />
                      <button
                        onClick={() => stopMutation.mutate({ id: t.id, grund: beendenGrund })}
                        disabled={!beendenGrund.trim() || stopMutation.isPending}
                        className="btn-touch btn-ap-primary px-2 py-1.5 text-xs disabled:opacity-40"
                      >
                        OK
                      </button>
                      <button
                        onClick={() => {
                          setBeendenId(null);
                          setBeendenGrund("");
                        }}
                        className="btn-touch px-1.5 py-1.5 text-xs text-label2"
                      >
                        Abbrechen
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => (istFremd ? setBeendenId(t.id) : stopMutation.mutate({ id: t.id }))}
                      disabled={stopMutation.isPending}
                      className="btn-touch shrink-0 border border-sepstrong px-3 py-1.5 text-xs font-medium text-label hover:bg-fill"
                    >
                      Beenden
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {sheetEintrag && (
        <ZeiteintragSheet
          offen
          onClose={() => setSheetEintrag(null)}
          vorgangId={sheetEintrag.vorgang_id ?? ""}
          eintrag={sheetEintrag}
          onGespeichert={() => queryClient.invalidateQueries({ queryKey: ["zeiterfassung-buchen-liste"] })}
        />
      )}
    </div>
  );
}
