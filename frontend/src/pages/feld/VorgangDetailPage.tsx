import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Ban, Building2, Camera, Clock, Eye, EyeOff, FileText, Mail, Package, Paperclip, PenLine, Star, UserCheck, UserPlus } from "lucide-react";
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { SymbolKachel } from "../../components/apple/SymbolKachel";
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
  projektAufgabenApi,
  standorteApi,
  termineApi,
  usersApi,
  vorgangEventsApi,
  vorgaengeApi,
  zeiterfassungApi,
} from "../../api/endpoints";
import { EmailSection } from "../../components/EmailSection";
import { EmptyState } from "../../components/EmptyState";
import { FormularAbschnitt } from "../../components/FormularAbschnitt";
import { MentionText } from "../../components/MentionText";
import { SearchableSelect } from "../../components/SearchableSelect";
import { SignaturePad } from "../../components/SignaturePad";
import { Sheet } from "../../components/apple/Sheet";
import { StatusPille } from "../../components/apple/StatusPille";
import { ZeiteintragSheet } from "../../components/ZeiteintragSheet";
import { useAuth } from "../../context/AuthContext";
import { cacheEvents, cacheKunde, getCachedEvents, getCachedKunde } from "../../offline/cache";
import {
  discardOutboxItem,
  getOutboxItems,
  queueDokument,
  queueFoto,
  queueKommentar,
  queueStatusChange,
} from "../../offline/outbox";
import { formatSekundenAlsHHMM } from "../../utils/duration";
import { istModulAktiv } from "../../utils/module";
import { BUCHUNGSSTATUS_LABEL, buchungsstatusZuToken } from "../../utils/zeiterfassung";
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
  TerminStatus,
  TerminWarnung,
  VorgangAbrechnungsart,
  VorgangEvent,
  VorgangStatus,
  Zeiterfassung,
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

const SCHWEREGRAD_LABEL: Record<MangelSchweregrad, string> = Object.fromEntries(
  SCHWEREGRAD_OPTIONEN.map((o) => [o.value, o.label]),
) as Record<MangelSchweregrad, string>;

// Hervorhebung bei kritisch/hoch statt neutralem border-sep -- sonst
// sieht ein kritischer Mangel unter Zeitdruck optisch identisch zu einem
// niedrigen aus (Status-Token st-arbeit/st-fehlt statt eigener Farben).
const SCHWEREGRAD_BADGE: Record<MangelSchweregrad, string> = {
  niedrig: "border-sep text-label",
  mittel: "border-sep text-label",
  hoch: "border-st-arbeit text-st-arbeit",
  kritisch: "border-st-fehlt text-st-fehlt",
};

const MANGEL_STATUS_LABEL: Record<MangelStatus, string> = {
  offen: "Offen",
  in_angebot: "Im Angebot",
  in_bearbeitung: "In Bearbeitung",
  behoben: "Behoben",
  abgelehnt: "Abgelehnt",
};

const TERMIN_STATUS_LABEL: Record<TerminStatus, string> = {
  geplant: "Geplant",
  bestaetigt: "Bestätigt",
  abgeschlossen: "Abgeschlossen",
  abgesagt: "Abgesagt",
};

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

// Fuer die Kurzuebersicht-Spalte im Desktop-Layout (layout="dicht") --
// Leistungstyp/Abrechnungsart stehen sonst nirgends auf dieser Seite.
const LEISTUNGSTYP_LABEL: Record<Leistungstyp, string> = {
  stoerung: "Störung",
  installation: "Installation",
  wartung: "Wartung",
  pruefung: "Prüfung",
  beratung: "Beratung",
  planung: "Planung",
};

const ABRECHNUNGSART_LABEL: Record<VorgangAbrechnungsart, string> = {
  pauschale: "Pauschale",
  aufwand: "Nach Aufwand",
  festpreis: "Festpreis",
  wartungsvertrag: "Wartungsvertrag",
  gewaehrleistung: "Gewährleistung",
};

// Spiegelt app/services/vorgang_completion_service.py:VORGANG_STATUS_GESCHLOSSEN
// -- "Ticket übernehmen" ergibt fuer bereits geschlossene Vorgaenge keinen
// Sinn mehr (das Backend lehnt es dort ohnehin mit 409 ab).
const VORGANG_STATUS_GESCHLOSSEN: VorgangStatus[] = ["abgeschlossen", "abgerechnet", "storniert"];

// Spiegelt app/api/routes/zeiterfassung.py:_VORGANG_STATUS_ZEIT_GESPERRT --
// enger als VORGANG_STATUS_GESCHLOSSEN: Zeit nachtragen/bearbeiten bleibt
// nach "abgeschlossen" bewusst moeglich, nur nach Abrechnung/Stornierung
// nicht mehr (das Backend lehnt es sonst ohnehin mit 409 ab).
const VORGANG_STATUS_ZEIT_GESPERRT: VorgangStatus[] = ["abgerechnet", "storniert"];

const PRIORITAET_OPTIONEN = [1, 2, 3, 4, 5];

