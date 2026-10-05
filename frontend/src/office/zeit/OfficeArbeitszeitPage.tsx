import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Clock, Lock, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { zeiterfassungApi } from "../../api/endpoints";
import { StatusPille } from "../../components/apple/StatusPille";
import { EmptyState } from "../../components/EmptyState";
import { ZeiterfassungManuellForm } from "../../components/ZeiterfassungManuellForm";
import { ZeiteintragSheet } from "../../components/ZeiteintragSheet";
import { useAuth } from "../../context/AuthContext";
import { TeamKennzahlen } from "../../pages/feld/StatistikPage";
import type { Zeiterfassung } from "../../types";
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
import { KennzahlKarte, Karte, SeitenKopf } from "../OfficeUi";

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

  const { von, bis } = monatsGrenzen(jahr, monat0);
  const tage = useMemo(() => tageDesMonats(jahr, monat0), [jahr, monat0]);

  const { data: statistik, refetch: statistikNeuLaden } = useQuery({
    queryKey: ["zeiterfassung-statistik", currentUser?.id],
    queryFn: () => zeiterfassungApi.statistik(),
    enabled: kannAuswerten,
  });

  const { data: eintraege, refetch: monatNeuLaden } = useQuery({
    queryKey: ["zeiterfassung-monat", currentUser?.id, von],
    queryFn: () => zeiterfassungApi.listFuerZeitraum({ techniker_id: currentUser!.id, von, bis }),
    enabled: kannErfassen,
  });

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

  const monatsName = new Date(jahr, monat0, 1).toLocaleDateString("de-DE", { month: "long", year: "numeric" });

  return (
    <div className="space-y-4">
      <SeitenKopf titel="Arbeitszeit">
        <button type="button" onClick={() => monatWechseln(-1)} className="btn-ap px-3 py-1.5">
          ← Monat
        </button>
        <span className="min-w-36 text-center text-sm font-semibold text-label">{monatsName}</span>
        <button type="button" onClick={() => monatWechseln(1)} className="btn-ap px-3 py-1.5">
          Monat →
        </button>
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
      </SeitenKopf>

      {kannAuswerten && hatRecht("statistik", "sehen") && <TeamKennzahlen />}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KennzahlKarte label="Arbeitszeit im Monat" wert={`${formatStundenAlsHHMM(monatssumme)} Std.`} icon={Clock} />
        {kannAuswerten && statistik && (
          <>
            <KennzahlKarte label="Diese Woche" wert={`${formatStundenAlsHHMM(Number(statistik.wochenstunden))} Std.`} />
            <KennzahlKarte label="Aktueller Monat" wert={`${formatStundenAlsHHMM(Number(statistik.monatsstunden))} Std.`} />
            <KennzahlKarte label="Dieses Jahr" wert={`${formatStundenAlsHHMM(Number(statistik.jahresstunden))} Std.`} />
          </>
        )}
      </div>

      {kannErfassen && (
        <Karte className="space-y-1 p-2">
          {tage.map((t) => {
            const tagesEintraege = jeTag.get(t.tag) ?? [];
            const offen = offeneTage.has(t.tag);
            const istHeute = t.tag === heuteTag;
            const flaeche = istHeute ? "bg-tintbg" : t.istWochenende ? "bg-fill" : "";
            const textFarbe = t.istWochenende && !istHeute ? "text-label2" : "text-label";
            return (
              <div key={t.tag} className={`rounded-[var(--radius-ap-md)] ${flaeche}`}>
                <button
                  type="button"
                  onClick={() => toggle(t.tag)}
                  aria-expanded={offen}
                  className={`flex w-full items-center gap-3 px-3 py-2 text-left text-sm ${textFarbe}`}
                >
                  {offen ? <ChevronDown size={15} strokeWidth={2} /> : <ChevronRight size={15} strokeWidth={2} />}
                  <span className="w-7 font-semibold">{WOCHENTAG_KURZ[t.wochentag]}</span>
                  <span className="w-14 tabular-nums">
                    {String(t.tagNr).padStart(2, "0")}.{String(monat0 + 1).padStart(2, "0")}.
                  </span>
                  <span className="flex-1 text-xs text-label2">
                    {tagesEintraege.length > 0 &&
                      `${tagesEintraege.length} ${tagesEintraege.length === 1 ? "Eintrag" : "Einträge"}`}
                  </span>
                  <span className="font-medium tabular-nums">
                    {tagesEintraege.length > 0 ? `${formatStundenAlsHHMM(arbeitsstunden(tagesEintraege))} Std.` : "—"}
                  </span>
                </button>

                {offen && (
                  <div className="px-3 pb-3">
                    {tagesEintraege.length > 0 && (
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-xs text-label2">
                            <th className="py-1 pr-3 font-medium">Von–Bis</th>
                            <th className="py-1 pr-3 text-right font-medium">Dauer</th>
                            <th className="py-1 pr-3 font-medium">Vorgang / Kategorie</th>
                            <th className="py-1 pr-3 font-medium">Tätigkeit</th>
                            <th className="py-1 font-medium">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tagesEintraege.map((e) => (
                            <tr key={e.id} onClick={() => setBearbeitet(e)} className="cursor-pointer hover:bg-fill">
                              <td className="py-1.5 pr-3 tabular-nums">
                                <button
                                  type="button"
                                  onClick={(ev) => {
                                    ev.stopPropagation();
                                    setBearbeitet(e);
                                  }}
                                  className="text-tint-text"
                                >
                                  {formatUhrzeit(e.start_at)}–{e.ende_at ? formatUhrzeit(e.ende_at) : "läuft"}
                                </button>
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
                              <td className="max-w-xs truncate py-1.5 pr-3 text-label2">{e.taetigkeit ?? "—"}</td>
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
                    <button
                      type="button"
                      onClick={() => setNeuAm(t.tag)}
                      className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-tint-text"
                    >
                      <Plus size={14} strokeWidth={2} /> Zeit eintragen
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </Karte>
      )}

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
