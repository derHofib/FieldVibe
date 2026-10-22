import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileUp, Undo2 } from "lucide-react";
import { Navigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { datenimportApi } from "../../api/endpoints";
import { FilterChip } from "../../components/apple/FilterChip";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { useAuth } from "../../context/AuthContext";
import { downloadBlob } from "../../utils/download";
import { KennzahlKarte, Karte, SeitenKopf, TabellenRahmen } from "../OfficeUi";
import {
  AKTION_LABEL,
  ENTITAET_LABEL,
  LAUF_STATUS_LABEL,
  SCHRITT_TITEL,
  STATUS_LABEL,
  type Mapping,
  type Schritt,
  type ZeilenFilter,
  dateigroesseText,
  darfAusfuehren,
  konfigurationBauen,
  mappingAusVorschlag,
  offenePflichtGruppen,
  pflichtLabel,
  schrittErreichbar,
  spalteZuweisen,
  standardAktionen,
  statusAnzahl,
  zeilenFiltern,
} from "./datenimportUtils";
import type {
  DublettenAktion,
  ImportAnalyse,
  ImportEntitaet,
  ImportErgebnis,
  ImportLauf,
  ImportModus,
  ZeilenStatus,
} from "./typen";
import { bestaetigen } from "../../components/apple/BestaetigungsDialog";

const STATUS_KLASSE: Record<ZeilenStatus, string> = {
  neu: "bg-st-neu-bg text-st-neu-text",
  warnung: "bg-st-arbeit-bg text-st-arbeit-text",
  dublette: "bg-fill text-label",
  fehler: "bg-st-fehlt-bg text-st-fehlt-text",
};

function fehlerText(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof DOMException && err.name === "AbortError") {
    return "Die Verarbeitung dauert zu lange. Bitte die Datei in kleinere Teile aufteilen.";
  }
  return "Unerwarteter Fehler – bitte erneut versuchen.";
}

