import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Building2, Camera, Clock, Eye, EyeOff, FileText, Mail, PenLine, Star, UserCheck, UserPlus } from "lucide-react";
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  angeboteApi,
  rechnungenApi,
  anlagenApi,
  fahrzeugZuweisungenApi,
  highlightsApi,
  kundenApi,
  leistungsverzeichnisApi,
  lieferantenApi,
  maengelApi,
  mandantEinstellungenApi,
  materialApi,
  materialBedarfeApi,
  partnerApi,
  standorteApi,
  termineApi,
  usersApi,
  vorgangEventsApi,
  vorgaengeApi,
  zeiterfassungApi,
} from "../../api/endpoints";
import { EmailSection } from "../../components/EmailSection";
import { FormularAbschnitt } from "../../components/FormularAbschnitt";
import { MentionText } from "../../components/MentionText";
import { SearchableSelect } from "../../components/SearchableSelect";
import { SignaturePad } from "../../components/SignaturePad";
import { useAuth } from "../../context/AuthContext";
import { cacheEvents, cacheKunde, getCachedEvents, getCachedKunde } from "../../offline/cache";
import { discardOutboxItem, getOutboxItems, queueFoto, queueKommentar, queueStatusChange } from "../../offline/outbox";
import { formatSekundenAlsHHMM } from "../../utils/duration";
import { istModulAktiv } from "../../utils/module";
import { openPdfBlob } from "../../utils/pdf";
import type { OutboxItem } from "../../offline/db";
import type {
  Adresse,
  EmailLog,
  Leistungstyp,
  MangelSchweregrad,
  MangelStatus,
  MaterialBedarfZweck,
  PartnerFreigabeStatus,
  TerminWarnung,
  VorgangEvent,
  VorgangStatus,
} from "../../types";

// Lazy statt statisch importiert: mapbox-gl allein ist ~1.8 MB und wuerde
// sonst in jedem Bundle landen, auch fuer Nutzer, die nie eine Karte sehen
// (und den PWA-Precache-Limit von 2 MiB sprengen).
const MapboxMap = lazy(() => import("../../components/MapboxMap").then((m) => ({ default: m.MapboxMap })));

const SCHWEREGRAD_OPTIONEN: { value: MangelSchweregrad; label: string }[] = [
  { value: "niedrig", label: "Niedrig" },
  { value: "mittel", label: "Mittel" },
  { value: "hoch", label: "Hoch" },
  { value: "kritisch", label: "Kritisch" },
];

const LEISTUNGSTYPEN: { value: Leistungstyp; label: string }[] = [
  { value: "stoerung", label: "Störung" },
  { value: "installation", label: "Installation" },
  { value: "wartung", label: "Wartung" },
  { value: "pruefung", label: "Prüfung" },
  { value: "beratung", label: "Beratung" },
  { value: "planung", label: "Planung" },
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

// Spiegelt app/services/vorgang_completion_service.py:VORGANG_STATUS_GESCHLOSSEN
// -- "Ticket übernehmen" ergibt fuer bereits geschlossene Vorgaenge keinen
// Sinn mehr (das Backend lehnt es dort ohnehin mit 409 ab).
const VORGANG_STATUS_GESCHLOSSEN: VorgangStatus[] = ["abgeschlossen", "abgerechnet", "storniert"];

const PRIORITAET_OPTIONEN = [1, 2, 3, 4, 5];

const FREIGABE_LABEL: Record<PartnerFreigabeStatus, string> = {
  vorgeschlagen: "Wartet auf Rückmeldung",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

const FREIGABE_FARBE: Record<PartnerFreigabeStatus, string> = {
  vorgeschlagen: "bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
  angenommen: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
  abgelehnt: "bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400",
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
  leistung: "Leistung erfasst",
};

const NEU_MATERIAL = "__neu__";

const ANCHOR_ABSCHNITTE: { ziel: string; label: string }[] = [
  { ziel: "abschnitt-uebersicht", label: "Übersicht" },
  { ziel: "abschnitt-zeit", label: "Zeit" },
  { ziel: "abschnitt-termine", label: "Termine" },
  { ziel: "abschnitt-maengel", label: "Mängel" },
  { ziel: "abschnitt-material", label: "Positionen" },
  { ziel: "abschnitt-verlauf", label: "Verlauf" },
];

// Unauffaellige, transparente Pill zur Unterscheidung der Eintragsart im
// gemeinsamen Verlauf (Kommentar/E-Mail laufen dort jetzt durcheinander) --
// bewusst zurueckhaltend statt eines vollflaechigen Badges, siehe
// Design-Vorschlag "Feed und Detail neu gedacht".
function VerlaufTypTag({ children }: { children: string }) {
  return (
    <span className="rounded-full border border-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-400 dark:border-stone-700 dark:text-stone-500">
      {children}
    </span>
  );
}

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
    <div className="mb-3 rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-400 dark:text-stone-500">
        <div className="flex items-center gap-1.5">
          <span>{new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}</span>
          {event.event_type === "kommentar" && <VerlaufTypTag>Kommentar</VerlaufTypTag>}
        </div>
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
            className="btn-touch mb-2 flex items-center gap-1 text-xs font-medium text-amber-600 dark:text-amber-400"
          >
            <Star size={13} strokeWidth={2} /> Als Highlight markieren
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
            <p className="mt-1 text-xs text-slate-500 dark:text-stone-400">
              Unterschrieben von: {event.payload.unterzeichner_name}
            </p>
          )}
        </div>
      )}
      {event.body && (
        <p className="whitespace-pre-wrap text-sm text-slate-800 dark:text-stone-100">
          <MentionText text={event.body} />
        </p>
      )}
    </div>
  );
}

