import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ChevronsUpDown, Clock, Hourglass } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { auftraegeApi, kundenApi, projekteApi, usersApi, zeiterfassungApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SearchableSelect } from "../../components/SearchableSelect";
import { ZeiteintragSheet } from "../../components/ZeiteintragSheet";
import { StatusPille } from "../../components/apple/StatusPille";
import { LaeuftPille } from "../../components/apple/LaeuftPille";
import { useAuth } from "../../context/AuthContext";
import type { Zeiterfassung, ZeiterfassungBuchungsstatus } from "../../types";
import { formatSekundenAlsHHMM } from "../../utils/duration";
import {
  BUCHUNGSSTATUS_LABEL,
  ZEITERFASSUNG_KATEGORIE_LABEL,
  buchungsstatusZuToken,
  formatUhrzeit,
} from "../../utils/zeiterfassung";
import {
  alleAuswaehlbarenIds,
  dauerSekunden,
  gruppenBilden,
  gruppenSumme,
  kopfCheckboxZustand,
  sortiereEintraege,
  summeSekunden,
  type ZeitenSortierung,
} from "../../utils/zeitenBuchen";
import { SeitenKopf, TabellenRahmen } from "../../office/OfficeUi";
import { FehlerZustand } from "../../components/FehlerZustand";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { Select } from "../../components/apple/Select";

const BUCHUNGSSTATUS_OPTIONEN: ZeiterfassungBuchungsstatus[] = ["vermerkt", "vorgemerkt", "gebucht", "abgerechnet"];

/** Zentrale Seite fuer Buchungsberechtigte: mandantenweite Sicht auf zur
 * Buchung anstehende Zeiteintraege (Filter + Sammel-Aktionsleiste wie im
 * Zeit-Tab von VorgangDetailPage.tsx, hier ueber alle Vorgaenge hinweg
 * statt nur den aktuellen) plus laufende Timer mit der Moeglichkeit,
 * einen fremden Timer zu beenden (siehe docs/konzepte/ZEITERFASSUNG.md
 * Abschnitt 7.1/7.3, darf_zeiten_buchen in types/index.ts). Reiht sich per
 * navSeiten.ts in Feld-App und Office ein. */
