import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, ReceiptText, Search } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { formatEuro, formatIsoTag } from "../../utils/format";
import { ApiError } from "../../api/client";
import { eingangsrechnungenApi } from "../../api/endpoints";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { useAuth } from "../../context/AuthContext";
import { pruefeERechnungDatei } from "../../utils/eRechnung";
import { istModulAktiv } from "../../utils/module";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import { filterAnwenden, sucheAnwenden } from "../../components/filter/auswerten";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import {
  EINGANG_KATEGORIE_LABEL as KATEGORIE_LABEL,
  EINGANG_STATUS_LABEL as STATUS_LABEL,
  eingangsrechnungFelder,
} from "../../components/rechnung/rechnungenFilter";
import { FehlerZustand } from "../../components/FehlerZustand";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { NeueEingangsrechnungForm } from "../../components/rechnung/NeueEingangsrechnungForm";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";

export function RechnungseingangPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const abrechnungAktiv = istModulAktiv(currentUser, "abrechnung");
  const kannSehen = hatRecht("abrechnung", "sehen");
  const kannErstellen = hatRecht("abrechnung", "erstellen");

  const [showForm, setShowForm] = useState(false);
  const [importFehler, setImportFehler] = useState<string | null>(null);
  const importInputRef = useRef<HTMLInputElement>(null);

  const { data: eingangsrechnungen, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["eingangsrechnungen"],
    queryFn: () => eingangsrechnungenApi.list(),
    enabled: abrechnungAktiv && kannSehen,
  });
  // Die Liste kommt ungepaged vom Server, daher läuft alles clientseitig.
  const felder = useMemo(() => eingangsrechnungFelder(), []);
  const zustand = useFilterZustand({ felder });
  const sichtbar = useMemo(
    () =>
      sucheAnwenden(
        filterAnwenden(eingangsrechnungen ?? [], zustand.bedingungen, felder),
        zustand.sucheVerzoegert,
        (e) =>
          [
            e.lieferant_name,
            e.rechnungsnummer_lieferant,
            STATUS_LABEL[e.status],
            e.kategorie ? KATEGORIE_LABEL[e.kategorie] : "",
            e.rechnungsdatum,
            new Date(e.rechnungsdatum).toLocaleDateString("de-DE"),
            e.betrag_brutto,
          ].join(" "),
      ),
    [eingangsrechnungen, zustand.bedingungen, zustand.sucheVerzoegert, felder],
  );
  const filterAktiv = zustand.aktiveAnzahl > 0 || zustand.suche.trim() !== "";

  const eRechnungMutation = useMutation({
    mutationFn: (file: File) => eingangsrechnungenApi.eRechnungImport(file),
    onSuccess: (eingangsrechnung) => {
      setImportFehler(null);
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
      navigate(`/rechnungseingang/${eingangsrechnung.id}`);
    },
    onError: (err) =>
      setImportFehler(err instanceof ApiError ? err.message : "Import der E-Rechnung fehlgeschlagen"),
  });

  function eRechnungGewaehlt(datei: File | undefined) {
    if (importInputRef.current) importInputRef.current.value = "";
    if (!datei) return;
    const vorabFehler = pruefeERechnungDatei(datei);
    if (vorabFehler) {
      setImportFehler(vorabFehler);
      return;
    }
    setImportFehler(null);
    eRechnungMutation.mutate(datei);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-titel-mobil font-bold text-label">Rechnungseingang</h1>
        {kannErstellen && (
          <div className="flex items-center gap-2">
            <input
              ref={importInputRef}
              type="file"
              accept=".xml,.pdf,application/xml,text/xml,application/pdf"
              className="hidden"
              onChange={(e) => eRechnungGewaehlt(e.target.files?.[0])}
            />
            <button
              onClick={() => importInputRef.current?.click()}
              disabled={eRechnungMutation.isPending}
              className="btn-touch btn-ap px-4"
            >
              <FileUp size={14} strokeWidth={2} aria-hidden="true" />
              {eRechnungMutation.isPending ? "Importiert…" : "E-Rechnung importieren"}
            </button>
            <button
              onClick={() => setShowForm(true)}
              className="btn-touch btn-ap-primary px-4"
            >
              + Neue Eingangsrechnung
            </button>
          </div>
        )}
      </div>

      {importFehler && (
        <Hinweiskasten ton="fehler" titel="E-Rechnung konnte nicht importiert werden">
          <p className="whitespace-pre-line">{importFehler}</p>
        </Hinweiskasten>
      )}

      <AnlegenPanel offen={showForm} titel="Neue Eingangsrechnung" onClose={() => setShowForm(false)}>
        <NeueEingangsrechnungForm
          onAngelegt={(eingangsrechnung) => {
            setShowForm(false);
            navigate(`/rechnungseingang/${eingangsrechnung.id}`);
          }}
        />
      </AnlegenPanel>

      <FilterLeiste
        felder={felder}
        zustand={zustand}
        suchPlatzhalter="Aussteller oder Rechnungsnummer suchen…"
      />

      <div className="space-y-2">
        {isLoading ? (
          <SkeletonList count={4} />
        ) : ladeFehler && !eingangsrechnungen ? (
          <FehlerZustand fehler={ladeFehler} was="Die Eingangsrechnungen" onErneut={() => void neuLaden()} />
        ) : sichtbar.length === 0 ? (
          <EmptyState
            icon={filterAktiv ? Search : ReceiptText}
            text={
              filterAktiv
                ? zustand.suche.trim() && zustand.aktiveAnzahl === 0
                  ? `Nichts gefunden für „${zustand.suche.trim()}“.`
                  : "Keine Treffer für diese Filter."
                : "Noch keine Eingangsrechnungen. Hier erscheinen Rechnungen deiner Lieferanten."
            }
            action={
              filterAktiv ? (
                <button type="button" onClick={zustand.zuruecksetzen} className="btn-touch btn-ap px-4">
                  Filter zurücksetzen
                </button>
              ) : kannErstellen ? (
                <button type="button" onClick={() => setShowForm(true)} className="btn-touch btn-ap px-4">
                  + Neue Eingangsrechnung
                </button>
              ) : undefined
            }
          />
        ) : null}
        {sichtbar.map((e) => (
          <button
            key={e.id}
            onClick={() => navigate(`/rechnungseingang/${e.id}`)}
            className="btn-touch flex w-full items-center justify-between card-ap p-3 text-left"
          >
            <div>
              <div className="text-fliess font-semibold text-label">
                {e.lieferant_name}
              </div>
              <div className="text-meta text-label2">
                {e.rechnungsnummer_lieferant} · {formatIsoTag(e.rechnungsdatum.slice(0, 10))}
                {e.kategorie && ` · ${KATEGORIE_LABEL[e.kategorie]}`}
                {e.hat_xml && " · E-Rechnung"}
                {e.import_hinweis && " · Hinweis prüfen"}
              </div>
            </div>
            <div className="text-right">
              <div className="text-fliess font-medium text-label">
                {formatEuro(e.betrag_brutto)}
              </div>
              <span className="border rounded-[var(--radius-ap-pill)] border-sep px-2 py-0.5 text-meta font-semibold text-label">
                {STATUS_LABEL[e.status]}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
