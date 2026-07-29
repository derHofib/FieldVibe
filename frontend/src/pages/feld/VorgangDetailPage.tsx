import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  angeboteApi,
  kundenApi,
  maengelApi,
  termineApi,
  usersApi,
  vorgangEventsApi,
  vorgaengeApi,
  zeiterfassungApi,
} from "../../api/endpoints";
import { MentionText } from "../../components/MentionText";
import { useAuth } from "../../context/AuthContext";
import { cacheEvents, cacheKunde, getCachedEvents, getCachedKunde } from "../../offline/cache";
import { getOutboxItems, queueFoto, queueKommentar } from "../../offline/outbox";
import { openPdfBlob } from "../../utils/pdf";
import type { OutboxItem } from "../../offline/db";
import type { MangelSchweregrad, MangelStatus, TerminWarnung, VorgangEvent, VorgangStatus } from "../../types";

const SCHWEREGRAD_OPTIONEN: { value: MangelSchweregrad; label: string }[] = [
  { value: "niedrig", label: "Niedrig" },
  { value: "mittel", label: "Mittel" },
  { value: "hoch", label: "Hoch" },
  { value: "kritisch", label: "Kritisch" },
];

const STATUS_OPTIONS: VorgangStatus[] = [
  "neu",
  "geplant",
  "in_arbeit",
  "wartet_kunde",
  "abgeschlossen",
  "abgerechnet",
  "storniert",
];

const STATUS_LABEL: Record<VorgangStatus, string> = {
  neu: "Neu",
  geplant: "Geplant",
  in_arbeit: "In Arbeit",
  wartet_kunde: "Wartet auf Kunde",
  abgeschlossen: "Abgeschlossen",
  abgerechnet: "Abgerechnet",
  storniert: "Storniert",
};

const EVENT_LABEL: Partial<Record<string, string>> = {
  status_change: "Status geändert",
  foto: "Foto hinzugefügt",
  dokument: "Dokument hinzugefügt",
  mangel: "Mangel erfasst",
  angebot: "Angebot aktualisiert",
  material: "Material erfasst",
  zeit_start: "Zeit gestartet",
  zeit_stop: "Zeit gestoppt",
  termin: "Termin",
  rechnung_status: "Rechnungsstatus aktualisiert",
};