export function OfficeDatenimportPage() {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();

  const [schritt, setSchritt] = useState<Schritt>(1);
  const [entitaet, setEntitaet] = useState<ImportEntitaet>("kunden");
  const [datei, setDatei] = useState<File | null>(null);
  const [analyse, setAnalyse] = useState<ImportAnalyse | null>(null);
  const [mapping, setMapping] = useState<Mapping>({});
  const [modus, setModus] = useState<ImportModus>("gueltige");
  const [aktionen, setAktionen] = useState<Record<string, DublettenAktion>>({});
  const [probe, setProbe] = useState<ImportErgebnis | null>(null);
  const [ergebnis, setErgebnis] = useState<ImportErgebnis | null>(null);
  const [filter, setFilter] = useState<ZeilenFilter>("alle");
  const [fehler, setFehler] = useState<string | null>(null);
  const [rueckgaengigErgebnis, setRueckgaengigErgebnis] = useState<ImportLauf | null>(null);

  const laeufe = useQuery({ queryKey: ["datenimport-laeufe"], queryFn: () => datenimportApi.laeufe() });

  const offeneGruppen = useMemo(
    () => (analyse ? offenePflichtGruppen(mapping, analyse.pflicht_gruppen) : []),
    [analyse, mapping],
  );
  const konfig = konfigurationBauen(mapping, modus, aktionen);

  const analyseMutation = useMutation({
    mutationFn: (blatt?: string | null) => datenimportApi.analyse(datei as File, entitaet, blatt),
    onSuccess: (a) => {
      if (analyse && analyse.import_lauf_id !== a.import_lauf_id) {
        void datenimportApi.verwerfen(analyse.import_lauf_id).catch(() => undefined);
      }
      setAnalyse(a);
      setMapping(mappingAusVorschlag(a.vorschlag));
      setAktionen(standardAktionen(a.dubletten_arten));
      setProbe(null);
      setErgebnis(null);
      setFehler(null);
      setSchritt(2);
      void queryClient.invalidateQueries({ queryKey: ["datenimport-laeufe"] });
    },
    onError: (err) => setFehler(fehlerText(err)),
  });

  const probeMutation = useMutation({
    mutationFn: () => datenimportApi.probelauf((analyse as ImportAnalyse).import_lauf_id, konfig),
    onSuccess: (e) => {
      setProbe(e);
      setFilter(e.zusammenfassung.fehler > 0 ? "fehler" : "alle");
      setFehler(null);
      setSchritt(3);
    },
    onError: (err) => setFehler(fehlerText(err)),
  });

  const ausfuehrenMutation = useMutation({
    mutationFn: () => datenimportApi.ausfuehren((analyse as ImportAnalyse).import_lauf_id, konfig),
    onSuccess: (e) => {
      setErgebnis(e);
      setFehler(null);
      setSchritt(4);
      void queryClient.invalidateQueries({ queryKey: ["datenimport-laeufe"] });
    },
    onError: (err) => setFehler(fehlerText(err)),
  });

  const rueckgaengigMutation = useMutation({
    mutationFn: (id: string) => datenimportApi.rueckgaengig(id),
    onSuccess: (lauf) => {
      setRueckgaengigErgebnis(lauf);
      setFehler(null);
      void queryClient.invalidateQueries({ queryKey: ["datenimport-laeufe"] });
    },
    onError: (err) => setFehler(fehlerText(err)),
  });

  if (currentUser && currentUser.role !== "mandant_admin") {
    return <Navigate to="/vorgaenge" replace />;
  }

  async function herunterladen(laden: () => Promise<Blob>, name: string) {
    try {
      downloadBlob(await laden(), name);
    } catch (err) {
      setFehler(fehlerText(err));
    }
  }

  function neuerImport() {
    setSchritt(1);
    setDatei(null);
    setAnalyse(null);
    setProbe(null);
    setErgebnis(null);
    setRueckgaengigErgebnis(null);
    setFehler(null);
  }

  const abgeschlossen = ergebnis !== null;
  const erreichbar = (s: Schritt) =>
    schrittErreichbar(s, {
      analyse,
      mappingGueltig: offeneGruppen.length === 0,
      probelaufErfolgt: probe !== null,
      abgeschlossen,
    });
  const beschaeftigt = analyseMutation.isPending || probeMutation.isPending || ausfuehrenMutation.isPending;

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <SeitenKopf titel="Datenimport">
        <button
          type="button"
          className="btn-ap inline-flex h-8 items-center gap-1.5 px-3 text-[13px]"
          onClick={() => herunterladen(() => datenimportApi.vorlage(entitaet), `Vorlage-${ENTITAET_LABEL[entitaet]}.csv`)}
        >
          <Download size={14} aria-hidden="true" /> Vorlage herunterladen
        </button>
      </SeitenKopf>

      <nav aria-label="Importschritte">
        <ol className="flex flex-wrap gap-2">
          {([1, 2, 3, 4] as Schritt[]).map((s) => {
            const aktiv = s === schritt;
            return (
              <li key={s}>
                <button
                  type="button"
                  aria-current={aktiv ? "step" : undefined}
                  disabled={!erreichbar(s) || beschaeftigt}
                  onClick={() => setSchritt(s)}
                  className={`h-8 rounded-full px-3 text-[13px] font-semibold disabled:opacity-50 ${
                    aktiv ? "bg-tint-solid text-white" : "bg-fill text-label"
                  }`}
                >
                  {s}. {SCHRITT_TITEL[s]}
                </button>
              </li>
            );
          })}
        </ol>
      </nav>

      {fehler && (
        <Hinweiskasten ton="fehler">
          <p>{fehler}</p>
        </Hinweiskasten>
      )}

      {schritt === 1 && (
        <Karte className="space-y-4 p-5">
          <h2 className="ap-heading text-lg font-semibold text-label">1. Datei und Typ wählen</h2>
          <fieldset>
            <legend className="mb-2 text-sm font-semibold text-label">Was soll importiert werden?</legend>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(ENTITAET_LABEL) as ImportEntitaet[]).map((key) => (
                <label
                  key={key}
                  className={`flex cursor-pointer items-center gap-2 rounded-[var(--radius-ap-md)] px-3 py-2 text-sm ${
                    entitaet === key ? "bg-tint-solid text-white" : "bg-fill text-label"
                  }`}
                >
                  <input
                    type="radio"
                    name="entitaet"
                    value={key}
                    checked={entitaet === key}
                    onChange={() => setEntitaet(key)}
                    className="sr-only"
                  />
                  {ENTITAET_LABEL[key]}
                </label>
              ))}
            </div>
            <p className="mt-2 text-xs text-label2">
              Reihenfolge-Tipp: zuerst Kunden, danach Standorte & Anlagen (die den Kunden brauchen), Material ist unabhängig.
            </p>
          </fieldset>
          <div>
            <label htmlFor="import-datei" className="mb-1 block text-sm font-semibold text-label">
              Datei (CSV oder XLSX, max. 10 MB / 20.000 Zeilen)
            </label>
            <input
              id="import-datei"
              type="file"
              accept=".csv,.txt,.tsv,.xlsx"
              onChange={(e) => setDatei(e.target.files?.[0] ?? null)}
              className="field-ap w-full text-sm"
            />
            {datei && (
              <p className="mt-1 text-xs text-label2">
                {datei.name} · {dateigroesseText(datei.size)}
              </p>
            )}
          </div>
          <button
            type="button"
            className="btn-ap-primary inline-flex h-9 items-center gap-2 px-4 text-sm font-semibold disabled:opacity-50"
            disabled={!datei || analyseMutation.isPending}
            onClick={() => analyseMutation.mutate(undefined)}
          >
            <FileUp size={15} aria-hidden="true" />
            {analyseMutation.isPending ? "Datei wird analysiert …" : "Datei analysieren"}
          </button>
        </Karte>
      )}

      {schritt === 2 && analyse && (
        <Karte className="space-y-4 p-5">
          <h2 className="ap-heading text-lg font-semibold text-label">2. Spalten zuordnen</h2>
          <p className="text-sm text-label2">
            {analyse.dateiname} · {analyse.zeilen_gesamt.toLocaleString("de-DE")} Zeilen · {analyse.format.toUpperCase()}
            {analyse.kodierung ? ` · ${analyse.kodierung}` : ""}
            {analyse.trennzeichen ? ` · Trennzeichen ${analyse.trennzeichen === "\t" ? "Tab" : analyse.trennzeichen}` : ""}
          </p>
          {analyse.blaetter.length > 1 && (
            <div>
              <label htmlFor="import-blatt" className="mb-1 block text-sm font-semibold text-label">
                Tabellenblatt
              </label>
              <select
                id="import-blatt"
                className="field-ap"
                value={analyse.blatt ?? ""}
                onChange={(e) => analyseMutation.mutate(e.target.value)}
              >
                {analyse.blaetter.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </div>
          )}
          <Hinweiskasten ton="info">
            <p>Die Zuordnung wurde anhand der Spaltenüberschriften vorgeschlagen. Bitte prüfen und bei Bedarf ändern.</p>
          </Hinweiskasten>
          {offeneGruppen.length > 0 && (
            <Hinweiskasten ton="fehler" titel="Pflichtangaben fehlen">
              <ul className="list-disc pl-4">
                {offeneGruppen.map((g) => (
                  <li key={g.join()}>{pflichtLabel(analyse, g)}</li>
                ))}
              </ul>
            </Hinweiskasten>
          )}
          <TabellenRahmen>
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Zuordnung der Dateispalten zu den Feldern</caption>
              <thead className="bg-fill text-xs text-label2">
                <tr>
                  <th scope="col" className="px-3 py-2">Feld</th>
                  <th scope="col" className="px-3 py-2">Spalte in der Datei</th>
                  <th scope="col" className="px-3 py-2">Beispielwerte</th>
                </tr>
              </thead>
              <tbody>
                {analyse.felder.map((feld) => {
                  const spalte = mapping[feld.key];
                  const vorschlag = analyse.vorschlag.find((v) => v.feld === feld.key);
                  const beispiele = spalte != null ? analyse.spalten[spalte]?.beispiele ?? [] : [];
                  return (
                    <tr key={feld.key} className="border-t border-sep align-top">
                      <th scope="row" className="px-3 py-2 font-medium text-label">
                        <label htmlFor={`feld-${feld.key}`}>
                          {feld.label}
                          {feld.pflicht && <span aria-hidden="true"> *</span>}
                        </label>
                        {feld.hinweis && <p className="text-xs font-normal text-label2">{feld.hinweis}</p>}
                      </th>
                      <td className="px-3 py-2">
                        <select
                          id={`feld-${feld.key}`}
                          className="field-ap w-full max-w-xs"
                          value={spalte ?? ""}
                          onChange={(e) =>
                            setMapping((m) => spalteZuweisen(m, feld.key, e.target.value === "" ? null : Number(e.target.value)))
                          }
                        >
                          <option value="">– nicht importieren –</option>
                          {analyse.spalten.map((s) => (
                            <option key={s.index} value={s.index}>
                              {s.name}
                            </option>
                          ))}
                        </select>
                        {vorschlag?.sicherheit === "vermutet" && spalte === vorschlag.spalte && (
                          <p className="mt-1 text-xs text-label2">Vermutete Zuordnung – bitte prüfen</p>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs text-label2">
                        {beispiele.length > 0 ? beispiele.join(" · ") : "–"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TabellenRahmen>

          <fieldset className="space-y-2">
            <legend className="text-sm font-semibold text-label">Dubletten</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {analyse.dubletten_arten.map((art) => (
                <div key={art.key}>
                  <label htmlFor={`dublette-${art.key}`} className="mb-1 block text-xs text-label2">
                    {art.label}
                  </label>
                  <select
                    id={`dublette-${art.key}`}
                    className="field-ap w-full"
                    value={aktionen[art.key] ?? art.standard}
                    onChange={(e) => setAktionen((a) => ({ ...a, [art.key]: e.target.value as DublettenAktion }))}
                  >
                    {art.aktionen.map((a) => (
                      <option key={a} value={a}>
                        {AKTION_LABEL[a]}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="mb-1 text-sm font-semibold text-label">Bei fehlerhaften Zeilen</legend>
            <label className="mr-4 inline-flex items-center gap-2 text-sm">
              <input type="radio" name="modus" checked={modus === "gueltige"} onChange={() => setModus("gueltige")} />
              Gültige Zeilen importieren, Fehler als Bericht ausgeben
            </label>
            <label className="inline-flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="modus"
                checked={modus === "alles_oder_nichts"}
                onChange={() => setModus("alles_oder_nichts")}
              />
              Alles oder nichts
            </label>
          </fieldset>

          <div className="flex gap-2">
            <button type="button" className="btn-ap h-9 px-4 text-sm" onClick={() => setSchritt(1)}>
              Zurück
            </button>
            <button
              type="button"
              className="btn-ap-primary h-9 px-4 text-sm font-semibold disabled:opacity-50"
              disabled={offeneGruppen.length > 0 || probeMutation.isPending}
              onClick={() => probeMutation.mutate()}
            >
              {probeMutation.isPending ? "Probelauf läuft …" : "Probelauf starten"}
            </button>
          </div>
        </Karte>
      )}

      {schritt === 3 && analyse && probe && (
        <Karte className="space-y-4 p-5">
          <h2 className="ap-heading text-lg font-semibold text-label">3. Probelauf – es wurde noch nichts importiert</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <KennzahlKarte label="Neu" wert={String(probe.zusammenfassung.neu)} />
            <KennzahlKarte label="Mit Warnung" wert={String(probe.zusammenfassung.warnung)} ton={probe.zusammenfassung.warnung ? "warnung" : "neutral"} />
            <KennzahlKarte label="Dubletten" wert={String(probe.zusammenfassung.dublette)} />
            <KennzahlKarte label="Fehler" wert={String(probe.zusammenfassung.fehler)} ton={probe.zusammenfassung.fehler ? "warnung" : "gut"} />
          </div>
          <p className="text-sm text-label2">
            Der Import würde {probe.zusammenfassung.anlegen} Datensätze anlegen
            {probe.zusammenfassung.aktualisieren > 0 ? `, ${probe.zusammenfassung.aktualisieren} ergänzen` : ""} und{" "}
            {probe.zusammenfassung.ueberspringen + probe.zusammenfassung.fehler} Zeilen auslassen.
          </p>
          {modus === "alles_oder_nichts" && probe.zusammenfassung.fehler > 0 && (
            <Hinweiskasten ton="warnung">
              <p>Im Modus „alles oder nichts“ wird bei Fehlern nichts importiert. Bitte die Datei korrigieren oder den Modus ändern.</p>
            </Hinweiskasten>
          )}
          <div className="flex flex-wrap gap-2" role="group" aria-label="Zeilen filtern">
            {(["alle", "neu", "warnung", "dublette", "fehler"] as ZeilenFilter[]).map((f) => (
              <FilterChip
                key={f}
                label={f === "alle" ? "Alle" : STATUS_LABEL[f]}
                anzahl={statusAnzahl(probe.zusammenfassung, f)}
                aktiv={filter === f}
                onClick={() => setFilter(f)}
              />
            ))}
          </div>
          <TabellenRahmen>
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Ergebnis des Probelaufs je Zeile</caption>
              <thead className="bg-fill text-xs text-label2">
                <tr>
                  <th scope="col" className="px-3 py-2">Zeile</th>
                  <th scope="col" className="px-3 py-2">Status</th>
                  <th scope="col" className="px-3 py-2">Daten</th>
                  <th scope="col" className="px-3 py-2">Meldung</th>
                </tr>
              </thead>
              <tbody>
                {zeilenFiltern(probe.zeilen, filter).map((z) => (
                  <tr key={z.zeile} className="border-t border-sep align-top">
                    <td className="px-3 py-2 tabular-nums">{z.zeile}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_KLASSE[z.status]}`}>
                        {STATUS_LABEL[z.status]}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-label2">{Object.values(z.vorschau).join(" · ") || "–"}</td>
                    <td className="px-3 py-2 text-xs">{z.meldungen.join(" · ") || "–"}</td>
                  </tr>
                ))}
                {zeilenFiltern(probe.zeilen, filter).length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 py-4 text-center text-label2">
                      Keine Zeilen in dieser Ansicht.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </TabellenRahmen>
          {probe.zeilen_gekuerzt && (
            <p className="text-xs text-label2">
              Aus Platzgründen werden je Status nur die ersten Zeilen angezeigt; der vollständige Bericht steht als CSV bereit.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-ap h-9 px-4 text-sm" onClick={() => setSchritt(2)}>
              Zuordnung ändern
            </button>
            {probe.zusammenfassung.fehler > 0 && (
              <button
                type="button"
                className="btn-ap h-9 px-4 text-sm"
                onClick={() => herunterladen(() => datenimportApi.fehlerbericht(analyse.import_lauf_id), "Fehlerbericht.csv")}
              >
                Fehlerbericht (CSV)
              </button>
            )}
            <button
              type="button"
              className="btn-ap-primary h-9 px-4 text-sm font-semibold disabled:opacity-50"
              disabled={!darfAusfuehren(probe.zusammenfassung, modus) || ausfuehrenMutation.isPending}
              onClick={() => ausfuehrenMutation.mutate()}
            >
              {ausfuehrenMutation.isPending ? "Import läuft …" : "Import ausführen"}
            </button>
          </div>
        </Karte>
      )}

      {schritt === 4 && analyse && ergebnis && (
        <Karte className="space-y-4 p-5">
          <h2 className="ap-heading text-lg font-semibold text-label">4. Ergebnis</h2>
          {ergebnis.status === "abgeschlossen" ? (
            <Hinweiskasten ton="info" titel="Import abgeschlossen">
              <p>
                {ergebnis.zusammenfassung.anlegen} angelegt
                {ergebnis.zusammenfassung.aktualisieren > 0 ? `, ${ergebnis.zusammenfassung.aktualisieren} ergänzt` : ""},{" "}
                {ergebnis.zusammenfassung.ueberspringen} übersprungen, {ergebnis.zusammenfassung.fehler} fehlerhaft.
              </p>
            </Hinweiskasten>
          ) : (
            <Hinweiskasten ton="fehler" titel="Import abgebrochen">
              <p>{ergebnis.abbruch ?? "Es wurde nichts importiert."}</p>
            </Hinweiskasten>
          )}
          {rueckgaengigErgebnis && (
            <Hinweiskasten ton="info" titel="Import rückgängig gemacht">
              <p>
                Zurückgesetzt:{" "}
                {Object.entries(rueckgaengigErgebnis.ergebnis?.rueckgaengig?.zurueckgesetzt ?? {})
                  .map(([typ, n]) => `${n} × ${typ}`)
                  .join(", ") || "nichts"}
                . Nicht zurückgesetzt (seit dem Import geändert oder in Benutzung):{" "}
                {rueckgaengigErgebnis.ergebnis?.rueckgaengig?.uebersprungen_gesamt ?? 0}. Die Datensätze liegen im Papierkorb.
              </p>
            </Hinweiskasten>
          )}
          <div className="flex flex-wrap gap-2">
            {ergebnis.zusammenfassung.fehler > 0 && (
              <button
                type="button"
                className="btn-ap h-9 px-4 text-sm"
                onClick={() => herunterladen(() => datenimportApi.fehlerbericht(analyse.import_lauf_id), "Fehlerbericht.csv")}
              >
                Fehlerliste herunterladen (CSV)
              </button>
            )}
            {ergebnis.status === "abgeschlossen" && !rueckgaengigErgebnis && (
              <button
                type="button"
                className="btn-ap inline-flex h-9 items-center gap-1.5 px-4 text-sm"
                disabled={rueckgaengigMutation.isPending}
                onClick={async () => {
                  if (await bestaetigen("Alle durch diesen Import angelegten, seither unveränderten Datensätze in den Papierkorb legen?")) {
                    rueckgaengigMutation.mutate(analyse.import_lauf_id);
                  }
                }}
              >
                <Undo2 size={14} aria-hidden="true" /> Import rückgängig machen
              </button>
            )}
            <button type="button" className="btn-ap-primary h-9 px-4 text-sm font-semibold" onClick={neuerImport}>
              Weiteren Import starten
            </button>
          </div>
        </Karte>
      )}

      <section aria-labelledby="import-laeufe-titel" className="space-y-2">
        <h2 id="import-laeufe-titel" className="ap-heading text-lg font-semibold text-label">
          Bisherige Importe
        </h2>
        <TabellenRahmen>
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Liste der bisherigen Importläufe</caption>
            <thead className="bg-fill text-xs text-label2">
              <tr>
                <th scope="col" className="px-3 py-2">Datum</th>
                <th scope="col" className="px-3 py-2">Typ</th>
                <th scope="col" className="px-3 py-2">Datei</th>
                <th scope="col" className="px-3 py-2">Status</th>
                <th scope="col" className="px-3 py-2">Neu / Fehler</th>
                <th scope="col" className="px-3 py-2"><span className="sr-only">Aktionen</span></th>
              </tr>
            </thead>
            <tbody>
              {(laeufe.data ?? []).map((l) => (
                <tr key={l.id} className="border-t border-sep">
                  <td className="px-3 py-2">{new Date(l.created_at).toLocaleString("de-DE")}</td>
                  <td className="px-3 py-2">{ENTITAET_LABEL[l.entitaet]}</td>
                  <td className="px-3 py-2">{l.dateiname}</td>
                  <td className="px-3 py-2">{LAUF_STATUS_LABEL[l.status] ?? l.status}</td>
                  <td className="px-3 py-2 tabular-nums">
                    {l.zeilen_neu} / {l.zeilen_fehler}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span className="inline-flex gap-2">
                      {l.fehlerbericht_verfuegbar && (
                        <button
                          type="button"
                          className="text-[13px] font-medium text-tint-text underline"
                          onClick={() => herunterladen(() => datenimportApi.fehlerbericht(l.id), `Fehlerbericht-${l.dateiname}.csv`)}
                        >
                          Fehlerliste
                        </button>
                      )}
                      {l.kann_rueckgaengig && (
                        <button
                          type="button"
                          className="text-[13px] font-medium text-tint-text underline"
                          onClick={async () => {
                            if (await bestaetigen("Diesen Import rückgängig machen?")) rueckgaengigMutation.mutate(l.id);
                          }}
                        >
                          Rückgängig
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
              {(laeufe.data ?? []).length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-center text-label2">
                    Noch keine Importe.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </TabellenRahmen>
      </section>
    </div>
  );
}
