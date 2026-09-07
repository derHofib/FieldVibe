import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileCheck2, Plus, Receipt } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { angeboteApi, kundenApi, rechnungenApi } from "../../api/endpoints";
import { NeueRechnungForm } from "../../components/NeueRechnungForm";
import { SearchableSelect } from "../../components/SearchableSelect";
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
  entwurf: "border border-slate-300 text-slate-500 dark:border-stone-700 dark:text-stone-400",
  versendet: "border border-blue-400 text-blue-700 dark:border-blue-600 dark:text-blue-300",
  teilweise_bezahlt: "border border-amber-400 text-amber-700 dark:border-amber-600 dark:text-amber-300",
  bezahlt: "border border-green-400 text-green-700 dark:border-green-600 dark:text-green-300",
  storniert: "border border-slate-300 text-slate-400 dark:border-stone-700 dark:text-stone-500",
};

const RECHNUNG_STATUS_LABEL: Record<RechnungStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  teilweise_bezahlt: "Teilweise bezahlt",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

const ANGEBOT_STATUS_BADGE: Record<AngebotStatus, string> = {
  entwurf: "border border-slate-300 text-slate-500 dark:border-stone-700 dark:text-stone-400",
  versendet: "border border-blue-400 text-blue-700 dark:border-blue-600 dark:text-blue-300",
  angenommen: "border border-green-400 text-green-700 dark:border-green-600 dark:text-green-300",
  abgelehnt: "border border-rose-400 text-rose-700 dark:border-rose-600 dark:text-rose-300",
};

const ANGEBOT_STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

function NeuesAngebotForm({ onAbbrechen, onErfolg }: { onAbbrechen: () => void; onErfolg: (id: string) => void }) {
  const [kundeId, setKundeId] = useState("");
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });

  const erstellen = useMutation({
    mutationFn: () => angeboteApi.create({ kunde_id: kundeId }),
    onSuccess: (angebot) => onErfolg(angebot.id),
  });

  return (
    <Karte className="mb-4 space-y-3 p-4">
      <div>
        <label className="mb-1 block text-xs font-medium text-ind-ink-3">Kunde</label>
        <SearchableSelect
          value={kundeId}
          onChange={setKundeId}
          placeholder="Kunde wählen…"
          options={(kunden ?? []).map((k) => ({ value: k.id, label: `${k.name} (${k.kundennummer})` }))}
        />
      </div>
      <div className="flex items-center gap-2">
        <button
          disabled={!kundeId || erstellen.isPending}
          onClick={() => erstellen.mutate()}
          className="btn-clay flex-1 rounded-md bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Angebot anlegen
        </button>
        <button onClick={onAbbrechen} className="px-2 text-sm font-medium text-ind-ink-3">
          Abbrechen
        </button>
      </div>
    </Karte>
  );
}

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
  const queryClient = useQueryClient();
  const [bereich, setBereich] = useState<Bereich>("rechnungen");
  const [gewaehlt, setGewaehlt] = useState<string | null>(null);
  const [zeigeNeu, setZeigeNeu] = useState(false);

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
    setZeigeNeu(false);
  };

  const neuAngelegt = (id: string) => {
    setZeigeNeu(false);
    setGewaehlt(id);
    queryClient.invalidateQueries({ queryKey: [bereich === "rechnungen" ? "rechnungen" : "angebote"] });
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
        <button
          onClick={() => setZeigeNeu((v) => !v)}
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-800 dark:border-stone-700 dark:text-stone-300 dark:hover:text-stone-100"
        >
          <Plus size={13} strokeWidth={2.5} />
          {bereich === "rechnungen" ? "Neue Rechnung" : "Neues Angebot"}
        </button>
      </SeitenKopf>

      {zeigeNeu &&
        (bereich === "rechnungen" ? (
          <div className="mb-4">
            <NeueRechnungForm onAbbrechen={() => setZeigeNeu(false)} onErfolg={neuAngelegt} />
          </div>
        ) : (
          <NeuesAngebotForm onAbbrechen={() => setZeigeNeu(false)} onErfolg={neuAngelegt} />
        ))}

      {rechnungen.data && bereich === "rechnungen" && (
        <div className="mb-4 flex flex-wrap gap-4 text-xs text-ind-ink-3">
          <span>
            Summe brutto:{" "}
            <strong className="tabular-nums text-ind-ink">
              {euro(rechnungen.data.summe_brutto)}
            </strong>
          </span>
          <span>
            Davon offen:{" "}
            <strong className="tabular-nums text-ind-ink">
              {euro(rechnungen.data.summe_offen)}
            </strong>
          </span>
        </div>
      )}

      {laedt ? (
        <p className="py-10 text-center text-sm text-ind-ink-3">Lädt…</p>
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
                <p className="truncate text-[13px] font-semibold text-ind-ink">
                  {e.nummer} · <span className="tabular-nums">{e.betrag}</span>
                </p>
                {e.zusatz && (
                  <p
                    className={`mt-0.5 truncate text-[11.5px] ${
                      e.warnung
                        ? "font-bold text-rose-600 dark:text-rose-300"
                        : "text-ind-ink-3"
                    }`}
                  >
                    {e.zusatz}
                  </p>
                )}
                <span
                  className={`mt-1.5 inline-block px-2 py-0.5 text-[10px] font-semibold ${e.badge}`}
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
