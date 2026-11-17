import { useMutation, useQuery } from "@tanstack/react-query";
import { FileCheck2, Receipt, Search } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { angeboteApi, kundenApi, rechnungenApi } from "../../api/endpoints";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import { filterAnwenden, sucheAnwenden } from "../../components/filter/auswerten";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { angebotFelder, kundenOptionen, rechnungFelder, rechnungServerParameter } from "../../components/rechnung/rechnungenFilter";
import { NeueRechnungForm } from "../../components/NeueRechnungForm";
import { EmptyState } from "../../components/EmptyState";
import { SearchableSelect } from "../../components/SearchableSelect";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { useAuth } from "../../context/AuthContext";
import { RECHNUNG_STATUS_LABEL, RECHNUNG_STATUS_TONE } from "../../utils/buchhaltung";
import { downloadBlob } from "../../utils/download";
import { formatDatum, formatEuro } from "../../utils/format";
import { istModulAktiv } from "../../utils/module";
import {
  RECHNUNGSART_LABEL,
  RECHNUNGSART_TONE,
  rechnungsartVon,
} from "../../utils/rechnungsart";
import type { RechnungenFilter } from "../../types";
import { FehlerZustand } from "../../components/FehlerZustand";
import { AnlegenPanel } from "../../components/AnlegenPanel";

type Bereich = "rechnungen" | "angebote";

const SEITENGROESSE = 50;

import { ANGEBOT_STATUS_LABEL } from "../../components/rechnung/rechnungenFilter";

