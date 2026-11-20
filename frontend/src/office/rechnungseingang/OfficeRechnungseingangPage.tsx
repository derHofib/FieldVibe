import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlarmClock,
  CircleCheck,
  ExternalLink,
  FileDown,
  FileUp,
  Inbox,
  Percent,
  Plus,
  Search,
  Wallet,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { eingangsrechnungenApi, exportApi } from "../../api/endpoints";
import { AktionsMenue } from "../../components/AktionsMenue";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { StatusPille } from "../../components/apple/StatusPille";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { filterAnwenden, formatDatum, sucheAnwenden } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import type { FilterBedingung } from "../../components/filter/typen";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { NeueEingangsrechnungForm } from "../../components/rechnung/NeueEingangsrechnungForm";
import {
  EINGANG_KATEGORIE_LABEL,
  EINGANG_STATUS_LABEL,
  eingangsrechnungFelder,
  eingangStatusToken,
} from "../../components/rechnung/rechnungenFilter";
import { SkeletonList } from "../../components/Skeleton";
import { useToast } from "../../components/Toast";
import { useAuth } from "../../context/AuthContext";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { EingangsrechnungDetailPage } from "../../pages/feld/EingangsrechnungDetailPage";
import type { Eingangsrechnung } from "../../types";
import { pruefeERechnungDatei } from "../../utils/eRechnung";
import { eingangsKennzahlen } from "../../utils/eingangsrechnung";
import { downloadBlob } from "../../utils/download";
import { heuteIso } from "../../utils/format";
import { istModulAktiv } from "../../utils/module";
import { ListeMitPanel } from "../ListeMitPanel";
import { KennzahlKarte, SeitenKopf } from "../OfficeUi";
import { SortierbareTabelle, type Spalte } from "../SortierbareTabelle";

const EURO = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
const ANNAHME = ".xml,.pdf,application/xml,text/xml,application/pdf";

const rechnungen = (n: number) => (n === 1 ? "1 Rechnung" : `${n} Rechnungen`);
const tag = (iso: string | null) => (iso ? formatDatum(iso) : "–");
const istUeberfaellig = (e: Eingangsrechnung) =>
  e.status === "offen" && !!e.faellig_am && e.faellig_am.slice(0, 10) < heuteIso();

/** Desktop-Fassung des Rechnungseingangs: Kennzahlen, Tabelle links, rechts die bestehende Detailseite
 * (/rechnungseingang/:id). E-Rechnungen lassen sich auf die Seite ziehen. Die Feld-App-Liste bleibt unverändert. */
