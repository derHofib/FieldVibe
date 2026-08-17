import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileCheck2, Receipt } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { angeboteApi, rechnungenApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { AngebotDetailPage } from "../../pages/feld/AngebotDetailPage";
import { RechnungDetailPage } from "../../pages/feld/RechnungDetailPage";
import type { AngebotStatus, RechnungStatus } from "../../types";
import { AnsichtUmschalter, Karte, SeitenKopf } from "../OfficeUi";

type Bereich = "rechnungen" | "angebote";

const UMSCHALTER = [
  { wert: "rechnungen" as const, label: "Rechnungen", icon: Receipt },
  { wert: "angebote" as const, label: "Angebote", icon: FileCheck2 },
];

const RECHNUNG_STATUS_BADGE: Record<RechnungStatus, string> = {
  entwurf: "bg-slate-100 text-slate-500 dark:bg-stone-800 dark:text-stone-400",
  versendet: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300",
  teilweise_bezahlt: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  bezahlt: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300",
  storniert: "bg-slate-100 text-slate-400 dark:bg-stone-800 dark:text-stone-500",
};

const RECHNUNG_STATUS_LABEL: Record<RechnungStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  teilweise_bezahlt: "Teilweise bezahlt",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

const ANGEBOT_STATUS_BADGE: Record<AngebotStatus, string> = {
  entwurf: "bg-slate-100 text-slate-500 dark:bg-stone-800 dark:text-stone-400",
  versendet: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300",
  angenommen: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300",
  abgelehnt: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
};

const ANGEBOT_STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

function euro(betrag: string): string {
  const zahl = Number(betrag);
  if (Number.isNaN(zahl)) return betrag;
  return zahl.toLocaleString("de-DE", { style: "currency", currency: "EUR" });
}

/** Liste links, bestehende Detailseite rechts -- dasselbe Muster wie bei den
 * Vorgaengen, damit Rechnungen und Angebote nicht in einer zweiten Fassung
 * gepflegt werden muessen. */
export function OfficeRechnungenPage() {
  const navigate = useNavigate();
  const [bereich, setBereich] = useState<Bereich>("rechnungen");
  const [gewaehlt, setGewaehlt] = useState<string | null>(null);

  const rechnungen = useQuery({
    queryKey: ["rechnungen", {}],
    queryFn: () => rechnungenApi.list(),
    enabled: bereich === "rechnungen",
  });
  const angebote = useQuery({
    queryKey: ["angebote"],
    queryFn: () => angeboteApi.list(),
    enabled: bereich === "angebote",
  });

  const wechsle = (neu: Bereich) => {
    setBereich(neu);
    setGewaehlt(null);
  };

  const eintraege =
    bereich === "rechnungen"
      ? (rechnungen.data?.eintraege ?? []).map((r) => ({
          id: r.id,
          nummer: r.rechnungsnummer,
          betrag: euro(r.betrag_brutto),
          zusatz: r.ist_ueberfaellig
            ? `${r.tage_ueberfaellig} Tage überfällig`
            : r.faellig_am
              ? `fällig ${r.faellig_am}`
              : "",
          warnung: r.ist_ueberfaellig,
          badge: RECHNUNG_STATUS_BADGE[r.status],
          label: RECHNUNG_STATUS_LABEL[r.status],
        }))
      : (angebote.data ?? []).map((a) => ({
          id: a.id,
          nummer: a.angebotsnummer,
          betrag: euro(a.gesamt_brutto),
          zusatz: a.gueltig_bis ? `gültig bis ${a.gueltig_bis}` : "",
          warnung: false,
          badge: ANGEBOT_STATUS_BADGE[a.status],
          label: ANGEBOT_STATUS_LABEL[a.status],
        }));

  const laedt = bereich === "rechnungen" ? rechnungen.isLoading : angebote.isLoading;
  const aktiv = gewaehlt && eintraege.some((e) => e.id === gewaehlt) ? gewaehlt : eintraege[0]?.id;

  return (
    <div>
      <SeitenKopf titel={bereich === "rechnungen" ? "Rechnungen" : "Angebote"} anzahl={eintraege.length}>
        <AnsichtUmschalter wert={bereich} optionen={UMSCHALTER} onWechsel={wechsle} />
      </SeitenKopf>

      {rechnungen.data && bereich === "rechnungen" && (
        <div className="mb-4 flex flex-wrap gap-4 text-xs text-slate-500 dark:text-stone-400">
          <span>
            Summe brutto:{" "}
            <strong className="tabular-nums text-slate-800 dark:text-stone-100">
              {euro(rechnungen.data.summe_brutto)}
            </strong>
          </span>
          <span>
            Davon offen:{" "}
            <strong className="tabular-nums text-slate-800 dark:text-stone-100">
              {euro(rechnungen.data.summe_offen)}
            </strong>
          </span>
        </div>
      )}

      {laedt ? (
        <p className="py-10 text-center text-sm text-slate-400 dark:text-stone-500">Lädt…</p>
      ) : eintraege.length === 0 ? (
        <EmptyState
          icon={bereich === "rechnungen" ? Receipt : FileCheck2}
          text={bereich === "rechnungen" ? "Keine Rechnungen vorhanden." : "Keine Angebote vorhanden."}
        />
      ) : (
        <div className="grid grid-cols-[minmax(260px,320px)_1fr] gap-4">
          <Karte className="max-h-[calc(100vh-15rem)] overflow-y-auto">
            {eintraege.map((e) => (
              <button
                key={e.id}
                onClick={() => setGewaehlt(e.id)}
                className={`block w-full border-b border-slate-100 px-3 py-2.5 text-left last:border-b-0 dark:border-stone-800 ${
                  e.id === aktiv
                    ? "border-l-2 border-l-blue-500 bg-blue-50/60 pl-[10px] dark:bg-blue-500/10"
                    : "hover:bg-slate-50 dark:hover:bg-stone-800/50"
                }`}
              >
                <p className="truncate text-[13px] font-semibold text-slate-800 dark:text-stone-100">
                  {e.nummer} · <span className="tabular-nums">{e.betrag}</span>
                </p>
                {e.zusatz && (
                  <p
                    className={`mt-0.5 truncate text-[11.5px] ${
                      e.warnung
                        ? "font-bold text-rose-600 dark:text-rose-300"
                        : "text-slate-500 dark:text-stone-400"
                    }`}
                  >
                    {e.zusatz}
                  </p>
                )}
                <span
                  className={`mt-1.5 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${e.badge}`}
                >
                  {e.label}
                </span>
              </button>
            ))}
          </Karte>

          <Karte className="max-h-[calc(100vh-15rem)] overflow-y-auto p-4">
            {aktiv ? (
              <>
                <div className="mb-3 flex justify-end">
                  <button
                    onClick={() =>
                      navigate(
                        bereich === "rechnungen" ? `/rechnungen/${aktiv}` : `/angebote/${aktiv}`,
                      )
                    }
                    className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 dark:border-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
                  >
                    <ExternalLink size={13} strokeWidth={2} />
                    Ganze Seite
                  </button>
                </div>
                {bereich === "rechnungen" ? (
                  <RechnungDetailPage id={aktiv} />
                ) : (
                  <AngebotDetailPage id={aktiv} />
                )}
              </>
            ) : null}
          </Karte>
        </div>
      )}
    </div>
  );
}