export function ZeitenBuchenPage({ layout = "kompakt" }: { layout?: "kompakt" | "dicht" } = {}) {
  const uid = useId();
  const bestaetigen = useBestaetigung();
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
  const [gruppiert, setGruppiert] = useState(true);
  // Neueste zuerst: im Arbeitsvorrat zaehlt, was zuletzt angefallen ist.
  const [sortierung, setSortierung] = useState<ZeitenSortierung>({ key: "datum", absteigend: true });
  const [aktionsFehler, setAktionsFehler] = useState<string | null>(null);
  const meldeAktionsFehler = (err: unknown) =>
    setAktionsFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.");

  const { data: users } = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl, enabled: darfZeitenBuchen });
  const techniker = (users ?? []).filter((u) => u.nur_zugewiesene_kunden);
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list(), enabled: darfZeitenBuchen });
  const { data: auftraege } = useQuery({ queryKey: ["auftraege"], queryFn: () => auftraegeApi.list(), enabled: darfZeitenBuchen });
  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list(), enabled: darfZeitenBuchen });

  const { data: eintraege, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
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
  const technikerName = (id: string) => users?.find((u) => u.id === id)?.name ?? "—";
  function filterZuruecksetzen() {
    setTechnikerId("");
    setVon("");
    setBis("");
    setKundeId("");
    setAuftragId("");
    setProjektId("");
    setVermerktAelterAlsTage("");
    setBuchungsstatus("vorgemerkt");
  }
  async function handleBuchen() {
    const stunden = formatSekundenAlsHHMM(summeSekunden(ausgewaehlteEintraege));
    if (
      await bestaetigen({ titel: `${ausgewaehlteEintraege.length} Eintrag/Einträge mit insgesamt ${stunden} Std. buchen?`, text: `Gebuchte Einträge kannst du danach nicht mehr ändern.`, bestaetigenLabel: "Buchen", destruktiv: false })
    ) {
      buchenMutation.mutate([...ausgewaehlteIds]);
    }
  }

  const filterBlock = (
    <FilterBlock
      layout={layout}
      uid={uid}
      technikerId={technikerId}
      setTechnikerId={setTechnikerId}
      techniker={techniker}
      buchungsstatus={buchungsstatus}
      setBuchungsstatus={setBuchungsstatus}
      vermerktAelterAlsTage={vermerktAelterAlsTage}
      setVermerktAelterAlsTage={setVermerktAelterAlsTage}
      von={von}
      setVon={setVon}
      bis={bis}
      setBis={setBis}
      kundeId={kundeId}
      setKundeId={setKundeId}
      auftragId={auftragId}
      setAuftragId={setAuftragId}
      projektId={projektId}
      setProjektId={setProjektId}
      kunden={kunden}
      auftraege={auftraege}
      projekte={projekte}
    />
  );

  const aktionsleiste = (
    <SammelAktionen
      anzahl={ausgewaehlteIds.size}
      status={ausgewaehlterStatus}
      stornierenModus={stornierenModus}
      setStornierenModus={setStornierenModus}
      stornierenGrund={stornierenGrund}
      setStornierenGrund={setStornierenGrund}
      onVormerken={() => vormerkenMutation.mutate([...ausgewaehlteIds])}
      vormerkenLaeuft={vormerkenMutation.isPending}
      onBuchen={handleBuchen}
      buchenLaeuft={buchenMutation.isPending}
      onZurueckziehen={() => zurueckziehenMutation.mutate([...ausgewaehlteIds])}
      zurueckziehenLaeuft={zurueckziehenMutation.isPending}
      onStornieren={() => stornierenMutation.mutate()}
      stornierenLaeuft={stornierenMutation.isPending}
      onAufheben={() => setAusgewaehlteIds(new Set())}
    />
  );

  const beendenAktion = (t: Zeiterfassung) => (
    <BeendenAktion
      istFremd={t.techniker_id !== currentUser?.id}
      offen={beendenId === t.id}
      grund={beendenGrund}
      setGrund={setBeendenGrund}
      laeuft={stopMutation.isPending}
      onOeffnen={() => setBeendenId(t.id)}
      onAbbrechen={() => {
        setBeendenId(null);
        setBeendenGrund("");
      }}
      onBeenden={(grund) => stopMutation.mutate({ id: t.id, grund })}
      onDirektBeenden={() => stopMutation.mutate({ id: t.id })}
    />
  );

  const sheet = sheetEintrag && (
    <ZeiteintragSheet
      offen
      onClose={() => setSheetEintrag(null)}
      vorgangId={sheetEintrag.vorgang_id ?? ""}
      eintrag={sheetEintrag}
      onGespeichert={() => queryClient.invalidateQueries({ queryKey: ["zeiterfassung-buchen-liste"] })}
    />
  );

  if (layout === "dicht") {
    const kontextVonId = new Map<string, string | null>();
    for (const g of gruppen) for (const e of g.eintraege) kontextVonId.set(e.id, g.kontext);
    const sichtbarAuswaehlbar = alleAuswaehlbarenIds(buchbareEintraege, ausgewaehlterStatus);
    const kopfZustand = kopfCheckboxZustand(buchbareEintraege, ausgewaehlteIds, ausgewaehlterStatus);
    const sortiertFlach = sortiereEintraege(buchbareEintraege, sortierung, technikerName);
    const umschalten = (key: ZeitenSortierung["key"]) =>
      setSortierung((alt) => (alt.key === key ? { key, absteigend: !alt.absteigend } : { key, absteigend: false }));

    const zeile = (e: Zeiterfassung) => {
      const ausgewaehlt = ausgewaehlteIds.has(e.id);
      const kontext = kontextVonId.get(e.id) ?? null;
      return (
        <tr
          key={e.id}
          onClick={() => setSheetEintrag(e)}
          aria-selected={ausgewaehlt}
          className={`cursor-pointer border-b border-sep ${ausgewaehlt ? "bg-tintbg" : "hover:bg-fill"}`}
        >
          <td className="w-10 px-3 py-2" onClick={(ev) => ev.stopPropagation()}>
            {kannZeitAuswaehlen(e) && (
              <input
                type="checkbox"
                checked={ausgewaehlt}
                onChange={() => zeitCheckboxToggeln(e)}
                aria-label={`Eintrag vom ${new Date(e.start_at).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin" })} auswählen`}
                className="h-4 w-4"
              />
            )}
          </td>
          <td className="whitespace-nowrap px-3 py-2 text-label">
            <button
              onClick={(ev) => {
                ev.stopPropagation();
                setSheetEintrag(e);
              }}
              className="rounded-sm text-left font-semibold text-label"
            >
              {new Date(e.start_at).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin" })}
            </button>
          </td>
          <td className="whitespace-nowrap px-3 py-2 tabular-nums text-label">
            {formatUhrzeit(e.start_at)}–{formatUhrzeit(e.ende_at!)}
          </td>
          <td className="px-3 py-2 text-label">{technikerName(e.techniker_id)}</td>
          <td className="whitespace-nowrap px-3 py-2 text-label">
            {e.vorgang_id ? (
              <button
                onClick={(ev) => {
                  ev.stopPropagation();
                  navigate(`/vorgaenge/${e.vorgang_id}`);
                }}
                className="rounded-sm font-semibold text-tint hover:underline"
              >
                {e.vorgangsnummer ?? "Vorgang"}
              </button>
            ) : (
              (ZEITERFASSUNG_KATEGORIE_LABEL[e.kategorie] ?? e.kategorie)
            )}
          </td>
          <td className="max-w-[220px] truncate px-3 py-2 text-label2" title={kontext ?? undefined}>
            {kontext ?? "—"}
          </td>
          <td className="max-w-[260px] truncate px-3 py-2 text-label" title={e.taetigkeit || undefined}>
            {e.taetigkeit || "—"}
          </td>
          <td className="px-3 py-2 text-right tabular-nums text-label">{formatSekundenAlsHHMM(dauerSekunden(e))}</td>
          <td className="px-3 py-2 text-right tabular-nums text-label">{e.km ? e.km : "–"}</td>
          <td className="px-3 py-2">
            <StatusPille status={buchungsstatusZuToken(e.buchungsstatus)} label={BUCHUNGSSTATUS_LABEL[e.buchungsstatus]} />
          </td>
        </tr>
      );
    };

    const spaltenKopf = (label: string, key?: ZeitenSortierung["key"], rechts = false) => {
      const aktiv = key !== undefined && sortierung.key === key;
      return (
        <th
          scope="col"
          aria-sort={aktiv ? (sortierung.absteigend ? "descending" : "ascending") : undefined}
          className={`px-3 py-2 text-meta font-medium tracking-wide uppercase ${rechts ? "text-right" : "text-left"}`}
        >
          {key ? (
            <button
              onClick={() => umschalten(key)}
              className={`inline-flex items-center gap-1 rounded-sm tracking-wide uppercase hover:text-label ${aktiv ? "text-label" : ""}`}
            >
              {label}
              {aktiv ? (
                sortierung.absteigend ? (
                  <ArrowDown size={12} strokeWidth={2.5} />
                ) : (
                  <ArrowUp size={12} strokeWidth={2.5} />
                )
              ) : (
                <ChevronsUpDown size={12} strokeWidth={2} className="text-label3" />
              )}
            </button>
          ) : (
            label
          )}
        </th>
      );
    };

    return (
      <div className="space-y-4">
        <SeitenKopf titel="Zeiten buchen" anzahl={buchbareEintraege.length}>
          <label className="flex items-center gap-2 text-sekundaer font-medium text-label">
            <input type="checkbox" checked={gruppiert} onChange={(e) => setGruppiert(e.target.checked)} className="h-4 w-4" />
            Nach Vorgang gruppieren
          </label>
          <button
            onClick={filterZuruecksetzen}
            className="border rounded-[var(--radius-ap-md)] border-sepstrong px-3 py-1.5 text-sekundaer font-medium text-label hover:bg-fill"
          >
            Filter zurücksetzen
          </button>
        </SeitenKopf>

        {aktionsFehler && <p className="text-fliess text-st-fehlt">{aktionsFehler}</p>}

        {filterBlock}

        {isLoading ? (
          <div className="card-ap p-3">
            <p className="text-sekundaer text-label2">Lädt…</p>
          </div>
        ) : ladeFehler && !eintraege ? (
          <div className="card-ap p-3">
            <FehlerZustand fehler={ladeFehler} was="Die Zeiten" onErneut={() => void neuLaden()} />
          </div>
        ) : gruppen.length === 0 ? (
          <div className="card-ap p-3">
            <EmptyState icon={Hourglass} text="Keine Zeiteinträge für diese Filter." />
          </div>
        ) : (
          <TabellenRahmen>
            <table className="w-full border-collapse text-fliess">
              <thead className="border-b border-sepstrong text-sekundaer text-label2">
                <tr>
                  <th scope="col" className="w-10 px-3 py-2 text-left">
                    <input
                      type="checkbox"
                      ref={(el) => {
                        if (el) el.indeterminate = kopfZustand === "teilweise";
                      }}
                      checked={kopfZustand === "an"}
                      disabled={sichtbarAuswaehlbar.size === 0}
                      onChange={() =>
                        setAusgewaehlteIds(kopfZustand === "an" ? new Set() : alleAuswaehlbarenIds(buchbareEintraege, ausgewaehlterStatus))
                      }
                      aria-label="Alle sichtbaren Einträge auswählen"
                      className="h-4 w-4"
                    />
                  </th>
                  {spaltenKopf("Datum", "datum")}
                  {spaltenKopf("Zeit")}
                  {spaltenKopf("Techniker", "techniker")}
                  {spaltenKopf("Vorgang", "vorgang")}
                  {spaltenKopf("Kunde / Auftrag / Projekt")}
                  {spaltenKopf("Tätigkeit")}
                  {spaltenKopf("Dauer", "dauer", true)}
                  {spaltenKopf("km", undefined, true)}
                  {spaltenKopf("Status")}
                </tr>
              </thead>
              <tbody>
                {gruppiert
                  ? gruppen.flatMap((gruppe) => [
                      <tr key={`g-${gruppe.key}`} className="border-b border-sep bg-fill">
                        <td colSpan={10} className="px-3 py-1.5">
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex min-w-0 items-center gap-3">
                              {gruppe.vorgangId ? (
                                <button
                                  onClick={() => navigate(`/vorgaenge/${gruppe.vorgangId}`)}
                                  className="shrink-0 rounded-sm text-sekundaer font-semibold text-tint hover:underline"
                                >
                                  {gruppe.vorgangsnummer ?? "Vorgang"}
                                </button>
                              ) : (
                                <span className="shrink-0 text-sekundaer font-semibold text-label">{gruppe.kategorieLabel}</span>
                              )}
                              {gruppe.kontext && (
                                <span className="truncate text-sekundaer text-label2" title={gruppe.kontext}>
                                  {gruppe.kontext}
                                </span>
                              )}
                            </div>
                            <span className="shrink-0 text-sekundaer font-medium tabular-nums text-label2">
                              {formatSekundenAlsHHMM(gruppenSumme(gruppe))} Std.
                            </span>
                          </div>
                        </td>
                      </tr>,
                      ...sortiereEintraege(gruppe.eintraege, sortierung, technikerName).map(zeile),
                    ])
                  : sortiertFlach.map(zeile)}
              </tbody>
              <tfoot className="border-t border-sepstrong text-sekundaer text-label2">
                <tr>
                  <td colSpan={10} className="px-3 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-3 tabular-nums">
                      <span>Summe sichtbar: {formatSekundenAlsHHMM(summeSekunden(buchbareEintraege))} Std.</span>
                      <span>
                        Auswahl: {ausgewaehlteEintraege.length} {ausgewaehlteEintraege.length === 1 ? "Eintrag" : "Einträge"},{" "}
                        {formatSekundenAlsHHMM(summeSekunden(ausgewaehlteEintraege))} Std.
                      </span>
                    </div>
                  </td>
                </tr>
              </tfoot>
            </table>
          </TabellenRahmen>
        )}

        {ausgewaehlteIds.size > 0 && (
          <div className="card-ap sticky bottom-0 z-10 p-3 shadow-[0_-2px_10px_rgba(0,0,0,.14)]">{aktionsleiste}</div>
        )}

        <div className="card-ap p-3">
          <h2 className="mb-2 flex items-center gap-1.5 font-heading text-fliess font-semibold text-label">
            <Clock size={15} strokeWidth={2} />
            Laufende Timer
          </h2>
          {!laufendeTimer || laufendeTimer.length === 0 ? (
            <p className="text-sekundaer text-label2">Kein Timer läuft gerade.</p>
          ) : (
            <TimerTabelle timer={laufendeTimer} technikerName={technikerName} beendenAktion={beendenAktion} />
          )}
        </div>

        {sheet}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="flex items-center gap-2 text-titel-mobil font-bold text-label">
        <Hourglass size={19} strokeWidth={2} className="text-tint" />
        Zeiten buchen
      </h1>

      {aktionsFehler && <p className="text-fliess text-st-fehlt">{aktionsFehler}</p>}

      {filterBlock}

      <div className="card-ap p-3">
        {isLoading ? (
          <p className="text-sekundaer text-label2">Lädt…</p>
        ) : ladeFehler && !eintraege ? (
          <FehlerZustand fehler={ladeFehler} was="Die Zeiten" onErneut={() => void neuLaden()} />
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
                        className="truncate text-sekundaer font-semibold text-tint hover:underline"
                      >
                        {gruppe.vorgangsnummer ?? "Vorgang"}
                      </button>
                    ) : (
                      <span className="truncate text-fliess font-semibold text-label">{gruppe.kategorieLabel}</span>
                    )}
                    {gruppe.kontext && <p className="truncate text-sekundaer text-label2">{gruppe.kontext}</p>}
                  </div>
                  <span className="shrink-0 text-sekundaer font-medium text-label2">
                    {formatSekundenAlsHHMM(gruppenSumme(gruppe))} Std.
                  </span>
                </div>
                <div className="space-y-1 pt-1.5">
                  {gruppe.eintraege.map((e) => {
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
                          className="btn-touch flex min-w-0 flex-1 items-center justify-between gap-2 text-left text-sekundaer text-label2 hover:bg-fill"
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
                              {formatSekundenAlsHHMM(dauerSekunden(e))} Std.
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

        {ausgewaehlteIds.size > 0 && <div className="mt-3 border-t border-sep pt-2">{aktionsleiste}</div>}
      </div>

      <div className="card-ap p-3">
        <h2 className="mb-2 flex items-center gap-1.5 font-heading text-fliess font-semibold text-label">
          <Clock size={15} strokeWidth={2} />
          Laufende Timer
        </h2>
        {!laufendeTimer || laufendeTimer.length === 0 ? (
          <p className="text-sekundaer text-label2">Kein Timer läuft gerade.</p>
        ) : (
          <div className="space-y-1">
            {laufendeTimer.map((t) => (
              <div key={t.id} className="flex items-center justify-between gap-2 border-b border-sep py-2 text-fliess last:border-0">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 truncate font-medium text-label">
                    {technikerName(t.techniker_id)}
                    <LaeuftPille />
                  </p>
                  <p className="truncate text-meta text-label2">
                    {t.vorgangsnummer ?? ZEITERFASSUNG_KATEGORIE_LABEL[t.kategorie] ?? t.kategorie}
                    {" · seit "}
                    {formatUhrzeit(t.start_at)}
                  </p>
                </div>
                {beendenAktion(t)}
              </div>
            ))}
          </div>
        )}
      </div>

      {sheet}
    </div>
  );
}

type FilterProps = {
  layout: "kompakt" | "dicht";
  uid: string;
  technikerId: string;
  setTechnikerId: (v: string) => void;
  techniker: { id: string; name: string }[];
  buchungsstatus: ZeiterfassungBuchungsstatus | "";
  setBuchungsstatus: (v: ZeiterfassungBuchungsstatus | "") => void;
  vermerktAelterAlsTage: string;
  setVermerktAelterAlsTage: (v: string) => void;
  von: string;
  setVon: (v: string) => void;
  bis: string;
  setBis: (v: string) => void;
  kundeId: string;
  setKundeId: (v: string) => void;
  auftragId: string;
  setAuftragId: (v: string) => void;
  projektId: string;
  setProjektId: (v: string) => void;
  kunden: { id: string; name: string }[] | undefined;
  auftraege: { id: string; titel: string }[] | undefined;
  projekte: { id: string; name: string }[] | undefined;
};

function FilterFeld({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sekundaer font-medium text-label2">{label}</label>
      {children}
    </div>
  );
}

function FilterBlock(p: FilterProps) {
  const { uid } = p;
  const felder: Record<string, ReactNode> = {
    techniker: (
      <FilterFeld key="techniker" id={`${uid}-0`} label="Techniker">
        <Select id={`${uid}-0`} value={p.technikerId} onChange={(e) => p.setTechnikerId(e.target.value)}>
          <option value="">Alle</option>
          {p.techniker.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      </FilterFeld>
    ),
    status: (
      <FilterFeld key="status" id={`${uid}-1`} label="Status">
        <Select id={`${uid}-1`}
          value={p.buchungsstatus}
          onChange={(e) => p.setBuchungsstatus(e.target.value as ZeiterfassungBuchungsstatus | "")}
        >
          <option value="">Alle</option>
          {BUCHUNGSSTATUS_OPTIONEN.map((s) => (
            <option key={s} value={s}>
              {BUCHUNGSSTATUS_LABEL[s]}
            </option>
          ))}
        </Select>
      </FilterFeld>
    ),
    aelter: (
      <FilterFeld key="aelter" id={`${uid}-2`} label="Vermerkt älter als (Tage)">
        <input id={`${uid}-2`}
          type="number"
          min="0"
          inputMode="numeric"
          value={p.vermerktAelterAlsTage}
          onChange={(e) => p.setVermerktAelterAlsTage(e.target.value)}
          placeholder="z. B. 3"
          className="field-ap"
        />
      </FilterFeld>
    ),
    von: (
      <FilterFeld key="von" id={`${uid}-3`} label="Von">
        <input id={`${uid}-3`} type="date" value={p.von} onChange={(e) => p.setVon(e.target.value)} className="field-ap" />
      </FilterFeld>
    ),
    bis: (
      <FilterFeld key="bis" id={`${uid}-4`} label="Bis">
        <input id={`${uid}-4`} type="date" value={p.bis} onChange={(e) => p.setBis(e.target.value)} className="field-ap" />
      </FilterFeld>
    ),
    kunde: (
      <FilterFeld key="kunde" id={`${uid}-5`} label="Kunde">
        <SearchableSelect id={`${uid}-5`}
          value={p.kundeId}
          onChange={p.setKundeId}
          placeholder="Alle"
          options={(p.kunden ?? []).map((k) => ({ value: k.id, label: k.name }))}
        />
      </FilterFeld>
    ),
    auftrag: (
      <FilterFeld key="auftrag" id={`${uid}-6`} label="Auftrag">
        <SearchableSelect id={`${uid}-6`}
          value={p.auftragId}
          onChange={p.setAuftragId}
          placeholder="Alle"
          options={(p.auftraege ?? []).map((a) => ({ value: a.id, label: a.titel }))}
        />
      </FilterFeld>
    ),
    projekt: (
      <FilterFeld key="projekt" id={`${uid}-7`} label="Projekt">
        <SearchableSelect id={`${uid}-7`}
          value={p.projektId}
          onChange={p.setProjektId}
          placeholder="Alle"
          options={(p.projekte ?? []).map((pr) => ({ value: pr.id, label: pr.name }))}
        />
      </FilterFeld>
    ),
  };
  const dicht = p.layout === "dicht";
  const reihenfolge = dicht
    ? ["techniker", "status", "von", "bis", "kunde", "auftrag", "projekt", "aelter"]
    : ["techniker", "status", "aelter", "von", "bis", "kunde", "auftrag", "projekt"];
  return (
    <div
      className={
        dicht
          ? "card-ap grid grid-cols-4 gap-3 p-3 xl:grid-cols-8"
          : "card-ap grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 lg:grid-cols-3"
      }
    >
      {reihenfolge.map((k) => felder[k])}
    </div>
  );
}

function SammelAktionen(p: {
  anzahl: number;
  status: ZeiterfassungBuchungsstatus | null;
  stornierenModus: boolean;
  setStornierenModus: (v: boolean) => void;
  stornierenGrund: string;
  setStornierenGrund: (v: string) => void;
  onVormerken: () => void;
  vormerkenLaeuft: boolean;
  onBuchen: () => void;
  buchenLaeuft: boolean;
  onZurueckziehen: () => void;
  zurueckziehenLaeuft: boolean;
  onStornieren: () => void;
  stornierenLaeuft: boolean;
  onAufheben: () => void;
}) {
  if (p.stornierenModus) {
    return (
      <div className="flex items-center gap-2">
        <input
          autoFocus
          value={p.stornierenGrund}
          onChange={(e) => p.setStornierenGrund(e.target.value)}
          placeholder="Grund für die Stornierung"
          className="field-ap flex-1 text-zeile"
        />
        <button
          onClick={p.onStornieren}
          disabled={!p.stornierenGrund.trim() || p.stornierenLaeuft}
          className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-sekundaer disabled:opacity-40"
        >
          Bestätigen
        </button>
        <button
          onClick={() => p.setStornierenModus(false)}
          className="btn-touch shrink-0 px-2 py-1.5 text-sekundaer text-label2"
        >
          Abbrechen
        </button>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sekundaer text-label2">{p.anzahl} ausgewählt</span>
      {p.status === "vermerkt" && (
        <button
          onClick={p.onVormerken}
          disabled={p.vormerkenLaeuft}
          className="btn-touch border rounded-[var(--radius-ap-md)] border-sepstrong px-3 py-1.5 text-sekundaer font-medium text-label hover:bg-fill"
        >
          Zur Buchung vormerken
        </button>
      )}
      {(p.status === "vermerkt" || p.status === "vorgemerkt") && (
        <button
          onClick={p.onBuchen}
          disabled={p.buchenLaeuft}
          className="btn-touch btn-ap-primary px-3 py-1.5 text-sekundaer"
        >
          Buchen
        </button>
      )}
      {p.status === "vorgemerkt" && (
        <button
          onClick={p.onZurueckziehen}
          disabled={p.zurueckziehenLaeuft}
          className="btn-touch border rounded-[var(--radius-ap-md)] border-sepstrong px-3 py-1.5 text-sekundaer font-medium text-label hover:bg-fill"
        >
          Zurückziehen
        </button>
      )}
      {p.status === "gebucht" && (
        <button
          onClick={() => p.setStornierenModus(true)}
          className="btn-touch border rounded-[var(--radius-ap-md)] border-sepstrong px-3 py-1.5 text-sekundaer font-medium text-label hover:bg-fill"
        >
          Buchung stornieren
        </button>
      )}
      <button onClick={p.onAufheben} className="btn-touch px-2 py-1.5 text-sekundaer text-label2">
        Auswahl aufheben
      </button>
    </div>
  );
}

function BeendenAktion(p: {
  istFremd: boolean;
  offen: boolean;
  grund: string;
  setGrund: (v: string) => void;
  laeuft: boolean;
  onOeffnen: () => void;
  onAbbrechen: () => void;
  onBeenden: (grund: string) => void;
  onDirektBeenden: () => void;
}) {
  if (p.offen) {
    return (
      <div className="flex shrink-0 items-center gap-1.5">
        <input
          autoFocus
          value={p.grund}
          onChange={(e) => p.setGrund(e.target.value)}
          placeholder="Grund"
          className="field-ap w-28 text-sekundaer"
        />
        <button
          onClick={() => p.onBeenden(p.grund)}
          disabled={!p.grund.trim() || p.laeuft}
          className="btn-touch btn-ap-primary px-2 py-1.5 text-sekundaer disabled:opacity-40"
        >
          OK
        </button>
        <button onClick={p.onAbbrechen} className="btn-touch px-1.5 py-1.5 text-sekundaer text-label2">
          Abbrechen
        </button>
      </div>
    );
  }
  return (
    <button
      onClick={() => (p.istFremd ? p.onOeffnen() : p.onDirektBeenden())}
      disabled={p.laeuft}
      className="btn-touch shrink-0 border rounded-[var(--radius-ap-md)] border-sepstrong px-3 py-1.5 text-sekundaer font-medium text-label hover:bg-fill"
    >
      Beenden
    </button>
  );
}

function TimerTabelle({
  timer,
  technikerName,
  beendenAktion,
}: {
  timer: Zeiterfassung[];
  technikerName: (id: string) => string;
  beendenAktion: (t: Zeiterfassung) => ReactNode;
}) {
  // Laufzeit ohne eigene Abfrage mitlaufen lassen; Minutenanzeige braucht nur grobe Takte.
  const [jetzt, setJetzt] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setJetzt(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-fliess">
        <thead className="border-b border-sepstrong text-sekundaer text-label2">
          <tr>
            <th scope="col" className="px-3 py-2 text-left text-meta font-medium tracking-wide uppercase">Techniker</th>
            <th scope="col" className="px-3 py-2 text-left text-meta font-medium tracking-wide uppercase">Vorgang</th>
            <th scope="col" className="px-3 py-2 text-left text-meta font-medium tracking-wide uppercase">Seit</th>
            <th scope="col" className="px-3 py-2 text-right text-meta font-medium tracking-wide uppercase">Laufzeit</th>
            <th scope="col" className="px-3 py-2 text-right"><span className="sr-only">Aktion</span></th>
          </tr>
        </thead>
        <tbody>
          {timer.map((t) => (
            <tr key={t.id} className="border-b border-sep last:border-b-0">
              <td className="px-3 py-2 text-label">
                <span className="flex items-center gap-2 font-medium">
                  {technikerName(t.techniker_id)}
                  <LaeuftPille />
                </span>
              </td>
              <td className="px-3 py-2 text-label">
                {t.vorgangsnummer ?? ZEITERFASSUNG_KATEGORIE_LABEL[t.kategorie] ?? t.kategorie}
              </td>
              <td className="px-3 py-2 tabular-nums text-label">{formatUhrzeit(t.start_at)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-label">
                {formatSekundenAlsHHMM(Math.max(0, (jetzt - new Date(t.start_at).getTime()) / 1000))}
              </td>
              <td className="px-3 py-2">
                <div className="flex justify-end">{beendenAktion(t)}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
