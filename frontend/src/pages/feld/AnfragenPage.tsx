import { useQuery } from "@tanstack/react-query";
import { Inbox, SearchX } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { kundenApi, vorgangAnfragenApi } from "../../api/endpoints";
import type { VorgangAbrechnungsart, VorgangAnfrage } from "../../types";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { useAuth } from "../../context/AuthContext";
import { SkeletonList } from "../../components/Skeleton";
import { Select } from "../../components/apple/Select";
import { filterAnwenden, sucheAnwenden } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import {
  ABRECHNUNGSARTEN,
  LEISTUNGSTYP_LABEL,
  PRIORITAETEN,
  useAnfrageAktionen,
  useAnfragenFilterFelder,
} from "./anfragen/anfragenGemeinsam";

function AnfrageKarte({ anfrage }: { anfrage: VorgangAnfrage }) {
  const uid = useId();
  const [zeigeAnnehmen, setZeigeAnnehmen] = useState(false);
  const [zeigeAblehnen, setZeigeAblehnen] = useState(false);
  const [abrechnungsart, setAbrechnungsart] = useState<VorgangAbrechnungsart>("aufwand");
  const [prioritaet, setPrioritaet] = useState(3);
  const [ablehnungsgrund, setAblehnungsgrund] = useState("");
  const { annehmen, ablehnen, fehler: error } = useAnfrageAktionen(anfrage);

  return (
    <div className="card-ap p-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-meta text-label2">
            {anfrage.kunde_name ?? "–"} · {anfrage.standort_bezeichnung ?? "–"} · {anfrage.anlage_bezeichnung ?? "–"}
          </div>
          <div className="text-fliess font-medium text-label">{anfrage.titel}</div>
          <span className="mt-1 inline-block border rounded-[var(--radius-ap-pill)] border-sep px-2 py-0.5 text-meta text-label">
            {LEISTUNGSTYP_LABEL[anfrage.leistungstyp]}
          </span>
        </div>
        {anfrage.status !== "offen" && (
          <span
            className={`rounded-full px-2 py-1 text-meta font-semibold ${
              anfrage.status === "angenommen"
                ? "bg-st-erledigt-bg text-st-erledigt  "
                : "bg-fill2 text-label "
            }`}
          >
            {anfrage.status === "angenommen" ? "Angenommen" : "Abgelehnt"}
          </span>
        )}
      </div>
      {anfrage.beschreibung && (
        <p className="mt-2 text-fliess text-label">{anfrage.beschreibung}</p>
      )}
      {anfrage.status === "angenommen" && anfrage.vorgang_id && (
        <Link to={`/vorgaenge/${anfrage.vorgang_id}`} className="mt-2 inline-block text-sekundaer font-medium text-tint-text hover:underline">
          Zum Vorgang {anfrage.vorgang_nummer ?? ""}
        </Link>
      )}
      {anfrage.ablehnungsgrund && (
        <p className="mt-2 text-sekundaer text-label2">Grund: {anfrage.ablehnungsgrund}</p>
      )}

      {anfrage.status === "offen" && (
        <div className="mt-3 space-y-2">
          {error && <p className="text-fliess text-st-fehlt ">{error}</p>}

          {!zeigeAnnehmen && !zeigeAblehnen && (
            <div className="flex gap-2">
              <button
                onClick={() => setZeigeAnnehmen(true)}
                className="btn-touch flex-1 rounded-md btn-ap-primary py-2 text-sekundaer font-medium"
              >
                Annehmen
              </button>
              <button
                onClick={() => setZeigeAblehnen(true)}
                className="btn-touch flex-1 rounded-md border border-sep py-2 text-sekundaer font-medium text-label "
              >
                Ablehnen
              </button>
            </div>
          )}

          {zeigeAnnehmen && (
            <div className="space-y-2 border rounded-[var(--radius-ap-card)] border-sepstrong p-3">
              <label htmlFor={`${uid}-0`} className="block text-sekundaer font-medium text-label2">Abrechnungsart</label>
              <Select id={`${uid}-0`}
                value={abrechnungsart}
                onChange={(e) => setAbrechnungsart(e.target.value as VorgangAbrechnungsart)}
              >
                {ABRECHNUNGSARTEN.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </Select>
              <label htmlFor={`${uid}-1`} className="block text-sekundaer font-medium text-label2">Priorität</label>
              <Select id={`${uid}-1`} value={prioritaet} onChange={(e) => setPrioritaet(Number(e.target.value))}>
                {PRIORITAETEN.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </Select>
              <div className="flex gap-2">
                <button
                  onClick={() => annehmen.mutate({ abrechnungsart, prioritaet })}
                  disabled={annehmen.isPending}
                  className="btn-touch flex-1 rounded-md btn-ap-primary py-2 text-sekundaer font-medium disabled:opacity-50"
                >
                  Vorgang anlegen
                </button>
                <button
                  onClick={() => setZeigeAnnehmen(false)}
                  className="btn-touch flex-1 rounded-md border border-sep py-2 text-sekundaer font-medium text-label "
                >
                  Abbrechen
                </button>
              </div>
            </div>
          )}

          {zeigeAblehnen && (
            <div className="space-y-2 border rounded-[var(--radius-ap-card)] border-sepstrong p-3">
              <textarea
                value={ablehnungsgrund}
                onChange={(e) => setAblehnungsgrund(e.target.value)}
                placeholder="Grund (optional, für interne Notiz)"
                rows={2}
                className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent p-2 text-zeile text-label"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => ablehnen.mutate(ablehnungsgrund)}
                  disabled={ablehnen.isPending}
                  className="btn-touch flex-1 rounded-md bg-st-fehlt-dot py-2 text-sekundaer font-medium text-white disabled:opacity-50"
                >
                  Ablehnen bestätigen
                </button>
                <button
                  onClick={() => setZeigeAblehnen(false)}
                  className="btn-touch flex-1 rounded-md border border-sep py-2 text-sekundaer font-medium text-label "
                >
                  Abbrechen
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AnfragenPage() {
  const { hatRecht } = useAuth();
  const [params] = useSearchParams();
  const { data: anfragen, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["vorgang-anfragen"],
    queryFn: () => vorgangAnfragenApi.list(),
  });
  const { data: kunden } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
    enabled: hatRecht("kunden", "sehen"),
  });

  const felder = useAnfragenFilterFelder(kunden);
  const zustand = useFilterZustand({ felder });

  // Bisher zeigte die Seite standardmäßig nur offene Anfragen; ohne gespeicherten Filterstand bleibt das so.
  const startFilterGesetzt = useRef(false);
  useEffect(() => {
    if (startFilterGesetzt.current) return;
    startFilterGesetzt.current = true;
    if (!params.has("f")) zustand.setBedingungen([{ feld: "status", op: "ist", wert: ["offen"] }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sichtbar = sucheAnwenden(
    filterAnwenden(anfragen ?? [], zustand.bedingungen, felder),
    zustand.sucheVerzoegert,
    (a) => `${a.titel} ${a.beschreibung ?? ""} ${a.kunde_name ?? ""}`,
  );

  return (
    <div className="space-y-4">
      <h1 className="text-titel-mobil font-bold text-label">Vorgangsanfragen</h1>
      {anfragen && anfragen.length > 0 && (
        <FilterLeiste felder={felder} zustand={zustand} suchPlatzhalter="Anfragen durchsuchen…" />
      )}

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !anfragen ? (
        <FehlerZustand fehler={ladeFehler} was="Die Anfragen" onErneut={() => void neuLaden()} />
      ) : !anfragen || anfragen.length === 0 ? (
        <EmptyState icon={Inbox} text="Noch keine Anfragen vorhanden. Anfragen aus dem Kundenportal erscheinen hier." />
      ) : sichtbar.length === 0 ? (
        <EmptyState
          icon={SearchX}
          text={
            zustand.bedingungen.length > 0 || !zustand.sucheVerzoegert
              ? "Keine Treffer für diese Filter"
              : `Nichts gefunden für „${zustand.sucheVerzoegert}"`
          }
          action={
            <button type="button" onClick={zustand.zuruecksetzen} className="btn-touch btn-ap px-4">
              Filter zurücksetzen
            </button>
          }
        />
      ) : (
        <div className="space-y-2">
          {sichtbar.map((a) => (
            <AnfrageKarte key={a.id} anfrage={a} />
          ))}
        </div>
      )}
    </div>
  );
}
