import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  angeboteApi,
  anlagenApi,
  fahrzeugZuweisungenApi,
  highlightsApi,
  kundenApi,
  lieferantenApi,
  maengelApi,
  materialApi,
  materialBedarfeApi,
  termineApi,
  usersApi,
  vorgangEventsApi,
  vorgaengeApi,
  zeiterfassungApi,
} from "../../api/endpoints";
import { MentionText } from "../../components/MentionText";
import { SignaturePad } from "../../components/SignaturePad";
import { useAuth } from "../../context/AuthContext";
import { cacheEvents, cacheKunde, getCachedEvents, getCachedKunde } from "../../offline/cache";
import { discardOutboxItem, getOutboxItems, queueFoto, queueKommentar, queueStatusChange } from "../../offline/outbox";
import { formatSekundenAlsHHMM } from "../../utils/duration";
import { openPdfBlob } from "../../utils/pdf";
import type { OutboxItem } from "../../offline/db";
import type {
  MangelSchweregrad,
  MangelStatus,
  MaterialBedarfZweck,
  TerminWarnung,
  VorgangEvent,
  VorgangStatus,
} from "../../types";

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
  unterschrift: "Unterschrift erfasst",
};

const NEU_MATERIAL = "__neu__";

function EventBubble({
  event,
  onHighlight,
}: {
  event: VorgangEvent;
  onHighlight: (eventId: number) => void;
}) {
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
    <div className="mb-3 rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
      <div className="mb-1 flex items-center justify-between text-xs text-slate-400 dark:text-slate-500">
        <span>{new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}</span>
        {event.kundensichtbar && (
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-blue-600 dark:bg-blue-500/15 dark:text-blue-300">
            Kundensichtbar
          </span>
        )}
      </div>
      {event.event_type === "foto" && event.foto_url && (
        <>
          <a href={event.foto_url} target="_blank" rel="noreferrer">
            <img
              src={event.foto_thumbnail_url ?? event.foto_url}
              alt="Foto"
              className="mb-2 max-h-64 rounded-md object-cover"
            />
          </a>
          <button
            onClick={() => onHighlight(event.id)}
            className="btn-touch mb-2 text-xs font-medium text-amber-600 dark:text-amber-400"
          >
            ⭐ Als Highlight markieren
          </button>
        </>
      )}
      {event.event_type === "unterschrift" && event.unterschrift_url && (
        <div className="mb-2">
          <img
            src={event.unterschrift_url}
            alt="Unterschrift"
            className="max-h-32 rounded-md border border-slate-200 bg-white"
          />
          {typeof event.payload.unterzeichner_name === "string" && (
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Unterschrieben von: {event.payload.unterzeichner_name}
            </p>
          )}
        </div>
      )}
      {event.body && (
        <p className="whitespace-pre-wrap text-sm text-slate-800 dark:text-slate-100">
          <MentionText text={event.body} />
        </p>
      )}
    </div>
  );
}

