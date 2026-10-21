import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Download, ShieldCheck } from "lucide-react";
import { Navigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { protokollApi } from "../../api/endpoints";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { useAuth } from "../../context/AuthContext";
import { downloadBlob } from "../../utils/download";
import { Karte, SeitenKopf, TabellenRahmen } from "../OfficeUi";
import {
  AKTEUR_LABEL,
  aktionLabel,
  detailsText,
  seitenText,
  zeitText,
  type ProtokollFilter,
} from "./protokollUtils";

const SEITENGROESSE = 50;

function fehlerText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Unerwarteter Fehler – bitte erneut versuchen.";
}

export function OfficeProtokollPage() {
  const { currentUser } = useAuth();
  const [filter, setFilter] = useState<ProtokollFilter>({});
  const [offset, setOffset] = useState(0);
  const [fehler, setFehler] = useState<string | null>(null);

  const liste = useQuery({
    queryKey: ["protokoll", filter, offset],
    queryFn: () => protokollApi.liste(filter, SEITENGROESSE, offset),
    placeholderData: (vorher) => vorher,
  });
  const aktionen = useQuery({ queryKey: ["protokoll-aktionen"], queryFn: () => protokollApi.aktionen() });
  const pruefung = useMutation({
    mutationFn: () => protokollApi.verifizieren(),
    onError: (err) => setFehler(fehlerText(err)),
    onSuccess: () => setFehler(null),
  });

  if (currentUser && currentUser.role !== "mandant_admin") {
    return <Navigate to="/vorgaenge" replace />;
  }

  function filterSetzen(neu: ProtokollFilter) {
    setFilter(neu);
    setOffset(0);
  }

  async function csvLaden() {
    try {
      downloadBlob(await protokollApi.csv(filter), "protokoll.csv");
    } catch (err) {
      setFehler(fehlerText(err));
    }
  }

  const daten = liste.data;
  const ergebnis = pruefung.data;

  return (
    <div className="mx-auto max-w-[1200px] space-y-4">
      <SeitenKopf titel="Protokoll" anzahl={daten?.gesamt}>
        <button
          type="button"
          className="btn-ap inline-flex h-8 items-center gap-1.5 px-3 text-[13px]"
          onClick={csvLaden}
        >
          <Download size={14} aria-hidden="true" /> CSV exportieren
        </button>
        <button
          type="button"
          className="btn-ap-primary inline-flex h-8 items-center gap-1.5 px-3 text-[13px] font-semibold disabled:opacity-50"
          disabled={pruefung.isPending}
          onClick={() => pruefung.mutate()}
        >
          <ShieldCheck size={14} aria-hidden="true" />
          {pruefung.isPending ? "Prüfe …" : "Integrität prüfen"}
        </button>
      </SeitenKopf>

      <p className="text-sm text-label2">
        Unveränderliches Protokoll aller GoBD-relevanten Vorgänge Ihres Betriebs. Einträge lassen sich weder ändern noch
        löschen und sind pro Betrieb in einer Hash-Kette verbunden.
      </p>

      {fehler && (
        <Hinweiskasten ton="fehler">
          <p>{fehler}</p>
        </Hinweiskasten>
      )}

      {ergebnis && (
        <Hinweiskasten
          ton={ergebnis.ok ? "info" : "fehler"}
          titel={ergebnis.ok ? "Protokoll unverändert" : "Abweichungen im Protokoll gefunden"}
        >
          <p>
            {ergebnis.geprueft.toLocaleString("de-DE")} Einträge geprüft
            {ergebnis.legacy_eintraege > 0 &&
              `; ${ergebnis.legacy_eintraege.toLocaleString("de-DE")} ältere Einträge aus der Zeit vor der Verkettung sind nicht Teil der Kette`}
            .
          </p>
          {ergebnis.kopf_hash && (
            <p>
              Kettenkopf Nr. {ergebnis.kopf_seq}: <code className="break-all text-xs">{ergebnis.kopf_hash}</code>
            </p>
          )}
          {ergebnis.fehler.length > 0 && (
            <ul className="list-disc pl-4">
              {ergebnis.fehler.map((f, i) => (
                <li key={i}>
                  {f.seq !== null ? `Nr. ${f.seq}: ` : ""}
                  {f.grund}
                </li>
              ))}
            </ul>
          )}
        </Hinweiskasten>
      )}

      <Karte className="p-4">
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => e.preventDefault()}>
          <div>
            <label htmlFor="pf-von" className="mb-1 block text-xs font-semibold text-label2">
              Von
            </label>
            <input
              id="pf-von"
              type="date"
              className="field-ap"
              value={filter.von ?? ""}
              onChange={(e) => filterSetzen({ ...filter, von: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="pf-bis" className="mb-1 block text-xs font-semibold text-label2">
              Bis
            </label>
            <input
              id="pf-bis"
              type="date"
              className="field-ap"
              value={filter.bis ?? ""}
              onChange={(e) => filterSetzen({ ...filter, bis: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="pf-aktion" className="mb-1 block text-xs font-semibold text-label2">
              Aktion
            </label>
            <select
              id="pf-aktion"
              className="field-ap"
              value={filter.aktion ?? ""}
              onChange={(e) => filterSetzen({ ...filter, aktion: e.target.value })}
            >
              <option value="">Alle</option>
              {(aktionen.data ?? []).map((a) => (
                <option key={a} value={a}>
                  {aktionLabel(a)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="pf-akteur" className="mb-1 block text-xs font-semibold text-label2">
              Akteur
            </label>
            <select
              id="pf-akteur"
              className="field-ap"
              value={filter.akteur_typ ?? ""}
              onChange={(e) => filterSetzen({ ...filter, akteur_typ: e.target.value })}
            >
              <option value="">Alle</option>
              {Object.entries(AKTEUR_LABEL).map(([wert, label]) => (
                <option key={wert} value={wert}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="btn-ap h-9 px-3 text-[13px]"
            onClick={() => filterSetzen({})}
            disabled={Object.values(filter).every((v) => !v)}
          >
            Zurücksetzen
          </button>
        </form>
      </Karte>

      {liste.isError && (
        <Hinweiskasten ton="fehler">
          <p>{fehlerText(liste.error)}</p>
        </Hinweiskasten>
      )}

      <TabellenRahmen>
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Protokolleinträge, neueste zuerst</caption>
          <thead className="bg-fill text-xs text-label2">
            <tr>
              <th scope="col" className="px-3 py-2">Zeit</th>
              <th scope="col" className="px-3 py-2">Akteur</th>
              <th scope="col" className="px-3 py-2">Aktion</th>
              <th scope="col" className="px-3 py-2">Objekt</th>
              <th scope="col" className="px-3 py-2">Details</th>
            </tr>
          </thead>
          <tbody>
            {daten?.eintraege.map((e) => (
              <tr key={e.id} className="border-t border-sep align-top">
                <td className="whitespace-nowrap px-3 py-2 tabular-nums text-label">{zeitText(e.zeit)}</td>
                <td className="px-3 py-2 text-label">
                  {e.actor_name ?? AKTEUR_LABEL[e.akteur_typ]}
                  {e.actor_name && <span className="block text-xs text-label2">{AKTEUR_LABEL[e.akteur_typ]}</span>}
                </td>
                <td className="px-3 py-2 font-medium text-label">{aktionLabel(e.aktion)}</td>
                <td className="px-3 py-2 text-label2">
                  {e.entity_type ?? "–"}
                  {e.entity_id && <span className="block text-xs">{e.entity_id.slice(0, 8)}</span>}
                </td>
                <td className="max-w-[360px] px-3 py-2 text-xs text-label2">
                  {detailsText(e.payload)}
                  {e.ip && <span className="block">IP {e.ip}</span>}
                  {e.request_id && <span className="block">Anfrage {e.request_id.slice(0, 8)}</span>}
                </td>
              </tr>
            ))}
            {daten && daten.eintraege.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-label2">
                  Keine Einträge für diese Auswahl.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </TabellenRahmen>

      {daten && (
        <div className="flex items-center justify-between text-sm text-label2">
          <span>{seitenText(offset, daten.eintraege.length, daten.gesamt)}</span>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-ap inline-flex h-8 items-center gap-1 px-3 text-[13px]"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - SEITENGROESSE))}
            >
              <ChevronLeft size={14} aria-hidden="true" /> Neuere
            </button>
            <button
              type="button"
              className="btn-ap inline-flex h-8 items-center gap-1 px-3 text-[13px]"
              disabled={offset + SEITENGROESSE >= daten.gesamt}
              onClick={() => setOffset(offset + SEITENGROESSE)}
            >
              Ältere <ChevronRight size={14} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
