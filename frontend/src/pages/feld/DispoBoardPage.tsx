import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { termineApi, usersApi, vorgaengeApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import type { Termin, TerminWarnung } from "../../types";

const WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const OFFENE_VORGANG_STATUS = ["neu", "geplant", "in_arbeit", "wartet_kunde"];

function startOfWeek(d: Date): Date {
  const date = new Date(d);
  const tag = date.getDay(); // 0 = Sonntag
  const diffZuMontag = tag === 0 ? -6 : 1 - tag;
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + diffZuMontag);
  return date;
}

function addDays(d: Date, n: number): Date {
  const date = new Date(d);
  date.setDate(date.getDate() + n);
  return date;
}

function dateKey(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function formatDayLabel(d: Date): string {
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
}

function formatTime(iso: string): string {
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

interface NeuerTerminForm {
  vorgangId: string;
  technikerId: string;
  titel: string;
  start: string;
  ende: string;
}

export function DispoBoardPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [weekOffset, setWeekOffset] = useState(0);
  const [warnungen, setWarnungen] = useState<TerminWarnung[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<NeuerTerminForm | null>(null);

  const weekStart = useMemo(() => addDays(startOfWeek(new Date()), weekOffset * 7), [weekOffset]);
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart]);
  const weekEnd = addDays(weekStart, 7);

  const { data: technikerListe } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  // Spiegelt app/api/routes/termine.py:_load_vorgang_and_techniker -- jeder
  // aktive mandant_admin/custom-Account kann als Techniker fuer einen
  // Termin eingeplant werden, seit die vier festen Rollen entfallen sind.
  const technikers = (technikerListe ?? []).filter(
    (u) => u.aktiv && (u.role === "mandant_admin" || u.role === "custom"),
  );

  const { data: offeneVorgaenge } = useQuery({
    queryKey: ["vorgaenge", "offen"],
    queryFn: () => vorgaengeApi.list(),
  });
  const wahlbareVorgaenge = (offeneVorgaenge ?? []).filter((v) =>
    OFFENE_VORGANG_STATUS.includes(v.status),
  );

  const { data: termine } = useQuery({
    queryKey: ["termine", dateKey(weekStart)],
    queryFn: () =>
      termineApi.list({ von: weekStart.toISOString(), bis: weekEnd.toISOString() }),
  });

  const createMutation = useMutation({
    mutationFn: termineApi.create,
    onSuccess: (result) => {
      setWarnungen(result.warnungen);
      setShowForm(false);
      setForm(null);
      queryClient.invalidateQueries({ queryKey: ["termine"] });
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

  if (currentUser && !hatRecht("dispo", "sehen")) return <Navigate to="/feed" replace />;

  const terminenNachTechnikerUndTag = new Map<string, Map<string, Termin[]>>();
  for (const t of termine ?? []) {
    const tagSchluessel = dateKey(new Date(t.start_at));
    if (!terminenNachTechnikerUndTag.has(t.techniker_id)) {
      terminenNachTechnikerUndTag.set(t.techniker_id, new Map());
    }
    const proTag = terminenNachTechnikerUndTag.get(t.techniker_id)!;
    if (!proTag.has(tagSchluessel)) proTag.set(tagSchluessel, []);
    proTag.get(tagSchluessel)!.push(t);
  }

  const handleDrop = (technikerId: string, tag: Date, terminId: string) => {
    const termin = (termine ?? []).find((t) => t.id === terminId);
    if (!termin) return;
    const alterStart = new Date(termin.start_at);
    const alterEnde = new Date(termin.ende_at);
    const dauerMs = alterEnde.getTime() - alterStart.getTime();

    const neuerStart = new Date(tag);
    neuerStart.setHours(alterStart.getHours(), alterStart.getMinutes(), 0, 0);
    const neuesEnde = new Date(neuerStart.getTime() + dauerMs);

    updateMutation.mutate({
      id: terminId,
      body: {
        techniker_id: technikerId,
        start_at: neuerStart.toISOString(),
        ende_at: neuesEnde.toISOString(),
      },
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-slate-400">
          ← Zurück
        </button>
        <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">Dispo-Board</h1>
        {istModulAktiv(currentUser, "pruefzyklen") ? (
          <button
            onClick={() => navigate("/pruefmittel")}
            className="text-sm text-blue-700 underline-offset-2 hover:underline dark:text-blue-400"
          >
            Prüfmittel →
          </button>
        ) : (
          <span />
        )}
      </div>

      <div className="flex items-center justify-between rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <button
          onClick={() => setWeekOffset((w) => w - 1)}
          className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm dark:bg-slate-800 dark:text-slate-300"
        >
          ← Vorherige Woche
        </button>
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
          {formatDayLabel(weekStart)} – {formatDayLabel(addDays(weekStart, 6))}
        </span>
        <button
          onClick={() => setWeekOffset((w) => w + 1)}
          className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm dark:bg-slate-800 dark:text-slate-300"
        >
          Nächste Woche →
        </button>
      </div>

      {warnungen.length > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          {warnungen.map((w, i) => (
            <p key={i}>⚠️ {w.meldung}</p>
          ))}
          <button onClick={() => setWarnungen([])} className="mt-1 text-xs underline">
            Ausblenden
          </button>
        </div>
      )}

      <button
        onClick={() => {
          setShowForm(true);
          const start = new Date();
          start.setMinutes(0, 0, 0);
          start.setHours(start.getHours() + 1);
          const ende = new Date(start.getTime() + 60 * 60 * 1000);
          setForm({
            vorgangId: "",
            technikerId: technikers[0]?.id ?? "",
            titel: "",
            start: toLocalInputValue(start),
            ende: toLocalInputValue(ende),
          });
        }}
        className="btn-touch rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white"
      >
        + Neuer Termin
      </button>

      {showForm && form && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Vorgang</label>
            <select
              value={form.vorgangId}
              onChange={(e) => setForm({ ...form, vorgangId: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="">Bitte wählen…</option>
              {wahlbareVorgaenge.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.vorgangsnummer}: {v.titel}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Techniker</label>
            <select
              value={form.technikerId}
              onChange={(e) => setForm({ ...form, technikerId: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              {technikers.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Titel</label>
            <input
              value={form.titel}
              onChange={(e) => setForm({ ...form, titel: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              placeholder="z.B. E-Check Hauptverteilung"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Start</label>
              <input
                type="datetime-local"
                value={form.start}
                onChange={(e) => setForm({ ...form, start: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Ende</label>
              <input
                type="datetime-local"
                value={form.ende}
                onChange={(e) => setForm({ ...form, ende: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setShowForm(false);
                setForm(null);
              }}
              className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm dark:bg-slate-800 dark:text-slate-300"
            >
              Abbrechen
            </button>
            <button
              disabled={!form.vorgangId || !form.technikerId || !form.titel || createMutation.isPending}
              onClick={() =>
                createMutation.mutate({
                  vorgang_id: form.vorgangId,
                  techniker_id: form.technikerId,
                  titel: form.titel,
                  start_at: new Date(form.start).toISOString(),
                  ende_at: new Date(form.ende).toISOString(),
                })
              }
              className="btn-touch rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Anlegen
            </button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg bg-white shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <table className="w-full min-w-[900px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800">
              <th className="w-40 p-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Techniker
              </th>
              {days.map((day, i) => (
                <th
                  key={i}
                  className="w-32 p-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400"
                >
                  {WOCHENTAGE[i]} {formatDayLabel(day)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {technikers.map((tech) => (
              <tr key={tech.id} className="border-b border-slate-100 dark:border-slate-800">
                <td className="p-2 align-top text-sm font-medium text-slate-700 dark:text-slate-300">
                  {tech.name}
                </td>
                {days.map((day, i) => {
                  const eintraege = terminenNachTechnikerUndTag.get(tech.id)?.get(dateKey(day)) ?? [];
                  return (
                    <td
                      key={i}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        const terminId = e.dataTransfer.getData("text/plain");
                        if (terminId) handleDrop(tech.id, day, terminId);
                      }}
                      className="min-h-[64px] w-32 space-y-1 p-1.5 align-top"
                    >
                      {eintraege.map((t) => (
                        <div
                          key={t.id}
                          draggable
                          onDragStart={(e) => e.dataTransfer.setData("text/plain", t.id)}
                          onClick={() => navigate(`/vorgaenge/${t.vorgang_id}`)}
                          title={t.titel}
                          className={`btn-touch cursor-grab rounded-md p-1.5 text-xs shadow-sm ${
                            t.status === "abgesagt"
                              ? "bg-slate-100 text-slate-400 line-through dark:bg-slate-800 dark:text-slate-500"
                              : "bg-blue-50 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300"
                          }`}
                        >
                          <div className="font-semibold">
                            {formatTime(t.start_at)}–{formatTime(t.ende_at)}
                          </div>
                          <div className="truncate">{t.titel}</div>
                        </div>
                      ))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
