import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileCheck2, Plus, Receipt, Search } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { angeboteApi, kundenApi, rechnungenApi } from "../../api/endpoints";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { useAuth } from "../../context/AuthContext";
import { NeueRechnungForm } from "../../components/NeueRechnungForm";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import { filterAnwenden, sucheAnwenden } from "../../components/filter/auswerten";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { angebotFelder, kundenOptionen, rechnungFelder, rechnungServerParameter } from "../../components/rechnung/rechnungenFilter";
import { SearchableSelect } from "../../components/SearchableSelect";
import { EmptyState } from "../../components/EmptyState";
import { AngebotDetailPage } from "../../pages/feld/AngebotDetailPage";
import { RechnungDetailPage } from "../../pages/feld/RechnungDetailPage";
import { StatusBadge } from "../../components/StatusBadge";
import type { AngebotStatus, RechnungenFilter, RechnungStatus } from "../../types";
import {
  RECHNUNGSART_LABEL,
  RECHNUNGSART_TONE,
  rechnungsartVon,
} from "../../utils/rechnungsart";
import { AnsichtUmschalter, Karte, SeitenKopf } from "../OfficeUi";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";

type Bereich = "rechnungen" | "angebote";

const SEITENGROESSE = 50;

const UMSCHALTER = [
  { wert: "rechnungen" as const, label: "Rechnungen", icon: Receipt },
  { wert: "angebote" as const, label: "Angebote", icon: FileCheck2 },
];

const RECHNUNG_STATUS_BADGE: Record<RechnungStatus, string> = {
  entwurf: "border rounded-[var(--radius-ap-pill)] border-sep text-label2 ",
  versendet: "border rounded-[var(--radius-ap-pill)] border-tint text-tint ",
  teilweise_bezahlt: "border rounded-[var(--radius-ap-pill)] border-st-arbeit text-st-arbeit ",
  bezahlt: "border rounded-[var(--radius-ap-pill)] border-st-erledigt text-st-erledigt ",
  storniert: "border rounded-[var(--radius-ap-pill)] border-sep text-label2",
};

const RECHNUNG_STATUS_LABEL: Record<RechnungStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  teilweise_bezahlt: "Teilweise bezahlt",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

const ANGEBOT_STATUS_BADGE: Record<AngebotStatus, string> = {
  entwurf: "border rounded-[var(--radius-ap-pill)] border-sep text-label2 ",
  versendet: "border rounded-[var(--radius-ap-pill)] border-tint text-tint ",
  angenommen: "border rounded-[var(--radius-ap-pill)] border-st-erledigt text-st-erledigt ",
  abgelehnt: "border rounded-[var(--radius-ap-pill)] border-st-fehlt text-st-fehlt ",
  widerrufen: "border rounded-[var(--radius-ap-pill)] border-st-arbeit text-st-arbeit ",
};

const ANGEBOT_STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
  widerrufen: "Widerrufen",
};

