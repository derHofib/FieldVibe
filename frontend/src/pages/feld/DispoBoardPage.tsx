import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { datumZuIso } from "../../utils/format";
import { AlertTriangle, CalendarX, ChevronLeft, ChevronRight } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { termineApi, usersApi, vorgaengeApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import type { Termin, TerminWarnung } from "../../types";
import { Select } from "../../components/apple/Select";

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
  return datumZuIso(d);
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
  const uid = useId();
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [weekOffset, setWeekOffset] = useState(0);
  // Handy-Tagesansicht: Index 0 = Montag der angezeigten Woche; startet auf heute.
  const [tagIndex, setTagIndex] = useState(() => (new Date().getDay() + 6) % 7);
  const [warnungen, setWarnungen] = useState<TerminWarnung[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<NeuerTerminForm | null>(null);

  const weekStart = useMemo(() => addDays(startOfWeek(new Date()), weekOffset * 7), [weekOffset]);
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart]);
  const weekEnd = addDays(weekStart, 7);

  const { data: technikerListe } = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl, enabled: hatRecht("mitarbeiterverwaltung", "sehen") });
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
    meta: { erfolg: "Angelegt" },
    mutationFn: termineApi.create,
    onSuccess: (result) => {
      setWarnungen(result.warnungen);
      setShowForm(false);
      setForm(null);
      queryClient.invalidateQueries({ queryKey: ["termine"] });
    },
  });

  const updateMutation = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof termineApi.update>[1] }) =>
      termineApi.update(id, body),
    onSuccess: (result) => {
      setWarnungen(result.warnungen);
      queryClient.invalidateQueries({ queryKey: ["termine"] });
    },
  });

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

  function tagWechseln(schritt: -1 | 1) {
    const neu = tagIndex + schritt;
    if (neu < 0) {
      setWeekOffset((w) => w - 1);
      setTagIndex(6);
    } else if (neu > 6) {
      setWeekOffset((w) => w + 1);
      setTagIndex(0);
    } else {
      setTagIndex(neu);
    }
  }

  const gewaehlterTag = days[tagIndex];
  const tagesTermine = technikers
    .map((tech) => ({
      tech,
      eintraege: (terminenNachTechnikerUndTag.get(tech.id)?.get(dateKey(gewaehlterTag)) ?? [])
        .slice()
        .sort((a, b) => a.start_at.localeCompare(b.start_at)),
    }))
    .filter((z) => z.eintraege.length > 0);

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        <h1 className="text-lg font-bold text-label">Dispo-Board</h1>
        {istModulAktiv(currentUser, "pruefzyklen") ? (
          <button
            onClick={() => navigate("/pruefmittel")}
            className="text-sm text-tint underline-offset-2 hover:underline "
          >
            Prüfmittel →
          </button>
        ) : (
          <span />
        )}
      </div>

      <div className="space-y-2 md:hidden">
        <div className="card-ap flex items-center justify-between p-2">
          <button
            onClick={() => tagWechseln(-1)}
            aria-label="Vorheriger Tag"
            className="btn-touch flex items-center justify-center rounded-md bg-fill text-label"
          >
            <ChevronLeft size={20} strokeWidth={2} aria-hidden="true" />
          </button>
          <span className="text-sm font-semibold text-label">
            {gewaehlterTag.toLocaleDateString("de-DE", { weekday: "long", day: "2-digit", month: "2-digit" })}
          </span>
          <button
            onClick={() => tagWechseln(1)}
            aria-label="Nächster Tag"
            className="btn-touch flex items-center justify-center rounded-md bg-fill text-label"
          >
            <ChevronRight size={20} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
        <div className="grid grid-cols-7 gap-1" role="group" aria-label="Wochentag">
          {days.map((day, i) => (
            <button
              key={i}
              aria-pressed={i === tagIndex}
              onClick={() => setTagIndex(i)}
              className={`btn-touch flex flex-col items-center justify-center rounded-lg py-1 text-xs ${
                i === tagIndex ? "bg-tint-solid font-semibold text-white" : "card-ap text-label"
              }`}
            >
              {WOCHENTAGE[i]}
              <span className="text-[11px] opacity-80">{day.getDate()}.</span>
            </button>
          ))}
        </div>
      </div>

      <div className="hidden items-center justify-between card-ap p-3 md:flex">
        <button
          onClick={() => setWeekOffset((w) => w - 1)}
          className="btn-touch rounded-md bg-fill px-3 py-1.5 text-sm "
        >
          ← Vorherige Woche
        </button>
        <span className="text-sm font-medium text-label">
          {formatDayLabel(weekStart)} – {formatDayLabel(addDays(weekStart, 6))}
        </span>
        <button
          onClick={() => setWeekOffset((w) => w + 1)}
          className="btn-touch rounded-md bg-fill px-3 py-1.5 text-sm "
        >
          Nächste Woche →
        </button>
      </div>

      {warnungen.length > 0 && (
        <div className="rounded-lg border border-st-arbeit bg-st-arbeit-bg p-3 text-sm text-st-arbeit ">
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
        className="btn-touch btn-ap-primary px-4"
      >
        + Neuer Termin
      </button>

      {showForm && form && (
        <div className="space-y-3 card-ap p-4">
          <div>
            <label htmlFor={`${uid}-0`} className="mb-1 block text-xs font-medium text-label2">Vorgang</label>
            <Select id={`${uid}-0`}
              value={form.vorgangId}
              onChange={(e) => setForm({ ...form, vorgangId: e.target.value })}
            >
              <option value="">Bitte wählen…</option>
              {wahlbareVorgaenge.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.vorgangsnummer}: {v.titel}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor={`${uid}-1`} className="mb-1 block text-xs font-medium text-label2">Techniker</label>
            <Select id={`${uid}-1`}
              value={form.technikerId}
              onChange={(e) => setForm({ ...form, technikerId: e.target.value })}
            >
              {technikers.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor={`${uid}-2`} className="mb-1 block text-xs font-medium text-label2">Titel</label>
            <input id={`${uid}-2`}
              value={form.titel}
              onChange={(e) => setForm({ ...form, titel: e.target.value })}
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              placeholder="z.B. E-Check Hauptverteilung"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label htmlFor={`${uid}-3`} className="mb-1 block text-xs font-medium text-label2">Start</label>
              <input id={`${uid}-3`}
                type="datetime-local"
                value={form.start}
                onChange={(e) => setForm({ ...form, start: e.target.value })}
                className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
            <div className="flex-1">
              <label htmlFor={`${uid}-4`} className="mb-1 block text-xs font-medium text-label2">Ende</label>
              <input id={`${uid}-4`}
                type="datetime-local"
                value={form.ende}
                onChange={(e) => setForm({ ...form, ende: e.target.value })}
                className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setShowForm(false);
                setForm(null);
              }}
              className="btn-touch rounded-md bg-fill px-3 py-1.5 text-sm "
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
              className="btn-touch rounded-md btn-ap-primary px-4 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Anlegen
            </button>
          </div>
        </div>
      )}

      <div className="md:hidden">
        {tagesTermine.length === 0 ? (
          <EmptyState icon={CalendarX} text="Keine Termine an diesem Tag." />
        ) : (
          <div className="space-y-3">
            {tagesTermine.map(({ tech, eintraege }) => (
              <section key={tech.id}>
                <h2 className="mb-1 text-sm font-semibold text-label2">{tech.name}</h2>
                <div className="space-y-2">
                  {eintraege.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => navigate(`/vorgaenge/${t.vorgang_id}`)}
                      className={`card-interactive card-ap btn-touch flex w-full flex-col items-start p-3 text-left text-sm ${
                        t.status === "abgesagt" ? "text-label2 line-through" : "text-label"
                      }`}
                    >
                      <span className="text-xs font-semibold text-tint">
                        {formatTime(t.start_at)}–{formatTime(t.ende_at)}
                      </span>
                      <span className="font-medium">{t.titel}</span>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>

      <div className="hidden overflow-x-auto rounded-lg bg-card shadow-xs md:block dark:shadow-none dark:ring-1 ">
        <table className="w-full min-w-[900px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-sep">
              <th className="w-40 p-2 text-left text-xs font-semibold text-label2">
                Techniker
              </th>
              {days.map((day, i) => (
                <th
                  key={i}
                  className="w-32 p-2 text-left text-xs font-semibold text-label2"
                >
                  {WOCHENTAGE[i]} {formatDayLabel(day)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {technikers.map((tech) => (
              <tr key={tech.id} className="border-b border-sep ">
                <td className="p-2 align-top text-sm font-medium text-label">
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
                          className={`btn-touch cursor-grab rounded-md p-1.5 text-xs shadow-xs ${
                            t.status === "abgesagt"
                              ? "bg-fill text-label2 line-through"
                              : "bg-tintbg text-tint  "
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
