import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Download, FileSpreadsheet } from "lucide-react";
import { Navigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { exporteApi } from "../../api/endpoints";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { IconBadge } from "../../components/IconBadge";
import { useAuth } from "../../context/AuthContext";
import { dateigroesseText } from "../datenimport/datenimportUtils";
import { Karte, SeitenKopf, TabellenRahmen } from "../OfficeUi";
import {
  ART_LABEL,
  STATUS_KLASSE,
  STATUS_LABEL,
  aktiverExportVorhanden,
  parameterText,
  resttage,
  standardZeitraum,
  zeitraumGueltig,
  type MandantExport,
} from "./exportUtils";

function fehlerText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Unerwarteter Fehler – bitte erneut versuchen.";
}

function zeitText(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

export function OfficeExportPage() {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();
  const standard = standardZeitraum();
  const [von, setVon] = useState(standard.von);
  const [bis, setBis] = useState(standard.bis);
  const [fehler, setFehler] = useState<string | null>(null);

  const liste = useQuery({
    queryKey: ["exporte"],
    queryFn: () => exporteApi.liste(),
    // Solange einer laeuft, alle paar Sekunden nachsehen; sonst Ruhe.
    refetchInterval: (query) => (aktiverExportVorhanden(query.state.data ?? []) ? 3000 : false),
  });

  const anfordern = useMutation({
    mutationFn: (art: "vollexport" | "z3") => (art === "vollexport" ? exporteApi.vollexport() : exporteApi.z3(von, bis)),
    onSuccess: () => {
      setFehler(null);
      void queryClient.invalidateQueries({ queryKey: ["exporte"] });
    },
    onError: (err) => setFehler(fehlerText(err)),
  });

  if (currentUser && currentUser.role !== "mandant_admin") {
    return <Navigate to="/vorgaenge" replace />;
  }

  async function herunterladen(e: MandantExport) {
    try {
      const antwort = await exporteApi.downloadUrl(e.id);
      const a = document.createElement("a");
      a.href = antwort.url;
      a.rel = "noopener";
      a.click();
      setFehler(null);
    } catch (err) {
      setFehler(fehlerText(err));
      void queryClient.invalidateQueries({ queryKey: ["exporte"] });
    }
  }

  const exporte = liste.data ?? [];
  const laeuft = aktiverExportVorhanden(exporte);
  const zeitraumFehler = zeitraumGueltig(von, bis);

  return (
    <div className="mx-auto max-w-[1000px] space-y-5">
      <SeitenKopf titel="Daten exportieren" />

      <p className="text-sm text-label2">
        Exportieren Sie Ihre Daten als ZIP – zur Datenübernahme, zur Übergabe an Ihren Steuerberater oder für die
        Finanzverwaltung. Die Erstellung läuft im Hintergrund; das fertige ZIP ist 7 Tage abrufbar und wird danach
        automatisch entfernt. Jeder Export wird im Protokoll vermerkt.
      </p>

      {fehler && (
        <Hinweiskasten ton="fehler">
          <p>{fehler}</p>
        </Hinweiskasten>
      )}
      {laeuft && (
        <Hinweiskasten ton="info">
          <p>Ein Export wird gerade erstellt. Ein weiterer kann erst danach gestartet werden.</p>
        </Hinweiskasten>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Karte className="space-y-3 p-5">
          <div className="flex items-center gap-3">
            <IconBadge icon={Archive} tone="teal" />
            <h2 className="ap-heading text-lg font-semibold text-label">Vollexport</h2>
          </div>
          <p className="text-sm text-label2">
            Alle Daten Ihres Betriebs (Kunden, Anlagen, Vorgänge, Angebote, Rechnungen, Zeiten, Material, Nutzer ohne
            Passwörter, Einstellungen ohne Zugangsdaten) als CSV und JSON, dazu alle archivierten Belege, Fotos und
            Dokumente. Mit Prüfsummen und Beschreibung (Art. 20 DSGVO).
          </p>
          <button
            type="button"
            className="btn-ap-primary inline-flex h-9 items-center gap-2 px-4 text-sm font-semibold disabled:opacity-50"
            disabled={laeuft || anfordern.isPending}
            onClick={() => anfordern.mutate("vollexport")}
          >
            <Archive size={15} aria-hidden="true" />
            Vollexport anfordern
          </button>
        </Karte>

        <Karte className="space-y-3 p-5">
          <div className="flex items-center gap-3">
            <IconBadge icon={FileSpreadsheet} tone="indigo" />
            <h2 className="ap-heading text-lg font-semibold text-label">Z3-Export (Finanzverwaltung)</h2>
          </div>
          <p className="text-sm text-label2">
            Datenträgerüberlassung für eine Außenprüfung: Rechnungen, Positionen, Zahlungen, Kunden,
            Eingangsrechnungen und Kontenbezüge mit Beschreibungsdatei (index.xml) für IDEA. Bitte vor der Übergabe
            mit Ihrem Steuerberater abstimmen.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor="z3-von" className="mb-1 block text-xs font-semibold text-label2">
                Von
              </label>
              <input id="z3-von" type="date" className="field-ap" value={von} onChange={(e) => setVon(e.target.value)} />
            </div>
            <div>
              <label htmlFor="z3-bis" className="mb-1 block text-xs font-semibold text-label2">
                Bis
              </label>
              <input id="z3-bis" type="date" className="field-ap" value={bis} onChange={(e) => setBis(e.target.value)} />
            </div>
            <button
              type="button"
              className="btn-ap-primary inline-flex h-9 items-center gap-2 px-4 text-sm font-semibold disabled:opacity-50"
              disabled={laeuft || anfordern.isPending || zeitraumFehler !== null}
              onClick={() => anfordern.mutate("z3")}
            >
              <FileSpreadsheet size={15} aria-hidden="true" />
              Z3-Export anfordern
            </button>
          </div>
          {zeitraumFehler && <p className="text-xs text-st-fehlt">{zeitraumFehler}</p>}
        </Karte>
      </div>

      <h2 className="ap-heading text-lg font-semibold text-label">Letzte Exporte</h2>
      <TabellenRahmen>
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Angeforderte Exporte, neueste zuerst</caption>
          <thead className="bg-fill text-xs text-label2">
            <tr>
              <th scope="col" className="px-3 py-2">Art</th>
              <th scope="col" className="px-3 py-2">Angefordert</th>
              <th scope="col" className="px-3 py-2">Status</th>
              <th scope="col" className="px-3 py-2">Größe</th>
              <th scope="col" className="px-3 py-2">Abrufbar noch</th>
              <th scope="col" className="px-3 py-2"><span className="sr-only">Aktion</span></th>
            </tr>
          </thead>
          <tbody>
            {exporte.map((e) => {
              const rest = resttage(e.laeuft_ab_am);
              return (
                <tr key={e.id} className="border-t border-sep align-top">
                  <td className="px-3 py-2 font-medium text-label">
                    {ART_LABEL[e.art]}
                    {parameterText(e) && <span className="block text-xs font-normal text-label2">{parameterText(e)}</span>}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums text-label2">{zeitText(e.angefordert_am)}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${STATUS_KLASSE[e.status]}`}>
                      {STATUS_LABEL[e.status]}
                    </span>
                    {e.fehler && <span className="mt-1 block text-xs text-st-fehlt">{e.fehler}</span>}
                  </td>
                  <td className="px-3 py-2 tabular-nums text-label2">
                    {e.groesse_bytes != null ? dateigroesseText(e.groesse_bytes) : "–"}
                    {e.anzahl_dateien != null && <span className="block text-xs">{e.anzahl_dateien} Dateien</span>}
                  </td>
                  <td className="px-3 py-2 text-label2">
                    {e.status === "fertig" && rest != null ? (rest === 1 ? "1 Tag" : `${rest} Tage`) : "–"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {e.status === "fertig" && (
                      <button
                        type="button"
                        className="btn-ap inline-flex h-8 items-center gap-1.5 px-3 text-[13px]"
                        onClick={() => herunterladen(e)}
                      >
                        <Download size={14} aria-hidden="true" /> Herunterladen
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {liste.isSuccess && exporte.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-label2">
                  Noch kein Export angefordert.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </TabellenRahmen>
      <p className="text-xs text-label2">
        Prüfsumme (SHA-256) und Dateiliste stehen im ZIP in <code>manifest.json</code>; die Summe des gesamten ZIP
        steht im Protokoll.
      </p>
    </div>
  );
}
