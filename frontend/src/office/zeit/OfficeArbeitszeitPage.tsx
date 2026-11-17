import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Lock,
  Plus,
  SlidersHorizontal,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api/client";
import { abwesenheitenApi, arbeitszeitApi, zeiterfassungApi } from "../../api/endpoints";
import { StatusPille } from "../../components/apple/StatusPille";
import { LaeuftPille } from "../../components/apple/LaeuftPille";
import { AktionsMenue, type AktionsMenueEintrag } from "../../components/AktionsMenue";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import { ZeiterfassungManuellForm } from "../../components/ZeiterfassungManuellForm";
import { ZeiteintragSheet } from "../../components/ZeiteintragSheet";
import { useAuth } from "../../context/AuthContext";
import { TeamKennzahlen } from "../../pages/feld/StatistikPage";
import type { Zeiterfassung } from "../../types";
import { ABWESENHEIT_ART_LABEL, formatTage, kontoHinweis, resturlaubHinweis } from "../../utils/abwesenheit";
import {
  ARBEITSZEIT_KACHELN,
  type ArbeitszeitKachelId,
  kachelAuswahlAusSpeicher,
  kachelAuswahlFuerSpeicher,
  kachelSpeicherKey,
  kachelUmschalten,
  sichtbareKacheln,
  standardKacheln,
} from "../../utils/arbeitszeitKacheln";
import {
  SALDO_TON_KLASSE,
  formatSaldo,
  parseStunden,
  saldoBis,
  saldoTageNachDatum,
  saldoTon,
} from "../../utils/arbeitszeit";
import { formatStundenAlsHHMM } from "../../utils/duration";
import { istModulAktiv } from "../../utils/module";
import {
  BUCHUNGSSTATUS_LABEL,
  ZEITERFASSUNG_KATEGORIE_LABEL,
  arbeitsstunden,
  buchungsstatusGesperrt,
  buchungsstatusZuToken,
  eintraegeJeTag,
  formatDauer,
  formatUhrzeit,
  monatsGrenzen,
  tageDesMonats,
  toDateInput,
} from "../../utils/zeiterfassung";
import { Karte, SeitenKopf } from "../OfficeUi";
import { AbwesenheitSheet } from "./AbwesenheitSheet";
import { AbwesenheitZeile } from "./AbwesenheitUi";
import { KpiKachel, type KpiKachelProps } from "./KpiKachel";

const WOCHENTAG_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

