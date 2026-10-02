import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, LayoutTemplate, Pencil, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api/client";
import { projektVorlagenApi } from "../../api/endpoints";
import { Sheet } from "../../components/apple/Sheet";
import { EmptyState } from "../../components/EmptyState";
import type { ProjektVorlage, ProjektVorlageDetail, ProjektVorlageElement } from "../../types";
import { Karte, SeitenKopf } from "../OfficeUi";

function fehlerText(e: unknown): string {
  return e instanceof ApiError ? e.message : "Die Aktion ist fehlgeschlagen.";
}

interface VorlagenZeile {
  element: ProjektVorlageElement;
  ebene: 0 | 1;
}

/** Phasen als Gruppenkopf, darunter ihre Schritte/Meilensteine, jeweils nach reihenfolge. */
function vorlagenZeilen(elemente: ProjektVorlageElement[]): VorlagenZeile[] {
  const sortiert = [...elemente].sort((a, b) => a.reihenfolge - b.reihenfolge);
  const phasen = sortiert.filter((e) => e.typ === "phase");
  const phasenRefs = new Set(phasen.map((p) => p.ref));
  const zeilen: VorlagenZeile[] = [];
  for (const e of sortiert.filter((x) => x.typ !== "phase" && (!x.phase_ref || !phasenRefs.has(x.phase_ref)))) zeilen.push({ element: e, ebene: 0 });
  for (const p of phasen) {
    zeilen.push({ element: p, ebene: 0 });
    for (const k of sortiert.filter((x) => x.typ !== "phase" && x.phase_ref === p.ref)) zeilen.push({ element: k, ebene: 1 });
  }
  return zeilen;
}

/** Einfacher Mini-Gantt (reines HTML): Balken relativ zur Gesamtdauer, kein Ziehen. Phasen ohne eigene
 * Dauer spannen ueber ihre Kinder. */
