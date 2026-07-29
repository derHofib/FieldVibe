import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  kundenApi,
  usersApi,
  vorgangEventsApi,
  vorgaengeApi,
  zeiterfassungApi,
} from "../../api/endpoints";
import { MentionText } from "../../components/MentionText";
import { cacheEvents, cacheKunde, getCachedEvents, getCachedKunde } from "../../offline/cache";
import { getOutboxItems, queueFoto, queueKommentar } from "../../offline/outbox";
import type { OutboxItem } from "../../offline/db";
import type { VorgangEvent, VorgangStatus } from "../../types";

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

export function VorgangDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [comment, setComment] = useState("");
  const [kundensichtbar, setKundensichtbar] = useState(false);
  const [kundenansicht, setKundenansicht] = useState(false);
  const [showMentionPicker, setShowMentionPicker] = useState(false);
  const [taetigkeit, setTaetigkeit] = useState("");

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