export function OfficeArbeitszeitPage() {
  const { currentUser, hatRecht } = useAuth();
  const kannErfassen = istModulAktiv(currentUser, "zeiterfassung");
  const kannAuswerten = istModulAktiv(currentUser, "statistik");

  const heute = new Date();
  const heuteTag = toDateInput(heute);
  const [jahr, setJahr] = useState(heute.getFullYear());
  const [monat0, setMonat0] = useState(heute.getMonth());
  const [offeneTage, setOffeneTage] = useState<Set<string>>(() => new Set([heuteTag]));
  const [neuAm, setNeuAm] = useState<string | null>(null);
  const [bearbeitet, setBearbeitet] = useState<Zeiterfassung | null>(null);
  const [abwesenheitAm, setAbwesenheitAm] = useState<string | null>(null);
  const [abwesenheitFehler, setAbwesenheitFehler] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { von, bis } = monatsGrenzen(jahr, monat0);
  const tage = useMemo(() => tageDesMonats(jahr, monat0), [jahr, monat0]);

  const { data: statistik, refetch: statistikNeuLaden } = useQuery({
    queryKey: ["zeiterfassung-statistik", currentUser?.id],
    queryFn: () => zeiterfassungApi.statistik(),
    enabled: kannAuswerten,
  });

  const { data: eintraege, isLoading: monatLaedt, error: monatFehler, refetch: monatNeuLaden } = useQuery({
    queryKey: ["zeiterfassung-monat", currentUser?.id, von],
    queryFn: () => zeiterfassungApi.listFuerZeitraum({ techniker_id: currentUser!.id, von, bis }),
    enabled: kannErfassen,
  });

  // Saldo nur bis heute: Zukunftstage haben Soll, aber noch kein Ist.
  const saldoBisTag = saldoBis(von, bis, heuteTag);
  const jahresStart = `${heute.getFullYear()}-01-01`;
  // Fehler/403 bewusst nicht weiterreichen: die Seite funktioniert ohne Saldo.
  const { data: monatsSaldo } = useQuery({
    queryKey: ["arbeitszeit-saldo", currentUser?.id, von, saldoBisTag],
    queryFn: () => arbeitszeitApi.saldo({ von, bis: saldoBisTag!, user_id: currentUser!.id }),
    enabled: kannErfassen && !!currentUser && saldoBisTag !== null,
    retry: false,
  });
  const { data: jahresSaldo } = useQuery({
    queryKey: ["arbeitszeit-saldo", currentUser?.id, jahresStart, heuteTag],
    queryFn: () => arbeitszeitApi.saldo({ von: jahresStart, bis: heuteTag, user_id: currentUser!.id }),
    enabled: kannErfassen && !!currentUser,
    retry: false,
  });
  const saldoJeTag = useMemo(() => saldoTageNachDatum(monatsSaldo?.tage ?? []), [monatsSaldo]);
  const hatSoll = parseStunden(jahresSaldo?.soll_stunden) > 0 || parseStunden(monatsSaldo?.soll_stunden) > 0;
  const keinSoll = !!jahresSaldo && !hatSoll;

  // Feiertagsname je Datum; Saldo-Tage tragen nur das Flag.
  const { data: feiertage } = useQuery({
    queryKey: ["arbeitszeit-feiertage", jahr],
    queryFn: () => arbeitszeitApi.feiertage(jahr),
    enabled: kannErfassen && hatSoll,
    retry: false,
  });
  const feiertagsName = useMemo(
    () => new Map((feiertage ?? []).map((f) => [f.datum, f.bezeichnung])),
    [feiertage],
  );

  const { data: meineAbwesenheiten } = useQuery({
    queryKey: ["abwesenheiten", "eigene", currentUser?.id, von],
    queryFn: () => abwesenheitenApi.liste({ von, bis }),
    enabled: kannErfassen && !!currentUser,
    retry: false,
  });
  const { data: konto } = useQuery({
    queryKey: ["abwesenheiten", "konto", currentUser?.id, jahr],
    queryFn: () => abwesenheitenApi.konto({ jahr }),
    enabled: kannErfassen && !!currentUser,
    retry: false,
  });
  const zurueckziehen = useMutation({
    mutationFn: (id: string) => abwesenheitenApi.zurueckziehen(id),
    onSuccess: () => {
      setAbwesenheitFehler(null);
      void queryClient.invalidateQueries({ queryKey: ["abwesenheiten"] });
      void queryClient.invalidateQueries({ queryKey: ["arbeitszeit-saldo"] });
      neuLaden();
    },
    onError: (err) => setAbwesenheitFehler(err instanceof ApiError ? err.message : "Fehler"),
  });
  const darfVerwalten = !!currentUser?.darf_abwesenheiten_verwalten;

  const jeTag = useMemo(() => eintraegeJeTag(eintraege ?? []), [eintraege]);
  const monatssumme = arbeitsstunden(eintraege ?? []);

  if (!kannErfassen && !kannAuswerten) {
    return <EmptyState icon={Clock} text="Diese Funktion ist für deinen Account nicht freigeschaltet." />;
  }

  function monatWechseln(delta: number) {
    const d = new Date(jahr, monat0 + delta, 1);
    setJahr(d.getFullYear());
    setMonat0(d.getMonth());
  }

  function toggle(tag: string) {
    setOffeneTage((vorher) => {
      const neu = new Set(vorher);
      if (neu.has(tag)) neu.delete(tag);
      else neu.add(tag);
      return neu;
    });
  }

  function neuLaden() {
    void monatNeuLaden();
    void statistikNeuLaden();
  }

  const [auswahl, setAuswahl] = useState<Set<ArbeitszeitKachelId>>(() => {
    try {
      return kachelAuswahlAusSpeicher(localStorage.getItem(kachelSpeicherKey(currentUser?.id)));
    } catch {
      return standardKacheln();
    }
  });
  function kachelSchalten(id: ArbeitszeitKachelId) {
    const neu = kachelUmschalten(auswahl, id);
    setAuswahl(neu);
    try {
      localStorage.setItem(kachelSpeicherKey(currentUser?.id), kachelAuswahlFuerSpeicher(neu));
    } catch {
      // Speicher gesperrt (privater Modus): Auswahl gilt nur für diese Sitzung.
    }
  }
  const kachelMenue: AktionsMenueEintrag[] = ARBEITSZEIT_KACHELN.map((k) => ({
    label: `${k.gruppe}: ${k.label}`,
    aktiv: auswahl.has(k.id),
    onClick: () => kachelSchalten(k.id),
  }));

  const statistikSichtbar = kannAuswerten && !!statistik;
  const std = (v: number) => `${formatStundenAlsHHMM(v)} Std.`;
  const saldoWert = (s: typeof monatsSaldo) => (s ? formatSaldo(s.saldo_stunden) : "—");
  const saldoKlasse = (s: typeof monatsSaldo) => (s ? SALDO_TON_KLASSE[saldoTon(s.saldo_stunden)] : "text-label");
  const urlaubInfo = konto ? kontoHinweis(konto) : null;
  const kacheln: Partial<Record<ArbeitszeitKachelId, KpiKachelProps>> = {};
  if (kannErfassen) {
    kacheln.ist_monat = { label: "Ist (Monat)", wert: std(monatssumme), icon: Clock };
    if (hatSoll) {
      kacheln.soll_monat = {
        label: "Soll (Monat)",
        wert: monatsSaldo ? std(parseStunden(monatsSaldo.soll_stunden)) : "—",
      };
      kacheln.saldo_monat = {
        label: "Saldo (Monat)",
        wert: saldoWert(monatsSaldo),
        wertKlasse: saldoKlasse(monatsSaldo),
        zusatz: saldoBisTag && saldoBisTag < bis ? "bis heute" : undefined,
      };
      kacheln.saldo_jahr = {
        label: "Saldo Jahr",
        wert: saldoWert(jahresSaldo),
        wertKlasse: saldoKlasse(jahresSaldo),
        zusatz: "bis heute",
      };
    }
    if (konto) {
      kacheln.urlaub_verbleibend = {
        label: "Urlaub verbleibend",
        wert: formatTage(konto.verbleibend),
        zusatz: urlaubInfo?.ueberzogen ? "überzogen" : "Tage",
        wertKlasse: urlaubInfo?.ueberzogen ? "text-st-fehlt" : "text-label",
      };
      kacheln.urlaub_beantragt = { label: "Urlaub beantragt", wert: formatTage(konto.beantragt), zusatz: "Tage, offen" };
      kacheln.urlaub_resturlaub = { label: "Resturlaub", wert: formatTage(konto.resturlaub), zusatz: resturlaubHinweis(konto) ?? "Tage" };
      kacheln.urlaub_genommen = { label: "Urlaub genommen", wert: formatTage(konto.genommen), zusatz: "Tage, genehmigt" };
      kacheln.urlaub_anspruch = { label: "Urlaubsanspruch", wert: formatTage(konto.anspruch), zusatz: "Tage" };
    }
  }
  if (statistikSichtbar) {
    kacheln.woche = { label: "Diese Woche", wert: std(Number(statistik!.wochenstunden)) };
    kacheln.monat_laufend = { label: "Laufender Monat", wert: std(Number(statistik!.monatsstunden)) };
    kacheln.jahr = { label: "Dieses Jahr", wert: std(Number(statistik!.jahresstunden)) };
  }
  const sichtbar = sichtbareKacheln(auswahl, new Set(Object.keys(kacheln) as ArbeitszeitKachelId[]));
  const urlaubHinweis = konto && sichtbar.some((id) => id.startsWith("urlaub_")) ? urlaubInfo?.text : null;
  const teamSichtbar = kannAuswerten && hatRecht("statistik", "sehen") && auswahl.has("team");
  const abwesenheitenSichtbar = kannErfassen && !!meineAbwesenheiten && meineAbwesenheiten.length > 0;

  const monatsName = new Date(jahr, monat0, 1).toLocaleDateString("de-DE", { month: "long", year: "numeric" });

  return (
    <div>
      <SeitenKopf titel="Arbeitszeit">
        <div className="flex items-center gap-1 rounded-[var(--radius-ap-sm)] bg-fill p-0.5">
          <button type="button" onClick={() => monatWechseln(-1)} aria-label="Vorheriger Monat" className="btn-ap-toolbar">
            <ChevronLeft size={16} strokeWidth={2} />
          </button>
          <span className="min-w-32 text-center text-sekundaer font-semibold text-label">{monatsName}</span>
          <button type="button" onClick={() => monatWechseln(1)} aria-label="Nächster Monat" className="btn-ap-toolbar">
            <ChevronRight size={16} strokeWidth={2} />
          </button>
        </div>
        <button
          type="button"
          onClick={() => {
            setJahr(heute.getFullYear());
            setMonat0(heute.getMonth());
          }}
          className="btn-ap px-3 py-1.5"
        >
          Heute
        </button>
        {kannErfassen && darfVerwalten && (
          <Link to="/abwesenheiten" className="btn-ap inline-flex items-center gap-1 px-3 py-1.5">
            <CalendarCheck size={14} strokeWidth={2} aria-hidden="true" /> Abwesenheiten
          </Link>
        )}
        <AktionsMenue
          label="Kacheln anpassen"
          richtung="unten"
          ausloeser={() => (
            <span className="btn-ap inline-flex items-center gap-1 px-3 py-1.5">
              <SlidersHorizontal size={14} strokeWidth={2} aria-hidden="true" /> Kacheln
            </span>
          )}
          eintraege={kachelMenue}
        />
        {kannErfassen && (
          <button type="button" onClick={() => setAbwesenheitAm(heuteTag)} className="btn-ap btn-ap-primary px-3 py-1.5">
            Abwesenheit beantragen
          </button>
        )}
      </SeitenKopf>

      {sichtbar.length > 0 && (
        <div className="mb-4 grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2">
          {sichtbar.map((id) => {
            const k = kacheln[id];
            return k ? <KpiKachel key={id} {...k} /> : null;
          })}
        </div>
      )}
      {kannErfassen && urlaubHinweis && (
        <p role="alert" className="mb-4 flex items-center gap-1.5 text-fliess font-medium text-st-fehlt">
          <AlertTriangle size={15} strokeWidth={2} aria-hidden="true" />
          {urlaubHinweis}
        </p>
      )}
      {kannErfassen && keinSoll && (
        <p className="mb-4 text-sekundaer text-label2">
          Keine Soll-Zeit hinterlegt.
          {currentUser?.darf_abwesenheiten_verwalten && (
            <>
              {" "}
              <Link to="/einstellungen/arbeitszeit" className="font-medium text-tint-text hover:underline">
                Soll-Zeit in den Einstellungen anlegen
              </Link>
            </>
          )}
        </p>
      )}

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-4">
      {kannErfassen && monatLaedt && <SkeletonList count={5} />}
      {kannErfassen && monatFehler && (
        <FehlerZustand fehler={monatFehler} was="Die Zeiteinträge" onErneut={() => void monatNeuLaden()} />
      )}
      {kannErfassen && !monatLaedt && !monatFehler && (
        <Karte className="space-y-1 p-2">
          {tage.map((t) => {
            const tagesEintraege = jeTag.get(t.tag) ?? [];
            const offen = offeneTage.has(t.tag);
            const istHeute = t.tag === heuteTag;
            const flaeche = istHeute ? "bg-tintbg" : t.istWochenende ? "bg-fill" : "";
            const saldoTag = hatSoll ? saldoJeTag.get(t.tag) : undefined;
            const hatSollTag = !!saldoTag && parseStunden(saldoTag.soll) > 0;
            const textFarbe = t.istWochenende && !istHeute ? "text-label2" : "text-label";
            return (
              <div key={t.tag} className={`rounded-[var(--radius-ap-md)] ${flaeche}`}>
                <button
                  type="button"
                  onClick={() => toggle(t.tag)}
                  aria-expanded={offen}
                  className={`flex w-full items-center gap-3 px-3 py-2 text-left text-sekundaer ${textFarbe}`}
                >
                  {offen ? <ChevronDown size={15} strokeWidth={2} /> : <ChevronRight size={15} strokeWidth={2} />}
                  <span className="w-7 font-semibold">{WOCHENTAG_KURZ[t.wochentag]}</span>
                  <span className="w-14 tabular-nums">
                    {String(t.tagNr).padStart(2, "0")}.{String(monat0 + 1).padStart(2, "0")}.
                  </span>
                  <span className="flex flex-1 flex-wrap items-center gap-2 text-sekundaer text-label2">
                    {tagesEintraege.length > 0 &&
                      `${tagesEintraege.length} ${tagesEintraege.length === 1 ? "Eintrag" : "Einträge"}`}
                    {saldoTag?.feiertag && (
                      <span className="rounded-full bg-st-wartet-bg px-2 py-0.5 font-medium text-st-wartet">
                        {feiertagsName.get(t.tag) ?? "Feiertag"}
                      </span>
                    )}
                    {saldoTag?.abwesenheit && (
                      <span className="rounded-full bg-st-neu-bg px-2 py-0.5 font-medium text-st-neu">
                        {ABWESENHEIT_ART_LABEL[saldoTag.abwesenheit]}
                      </span>
                    )}
                  </span>
                  {saldoTag && (hatSollTag || saldoTag.feiertag || saldoTag.abwesenheit) && (
                    <>
                      <span className="w-24 text-right text-sekundaer tabular-nums text-label2">
                        {hatSollTag ? `Soll ${formatStundenAlsHHMM(parseStunden(saldoTag.soll))}` : ""}
                      </span>
                      <span
                        className={`w-16 text-right text-sekundaer font-medium tabular-nums ${SALDO_TON_KLASSE[saldoTon(saldoTag.saldo)]}`}
                      >
                        {hatSollTag || saldoTon(saldoTag.saldo) !== "null" ? formatSaldo(saldoTag.saldo) : ""}
                      </span>
                    </>
                  )}
                  <span className="font-medium tabular-nums">
                    {tagesEintraege.length > 0 ? `${formatStundenAlsHHMM(arbeitsstunden(tagesEintraege))} Std.` : "—"}
                  </span>
                </button>

                {offen && (
                  <div className="px-3 pb-3">
                    {tagesEintraege.length > 0 && (
                      <table className="w-full text-fliess">
                        <thead>
                          <tr className="text-left text-sekundaer text-label2">
                            <th className="py-1 pr-3 font-medium">Von–Bis</th>
                            <th className="py-1 pr-3 text-right font-medium">Dauer</th>
                            <th className="py-1 pr-3 font-medium">Vorgang / Kategorie</th>
                            <th className="py-1 pr-3 font-medium">Tätigkeit</th>
                            <th className="py-1 font-medium">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tagesEintraege.map((e) => (
                            <tr
                              key={e.id}
                              onClick={e.abwesenheit_id ? undefined : () => setBearbeitet(e)}
                              className={e.abwesenheit_id ? "" : "cursor-pointer hover:bg-fill"}
                            >
                              <td className="py-1.5 pr-3 tabular-nums">
                                {e.abwesenheit_id ? (
                                  <span>
                                    {formatUhrzeit(e.start_at)}–{e.ende_at ? formatUhrzeit(e.ende_at) : <LaeuftPille className="align-middle" />}
                                  </span>
                                ) : (
                                  <button
                                    type="button"
                                    onClick={(ev) => {
                                      ev.stopPropagation();
                                      setBearbeitet(e);
                                    }}
                                    className="text-tint-text"
                                  >
                                    {formatUhrzeit(e.start_at)}–{e.ende_at ? formatUhrzeit(e.ende_at) : <LaeuftPille className="align-middle" />}
                                  </button>
                                )}
                              </td>
                              <td className="py-1.5 pr-3 text-right tabular-nums text-label">
                                {formatStundenAlsHHMM(formatDauer(e.start_at, e.ende_at))}
                              </td>
                              <td className="py-1.5 pr-3 text-label">
                                {e.vorgang_id && e.vorgangsnummer ? (
                                  <Link
                                    to={`/vorgaenge/${e.vorgang_id}`}
                                    onClick={(ev) => ev.stopPropagation()}
                                    className="font-medium text-tint-text"
                                  >
                                    {e.vorgangsnummer}
                                  </Link>
                                ) : (
                                  (ZEITERFASSUNG_KATEGORIE_LABEL[e.kategorie] ?? e.kategorie)
                                )}
                              </td>
                              <td className="max-w-xs truncate py-1.5 pr-3 text-label2">
                                {e.abwesenheit_id ? "aus Abwesenheitsantrag" : (e.taetigkeit ?? "—")}
                              </td>
                              <td className="py-1.5">
                                <span className="inline-flex items-center gap-1">
                                  <StatusPille
                                    status={buchungsstatusZuToken(e.buchungsstatus)}
                                    label={BUCHUNGSSTATUS_LABEL[e.buchungsstatus]}
                                  />
                                  {buchungsstatusGesperrt(e.buchungsstatus) && (
                                    <Lock size={12} strokeWidth={2} className="text-label2" aria-hidden="true" />
                                  )}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                    <div className="mt-2 flex flex-wrap gap-4">
                      <button
                        type="button"
                        onClick={() => setNeuAm(t.tag)}
                        className="inline-flex items-center gap-1 text-sekundaer font-medium text-tint-text"
                      >
                        <Plus size={14} strokeWidth={2} /> Zeit eintragen
                      </button>
                      <button
                        type="button"
                        onClick={() => setAbwesenheitAm(t.tag)}
                        className="inline-flex items-center gap-1 text-sekundaer font-medium text-tint-text"
                      >
                        <Plus size={14} strokeWidth={2} /> Abwesenheit beantragen
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </Karte>
      )}
        </div>
        {(teamSichtbar || abwesenheitenSichtbar) && (
          <aside className="min-w-0 space-y-4">
            {teamSichtbar && <TeamKennzahlen />}
            {abwesenheitenSichtbar && (
              <section aria-label="Meine Abwesenheiten" className="space-y-2">
                <h2 className="text-fliess font-semibold text-label">Meine Abwesenheiten</h2>
                <Karte className="p-1">
                  <ul className="divide-y divide-sep">
                    {meineAbwesenheiten!.map((a) => (
                      <AbwesenheitZeile key={a.id} a={a}>
                        {a.status === "offen" && (
                          <button
                            type="button"
                            className="text-sekundaer font-medium text-tint-text disabled:opacity-50"
                            disabled={zurueckziehen.isPending}
                            onClick={() => zurueckziehen.mutate(a.id)}
                          >
                            Zurückziehen
                          </button>
                        )}
                        {a.status === "genehmigt" && !darfVerwalten && (
                          <span className="text-sekundaer text-label2">Stornierung über das Büro</span>
                        )}
                      </AbwesenheitZeile>
                    ))}
                  </ul>
                </Karte>
                {abwesenheitFehler && <p className="text-fliess text-st-fehlt">{abwesenheitFehler}</p>}
              </section>
            )}
          </aside>
        )}
      </div>

      {neuAm && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4">
          <div className="mt-12 w-full max-w-xl">
            <ZeiterfassungManuellForm
              key={neuAm}
              vorbelegtesDatum={neuAm}
              onClose={() => setNeuAm(null)}
              onGespeichert={() => {
                setNeuAm(null);
                neuLaden();
              }}
            />
          </div>
        </div>
      )}

      {abwesenheitAm && (
        <AbwesenheitSheet
          key={abwesenheitAm}
          vorbelegtesDatum={abwesenheitAm}
          onClose={() => setAbwesenheitAm(null)}
          onGespeichert={() => {
            setAbwesenheitAm(null);
            neuLaden();
          }}
        />
      )}

      {bearbeitet && (
        <ZeiteintragSheet
          key={bearbeitet.id}
          offen
          eintrag={bearbeitet}
          vorgangId={bearbeitet.vorgang_id ?? ""}
          onClose={() => setBearbeitet(null)}
          onGespeichert={neuLaden}
        />
      )}
    </div>
  );
}
