import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ClipboardList, Lock, Rss } from "lucide-react";
import { useState } from "react";

import { auftraegeApi, vorgaengeApi } from "../../api/endpoints";
import { Fortschritt } from "../../components/apple/Fortschritt";
import { StatusPille } from "../../components/apple/StatusPille";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { VorgangStatusPille } from "../../components/VorgangStatusPille";
import { istUeberfaellig } from "../../config/vorgangDarstellung";
import type { Auftrag, Projekt, Vorgang } from "../../types";
import { ABSCHNITT_AKTION, Abschnitt } from "../../pages/feld/vorgang/Abschnitt";
import { auftragLink, auftragStatusZuToken, gruppiereNachAuftrag, istVorgangOffen } from "../../utils/verknuepfung";
import { AUFTRAG_STATUS_LABEL } from "../auftraege/AuftraegeTabelle";
import { KennzahlKarte } from "../OfficeUi";

/** Aufträge und Vorgänge eines Projekts. Vorgänge kommen aus der Listen-Route (nicht dem Feed), weil nur
 * sie auftrag_id und die Eigenständig-Kennzeichnung mitliefert; 200 ist das Server-Maximum je Abfrage. */
export function useProjektInhalt(projektId: string) {
  const auftraege = useQuery({
    queryKey: ["auftraege", "projekt", projektId],
    queryFn: () => auftraegeApi.list({ projekt_id: projektId }),
  });
  const vorgaenge = useQuery({
    queryKey: ["vorgaenge", "projekt", projektId],
    queryFn: () => vorgaengeApi.list({ projekt_id: projektId, limit: "200" }),
  });
  return {
    auftraege: auftraege.data,
    vorgaenge: vorgaenge.data,
    laedt: auftraege.isLoading || vorgaenge.isLoading,
  };
}

/** Kennzahlen bevorzugt aus den Server-Zählern des Projekts, sonst aus den geladenen Listen. */
export function ProjektKennzahlen({
  projekt,
  auftraege,
  vorgaenge,
}: {
  projekt: Projekt;
  auftraege: Auftrag[] | undefined;
  vorgaenge: Vorgang[] | undefined;
}) {
  const offen = vorgaenge?.filter((v) => istVorgangOffen(v.status)).length;
  const ueberfaellig = vorgaenge?.filter((v) => istVorgangOffen(v.status) && istUeberfaellig(v.faelligkeit_am)).length;
  const ueberfaelligWert = projekt.anzahl_ueberfaellig ?? ueberfaellig ?? 0;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <KennzahlKarte label="Aufträge" wert={String(projekt.anzahl_auftraege ?? auftraege?.length ?? 0)} />
      <KennzahlKarte label="Vorgänge gesamt" wert={String(projekt.anzahl_vorgaenge ?? vorgaenge?.length ?? 0)} />
      <KennzahlKarte label="Offen" wert={String(projekt.anzahl_offen ?? offen ?? 0)} />
      <KennzahlKarte label="Überfällig" wert={String(ueberfaelligWert)} ton={ueberfaelligWert > 0 ? "warnung" : "neutral"} />
    </div>
  );
}

const KACHEL = "flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-ap-md)] bg-fill text-label2";
const OFFEN_STANDARD = ["offen", "in_arbeit"];

function VorgangZeile({ vorgang, onOeffnen }: { vorgang: Vorgang; onOeffnen: () => void }) {
  return (
    <li>
      <button type="button" onClick={onOeffnen} className="flex w-full items-center gap-3 rounded-[var(--radius-ap-md)] py-2 pr-1 text-left text-fliess hover:bg-fill">
        <span className="shrink-0 text-label2">{vorgang.vorgangsnummer}</span>
        <span className="min-w-0 flex-1 truncate text-label">{vorgang.titel}</span>
        {vorgang.verknuepfung_eigenstaendig && (
          <span className="inline-flex shrink-0 items-center gap-1 text-meta text-label2" title="Eigenständig geführt, zählt trotzdem im Auftrag und Projekt mit">
            <Lock size={12} strokeWidth={1.5} aria-hidden="true" />
            eigenständig
          </span>
        )}
        <VorgangStatusPille status={vorgang.status} />
      </button>
    </li>
  );
}

/** Abschnitt "Aufträge und Vorgänge": je Auftrag eine aufklappbare Zeile (offene Aufträge standardmäßig auf,
 * abgeschlossene zu), darunter die Gruppe "Ohne Auftrag". */