function EventBubble({ event }: { event: VorgangEvent }) {
  if (event.is_system || event.event_type === "status_change") {
    const label =
      event.event_type === "status_change"
        ? `Status: ${(event.payload as { von?: string }).von ?? "?"} → ${(event.payload as { nach?: string }).nach ?? "?"}`
        : event.body ?? EVENT_LABEL[event.event_type] ?? event.event_type;
    return (
      <div className="my-2 text-center text-xs text-slate-400">
        {label} · {new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
      </div>
    );
  }

  return (
    <div className="mb-3 rounded-lg bg-white p-3 shadow-sm">
      <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
        <span>{new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}</span>
        {event.kundensichtbar && (
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-blue-600">Kundensichtbar</span>
        )}
      </div>
      {event.event_type === "foto" && event.foto_url && (
        <a href={event.foto_url} target="_blank" rel="noreferrer">
          <img
            src={event.foto_thumbnail_url ?? event.foto_url}
            alt="Foto"
            className="mb-2 max-h-64 rounded-md object-cover"
          />
        </a>
      )}
      {event.body && (
        <p className="whitespace-pre-wrap text-sm text-slate-800">
          <MentionText text={event.body} />
        </p>
      )}
    </div>
  );
}

function OutboxBubble({ item }: { item: OutboxItem }) {
  return (
    <div className="mb-3 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3">
      <div className="mb-1 flex items-center gap-1 text-xs text-slate-400">
        <span>🕘</span>
        <span>Nicht synchronisiert</span>
      </div>
      {item.kind === "foto" ? (
        <p className="text-sm text-slate-600">📷 Foto wartet auf Synchronisierung</p>
      ) : (
        <p className="whitespace-pre-wrap text-sm text-slate-700">{item.body}</p>
      )}
    </div>
  );
}

function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function VorgangDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [comment, setComment] = useState("");
  const [kundensichtbar, setKundensichtbar] = useState(false);
  const [kundenansicht, setKundenansicht] = useState(false);
  const [showMentionPicker, setShowMentionPicker] = useState(false);
  const [taetigkeit, setTaetigkeit] = useState("");
  const [showTerminForm, setShowTerminForm] = useState(false);
  const [terminWarnungen, setTerminWarnungen] = useState<TerminWarnung[]>([]);
  const [terminTechnikerId, setTerminTechnikerId] = useState("");
  const [terminTitel, setTerminTitel] = useState("");
  const [terminStart, setTerminStart] = useState("");
  const [terminEnde, setTerminEnde] = useState("");
  const [showMangelForm, setShowMangelForm] = useState(false);
  const [mangelBeschreibung, setMangelBeschreibung] = useState("");
  const [mangelSchweregrad, setMangelSchweregrad] = useState<MangelSchweregrad>("mittel");

  const kannDisponieren =
    currentUser?.role === "mandant_admin" || currentUser?.role === "disponent";

  const { data: vorgang } = useQuery({
    queryKey: ["vorgang", id],
    queryFn: () => vorgaengeApi.get(id!),
    enabled: !!id,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", vorgang?.kunde_id],
    queryFn: async () => {
      try {
        const result = await kundenApi.get(vorgang!.kunde_id);
        await cacheKunde(result);
        return result;
      } catch (err) {
        if (!navigator.onLine) {
          const cached = await getCachedKunde(vorgang!.kunde_id);
          if (cached) return cached;
        }
        throw err;
      }
    },
    enabled: !!vorgang,
  });
  const { data: events } = useQuery({
    queryKey: ["vorgang-events", id],
    queryFn: async () => {
      try {
        const result = await vorgangEventsApi.list(id!);
        await cacheEvents(result);
        return result;
      } catch (err) {
        if (!navigator.onLine) return getCachedEvents(id!);
        throw err;
      }
    },
    enabled: !!id,
  });
  const { data: outboxItems } = useQuery({
    queryKey: ["outbox", id],
    queryFn: () => getOutboxItems(id!),
    enabled: !!id,
  });
  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  const { data: laufenderTimer } = useQuery({
    queryKey: ["zeiterfassung-laufend"],
    queryFn: zeiterfassungApi.laufend,
  });
  const { data: termine } = useQuery({
    queryKey: ["termine", "vorgang", id],
    queryFn: () => termineApi.list({ vorgang_id: id! }),
    enabled: !!id,
  });

  const terminMutation = useMutation({
    mutationFn: () =>
      termineApi.create({
        vorgang_id: id!,
        techniker_id: terminTechnikerId,
        titel: terminTitel,
        start_at: new Date(terminStart).toISOString(),
        ende_at: new Date(terminEnde).toISOString(),
      }),
    onSuccess: (result) => {
      setTerminWarnungen(result.warnungen);
      setShowTerminForm(false);
      setTerminTitel("");
      queryClient.invalidateQueries({ queryKey: ["termine", "vorgang", id] });
    },
  });

  const { data: maengel } = useQuery({
    queryKey: ["maengel", "vorgang", id],
    queryFn: () => maengelApi.list({ vorgang_id: id! }),
    enabled: !!id,
  });

  const mangelMutation = useMutation({
    mutationFn: () =>
      maengelApi.create({ vorgang_id: id!, beschreibung: mangelBeschreibung, schweregrad: mangelSchweregrad }),
    onSuccess: () => {
      setShowMangelForm(false);
      setMangelBeschreibung("");
      queryClient.invalidateQueries({ queryKey: ["maengel", "vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
  });

  const mangelStatusMutation = useMutation({
    mutationFn: ({ mangelId, status }: { mangelId: string; status: MangelStatus }) =>
      maengelApi.update(mangelId, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["maengel", "vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
  });

  const angebotAusMaengelnMutation = useMutation({
    mutationFn: (mangelIds: string[]) => angeboteApi.createFromMaengel(mangelIds),
    onSuccess: (angebot) => navigate(`/angebote/${angebot.id}`),
  });

  const maengelProtokollMutation = useMutation({
    mutationFn: () => maengelApi.protokollPdf(id!),
    onSuccess: openPdfBlob,
  });

  const statusMutation = useMutation({
    mutationFn: (status: VorgangStatus) => vorgaengeApi.update(id!, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
  });

  const commentMutation = useMutation({
    mutationFn: async () => {
      try {
        return await vorgangEventsApi.create(id!, {
          event_type: "kommentar",
          body: comment,
          kundensichtbar,
          client_uuid: crypto.randomUUID(),
        });
      } catch (err) {
        if (err instanceof ApiError) throw err; // echte Ablehnung, nicht queuen
        await queueKommentar(id!, comment, kundensichtbar); // Netzwerkfehler -> offline
        return null;
      }
    },
    onSuccess: () => {
      setComment("");
      setKundensichtbar(false);
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["outbox", id] });
    },
  });

  const fotoMutation = useMutation({
    mutationFn: async (file: File) => {
      try {
        return await vorgangEventsApi.uploadFoto(id!, file, file.name, kundensichtbar);
      } catch (err) {
        if (err instanceof ApiError) throw err;
        await queueFoto(id!, file, file.name, kundensichtbar);
        return null;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["outbox", id] });
    },
  });

  const startTimerMutation = useMutation({
    mutationFn: () => zeiterfassungApi.start(id!, taetigkeit || undefined),
    onSuccess: () => {
      setTaetigkeit("");
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
    },
  });

  const stopTimerMutation = useMutation({
    mutationFn: (timerId: string) => zeiterfassungApi.stop(timerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
    },
  });

  if (!vorgang) return <p className="text-center text-slate-500">Lädt…</p>;

  const eventsChronological = [...(events ?? [])].reverse();
  const sichtbareEvents = kundenansicht
    ? eventsChronological.filter((e) => e.kundensichtbar)
    : eventsChronological;
  const eigeneOutboxItems = (outboxItems ?? []).filter((i) => i.vorgang_id === id);

  const timerLaeuftHier = laufenderTimer && laufenderTimer.vorgang_id === id;
  const timerLaeuftAnderswo = laufenderTimer && laufenderTimer.vorgang_id !== id;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <div className="text-xs text-slate-400">{vorgang.vorgangsnummer}</div>
        <h1 className="text-lg font-bold text-slate-800">{vorgang.titel}</h1>
        {kunde && (
          <button
            onClick={() => navigate(`/kunden/${kunde.id}`)}
            className="text-sm text-blue-700 underline-offset-2 hover:underline"
          >
            {kunde.name}
          </button>
        )}
        {vorgang.beschreibung && <p className="mt-2 text-sm text-slate-600">{vorgang.beschreibung}</p>}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="text-sm text-slate-500">Status:</label>
          <select
            value={vorgang.status}
            onChange={(e) => statusMutation.mutate(e.target.value as VorgangStatus)}
            className="btn-touch rounded-md border border-slate-300 px-2 py-1 text-sm"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </select>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">
            Priorität {vorgang.prioritaet}
          </span>
        </div>
      </div>

      <div className="rounded-lg bg-white p-3 shadow-sm">
        {timerLaeuftHier ? (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm font-medium text-slate-700">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />
              Zeit läuft seit{" "}
              {new Date(laufenderTimer.start_at).toLocaleTimeString("de-DE", {
                timeZone: "Europe/Berlin",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
            <button
              onClick={() => stopTimerMutation.mutate(laufenderTimer.id)}
              disabled={stopTimerMutation.isPending}
              className="btn-touch rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Stoppen
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <input
              value={taetigkeit}
              onChange={(e) => setTaetigkeit(e.target.value)}
              placeholder="Tätigkeit (optional)"
              className="btn-touch flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
            <button
              onClick={() => startTimerMutation.mutate()}
              disabled={startTimerMutation.isPending || !!timerLaeuftAnderswo}
              title={timerLaeuftAnderswo ? "Es läuft bereits ein Timer für einen anderen Vorgang" : ""}
              className="btn-touch shrink-0 rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Zeit starten
            </button>
          </div>
        )}
      </div>

      <div className="rounded-lg bg-white p-3 shadow-sm">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500">Termine</h2>
          {kannDisponieren && (
            <button
              onClick={() => {
                setShowTerminForm((v) => !v);
                if (!terminStart) {
                  const start = new Date();
                  start.setMinutes(0, 0, 0);
                  start.setHours(start.getHours() + 1);
                  const ende = new Date(start.getTime() + 60 * 60 * 1000);
                  setTerminStart(toLocalInputValue(start));
                  setTerminEnde(toLocalInputValue(ende));
                  setTerminTechnikerId(users?.find((u) => u.role === "techniker")?.id ?? "");
                }
              }}
              className="btn-touch text-xs font-medium text-blue-700"
            >
              {showTerminForm ? "Abbrechen" : "+ Termin planen"}
            </button>
          )}
        </div>

        {terminWarnungen.length > 0 && (
          <div className="mb-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
            {terminWarnungen.map((w, i) => (
              <p key={i}>⚠️ {w.meldung}</p>
            ))}
          </div>
        )}

        {showTerminForm && (
          <div className="mb-2 space-y-2 rounded-md bg-slate-50 p-2">
            <input
              value={terminTitel}
              onChange={(e) => setTerminTitel(e.target.value)}
              placeholder="Titel"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
            <select
              value={terminTechnikerId}
              onChange={(e) => setTerminTechnikerId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            >
              {(users ?? [])
                .filter((u) => u.role === "techniker")
                .map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
            </select>
            <div className="flex gap-2">
              <input
                type="datetime-local"
                value={terminStart}
                onChange={(e) => setTerminStart(e.target.value)}
                className="w-1/2 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
              <input
                type="datetime-local"
                value={terminEnde}
                onChange={(e) => setTerminEnde(e.target.value)}
                className="w-1/2 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            </div>
            <button
              disabled={!terminTitel || !terminTechnikerId || terminMutation.isPending}
              onClick={() => terminMutation.mutate()}
              className="btn-touch w-full rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Anlegen
            </button>
          </div>
        )}

        {(termine ?? []).length === 0 ? (
          <p className="text-sm text-slate-400">Keine Termine geplant.</p>
        ) : (
          <div className="space-y-1.5">
            {termine!.map((t) => (
              <div key={t.id} className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm">
                <div>
                  <div className="font-medium text-slate-700">{t.titel}</div>
                  <div className="text-xs text-slate-400">
                    {new Date(t.start_at).toLocaleString("de-DE", {
                      timeZone: "Europe/Berlin",
                      dateStyle: "short",
                      timeStyle: "short",
                    })}
                  </div>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    t.status === "abgesagt" ? "bg-slate-200 text-slate-500" : "bg-blue-50 text-blue-700"
                  }`}
                >
                  {t.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg bg-white p-3 shadow-sm">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500">Mängel</h2>
          <div className="flex items-center gap-3">
            {(maengel ?? []).length > 0 && (
              <button
                onClick={() => maengelProtokollMutation.mutate()}
                disabled={maengelProtokollMutation.isPending}
                className="btn-touch text-xs font-medium text-slate-500"
              >
                📄 Protokoll
              </button>
            )}
            <button onClick={() => setShowMangelForm((v) => !v)} className="btn-touch text-xs font-medium text-blue-700">
              {showMangelForm ? "Abbrechen" : "+ Mangel melden"}
            </button>
          </div>
        </div>

        {showMangelForm && (
          <div className="mb-2 space-y-2 rounded-md bg-slate-50 p-2">
            <textarea
              value={mangelBeschreibung}
              onChange={(e) => setMangelBeschreibung(e.target.value)}
              placeholder="Was ist defekt?"
              rows={2}
              className="w-full resize-none rounded-md border border-slate-300 p-2 text-sm"
            />
            <select
              value={mangelSchweregrad}
              onChange={(e) => setMangelSchweregrad(e.target.value as MangelSchweregrad)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            >
              {SCHWEREGRAD_OPTIONEN.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            <button
              disabled={!mangelBeschreibung.trim() || mangelMutation.isPending}
              onClick={() => mangelMutation.mutate()}
              className="btn-touch w-full rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Erfassen
            </button>
          </div>
        )}

        {(maengel ?? []).length === 0 ? (
          <p className="text-sm text-slate-400">Keine Mängel erfasst.</p>
        ) : (
          <div className="space-y-1.5">
            {maengel!.map((m) => (
              <div key={m.id} className="rounded-md bg-slate-50 p-2 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-slate-700">{m.beschreibung}</p>
                  <span className="shrink-0 rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-600">
                    {m.schweregrad}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-xs text-slate-400">{m.status}</span>
                  {m.status === "offen" && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => mangelStatusMutation.mutate({ mangelId: m.id, status: "behoben" })}
                        className="btn-touch text-xs font-medium text-green-700"
                      >
                        Behoben
                      </button>
                      <button
                        onClick={() => mangelStatusMutation.mutate({ mangelId: m.id, status: "abgelehnt" })}
                        className="btn-touch text-xs font-medium text-red-700"
                      >
                        Verwerfen
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {kannDisponieren && (maengel ?? []).some((m) => m.status === "offen") && (
          <button
            onClick={() =>
              angebotAusMaengelnMutation.mutate(maengel!.filter((m) => m.status === "offen").map((m) => m.id))
            }
            disabled={angebotAusMaengelnMutation.isPending}
            className="btn-touch mt-2 w-full rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50"
          >
            Angebot aus offenen Mängeln erstellen
          </button>
        )}
      </div>

      <div className="flex items-center justify-end gap-2">
        <span className="text-sm text-slate-500">
          {kundenansicht ? "Kundenansicht" : "Interne Ansicht"}
        </span>
        <button
          onClick={() => setKundenansicht((v) => !v)}
          className={`btn-touch rounded-full px-3 py-1 text-xs font-semibold ${
            kundenansicht ? "bg-blue-600 text-white" : "bg-slate-200 text-slate-700"
          }`}
        >
          Umschalten
        </button>
      </div>

      <div>
        {sichtbareEvents.length === 0 && eigeneOutboxItems.length === 0 ? (
          <p className="text-center text-sm text-slate-400">Noch keine Einträge.</p>
        ) : (
          <>
            {sichtbareEvents.map((event) => (
              <EventBubble key={event.id} event={event} />
            ))}
            {!kundenansicht &&
              eigeneOutboxItems.map((item) => <OutboxBubble key={item.client_uuid} item={item} />)}
          </>
        )}
      </div>

      {!kundenansicht && (
        <div className="sticky bottom-16 space-y-2 rounded-lg bg-white p-3 shadow-md">
          <div className="relative">
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Kommentar schreiben…"
              rows={2}
              className="w-full resize-none rounded-md border border-slate-300 p-2 text-sm"
            />
            {showMentionPicker && (
              <div className="absolute bottom-full left-0 mb-1 max-h-40 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
                {users?.map((u) => (
                  <button
                    key={u.id}
                    onClick={() => {
                      setComment((c) => `${c}@[${u.name}](${u.id}) `);
                      setShowMentionPicker(false);
                    }}
                    className="btn-touch block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                  >
                    {u.name}
                  </button>
                ))}
              </div>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) fotoMutation.mutate(file);
              e.target.value = "";
            }}
          />
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowMentionPicker((v) => !v)}
                className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600"
              >
                @ Erwähnen
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={fotoMutation.isPending}
                className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 disabled:opacity-50"
              >
                📷 Foto
              </button>
              <label className="flex items-center gap-1.5 text-sm text-slate-500">
                <input
                  type="checkbox"
                  checked={kundensichtbar}
                  onChange={(e) => setKundensichtbar(e.target.checked)}
                  className="h-4 w-4"
                />
                Für Kunde sichtbar
              </label>
            </div>
            <button
              onClick={() => commentMutation.mutate()}
              disabled={!comment.trim() || commentMutation.isPending}
              className="btn-touch rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Senden
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