function AngeboteListe() {
  const uid = useId();
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const [kundeId, setKundeId] = useState("");
  const [kundeFehler, setKundeFehler] = useState<string | null>(null);

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });
  const { data: angebote, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({ queryKey: ["angebote"], queryFn: () => angeboteApi.list() });
  const { hatRecht } = useAuth();
  const kundenOpt = useMemo(() => (hatRecht("kunden", "sehen") ? kundenOptionen(kunden) : undefined), [kunden, hatRecht]);
  const felder = useMemo(() => angebotFelder(kundenOpt), [kundenOpt]);
  const zustand = useFilterZustand({ felder, praefix: "a" });
  const sichtbar = useMemo(
    () =>
      sucheAnwenden(filterAnwenden(angebote ?? [], zustand.bedingungen, felder), zustand.sucheVerzoegert, (a) =>
        `${a.angebotsnummer} ${kunden?.find((k) => k.id === a.kunde_id)?.name ?? ""} ${ANGEBOT_STATUS_LABEL[a.status]} ${a.gesamt_brutto}`,
      ),
    [angebote, zustand.bedingungen, zustand.sucheVerzoegert, felder, kunden],
  );
  const filterAktiv = zustand.aktiveAnzahl > 0 || zustand.suche.trim() !== "";

  const erstellen = useMutation({
    mutationFn: () => angeboteApi.create({ kunde_id: kundeId }),
    onSuccess: (angebot) => navigate(`/angebote/${angebot.id}`),
  });

  const nameFuer = (id: string) => kunden?.find((k) => k.id === id)?.name ?? "—";

  return (
    <div className="space-y-4">
      <button
        onClick={() => setShowForm(true)}
        className="btn-touch btn-ap-primary px-4"
      >
        + Neues Angebot
      </button>

      <AnlegenPanel offen={showForm} titel="Neues Angebot" onClose={() => setShowForm(false)}>
        <div className="space-y-3 p-4">
          <div>
            <label htmlFor={`${uid}-0`} className="mb-1 block text-sekundaer font-medium text-label2">
              Kunde <span aria-hidden="true" className="text-st-fehlt">*</span>
            </label>
            <SearchableSelect id={`${uid}-0`}
              value={kundeId}
              onChange={(v) => {
                setKundeId(v);
                setKundeFehler(null);
              }}
              placeholder="Kunde wählen…"
              options={(kunden ?? []).map((k) => ({ value: k.id, label: `${k.name} (${k.kundennummer})` }))}
            />
            {kundeFehler && (
              <p role="alert" className="mt-1 text-sekundaer text-st-fehlt">
                {kundeFehler}
              </p>
            )}
          </div>
          <button
            disabled={erstellen.isPending}
            onClick={() => {
              if (!kundeId) {
                setKundeFehler("Bitte einen Kunden auswählen.");
                return;
              }
              erstellen.mutate();
            }}
            className="btn-touch w-full rounded-md btn-ap-primary px-4 py-2 text-sekundaer font-medium disabled:opacity-50"
          >
            Angebot anlegen
          </button>
        </div>
      </AnlegenPanel>

      <FilterLeiste
        felder={felder}
        zustand={zustand}
        suchPlatzhalter="Nummer oder Kunde suchen…"
      />

      <div className="space-y-2">
        {isLoading ? (
          <SkeletonList count={3} />
        ) : ladeFehler && !angebote ? (
          <FehlerZustand fehler={ladeFehler} was="Die Angebote" onErneut={() => void neuLaden()} />
        ) : sichtbar.length === 0 ? (
          filterAktiv ? (
            <EmptyState
              icon={Search}
              text={zustand.suche.trim() && zustand.aktiveAnzahl === 0 ? `Nichts gefunden für „${zustand.suche.trim()}“.` : "Keine Treffer für diese Filter."}
              action={
                <button type="button" onClick={zustand.zuruecksetzen} className="btn-touch btn-ap px-4">
                  Filter zurücksetzen
                </button>
              }
            />
          ) : (
            <EmptyState icon={FileCheck2} text="Keine Angebote vorhanden." />
          )
        ) : (
          sichtbar.map((a) => (
            <button
              key={a.id}
              onClick={() => navigate(`/angebote/${a.id}`)}
              className="card-interactive btn-touch flex w-full items-center justify-between card-ap p-3 text-left"
            >
              <div>
                <div className="text-meta text-label2">{a.angebotsnummer}</div>
                <div className="text-fliess font-medium text-label">{nameFuer(a.kunde_id)}</div>
                <div className="text-sekundaer text-label2">{formatEuro(a.gesamt_brutto)}</div>
              </div>
              <span className="border rounded-[var(--radius-ap-pill)] border-sep px-2 py-1 text-sekundaer font-semibold text-label">
                {ANGEBOT_STATUS_LABEL[a.status]}
              </span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

export function RechnungenPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();

  const abrechnungAktiv = istModulAktiv(currentUser, "abrechnung");
  const kannSehen = hatRecht("abrechnung", "sehen");

  const [bereich, setBereich] = useState<Bereich>("rechnungen");
  const [zeigeNeu, setZeigeNeu] = useState(false);
  const [seiten, setSeiten] = useState(1);

  const { data: kunden } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
    enabled: abrechnungAktiv && kannSehen && hatRecht("kunden", "sehen"),
  });
  const kundenOpt = useMemo(() => kundenOptionen(kunden), [kunden]);
  const felder = useMemo(() => rechnungFelder(kundenOpt), [kundenOpt]);
  const zustand = useFilterZustand({ felder });

  // Bedingungen und Suche gehören in den Query-Key; bei Änderung beginnt die Liste wieder auf Seite 1.
  const filterBasis: RechnungenFilter = {
    ...rechnungServerParameter(zustand.bedingungen),
    q: zustand.sucheVerzoegert.trim() || undefined,
    sort: "-faellig",
  };
  const filterSchluessel = JSON.stringify(filterBasis);
  const [zuletztSchluessel, setZuletztSchluessel] = useState(filterSchluessel);
  if (zuletztSchluessel !== filterSchluessel) {
    setZuletztSchluessel(filterSchluessel);
    setSeiten(1);
  }
  const filter: RechnungenFilter = { ...filterBasis, limit: SEITENGROESSE * seiten };

  const { data, isLoading, error: rechnungenFehler, refetch: rechnungenNeu } = useQuery({
    queryKey: ["rechnungen-uebersicht", filter],
    queryFn: () => rechnungenApi.list(filter),
    enabled: abrechnungAktiv && kannSehen && bereich === "rechnungen",
  });

  const exportieren = async () => {
    const blob = await rechnungenApi.exportCsv(filterBasis);
    downloadBlob(blob, "Rechnungen.csv");
  };

  const filterAktiv = zustand.aktiveAnzahl > 0 || zustand.suche.trim() !== "";
  const eintraege = data?.eintraege ?? [];
  const gibtMehr = data ? data.gesamt_anzahl > eintraege.length : false;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-titel-mobil font-bold text-label">
          {bereich === "rechnungen" ? "Rechnungen" : "Angebote"}
        </h1>
        {bereich === "rechnungen" && (
          <button
            onClick={exportieren}
            className="btn-touch btn-ap px-3 py-1.5 text-sekundaer font-medium"
          >
            CSV-Export
          </button>
        )}
      </div>

      <SegmentedControl
        ariaLabel="Bereich"
        groesse="touch"
        volleBreite
        optionen={[
          { wert: "rechnungen", label: "Rechnungen" },
          { wert: "angebote", label: "Angebote" },
        ]}
        wert={bereich}
        onChange={(wert) => {
          setBereich(wert);
          setZeigeNeu(false);
        }}
      />

      {bereich === "angebote" ? (
        <AngeboteListe />
      ) : (
        <>
          <button
            onClick={() => setZeigeNeu(true)}
            className="btn-touch btn-ap-primary px-4"
          >
            + Neue Rechnung
          </button>

          <AnlegenPanel offen={zeigeNeu} titel="Neue Rechnung" onClose={() => setZeigeNeu(false)}>
            <NeueRechnungForm
              onAbbrechen={() => setZeigeNeu(false)}
              onErfolg={(id) => navigate(`/rechnungen/${id}`)}
            />
          </AnlegenPanel>

          <FilterLeiste
            felder={felder}
            zustand={zustand}
            suchPlatzhalter="Rechnungsnummer oder Kunde suchen…"
            ansichten="rechnungen"
            alteVorlageUmrechnen={() => []}
          />

          {data && (
            <div className="grid grid-cols-3 gap-2 card-ap p-3 text-center">
              <div>
                <div className="text-sekundaer text-label2">Treffer</div>
                <div className="text-fliess font-semibold tabular-nums text-label">
                  {data.gesamt_anzahl}
                </div>
              </div>
              <div>
                <div className="text-sekundaer text-label2">Brutto gesamt</div>
                <div className="text-fliess font-semibold tabular-nums text-label">
                  {formatEuro(data.summe_brutto)}
                </div>
              </div>
              <div>
                <div className="text-sekundaer text-label2">Offen</div>
                <div className="text-fliess font-semibold tabular-nums text-st-arbeit ">
                  {formatEuro(data.summe_offen)}
                </div>
              </div>
            </div>
          )}

          <div className="space-y-2">
            {isLoading ? (
              <SkeletonList count={5} />
            ) : rechnungenFehler && !data ? (
              <FehlerZustand fehler={rechnungenFehler} was="Die Rechnungen" onErneut={() => void rechnungenNeu()} />
            ) : eintraege.length === 0 ? (
              <EmptyState
                icon={Receipt}
                text={
                  filterAktiv
                    ? zustand.suche.trim() && zustand.aktiveAnzahl === 0
                      ? `Nichts gefunden für „${zustand.suche.trim()}“.`
                      : "Keine Treffer für diese Filter."
                    : "Keine Rechnungen vorhanden."
                }
                action={
                  filterAktiv ? (
                    <button type="button" onClick={zustand.zuruecksetzen} className="btn-touch btn-ap px-4">
                      Filter zurücksetzen
                    </button>
                  ) : hatRecht("abrechnung", "erstellen") ? (
                    <button type="button" onClick={() => setZeigeNeu(true)} className="btn-touch btn-ap px-4">
                      + Neue Rechnung
                    </button>
                  ) : undefined
                }
              />
            ) : (
              eintraege.map((r) => (
                <button
                  key={r.id}
                  onClick={() => navigate(`/rechnungen/${r.id}`)}
                  className={`card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-card p-3 text-left shadow-xs dark:shadow-none dark:ring-1 ${
                    r.ist_ueberfaellig
                      ? "ring-st-fehlt "
                      : ""
                  }`}
                >
                  <div className="min-w-0">
                    <div className="text-meta text-label2">{r.rechnungsnummer}</div>
                    <div className="truncate text-fliess font-medium text-label">
                      Fällig: {formatDatum(r.faellig_am)}
                      {r.ist_ueberfaellig && (
                        <span className="ml-1 text-st-fehlt ">
                          ({r.tage_ueberfaellig} Tage überfällig)
                        </span>
                      )}
                    </div>
                    {r.mahnstufe > 0 && (
                      <div className="text-sekundaer text-st-arbeit ">
                        Mahnstufe {r.mahnstufe}
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span
                      className={`tabular-nums text-fliess font-medium ${
                        Number(r.betrag_brutto) < 0 ? "text-st-fehlt" : "text-label"
                      }`}
                    >
                      {formatEuro(r.betrag_brutto)}
                    </span>
                    <div className="flex flex-wrap justify-end gap-1">
                      {rechnungsartVon(r) !== "rechnung" && (
                        <StatusBadge label={RECHNUNGSART_LABEL[rechnungsartVon(r)]} tone={RECHNUNGSART_TONE[rechnungsartVon(r)]} />
                      )}
                      <StatusBadge label={RECHNUNG_STATUS_LABEL[r.status]} tone={RECHNUNG_STATUS_TONE[r.status]} />
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>

          {gibtMehr && (
            <button
              onClick={() => setSeiten((v) => v + 1)}
              className="btn-touch w-full btn-ap px-3 py-2 text-sekundaer font-medium"
            >
              Mehr laden
            </button>
          )}
        </>
      )}
    </div>
  );
}