const FREIGABE_LABEL: Record<PartnerFreigabeStatus, string> = {
  vorgeschlagen: "Wartet auf Rückmeldung",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

const FREIGABE_FARBE: Record<PartnerFreigabeStatus, string> = {
  vorgeschlagen: "bg-st-arbeit-bg text-st-arbeit",
  angenommen: "bg-st-erledigt-bg text-st-erledigt",
  abgelehnt: "bg-st-fehlt-bg text-st-fehlt",
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
    <span className="border border-sep px-1.5 py-0.5 text-[10px] font-medium text-label2">
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
      <div className="my-2 text-center text-xs text-label2">
        {label} · {new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}
      </div>
    );
  }

  return (
    <div className="mb-3 card-ap p-3">
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-label2">
        <div className="flex items-center gap-1.5">
          <span>{new Date(event.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}</span>
          {event.event_type === "kommentar" && <VerlaufTypTag>Kommentar</VerlaufTypTag>}
        </div>
        {event.kundensichtbar && (
          <span className="border border-tint px-2 py-0.5 text-tint">
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
            className="btn-touch mb-2 flex items-center gap-1 text-xs font-medium text-st-arbeit"
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
            className="max-h-32 border border-sep bg-white"
          />
          {typeof event.payload.unterzeichner_name === "string" && (
            <p className="mt-1 text-xs text-label2">
              Unterschrieben von: {event.payload.unterzeichner_name}
            </p>
          )}
        </div>
      )}
      {event.event_type === "dokument" && event.dokument_url && (
        <a
          href={event.dokument_url}
          target="_blank"
          rel="noreferrer"
          className="btn-touch mb-2 flex items-center gap-2 border border-sep px-3 py-2 text-sm text-label hover:bg-fill"
        >
          <Paperclip size={15} strokeWidth={2} />
          {event.dokument_dateiname ?? "Dokument"}
        </a>
      )}
      {event.body && (
        <p className="whitespace-pre-wrap break-words text-sm text-label">
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
    <div className="mb-3 card-ap p-3">
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-label2">
        <div className="flex items-center gap-1.5">
          <span>{new Date(email.created_at).toLocaleString("de-DE", { timeZone: "Europe/Berlin" })}</span>
          <VerlaufTypTag>E-Mail</VerlaufTypTag>
        </div>
        {email.status === "fehler" && (
          <span className="border border-st-fehlt px-2 py-0.5 text-st-fehlt">
            Fehler
          </span>
        )}
      </div>
      <div className="mb-1 flex items-start gap-1.5 text-sm text-label">
        <Mail size={14} strokeWidth={2} className="mt-0.5 shrink-0 text-label2" />
        <div>
          <span className="font-medium">{email.betreff || "(ohne Betreff)"}</span>
          <span className="text-label2"> · an {email.empfaenger}</span>
        </div>
      </div>
      {email.status === "fehler" && email.fehlermeldung && (
        <p className="text-xs text-st-fehlt">{email.fehlermeldung}</p>
      )}
    </div>
  );
}

function OutboxBubble({ item, onDiscard }: { item: OutboxItem; onDiscard: (clientUuid: string) => void }) {
  return (
    <div
      className={`mb-3 rounded-lg border border-dashed p-3 ${
        item.failed
          ? "border-st-fehlt bg-st-fehlt-bg"
          : "border-sepstrong"
      }`}
    >
      <div className="mb-1 flex items-center justify-between gap-1 text-xs">
        {item.failed ? (
          <span className="flex items-center gap-1 text-st-fehlt">
            <AlertTriangle size={13} strokeWidth={2} /> Vom Server abgelehnt{item.errorMessage ? `: ${item.errorMessage}` : ""}
          </span>
        ) : (
          <span className="flex items-center gap-1 text-label2">
            <Clock size={13} strokeWidth={2} />
            <span>Nicht synchronisiert</span>
          </span>
        )}
        {item.failed && (
          <button
            onClick={() => onDiscard(item.client_uuid)}
            className="btn-touch text-st-fehlt underline"
          >
            Verwerfen
          </button>
        )}
      </div>
      {item.kind === "foto" ? (
        <p className="flex items-center gap-1 text-sm text-label">
          <Camera size={14} strokeWidth={2} /> Foto wartet auf Synchronisierung
        </p>
      ) : item.kind === "dokument" ? (
        <p className="flex items-center gap-1 text-sm text-label">
          <FileText size={14} strokeWidth={2} /> {item.dokumentName ?? "Dokument"} wartet auf Synchronisierung
        </p>
      ) : item.kind === "status" ? (
        <p className="text-sm text-label">Statusänderung zu „{item.statusValue}“ wartet auf Synchronisierung</p>
      ) : (
        <p className="whitespace-pre-wrap break-words text-sm text-label">{item.body}</p>
      )}
    </div>
  );
}

function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Fuer den Termine-Wochenkalender im Desktop-Layout (layout="dicht") --
// gleiche Rechenlogik wie office/DispoBoardPage.tsx, hier aber lokal
// kopiert statt importiert: dort ist es eine Seiten-lokale Hilfsfunktion,
// kein geteiltes Modul.
const WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

function startOfWoche(d: Date): Date {
  const date = new Date(d);
  const tag = date.getDay(); // 0 = Sonntag
  const diffZuMontag = tag === 0 ? -6 : 1 - tag;
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + diffZuMontag);
  return date;
}

function addTage(d: Date, n: number): Date {
  const date = new Date(d);
  date.setDate(date.getDate() + n);
  return date;
}

function tagesSchluessel(d: Date): string {
  return d.toISOString().slice(0, 10);
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
export function VorgangDetailPage({
  id: idProp,
  layout = "kompakt",
}: { id?: string; layout?: "kompakt" | "dicht" } = {}) {
  const { id: idParam } = useParams<{ id: string }>();
  const id = idProp ?? idParam;
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  // Nur im "dicht"-Layout (Office-Inspektor-Spalte, siehe VorgaengeListe.tsx)
  // werden die Abschnitte zu echten Tabs (ein Panel sichtbar) statt der
  // mobilen Anker-Scroll-Liste (alle Abschnitte untereinander).
  const [desktopTab, setDesktopTab] = useState(ANCHOR_ABSCHNITTE[0].ziel);
  // Im "kompakt"-Layout ist die Arbeitszeit-Liste die einzige Ausnahme von
  // der Anker-Scroll-Liste: standardmaessig eingeklappt (nur ein "Zeit
  // erfassen"-Button auf der Hauptseite), erst auf Wunsch als eigener
  // Abschnitt sichtbar -- der lange Verlauf frueherer Buchungen war sonst
  // immer Teil des ersten Scrollens durch den Vorgang.
  const [zeitTabOffen, setZeitTabOffen] = useState(false);
  const istAktiverTab = (ziel: string) => {
    if (layout === "dicht") return desktopTab === ziel;
    if (ziel === "abschnitt-zeit") return zeitTabOffen;
    return true;
  };
  const tabPanelProps = (ziel: string) =>
    layout === "dicht" ? { role: "tabpanel" as const, "aria-labelledby": `tab-${ziel}` } : {};
  const { currentUser, hatRecht } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dokumentInputRef = useRef<HTMLInputElement>(null);
  const zeitAbschnittRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (zeitTabOffen && layout !== "dicht") {
      zeitAbschnittRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [zeitTabOffen, layout]);

  const [comment, setComment] = useState("");
  const [kundensichtbar, setKundensichtbar] = useState(false);
  const [kundenansicht, setKundenansicht] = useState(false);
  const [showMentionPicker, setShowMentionPicker] = useState(false);
  const [showUnterschriftPad, setShowUnterschriftPad] = useState(false);
  const [taetigkeit, setTaetigkeit] = useState("");
  // Zeit-Tab: Sheet zum Anlegen/Bearbeiten eines Eintrags (Stufe 1, siehe
  // docs/konzepte/ZEITERFASSUNG.md) -- offen, wenn zeitSheetModus gesetzt ist.
  // "neu" oeffnet leer (vorbelegt mit diesem Vorgang), "neu-fahrt" oeffnet
  // leer mit kategorie="fahrzeit" vorbelegt (Stufe 3), ein Eintrag oeffnet
  // zum Bearbeiten.
  const [zeitSheetModus, setZeitSheetModus] = useState<"neu" | "neu-fahrt" | Zeiterfassung | null>(null);
  // Kleines Taetigkeits-Sheet, das automatisch nach "Stoppen" erscheint --
  // der gerade beendete Eintrag, oder null wenn keins offen ist.
  const [nachStoppenEintrag, setNachStoppenEintrag] = useState<Zeiterfassung | null>(null);
  const [nachStoppenTaetigkeit, setNachStoppenTaetigkeit] = useState("");
  // Buchungsablauf (Stufe 2, siehe docs/konzepte/ZEITERFASSUNG.md
  // Abschnitt 6.1) -- Auswahl im Zeit-Tab, alle ausgewaehlten Eintraege
  // muessen denselben Buchungsstatus haben (siehe kannZeitAuswaehlen unten).
  const [ausgewaehlteZeitIds, setAusgewaehlteZeitIds] = useState<Set<string>>(new Set());
  const [stornierenModus, setStornierenModus] = useState(false);
  const [stornierenGrund, setStornierenGrund] = useState("");
  const [showTerminForm, setShowTerminForm] = useState(false);
  const [terminWarnungen, setTerminWarnungen] = useState<TerminWarnung[]>([]);
  const [terminTechnikerId, setTerminTechnikerId] = useState("");
  const [terminTitel, setTerminTitel] = useState("");
  const [terminStart, setTerminStart] = useState("");
  const [terminEnde, setTerminEnde] = useState("");
  const [terminWocheOffset, setTerminWocheOffset] = useState(0);
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
  // Gemeinsame Fehleranzeige fuer alle Aktionen unten, die keinen eigenen
  // Inline-Fehlertext neben einem Formular haben (z. B. Uebernehmen, Foto-
  // Upload, Timer) -- sonst verpufft ein Fehlschlag beim Techniker unsichtbar.
  const [aktionsFehler, setAktionsFehler] = useState<string | null>(null);
  const meldeAktionsFehler = (err: unknown) =>
    setAktionsFehler(
      err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.",
    );

  const kannDisponieren = hatRecht("vorgaenge", "bearbeiten");
  const kannLoeschen = hatRecht("vorgaenge", "loeschen");
  const kannPartnerVerwalten =
    istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "bearbeiten");

  const {
    data: vorgang,
    isError: vorgangIstFehler,
    error: vorgangFehler,
  } = useQuery({
    queryKey: ["vorgang", id],
    queryFn: () => vorgaengeApi.get(id!),
    enabled: !!id,
    retry: false,
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
    onError: meldeAktionsFehler,
  });
  const anlageEntfernenMutation = useMutation({
    mutationFn: (anlageId: string) => vorgaengeApi.anlageEntfernen(id!, anlageId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vorgang-anlagen", id] }),
    onError: meldeAktionsFehler,
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
    onError: (err) =>
      setZuordnungError(
        err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.",
      ),
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
    onError: (err) =>
      setAdresseError(
        err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.",
      ),
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
    onError: meldeAktionsFehler,
  });

  const { data: maengel } = useQuery({
    queryKey: ["maengel", "vorgang", id],
    queryFn: () => maengelApi.list({ vorgang_id: id! }),
    enabled: !!id,
  });

  // Kein Rechte-Gate hier: das Backend liefert bei vorgang_id-Filter
  // ohnehin nur Kanban-Aufgaben mit "projekte"-Recht plus die eigenen
  // privaten Aufgaben (siehe app/api/routes/projekte.py) -- Techniker ohne
  // Projekte-Recht sollen ihre privat verknuepften Aufgaben trotzdem sehen.
  const { data: verknuepfteAufgaben } = useQuery({
    queryKey: ["projekt-aufgaben", "vorgang", id],
    queryFn: () => projektAufgabenApi.list({ vorgang_id: id! }),
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
    onError: meldeAktionsFehler,
  });
  // `mangelMutation.isPending` allein reicht nicht als Doppel-Submit-Schutz --
  // zwei sehr schnelle Klicks koennen beide feuern, bevor React nach dem
  // ersten mutate()-Aufruf neu gerendert hat (disabled greift dann zu spaet).
  // Ref ist synchron, unabhaengig vom Render-Zyklus.
  const mangelErfassenLaeuft = useRef(false);
  const mangelErfassen = () => {
    if (!mangelBeschreibung.trim() || mangelErfassenLaeuft.current) return;
    mangelErfassenLaeuft.current = true;
    mangelMutation.mutate(undefined, { onSettled: () => (mangelErfassenLaeuft.current = false) });
  };

  const mangelStatusMutation = useMutation({
    mutationFn: ({ mangelId, status }: { mangelId: string; status: MangelStatus }) =>
      maengelApi.update(mangelId, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["maengel", "vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
    onError: meldeAktionsFehler,
  });

  const deleteMangelMutation = useMutation({
    mutationFn: (mangelId: string) => maengelApi.remove(mangelId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["maengel", "vorgang", id] }),
    onError: meldeAktionsFehler,
  });

  const deleteTerminMutation = useMutation({
    mutationFn: (terminId: string) => termineApi.remove(terminId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["termine", "vorgang", id] }),
    onError: meldeAktionsFehler,
  });

  const kannPapierkorbLoeschen = currentUser?.role === "loesch_operativ";

  const angebotAusMaengelnMutation = useMutation({
    mutationFn: (mangelIds: string[]) => angeboteApi.createFromMaengel(mangelIds),
    onSuccess: (angebot) => navigate(`/angebote/${angebot.id}`),
    onError: meldeAktionsFehler,
  });

  const angebotAusVorgangMutation = useMutation({
    mutationFn: () => angeboteApi.createFromVorgang(id!),
    onSuccess: (angebot) => navigate(`/angebote/${angebot.id}`),
    onError: meldeAktionsFehler,
  });

  const rechnungAusVorgangMutation = useMutation({
    mutationFn: () => rechnungenApi.create({ kunde_id: vorgang!.kunde_id, vorgang_id: id }),
    onSuccess: (rechnung) => navigate(`/rechnungen/${rechnung.id}`),
    onError: meldeAktionsFehler,
  });

  const maengelProtokollMutation = useMutation({
    mutationFn: () => maengelApi.protokollPdf(id!),
    onSuccess: openPdfBlob,
    onError: meldeAktionsFehler,
  });

  const highlightMutation = useMutation({
    mutationFn: (eventId: number) => highlightsApi.create(eventId),
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        setAktionsFehler("Dieses Foto ist bereits als Highlight markiert.");
      } else {
        meldeAktionsFehler(err);
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
    onError: meldeAktionsFehler,
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
    onError: meldeAktionsFehler,
  });

  const lvVerwendungEntfernenMutation = useMutation({
    mutationFn: (verwendungId: string) => leistungsverzeichnisApi.verwendungEntfernen(verwendungId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnis-verwendungen", "vorgang", id] }),
    onError: meldeAktionsFehler,
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
    onError: meldeAktionsFehler,
  });

  const partnerAufhebenMutation = useMutation({
    mutationFn: () => vorgaengeApi.partnerZuweisen(id!, null),
    onSuccess: () => {
      setPartnerWarnung(false);
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
    },
    onError: meldeAktionsFehler,
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
    onError: meldeAktionsFehler,
  });

  const bedarfEntfernenMutation = useMutation({
    mutationFn: (bedarfId: string) => materialBedarfeApi.remove(bedarfId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["material-bedarfe", "vorgang", id] }),
    onError: meldeAktionsFehler,
  });

  const deleteVorgangMutation = useMutation({
    mutationFn: () => vorgaengeApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      navigate("/feed");
    },
    onError: meldeAktionsFehler,
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
    onError: meldeAktionsFehler,
  });

  const folgeAuftragMutation = useMutation({
    mutationFn: (leistungstyp: Leistungstyp) => vorgaengeApi.folgeAuftrag(id!, leistungstyp),
    onSuccess: (result) => {
      setFolgeVorgangId(result.id);
      queryClient.invalidateQueries({ queryKey: ["vorgaenge", "folge", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
    onError: meldeAktionsFehler,
  });

  const uebernehmenMutation = useMutation({
    mutationFn: () => vorgaengeApi.uebernehmen(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
    onError: meldeAktionsFehler,
  });

  const prioritaetMutation = useMutation({
    mutationFn: (prioritaet: number) => vorgaengeApi.update(id!, { prioritaet }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vorgang", id] }),
    onError: meldeAktionsFehler,
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
    onError: meldeAktionsFehler,
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
    onError: meldeAktionsFehler,
  });

  const dokumentMutation = useMutation({
    mutationFn: async (file: File) => {
      const clientUuid = crypto.randomUUID();
      try {
        return await vorgangEventsApi.uploadDokument(
          id!,
          file,
          file.name,
          kundensichtbar,
          undefined,
          clientUuid,
        );
      } catch (err) {
        if (err instanceof ApiError) throw err;
        await queueDokument(id!, file, file.name, kundensichtbar, clientUuid);
        return null;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["outbox", id] });
    },
    onError: meldeAktionsFehler,
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
    onError: meldeAktionsFehler,
  });

  const stopTimerMutation = useMutation({
    mutationFn: (timerId: string) => zeiterfassungApi.stop(timerId),
    onSuccess: (gestoppterEintrag) => {
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung-laufend"] });
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      // Automatisches Taetigkeits-Sheet nach dem Stoppen (Stufe 1, siehe
      // docs/konzepte/ZEITERFASSUNG.md) -- nur wenn die Taetigkeit noch
      // fehlt, sonst waere die Nachfrage ueberfluessig.
      if (!gestoppterEintrag.taetigkeit) {
        setNachStoppenEintrag(gestoppterEintrag);
        setNachStoppenTaetigkeit("");
      }
    },
    onError: meldeAktionsFehler,
  });

  const nachStoppenTaetigkeitMutation = useMutation({
    mutationFn: () =>
      zeiterfassungApi.aktualisieren(nachStoppenEintrag!.id, { taetigkeit: nachStoppenTaetigkeit }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zeiterfassung", id] });
      setNachStoppenEintrag(null);
    },
    onError: meldeAktionsFehler,
  });

  function nachBuchungsaktionAufraeumen() {
    queryClient.invalidateQueries({ queryKey: ["zeiterfassung", id] });
    setAusgewaehlteZeitIds(new Set());
    setStornierenModus(false);
    setStornierenGrund("");
  }

  const vormerkenMutation = useMutation({
    mutationFn: (ids: string[]) => zeiterfassungApi.vormerken(ids),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });
  const zurueckziehenMutation = useMutation({
    mutationFn: (ids: string[]) => zeiterfassungApi.vormerkungZurueckziehen(ids),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });
  const buchenMutation = useMutation({
    mutationFn: (ids: string[]) => zeiterfassungApi.buchen(ids),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });
  const stornierenMutation = useMutation({
    mutationFn: () => zeiterfassungApi.buchungStornieren([...ausgewaehlteZeitIds], stornierenGrund),
    onSuccess: nachBuchungsaktionAufraeumen,
    onError: meldeAktionsFehler,
  });

  if (vorgangIstFehler) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        <EmptyState
          icon={Ban}
          text={
            vorgangFehler instanceof ApiError && vorgangFehler.status === 404
              ? "Vorgang nicht gefunden oder kein Zugriff."
              : "Vorgang konnte nicht geladen werden."
          }
        />
      </div>
    );
  }
  if (!vorgang) return <p className="text-center text-label2">Lädt…</p>;

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
  const gesamtKm = (zeiterfassungListe ?? []).reduce((summe, e) => summe + (Number(e.km) || 0), 0);

  const timerLaeuftHier = laufenderTimer && laufenderTimer.vorgang_id === id;
  const timerLaeuftAnderswo = laufenderTimer && laufenderTimer.vorgang_id !== id;

  // Buchungsablauf (Stufe 2, siehe docs/konzepte/ZEITERFASSUNG.md
  // Abschnitt 6.1/6.2) -- eine Zeile ist auswaehlbar, wenn sie zu einem der
  // Sammel-Endpunkte passt: vermerkt/vorgemerkt fuer eigene Eintraege oder
  // mit Buchungsrecht fuer beliebige, gebucht nur mit Buchungsrecht (fuer
  // "Buchung stornieren"). Alle ausgewaehlten Eintraege muessen denselben
  // Status haben, sonst waere unklar, welche Aktion gemeint ist.
  const darfZeitenBuchen = !!currentUser?.darf_zeiten_buchen;
  function kannZeitAuswaehlen(e: Zeiterfassung): boolean {
    const eigene = e.techniker_id === currentUser?.id;
    if (e.buchungsstatus === "vermerkt" || e.buchungsstatus === "vorgemerkt") {
      return eigene || darfZeitenBuchen;
    }
    if (e.buchungsstatus === "gebucht") {
      return darfZeitenBuchen;
    }
    return false;
  }
  const ausgewaehlteEintraege = (zeiterfassungListe ?? []).filter((e) => ausgewaehlteZeitIds.has(e.id));
  const ausgewaehlterStatus = ausgewaehlteEintraege[0]?.buchungsstatus ?? null;
  function zeitCheckboxToggeln(e: Zeiterfassung) {
    setAusgewaehlteZeitIds((bisherige) => {
      const neu = new Set(bisherige);
      if (neu.has(e.id)) {
        neu.delete(e.id);
      } else {
        // Nur Eintraege desselben Status gleichzeitig auswaehlbar.
        if (ausgewaehlterStatus && e.buchungsstatus !== ausgewaehlterStatus) neu.clear();
        neu.add(e.id);
      }
      return neu;
    });
  }
  function handleBuchen() {
    const stunden = formatSekundenAlsHHMM(
      ausgewaehlteEintraege.reduce(
        (summe, e) => summe + (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000,
        0,
      ),
    );
    if (
      window.confirm(
        `${ausgewaehlteEintraege.length} Eintrag/Einträge mit insgesamt ${stunden} Std. buchen? Gebuchte Einträge kannst du danach nicht mehr ändern.`,
      )
    ) {
      buchenMutation.mutate([...ausgewaehlteZeitIds]);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
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
            className="btn-touch text-sm font-medium text-st-fehlt disabled:opacity-50"
          >
            Vorgang löschen
          </button>
        )}
      </div>

      {aktionsFehler && (
        <div className="flex items-center justify-between gap-2 border border-st-fehlt px-3 py-2 text-sm text-st-fehlt">
          <span className="flex items-center gap-1.5">
            <AlertTriangle size={14} strokeWidth={1.5} /> {aktionsFehler}
          </span>
          <button onClick={() => setAktionsFehler(null)} className="btn-touch text-xs underline">
            Ausblenden
          </button>
        </div>
      )}

      {/* Fakten-Leiste: die wichtigsten Eckdaten auf einen Blick, bevor man
          in die Karte darunter eintaucht (siehe Design-Vorschlag "Feed und
          Detail neu gedacht"). */}
      {(anlage?.bezeichnung || standort?.bezeichnung || vorgang.faelligkeit_am || !vorgang.zugewiesener_user_id) && (
        <div className="flex flex-wrap gap-1.5">
          {(anlage?.bezeichnung || standort?.bezeichnung) && (
            <span className="flex items-center gap-1.5 border border-sep px-2.5 py-1 text-xs font-medium text-label">
              <Building2 size={13} strokeWidth={1.5} /> {anlage?.bezeichnung ?? standort?.bezeichnung}
            </span>
          )}
          {vorgang.faelligkeit_am && (
            <span
              className={`flex items-center gap-1.5 border px-2.5 py-1 text-xs font-medium ${
                vorgang.faelligkeit_am.slice(0, 10) < new Date().toISOString().slice(0, 10) &&
                !VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status)
                  ? "border-st-fehlt text-st-fehlt"
                  : "border-sep text-label"
              }`}
            >
              <Clock size={13} strokeWidth={1.5} />
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
            <span className="flex items-center gap-1.5 border border-dashed border-st-arbeit px-2.5 py-1 text-xs font-medium text-st-arbeit">
              <UserPlus size={13} strokeWidth={1.5} /> Nicht zugewiesen
            </span>
          )}
        </div>
      )}

      {/* Kompakt (Feld-App, Office-SchmaleSpalte): Anker-Nav, springt zu den
       * Abschnitten weiter unten -- reine <a href="#..."> statt
       * scrollIntoView, bleibt so auch ohne JS-Handler funktionsfaehig.
       * Dicht (Office-Inspektor-Spalte): echte Tabs, ein Panel sichtbar,
       * role="tablist"/"tab" fuer Screenreader. */}
      {layout === "dicht" ? (
        <div
          role="tablist"
          aria-label="Vorgangs-Abschnitte"
          className="-mx-3 mb-3 flex gap-1 overflow-x-auto border-b border-sep px-3 pb-2 text-sm"
        >
          {ANCHOR_ABSCHNITTE.map((a) => (
            <button
              key={a.ziel}
              type="button"
              role="tab"
              id={`tab-${a.ziel}`}
              aria-selected={desktopTab === a.ziel}
              aria-controls={a.ziel}
              onClick={() => setDesktopTab(a.ziel)}
              className={`shrink-0 rounded-[7px] px-2.5 py-1 font-medium whitespace-nowrap ${
                desktopTab === a.ziel ? "bg-fill text-label" : "text-label2 hover:text-label"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
      ) : (
        <nav aria-label="Vorgangs-Abschnitte" className="scrollbar-none -mx-3 flex gap-4 overflow-x-auto border-b border-sep px-3 pb-2 text-sm">
          {ANCHOR_ABSCHNITTE.map((a) =>
            a.ziel === "abschnitt-zeit" ? (
              <button
                key={a.ziel}
                type="button"
                onClick={() => setZeitTabOffen(true)}
                className={`shrink-0 whitespace-nowrap font-medium ${
                  zeitTabOffen ? "text-label" : "text-label2 hover:text-label"
                }`}
              >
                {a.label}
              </button>
            ) : (
              <a
                key={a.ziel}
                href={`#${a.ziel}`}
                className="shrink-0 whitespace-nowrap font-medium text-label2 hover:text-label"
              >
                {a.label}
              </a>
            ),
          )}
        </nav>
      )}

      <div
        id="abschnitt-uebersicht"
        className={`scroll-mt-4 grid gap-4 ${layout === "dicht" ? "lg:grid-cols-[1fr_280px] lg:items-start" : ""} ${istAktiverTab("abschnitt-uebersicht") ? "" : "hidden"}`}
        {...tabPanelProps("abschnitt-uebersicht")}
      >
      <div className="card-ap p-4">
        <div className="text-xs text-label2">{vorgang.vorgangsnummer}</div>
        <h1 className="font-heading text-lg font-semibold uppercase tracking-wide text-label">{vorgang.titel}</h1>
        {parentVorgang && (
          <button
            onClick={() => navigate(`/vorgaenge/${parentVorgang.id}`)}
            className="mt-0.5 block text-xs text-label2 underline-offset-2 hover:underline"
          >
            Entstanden aus Vorgang {parentVorgang.vorgangsnummer}
          </button>
        )}

        <div className="mt-1 flex items-center justify-between">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
            {kunde && (
              <button
                onClick={() => navigate(`/kunden/${kunde.id}`)}
                className="text-tint underline-offset-2 hover:underline"
              >
                {kunde.name}
              </button>
            )}
            {anlage && (
              <>
                <span className="text-label2">·</span>
                <button
                  onClick={() => navigate(`/anlagen/${anlage.id}`)}
                  className="text-tint underline-offset-2 hover:underline"
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
              className="btn-touch text-xs font-medium text-tint"
            >
              Bearbeiten
            </button>
          )}
        </div>

        {editingZuordnung && (
          <div className="mt-2 space-y-2 border border-sepstrong p-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-label2">Kunde</label>
              <select
                value={editKundeId}
                onChange={(e) => {
                  setEditKundeId(e.target.value);
                  setEditAnlageId("");
                }}
                className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              >
                {alleKunden?.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.name} ({k.kundennummer})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-label2">
                Anlage (optional)
              </label>
              <select
                value={editAnlageId}
                onChange={(e) => setEditAnlageId(e.target.value)}
                className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              >
                <option value="">Keine Anlage</option>
                {anlagenFuerEditKunde?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.bezeichnung}
                  </option>
                ))}
              </select>
            </div>
            {zuordnungError && <p className="text-xs text-st-fehlt">{zuordnungError}</p>}
            <div className="flex gap-2">
              <button
                onClick={() => zuordnungMutation.mutate()}
                disabled={!editKundeId || zuordnungMutation.isPending}
                className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm"
              >
                Speichern
              </button>
              <button
                onClick={() => {
                  setEditingZuordnung(false);
                  setZuordnungError(null);
                }}
                className="btn-touch flex-1 btn-ap py-1.5 text-sm"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        <div className="mt-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-label2">Adresse</span>
            {kannDisponieren && !editingAdresse && (
              <button
                onClick={() => {
                  setAdresseForm(leereAdresse(vorgang.adresse));
                  setAdresseError(null);
                  setEditingAdresse(true);
                }}
                className="btn-touch text-xs font-medium text-tint"
              >
                Bearbeiten
              </button>
            )}
          </div>
          {!editingAdresse &&
            (adresseAlsZeile(anzeigeAdresse) ? (
              <>
                <p className="mt-1 text-sm text-label">
                  {adresseAlsZeile(anzeigeAdresse)}
                  {!vorgang.adresse && (standort || anlage) && (
                    <span className="ml-1 text-xs text-label2">
                      ({standort ? "Standort" : "Anlage"})
                    </span>
                  )}
                </p>
                {kartenKoordinaten ? (
                  <Suspense
                    fallback={<div className="mt-2 h-40 w-full animate-pulse rounded-lg bg-fill" />}
                  >
                    <MapboxMap
                      lng={kartenKoordinaten.lng}
                      lat={kartenKoordinaten.lat}
                      className="mt-2 h-40 w-full rounded-lg"
                    />
                  </Suspense>
                ) : (
                  <div className="mt-2 flex h-40 w-full items-center justify-center border border-dashed border-sepstrong text-center text-xs text-label2">
                    Keine Kartenposition verfügbar
                  </div>
                )}
              </>
            ) : (
              <p className="mt-1 text-sm text-label2">Keine Adresse hinterlegt.</p>
            ))}
          {editingAdresse && (
            <div className="mt-2 space-y-2 border border-sepstrong p-3">
              <input
                value={adresseForm.strasse}
                onChange={(e) => setAdresseForm({ ...adresseForm, strasse: e.target.value })}
                placeholder="Straße + Hausnr."
                className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={adresseForm.plz}
                  onChange={(e) => setAdresseForm({ ...adresseForm, plz: e.target.value })}
                  placeholder="PLZ"
                  className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                />
                <input
                  value={adresseForm.ort}
                  onChange={(e) => setAdresseForm({ ...adresseForm, ort: e.target.value })}
                  placeholder="Ort"
                  className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                />
              </div>
              {adresseError && <p className="text-xs text-st-fehlt">{adresseError}</p>}
              <div className="flex gap-2">
                <button
                  onClick={() => adresseMutation.mutate()}
                  disabled={adresseMutation.isPending}
                  className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm"
                >
                  Speichern
                </button>
                <button
                  onClick={() => {
                    setEditingAdresse(false);
                    setAdresseError(null);
                  }}
                  className="btn-touch flex-1 btn-ap py-1.5 text-sm"
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
              <span className="text-xs font-medium text-label2">Weitere Anlagen</span>
              {kannDisponieren && !showAnlageHinzufuegen && (
                <button
                  onClick={() => setShowAnlageHinzufuegen(true)}
                  className="btn-touch text-xs font-medium text-tint"
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
                    className="flex items-center gap-1 border border-sep px-2 py-1 text-xs text-label"
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
                        className="relative text-label2 before:absolute before:-inset-2.5 hover:text-st-fehlt"
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
                  className="btn-touch flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
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
                  className="btn-touch btn-ap-primary px-3 py-1.5 text-sm"
                >
                  OK
                </button>
                <button
                  onClick={() => {
                    setShowAnlageHinzufuegen(false);
                    setNeueAnlageId("");
                  }}
                  className="btn-touch btn-ap px-3 py-1.5 text-sm"
                >
                  Abbrechen
                </button>
              </div>
            )}
          </div>
        )}

        {vorgang.beschreibung && (
          <p className="mt-2 text-sm text-label">{vorgang.beschreibung}</p>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label htmlFor="vorgang-status-select" className="text-sm text-label2">
            Status:
          </label>
          <select
            id="vorgang-status-select"
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
            className="btn-touch border border-sep bg-transparent px-2 py-1 text-sm text-label"
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
              className="border border-sep px-2 py-1 text-xs text-label"
            >
              Priorität {vorgang.prioritaet} (automatisch)
            </span>
          ) : (
            <label className="flex items-center gap-1 text-sm text-label2">
              Priorität
              <select
                value={vorgang.prioritaet}
                disabled={VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status) || prioritaetMutation.isPending}
                onChange={(e) => prioritaetMutation.mutate(Number(e.target.value))}
                className="btn-touch border border-sep bg-transparent px-2 py-1 text-sm text-label"
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
            className="btn-touch border border-sepstrong px-3 py-1 text-xs font-medium text-label hover:bg-fill"
          >
            + Folge-Vorgang
          </button>
        </div>

        {!VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status) && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-label2">
              {vorgang.zugewiesener_name ? (
                <>
                  Zugewiesen an: <span className="font-medium text-label">{vorgang.zugewiesener_name}</span>
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
                className="btn-touch btn-ap-primary flex items-center gap-1 px-3 py-1.5 text-xs disabled:cursor-not-allowed"
              >
                <UserCheck size={13} strokeWidth={2} />
                {vorgang.zugewiesener_user_id === currentUser.id ? "Von mir übernommen" : "Ticket übernehmen"}
              </button>
            )}
          </div>
        )}

        {showWartetKundeDialog && (
          <div className="mt-2 space-y-2 border border-sepstrong p-2">
            <p className="text-sm text-label">
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
              className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
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
                className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm"
              >
                Übernehmen
              </button>
              <button
                onClick={() => setShowWartetKundeDialog(false)}
                className="btn-touch flex-1 btn-ap py-1.5 text-sm"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        {showFolgeAuftragDialog && (
          <div className="mt-2 space-y-2 border border-sepstrong p-2">
            <p className="text-sm text-label">
              Folge-Vorgang anlegen: übernimmt Kunde/Anlage/Standort sowie offene Angebots-
              Materialpositionen dieses Vorgangs. Dieser Vorgang bleibt dabei unverändert.
            </p>
            <select
              value={folgeAuftragLeistungstyp}
              onChange={(e) => setFolgeAuftragLeistungstyp(e.target.value as Leistungstyp)}
              className="btn-touch w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
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
                className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm"
              >
                Anlegen
              </button>
              <button
                onClick={() => setShowFolgeAuftragDialog(false)}
                className="btn-touch flex-1 btn-ap py-1.5 text-sm"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        {folgeVorgangId && (
          <div className="mt-2 flex items-center justify-between rounded-md bg-st-erledigt-bg px-3 py-2 text-sm text-st-erledigt">
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
            <span className="text-xs font-medium text-label2">Folge-Vorgänge:</span>
            {folgeAuftraege.map((fa) => (
              <button
                key={fa.id}
                onClick={() => navigate(`/vorgaenge/${fa.id}`)}
                className="btn-touch block w-full border border-sep px-2 py-1.5 text-left text-sm text-label hover:bg-fill"
              >
                {fa.vorgangsnummer} · {fa.titel} · {STATUS_LABEL[fa.status]}
              </button>
            ))}
          </div>
        )}

        {layout !== "dicht" && !zeitTabOffen && (
          <button
            type="button"
            onClick={() => setZeitTabOffen(true)}
            className="btn-touch btn-ap-primary mt-3 w-full"
          >
            Zeit erfassen{gesamtStunden !== "0:00" && ` · bisher ${gesamtStunden} Std.`}
          </button>
        )}
      </div>

      {layout === "dicht" && (
        <div className="card-ap h-fit space-y-3 p-4">
          <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Kurzübersicht</h2>
          <dl className="space-y-2.5 text-sm">
            {[
              ["Status", STATUS_LABEL[vorgang.status]],
              ["Priorität", String(vorgang.prioritaet)],
              ["Zugewiesen an", vorgang.zugewiesener_name ?? "Nicht zugewiesen"],
              [
                "Fälligkeit",
                vorgang.faelligkeit_am ? new Date(vorgang.faelligkeit_am).toLocaleDateString("de-DE") : "—",
              ],
              ["Leistungstyp", LEISTUNGSTYP_LABEL[vorgang.leistungstyp]],
              ["Abrechnungsart", ABRECHNUNGSART_LABEL[vorgang.abrechnungsart]],
              ["Erstellt am", new Date(vorgang.created_at).toLocaleDateString("de-DE")],
            ].map(([label, wert]) => (
              <div key={label} className="flex items-baseline justify-between gap-2">
                <dt className="text-label2">{label}</dt>
                <dd className="text-right font-medium text-label">{wert}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      </div>

      <div
        id="abschnitt-zeit"
        ref={zeitAbschnittRef}
        className={`scroll-mt-4 card-ap p-3 ${istAktiverTab("abschnitt-zeit") ? "" : "hidden"}`}
        {...tabPanelProps("abschnitt-zeit")}
      >
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Arbeitszeit</h2>
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-label">
              Bisher {gesamtStunden} Std.{gesamtKm > 0 && ` · ${gesamtKm.toFixed(1)} km`}
            </span>
            {!VORGANG_STATUS_ZEIT_GESPERRT.includes(vorgang.status) && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setZeitSheetModus("neu-fahrt")}
                  className="btn-touch text-xs font-medium text-tint"
                >
                  + Fahrt erfassen
                </button>
                <button
                  onClick={() => setZeitSheetModus("neu")}
                  className="btn-touch text-xs font-medium text-tint"
                >
                  + Zeit nachtragen
                </button>
              </div>
            )}
          </div>
        </div>
        {timerLaeuftHier ? (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm font-medium text-label">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-st-fehlt-dot" />
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
              className="btn-touch rounded-md bg-st-fehlt-dot px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
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
              className="btn-touch flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <button
              onClick={() => startTimerMutation.mutate()}
              disabled={startTimerMutation.isPending || !!timerLaeuftAnderswo}
              title={timerLaeuftAnderswo ? "Es läuft bereits ein Timer für einen anderen Vorgang" : ""}
              className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-sm"
            >
              Zeit starten
            </button>
          </div>
        )}

        {(zeiterfassungListe ?? []).filter((e) => e.ende_at).length > 0 &&
          (layout === "dicht" ? (
            <div className="mt-2 overflow-x-auto border-t border-sep pt-2">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="text-left text-label2">
                    <th className="w-6 px-2 py-1" />
                    <th className="px-2 py-1 font-medium">Techniker</th>
                    <th className="px-2 py-1 font-medium">Tätigkeit</th>
                    <th className="px-2 py-1 font-medium">Datum</th>
                    <th className="px-2 py-1 font-medium">Von–Bis</th>
                    <th className="px-2 py-1 text-right font-medium">Dauer</th>
                    <th className="px-2 py-1 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {[...(zeiterfassungListe ?? [])]
                    .filter((e) => e.ende_at)
                    .sort((a, b) => new Date(b.start_at).getTime() - new Date(a.start_at).getTime())
                    .map((e) => {
                      const dauerSekunden =
                        (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000;
                      const techniker = users?.find((u) => u.id === e.techniker_id);
                      return (
                        <tr key={e.id} className="border-t border-sep hover:bg-fill">
                          <td className="px-2 py-1.5">
                            {kannZeitAuswaehlen(e) && (
                              <input
                                type="checkbox"
                                checked={ausgewaehlteZeitIds.has(e.id)}
                                onChange={() => zeitCheckboxToggeln(e)}
                                onClick={(ev) => ev.stopPropagation()}
                                className="h-4 w-4"
                              />
                            )}
                          </td>
                          <td className="cursor-pointer px-2 py-1.5 text-label" onClick={() => setZeitSheetModus(e)}>
                            {techniker?.name ?? "—"}
                          </td>
                          <td className="cursor-pointer px-2 py-1.5 text-label2" onClick={() => setZeitSheetModus(e)}>
                            {e.taetigkeit || (
                              <span className="flex items-center gap-1 text-st-arbeit">
                                <AlertTriangle size={12} strokeWidth={2} /> Tätigkeit fehlt
                              </span>
                            )}
                          </td>
                          <td className="cursor-pointer px-2 py-1.5 tabular-nums text-label2" onClick={() => setZeitSheetModus(e)}>
                            {new Date(e.start_at).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin" })}
                          </td>
                          <td className="cursor-pointer px-2 py-1.5 tabular-nums text-label2" onClick={() => setZeitSheetModus(e)}>
                            {new Date(e.start_at).toLocaleTimeString("de-DE", {
                              timeZone: "Europe/Berlin",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                            –
                            {new Date(e.ende_at!).toLocaleTimeString("de-DE", {
                              timeZone: "Europe/Berlin",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </td>
                          <td
                            className="cursor-pointer px-2 py-1.5 text-right font-medium tabular-nums text-label"
                            onClick={() => setZeitSheetModus(e)}
                          >
                            {formatSekundenAlsHHMM(dauerSekunden)} Std.
                            {e.km && <span className="ml-1 font-normal text-label2">· {e.km} km</span>}
                          </td>
                          <td className="cursor-pointer px-2 py-1.5" onClick={() => setZeitSheetModus(e)}>
                            <StatusPille
                              status={buchungsstatusZuToken(e.buchungsstatus)}
                              label={BUCHUNGSSTATUS_LABEL[e.buchungsstatus]}
                            />
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="mt-2 space-y-1 border-t border-sep pt-2">
              {[...(zeiterfassungListe ?? [])]
                .filter((e) => e.ende_at)
                .sort((a, b) => new Date(b.start_at).getTime() - new Date(a.start_at).getTime())
                .map((e) => {
                  const dauerSekunden =
                    (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000;
                  const techniker = users?.find((u) => u.id === e.techniker_id);
                  return (
                    <div key={e.id} className="flex items-center gap-2">
                      {kannZeitAuswaehlen(e) && (
                        <input
                          type="checkbox"
                          checked={ausgewaehlteZeitIds.has(e.id)}
                          onChange={() => zeitCheckboxToggeln(e)}
                          className="btn-touch h-4 w-4 shrink-0"
                        />
                      )}
                      <button
                        onClick={() => setZeitSheetModus(e)}
                        className="btn-touch flex min-w-0 flex-1 items-center justify-between gap-2 text-left text-xs text-label2 hover:bg-fill"
                      >
                        <span className="min-w-0">
                          {techniker?.name ?? "—"}
                          {" · "}
                          {e.taetigkeit || (
                            <span className="inline-flex items-center gap-1 text-st-arbeit">
                              <AlertTriangle size={12} strokeWidth={2} /> Tätigkeit fehlt
                            </span>
                          )}
                          {" · "}
                          {new Date(e.start_at).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin" })}
                          {" · "}
                          {new Date(e.start_at).toLocaleTimeString("de-DE", {
                            timeZone: "Europe/Berlin",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                          –
                          {new Date(e.ende_at!).toLocaleTimeString("de-DE", {
                            timeZone: "Europe/Berlin",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                        <span className="flex shrink-0 items-center gap-2">
                          <span className="font-medium text-label">
                            {formatSekundenAlsHHMM(dauerSekunden)} Std.
                            {e.km && <span className="ml-1 font-normal text-label2">· {e.km} km</span>}
                          </span>
                          <StatusPille
                            status={buchungsstatusZuToken(e.buchungsstatus)}
                            label={BUCHUNGSSTATUS_LABEL[e.buchungsstatus]}
                          />
                        </span>
                      </button>
                    </div>
                  );
                })}
            </div>
          ))}

        {ausgewaehlteZeitIds.size > 0 && (
          <div className="mt-2 border-t border-sep pt-2">
            {stornierenModus ? (
              <div className="flex items-center gap-2">
                <input
                  autoFocus
                  value={stornierenGrund}
                  onChange={(e) => setStornierenGrund(e.target.value)}
                  placeholder="Grund für die Stornierung"
                  className="field-ap flex-1 text-sm"
                />
                <button
                  onClick={() => stornierenMutation.mutate()}
                  disabled={!stornierenGrund.trim() || stornierenMutation.isPending}
                  className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-xs disabled:opacity-40"
                >
                  Bestätigen
                </button>
                <button
                  onClick={() => setStornierenModus(false)}
                  className="btn-touch shrink-0 px-2 py-1.5 text-xs text-label2"
                >
                  Abbrechen
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-label2">{ausgewaehlteZeitIds.size} ausgewählt</span>
                {ausgewaehlterStatus === "vermerkt" && (
                  <button
                    onClick={() => vormerkenMutation.mutate([...ausgewaehlteZeitIds])}
                    disabled={vormerkenMutation.isPending}
                    className="btn-touch border border-sepstrong px-3 py-1.5 text-xs font-medium text-label hover:bg-fill"
                  >
                    Zur Buchung vormerken
                  </button>
                )}
                {(ausgewaehlterStatus === "vermerkt" || ausgewaehlterStatus === "vorgemerkt") &&
                  darfZeitenBuchen && (
                    <button
                      onClick={handleBuchen}
                      disabled={buchenMutation.isPending}
                      className="btn-touch btn-ap-primary px-3 py-1.5 text-xs"
                    >
                      Buchen
                    </button>
                  )}
                {ausgewaehlterStatus === "vorgemerkt" && (
                  <button
                    onClick={() => zurueckziehenMutation.mutate([...ausgewaehlteZeitIds])}
                    disabled={zurueckziehenMutation.isPending}
                    className="btn-touch border border-sepstrong px-3 py-1.5 text-xs font-medium text-label hover:bg-fill"
                  >
                    Zurückziehen
                  </button>
                )}
                {ausgewaehlterStatus === "gebucht" && darfZeitenBuchen && (
                  <button
                    onClick={() => setStornierenModus(true)}
                    className="btn-touch border border-sepstrong px-3 py-1.5 text-xs font-medium text-label hover:bg-fill"
                  >
                    Buchung stornieren
                  </button>
                )}
                <button
                  onClick={() => setAusgewaehlteZeitIds(new Set())}
                  className="btn-touch px-2 py-1.5 text-xs text-label2"
                >
                  Auswahl aufheben
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div
        id="abschnitt-termine"
        className={`scroll-mt-4 card-ap p-3 ${istAktiverTab("abschnitt-termine") ? "" : "hidden"}`}
        {...tabPanelProps("abschnitt-termine")}
      >
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Termine</h2>
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
              className="btn-touch text-xs font-medium text-tint"
            >
              {showTerminForm ? "Abbrechen" : "+ Termin planen"}
            </button>
          )}
        </div>

        {terminWarnungen.length > 0 && (
          <div className="mb-2 rounded-md border border-st-arbeit bg-st-arbeit-bg p-2 text-xs text-st-arbeit">
            {terminWarnungen.map((w, i) => (
              <p key={i} className="flex items-center gap-1">
                <AlertTriangle size={13} strokeWidth={2} /> {w.meldung}
              </p>
            ))}
          </div>
        )}

        {showTerminForm && (
          <div className="mb-2 space-y-2 border border-sepstrong p-2">
            <input
              value={terminTitel}
              onChange={(e) => setTerminTitel(e.target.value)}
              placeholder="Titel"
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <select
              value={terminTechnikerId}
              onChange={(e) => setTerminTechnikerId(e.target.value)}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
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
                className="w-1/2 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <input
                type="datetime-local"
                value={terminEnde}
                onChange={(e) => setTerminEnde(e.target.value)}
                className="w-1/2 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
            <button
              disabled={!terminTitel || !terminTechnikerId || terminMutation.isPending}
              onClick={() => terminMutation.mutate()}
              className="btn-touch btn-ap-primary w-full px-3 py-1.5 text-sm"
            >
              Anlegen
            </button>
          </div>
        )}

        {layout === "dicht"
          ? (() => {
              const heute = new Date();
              const sortiert = [...(termine ?? [])].sort(
                (a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime(),
              );
              const naechster =
                sortiert.find((t) => new Date(t.start_at).getTime() >= heute.getTime()) ??
                sortiert[sortiert.length - 1];
              const referenz = naechster ? new Date(naechster.start_at) : heute;
              const wocheStart = addTage(startOfWoche(referenz), terminWocheOffset * 7);
              const wocheTage = Array.from({ length: 7 }, (_, i) => addTage(wocheStart, i));
              const wocheEnde = addTage(wocheStart, 6);
              const perTag = new Map<string, typeof sortiert>();
              for (const t of sortiert) {
                const key = tagesSchluessel(new Date(t.start_at));
                perTag.set(key, [...(perTag.get(key) ?? []), t]);
              }
              return (
                <div>
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => setTerminWocheOffset((o) => o - 1)}
                        className="btn-touch border border-sep px-2 py-1 text-xs text-label hover:bg-fill"
                      >
                        ← Vorherige Woche
                      </button>
                      <button
                        type="button"
                        onClick={() => setTerminWocheOffset(0)}
                        disabled={terminWocheOffset === 0}
                        className="btn-touch border border-sep px-2 py-1 text-xs text-label hover:bg-fill disabled:opacity-50"
                      >
                        Diese Woche
                      </button>
                      <button
                        type="button"
                        onClick={() => setTerminWocheOffset((o) => o + 1)}
                        className="btn-touch border border-sep px-2 py-1 text-xs text-label hover:bg-fill"
                      >
                        Nächste Woche →
                      </button>
                    </div>
                    <span className="text-xs text-label2">
                      {wocheStart.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}–
                      {wocheEnde.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" })}
                    </span>
                  </div>
                  <div className="grid grid-cols-7 gap-px overflow-hidden border border-sep bg-sep">
                    {wocheTage.map((tag, i) => {
                      const heuteFlag = tagesSchluessel(tag) === tagesSchluessel(heute);
                      const eintraege = perTag.get(tagesSchluessel(tag)) ?? [];
                      return (
                        <div key={i} className="min-h-[110px] bg-card p-1.5">
                          <div className={`mb-1 text-[11px] font-medium ${heuteFlag ? "text-tint" : "text-label2"}`}>
                            {WOCHENTAGE[i]} {tag.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}
                          </div>
                          <div className="space-y-1">
                            {eintraege.map((t) => (
                              <div
                                key={t.id}
                                title={t.titel}
                                className={`rounded-[5px] border p-1 text-[11px] ${
                                  t.status === "abgesagt"
                                    ? "border-sep text-label2 line-through"
                                    : "border-tint text-tint"
                                }`}
                              >
                                <div className="font-semibold">
                                  {new Date(t.start_at).toLocaleTimeString("de-DE", {
                                    timeZone: "Europe/Berlin",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })}
                                </div>
                                <div className="truncate">{t.titel}</div>
                                {kannPapierkorbLoeschen && (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      if (window.confirm(`Termin "${t.titel}" wirklich löschen?`)) {
                                        deleteTerminMutation.mutate(t.id);
                                      }
                                    }}
                                    disabled={deleteTerminMutation.isPending}
                                    className="mt-0.5 text-[10px] font-medium text-st-fehlt"
                                  >
                                    Löschen
                                  </button>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()
          : (termine ?? []).length === 0 ? (
              <p className="text-sm text-label2">Keine Termine geplant.</p>
            ) : (
              <div className="space-y-1.5">
                {termine!.map((t) => (
                  <div
                    key={t.id}
                    className="flex items-center justify-between border border-sepstrong p-2 text-sm"
                  >
                    <div>
                      <div className="font-medium text-label">{t.titel}</div>
                      <div className="text-xs text-label2">
                        {new Date(t.start_at).toLocaleString("de-DE", {
                          timeZone: "Europe/Berlin",
                          dateStyle: "short",
                          timeStyle: "short",
                        })}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`border px-2 py-0.5 text-xs font-medium ${
                          t.status === "abgesagt"
                            ? "border-sep text-label2"
                            : "border-tint text-tint"
                        }`}
                      >
                        {TERMIN_STATUS_LABEL[t.status]}
                      </span>
                      {kannPapierkorbLoeschen && (
                        <button
                          onClick={() => {
                            if (window.confirm(`Termin "${t.titel}" wirklich löschen?`)) {
                              deleteTerminMutation.mutate(t.id);
                            }
                          }}
                          disabled={deleteTerminMutation.isPending}
                          className="btn-touch text-xs font-medium text-st-fehlt"
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

      {vorgang && (
        <div className={istAktiverTab("abschnitt-uebersicht") ? "" : "hidden"} {...tabPanelProps("abschnitt-uebersicht")}>
          <FormularAbschnitt vorgangId={vorgang.id} vorgangStatus={vorgang.status} />
        </div>
      )}

      <div
        id="abschnitt-maengel"
        className={`scroll-mt-4 card-ap p-3 ${istAktiverTab("abschnitt-maengel") ? "" : "hidden"}`}
        {...tabPanelProps("abschnitt-maengel")}
      >
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Mängel</h2>
          <div className="flex items-center gap-3">
            {(maengel ?? []).length > 0 && (
              <button
                onClick={() => maengelProtokollMutation.mutate()}
                disabled={maengelProtokollMutation.isPending}
                className="btn-touch flex items-center gap-1 text-xs font-medium text-label2"
              >
                <FileText size={13} strokeWidth={2} /> Protokoll
              </button>
            )}
            <button
              onClick={() => setShowMangelForm((v) => !v)}
              className="btn-touch text-xs font-medium text-tint"
            >
              {showMangelForm ? "Abbrechen" : "+ Mangel melden"}
            </button>
          </div>
        </div>

        {showMangelForm && (
          <div className="mb-2 space-y-2 border border-sepstrong p-2">
            <textarea
              value={mangelBeschreibung}
              onChange={(e) => setMangelBeschreibung(e.target.value)}
              placeholder="Was ist defekt?"
              rows={2}
              className="w-full resize-none border border-sep bg-transparent p-2 text-sm text-label"
            />
            <select
              value={mangelSchweregrad}
              onChange={(e) => setMangelSchweregrad(e.target.value as MangelSchweregrad)}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            >
              {SCHWEREGRAD_OPTIONEN.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            <button
              disabled={!mangelBeschreibung.trim() || mangelMutation.isPending}
              onClick={mangelErfassen}
              className="btn-touch btn-ap-primary w-full px-3 py-1.5 text-sm"
            >
              Erfassen
            </button>
          </div>
        )}

        {(maengel ?? []).length === 0 ? (
          <p className="text-sm text-label2">Keine Mängel erfasst.</p>
        ) : (
          <div className="space-y-1.5">
            {maengel!.map((m) => (
              <div key={m.id} className="border border-sepstrong p-2 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-label">{m.beschreibung}</p>
                  <span className={`shrink-0 border px-2 py-0.5 text-xs font-medium ${SCHWEREGRAD_BADGE[m.schweregrad]}`}>
                    {SCHWEREGRAD_LABEL[m.schweregrad]}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-xs text-label2">{MANGEL_STATUS_LABEL[m.status]}</span>
                  <div className="flex gap-2">
                    {m.status === "offen" && (
                      <>
                        <button
                          onClick={() => mangelStatusMutation.mutate({ mangelId: m.id, status: "behoben" })}
                          className="btn-touch text-xs font-medium text-st-erledigt"
                        >
                          Behoben
                        </button>
                        <button
                          onClick={() => mangelStatusMutation.mutate({ mangelId: m.id, status: "abgelehnt" })}
                          className="btn-touch text-xs font-medium text-st-fehlt"
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
                        className="btn-touch text-xs font-medium text-st-fehlt"
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
            className="btn-touch mt-2 btn-ap w-full px-3 py-1.5 text-sm"
          >
            Angebot aus offenen Mängeln erstellen
          </button>
        )}
      </div>

      {(verknuepfteAufgaben ?? []).length > 0 && (
        <div className="scroll-mt-4 card-ap p-3">
          <h2 className="font-heading mb-2 text-sm font-semibold uppercase tracking-wide text-label">Verknüpfte Aufgaben</h2>
          {/* Rein anzeigend: Bearbeitung nur ueber das Projekte-Kanban in der
              Office-Oberflaeche, kein Statusabgleich zurueck zum Vorgang. */}
          <div className="space-y-1.5">
            {verknuepfteAufgaben!.map((a) => (
              <div key={a.id} className="border border-sepstrong p-2 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-label">{a.titel}</p>
                  <span className="shrink-0 border border-sep px-2 py-0.5 text-xs font-medium text-label">
                    {a.prioritaet}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between text-xs text-label2">
                  <span>
                    {a.checkliste.length > 0
                      ? `${a.checkliste.filter((p) => p.erledigt).length}/${a.checkliste.length} erledigt`
                      : a.zugewiesener_name || "Nicht zugewiesen"}
                  </span>
                  {a.faelligkeit_am && <span>fällig {a.faelligkeit_am}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div
        id="abschnitt-material"
        className={`scroll-mt-4 card-ap p-3 ${istAktiverTab("abschnitt-material") ? "" : "hidden"}`}
        {...tabPanelProps("abschnitt-material")}
      >
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Positionen</h2>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => setShowBedarfForm((v) => !v)}
              className="btn-touch text-xs font-medium text-tint"
            >
              {showBedarfForm ? "Abbrechen" : "+ Material bestellen"}
            </button>
            <button
              onClick={() => setShowMaterialForm((v) => !v)}
              className="btn-touch text-xs font-medium text-tint"
            >
              {showMaterialForm ? "Abbrechen" : "+ Material verwenden"}
            </button>
            <button
              onClick={() => setShowLeistungForm((v) => !v)}
              className="btn-touch text-xs font-medium text-tint"
            >
              {showLeistungForm ? "Abbrechen" : "+ Leistung verwenden"}
            </button>
          </div>
        </div>

        {showBedarfForm && (
          <div className="mb-2 space-y-2 border border-sepstrong p-2">
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
              <div className="space-y-2 border border-dashed border-sepstrong p-2">
                <input
                  type="text"
                  value={bedarfNeuBezeichnung}
                  onChange={(e) => setBedarfNeuBezeichnung(e.target.value)}
                  placeholder="Bezeichnung"
                  className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                />
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={bedarfNeuEinheit}
                    onChange={(e) => setBedarfNeuEinheit(e.target.value)}
                    placeholder="Einheit"
                    className="w-20 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                  />
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={bedarfNeuEinzelpreis}
                    onChange={(e) => setBedarfNeuEinzelpreis(e.target.value)}
                    placeholder="Preis (optional)"
                    className="flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                  />
                </div>
                <select
                  value={bedarfNeuLieferantId}
                  onChange={(e) => setBedarfNeuLieferantId(e.target.value)}
                  className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
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
                className="flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <select
                value={bedarfZweck}
                onChange={(e) => setBedarfZweck(e.target.value as MaterialBedarfZweck)}
                className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
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
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <button
              disabled={
                !bedarfMaterialId ||
                !bedarfMenge ||
                (bedarfMaterialId === NEU_MATERIAL && !bedarfNeuBezeichnung.trim()) ||
                materialBedarfMutation.isPending
              }
              onClick={() => materialBedarfMutation.mutate()}
              className="btn-touch btn-ap-primary w-full px-3 py-1.5 text-sm"
            >
              Vormerken
            </button>
            {materialBedarfMutation.isError && (
              <p className="text-xs text-st-fehlt">
                {materialBedarfMutation.error instanceof ApiError
                  ? materialBedarfMutation.error.message
                  : "Fehler beim Vormerken"}
              </p>
            )}
          </div>
        )}

        {(materialBedarfe ?? []).length > 0 &&
          (layout === "dicht" ? (
            <div className="mb-2 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left text-label2">
                    <th className="px-2 py-1 text-xs font-medium">Menge</th>
                    <th className="px-2 py-1 text-xs font-medium">Material</th>
                    <th className="px-2 py-1 text-xs font-medium">Zweck</th>
                    <th className="px-2 py-1 text-xs font-medium">Status</th>
                    <th className="px-2 py-1"></th>
                  </tr>
                </thead>
                <tbody>
                  {materialBedarfe!.map((b) => (
                    <tr key={b.id} className="border-t border-sep">
                      <td className="px-2 py-1.5 tabular-nums text-label">{b.menge}×</td>
                      <td className="px-2 py-1.5 text-label">{b.material_bezeichnung}</td>
                      <td className="px-2 py-1.5 text-label2">{b.zweck === "angebot" ? "Angebot" : "Bestellung"}</td>
                      <td className="px-2 py-1.5 text-label2">{b.status}</td>
                      <td className="px-2 py-1.5 text-right">
                        {b.status === "offen" && (
                          <button
                            onClick={() => bedarfEntfernenMutation.mutate(b.id)}
                            className="btn-touch text-xs text-st-fehlt"
                          >
                            Entfernen
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="mb-2 space-y-1">
              {materialBedarfe!.map((b) => (
                <div
                  key={b.id}
                  className="flex items-center justify-between border border-sepstrong px-2 py-1.5 text-sm"
                >
                  <span className="text-label">
                    {b.menge}× {b.material_bezeichnung}
                    <span className="ml-1.5 border border-sep px-1.5 py-0.5 text-xs text-label">
                      {b.zweck === "angebot" ? "Angebot" : "Bestellung"} · {b.status}
                    </span>
                  </span>
                  {b.status === "offen" && (
                    <button
                      onClick={() => bedarfEntfernenMutation.mutate(b.id)}
                      className="btn-touch text-xs text-st-fehlt"
                    >
                      Entfernen
                    </button>
                  )}
                </div>
              ))}
            </div>
          ))}

        {(materialVerwendungen ?? []).length > 0 || (lvVerwendungen ?? []).length > 0 ? (
          layout === "dicht" ? (
            <div className="mb-2 overflow-x-auto">
              <h3 className="px-1 pb-1 text-xs font-medium text-label2">Verwendet</h3>
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left text-label2">
                    <th className="px-2 py-1 text-xs font-medium">Typ</th>
                    <th className="px-2 py-1 text-xs font-medium">Bezeichnung</th>
                    <th className="px-2 py-1 text-xs font-medium">Menge</th>
                    <th className="px-2 py-1"></th>
                  </tr>
                </thead>
                <tbody>
                  {(materialVerwendungen ?? []).map((v) => (
                    <tr key={`material-${v.id}`} className="border-t border-sep">
                      <td className="px-2 py-1.5">
                        <SymbolKachel icon={Package} farbe="orange" groesse={20} />
                      </td>
                      <td className="px-2 py-1.5 text-label">{v.material_bezeichnung}</td>
                      <td className="px-2 py-1.5 tabular-nums text-label2">
                        {v.menge} {v.material_einheit}
                      </td>
                      <td className="px-2 py-1.5"></td>
                    </tr>
                  ))}
                  {(lvVerwendungen ?? []).map((v) => (
                    <tr key={`lv-${v.id}`} className="border-t border-sep">
                      <td className="px-2 py-1.5">
                        <SymbolKachel icon={Clock} farbe="blue" groesse={20} />
                      </td>
                      <td className="px-2 py-1.5 text-label">{v.lv_bezeichnung}</td>
                      <td className="px-2 py-1.5 tabular-nums text-label2">
                        {v.menge} {v.lv_einheit}
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <button
                          onClick={() => lvVerwendungEntfernenMutation.mutate(v.id)}
                          disabled={lvVerwendungEntfernenMutation.isPending}
                          className="btn-touch text-xs text-st-fehlt disabled:opacity-50"
                        >
                          Entfernen
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="mb-2 space-y-1">
              <h3 className="px-1 text-xs font-medium text-label2">Verwendet</h3>
              {(materialVerwendungen ?? []).map((v) => (
                <div
                  key={`material-${v.id}`}
                  className="flex items-center justify-between gap-2 border border-sepstrong px-2 py-1.5 text-sm"
                >
                  <span className="flex min-w-0 items-center gap-2 text-label">
                    <SymbolKachel icon={Package} farbe="orange" groesse={24} />
                    <span className="truncate">
                      {v.menge}× {v.material_bezeichnung}
                      <span className="ml-1.5 border border-sep px-1.5 py-0.5 text-xs text-label">
                        {v.material_einheit}
                      </span>
                    </span>
                  </span>
                </div>
              ))}
              {(lvVerwendungen ?? []).map((v) => (
                <div
                  key={`lv-${v.id}`}
                  className="flex items-center justify-between gap-2 border border-sepstrong px-2 py-1.5 text-sm"
                >
                  <span className="flex min-w-0 items-center gap-2 text-label">
                    <SymbolKachel icon={Clock} farbe="blue" groesse={24} />
                    <span className="truncate">
                      {v.menge}× {v.lv_bezeichnung}
                      <span className="ml-1.5 border border-sep px-1.5 py-0.5 text-xs text-label">
                        {v.lv_einheit}
                      </span>
                    </span>
                  </span>
                  <button
                    onClick={() => lvVerwendungEntfernenMutation.mutate(v.id)}
                    disabled={lvVerwendungEntfernenMutation.isPending}
                    className="btn-touch shrink-0 text-xs text-st-fehlt disabled:opacity-50"
                  >
                    Entfernen
                  </button>
                </div>
              ))}
            </div>
          )
        ) : null}

        {kannDisponieren && (
          <button
            onClick={() => angebotAusVorgangMutation.mutate()}
            disabled={angebotAusVorgangMutation.isPending}
            className="btn-touch mb-2 btn-ap w-full px-3 py-1.5 text-sm"
          >
            + Angebot aus diesem Vorgang erstellen
          </button>
        )}

        {kannDisponieren && (
          <button
            onClick={() => rechnungAusVorgangMutation.mutate()}
            disabled={rechnungAusVorgangMutation.isPending}
            className="btn-touch mb-2 btn-ap w-full px-3 py-1.5 text-sm"
          >
            + Rechnung aus diesem Vorgang erstellen
          </button>
        )}

        {showMaterialForm && (
          <div className="space-y-2 border border-sepstrong p-2">
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
                className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
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
                className="flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <button
                disabled={!materialId || !materialLagerId || !materialMenge || materialVerwendenMutation.isPending}
                onClick={() => materialVerwendenMutation.mutate()}
                className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-sm"
              >
                Erfassen
              </button>
            </div>
            {materialVerwendenMutation.isError && (
              <p className="text-xs text-st-fehlt">
                {materialVerwendenMutation.error instanceof ApiError
                  ? materialVerwendenMutation.error.message
                  : "Fehler beim Erfassen"}
              </p>
            )}
          </div>
        )}

        {showLeistungForm && (
          <div className="space-y-2 border border-sepstrong p-2">
            {(leistungsverzeichnis ?? []).length === 0 ? (
              <p className="text-xs text-label2">
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
                    className="flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                  />
                  <button
                    disabled={!lvPositionId || !lvMenge || leistungVerwendenMutation.isPending}
                    onClick={() => leistungVerwendenMutation.mutate()}
                    className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-sm"
                  >
                    Erfassen
                  </button>
                </div>
                {leistungVerwendenMutation.isError && (
                  <p className="text-xs text-st-fehlt">
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
        <div
          className={`card-ap p-3 ${istAktiverTab("abschnitt-uebersicht") ? "" : "hidden"}`}
          {...tabPanelProps("abschnitt-uebersicht")}
        >
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Nachunternehmer</h2>
            {!vorgang.partner_id && (
              <button
                onClick={() => setShowPartnerForm((v) => !v)}
                className="btn-touch text-xs font-medium text-tint"
              >
                {showPartnerForm ? "Abbrechen" : "+ Zuweisen"}
              </button>
            )}
          </div>

          {partnerWarnung && (
            <p className="mb-2 rounded-md bg-st-arbeit-bg px-3 py-2 text-xs text-st-arbeit">
              Für diesen Partner liegt keine gültige Freistellungsbescheinigung vor -- ohne sie greift bei
              Zahlungen für Bauleistungen grundsätzlich die 15%-Bauabzugsteuer nach § 48 EStG.
            </p>
          )}

          {vorgang.partner_id ? (
            <div className="flex items-center justify-between border border-sepstrong px-3 py-2">
              <div>
                <button
                  onClick={() => navigate(`/partner/${vorgang.partner_id}`)}
                  className="text-sm font-medium text-label hover:underline"
                >
                  {zugewiesenerPartner?.name ?? "…"}
                </button>
                {vorgang.partner_honorar_netto && (
                  <div className="text-xs text-label2">
                    Honorar: {vorgang.partner_honorar_netto} EUR netto
                  </div>
                )}
                {vorgang.partner_freigabe_status === "abgelehnt" && vorgang.partner_ablehnung_grund && (
                  <div className="text-xs text-st-fehlt">
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
                  className="btn-touch text-xs text-st-fehlt"
                >
                  Aufheben
                </button>
              </div>
            </div>
          ) : (
            !showPartnerForm && (
              <p className="text-sm text-label2">Kein Nachunternehmer zugewiesen.</p>
            )
          )}

          {showPartnerForm && (
            <div className="space-y-2 border border-sepstrong p-2">
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
                className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <button
                disabled={!partnerAuswahl || partnerZuweisenMutation.isPending}
                onClick={() => partnerZuweisenMutation.mutate()}
                className="btn-touch btn-ap-primary w-full px-3 py-1.5 text-sm"
              >
                Zuweisen
              </button>
            </div>
          )}
        </div>
      )}

      {/* Verlauf-Tab-Inhalt (EmailSection + gemischter Kommentar-/E-Mail-Feed
       * + Kommentar-Composer) hat keinen einzelnen umschliessenden Container
       * im Quelltext -- deshalb hier als ein Wrapper-Div fuer das
       * Tab-Ausblenden im "dicht"-Layout ergaenzt, statt jede einzelne
       * Stelle separat zu gaten. */}
      <div className={istAktiverTab("abschnitt-verlauf") ? "" : "hidden"} {...tabPanelProps("abschnitt-verlauf")}>
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
        <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Verlauf</h2>
        <span className="text-sm text-label2">
          {kundenansicht ? "Kundenansicht" : "Interne Ansicht"}
        </span>
        <button
          onClick={() => setKundenansicht((v) => !v)}
          className={`btn-touch border px-3 py-1 text-xs font-semibold ${
            kundenansicht
              ? "border-tint bg-tint-solid text-white"
              : "border-sep text-label hover:bg-fill"
          }`}
        >
          Umschalten
        </button>
      </div>

      <div>
        {verlaufEintraege.length === 0 && eigeneOutboxItems.length === 0 ? (
          <p className="text-center text-sm text-label2">Noch keine Einträge.</p>
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
        <div className="sticky bottom-[var(--klebe-abstand)] space-y-2 card-ap p-3">
          <div className="relative">
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Kommentar schreiben…"
              rows={2}
              className="w-full resize-none border border-sep bg-transparent p-2 text-sm text-label"
            />
            {/* .card-ap bringt schon eine eigene box-shadow mit (siehe
             * Cascade-Layer-Falle in DESIGN.md) -- shadow-lg hier waere
             * tot, deshalb nicht ergaenzt. */}
            {showMentionPicker && (
              <div className="absolute bottom-full left-0 mb-1 max-h-40 w-full overflow-y-auto card-ap">
                {users?.map((u) => (
                  <button
                    key={u.id}
                    onClick={() => {
                      setComment((c) => `${c}@[${u.name}](${u.id}) `);
                      setShowMentionPicker(false);
                    }}
                    className="btn-touch block w-full px-3 py-2 text-left text-sm text-label hover:bg-fill"
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
          <input
            ref={dokumentInputRef}
            type="file"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) dokumentMutation.mutate(file);
              e.target.value = "";
            }}
          />
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setShowMentionPicker((v) => !v)}
                title="Erwähnen"
                aria-label="Erwähnen"
                className="btn-touch flex h-9 w-9 items-center justify-center border border-sep text-base text-label hover:bg-fill"
              >
                @
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={fotoMutation.isPending}
                title="Foto anhängen"
                aria-label="Foto anhängen"
                className="btn-touch flex h-9 w-9 items-center justify-center border border-sep text-label hover:bg-fill disabled:opacity-50"
              >
                <Camera size={16} strokeWidth={2} />
              </button>
              <button
                onClick={() => dokumentInputRef.current?.click()}
                disabled={dokumentMutation.isPending}
                title="Dokument anhängen"
                aria-label="Dokument anhängen"
                className="btn-touch flex h-9 w-9 items-center justify-center border border-sep text-label hover:bg-fill disabled:opacity-50"
              >
                <Paperclip size={16} strokeWidth={2} />
              </button>
              <button
                onClick={() => setShowUnterschriftPad((v) => !v)}
                title="Unterschrift erfassen"
                aria-label="Unterschrift erfassen"
                className="btn-touch flex h-9 w-9 items-center justify-center border border-sep text-label hover:bg-fill"
              >
                <PenLine size={16} strokeWidth={1.5} />
              </button>
              <button
                onClick={() => setKundensichtbar((v) => !v)}
                title={kundensichtbar ? "Für Kunde sichtbar – antippen zum Verbergen" : "Nur intern – antippen um für Kunde sichtbar zu machen"}
                aria-label="Für Kunde sichtbar umschalten"
                aria-pressed={kundensichtbar}
                className={`btn-touch flex h-9 w-9 items-center justify-center border ${
                  kundensichtbar
                    ? "border-tint text-tint"
                    : "border-sep text-label2 hover:bg-fill"
                }`}
              >
                {kundensichtbar ? <Eye size={16} strokeWidth={2} /> : <EyeOff size={16} strokeWidth={2} />}
              </button>
            </div>
            <button
              onClick={() => commentMutation.mutate()}
              disabled={!comment.trim() || commentMutation.isPending}
              className="btn-touch btn-ap-primary shrink-0 px-4 py-2 text-sm"
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
                <p className="mt-1 text-xs text-st-fehlt">
                  {unterschriftMutation.error instanceof ApiError
                    ? unterschriftMutation.error.message
                    : "Unterschrift konnte nicht gespeichert werden — bitte erneut versuchen."}
                </p>
              )}
            </div>
          )}
        </div>
      )}
      </div>

      {zeitSheetModus && (
        <ZeiteintragSheet
          offen
          onClose={() => setZeitSheetModus(null)}
          vorgangId={id!}
          eintrag={zeitSheetModus === "neu" || zeitSheetModus === "neu-fahrt" ? null : zeitSheetModus}
          initialKategorie={zeitSheetModus === "neu-fahrt" ? "fahrzeit" : undefined}
          onGespeichert={() => setZeitSheetModus(null)}
        />
      )}

      <Sheet
        offen={!!nachStoppenEintrag}
        onClose={() => setNachStoppenEintrag(null)}
        titel="Was hast du gemacht?"
        links={
          <button
            type="button"
            onClick={() => setNachStoppenEintrag(null)}
            className="text-[17px] text-tint"
          >
            Später
          </button>
        }
        rechts={
          <button
            type="button"
            onClick={() => nachStoppenTaetigkeitMutation.mutate()}
            disabled={!nachStoppenTaetigkeit.trim() || nachStoppenTaetigkeitMutation.isPending}
            className="text-[17px] font-semibold text-tint disabled:opacity-40"
          >
            Fertig
          </button>
        }
      >
        <div className="space-y-4 p-4">
          <input
            autoFocus
            value={nachStoppenTaetigkeit}
            onChange={(e) => setNachStoppenTaetigkeit(e.target.value)}
            placeholder="z. B. Wartung an Anlage durchgeführt"
            className="field-ap"
          />
        </div>
      </Sheet>
    </div>
  );
}