function NeuesAngebotForm({ onAbbrechen, onErfolg }: { onAbbrechen: () => void; onErfolg: (id: string) => void }) {
  const uid = useId();
  const [kundeId, setKundeId] = useState("");
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });

  const erstellen = useMutation({
    mutationFn: () => angeboteApi.create({ kunde_id: kundeId }),
    onSuccess: (angebot) => onErfolg(angebot.id),
  });

  return (
    <div className="space-y-3 p-4">
      <div>
        <label htmlFor={`${uid}-0`} className="mb-1 block text-fliess font-medium text-label">Kunde</label>
        <SearchableSelect id={`${uid}-0`}
          value={kundeId}
          onChange={setKundeId}
          placeholder="Kunde wählen…"
          options={(kunden ?? []).map((k) => ({ value: k.id, label: `${k.name} (${k.kundennummer})` }))}
        />
      </div>
      {erstellen.isError && (
        <p role="alert" className="text-sekundaer text-st-fehlt">Das Angebot konnte nicht angelegt werden.</p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onAbbrechen} className="btn-touch btn-ap px-4">
          Abbrechen
        </button>
        <button
          disabled={!kundeId || erstellen.isPending}
          onClick={() => erstellen.mutate()}
          className={NEU_BUTTON_KLASSE}
        >
          Angebot anlegen
        </button>
      </div>
    </div>
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
  const { hatRecht } = useAuth();
  const darfAnlegen = hatRecht("abrechnung", "erstellen");
  const darfKundenSehen = hatRecht("kunden", "sehen");

  const { data: kunden } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
    enabled: darfKundenSehen,
  });
  const kundenOpt = useMemo(() => kundenOptionen(kunden), [kunden]);
  const rFelder = useMemo(() => rechnungFelder(kundenOpt), [kundenOpt]);
  const aFelder = useMemo(() => angebotFelder(kundenOpt), [kundenOpt]);
  const rechnungsZustand = useFilterZustand({ felder: rFelder });
  const angebotsZustand = useFilterZustand({ felder: aFelder, praefix: "a" });
  const zustand = bereich === "rechnungen" ? rechnungsZustand : angebotsZustand;

  // Suche und Filter laufen serverseitig und seitenweise: die Liste kann länger sein als eine Seite.
  const rechnungsFilter: RechnungenFilter = {
    ...rechnungServerParameter(rechnungsZustand.bedingungen),
    q: rechnungsZustand.sucheVerzoegert.trim() || undefined,
  };
  const rechnungen = useInfiniteQuery({
    queryKey: ["rechnungen", "office-liste", rechnungsFilter],
    queryFn: ({ pageParam }) => rechnungenApi.list({ ...rechnungsFilter, limit: SEITENGROESSE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (letzte, seiten) => {
      const geladen = seiten.reduce((n, s) => n + s.eintraege.length, 0);
      return geladen < letzte.gesamt_anzahl ? geladen : undefined;
    },
    enabled: bereich === "rechnungen",
  });
  const rechnungsSeiten = rechnungen.data?.pages ?? [];
  const erstSeite = rechnungsSeiten[0];
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

  const angebotGefiltert = useMemo(
    () =>
      sucheAnwenden(
        filterAnwenden(angebote.data ?? [], angebotsZustand.bedingungen, aFelder),
        angebotsZustand.sucheVerzoegert,
        (a) =>
          `${a.angebotsnummer} ${kunden?.find((k) => k.id === a.kunde_id)?.name ?? ""} ${ANGEBOT_STATUS_LABEL[a.status]} ${a.gesamt_brutto}`,
      ),
    [angebote.data, angebotsZustand.bedingungen, angebotsZustand.sucheVerzoegert, aFelder, kunden],
  );

  const eintraege =
    bereich === "rechnungen"
      ? rechnungsSeiten.flatMap((s) => s.eintraege).map((r) => ({
          id: r.id,
          nummer: r.rechnungsnummer,
          betrag: euro(r.betrag_brutto),
          zusatz: r.ist_ueberfaellig
            ? `${r.tage_ueberfaellig} Tage überfällig`
            : r.faellig_am
              ? `fällig ${r.faellig_am}`
              : "",
          warnung: r.ist_ueberfaellig,
          negativ: Number(r.betrag_brutto) < 0,
          art: rechnungsartVon(r) !== "rechnung" ? rechnungsartVon(r) : null,
          badge: RECHNUNG_STATUS_BADGE[r.status],
          label: RECHNUNG_STATUS_LABEL[r.status],
        }))
      : angebotGefiltert.map((a) => ({
          id: a.id,
          nummer: a.angebotsnummer,
          betrag: euro(a.gesamt_brutto),
          zusatz: a.gueltig_bis ? `gültig bis ${a.gueltig_bis}` : "",
          warnung: false,
          negativ: false,
          art: null,
          badge: ANGEBOT_STATUS_BADGE[a.status],
          label: ANGEBOT_STATUS_LABEL[a.status],
        }));

  const aktuelleAbfrage = bereich === "rechnungen" ? rechnungen : angebote;
  const laedt = aktuelleAbfrage.isLoading;
  const filterAktiv = zustand.aktiveAnzahl > 0 || zustand.suche.trim() !== "";
  const aktiv = gewaehlt && eintraege.some((e) => e.id === gewaehlt) ? gewaehlt : eintraege[0]?.id;

  return (
    <div>
      <SeitenKopf titel={bereich === "rechnungen" ? "Rechnungen" : "Angebote"} anzahl={bereich === "rechnungen" ? erstSeite?.gesamt_anzahl : eintraege.length}>
        <AnsichtUmschalter wert={bereich} optionen={UMSCHALTER} onWechsel={wechsle} />
        {darfAnlegen && (
          <button onClick={() => setZeigeNeu(true)} className={NEU_BUTTON_KLASSE}>
            <Plus size={13} strokeWidth={2.5} aria-hidden="true" />
            {bereich === "rechnungen" ? "Neue Rechnung" : "Neues Angebot"}
          </button>
        )}
      </SeitenKopf>

      <AnlegenPanel
        offen={zeigeNeu}
        titel={bereich === "rechnungen" ? "Neue Rechnung" : "Neues Angebot"}
        onClose={() => setZeigeNeu(false)}
      >
        {bereich === "rechnungen" ? (
          <NeueRechnungForm onAbbrechen={() => setZeigeNeu(false)} onErfolg={neuAngelegt} />
        ) : (
          <NeuesAngebotForm onAbbrechen={() => setZeigeNeu(false)} onErfolg={neuAngelegt} />
        )}
      </AnlegenPanel>

      {bereich === "rechnungen" ? (
        <FilterLeiste
          key="rechnungen"
          variante="office"
          felder={rFelder}
          zustand={rechnungsZustand}
          suchPlatzhalter="Nummer oder Kunde suchen…"
          ansichten="rechnungen"
          alteVorlageUmrechnen={() => []}
          className="mb-4"
        />
      ) : (
        <FilterLeiste
          key="angebote"
          variante="office"
          felder={aFelder}
          zustand={angebotsZustand}
          suchPlatzhalter="Nummer oder Kunde suchen…"
          className="mb-4"
        />
      )}

      {erstSeite && bereich === "rechnungen" && (
        <div className="mb-4 flex flex-wrap gap-4 text-sekundaer text-label2">
          <span>
            Summe brutto:{" "}
            <strong className="tabular-nums text-label">
              {euro(erstSeite.summe_brutto)}
            </strong>
          </span>
          <span>
            Davon offen:{" "}
            <strong className="tabular-nums text-label">
              {euro(erstSeite.summe_offen)}
            </strong>
          </span>
        </div>
      )}

      {laedt ? (
        <SkeletonList count={4} />
      ) : aktuelleAbfrage.error && !aktuelleAbfrage.data ? (
        <FehlerZustand
          fehler={aktuelleAbfrage.error}
          was={bereich === "rechnungen" ? "Die Rechnungen" : "Die Angebote"}
          onErneut={() => void aktuelleAbfrage.refetch()}
        />
      ) : eintraege.length === 0 ? (
        filterAktiv ? (
          <EmptyState
            icon={Search}
            text={zustand.suche.trim() && zustand.aktiveAnzahl === 0 ? `Nichts gefunden für „${zustand.suche.trim()}“.` : "Keine Treffer für diese Filter."}
            action={
              <button type="button" onClick={zustand.zuruecksetzen} className="btn-ap px-4 py-2 text-sekundaer">
                Filter zurücksetzen
              </button>
            }
          />
        ) : (
          <EmptyState
            icon={bereich === "rechnungen" ? Receipt : FileCheck2}
            text={
              bereich === "rechnungen"
                ? "Keine Rechnungen vorhanden. Rechnungen entstehen aus Vorgängen oder werden hier neu angelegt."
                : "Keine Angebote vorhanden. Angebote entstehen aus Mängeln oder werden hier neu angelegt."
            }
            action={
              darfAnlegen ? (
                <button type="button" onClick={() => setZeigeNeu(true)} className="btn-ap px-4 py-2 text-sekundaer">
                  {bereich === "rechnungen" ? "Neue Rechnung" : "Neues Angebot"}
                </button>
              ) : undefined
            }
          />
        )
      ) : (
        <div className="grid grid-cols-[minmax(260px,320px)_1fr] gap-4">
          <Karte className="max-h-[calc(100vh-15rem)] overflow-y-auto">
            {eintraege.map((e) => (
              <button
                key={e.id}
                onClick={() => setGewaehlt(e.id)}
                className={`block w-full border-b border-sep px-3 py-2.5 text-left last:border-b-0 ${
                  e.id === aktiv
                    ? "border-l-2 border-l-blue-500 bg-tintbg pl-[10px] "
                    : "hover:bg-fill"
                }`}
              >
                <p className="truncate text-sekundaer font-semibold text-label">
                  {e.nummer} ·{" "}
                  <span className={`tabular-nums ${e.negativ ? "text-st-fehlt" : ""}`}>{e.betrag}</span>
                </p>
                {e.zusatz && (
                  <p
                    className={`mt-0.5 truncate text-meta ${
                      e.warnung
                        ? "font-bold text-st-fehlt "
                        : "text-label2"
                    }`}
                  >
                    {e.zusatz}
                  </p>
                )}
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {e.art && <StatusBadge label={RECHNUNGSART_LABEL[e.art]} tone={RECHNUNGSART_TONE[e.art]} />}
                  <span className={`inline-block px-2 py-0.5 text-meta font-semibold ${e.badge}`}>{e.label}</span>
                </div>
              </button>
            ))}
            {bereich === "rechnungen" && rechnungen.hasNextPage && (
              <button
                type="button"
                onClick={() => void rechnungen.fetchNextPage()}
                disabled={rechnungen.isFetchingNextPage}
                className="btn-ap m-3 px-3 py-1.5 text-sekundaer font-medium disabled:opacity-50"
              >
                {rechnungen.isFetchingNextPage ? "Lädt…" : "Weitere laden"}
              </button>
            )}
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
                    className="flex items-center gap-1.5 rounded-lg border border-sep px-2.5 py-1.5 text-meta font-medium text-label2 hover:text-label dark:hover:text-label3"
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