// E-Mails werden nicht mehr in einer separaten Box gefuehrt, sondern im
// gemeinsamen Verlauf mit den Kommentaren gemischt (siehe Design-Vorschlag
// "Feed und Detail neu gedacht") -- gleiche Bubble-Optik wie EventBubble,
// nur mit Betreff/Empfaenger statt Freitext-Body.
function EmailBubble({ email }: { email: EmailLog }) {
  return (
    <div className="mb-3 rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-400 dark:text-stone-500">
        <div className="flex items-center gap-1.5">
          <span>{new Date(email.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}</span>
          <VerlaufTypTag>E-Mail</VerlaufTypTag>
        </div>
        {email.status === "fehler" && (
          <span className="rounded-full bg-red-50 px-2 py-0.5 text-red-700 dark:bg-red-500/15 dark:text-red-400">
            Fehler
          </span>
        )}
      </div>
      <div className="mb-1 flex items-start gap-1.5 text-sm text-slate-800 dark:text-stone-100">
        <Mail size={14} strokeWidth={2} className="mt-0.5 shrink-0 text-slate-400 dark:text-stone-500" />
        <div>
          <span className="font-medium">{email.betreff || "(ohne Betreff)"}</span>
          <span className="text-slate-400 dark:text-stone-500"> · an {email.empfaenger}</span>
        </div>
      </div>
      {email.status === "fehler" && email.fehlermeldung && (
        <p className="text-xs text-red-600 dark:text-red-400">{email.fehlermeldung}</p>
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
          : "border-slate-300 bg-slate-50 dark:border-stone-700 dark:bg-stone-800/60"
      }`}
    >
      <div className="mb-1 flex items-center justify-between gap-1 text-xs">
        {item.failed ? (
          <span className="flex items-center gap-1 text-red-500 dark:text-red-400">
            <AlertTriangle size={13} strokeWidth={2} /> Vom Server abgelehnt{item.errorMessage ? `: ${item.errorMessage}` : ""}
          </span>
        ) : (
          <span className="flex items-center gap-1 text-slate-400 dark:text-stone-500">
            <Clock size={13} strokeWidth={2} />
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
        <p className="flex items-center gap-1 text-sm text-slate-600 dark:text-stone-300">
          <Camera size={14} strokeWidth={2} /> Foto wartet auf Synchronisierung
        </p>
      ) : item.kind === "status" ? (
        <p className="text-sm text-slate-600 dark:text-stone-300">Statusänderung zu „{item.statusValue}“ wartet auf Synchronisierung</p>
      ) : (
        <p className="whitespace-pre-wrap text-sm text-slate-700 dark:text-stone-300">{item.body}</p>
      )}
    </div>
  );
}

function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function leereAdresse(adresse: Adresse | null | undefined): { strasse: string; plz: string; ort: string } {
  return { strasse: adresse?.strasse ?? "", plz: adresse?.plz ?? "", ort: adresse?.ort ?? "" };
}

function adresseAlsZeile(adresse: Adresse | null | undefined): string {
  return [adresse?.strasse, [adresse?.plz, adresse?.ort].filter(Boolean).join(" ")]
    .filter(Boolean)
    .join(", ");
}

// id optional als Prop, damit die Office-Oberflaeche diese Seite in ihrem
// Detail-Panel einbetten kann, ohne dass es einen zweiten, parallel zu
// pflegenden Nachbau braucht. Ohne Prop verhaelt sie sich wie bisher.
export function VorgangDetailPage({ id: idProp }: { id?: string } = {}) {
  const { id: idParam } = useParams<{ id: string }>();
  const id = idProp ?? idParam;
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();
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
  const [showLeistungForm, setShowLeistungForm] = useState(false);
  const [lvPositionId, setLvPositionId] = useState("");
  const [lvMenge, setLvMenge] = useState("");
  const [showPartnerForm, setShowPartnerForm] = useState(false);
  const [partnerAuswahl, setPartnerAuswahl] = useState("");
  const [partnerHonorar, setPartnerHonorar] = useState("");
  const [partnerWarnung, setPartnerWarnung] = useState(false);
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
  const [editingAdresse, setEditingAdresse] = useState(false);
  const [adresseForm, setAdresseForm] = useState(() => leereAdresse(null));
  const [adresseError, setAdresseError] = useState<string | null>(null);
  const [showWartetKundeDialog, setShowWartetKundeDialog] = useState(false);
  const [wiedervorlageTage, setWiedervorlageTage] = useState("");
  const [showFolgeAuftragDialog, setShowFolgeAuftragDialog] = useState(false);
  const [folgeAuftragLeistungstyp, setFolgeAuftragLeistungstyp] = useState<Leistungstyp>("stoerung");
  const [folgeVorgangId, setFolgeVorgangId] = useState<string | null>(null);

  const kannDisponieren = hatRecht("vorgaenge", "bearbeiten");
  const kannLoeschen = hatRecht("vorgaenge", "loeschen");
  const kannPartnerVerwalten =
    istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "bearbeiten");

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
  const { data: standort } = useQuery({
    queryKey: ["standort", vorgang?.standort_id],
    queryFn: () => standorteApi.get(vorgang!.standort_id!),
    enabled: !!vorgang?.standort_id,
  });
  const { data: parentVorgang } = useQuery({
    queryKey: ["vorgang", vorgang?.parent_vorgang_id],
    queryFn: () => vorgaengeApi.get(vorgang!.parent_vorgang_id!),
    enabled: !!vorgang?.parent_vorgang_id,
  });
  const { data: folgeAuftraege } = useQuery({
    queryKey: ["vorgaenge", "folge", id],
    queryFn: () => vorgaengeApi.list({ parent_vorgang_id: id! }),
    enabled: !!id,
  });
  const { data: mandantEinstellungen } = useQuery({
    queryKey: ["mandant-einstellungen"],
    queryFn: mandantEinstellungenApi.get,
    enabled: showWartetKundeDialog,
  });
  const { data: weitereAnlagen } = useQuery({
    queryKey: ["vorgang-anlagen", id],
    queryFn: () => vorgaengeApi.anlagen(id!),
    enabled: !!id,
  });
  const [showAnlageHinzufuegen, setShowAnlageHinzufuegen] = useState(false);
  const [neueAnlageId, setNeueAnlageId] = useState("");
  const { data: anlagenFuerVorgangKunde } = useQuery({
    queryKey: ["anlagen", vorgang?.kunde_id],
    queryFn: () => anlagenApi.list(vorgang!.kunde_id, undefined, true),
    enabled: showAnlageHinzufuegen && !!vorgang?.kunde_id,
  });
  const bereitsZugeordneteAnlageIds = new Set([
    ...(weitereAnlagen ?? []).map((a) => a.id),
    ...(vorgang?.anlage_id ? [vorgang.anlage_id] : []),
  ]);
  const anlageHinzufuegenMutation = useMutation({
    mutationFn: (anlageId: string) => vorgaengeApi.anlagenHinzufuegen(id!, [anlageId]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang-anlagen", id] });
      setShowAnlageHinzufuegen(false);
      setNeueAnlageId("");
    },
  });
  const anlageEntfernenMutation = useMutation({
    mutationFn: (anlageId: string) => vorgaengeApi.anlageEntfernen(id!, anlageId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vorgang-anlagen", id] }),
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
  const adresseMutation = useMutation({
    mutationFn: () =>
      vorgaengeApi.update(id!, {
        adresse:
          adresseForm.strasse || adresseForm.plz || adresseForm.ort
            ? {
                strasse: adresseForm.strasse || undefined,
                plz: adresseForm.plz || undefined,
                ort: adresseForm.ort || undefined,
              }
            : null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      setEditingAdresse(false);
      setAdresseError(null);
    },
    onError: (err) => setAdresseError(err instanceof ApiError ? err.message : "Fehler"),
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
  // Gleicher queryKey wie in der EmailSection weiter unten -- React Query
  // dedupliziert daher den Request, es wird trotz zwei useQuery-Aufrufen
  // nur einmal geladen.
  const { data: emails } = useQuery({
    queryKey: ["vorgang-emails", id],
    queryFn: () => vorgaengeApi.emails(id!),
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

  const deleteMangelMutation = useMutation({
    mutationFn: (mangelId: string) => maengelApi.remove(mangelId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["maengel", "vorgang", id] }),
  });

  const deleteTerminMutation = useMutation({
    mutationFn: (terminId: string) => termineApi.remove(terminId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["termine", "vorgang", id] }),
  });

  const kannPapierkorbLoeschen = currentUser?.role === "loesch_operativ";

  const angebotAusMaengelnMutation = useMutation({
    mutationFn: (mangelIds: string[]) => angeboteApi.createFromMaengel(mangelIds),
    onSuccess: (angebot) => navigate(`/angebote/${angebot.id}`),
  });

  const angebotAusVorgangMutation = useMutation({
    mutationFn: () => angeboteApi.createFromVorgang(id!),
    onSuccess: (angebot) => navigate(`/angebote/${angebot.id}`),
  });

  const rechnungAusVorgangMutation = useMutation({
    mutationFn: () => rechnungenApi.create({ kunde_id: vorgang!.kunde_id, vorgang_id: id }),
    onSuccess: (rechnung) => navigate(`/rechnungen/${rechnung.id}`),
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
    enabled: showMaterialForm && !!currentUser?.nur_zugewiesene_kunden,
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
      queryClient.invalidateQueries({ queryKey: ["material-verwendungen", "vorgang", id] });
    },
  });

  const { data: leistungsverzeichnis } = useQuery({
    queryKey: ["leistungsverzeichnis", kunde?.id],
    queryFn: () => leistungsverzeichnisApi.list(kunde!.id),
    enabled: showLeistungForm && !!kunde,
  });

  const leistungVerwendenMutation = useMutation({
    mutationFn: () => leistungsverzeichnisApi.verwenden(lvPositionId, id!, lvMenge),
    onSuccess: () => {
      setShowLeistungForm(false);
      setLvPositionId("");
      setLvMenge("");
      queryClient.invalidateQueries({ queryKey: ["stories"] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnis-verwendungen", "vorgang", id] });
    },
  });

  const { data: partnerListe } = useQuery({
    queryKey: ["partner"],
    queryFn: () => partnerApi.list(),
    enabled: showPartnerForm && kannPartnerVerwalten,
  });
  const { data: zugewiesenerPartner } = useQuery({
    queryKey: ["partner", vorgang?.partner_id],
    queryFn: () => partnerApi.get(vorgang!.partner_id!),
    enabled: kannPartnerVerwalten && !!vorgang?.partner_id,
  });

  const partnerZuweisenMutation = useMutation({
    mutationFn: () => vorgaengeApi.partnerZuweisen(id!, partnerAuswahl, partnerHonorar || undefined),
    onSuccess: (antwort) => {
      setShowPartnerForm(false);
      setPartnerAuswahl("");
      setPartnerHonorar("");
      setPartnerWarnung(antwort.freistellungsbescheinigung_warnung);
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
    },
  });

  const partnerAufhebenMutation = useMutation({
    mutationFn: () => vorgaengeApi.partnerZuweisen(id!, null),
    onSuccess: () => {
      setPartnerWarnung(false);
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
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
  const { data: materialVerwendungen } = useQuery({
    queryKey: ["material-verwendungen", "vorgang", id],
    queryFn: () => materialApi.verwendungen(id!),
    enabled: !!id,
  });
  const { data: lvVerwendungen } = useQuery({
    queryKey: ["leistungsverzeichnis-verwendungen", "vorgang", id],
    queryFn: () => leistungsverzeichnisApi.verwendungen(id!),
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

  const deleteVorgangMutation = useMutation({
    mutationFn: () => vorgaengeApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      navigate("/feed");
    },
  });

  const statusMutation = useMutation({
    mutationFn: async ({
      status,
      wiedervorlageTage,
    }: {
      status: VorgangStatus;
      wiedervorlageTage?: number;
    }) => {
      try {
        return await vorgaengeApi.update(id!, {
          status,
          ...(wiedervorlageTage ? { wiedervorlage_tage: wiedervorlageTage } : {}),
        });
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

  const folgeAuftragMutation = useMutation({
    mutationFn: (leistungstyp: Leistungstyp) => vorgaengeApi.folgeAuftrag(id!, leistungstyp),
    onSuccess: (result) => {
      setFolgeVorgangId(result.id);
      queryClient.invalidateQueries({ queryKey: ["vorgaenge", "folge", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
  });

  const uebernehmenMutation = useMutation({
    mutationFn: () => vorgaengeApi.uebernehmen(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
  });

  const prioritaetMutation = useMutation({
    mutationFn: (prioritaet: number) => vorgaengeApi.update(id!, { prioritaet }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vorgang", id] }),
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

  // Eigene Adresse am Vorgang hat Vorrang; ohne sie zeigen wir die Adresse
  // des zugeordneten Standorts bzw. ersatzweise der Anlage, damit die Karte
  // auch beim reinen Auswaehlen eines Standorts erscheint.
  const anzeigeAdresse: Adresse | null = vorgang.adresse ?? standort?.adresse ?? anlage?.adresse ?? null;
  // Koordinaten nur vertrauen, wenn die angezeigte Adresse tatsaechlich vom
  // Standort/der Anlage kommt (siehe Kommentar zu anzeigeAdresse) -- ein
  // manueller Adress-Override am Vorgang selbst hat keine eigenen
  // geo_lat/geo_lng-Spalten und darf nicht versehentlich die Koordinaten
  // eines ganz anderen Orts anzeigen.
  const kartenKoordinaten: { lng: number; lat: number } | null =
    !vorgang.adresse && standort?.geo_lat != null && standort?.geo_lng != null
      ? { lng: standort.geo_lng, lat: standort.geo_lat }
      : !vorgang.adresse && anlage?.geo_lat != null && anlage?.geo_lng != null
        ? { lng: anlage.geo_lng, lat: anlage.geo_lat }
        : null;

  // Neuestes Ereignis oben, ältestes unten -- der Backend-Endpunkt liefert
  // bereits "ORDER BY id DESC" (siehe app/api/routes/vorgang_events.py),
  // hier also unveraendert uebernehmen statt umzudrehen.
  const sichtbareEvents = kundenansicht
    ? (events ?? []).filter((e) => e.kundensichtbar)
    : events ?? [];
  const eigeneOutboxItems = (outboxItems ?? []).filter((i) => i.vorgang_id === id);

  // E-Mails laufen im gemeinsamen Verlauf mit den Kommentaren statt in einer
  // eigenen Box (siehe Design-Vorschlag). Nur in der internen Ansicht: das
  // Kundenportal kennt EmailLog nicht, die "Kundenansicht"-Vorschau soll
  // deshalb nicht mehr zeigen, als der Kunde dort tatsaechlich sieht.
  type VerlaufEintrag = { art: "event"; zeit: string; event: VorgangEvent } | { art: "email"; zeit: string; email: EmailLog };
  const verlaufEintraege: VerlaufEintrag[] = [
    ...sichtbareEvents.map((event): VerlaufEintrag => ({ art: "event", zeit: event.created_at, event })),
    ...(kundenansicht ? [] : (emails ?? []).map((email): VerlaufEintrag => ({ art: "email", zeit: email.created_at, email }))),
  ].sort((a, b) => new Date(b.zeit).getTime() - new Date(a.zeit).getTime());

  const gesamtSekunden = (zeiterfassungListe ?? []).reduce((summe, e) => {
    if (!e.ende_at) return summe;
    return summe + (new Date(e.ende_at).getTime() - new Date(e.start_at).getTime()) / 1000;
  }, 0);
  const gesamtStunden = formatSekundenAlsHHMM(gesamtSekunden);

  const timerLaeuftHier = laufenderTimer && laufenderTimer.vorgang_id === id;
  const timerLaeuftAnderswo = laufenderTimer && laufenderTimer.vorgang_id !== id;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
          ← Zurück
        </button>
        {kannLoeschen && (
          <button
            onClick={() => {
              if (window.confirm("Vorgang wirklich löschen? Verknüpfte Daten wandern in den Papierkorb.")) {
                deleteVorgangMutation.mutate();
              }
            }}
            disabled={deleteVorgangMutation.isPending}
            className="btn-touch text-sm font-medium text-red-700 disabled:opacity-50 dark:text-red-400"
          >
            Vorgang löschen
          </button>
        )}
      </div>

      {/* Fakten-Leiste: die wichtigsten Eckdaten auf einen Blick, bevor man
          in die Karte darunter eintaucht (siehe Design-Vorschlag "Feed und
          Detail neu gedacht"). */}
      {(anlage?.bezeichnung || standort?.bezeichnung || vorgang.faelligkeit_am || !vorgang.zugewiesener_user_id) && (
        <div className="flex flex-wrap gap-1.5">
          {(anlage?.bezeichnung || standort?.bezeichnung) && (
            <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300">
              <Building2 size={13} strokeWidth={2} /> {anlage?.bezeichnung ?? standort?.bezeichnung}
            </span>
          )}
          {vorgang.faelligkeit_am && (
            <span
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                vorgang.faelligkeit_am.slice(0, 10) < new Date().toISOString().slice(0, 10) &&
                !VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status)
                  ? "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-400"
                  : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
              }`}
            >
              <Clock size={13} strokeWidth={2} />
              {vorgang.faelligkeit_am.slice(0, 10) < new Date().toISOString().slice(0, 10) &&
              !VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status)
                ? `${Math.round(
                    (new Date().setHours(0, 0, 0, 0) - new Date(vorgang.faelligkeit_am).setHours(0, 0, 0, 0)) /
                      (1000 * 60 * 60 * 24),
                  )} Tage überfällig`
                : `Fällig: ${new Date(vorgang.faelligkeit_am).toLocaleDateString("de-DE")}`}
            </span>
          )}
          {!vorgang.zugewiesener_user_id && !VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status) && (
            <span className="flex items-center gap-1.5 rounded-full border border-dashed border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 dark:border-amber-700 dark:bg-amber-500/10 dark:text-amber-400">
              <UserPlus size={13} strokeWidth={2} /> Nicht zugewiesen
            </span>
          )}
        </div>
      )}

      <div id="abschnitt-uebersicht" className="scroll-mt-4 rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="text-xs text-slate-400 dark:text-stone-500">{vorgang.vorgangsnummer}</div>
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">{vorgang.titel}</h1>
        {parentVorgang && (
          <button
            onClick={() => navigate(`/vorgaenge/${parentVorgang.id}`)}
            className="mt-0.5 block text-xs text-slate-400 underline-offset-2 hover:underline dark:text-stone-500"
          >
            Entstanden aus Vorgang {parentVorgang.vorgangsnummer}
          </button>
        )}

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
                <span className="text-slate-300 dark:text-stone-600">·</span>
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
          <div className="mt-2 space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-stone-800/60">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400">Kunde</label>
              <select
                value={editKundeId}
                onChange={(e) => {
                  setEditKundeId(e.target.value);
                  setEditAnlageId("");
                }}
                className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              >
                {alleKunden?.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.name} ({k.kundennummer})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400">
                Anlage (optional)
              </label>
              <select
                value={editAnlageId}
                onChange={(e) => setEditAnlageId(e.target.value)}
                className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
                className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Speichern
              </button>
              <button
                onClick={() => {
                  setEditingZuordnung(false);
                  setZuordnungError(null);
                }}
                className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        <div className="mt-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500 dark:text-stone-400">Adresse</span>
            {kannDisponieren && !editingAdresse && (
              <button
                onClick={() => {
                  setAdresseForm(leereAdresse(vorgang.adresse));
                  setAdresseError(null);
                  setEditingAdresse(true);
                }}
                className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
              >
                Bearbeiten
              </button>
            )}
          </div>
          {!editingAdresse &&
            (adresseAlsZeile(anzeigeAdresse) ? (
              <>
                <p className="mt-1 text-sm text-slate-700 dark:text-stone-300">
                  {adresseAlsZeile(anzeigeAdresse)}
                  {!vorgang.adresse && (standort || anlage) && (
                    <span className="ml-1 text-xs text-slate-400 dark:text-stone-500">
                      ({standort ? "Standort" : "Anlage"})
                    </span>
                  )}
                </p>
                {kartenKoordinaten ? (
                  <Suspense
                    fallback={<div className="mt-2 h-40 w-full animate-pulse rounded-lg bg-slate-200 dark:bg-stone-700/60" />}
                  >
                    <MapboxMap
                      lng={kartenKoordinaten.lng}
                      lat={kartenKoordinaten.lat}
                      className="mt-2 h-40 w-full rounded-lg"
                    />
                  </Suspense>
                ) : (
                  <div className="mt-2 flex h-40 w-full items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-center text-xs text-slate-400 dark:border-stone-700 dark:bg-stone-800/60 dark:text-stone-500">
                    Keine Kartenposition verfügbar
                  </div>
                )}
              </>
            ) : (
              <p className="mt-1 text-sm text-slate-400 dark:text-stone-500">Keine Adresse hinterlegt.</p>
            ))}
          {editingAdresse && (
            <div className="mt-2 space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-stone-800/60">
              <input
                value={adresseForm.strasse}
                onChange={(e) => setAdresseForm({ ...adresseForm, strasse: e.target.value })}
                placeholder="Straße + Hausnr."
                className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={adresseForm.plz}
                  onChange={(e) => setAdresseForm({ ...adresseForm, plz: e.target.value })}
                  placeholder="PLZ"
                  className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
                <input
                  value={adresseForm.ort}
                  onChange={(e) => setAdresseForm({ ...adresseForm, ort: e.target.value })}
                  placeholder="Ort"
                  className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
              </div>
              {adresseError && <p className="text-xs text-red-700 dark:text-red-400">{adresseError}</p>}
              <div className="flex gap-2">
                <button
                  onClick={() => adresseMutation.mutate()}
                  disabled={adresseMutation.isPending}
                  className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  Speichern
                </button>
                <button
                  onClick={() => {
                    setEditingAdresse(false);
                    setAdresseError(null);
                  }}
                  className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
                >
                  Abbrechen
                </button>
              </div>
            </div>
          )}
        </div>

        {((weitereAnlagen && weitereAnlagen.length > 0) || kannDisponieren) && (
          <div className="mt-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500 dark:text-stone-400">Weitere Anlagen</span>
              {kannDisponieren && !showAnlageHinzufuegen && (
                <button
                  onClick={() => setShowAnlageHinzufuegen(true)}
                  className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
                >
                  + Hinzufügen
                </button>
              )}
            </div>
            {(weitereAnlagen ?? []).length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1.5">
                {weitereAnlagen!.map((a) => (
                  <span
                    key={a.id}
                    className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700 dark:bg-stone-800 dark:text-stone-300"
                  >
                    <button
                      onClick={() => navigate(`/anlagen/${a.id}`)}
                      className="underline-offset-2 hover:underline"
                    >
                      {a.bezeichnung}
                    </button>
                    {kannDisponieren && (
                      <button
                        onClick={() => anlageEntfernenMutation.mutate(a.id)}
                        disabled={anlageEntfernenMutation.isPending}
                        className="text-slate-400 hover:text-red-600 dark:text-stone-500 dark:hover:text-red-400"
                        aria-label={`${a.bezeichnung} entfernen`}
                      >
                        ✕
                      </button>
                    )}
                  </span>
                ))}
              </div>
            )}
            {showAnlageHinzufuegen && (
              <div className="mt-2 flex gap-2">
                <select
                  value={neueAnlageId}
                  onChange={(e) => setNeueAnlageId(e.target.value)}
                  className="btn-touch flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                >
                  <option value="">Anlage wählen…</option>
                  {(anlagenFuerVorgangKunde ?? [])
                    .filter((a) => !bereitsZugeordneteAnlageIds.has(a.id))
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.bezeichnung}
                      </option>
                    ))}
                </select>
                <button
                  onClick={() => anlageHinzufuegenMutation.mutate(neueAnlageId)}
                  disabled={!neueAnlageId || anlageHinzufuegenMutation.isPending}
                  className="btn-touch rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  OK
                </button>
                <button
                  onClick={() => {
                    setShowAnlageHinzufuegen(false);
                    setNeueAnlageId("");
                  }}
                  className="btn-touch rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
                >
                  Abbrechen
                </button>
              </div>
            )}
          </div>
        )}

        {vorgang.beschreibung && (
          <p className="mt-2 text-sm text-slate-600 dark:text-stone-300">{vorgang.beschreibung}</p>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="text-sm text-slate-500 dark:text-stone-400">Status:</label>
          <select
            value={vorgang.status}
            onChange={(e) => {
              const status = e.target.value as VorgangStatus;
              if (status === "wartet_kunde") {
                setWiedervorlageTage("");
                setShowWartetKundeDialog(true);
                return;
              }
              statusMutation.mutate({ status });
            }}
            className="btn-touch rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </select>
          {vorgang.dauerauftrag_id ? (
            <span
              title="Wird beim Dauerauftrag automatisch anhand der Fälligkeit berechnet"
              className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            >
              Priorität {vorgang.prioritaet} (automatisch)
            </span>
          ) : (
            <label className="flex items-center gap-1 text-sm text-slate-500 dark:text-stone-400">
              Priorität
              <select
                value={vorgang.prioritaet}
                disabled={VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status) || prioritaetMutation.isPending}
                onChange={(e) => prioritaetMutation.mutate(Number(e.target.value))}
                className="btn-touch rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              >
                {PRIORITAET_OPTIONEN.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            onClick={() => {
              setFolgeAuftragLeistungstyp("stoerung");
              setShowFolgeAuftragDialog(true);
            }}
            className="btn-touch rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 dark:border-stone-700 dark:text-stone-300"
          >
            + Folge-Auftrag
          </button>
        </div>

        {!VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status) && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-500 dark:text-stone-400">
              {vorgang.zugewiesener_name ? (
                <>
                  Zugewiesen an: <span className="font-medium text-slate-700 dark:text-stone-200">{vorgang.zugewiesener_name}</span>
                </>
              ) : (
                "Nicht zugewiesen"
              )}
            </span>
            {currentUser?.darf_vorgaenge_selbst_uebernehmen && (
              <button
                onClick={() => {
                  if (
                    vorgang.zugewiesener_user_id &&
                    vorgang.zugewiesener_user_id !== currentUser.id &&
                    !window.confirm(
                      `Dieser Vorgang ist bereits "${vorgang.zugewiesener_name}" zugewiesen. Trotzdem an mich übernehmen?`,
                    )
                  ) {
                    return;
                  }
                  uebernehmenMutation.mutate();
                }}
                disabled={uebernehmenMutation.isPending || vorgang.zugewiesener_user_id === currentUser.id}
                className="btn-touch btn-clay flex items-center gap-1 rounded-full bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                <UserCheck size={13} strokeWidth={2} />
                {vorgang.zugewiesener_user_id === currentUser.id ? "Von mir übernommen" : "Ticket übernehmen"}
              </button>
            )}
          </div>
        )}

        {showWartetKundeDialog && (
          <div className="mt-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
            <p className="text-sm text-slate-600 dark:text-stone-300">
              Wartet auf Kunde: Nach wie vielen Tagen soll FieldVibe dich erinnern, nachzufragen?
            </p>
            <input
              type="number"
              min={1}
              placeholder={
                mandantEinstellungen
                  ? mandantEinstellungen.effektive_wiedervorlage_standard_tage.toString()
                  : "14"
              }
              value={wiedervorlageTage}
              onChange={(e) => setWiedervorlageTage(e.target.value)}
              className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <div className="flex gap-2">
              <button
                onClick={() => {
                  statusMutation.mutate({
                    status: "wartet_kunde",
                    wiedervorlageTage: wiedervorlageTage ? Number(wiedervorlageTage) : undefined,
                  });
                  setShowWartetKundeDialog(false);
                }}
                disabled={statusMutation.isPending}
                className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Übernehmen
              </button>
              <button
                onClick={() => setShowWartetKundeDialog(false)}
                className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        {showFolgeAuftragDialog && (
          <div className="mt-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
            <p className="text-sm text-slate-600 dark:text-stone-300">
              Folge-Auftrag anlegen: übernimmt Kunde/Anlage/Standort sowie offene Angebots-
              Materialpositionen dieses Vorgangs. Dieser Vorgang bleibt dabei unverändert.
            </p>
            <select
              value={folgeAuftragLeistungstyp}
              onChange={(e) => setFolgeAuftragLeistungstyp(e.target.value as Leistungstyp)}
              className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            >
              {LEISTUNGSTYPEN.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  folgeAuftragMutation.mutate(folgeAuftragLeistungstyp);
                  setShowFolgeAuftragDialog(false);
                }}
                disabled={folgeAuftragMutation.isPending}
                className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Anlegen
              </button>
              <button
                onClick={() => setShowFolgeAuftragDialog(false)}
                className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        {folgeVorgangId && (
          <div className="mt-2 flex items-center justify-between rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300">
            <span>Folge-Vorgang wurde angelegt.</span>
            <button
              onClick={() => navigate(`/vorgaenge/${folgeVorgangId}`)}
              className="btn-touch font-medium underline"
            >
              Jetzt ansehen
            </button>
          </div>
        )}

        {folgeAuftraege && folgeAuftraege.length > 0 && (
          <div className="mt-2 space-y-1">
            <span className="text-xs font-medium text-slate-500 dark:text-stone-400">Folge-Aufträge:</span>
            {folgeAuftraege.map((fa) => (
              <button
                key={fa.id}
                onClick={() => navigate(`/vorgaenge/${fa.id}`)}
                className="btn-touch block w-full rounded-md border border-slate-200 px-2 py-1.5 text-left text-sm text-slate-600 dark:border-stone-700 dark:text-stone-300"
              >
                {fa.vorgangsnummer} · {fa.titel} · {STATUS_LABEL[fa.status]}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Anchor-Nav: springt per Ankerlink zu den Abschnitten weiter unten,
          statt dass man sich alles herunterscrollen muss (siehe
          Design-Vorschlag). Reine <a href="#..."> statt scrollIntoView, das
          bleibt auch ohne JS-Handler funktionsfaehig. */}
      <nav className="scrollbar-none -mx-3 flex gap-4 overflow-x-auto border-b border-slate-200 px-3 pb-2 text-sm dark:border-stone-800">
        {ANCHOR_ABSCHNITTE.map((a) => (
          <a
            key={a.ziel}
            href={`#${a.ziel}`}
            className="shrink-0 whitespace-nowrap font-medium text-slate-500 hover:text-slate-700 dark:text-stone-400 dark:hover:text-stone-200"
          >
            {a.label}
          </a>
        ))}
      </nav>

      <div id="abschnitt-zeit" className="scroll-mt-4 rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Arbeitszeit</h2>
          <span className="text-sm font-medium text-slate-700 dark:text-stone-300">
            Bisher {gesamtStunden} Std.
          </span>
        </div>
        {timerLaeuftHier ? (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-stone-300">
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
              className="btn-touch flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <button
              onClick={() => startTimerMutation.mutate()}
              disabled={startTimerMutation.isPending || !!timerLaeuftAnderswo}
              title={timerLaeuftAnderswo ? "Es läuft bereits ein Timer für einen anderen Vorgang" : ""}
              className="btn-touch shrink-0 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Zeit starten
            </button>
          </div>
        )}

        {(zeiterfassungListe ?? []).filter((e) => e.ende_at).length > 0 && (
          <div className="mt-2 space-y-1 border-t border-slate-100 pt-2 dark:border-stone-800">
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
                    className="flex items-center justify-between text-xs text-slate-500 dark:text-stone-400"
                  >
                    <span>
                      {techniker?.name ?? "—"}
                      {e.taetigkeit && ` · ${e.taetigkeit}`}
                      {" · "}
                      {new Date(e.start_at).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin" })}
                    </span>
                    <span className="shrink-0 font-medium text-slate-600 dark:text-stone-300">
                      {formatSekundenAlsHHMM(dauerSekunden)} Std.
                    </span>
                  </div>
                );
              })}
          </div>
        )}
      </div>

      <div id="abschnitt-termine" className="scroll-mt-4 rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Termine</h2>
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
                  setTerminTechnikerId(
                    users?.find((u) => u.role === "mandant_admin" || u.role === "custom")?.id ?? "",
                  );
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
              <p key={i} className="flex items-center gap-1">
                <AlertTriangle size={13} strokeWidth={2} /> {w.meldung}
              </p>
            ))}
          </div>
        )}

        {showTerminForm && (
          <div className="mb-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
            <input
              value={terminTitel}
              onChange={(e) => setTerminTitel(e.target.value)}
              placeholder="Titel"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <select
              value={terminTechnikerId}
              onChange={(e) => setTerminTechnikerId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            >
              {(users ?? [])
                .filter((u) => u.role === "mandant_admin" || u.role === "custom")
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
                className="w-1/2 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
              <input
                type="datetime-local"
                value={terminEnde}
                onChange={(e) => setTerminEnde(e.target.value)}
                className="w-1/2 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
            </div>
            <button
              disabled={!terminTitel || !terminTechnikerId || terminMutation.isPending}
              onClick={() => terminMutation.mutate()}
              className="btn-touch w-full rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Anlegen
            </button>
          </div>
        )}

        {(termine ?? []).length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-stone-500">Keine Termine geplant.</p>
        ) : (
          <div className="space-y-1.5">
            {termine!.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60"
              >
                <div>
                  <div className="font-medium text-slate-700 dark:text-stone-300">{t.titel}</div>
                  <div className="text-xs text-slate-400 dark:text-stone-500">
                    {new Date(t.start_at).toLocaleString("de-DE", {
                      timeZone: "Europe/Berlin",
                      dateStyle: "short",
                      timeStyle: "short",
                    })}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      t.status === "abgesagt"
                        ? "bg-slate-200 text-slate-500 dark:bg-stone-700 dark:text-stone-400"
                        : "bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300"
                    }`}
                  >
                    {t.status}
                  </span>
                  {kannPapierkorbLoeschen && (
                    <button
                      onClick={() => {
                        if (window.confirm(`Termin "${t.titel}" wirklich löschen?`)) {
                          deleteTerminMutation.mutate(t.id);
                        }
                      }}
                      disabled={deleteTerminMutation.isPending}
                      className="btn-touch text-xs font-medium text-red-700 dark:text-red-400"
                    >
                      Löschen
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {vorgang && <FormularAbschnitt vorgangId={vorgang.id} vorgangStatus={vorgang.status} />}

      <div id="abschnitt-maengel" className="scroll-mt-4 rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Mängel</h2>
          <div className="flex items-center gap-3">
            {(maengel ?? []).length > 0 && (
              <button
                onClick={() => maengelProtokollMutation.mutate()}
                disabled={maengelProtokollMutation.isPending}
                className="btn-touch flex items-center gap-1 text-xs font-medium text-slate-500 dark:text-stone-400"
              >
                <FileText size={13} strokeWidth={2} /> Protokoll
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
          <div className="mb-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
            <textarea
              value={mangelBeschreibung}
              onChange={(e) => setMangelBeschreibung(e.target.value)}
              placeholder="Was ist defekt?"
              rows={2}
              className="w-full resize-none rounded-md border border-slate-300 p-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <select
              value={mangelSchweregrad}
              onChange={(e) => setMangelSchweregrad(e.target.value as MangelSchweregrad)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
              className="btn-touch w-full rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Erfassen
            </button>
          </div>
        )}

        {(maengel ?? []).length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-stone-500">Keine Mängel erfasst.</p>
        ) : (
          <div className="space-y-1.5">
            {maengel!.map((m) => (
              <div key={m.id} className="rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-slate-700 dark:text-stone-300">{m.beschreibung}</p>
                  <span className="shrink-0 rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-stone-700 dark:text-stone-300">
                    {m.schweregrad}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-xs text-slate-400 dark:text-stone-500">{m.status}</span>
                  <div className="flex gap-2">
                    {m.status === "offen" && (
                      <>
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
                      </>
                    )}
                    {kannPapierkorbLoeschen && (
                      <button
                        onClick={() => {
                          if (window.confirm("Mangel wirklich löschen?")) {
                            deleteMangelMutation.mutate(m.id);
                          }
                        }}
                        disabled={deleteMangelMutation.isPending}
                        className="btn-touch text-xs font-medium text-red-700 dark:text-red-400"
                      >
                        Löschen
                      </button>
                    )}
                  </div>
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
            className="btn-touch mt-2 w-full rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            Angebot aus offenen Mängeln erstellen
          </button>
        )}
      </div>

      <div id="abschnitt-material" className="scroll-mt-4 rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Positionen</h2>
          <div className="flex flex-wrap gap-3">
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
            <button
              onClick={() => setShowLeistungForm((v) => !v)}
              className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
            >
              {showLeistungForm ? "Abbrechen" : "+ Leistung verwenden"}
            </button>
          </div>
        </div>

        {showBedarfForm && (
          <div className="mb-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
            <SearchableSelect
              value={bedarfMaterialId}
              onChange={setBedarfMaterialId}
              placeholder="Material wählen…"
              options={[
                ...(materialListe ?? []).map((m) => ({ value: m.id, label: m.bezeichnung })),
                { value: NEU_MATERIAL, label: "+ Neues Material anlegen…" },
              ]}
            />

            {bedarfMaterialId === NEU_MATERIAL && (
              <div className="space-y-2 rounded-md border border-dashed border-slate-300 p-2 dark:border-stone-700">
                <input
                  type="text"
                  value={bedarfNeuBezeichnung}
                  onChange={(e) => setBedarfNeuBezeichnung(e.target.value)}
                  placeholder="Bezeichnung"
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={bedarfNeuEinheit}
                    onChange={(e) => setBedarfNeuEinheit(e.target.value)}
                    placeholder="Einheit"
                    className="w-20 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                  />
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={bedarfNeuEinzelpreis}
                    onChange={(e) => setBedarfNeuEinzelpreis(e.target.value)}
                    placeholder="Preis (optional)"
                    className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                  />
                </div>
                <select
                  value={bedarfNeuLieferantId}
                  onChange={(e) => setBedarfNeuLieferantId(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
                className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
              <select
                value={bedarfZweck}
                onChange={(e) => setBedarfZweck(e.target.value as MaterialBedarfZweck)}
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <button
              disabled={
                !bedarfMaterialId ||
                !bedarfMenge ||
                (bedarfMaterialId === NEU_MATERIAL && !bedarfNeuBezeichnung.trim()) ||
                materialBedarfMutation.isPending
              }
              onClick={() => materialBedarfMutation.mutate()}
              className="btn-touch w-full rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
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
                className="flex items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-sm dark:bg-stone-800/60"
              >
                <span className="text-slate-700 dark:text-stone-200">
                  {b.menge}× {b.material_bezeichnung}
                  <span className="ml-1.5 rounded-full bg-slate-200 px-1.5 py-0.5 text-xs text-slate-600 dark:bg-stone-700 dark:text-stone-300">
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

        {(materialVerwendungen ?? []).length > 0 || (lvVerwendungen ?? []).length > 0 ? (
          <div className="mb-2 space-y-1">
            <h3 className="px-1 text-xs font-medium text-slate-400 dark:text-stone-500">Verwendet</h3>
            {(materialVerwendungen ?? []).map((v) => (
              <div
                key={`material-${v.id}`}
                className="flex items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-sm dark:bg-stone-800/60"
              >
                <span className="text-slate-700 dark:text-stone-200">
                  {v.menge}× {v.material_bezeichnung}
                  <span className="ml-1.5 rounded-full bg-slate-200 px-1.5 py-0.5 text-xs text-slate-600 dark:bg-stone-700 dark:text-stone-300">
                    {v.material_einheit}
                  </span>
                </span>
              </div>
            ))}
            {(lvVerwendungen ?? []).map((v) => (
              <div
                key={`lv-${v.id}`}
                className="flex items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-sm dark:bg-stone-800/60"
              >
                <span className="text-slate-700 dark:text-stone-200">
                  {v.menge}× {v.lv_bezeichnung}
                  <span className="ml-1.5 rounded-full bg-slate-200 px-1.5 py-0.5 text-xs text-slate-600 dark:bg-stone-700 dark:text-stone-300">
                    {v.lv_einheit}
                  </span>
                </span>
              </div>
            ))}
          </div>
        ) : null}

        {kannDisponieren && (
          <button
            onClick={() => angebotAusVorgangMutation.mutate()}
            disabled={angebotAusVorgangMutation.isPending}
            className="btn-touch mb-2 w-full rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            + Angebot aus diesem Vorgang erstellen
          </button>
        )}

        {kannDisponieren && (
          <button
            onClick={() => rechnungAusVorgangMutation.mutate()}
            disabled={rechnungAusVorgangMutation.isPending}
            className="btn-touch mb-2 w-full rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            + Rechnung aus diesem Vorgang erstellen
          </button>
        )}

        {showMaterialForm && (
          <div className="space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
            <SearchableSelect
              value={materialId}
              onChange={(v) => {
                setMaterialId(v);
                // Fuer Techniker das eigene zugewiesene Fahrzeug als
                // Standard-Lagerort vorschlagen (siehe Techniker-
                // Zuweisungen-Seite) -- spart bei jedem Materialverbrauch
                // aus dem eigenen Fahrzeug den manuellen Auswahlschritt.
                setMaterialLagerId(meinFahrzeug?.id ?? "");
              }}
              placeholder="Material wählen…"
              options={(materialListe ?? []).map((m) => ({
                value: m.id,
                label: m.bezeichnung,
                sublabel: `(${m.bestand_gesamt} ${m.einheit} gesamt verfügbar)`,
              }))}
            />
            {materialId && (
              <select
                value={materialLagerId}
                onChange={(e) => setMaterialLagerId(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
                className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
              <button
                disabled={!materialId || !materialLagerId || !materialMenge || materialVerwendenMutation.isPending}
                onClick={() => materialVerwendenMutation.mutate()}
                className="btn-touch shrink-0 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
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

        {showLeistungForm && (
          <div className="space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
            {(leistungsverzeichnis ?? []).length === 0 ? (
              <p className="text-xs text-slate-500 dark:text-stone-400">
                Für diesen Kunden ist kein Leistungsverzeichnis hinterlegt.
              </p>
            ) : (
              <>
                <SearchableSelect
                  value={lvPositionId}
                  onChange={setLvPositionId}
                  placeholder="Position wählen…"
                  options={(leistungsverzeichnis ?? []).map((p) => ({
                    value: p.id,
                    label: p.bezeichnung,
                    sublabel: `${p.einzelpreis} €/${p.einheit}`,
                  }))}
                />
                <div className="flex gap-2">
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={lvMenge}
                    onChange={(e) => setLvMenge(e.target.value)}
                    placeholder="Menge"
                    className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                  />
                  <button
                    disabled={!lvPositionId || !lvMenge || leistungVerwendenMutation.isPending}
                    onClick={() => leistungVerwendenMutation.mutate()}
                    className="btn-touch shrink-0 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                  >
                    Erfassen
                  </button>
                </div>
                {leistungVerwendenMutation.isError && (
                  <p className="text-xs text-red-700 dark:text-red-400">
                    {leistungVerwendenMutation.error instanceof ApiError
                      ? leistungVerwendenMutation.error.message
                      : "Fehler beim Erfassen"}
                  </p>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {kannPartnerVerwalten && (
        <div className="rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Nachunternehmer</h2>
            {!vorgang.partner_id && (
              <button
                onClick={() => setShowPartnerForm((v) => !v)}
                className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
              >
                {showPartnerForm ? "Abbrechen" : "+ Zuweisen"}
              </button>
            )}
          </div>

          {partnerWarnung && (
            <p className="mb-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
              Für diesen Partner liegt keine gültige Freistellungsbescheinigung vor -- ohne sie greift bei
              Zahlungen für Bauleistungen grundsätzlich die 15%-Bauabzugsteuer nach § 48 EStG.
            </p>
          )}

          {vorgang.partner_id ? (
            <div className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 dark:bg-stone-800/60">
              <div>
                <button
                  onClick={() => navigate(`/partner/${vorgang.partner_id}`)}
                  className="text-sm font-medium text-slate-800 hover:underline dark:text-stone-100"
                >
                  {zugewiesenerPartner?.name ?? "…"}
                </button>
                {vorgang.partner_honorar_netto && (
                  <div className="text-xs text-slate-400 dark:text-stone-500">
                    Honorar: {vorgang.partner_honorar_netto} EUR netto
                  </div>
                )}
                {vorgang.partner_freigabe_status === "abgelehnt" && vorgang.partner_ablehnung_grund && (
                  <div className="text-xs text-red-600 dark:text-red-400">
                    Grund: {vorgang.partner_ablehnung_grund}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2">
                {vorgang.partner_freigabe_status && (
                  <span
                    className={`rounded-full px-2 py-1 text-xs font-semibold ${FREIGABE_FARBE[vorgang.partner_freigabe_status]}`}
                  >
                    {FREIGABE_LABEL[vorgang.partner_freigabe_status]}
                  </span>
                )}
                <button
                  onClick={() => partnerAufhebenMutation.mutate()}
                  disabled={partnerAufhebenMutation.isPending}
                  className="btn-touch text-xs text-red-700 dark:text-red-400"
                >
                  Aufheben
                </button>
              </div>
            </div>
          ) : (
            !showPartnerForm && (
              <p className="text-sm text-slate-400 dark:text-stone-500">Kein Nachunternehmer zugewiesen.</p>
            )
          )}

          {showPartnerForm && (
            <div className="space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
              <SearchableSelect
                value={partnerAuswahl}
                onChange={setPartnerAuswahl}
                placeholder="Partner wählen…"
                options={(partnerListe ?? []).map((p) => ({
                  value: p.id,
                  label: p.name,
                  sublabel: p.gewerk ?? undefined,
                }))}
              />
              <input
                type="number"
                step="0.01"
                min="0"
                value={partnerHonorar}
                onChange={(e) => setPartnerHonorar(e.target.value)}
                placeholder="Honorar netto (optional)"
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
              <button
                disabled={!partnerAuswahl || partnerZuweisenMutation.isPending}
                onClick={() => partnerZuweisenMutation.mutate()}
                className="btn-touch w-full rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Zuweisen
              </button>
            </div>
          )}
        </div>
      )}

      <EmailSection
        queryKey={["vorgang-emails", id]}
        listEmails={() => vorgaengeApi.emails(id!)}
        sendEmail={(body) =>
          vorgaengeApi.sendEmail(id!, {
            empfaenger: body.empfaenger,
            betreff: body.betreff ?? "",
            inhalt: body.inhalt ?? "",
          })
        }
        defaultEmpfaenger={kunde?.ansprechpartner.find((a) => a.email)?.email ?? undefined}
        showHistory={false}
        defaultOpen={location.hash === "#email"}
      />

      <div id="abschnitt-verlauf" className="scroll-mt-4 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Verlauf</h2>
        <span className="text-sm text-slate-500 dark:text-stone-400">
          {kundenansicht ? "Kundenansicht" : "Interne Ansicht"}
        </span>
        <button
          onClick={() => setKundenansicht((v) => !v)}
          className={`btn-touch rounded-full px-3 py-1 text-xs font-semibold ${
            kundenansicht
              ? "bg-blue-600 text-white"
              : "bg-slate-200 text-slate-700 dark:bg-stone-800 dark:text-stone-300"
          }`}
        >
          Umschalten
        </button>
      </div>

      <div>
        {verlaufEintraege.length === 0 && eigeneOutboxItems.length === 0 ? (
          <p className="text-center text-sm text-slate-400 dark:text-stone-500">Noch keine Einträge.</p>
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
            {verlaufEintraege.map((eintrag) =>
              eintrag.art === "email" ? (
                <EmailBubble key={`email-${eintrag.email.id}`} email={eintrag.email} />
              ) : (
                <EventBubble
                  key={`event-${eintrag.event.id}`}
                  event={eintrag.event}
                  onHighlight={(eventId) => highlightMutation.mutate(eventId)}
                />
              ),
            )}
          </>
        )}
      </div>

      {!kundenansicht && (
        <div className="sticky bottom-[var(--klebe-abstand)] space-y-2 rounded-lg bg-white p-3 shadow-md dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <div className="relative">
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Kommentar schreiben…"
              rows={2}
              className="w-full resize-none rounded-md border border-slate-300 p-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            {showMentionPicker && (
              <div className="absolute bottom-full left-0 mb-1 max-h-40 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg dark:border-stone-700 dark:bg-stone-800">
                {users?.map((u) => (
                  <button
                    key={u.id}
                    onClick={() => {
                      setComment((c) => `${c}@[${u.name}](${u.id}) `);
                      setShowMentionPicker(false);
                    }}
                    className="btn-touch block w-full px-3 py-2 text-left text-sm hover:bg-slate-50 dark:text-stone-100 dark:hover:bg-stone-700"
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
                className="btn-touch flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-base text-slate-600 dark:bg-stone-800 dark:text-stone-300"
              >
                @
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={fotoMutation.isPending}
                title="Foto anhängen"
                aria-label="Foto anhängen"
                className="btn-touch flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-600 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
              >
                <Camera size={16} strokeWidth={2} />
              </button>
              <button
                onClick={() => setShowUnterschriftPad((v) => !v)}
                title="Unterschrift erfassen"
                aria-label="Unterschrift erfassen"
                className="btn-touch flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
              >
                <PenLine size={16} strokeWidth={2} />
              </button>
              <button
                onClick={() => setKundensichtbar((v) => !v)}
                title={kundensichtbar ? "Für Kunde sichtbar – antippen zum Verbergen" : "Nur intern – antippen um für Kunde sichtbar zu machen"}
                aria-label="Für Kunde sichtbar umschalten"
                aria-pressed={kundensichtbar}
                className={`btn-touch flex h-9 w-9 items-center justify-center rounded-full ${
                  kundensichtbar
                    ? "bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-300"
                    : "bg-slate-100 text-slate-400 dark:bg-stone-800 dark:text-stone-500"
                }`}
              >
                {kundensichtbar ? <Eye size={16} strokeWidth={2} /> : <EyeOff size={16} strokeWidth={2} />}
              </button>
            </div>
            <button
              onClick={() => commentMutation.mutate()}
              disabled={!comment.trim() || commentMutation.isPending}
              className="btn-touch shrink-0 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
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