function OutboxBubble({ item, onDiscard }: { item: OutboxItem; onDiscard: (clientUuid: string) => void }) {
  return (
    <div
      className={`mb-3 rounded-lg border border-dashed p-3 ${
        item.failed
          ? "border-red-300 bg-red-50 dark:border-red-900/60 dark:bg-red-950/30"
          : "border-slate-300 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60"
      }`}
    >
      <div className="mb-1 flex items-center justify-between gap-1 text-xs">
        {item.failed ? (
          <span className="text-red-500 dark:text-red-400">⚠ Vom Server abgelehnt{item.errorMessage ? `: ${item.errorMessage}` : ""}</span>
        ) : (
          <span className="flex items-center gap-1 text-slate-400 dark:text-slate-500">
            <span>🕘</span>
            <span>Nicht synchronisiert</span>
          </span>
        )}
        {item.failed && (
          <button
            onClick={() => onDiscard(item.client_uuid)}
            className="btn-touch text-red-500 underline dark:text-red-400"
          >
            Verwerfen
          </button>
        )}
      </div>
      {item.kind === "foto" ? (
        <p className="text-sm text-slate-600 dark:text-slate-300">📷 Foto wartet auf Synchronisierung</p>
      ) : item.kind === "status" ? (
        <p className="text-sm text-slate-600 dark:text-slate-300">Statusänderung zu „{item.statusValue}“ wartet auf Synchronisierung</p>
      ) : (
        <p className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">{item.body}</p>
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
  const [showUnterschriftPad, setShowUnterschriftPad] = useState(false);
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
  const [showMaterialForm, setShowMaterialForm] = useState(false);
  const [materialId, setMaterialId] = useState("");
  const [materialMenge, setMaterialMenge] = useState("");
  const [materialLagerId, setMaterialLagerId] = useState("");
  const [showBedarfForm, setShowBedarfForm] = useState(false);
  const [bedarfMaterialId, setBedarfMaterialId] = useState("");
  const [bedarfMenge, setBedarfMenge] = useState("");
  const [bedarfZweck, setBedarfZweck] = useState<MaterialBedarfZweck>("bestellung");
  const [bedarfNotiz, setBedarfNotiz] = useState("");
  const [bedarfNeuBezeichnung, setBedarfNeuBezeichnung] = useState("");
  const [bedarfNeuEinheit, setBedarfNeuEinheit] = useState("Stk");
  const [bedarfNeuEinzelpreis, setBedarfNeuEinzelpreis] = useState("");
  const [bedarfNeuLieferantId, setBedarfNeuLieferantId] = useState("");
  const [editingZuordnung, setEditingZuordnung] = useState(false);
  const [editKundeId, setEditKundeId] = useState("");
  const [editAnlageId, setEditAnlageId] = useState("");
  const [zuordnungError, setZuordnungError] = useState<string | null>(null);

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
  const { data: anlage } = useQuery({
    queryKey: ["anlage", vorgang?.anlage_id],
    queryFn: () => anlagenApi.get(vorgang!.anlage_id!),
    enabled: !!vorgang?.anlage_id,
  });
  const { data: alleKunden } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
    enabled: editingZuordnung,
  });
  const { data: anlagenFuerEditKunde } = useQuery({
    queryKey: ["anlagen", editKundeId],
    queryFn: () => anlagenApi.list(editKundeId),
    enabled: editingZuordnung && !!editKundeId,
  });
  const zuordnungMutation = useMutation({
    mutationFn: () =>
      vorgaengeApi.update(id!, { kunde_id: editKundeId, anlage_id: editAnlageId || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      setEditingZuordnung(false);
      setZuordnungError(null);
    },
    onError: (err) => setZuordnungError(err instanceof ApiError ? err.message : "Fehler"),
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
  const { data: zeiterfassungListe } = useQuery({
    queryKey: ["zeiterfassung", id],
    queryFn: () => zeiterfassungApi.list(id!),
    enabled: !!id,
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

  const highlightMutation = useMutation({
    mutationFn: (eventId: number) => highlightsApi.create(eventId),
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        window.alert("Dieses Foto ist bereits als Highlight markiert.");
      }
    },
  });

  const { data: materialListe } = useQuery({ queryKey: ["material"], queryFn: () => materialApi.list() });
  const { data: alleAnlagenFuerLager } = useQuery({
    queryKey: ["lagerorte"],
    queryFn: () => anlagenApi.list(),
    enabled: showMaterialForm,
  });
  const lagerorte = (alleAnlagenFuerLager ?? []).filter((a) => a.objekttyp !== "kundenanlage");
  const { data: meinFahrzeug } = useQuery({
    queryKey: ["fahrzeug-mir"],
    queryFn: fahrzeugZuweisungenApi.mir,
    enabled: showMaterialForm && currentUser?.role === "techniker",
  });

  const materialVerwendenMutation = useMutation({
    mutationFn: () => materialApi.verwenden(materialId, id!, materialLagerId, materialMenge),
    onSuccess: () => {
      setShowMaterialForm(false);
      setMaterialId("");
      setMaterialMenge("");
      setMaterialLagerId("");
      queryClient.invalidateQueries({ queryKey: ["material"] });
      queryClient.invalidateQueries({ queryKey: ["stories"] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
  });

  useEffect(() => {
    if (showBedarfForm && vorgang) {
      setBedarfZweck(vorgang.leistungstyp === "planung" || vorgang.leistungstyp === "beratung" ? "angebot" : "bestellung");
    }
  }, [showBedarfForm, vorgang]);

  const { data: materialBedarfe } = useQuery({
    queryKey: ["material-bedarfe", "vorgang", id],
    queryFn: () => materialBedarfeApi.list({ vorgang_id: id! }),
    enabled: !!id,
  });
  const { data: lieferantenFuerNeuesMaterial } = useQuery({
    queryKey: ["lieferanten"],
    queryFn: () => lieferantenApi.list(),
    enabled: showBedarfForm && bedarfMaterialId === NEU_MATERIAL,
  });

  const materialBedarfMutation = useMutation({
    mutationFn: async () => {
      // Wenn das Material noch nicht im Katalog existiert (haeufiger Fall
      // bei einer Erstbestellung), wird es hier mit Bestand 0 angelegt --
      // der Bedarf haengt sich danach an den neuen Katalogeintrag, statt
      // eine eigene Freitext-Ablage zu brauchen.
      const materialId =
        bedarfMaterialId === NEU_MATERIAL
          ? (
              await materialApi.create({
                bezeichnung: bedarfNeuBezeichnung,
                einheit: bedarfNeuEinheit,
                einzelpreis: bedarfNeuEinzelpreis || undefined,
                lieferant_id: bedarfNeuLieferantId || undefined,
              })
            ).id
          : bedarfMaterialId;
      return materialBedarfeApi.create({
        material_id: materialId,
        vorgang_id: id!,
        menge: bedarfMenge,
        zweck: bedarfZweck,
        notiz: bedarfNotiz || undefined,
      });
    },
    onSuccess: () => {
      setShowBedarfForm(false);
      setBedarfMaterialId("");
      setBedarfMenge("");
      setBedarfNotiz("");
      setBedarfNeuBezeichnung("");
      setBedarfNeuEinheit("Stk");
      setBedarfNeuEinzelpreis("");
      setBedarfNeuLieferantId("");
      queryClient.invalidateQueries({ queryKey: ["material-bedarfe", "vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["material"] });
    },
  });

  const bedarfEntfernenMutation = useMutation({
    mutationFn: (bedarfId: string) => materialBedarfeApi.remove(bedarfId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["material-bedarfe", "vorgang", id] }),
  });

  const statusMutation = useMutation({
    mutationFn: async (status: VorgangStatus) => {
      try {
        return await vorgaengeApi.update(id!, { status });
      } catch (err) {
        if (err instanceof ApiError) throw err; // echte Ablehnung, nicht queuen
        await queueStatusChange(id!, status); // Netzwerkfehler -> offline
        return null;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["outbox", id] });
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
      const clientUuid = crypto.randomUUID();
      try {
        return await vorgangEventsApi.uploadFoto(
          id!,
          file,
          file.name,
          kundensichtbar,
          undefined,
          clientUuid,
        );
      } catch (err) {
        if (err instanceof ApiError) throw err;
        await queueFoto(id!, file, file.name, kundensichtbar, clientUuid);
        return null;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["outbox", id] });
    },
  });

  const unterschriftMutation = useMutation({
    mutationFn: ({ blob, unterzeichnerName }: { blob: Blob; unterzeichnerName: string }) =>
      vorgangEventsApi.uploadUnterschrift(id!, blob, unterzeichnerName),
    onSuccess: () => {
      setShowUnterschriftPad(false);
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
  });

  const startTimerMutation = useMutation({
    mutationFn: () => zeiterfassungApi.start(id!, taetigkeit || undefined),
    onSuccess: () => {
      setTaetigkeit("");
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
    },
  });

  const stopTimerMutation = useMutation({
    mutationFn: (timerId: string) => zeiterfassungApi.stop(timerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
    },
  });

  if (!vorgang) return <p className="text-center text-slate-500">Lädt…</p>;

  // Neuestes Ereignis oben, ältestes unten -- der Backend-Endpunkt liefert
  // bereits "ORDER BY id DESC" (siehe app/api/routes/vorgang_events.py),
  // hier also unveraendert uebernehmen statt umzudrehen.
  const sichtbareEvents = kundenansicht
    ? (events ?? []).filter((e) => e.kundensichtbar)
    : events ?? [];
  const eigeneOutboxItems = (outboxItems ?? []).filter((i) => i.vorgang_id === id);

  const gesamtSekunden = (zeiterfassungListe ?? []).reduce((summe, e) => {
    if (!e.ende_at) return summe;
    return summe + (new Date(e.ende_at).getTime() - new Date(e.start_at).getTime()) / 1000;
  }, 0);
  const gesamtStunden = formatSekundenAlsHHMM(gesamtSekunden);

  const timerLaeuftHier = laufenderTimer && laufenderTimer.vorgang_id === id;
  const timerLaeuftAnderswo = laufenderTimer && laufenderTimer.vorgang_id !== id;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-slate-400">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <div className="text-xs text-slate-400 dark:text-slate-500">{vorgang.vorgangsnummer}</div>
        <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">{vorgang.titel}</h1>

        <div className="mt-1 flex items-center justify-between">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
            {kunde && (
              <button
                onClick={() => navigate(`/kunden/${kunde.id}`)}
                className="text-blue-700 underline-offset-2 hover:underline dark:text-blue-400"
              >
                {kunde.name}
              </button>
            )}
            {anlage && (
              <>
                <span className="text-slate-300 dark:text-slate-600">·</span>
                <button
                  onClick={() => navigate(`/anlagen/${anlage.id}`)}
                  className="text-blue-700 underline-offset-2 hover:underline dark:text-blue-400"
                >
                  {anlage.bezeichnung}
                </button>
              </>
            )}
          </div>
          {!editingZuordnung && (
            <button
              onClick={() => {
                setEditKundeId(vorgang.kunde_id);
                setEditAnlageId(vorgang.anlage_id ?? "");
                setZuordnungError(null);
                setEditingZuordnung(true);
              }}
              className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
            >
              Bearbeiten
            </button>
          )}
        </div>

        {editingZuordnung && (
          <div className="mt-2 space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Kunde</label>
              <select
                value={editKundeId}
                onChange={(e) => {
                  setEditKundeId(e.target.value);
                  setEditAnlageId("");
                }}
                className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              >
                {alleKunden?.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.name} ({k.kundennummer})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
                Anlage (optional)
              </label>
              <select
                value={editAnlageId}
                onChange={(e) => setEditAnlageId(e.target.value)}
                className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="">Keine Anlage</option>
                {anlagenFuerEditKunde?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.bezeichnung}
                  </option>
                ))}
              </select>
            </div>
            {zuordnungError && <p className="text-xs text-red-700 dark:text-red-400">{zuordnungError}</p>}
            <div className="flex gap-2">
              <button
                onClick={() => zuordnungMutation.mutate()}
                disabled={!editKundeId || zuordnungMutation.isPending}
                className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Speichern
              </button>
              <button
                onClick={() => {
                  setEditingZuordnung(false);
                  setZuordnungError(null);
                }}
                className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        {vorgang.beschreibung && (
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{vorgang.beschreibung}</p>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="text-sm text-slate-500 dark:text-slate-400">Status:</label>
          <select
            value={vorgang.status}
            onChange={(e) => statusMutation.mutate(e.target.value as VorgangStatus)}
            className="btn-touch rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </select>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            Priorität {vorgang.prioritaet}
          </span>
        </div>
      </div>

      <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">Arbeitszeit</h2>
          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
            Bisher {gesamtStunden} Std.
          </span>
        </div>
        {timerLaeuftHier ? (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
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
              className="btn-touch flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <button
              onClick={() => startTimerMutation.mutate()}
              disabled={startTimerMutation.isPending || !!timerLaeuftAnderswo}
              title={timerLaeuftAnderswo ? "Es läuft bereits ein Timer für einen anderen Vorgang" : ""}
              className="btn-touch shrink-0 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Zeit starten
            </button>
          </div>
        )}

        {(zeiterfassungListe ?? []).filter((e) => e.ende_at).length > 0 && (
          <div className="mt-2 space-y-1 border-t border-slate-100 pt-2 dark:border-slate-800">
            {[...(zeiterfassungListe ?? [])]
              .filter((e) => e.ende_at)
              .sort((a, b) => new Date(b.start_at).getTime() - new Date(a.start_at).getTime())
              .map((e) => {
                const dauerSekunden =
                  (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000;
                const techniker = users?.find((u) => u.id === e.techniker_id);
                return (
                  <div
                    key={e.id}
                    className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400"
                  >
                    <span>
                      {techniker?.name ?? "—"}
                      {e.taetigkeit && ` · ${e.taetigkeit}`}
                      {" · "}
                      {new Date(e.start_at).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin" })}
                    </span>
                    <span className="shrink-0 font-medium text-slate-600 dark:text-slate-300">
                      {formatSekundenAlsHHMM(dauerSekunden)} Std.
                    </span>
                  </div>
                );
              })}
          </div>
        )}
      </div>

      <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">Termine</h2>
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
              className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
            >
              {showTerminForm ? "Abbrechen" : "+ Termin planen"}
            </button>
          )}
        </div>

        {terminWarnungen.length > 0 && (
          <div className="mb-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
            {terminWarnungen.map((w, i) => (
              <p key={i}>⚠️ {w.meldung}</p>
            ))}
          </div>
        )}

        {showTerminForm && (
          <div className="mb-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-slate-800/60">
            <input
              value={terminTitel}
              onChange={(e) => setTerminTitel(e.target.value)}
              placeholder="Titel"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <select
              value={terminTechnikerId}
              onChange={(e) => setTerminTechnikerId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
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
                className="w-1/2 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
              <input
                type="datetime-local"
                value={terminEnde}
                onChange={(e) => setTerminEnde(e.target.value)}
                className="w-1/2 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <button
              disabled={!terminTitel || !terminTechnikerId || terminMutation.isPending}
              onClick={() => terminMutation.mutate()}
              className="btn-touch w-full rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Anlegen
            </button>
          </div>
        )}

        {(termine ?? []).length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500">Keine Termine geplant.</p>
        ) : (
          <div className="space-y-1.5">
            {termine!.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-slate-800/60"
              >
                <div>
                  <div className="font-medium text-slate-700 dark:text-slate-300">{t.titel}</div>
                  <div className="text-xs text-slate-400 dark:text-slate-500">
                    {new Date(t.start_at).toLocaleString("de-DE", {
                      timeZone: "Europe/Berlin",
                      dateStyle: "short",
                      timeStyle: "short",
                    })}
                  </div>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    t.status === "abgesagt"
                      ? "bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400"
                      : "bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300"
                  }`}
                >
                  {t.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">Mängel</h2>
          <div className="flex items-center gap-3">
            {(maengel ?? []).length > 0 && (
              <button
                onClick={() => maengelProtokollMutation.mutate()}
                disabled={maengelProtokollMutation.isPending}
                className="btn-touch text-xs font-medium text-slate-500 dark:text-slate-400"
              >
                📄 Protokoll
              </button>
            )}
            <button
              onClick={() => setShowMangelForm((v) => !v)}
              className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
            >
              {showMangelForm ? "Abbrechen" : "+ Mangel melden"}
            </button>
          </div>
        </div>

        {showMangelForm && (
          <div className="mb-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-slate-800/60">
            <textarea
              value={mangelBeschreibung}
              onChange={(e) => setMangelBeschreibung(e.target.value)}
              placeholder="Was ist defekt?"
              rows={2}
              className="w-full resize-none rounded-md border border-slate-300 p-2 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <select
              value={mangelSchweregrad}
              onChange={(e) => setMangelSchweregrad(e.target.value as MangelSchweregrad)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
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
              className="btn-touch w-full rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Erfassen
            </button>
          </div>
        )}

        {(maengel ?? []).length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500">Keine Mängel erfasst.</p>
        ) : (
          <div className="space-y-1.5">
            {maengel!.map((m) => (
              <div key={m.id} className="rounded-md bg-slate-50 p-2 text-sm dark:bg-slate-800/60">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-slate-700 dark:text-slate-300">{m.beschreibung}</p>
                  <span className="shrink-0 rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                    {m.schweregrad}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-xs text-slate-400 dark:text-slate-500">{m.status}</span>
                  {m.status === "offen" && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => mangelStatusMutation.mutate({ mangelId: m.id, status: "behoben" })}
                        className="btn-touch text-xs font-medium text-green-700 dark:text-green-400"
                      >
                        Behoben
                      </button>
                      <button
                        onClick={() => mangelStatusMutation.mutate({ mangelId: m.id, status: "abgelehnt" })}
                        className="btn-touch text-xs font-medium text-red-700 dark:text-red-400"
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
            className="btn-touch mt-2 w-full rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
          >
            Angebot aus offenen Mängeln erstellen
          </button>
        )}
      </div>

      <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">Material</h2>
          <div className="flex gap-3">
            <button
              onClick={() => setShowBedarfForm((v) => !v)}
              className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
            >
              {showBedarfForm ? "Abbrechen" : "+ Material bestellen"}
            </button>
            <button
              onClick={() => setShowMaterialForm((v) => !v)}
              className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
            >
              {showMaterialForm ? "Abbrechen" : "+ Material verwenden"}
            </button>
          </div>
        </div>

        {showBedarfForm && (
          <div className="mb-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-slate-800/60">
            <select
              value={bedarfMaterialId}
              onChange={(e) => setBedarfMaterialId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="">Material wählen…</option>
              {(materialListe ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.bezeichnung}
                </option>
              ))}
              <option value={NEU_MATERIAL}>+ Neues Material anlegen…</option>
            </select>

            {bedarfMaterialId === NEU_MATERIAL && (
              <div className="space-y-2 rounded-md border border-dashed border-slate-300 p-2 dark:border-slate-700">
                <input
                  type="text"
                  value={bedarfNeuBezeichnung}
                  onChange={(e) => setBedarfNeuBezeichnung(e.target.value)}
                  placeholder="Bezeichnung"
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                />
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={bedarfNeuEinheit}
                    onChange={(e) => setBedarfNeuEinheit(e.target.value)}
                    placeholder="Einheit"
                    className="w-20 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                  />
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={bedarfNeuEinzelpreis}
                    onChange={(e) => setBedarfNeuEinzelpreis(e.target.value)}
                    placeholder="Preis (optional)"
                    className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                  />
                </div>
                <select
                  value={bedarfNeuLieferantId}
                  onChange={(e) => setBedarfNeuLieferantId(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                >
                  <option value="">Kein Lieferant hinterlegt</option>
                  {(lieferantenFuerNeuesMaterial ?? []).map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex gap-2">
              <input
                type="number"
                step="0.01"
                min="0"
                value={bedarfMenge}
                onChange={(e) => setBedarfMenge(e.target.value)}
                placeholder="Menge"
                className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
              <select
                value={bedarfZweck}
                onChange={(e) => setBedarfZweck(e.target.value as MaterialBedarfZweck)}
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="bestellung">Zur Bestellung</option>
                <option value="angebot">Für Angebot</option>
              </select>
            </div>
            <input
              type="text"
              value={bedarfNotiz}
              onChange={(e) => setBedarfNotiz(e.target.value)}
              placeholder="Notiz (optional)"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <button
              disabled={
                !bedarfMaterialId ||
                !bedarfMenge ||
                (bedarfMaterialId === NEU_MATERIAL && !bedarfNeuBezeichnung.trim()) ||
                materialBedarfMutation.isPending
              }
              onClick={() => materialBedarfMutation.mutate()}
              className="btn-touch w-full rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Vormerken
            </button>
            {materialBedarfMutation.isError && (
              <p className="text-xs text-red-700 dark:text-red-400">
                {materialBedarfMutation.error instanceof ApiError
                  ? materialBedarfMutation.error.message
                  : "Fehler beim Vormerken"}
              </p>
            )}
          </div>
        )}

        {(materialBedarfe ?? []).length > 0 && (
          <div className="mb-2 space-y-1">
            {materialBedarfe!.map((b) => (
              <div
                key={b.id}
                className="flex items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-sm dark:bg-slate-800/60"
              >
                <span className="text-slate-700 dark:text-slate-200">
                  {b.menge}× {b.material_bezeichnung}
                  <span className="ml-1.5 rounded-full bg-slate-200 px-1.5 py-0.5 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                    {b.zweck === "angebot" ? "Angebot" : "Bestellung"} · {b.status}
                  </span>
                </span>
                {b.status === "offen" && (
                  <button
                    onClick={() => bedarfEntfernenMutation.mutate(b.id)}
                    className="btn-touch text-xs text-red-700 dark:text-red-400"
                  >
                    Entfernen
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {showMaterialForm && (
          <div className="space-y-2 rounded-md bg-slate-50 p-2 dark:bg-slate-800/60">
            <select
              value={materialId}
              onChange={(e) => {
                setMaterialId(e.target.value);
                // Fuer Techniker das eigene zugewiesene Fahrzeug als
                // Standard-Lagerort vorschlagen (siehe Techniker-
                // Zuweisungen-Seite) -- spart bei jedem Materialverbrauch
                // aus dem eigenen Fahrzeug den manuellen Auswahlschritt.
                setMaterialLagerId(meinFahrzeug?.id ?? "");
              }}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="">Material wählen…</option>
              {(materialListe ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.bezeichnung} ({m.bestand_gesamt} {m.einheit} gesamt verfügbar)
                </option>
              ))}
            </select>
            {materialId && (
              <select
                value={materialLagerId}
                onChange={(e) => setMaterialLagerId(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="">Lagerort wählen…</option>
                {(materialListe?.find((m) => m.id === materialId)?.bestaende ?? []).map((b) => (
                  <option key={b.lager_id} value={b.lager_id}>
                    {b.lager_bezeichnung} ({b.menge} verfügbar)
                  </option>
                ))}
                {lagerorte
                  .filter(
                    (l) => !materialListe?.find((m) => m.id === materialId)?.bestaende.some((b) => b.lager_id === l.id)
                  )
                  .map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.bezeichnung} (0 verfügbar)
                    </option>
                  ))}
              </select>
            )}
            <div className="flex gap-2">
              <input
                type="number"
                step="0.01"
                min="0"
                value={materialMenge}
                onChange={(e) => setMaterialMenge(e.target.value)}
                placeholder="Menge"
                className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
              <button
                disabled={!materialId || !materialLagerId || !materialMenge || materialVerwendenMutation.isPending}
                onClick={() => materialVerwendenMutation.mutate()}
                className="btn-touch shrink-0 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Erfassen
              </button>
            </div>
            {materialVerwendenMutation.isError && (
              <p className="text-xs text-red-700 dark:text-red-400">
                {materialVerwendenMutation.error instanceof ApiError
                  ? materialVerwendenMutation.error.message
                  : "Fehler beim Erfassen"}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center justify-end gap-2">
        <span className="text-sm text-slate-500 dark:text-slate-400">
          {kundenansicht ? "Kundenansicht" : "Interne Ansicht"}
        </span>
        <button
          onClick={() => setKundenansicht((v) => !v)}
          className={`btn-touch rounded-full px-3 py-1 text-xs font-semibold ${
            kundenansicht
              ? "bg-blue-600 text-white"
              : "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
          }`}
        >
          Umschalten
        </button>
      </div>

      <div>
        {sichtbareEvents.length === 0 && eigeneOutboxItems.length === 0 ? (
          <p className="text-center text-sm text-slate-400 dark:text-slate-500">Noch keine Einträge.</p>
        ) : (
          <>
            {/* Noch nicht synchronisierte Einträge sind immer die neuesten
                -- stehen deshalb vor den bereits synchronisierten Events. */}
            {!kundenansicht &&
              eigeneOutboxItems.map((item) => (
                <OutboxBubble
                  key={item.client_uuid}
                  item={item}
                  onDiscard={async (clientUuid) => {
                    await discardOutboxItem(clientUuid);
                    queryClient.invalidateQueries({ queryKey: ["outbox", id] });
                  }}
                />
              ))}
            {sichtbareEvents.map((event) => (
              <EventBubble key={event.id} event={event} onHighlight={(eventId) => highlightMutation.mutate(eventId)} />
            ))}
          </>
        )}
      </div>

      {!kundenansicht && (
        <div className="sticky bottom-24 space-y-2 rounded-lg bg-white p-3 shadow-md dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
          <div className="relative">
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Kommentar schreiben…"
              rows={2}
              className="w-full resize-none rounded-md border border-slate-300 p-2 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            {showMentionPicker && (
              <div className="absolute bottom-full left-0 mb-1 max-h-40 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-800">
                {users?.map((u) => (
                  <button
                    key={u.id}
                    onClick={() => {
                      setComment((c) => `${c}@[${u.name}](${u.id}) `);
                      setShowMentionPicker(false);
                    }}
                    className="btn-touch block w-full px-3 py-2 text-left text-sm hover:bg-slate-50 dark:text-slate-100 dark:hover:bg-slate-700"
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
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setShowMentionPicker((v) => !v)}
                title="Erwähnen"
                aria-label="Erwähnen"
                className="btn-touch flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-base text-slate-600 dark:bg-slate-800 dark:text-slate-300"
              >
                @
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={fotoMutation.isPending}
                title="Foto anhängen"
                aria-label="Foto anhängen"
                className="btn-touch flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-base text-slate-600 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
              >
                📷
              </button>
              <button
                onClick={() => setShowUnterschriftPad((v) => !v)}
                title="Unterschrift erfassen"
                aria-label="Unterschrift erfassen"
                className="btn-touch flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-base text-slate-600 dark:bg-slate-800 dark:text-slate-300"
              >
                ✍️
              </button>
              <button
                onClick={() => setKundensichtbar((v) => !v)}
                title={kundensichtbar ? "Für Kunde sichtbar – antippen zum Verbergen" : "Nur intern – antippen um für Kunde sichtbar zu machen"}
                aria-label="Für Kunde sichtbar umschalten"
                aria-pressed={kundensichtbar}
                className={`btn-touch flex h-9 w-9 items-center justify-center rounded-full text-base ${
                  kundensichtbar
                    ? "bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-300"
                    : "bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500"
                }`}
              >
                {kundensichtbar ? "👁️" : "🚫"}
              </button>
            </div>
            <button
              onClick={() => commentMutation.mutate()}
              disabled={!comment.trim() || commentMutation.isPending}
              className="btn-touch shrink-0 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Senden
            </button>
          </div>

          {showUnterschriftPad && (
            <div className="mt-2">
              <SignaturePad
                isSaving={unterschriftMutation.isPending}
                onCancel={() => setShowUnterschriftPad(false)}
                onSave={(blob, unterzeichnerName) =>
                  unterschriftMutation.mutate({ blob, unterzeichnerName })
                }
              />
              {unterschriftMutation.isError && (
                <p className="mt-1 text-xs text-red-700 dark:text-red-400">
                  {unterschriftMutation.error instanceof ApiError
                    ? unterschriftMutation.error.message
                    : "Fehler beim Speichern der Unterschrift"}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
