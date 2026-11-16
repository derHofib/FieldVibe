import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileCheck2, Plus, Receipt, Search } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { angeboteApi, kundenApi, rechnungenApi } from "../../api/endpoints";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { FilterChip } from "../../components/apple/FilterChip";
import { SearchField } from "../../components/apple/SearchField";
import { NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { useAuth } from "../../context/AuthContext";
import { NeueRechnungForm } from "../../components/NeueRechnungForm";
import { SearchableSelect } from "../../components/SearchableSelect";
import { EmptyState } from "../../components/EmptyState";
import { AngebotDetailPage } from "../../pages/feld/AngebotDetailPage";
import { RechnungDetailPage } from "../../pages/feld/RechnungDetailPage";
import { StatusBadge } from "../../components/StatusBadge";
import type { AngebotStatus, Rechnungsart, RechnungStatus } from "../../types";
import {
  RECHNUNGSART_FILTER,
  RECHNUNGSART_LABEL,
  RECHNUNGSART_TONE,
  rechnungsartVon,
} from "../../utils/rechnungsart";
import { AnsichtUmschalter, Karte, SeitenKopf } from "../OfficeUi";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";

type Bereich = "rechnungen" | "angebote";

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
  const [suche, setSuche] = useState("");
  const [artFilter, setArtFilter] = useState<Rechnungsart | null>(null);

  const rechnungen = useQuery({
    queryKey: ["rechnungen", { rechnungsart: artFilter }],
    queryFn: () => rechnungenApi.list({ rechnungsart: artFilter ?? undefined }),
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
    setSuche("");
  };

  const neuAngelegt = (id: string) => {
    setZeigeNeu(false);
    setGewaehlt(id);
    queryClient.invalidateQueries({ queryKey: [bereich === "rechnungen" ? "rechnungen" : "angebote"] });
  };

  const alleEintraege =
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
          negativ: Number(r.betrag_brutto) < 0,
          art: rechnungsartVon(r) !== "rechnung" ? rechnungsartVon(r) : null,
          badge: RECHNUNG_STATUS_BADGE[r.status],
          label: RECHNUNG_STATUS_LABEL[r.status],
        }))
      : (angebote.data ?? []).map((a) => ({
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

  // Beide Listen werden vollständig geladen, daher genügt ein Client-Filter.
  const eintraege = useMemo(() => {
    const q = suche.trim().toLowerCase();
    return q ? alleEintraege.filter((e) => e.nummer.toLowerCase().includes(q)) : alleEintraege;
  }, [alleEintraege, suche]);

  const aktuelleAbfrage = bereich === "rechnungen" ? rechnungen : angebote;
  const laedt = aktuelleAbfrage.isLoading;
  const aktiv = gewaehlt && eintraege.some((e) => e.id === gewaehlt) ? gewaehlt : eintraege[0]?.id;

  return (
    <div>
      <SeitenKopf titel={bereich === "rechnungen" ? "Rechnungen" : "Angebote"} anzahl={eintraege.length}>
        <AnsichtUmschalter wert={bereich} optionen={UMSCHALTER} onWechsel={wechsle} />
        <SearchField
          value={suche}
          onChange={setSuche}
          placeholder="Nummer…"
          ariaLabel={bereich === "rechnungen" ? "Rechnungen suchen" : "Angebote suchen"}
          className="w-48"
        />
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

      {bereich === "rechnungen" && (
        <div className="mb-4 flex flex-wrap items-center gap-2" role="group" aria-label="Art der Rechnung">
          <span className="text-sekundaer text-label2">Art</span>
          {RECHNUNGSART_FILTER.map((a) => (
            <FilterChip
              key={a}
              label={RECHNUNGSART_LABEL[a]}
              aktiv={artFilter === a}
              onClick={() => setArtFilter((aktuell) => (aktuell === a ? null : a))}
            />
          ))}
        </div>
      )}

      {rechnungen.data && bereich === "rechnungen" && (
        <div className="mb-4 flex flex-wrap gap-4 text-sekundaer text-label2">
          <span>
            Summe brutto:{" "}
            <strong className="tabular-nums text-label">
              {euro(rechnungen.data.summe_brutto)}
            </strong>
          </span>
          <span>
            Davon offen:{" "}
            <strong className="tabular-nums text-label">
              {euro(rechnungen.data.summe_offen)}
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
        suche.trim() && alleEintraege.length > 0 ? (
          <EmptyState icon={Search} text="Kein Eintrag entspricht der Suche." />
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