export function OfficeRechnungseingangPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { search } = useLocation();
  const [params] = useSearchParams();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { currentUser, hatRecht } = useAuth();

  const kannLesen = istModulAktiv(currentUser, "abrechnung") && hatRecht("abrechnung", "sehen");
  const kannErstellen = hatRecht("abrechnung", "erstellen");

  const [neu, setNeu] = useState(false);
  const [importFehler, setImportFehler] = useState<string[]>([]);
  const [ziehend, setZiehend] = useState(false);
  const ziehZaehler = useRef(0);
  const importInputRef = useRef<HTMLInputElement>(null);

  const breit = useMediaQuery("(min-width: 1440px)");
  const mittel = useMediaQuery("(min-width: 1280px)");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["eingangsrechnungen"],
    queryFn: () => eingangsrechnungenApi.list(),
    enabled: kannLesen,
  });

  // Die Liste kommt ungepaged vom Server, daher läuft alles clientseitig.
  const felder = useMemo(() => eingangsrechnungFelder(), []);
  const zustand = useFilterZustand({ felder });
  const { setBedingungen } = zustand;

  // Arbeitsliste: ohne Filter/Suche in der URL einmalig "Status ist Offen, Entwurf" voreinstellen.
  const startGesetzt = useRef(false);
  const ohneFilterInUrl = !params.has("f") && !params.has("q");
  useEffect(() => {
    if (startGesetzt.current) return;
    startGesetzt.current = true;
    if (ohneFilterInUrl) setBedingungen([{ feld: "status", op: "ist", wert: ["offen", "entwurf"] }]);
  }, [ohneFilterInUrl, setBedingungen]);

  const sichtbar = useMemo(
    () =>
      sucheAnwenden(filterAnwenden(data ?? [], zustand.bedingungen, felder), zustand.sucheVerzoegert, (e) =>
        [
          e.lieferant_name,
          e.rechnungsnummer_lieferant,
          EINGANG_STATUS_LABEL[e.status],
          e.kategorie ? EINGANG_KATEGORIE_LABEL[e.kategorie] : "",
          e.rechnungsdatum,
          new Date(e.rechnungsdatum).toLocaleDateString("de-DE"),
          e.betrag_brutto,
        ].join(" "),
      ),
    [data, zustand.bedingungen, zustand.sucheVerzoegert, felder],
  );
  const keineDaten = !isLoading && !error && (data ?? []).length === 0;

  const heute = new Date();
  const kennzahlen = useMemo(() => eingangsKennzahlen(data ?? [], new Date()), [data]);

  const oeffne = (rechnungId: string) => navigate({ pathname: `/rechnungseingang/${rechnungId}`, search });
  const schliessen = () => {
    if (id) navigate({ pathname: "/rechnungseingang", search });
  };

  const csvExport = useMutation({
    mutationFn: exportApi.eingangsrechnungenCsv,
    onSuccess: (blob) => downloadBlob(blob, "Eingangsrechnungen.csv"),
  });

  const importMutation = useMutation({
    mutationFn: async (dateien: File[]) => {
      const fehler: string[] = [];
      let letzte: Eingangsrechnung | null = null;
      let erfolge = 0;
      for (const datei of dateien) {
        const vorab = pruefeERechnungDatei(datei);
        if (vorab) {
          fehler.push(`${datei.name}: ${vorab}`);
          continue;
        }
        try {
          letzte = await eingangsrechnungenApi.eRechnungImport(datei);
          erfolge += 1;
          toast.erfolg(`Importiert: ${datei.name}`);
        } catch (err) {
          fehler.push(`${datei.name}: ${err instanceof ApiError ? err.message : "Import fehlgeschlagen"}`);
        }
      }
      return { fehler, erfolge, letzte };
    },
    onSuccess: ({ fehler, erfolge, letzte }) => {
      setImportFehler(fehler);
      if (erfolge > 0) queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
      if (erfolge === 1 && letzte) oeffne(letzte.id);
    },
  });

  function importiere(dateien: File[]) {
    if (!kannErstellen || dateien.length === 0) return;
    importMutation.mutate(dateien);
  }

  const hatDateien = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
  const dragHandler = kannErstellen
    ? {
        onDragEnter: (e: DragEvent) => {
          if (!hatDateien(e)) return;
          e.preventDefault();
          ziehZaehler.current += 1;
          setZiehend(true);
        },
        onDragOver: (e: DragEvent) => {
          if (!hatDateien(e)) return;
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
        },
        onDragLeave: (e: DragEvent) => {
          if (!hatDateien(e)) return;
          ziehZaehler.current = Math.max(0, ziehZaehler.current - 1);
          if (ziehZaehler.current === 0) setZiehend(false);
        },
        onDrop: (e: DragEvent) => {
          if (!hatDateien(e)) return;
          e.preventDefault();
          ziehZaehler.current = 0;
          setZiehend(false);
          importiere(Array.from(e.dataTransfer.files));
        },
      }
    : {};

  const kategorieLabel = (e: Eingangsrechnung) => (e.kategorie ? EINGANG_KATEGORIE_LABEL[e.kategorie] : "–");

  const aussteller: Spalte<Eingangsrechnung> = {
    key: "lieferant",
    label: "Aussteller",
    haupt: true,
    sortWert: (e) => e.lieferant_name,
    render: (e) =>
      id ? (
        <span className="block">
          <span className="block">{e.lieferant_name}</span>
          <span className="block text-meta font-normal text-label2">{e.rechnungsnummer_lieferant}</span>
        </span>
      ) : (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          {e.lieferant_name}
          {e.hat_xml && <StatusPille status="neu" label="E-Rechnung" />}
          {e.import_hinweis && <StatusPille status="arbeit" label="Prüfen" />}
        </span>
      ),
  };
  const nummer: Spalte<Eingangsrechnung> = {
    key: "nummer",
    label: "Rechnungsnr.",
    sortWert: (e) => e.rechnungsnummer_lieferant,
    render: (e) => <span className="whitespace-nowrap text-label2">{e.rechnungsnummer_lieferant}</span>,
  };
  const rechnungsdatum: Spalte<Eingangsrechnung> = {
    key: "rechnungsdatum",
    label: "Rechnungsdatum",
    sortWert: (e) => e.rechnungsdatum.slice(0, 10),
    render: (e) => <span className="whitespace-nowrap">{tag(e.rechnungsdatum)}</span>,
  };
  const faellig: Spalte<Eingangsrechnung> = {
    key: "faellig",
    label: "Fällig",
    // Ohne Fälligkeit ans Ende der aufsteigenden Sortierung.
    sortWert: (e) => e.faellig_am?.slice(0, 10) ?? "9999-12-31",
    render: (e) =>
      istUeberfaellig(e) ? (
        <span className="whitespace-nowrap font-semibold text-st-fehlt">
          {tag(e.faellig_am)}
          <span className="sr-only"> (überfällig)</span>
        </span>
      ) : (
        <span className="whitespace-nowrap">{tag(e.faellig_am)}</span>
      ),
  };
  const skonto: Spalte<Eingangsrechnung> = {
    key: "skonto",
    label: "Skonto bis",
    sortWert: (e) => e.skonto_frist?.slice(0, 10) ?? "9999-12-31",
    render: (e) =>
      e.skonto_frist && e.skonto_prozent ? (
        <span className="whitespace-nowrap text-tint-text">
          {formatDatum(e.skonto_frist, true)} · {Number(e.skonto_prozent).toLocaleString("de-DE")} %
        </span>
      ) : (
        <span className="text-label3">–</span>
      ),
  };
  const kategorie: Spalte<Eingangsrechnung> = {
    key: "kategorie",
    label: "Kategorie",
    sortWert: kategorieLabel,
    render: (e) => <span className="text-label2">{kategorieLabel(e)}</span>,
  };
  const netto: Spalte<Eingangsrechnung> = {
    key: "netto",
    label: "Netto",
    align: "rechts",
    sortWert: (e) => Number(e.betrag_netto),
    render: (e) => <span className="whitespace-nowrap">{EURO.format(Number(e.betrag_netto))}</span>,
  };
  const brutto: Spalte<Eingangsrechnung> = {
    key: "betrag",
    label: "Brutto",
    align: "rechts",
    sortWert: (e) => Number(e.betrag_brutto),
    render: (e) => <span className="whitespace-nowrap font-semibold">{EURO.format(Number(e.betrag_brutto))}</span>,
  };
  const offen: Spalte<Eingangsrechnung> = {
    key: "offen",
    label: "Offen",
    align: "rechts",
    sortWert: (e) => Number(e.offener_betrag),
    render: (e) => (
      <span className="whitespace-nowrap">{Number(e.offener_betrag) === 0 ? "–" : EURO.format(Number(e.offener_betrag))}</span>
    ),
  };
  const status: Spalte<Eingangsrechnung> = {
    key: "status",
    label: "Status",
    sortWert: (e) => EINGANG_STATUS_LABEL[e.status],
    render: (e) => <StatusPille status={eingangStatusToken(e.status) ?? "neu"} label={EINGANG_STATUS_LABEL[e.status]} />,
  };

  const spalten: Spalte<Eingangsrechnung>[] = id
    ? [aussteller, faellig, brutto, offen, status]
    : breit
      ? [aussteller, nummer, rechnungsdatum, faellig, skonto, kategorie, netto, brutto, offen, status]
      : mittel
        ? [aussteller, nummer, rechnungsdatum, faellig, skonto, brutto, offen, status]
        : [aussteller, nummer, faellig, brutto, offen, status];

  const filterSetzen = (b: FilterBedingung[]) => setBedingungen(b);
  const statusOffen: FilterBedingung = { feld: "status", op: "ist", wert: ["offen"] };

  const k = kennzahlen;
  const monat = heute.toLocaleDateString("de-DE", { month: "long" });

  const panel = id ? (
    <div className="pt-3">
      <EingangsrechnungDetailPage key={id} id={id} layout="dicht" />
    </div>
  ) : null;
  const ganzeSeite = id ? (
    <button
      type="button"
      onClick={() => navigate(`/rechnungseingang/${id}/vollbild`)}
      className="flex items-center gap-1.5 rounded-lg border border-sep px-2.5 py-1 text-meta font-medium text-label2 hover:text-label"
    >
      <ExternalLink size={13} strokeWidth={2} aria-hidden="true" />
      Ganze Seite
    </button>
  ) : null;

  const importKnopf = kannErstellen && (
    <button
      type="button"
      onClick={() => importInputRef.current?.click()}
      disabled={importMutation.isPending}
      className="btn-touch btn-ap px-4"
    >
      <FileUp size={14} strokeWidth={2} aria-hidden="true" />
      {importMutation.isPending ? "Importiert…" : "E-Rechnung importieren"}
    </button>
  );
  const anlegenKnopf = kannErstellen && (
    <button type="button" onClick={() => setNeu(true)} className={NEU_BUTTON_KLASSE}>
      <Plus size={13} strokeWidth={2.5} aria-hidden="true" />
      Neue Eingangsrechnung
    </button>
  );

  let liste;
  if (isLoading) {
    liste = <SkeletonList count={6} />;
  } else if (error && !data) {
    liste = <FehlerZustand fehler={error} was="Die Eingangsrechnungen" onErneut={() => void refetch()} />;
  } else if (keineDaten) {
    liste = (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 rounded-[var(--radius-ap-card)] border-2 border-dashed border-sepstrong p-8 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-fill text-label2">
          <Inbox size={26} strokeWidth={1.75} aria-hidden="true" />
        </span>
        <p className="text-fliess font-semibold text-label">Noch keine Eingangsrechnungen</p>
        <p className="max-w-lg text-sekundaer text-label2">
          Ziehe E-Rechnungen (XRechnung/ZUGFeRD) hierher oder lege eine Rechnung von Hand an. Rechnungen, die per
          E-Mail ins Postfach kommen, erscheinen hier automatisch.
        </p>
        {kannErstellen && (
          <div className="mt-1 flex flex-wrap justify-center gap-2">
            {importKnopf}
            <button type="button" onClick={() => setNeu(true)} className="btn-touch btn-ap px-4">
              <Plus size={13} strokeWidth={2.5} aria-hidden="true" />
              Neue Eingangsrechnung
            </button>
          </div>
        )}
      </div>
    );
  } else if (sichtbar.length === 0) {
    liste = (
      <EmptyState
        icon={Search}
        text={
          zustand.suche.trim() && zustand.aktiveAnzahl === 0
            ? `Nichts gefunden für „${zustand.suche.trim()}“.`
            : "Keine Treffer für diese Filter."
        }
        action={
          <button type="button" onClick={zustand.zuruecksetzen} className="btn-ap px-4 py-2 text-sekundaer">
            Filter zurücksetzen
          </button>
        }
      />
    );
  } else {
    liste = (
      <SortierbareTabelle
        zeilen={sichtbar}
        spalten={spalten}
        zeilenKey={(e) => e.id}
        gewaehlt={id}
        onWaehlen={(e) => oeffne(e.id)}
        startSortierung={{ key: "faellig" }}
        hervorgehoben={zustand.bedingungen.map((b) => b.feld)}
      />
    );
  }

  return (
    <div {...dragHandler}>
      <SeitenKopf titel="Rechnungseingang" anzahl={isLoading || error ? undefined : sichtbar.length}>
        {kannErstellen && (
          <input
            ref={importInputRef}
            type="file"
            multiple
            accept={ANNAHME}
            className="hidden"
            aria-label="E-Rechnung auswählen"
            onChange={(e) => {
              const dateien = Array.from(e.target.files ?? []);
              e.target.value = "";
              importiere(dateien);
            }}
          />
        )}
        {importKnopf}
        {anlegenKnopf}
        <AktionsMenue
          label="Weitere Aktionen"
          eintraege={[
            {
              label: "Als CSV exportieren",
              icon: FileDown,
              disabled: csvExport.isPending,
              onClick: () => csvExport.mutate(),
            },
          ]}
        />
      </SeitenKopf>

      <AnlegenPanel offen={neu} titel="Neue Eingangsrechnung" onClose={() => setNeu(false)}>
        <NeueEingangsrechnungForm
          onAngelegt={(e) => {
            setNeu(false);
            oeffne(e.id);
          }}
        />
      </AnlegenPanel>

      {importFehler.length > 0 && (
        <div className="mb-4">
          <Hinweiskasten ton="fehler" titel="Nicht importiert">
            {importFehler.map((zeile) => (
              <p key={zeile}>{zeile}</p>
            ))}
          </Hinweiskasten>
        </div>
      )}

      {!keineDaten && !isLoading && !error && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-4 xl:grid-cols-4">
            <KennzahlKarte
              label="Offen"
              icon={Wallet}
              wert={EURO.format(k.offen.summe)}
              zusatz={rechnungen(k.offen.anzahl)}
              onClick={() => filterSetzen([statusOffen])}
            />
            <KennzahlKarte
              label="Überfällig"
              icon={AlarmClock}
              wert={EURO.format(k.ueberfaellig.summe)}
              ton={k.ueberfaellig.anzahl > 0 ? "warnung" : "neutral"}
              zusatz={
                k.ueberfaellig.anzahl > 0
                  ? `${rechnungen(k.ueberfaellig.anzahl)} · seit ${k.ueberfaellig.aeltesteTage === 1 ? "1 Tag" : `${k.ueberfaellig.aeltesteTage} Tagen`}`
                  : "keine"
              }
              onClick={() => filterSetzen([statusOffen, { feld: "faellig", op: "vor", wert: heuteIso() }])}
            />
            <KennzahlKarte
              label="Skonto nutzbar (7 Tage)"
              icon={Percent}
              wert={rechnungen(k.skonto.anzahl)}
              ton={k.skonto.anzahl > 0 ? "gut" : "neutral"}
              zusatz={k.skonto.anzahl > 0 ? `bis zu ${EURO.format(k.skonto.ersparnis)} sparen` : "keine"}
              onClick={() => filterSetzen([statusOffen])}
            />
            <KennzahlKarte
              label={`Bezahlt im ${monat}`}
              icon={CircleCheck}
              wert={EURO.format(k.bezahltImMonat.summe)}
              zusatz={rechnungen(k.bezahltImMonat.anzahl)}
              onClick={() => filterSetzen([{ feld: "status", op: "ist", wert: ["bezahlt"] }])}
            />
          </div>

          <FilterLeiste
            felder={felder}
            zustand={zustand}
            variante="office"
            suchPlatzhalter="Aussteller oder Nr. suchen…"
            className="mb-4"
          />
        </>
      )}

      <div className={`relative ${ziehend ? "min-h-[18rem]" : ""}`}>
        <ListeMitPanel panelTitel="Eingangsrechnung" panel={panel} kopfAktionen={ganzeSeite} onSchliessen={schliessen} liste={liste} />
        {ziehend && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-1 rounded-[var(--radius-ap-card)] border-2 border-dashed border-tint bg-card"
          >
            <div className="absolute inset-0 rounded-[inherit] bg-tintbg" />
            <FileUp size={34} strokeWidth={1.75} className="relative text-tint-text" />
            <p className="relative text-fliess font-semibold text-tint-text">E-Rechnungen hier ablegen</p>
            <p className="relative text-sekundaer text-label2">
              XRechnung (XML) oder ZUGFeRD (PDF) · mehrere Dateien möglich
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