export function AuftraegeUndVorgaenge({
  projektId,
  auftraege,
  vorgaenge,
  laedt,
  navigate,
}: {
  projektId: string;
  auftraege: Auftrag[] | undefined;
  vorgaenge: Vorgang[] | undefined;
  laedt: boolean;
  navigate: (to: string) => void;
}) {
  // Nur ausdrückliche Klicks merken, damit nachgeladene Aufträge ihren Standard (offen/zu) behalten.
  const [umgeschaltet, setUmgeschaltet] = useState<Record<string, boolean>>({});
  const vorgangOeffnen = (id: string) => navigate(`/vorgaenge/${id}/vollbild`);
  const { gruppen, ohneAuftrag } = gruppiereNachAuftrag(auftraege ?? [], vorgaenge ?? []);
  const ohneOffen = umgeschaltet["__ohne__"] ?? true;

  return (
    <Abschnitt
      titel="Aufträge und Vorgänge"
      aktion={
        <button type="button" onClick={() => navigate(`/auftraege?neu=1&projekt_id=${projektId}`)} className={ABSCHNITT_AKTION}>
          + Auftrag
        </button>
      }
    >
      {laedt ? (
        <SkeletonList count={3} />
      ) : gruppen.length === 0 && ohneAuftrag.length === 0 ? (
        <EmptyState icon={ClipboardList} text="Noch kein Auftrag und kein Vorgang in diesem Projekt." />
      ) : (
        <div className="divide-y-[0.5px] divide-sep">
          {gruppen.map(({ auftrag, vorgaenge: eigene, erledigt }) => {
            const standard = OFFEN_STANDARD.includes(auftrag.status);
            const offen = umgeschaltet[auftrag.id] ?? standard;
            return (
              <div key={auftrag.id} className="py-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 py-1.5">
                  <button
                    type="button"
                    aria-expanded={offen}
                    aria-label={`${auftrag.titel} ${offen ? "zuklappen" : "aufklappen"}`}
                    onClick={() => setUmgeschaltet((alt) => ({ ...alt, [auftrag.id]: !offen }))}
                    className="btn-touch flex items-center justify-center text-label2"
                  >
                    <ChevronRight size={16} strokeWidth={2} aria-hidden="true" className={offen ? "rotate-90" : ""} />
                  </button>
                  <span className={KACHEL}>
                    <ClipboardList size={15} strokeWidth={1.5} aria-hidden="true" />
                  </span>
                  <button
                    type="button"
                    onClick={() => navigate(auftragLink(auftrag.id))}
                    className="min-w-0 truncate text-left text-fliess font-semibold text-label hover:underline"
                  >
                    {auftrag.titel}
                  </button>
                  <StatusPille status={auftragStatusZuToken(auftrag.status)} label={AUFTRAG_STATUS_LABEL[auftrag.status]} />
                  <span className="ml-auto">
                    <Fortschritt erledigt={erledigt} gesamt={eigene.length} />
                  </span>
                </div>
                {offen && (
                  <div className="pl-10">
                    <ul>
                      {eigene.map((v) => (
                        <VorgangZeile key={v.id} vorgang={v} onOeffnen={() => vorgangOeffnen(v.id)} />
                      ))}
                    </ul>
                    <button type="button" onClick={() => navigate(`/neu?auftrag_id=${auftrag.id}`)} className={`${ABSCHNITT_AKTION} py-1`}>
                      + Vorgang in diesem Auftrag
                    </button>
                  </div>
                )}
              </div>
            );
          })}
          {ohneAuftrag.length > 0 && (
            <div className="py-1">
              <div className="flex items-center gap-2 py-1.5">
                <button
                  type="button"
                  aria-expanded={ohneOffen}
                  aria-label={`Ohne Auftrag ${ohneOffen ? "zuklappen" : "aufklappen"}`}
                  onClick={() => setUmgeschaltet((alt) => ({ ...alt, __ohne__: !ohneOffen }))}
                  className="btn-touch flex items-center justify-center text-label2"
                >
                  <ChevronRight size={16} strokeWidth={2} aria-hidden="true" className={ohneOffen ? "rotate-90" : ""} />
                </button>
                <span className={KACHEL}>
                  <Rss size={15} strokeWidth={1.5} aria-hidden="true" />
                </span>
                <span className="text-fliess text-label2">Ohne Auftrag</span>
                <span className="ml-auto text-sekundaer text-label2">
                  {ohneAuftrag.length} {ohneAuftrag.length === 1 ? "Vorgang" : "Vorgänge"}
                </span>
              </div>
              {ohneOffen && (
                <ul className="pl-10">
                  {ohneAuftrag.map((v) => (
                    <VorgangZeile key={v.id} vorgang={v} onOeffnen={() => vorgangOeffnen(v.id)} />
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </Abschnitt>
  );
}