function MiniGantt({ detail }: { detail: ProjektVorlageDetail }) {
  const zeilen = useMemo(() => vorlagenZeilen(detail.elemente), [detail.elemente]);
  const gesamt = Math.max(
    1,
    detail.dauer_tage,
    ...detail.elemente.map((e) => e.offset_tage + Math.max(1, e.dauer_tage)),
  );
  const spanne = (e: ProjektVorlageElement) => {
    if (e.typ !== "phase") return { von: e.offset_tage, dauer: e.typ === "meilenstein" ? 0 : Math.max(1, e.dauer_tage) };
    const kinder = detail.elemente.filter((k) => k.phase_ref === e.ref);
    if (kinder.length === 0) return { von: e.offset_tage, dauer: Math.max(1, e.dauer_tage) };
    const von = Math.min(...kinder.map((k) => k.offset_tage));
    const bis = Math.max(...kinder.map((k) => k.offset_tage + Math.max(1, k.dauer_tage)));
    return { von, dauer: bis - von };
  };
  return (
    <ul className="space-y-1" aria-label="Vorschau der Vorlage">
      {zeilen.map(({ element: e, ebene }) => {
        const { von, dauer } = spanne(e);
        const links = (von / gesamt) * 100;
        const breite = Math.max((dauer / gesamt) * 100, 1.5);
        return (
          <li key={e.ref} className="grid grid-cols-[minmax(120px,200px)_1fr] items-center gap-3" style={{ paddingLeft: ebene * 14 }}>
            <span className={`truncate text-[13px] ${e.typ === "phase" ? "font-semibold text-label" : "text-label"}`} title={e.titel}>
              {e.titel}
            </span>
            <span className="relative h-4 rounded-[4px] bg-fill" title={`Tag ${von + 1}${dauer > 1 ? ` – ${von + dauer}` : ""}`}>
              {e.typ === "meilenstein" ? (
                <span className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 bg-tone-amber" style={{ left: `${links}%` }} />
              ) : (
                <span
                  className={`absolute top-0.5 bottom-0.5 rounded-[3px] ${e.typ === "phase" ? "bg-tone-indigo" : "bg-tint-solid"}`}
                  style={{ left: `${links}%`, width: `${breite}%` }}
                />
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function VorlagenVorschau({ vorlage }: { vorlage: ProjektVorlage }) {
  const { data, isLoading, error } = useQuery({ queryKey: ["projekt-vorlage", vorlage.id], queryFn: () => projektVorlagenApi.get(vorlage.id) });
  if (isLoading) return <p className="text-sm text-label2">Vorschau wird geladen …</p>;
  if (error || !data) return <p role="alert" className="text-sm text-st-fehlt">Vorschau konnte nicht geladen werden.</p>;
  return (
    <div className="space-y-3">
      <p className="text-xs text-label2">
        {data.anzahl_elemente} Elemente · {data.dauer_tage} Tage · {data.abhaengigkeiten.length} {data.abhaengigkeiten.length === 1 ? "Verbindung" : "Verbindungen"}
      </p>
      {data.elemente.length === 0 ? <p className="text-sm text-label2">Die Vorlage enthält keine Elemente.</p> : <MiniGantt detail={data} />}
    </div>
  );
}

function BearbeitenSheet({ vorlage, onClose }: { vorlage: ProjektVorlage; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(vorlage.name);
  const [beschreibung, setBeschreibung] = useState(vorlage.beschreibung ?? "");
  const speichern = useMutation({
    mutationFn: () => projektVorlagenApi.update(vorlage.id, { name: name.trim(), beschreibung: beschreibung.trim() || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projekt-vorlagen"] });
      onClose();
    },
  });
  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Vorlage bearbeiten"
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint-text">
          Abbrechen
        </button>
      }
      rechts={
        <button type="button" onClick={() => speichern.mutate()} disabled={!name.trim() || speichern.isPending} className="text-[17px] font-semibold text-tint-text disabled:opacity-40">
          Sichern
        </button>
      }
    >
      <div className="space-y-3 p-4">
        <label className="block text-sm text-label2">
          Name
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className="field-ap mt-1" />
        </label>
        <label className="block text-sm text-label2">
          Beschreibung
          <textarea value={beschreibung} onChange={(e) => setBeschreibung(e.target.value)} rows={3} className="field-ap mt-1" />
        </label>
        {speichern.error && (
          <div role="alert" className="rounded-[10px] bg-st-fehlt-bg px-3 py-2 text-sm text-st-fehlt">
            {fehlerText(speichern.error)}
          </div>
        )}
      </div>
    </Sheet>
  );
}

/** Verwaltung der Projektvorlagen (Zeitplan-Vorlagen): Liste links, Vorschau rechts, umbenennen und
 * loeschen. Angelegt werden Vorlagen aus dem Zeitplan-Tab eines Projekts ("Als Vorlage speichern"). */
export function OfficeProjektVorlagenPage() {
  const queryClient = useQueryClient();
  const { data: vorlagen, isLoading, error } = useQuery({ queryKey: ["projekt-vorlagen"], queryFn: projektVorlagenApi.list });
  const [auswahlId, setAuswahlId] = useState<string | null>(null);
  const [bearbeiten, setBearbeiten] = useState<ProjektVorlage | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const aktiv = vorlagen?.find((v) => v.id === auswahlId) ?? vorlagen?.[0] ?? null;
  useEffect(() => {
    if (auswahlId && vorlagen && !vorlagen.some((v) => v.id === auswahlId)) setAuswahlId(null);
  }, [auswahlId, vorlagen]);

  const loeschen = useMutation({
    mutationFn: (id: string) => projektVorlagenApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projekt-vorlagen"] }),
    onError: (e) => setFehler(fehlerText(e)),
  });

  return (
    <div>
      <Link to="/projekte" className="mb-2 inline-flex items-center gap-0.5 text-sm text-tint-text">
        <ChevronLeft size={16} strokeWidth={2} aria-hidden="true" />
        Projekte
      </Link>
      <SeitenKopf titel="Projektvorlagen" anzahl={vorlagen?.length} />

      {fehler && (
        <div role="alert" className="mb-3 flex items-start gap-2 rounded-[10px] bg-st-fehlt-bg px-3 py-2 text-sm text-st-fehlt">
          <span className="flex-1">{fehler}</span>
          <button type="button" onClick={() => setFehler(null)} aria-label="Meldung schließen">
            ×
          </button>
        </div>
      )}
      {isLoading && <p className="text-sm text-label2">Vorlagen werden geladen …</p>}
      {error && <p role="alert" className="text-sm text-st-fehlt">Vorlagen konnten nicht geladen werden.</p>}

      {vorlagen && vorlagen.length === 0 && (
        <Karte className="p-4">
          <EmptyState icon={LayoutTemplate} text="Noch keine Vorlagen. Öffne den Zeitplan eines Projekts und wähle „Als Vorlage speichern …“." />
        </Karte>
      )}

      {vorlagen && vorlagen.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-[minmax(260px,340px)_1fr]">
          <ul className="space-y-1.5" aria-label="Vorlagen">
            {vorlagen.map((v) => {
              const gewaehlt = aktiv?.id === v.id;
              return (
                <li key={v.id}>
                  <button
                    type="button"
                    onClick={() => setAuswahlId(v.id)}
                    aria-pressed={gewaehlt}
                    className="card-ap w-full px-3 py-2.5 text-left"
                    style={gewaehlt ? { borderColor: "var(--tint)", boxShadow: "0 0 0 1px var(--tint)" } : undefined}
                  >
                    <p className="truncate text-[15px] font-semibold text-label">{v.name}</p>
                    {v.beschreibung && <p className="truncate text-[13px] text-label2">{v.beschreibung}</p>}
                    <p className="text-xs text-label2">
                      {v.anzahl_elemente} Schritte · {v.dauer_tage} Tage
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>

          {aktiv && (
            <Karte className="p-4">
              <div className="mb-3 flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-lg font-semibold text-label">{aktiv.name}</h2>
                  {aktiv.beschreibung && <p className="text-sm text-label2">{aktiv.beschreibung}</p>}
                </div>
                <button type="button" onClick={() => setBearbeiten(aktiv)} className="btn-ap flex items-center gap-1.5 px-3 py-1.5 text-sm">
                  <Pencil size={14} strokeWidth={2} aria-hidden="true" />
                  Umbenennen
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Vorlage „${aktiv.name}“ wirklich löschen? Bereits angewendete Zeitpläne bleiben unverändert.`)) {
                      setFehler(null);
                      loeschen.mutate(aktiv.id);
                    }
                  }}
                  className="btn-ap flex items-center gap-1.5 px-3 py-1.5 text-sm text-st-fehlt hover:bg-st-fehlt-bg"
                >
                  <Trash2 size={14} strokeWidth={2} aria-hidden="true" />
                  Löschen
                </button>
              </div>
              <VorlagenVorschau vorlage={aktiv} />
            </Karte>
          )}
        </div>
      )}

      {bearbeiten && <BearbeitenSheet key={bearbeiten.id} vorlage={bearbeiten} onClose={() => setBearbeiten(null)} />}
    </div>
  );
}
