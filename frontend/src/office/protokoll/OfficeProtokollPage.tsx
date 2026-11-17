import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Activity, CalendarDays, ChevronLeft, ChevronRight, Download, ScrollText, ShieldCheck, User as UserIcon, Users } from "lucide-react";

import { ApiError } from "../../api/client";
import { protokollApi, usersApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { SkeletonList } from "../../components/Skeleton";
import { downloadBlob } from "../../utils/download";
import { Karte, SeitenKopf, TabellenRahmen } from "../OfficeUi";
import { zuServerParametern } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import type { FilterFeld } from "../../components/filter/typen";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { datumServerParameter } from "../../utils/datumFilterParameter";
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
  const [offset, setOffset] = useState(0);
  const [fehler, setFehler] = useState<string | null>(null);

  const aktionen = useQuery({ queryKey: ["protokoll-aktionen"], queryFn: () => protokollApi.aktionen() });
  const nutzer = useQuery({ queryKey: ["users"], queryFn: usersApi.list });

  const felder = useMemo<FilterFeld<unknown>[]>(
    () => [
      {
        key: "aktion",
        label: "Aktion",
        typ: "auswahl",
        icon: Activity,
        operatoren: ["ist"],
        einzelwert: true,
        optionen: (aktionen.data ?? []).map((a) => ({ wert: a, label: aktionLabel(a) })),
      },
      {
        key: "akteur",
        label: "Akteur",
        typ: "auswahl",
        icon: Users,
        operatoren: ["ist"],
        einzelwert: true,
        optionen: Object.entries(AKTEUR_LABEL).map(([wert, label]) => ({ wert, label })),
      },
      {
        key: "nutzer",
        label: "Nutzer",
        typ: "person",
        icon: UserIcon,
        operatoren: ["ist"],
        einzelwert: true,
        optionen: (nutzer.data ?? []).map((u) => ({ wert: u.id, label: u.name || u.email })),
      },
      { key: "zeit", label: "Zeit", typ: "datum", icon: CalendarDays, operatoren: ["am", "vor", "nach", "zwischen", "relativ"] },
    ],
    [aktionen.data, nutzer.data],
  );
  const zustand = useFilterZustand({ felder });
  const erster = (b: { wert?: unknown }) => (Array.isArray(b.wert) ? (b.wert[0] as string | undefined) : undefined);
  const filter: ProtokollFilter = zuServerParametern(zustand.bedingungen, {
    aktion: (b): Record<string, string> => (erster(b) ? { aktion: erster(b)! } : {}),
    akteur: (b): Record<string, string> => (erster(b) ? { akteur_typ: erster(b)! } : {}),
    nutzer: (b): Record<string, string> => (erster(b) ? { actor_user_id: erster(b)! } : {}),
    zeit: datumServerParameter,
  });
  const filterSchluessel = JSON.stringify(filter);
  useEffect(() => setOffset(0), [filterSchluessel]);
  const filterAktiv = zustand.bedingungen.length > 0;
  const wirkt = (key: string) => zustand.bedingungen.some((b) => b.feld === key);

  const liste = useQuery({
    queryKey: ["protokoll", filter, offset],
    queryFn: () => protokollApi.liste(filter, SEITENGROESSE, offset),
    placeholderData: (vorher) => vorher,
  });
  const pruefung = useMutation({
    mutationFn: () => protokollApi.verifizieren(),
    onError: (err) => setFehler(fehlerText(err)),
    onSuccess: () => setFehler(null),
  });

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
          className="btn-ap inline-flex h-8 items-center gap-1.5 px-3 text-sekundaer"
          onClick={csvLaden}
        >
          <Download size={14} aria-hidden="true" /> CSV exportieren
        </button>
        <button
          type="button"
          className="btn-ap-primary inline-flex h-8 items-center gap-1.5 px-3 text-sekundaer font-semibold disabled:opacity-50"
          disabled={pruefung.isPending}
          onClick={() => pruefung.mutate()}
        >
          <ShieldCheck size={14} aria-hidden="true" />
          {pruefung.isPending ? "Prüfe …" : "Integrität prüfen"}
        </button>
      </SeitenKopf>

      <p className="text-sekundaer text-label2">
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
              Kettenkopf Nr. {ergebnis.kopf_seq}: <code className="break-all text-sekundaer">{ergebnis.kopf_hash}</code>
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

      <FilterLeiste felder={felder} zustand={zustand} ohneSuche />

      {liste.isError ? (
        <FehlerZustand fehler={liste.error} was="Das Protokoll" onErneut={() => void liste.refetch()} />
      ) : !daten ? (
        <SkeletonList count={6} />
      ) : daten.eintraege.length === 0 ? (
        <Karte className="p-4">
          <EmptyState
            icon={ScrollText}
            text={
              filterAktiv
                ? "Keine Treffer für diese Filter"
                : "Noch keine Einträge. GoBD-relevante Vorgänge erscheinen hier, sobald sie stattfinden."
            }
            action={
              filterAktiv ? (
                <button type="button" onClick={zustand.zuruecksetzen} className="btn-ap h-9 px-3 text-sekundaer">
                  Filter zurücksetzen
                </button>
              ) : undefined
            }
          />
        </Karte>
      ) : (
      <TabellenRahmen>
        <table className="w-full text-left text-fliess">
          <caption className="sr-only">Protokolleinträge, neueste zuerst</caption>
          <thead className="bg-fill text-meta text-label2">
            <tr>
              <th scope="col" className={`px-3 py-2 ${wirkt("zeit") ? "text-tint-text" : ""}`}>Zeit</th>
              <th scope="col" className={`px-3 py-2 ${wirkt("akteur") ? "text-tint-text" : ""}`}>Akteur</th>
              <th scope="col" className={`px-3 py-2 ${wirkt("aktion") ? "text-tint-text" : ""}`}>Aktion</th>
              <th scope="col" className="px-3 py-2">Objekt</th>
              <th scope="col" className="px-3 py-2">Details</th>
            </tr>
          </thead>
          <tbody>
            {daten.eintraege.map((e) => (
              <tr key={e.id} className="border-t border-sep align-top">
                <td className="whitespace-nowrap px-3 py-2 tabular-nums text-label">{zeitText(e.zeit)}</td>
                <td className="px-3 py-2 text-label">
                  {e.actor_name ?? AKTEUR_LABEL[e.akteur_typ]}
                  {e.actor_name && <span className="block text-sekundaer text-label2">{AKTEUR_LABEL[e.akteur_typ]}</span>}
                </td>
                <td className="px-3 py-2 font-medium text-label">{aktionLabel(e.aktion)}</td>
                <td className="px-3 py-2 text-label2">
                  {e.entity_type ?? "–"}
                  {e.entity_id && <span className="block text-sekundaer">{e.entity_id.slice(0, 8)}</span>}
                </td>
                <td className="max-w-[360px] px-3 py-2 text-sekundaer text-label2">
                  {detailsText(e.payload)}
                  {e.ip && <span className="block">IP {e.ip}</span>}
                  {e.request_id && <span className="block">Anfrage {e.request_id.slice(0, 8)}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TabellenRahmen>
      )}

      {daten && (
        <div className="flex items-center justify-between text-sekundaer text-label2">
          <span>{seitenText(offset, daten.eintraege.length, daten.gesamt)}</span>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-ap inline-flex h-8 items-center gap-1 px-3 text-sekundaer"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - SEITENGROESSE))}
            >
              <ChevronLeft size={14} aria-hidden="true" /> Neuere
            </button>
            <button
              type="button"
              className="btn-ap inline-flex h-8 items-center gap-1 px-3 text-sekundaer"
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
