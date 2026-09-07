import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Car,
  ChevronLeft,
  ChevronRight,
  Coffee,
  ExternalLink,
  GripVertical,
  Inbox,
  Trash2,
  X,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Rnd } from "react-rnd";
import { useNavigate } from "react-router-dom";

import { termineApi, usersApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { istUeberfaellig, tageSeit } from "../../config/vorgangDarstellung";
import { useAlleSeitenLaden, useVorgangsListe } from "../../hooks/useVorgangsListe";
import type { FeedCard, Termin, TerminWarnung } from "../../types";
import { Karte, SeitenKopf } from "../OfficeUi";

const BACKLOG_FILTER = { unbisponiert: "true", sort: "faelligkeit_am" };

const START_STUNDE = 7;
const ENDE_STUNDE = 19;
const STUNDEN = Array.from({ length: ENDE_STUNDE - START_STUNDE }, (_, i) => START_STUNDE + i);
const PX_PRO_STUNDE = 96;
const PX_PRO_MINUTE = PX_PRO_STUNDE / 60;
const ROW_HOEHE = 64;
const BAR_PAD = 8;
const LABEL_BREITE = 160;
const RASTER_MINUTEN = 15;
const GESAMT_MINUTEN = (ENDE_STUNDE - START_STUNDE) * 60;
const GESAMT_BREITE = (ENDE_STUNDE - START_STUNDE) * PX_PRO_STUNDE;

function tagsBeginn(tag: Date): Date {
  const d = new Date(tag);
  d.setHours(START_STUNDE, 0, 0, 0);
  return d;
}

function tagsEnde(tag: Date): Date {
  const d = new Date(tag);
  d.setHours(ENDE_STUNDE, 0, 0, 0);
  return d;
}

function addTage(d: Date, n: number): Date {
  const date = new Date(d);
  date.setDate(date.getDate() + n);
  return date;
}

function istGleicherTag(a: Date, b: Date): boolean {
  return a.toDateString() === b.toDateString();
}

function minutenSeitTagesbeginn(iso: string, beginn: Date): number {
  return (new Date(iso).getTime() - beginn.getTime()) / 60000;
}

function formatTag(d: Date): string {
  return d.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
}

function formatUhrzeit(iso: string): string {
  return new Date(iso).toLocaleTimeString("de-DE", {
    timeZone: "Europe/Berlin",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

interface Techniker {
  id: string;
  name: string;
}

/** Gantt-Dispo: Zeilen = Techniker, Spalten = Tagesstunden. Bestehende
 * Termine sind per react-rnd verschieb-/verlaengerbar (dieselbe Bibliothek
 * wie FormularRasterEditor -- volle Kontrolle, keine neue Abhaengigkeit).
 * Unbisponierte Vorgaenge (kein aktiver Termin, siehe app/models/termin.py)
 * sammeln sich links nach Faelligkeit sortiert und werden per natives
 * Drag&Drop (gleiche Technik wie DispoBoardPage.tsx) in die Zeitachse
 * gezogen. */
export function OfficeDispoPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tag, setTag] = useState(() => new Date());
  const [warnungen, setWarnungen] = useState<TerminWarnung[]>([]);
  const [bearbeitenId, setBearbeitenId] = useState<string | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  const beginn = useMemo(() => tagsBeginn(tag), [tag]);
  const ende = useMemo(() => tagsEnde(tag), [tag]);
  const heute = istGleicherTag(tag, new Date());

  const { data: technikerListe } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  // Spiegelt app/api/routes/termine.py:_load_vorgang_and_techniker -- jeder
  // aktive mandant_admin/custom-Account kann als Techniker eingeplant werden.
  const technikers: Techniker[] = (technikerListe ?? []).filter(
    (u) => u.aktiv && (u.role === "mandant_admin" || u.role === "custom"),
  );

  const { data: termine } = useQuery({
    queryKey: ["termine", beginn.toISOString()],
    queryFn: () => termineApi.list({ von: beginn.toISOString(), bis: ende.toISOString() }),
  });

  const {
    data: backlogData,
    fetchNextPage,
    hasNextPage,
    isLoading: backlogLaedt,
  } = useVorgangsListe(BACKLOG_FILTER);
  useAlleSeitenLaden(true, hasNextPage, fetchNextPage);
  const backlog: FeedCard[] = backlogData?.pages.flatMap((p) => p.items) ?? [];

  const createMutation = useMutation({
    mutationFn: termineApi.create,
    onSuccess: (result) => {
      setWarnungen(result.warnungen);
      setBearbeitenId(result.termin.id);
      queryClient.invalidateQueries({ queryKey: ["termine"] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof termineApi.update>[1] }) =>
      termineApi.update(id, body),
    onSuccess: (result) => {
      setWarnungen(result.warnungen);
      queryClient.invalidateQueries({ queryKey: ["termine"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: termineApi.remove,
    onSuccess: () => {
      setBearbeitenId(null);
      queryClient.invalidateQueries({ queryKey: ["termine"] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
    },
  });

  const technikerIndex = new Map(technikers.map((t, i) => [t.id, i]));
  const bearbeitenTermin = (termine ?? []).find((t) => t.id === bearbeitenId) ?? null;

  const positionAusPixel = (xPx: number, yPx: number) => {
    const rasterPx = RASTER_MINUTEN * PX_PRO_MINUTE;
    const startMin = Math.max(
      0,
      Math.min(GESAMT_MINUTEN - RASTER_MINUTEN, Math.round(xPx / rasterPx) * RASTER_MINUTEN),
    );
    const rowIndex = Math.max(0, Math.min(technikers.length - 1, Math.round(yPx / ROW_HOEHE)));
    return { startMin, rowIndex };
  };

  const handleDropAusBacklog = (e: React.DragEvent) => {
    e.preventDefault();
    const vorgangId = e.dataTransfer.getData("text/plain");
    const vorgangTitel = e.dataTransfer.getData("application/x-vorgang-titel") || "Termin";
    if (!vorgangId || !gridRef.current || technikers.length === 0) return;
    const rect = gridRef.current.getBoundingClientRect();
    const { startMin, rowIndex } = positionAusPixel(e.clientX - rect.left, e.clientY - rect.top);
    const start = new Date(beginn.getTime() + startMin * 60000);
    const endeTermin = new Date(start.getTime() + Math.min(60, GESAMT_MINUTEN - startMin) * 60000);
    createMutation.mutate({
      vorgang_id: vorgangId,
      techniker_id: technikers[rowIndex].id,
      titel: vorgangTitel,
      start_at: start.toISOString(),
      ende_at: endeTermin.toISOString(),
    });
  };

  const handleDragStop = (termin: Termin, xPx: number, yPx: number) => {
    const { startMin, rowIndex } = positionAusPixel(xPx, yPx);
    const dauerMs = new Date(termin.ende_at).getTime() - new Date(termin.start_at).getTime();
    const neuerStart = new Date(beginn.getTime() + startMin * 60000);
    const neuesEnde = new Date(neuerStart.getTime() + dauerMs);
    updateMutation.mutate({
      id: termin.id,
      body: {
        techniker_id: technikers[rowIndex].id,
        start_at: neuerStart.toISOString(),
        ende_at: neuesEnde.toISOString(),
      },
    });
  };

  const handleResizeStop = (termin: Termin, xPx: number, breitePx: number) => {
    const rasterPx = RASTER_MINUTEN * PX_PRO_MINUTE;
    const startMin = Math.max(0, Math.round(xPx / rasterPx) * RASTER_MINUTEN);
    const dauerMin = Math.max(RASTER_MINUTEN, Math.round(breitePx / rasterPx) * RASTER_MINUTEN);
    const neuerStart = new Date(beginn.getTime() + startMin * 60000);
    const neuesEnde = new Date(neuerStart.getTime() + dauerMin * 60000);
    updateMutation.mutate({
      id: termin.id,
      body: { start_at: neuerStart.toISOString(), ende_at: neuesEnde.toISOString() },
    });
  };

  const jetztOffsetPx = heute
    ? Math.max(0, Math.min(GESAMT_BREITE, minutenSeitTagesbeginn(new Date().toISOString(), beginn) * PX_PRO_MINUTE))
    : null;

  return (
    <div>
      <SeitenKopf titel="Dispo" />

      {warnungen.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          {warnungen.map((w, i) => (
            <p key={i} className="flex items-center gap-1">
              <AlertTriangle size={13} strokeWidth={2} /> {w.meldung}
            </p>
          ))}
          <button onClick={() => setWarnungen([])} className="mt-1 text-xs underline">
            Ausblenden
          </button>
        </div>
      )}

      <div className="flex items-start gap-4">
        <div className="w-64 shrink-0 space-y-2">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-bold text-ind-ink-3">
              Nicht disponiert
            </span>
            <span className="rounded-full bg-slate-100 px-1.5 text-[10px] font-bold text-slate-400 dark:bg-stone-800 dark:text-stone-500">
              {backlog.length}
            </span>
          </div>
          {backlogLaedt ? (
            <p className="py-6 text-center text-xs text-ind-ink-3">Lädt…</p>
          ) : backlog.length === 0 ? (
            <EmptyState icon={Inbox} text="Alles disponiert." />
          ) : (
            <div className="max-h-[calc(100vh-220px)] space-y-2 overflow-y-auto pr-1">
              {backlog.map((v) => {
                const ueberfaellig = istUeberfaellig(v.faelligkeit_am);
                return (
                  <div
                    key={v.id}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData("text/plain", v.id);
                      e.dataTransfer.setData("application/x-vorgang-titel", v.titel);
                      e.dataTransfer.effectAllowed = "copy";
                    }}
                    className={`card-interactive cursor-grab rounded-xl border bg-white p-2.5 dark:bg-stone-900 ${
                      ueberfaellig
                        ? "border-rose-300 dark:border-rose-500/40"
                        : "border-ind-line"
                    }`}
                  >
                    <div className="flex items-start gap-1.5">
                      <GripVertical
                        size={14}
                        className="mt-0.5 shrink-0 text-ind-ink-3"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-[10.5px] font-bold text-ind-ink-3">
                          {v.vorgangsnummer}
                        </p>
                        <p className="truncate text-[13px] font-semibold text-ind-ink">
                          {v.titel}
                        </p>
                        <p className="truncate text-[11.5px] text-ind-ink-3">
                          {v.kunde_name}
                        </p>
                        {v.faelligkeit_am && (
                          <span
                            className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                              ueberfaellig
                                ? "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300"
                                : "bg-slate-100 text-slate-500 dark:bg-stone-800 dark:text-stone-400"
                            }`}
                          >
                            {ueberfaellig
                              ? `${tageSeit(v.faelligkeit_am)} Tage überfällig`
                              : `fällig ${new Date(v.faelligkeit_am).toLocaleDateString("de-DE")}`}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <Karte className="min-w-0 flex-1 overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-200 p-3 dark:border-stone-800">
            <button
              onClick={() => setTag((d) => addTage(d, -1))}
              className="btn-touch rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
              aria-label="Vorheriger Tag"
            >
              <ChevronLeft size={16} />
            </button>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-ind-ink">
                {formatTag(tag)}
              </span>
              {!heute && (
                <button
                  onClick={() => setTag(new Date())}
                  className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500 hover:bg-slate-200 dark:bg-stone-800 dark:text-stone-400 dark:hover:bg-stone-700"
                >
                  Heute
                </button>
              )}
            </div>
            <button
              onClick={() => setTag((d) => addTage(d, 1))}
              className="btn-touch rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
              aria-label="Nächster Tag"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          {technikers.length === 0 ? (
            <EmptyState icon={Inbox} text="Kein einplanbarer Techniker vorhanden." />
          ) : (
            <div className="overflow-x-auto">
              <div style={{ width: LABEL_BREITE + GESAMT_BREITE }}>
                <div className="flex border-b border-ind-line">
                  <div
                    className="sticky left-0 z-10 shrink-0 bg-white dark:bg-stone-900"
                    style={{ width: LABEL_BREITE }}
                  />
                  {STUNDEN.map((h) => (
                    <div
                      key={h}
                      className="shrink-0 border-l border-slate-100 py-1.5 pl-1.5 text-[11px] font-medium text-slate-400 dark:border-stone-800 dark:text-stone-500"
                      style={{ width: PX_PRO_STUNDE }}
                    >
                      {h}:00
                    </div>
                  ))}
                </div>

                <div className="relative" style={{ height: technikers.length * ROW_HOEHE }}>
                  <div
                    className="sticky left-0 z-10 shrink-0 bg-white dark:bg-stone-900"
                    style={{ width: LABEL_BREITE }}
                  >
                    {technikers.map((t, i) => (
                      <div
                        key={t.id}
                        className="absolute inset-x-0 flex items-center border-b border-slate-100 px-2 text-[13px] font-medium text-slate-700 dark:border-stone-800 dark:text-stone-300"
                        style={{ top: i * ROW_HOEHE, height: ROW_HOEHE }}
                      >
                        <span className="truncate">{t.name}</span>
                      </div>
                    ))}
                  </div>

                  <div
                    ref={gridRef}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={handleDropAusBacklog}
                    className="absolute top-0"
                    style={{
                      left: LABEL_BREITE,
                      width: GESAMT_BREITE,
                      height: technikers.length * ROW_HOEHE,
                    }}
                  >
                    {technikers.map((_, i) => (
                      <div
                        key={i}
                        className="absolute inset-x-0 border-b border-slate-100 dark:border-stone-800"
                        style={{ top: (i + 1) * ROW_HOEHE - 1 }}
                      />
                    ))}
                    {STUNDEN.map((h, i) => (
                      <div
                        key={h}
                        className="absolute inset-y-0 border-l border-slate-100 dark:border-stone-800"
                        style={{ left: i * PX_PRO_STUNDE }}
                      />
                    ))}
                    {jetztOffsetPx !== null && (
                      <div
                        className="absolute inset-y-0 z-20 w-px bg-rose-400 dark:bg-rose-500"
                        style={{ left: jetztOffsetPx }}
                      />
                    )}

                    {(termine ?? []).map((termin) => {
                      const rowIndex = technikerIndex.get(termin.techniker_id);
                      if (rowIndex === undefined) return null;
                      const startMin = minutenSeitTagesbeginn(termin.start_at, beginn);
                      const dauerMin =
                        (new Date(termin.ende_at).getTime() - new Date(termin.start_at).getTime()) / 60000;
                      const abgesagt = termin.status === "abgesagt";

                      return (
                        <div key={termin.id}>
                          {!!termin.fahrzeit_minuten && (
                            <div
                              title={`${termin.fahrzeit_minuten} Min. Fahrzeit`}
                              className="absolute flex items-center justify-center rounded-l-md bg-slate-100 text-slate-400 dark:bg-stone-800 dark:text-stone-500"
                              style={{
                                left: (startMin - termin.fahrzeit_minuten) * PX_PRO_MINUTE,
                                top: rowIndex * ROW_HOEHE + BAR_PAD,
                                width: termin.fahrzeit_minuten * PX_PRO_MINUTE,
                                height: ROW_HOEHE - BAR_PAD * 2,
                              }}
                            >
                              <Car size={12} strokeWidth={2} />
                            </div>
                          )}
                          {!!termin.pause_minuten && (
                            <div
                              title={`${termin.pause_minuten} Min. Pause`}
                              className="absolute flex items-center justify-center rounded-r-md bg-slate-100 text-slate-400 dark:bg-stone-800 dark:text-stone-500"
                              style={{
                                left: (startMin + dauerMin) * PX_PRO_MINUTE,
                                top: rowIndex * ROW_HOEHE + BAR_PAD,
                                width: termin.pause_minuten * PX_PRO_MINUTE,
                                height: ROW_HOEHE - BAR_PAD * 2,
                              }}
                            >
                              <Coffee size={12} strokeWidth={2} />
                            </div>
                          )}
                          <Rnd
                            bounds="parent"
                            dragGrid={[RASTER_MINUTEN * PX_PRO_MINUTE, ROW_HOEHE]}
                            resizeGrid={[RASTER_MINUTEN * PX_PRO_MINUTE, ROW_HOEHE]}
                            minWidth={RASTER_MINUTEN * PX_PRO_MINUTE}
                            enableResizing={{ left: true, right: true }}
                            position={{ x: startMin * PX_PRO_MINUTE, y: rowIndex * ROW_HOEHE + BAR_PAD }}
                            size={{ width: dauerMin * PX_PRO_MINUTE, height: ROW_HOEHE - BAR_PAD * 2 }}
                            onDragStop={(_e, d) => handleDragStop(termin, d.x, d.y)}
                            onResizeStop={(_e, _dir, ref, _delta, position) =>
                              handleResizeStop(termin, position.x, ref.offsetWidth)
                            }
                          >
                            <button
                              onClick={() => setBearbeitenId(termin.id)}
                              title={termin.titel}
                              className={`btn-touch flex h-full w-full flex-col justify-center overflow-hidden rounded-md px-2 text-left text-xs shadow-xs ${
                                abgesagt
                                  ? "bg-slate-100 text-slate-400 line-through dark:bg-stone-800 dark:text-stone-500"
                                  : "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300"
                              }`}
                            >
                              <span className="truncate font-semibold">{termin.titel}</span>
                              <span className="truncate text-[10.5px] opacity-80">
                                {formatUhrzeit(termin.start_at)}–{formatUhrzeit(termin.ende_at)}
                              </span>
                            </button>
                          </Rnd>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}
        </Karte>
      </div>

      {bearbeitenTermin && (
        <TerminBearbeitenPanel
          termin={bearbeitenTermin}
          technikers={technikers}
          onClose={() => setBearbeitenId(null)}
          onSave={(body) => updateMutation.mutate({ id: bearbeitenTermin.id, body })}
          onDelete={() => deleteMutation.mutate(bearbeitenTermin.id)}
          onZumVorgang={() => navigate(`/vorgaenge/${bearbeitenTermin.vorgang_id}`)}
        />
      )}
    </div>
  );
}

function TerminBearbeitenPanel({
  termin,
  technikers,
  onClose,
  onSave,
  onDelete,
  onZumVorgang,
}: {
  termin: Termin;
  technikers: Techniker[];
  onClose: () => void;
  onSave: (body: Parameters<typeof termineApi.update>[1]) => void;
  onDelete: () => void;
  onZumVorgang: () => void;
}) {
  const [titel, setTitel] = useState(termin.titel);
  const [technikerId, setTechnikerId] = useState(termin.techniker_id);
  const [start, setStart] = useState(toLocalInputValue(new Date(termin.start_at)));
  const [endeWert, setEndeWert] = useState(toLocalInputValue(new Date(termin.ende_at)));
  const [fahrzeit, setFahrzeit] = useState(termin.fahrzeit_minuten?.toString() ?? "");
  const [pause, setPause] = useState(termin.pause_minuten?.toString() ?? "");
  const [notiz, setNotiz] = useState(termin.notiz ?? "");

  const speichern = () => {
    onSave({
      titel,
      techniker_id: technikerId,
      start_at: new Date(start).toISOString(),
      ende_at: new Date(endeWert).toISOString(),
      fahrzeit_minuten: fahrzeit === "" ? null : Number(fahrzeit),
      pause_minuten: pause === "" ? null : Number(pause),
      notiz: notiz === "" ? null : notiz,
    });
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="h-full w-full max-w-sm space-y-3 overflow-y-auto bg-white p-4 shadow-xl dark:bg-stone-900"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-ind-ink">Termin bearbeiten</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800"
          >
            <X size={16} />
          </button>
        </div>

        <button
          onClick={onZumVorgang}
          className="flex items-center gap-1 text-xs text-cyan-700 hover:underline dark:text-cyan-400"
        >
          Zum Vorgang <ExternalLink size={12} />
        </button>

        <div>
          <label className="mb-1 block text-xs font-medium text-ind-ink-3">Titel</label>
          <input
            value={titel}
            onChange={(e) => setTitel(e.target.value)}
            className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ind-ink-3">Techniker</label>
          <select
            value={technikerId}
            onChange={(e) => setTechnikerId(e.target.value)}
            className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
          >
            {technikers.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex gap-3">
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-ind-ink-3">Start</label>
            <input
              type="datetime-local"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-ind-ink-3">Ende</label>
            <input
              type="datetime-local"
              value={endeWert}
              onChange={(e) => setEndeWert(e.target.value)}
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
        </div>

        <div className="flex gap-3">
          <div className="flex-1">
            <label className="mb-1 flex items-center gap-1 text-xs font-medium text-ind-ink-3">
              <Car size={12} /> Fahrzeit (Min.)
            </label>
            <input
              type="number"
              min={0}
              value={fahrzeit}
              onChange={(e) => setFahrzeit(e.target.value)}
              placeholder="0"
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <div className="flex-1">
            <label className="mb-1 flex items-center gap-1 text-xs font-medium text-ind-ink-3">
              <Coffee size={12} /> Pause danach (Min.)
            </label>
            <input
              type="number"
              min={0}
              value={pause}
              onChange={(e) => setPause(e.target.value)}
              placeholder="0"
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-ind-ink-3">Notiz</label>
          <textarea
            value={notiz}
            onChange={(e) => setNotiz(e.target.value)}
            rows={2}
            className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
          />
        </div>

        <div className="flex items-center justify-between gap-2 pt-2">
          <button
            onClick={() => {
              if (window.confirm("Termin wirklich löschen?")) onDelete();
            }}
            className="btn-touch flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10"
          >
            <Trash2 size={14} /> Löschen
          </button>
          <button
            onClick={speichern}
            className="btn-touch rounded-md btn-industry btn-industry-primary px-4 py-1.5 text-sm font-medium"
          >
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}
