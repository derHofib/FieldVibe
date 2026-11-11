import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { heuteIso } from "../../utils/format";
import { AlertTriangle, Ban, Building2, Clock, MoreHorizontal, Trash2, UserCheck, UserPlus } from "lucide-react";
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
  projektAufgabenApi,
  standorteApi,
  termineApi,
  usersApi,
  vorgangEventsApi,
  vorgaengeApi,
  zeiterfassungApi,
} from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FormularAbschnitt } from "../../components/FormularAbschnitt";
import { Sheet } from "../../components/apple/Sheet";
import { PulldownMenu } from "../../components/apple/PulldownMenu";
import { VorgangStatusAktionen } from "./vorgang/VorgangStatusAktionen";
import { ZeiteintragSheet } from "../../components/ZeiteintragSheet";
import { useAuth } from "../../context/AuthContext";
import { cacheEvents, cacheKunde, getCachedEvents, getCachedKunde } from "../../offline/cache";
import {
  getOutboxItems,
  queueDokument,
  queueFoto,
  queueKommentar,
  queueStatusChange,
} from "../../offline/outbox";
import { formatSekundenAlsHHMM } from "../../utils/duration";
import { istModulAktiv } from "../../utils/module";
import { openPdfBlob } from "../../utils/pdf";
import type {
  Adresse,
  Leistungstyp,
  MangelSchweregrad,
  MangelStatus,
  MaterialBedarfZweck,
  TerminWarnung,
  VorgangStatus,
  Zeiterfassung,
} from "../../types";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { DetailSkeleton } from "../../components/Skeleton";
import {
  type VerlaufEintrag,
  ANCHOR_ABSCHNITTE,
  ABSCHNITT_ROUTE,
  NEU_MATERIAL,
  VORGANG_STATUS_GESCHLOSSEN,
  VORGANG_STATUS_ZEIT_GESPERRT,
  PRIORITAET_OPTIONEN,
  LEISTUNGSTYPEN,
  STATUS_LABEL,
  LEISTUNGSTYP_LABEL,
  ABRECHNUNGSART_LABEL,
  leereAdresse,
  adresseAlsZeile,
} from "./vorgang/konstanten";
import { ArbeitszeitInhalt } from "./vorgang/ArbeitszeitInhalt";
import { VerlaufInhalt } from "./vorgang/VerlaufInhalt";
import { PositionenInhalt } from "./vorgang/PositionenInhalt";
import { PartnerAbschnitt } from "./vorgang/PartnerAbschnitt";
import { MaengelAbschnitt } from "./vorgang/MaengelAbschnitt";
import { TermineAbschnitt } from "./vorgang/TermineAbschnitt";

// Lazy statt statisch importiert: mapbox-gl allein ist ~1.8 MB und wuerde
// sonst in jedem Bundle landen, auch fuer Nutzer, die nie eine Karte sehen
// (und den PWA-Precache-Limit von 2 MiB sprengen).
const MapboxMap = lazy(() => import("../../components/MapboxMap").then((m) => ({ default: m.MapboxMap })));

// id optional als Prop, damit die Office-Oberflaeche diese Seite in ihrem
// Detail-Panel einbetten kann, ohne dass es einen zweiten, parallel zu
// pflegenden Nachbau braucht. Ohne Prop verhaelt sie sich wie bisher.
export function VorgangDetailPage({
  id: idProp,
  layout = "kompakt",
  // Eigene Unterseite fuer einen einzelnen Abschnitt (Routen /vorgaenge/
  // :id/zeit, /verlauf, /positionen, siehe App.tsx/OfficeApp.tsx und
  // ABSCHNITT_ROUTE oben) -- ausgeloest ueber die jeweilige Anker-Pille
  // bzw. den Einstiegspunkt auf der Uebersicht im "kompakt"-Layout. Im
  // "dicht"-Layout (Office-Inspektor-Spalte) ohne Wirkung, dort sind alle
  // Abschnitte ohnehin schon echte Tabs.
  ansicht = "voll",
  // Nur im "dicht"-Layout relevant: die Office-Vollbild-Route (siehe
  // OfficeApp.tsx, /vorgaenge/:id/vollbild) hat echte Desktop-Breite statt
  // der schmalen Inspektor-Spalte in VorgaengeListe.tsx -- dort lohnt sich
  // eine feste zweite Spalte fuer den Verlauf (immer sichtbar statt Tab,
  // siehe verlaufSpalteBreit unten), in der schmalen Spalte nicht.
  breit = false,
}: {
  id?: string;
  layout?: "kompakt" | "dicht";
  ansicht?: "voll" | "zeit" | "verlauf" | "positionen";
  breit?: boolean;
} = {}) {
  const bestaetigen = useBestaetigung();
  const { id: idParam } = useParams<{ id: string }>();
  const id = idProp ?? idParam;
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  // Nur im "dicht"-Layout (Office-Inspektor-Spalte, siehe VorgaengeListe.tsx)
  // werden die Abschnitte zu echten Tabs (ein Panel sichtbar) statt der
  // mobilen Anker-Scroll-Liste (alle Abschnitte untereinander).
  const [desktopTab, setDesktopTab] = useState(ANCHOR_ABSCHNITTE[0].ziel);
  const istAktiverTab = (ziel: string) => layout !== "dicht" || desktopTab === ziel;
  const tabPanelProps = (ziel: string) =>
    layout === "dicht" ? { role: "tabpanel" as const, "aria-labelledby": `tab-${ziel}` } : {};
  const { currentUser, hatRecht } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dokumentInputRef = useRef<HTMLInputElement>(null);

  const [comment, setComment] = useState("");
  const [kundensichtbar, setKundensichtbar] = useState(false);
  const [anPartner, setAnPartner] = useState(false);
  const [kundenansicht, setKundenansicht] = useState(false);
  // Verlauf-Filter: "system" = Statuswechsel/automatische Eintraege,
  // "kommentare" = alles Nutzergenerierte (Kommentar/Foto/Unterschrift/
  // Dokument), "email" = E-Mail-Verlauf -- rein clientseitig auf der
  // bereits geladenen Liste, kein eigener Endpunkt noetig.
  const [verlaufFilter, setVerlaufFilter] = useState<"alle" | "kommentare" | "system" | "email">("alle");
  const [showMentionPicker, setShowMentionPicker] = useState(false);
  const [showUnterschriftPad, setShowUnterschriftPad] = useState(false);
  const [taetigkeit, setTaetigkeit] = useState("");
  // Zeit-Tab: Sheet zum Anlegen/Bearbeiten eines Eintrags (Stufe 1, siehe
  // docs/konzepte/ZEITERFASSUNG.md) -- offen, wenn zeitSheetModus gesetzt
  // ist. "neu" oeffnet leer (vorbelegt mit diesem Vorgang, kategorie=
  // "auftrag"), km/Fahrzeug sind darin ein optionales Feld statt eines
  // eigenen "Fahrt"-Einstiegs (Konzept Abschnitt 11); ein Eintrag oeffnet
  // zum Bearbeiten.
  const [zeitSheetModus, setZeitSheetModus] = useState<"neu" | Zeiterfassung | null>(null);
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
    meta: { erfolg: "Gelöscht" },
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
    meta: { erfolg: "Gespeichert" },
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
  const { data: users } = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl, enabled: hatRecht("mitarbeiterverwaltung", "sehen") });
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
    meta: { erfolg: "Status geändert" },
    mutationFn: ({ mangelId, status }: { mangelId: string; status: MangelStatus }) =>
      maengelApi.update(mangelId, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["maengel", "vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
    onError: meldeAktionsFehler,
  });

  const deleteMangelMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: (mangelId: string) => maengelApi.remove(mangelId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["maengel", "vorgang", id] }),
    onError: meldeAktionsFehler,
  });

  const deleteTerminMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: (terminId: string) => termineApi.remove(terminId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["termine", "vorgang", id] }),
    onError: meldeAktionsFehler,
  });

  const kannPapierkorbLoeschen = currentUser?.role === "loesch_operativ";

  const angebotAusMaengelnMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: (mangelIds: string[]) => angeboteApi.createFromMaengel(mangelIds),
    onSuccess: (angebot) => navigate(`/angebote/${angebot.id}`),
    onError: meldeAktionsFehler,
  });

  const angebotAusVorgangMutation = useMutation({
    meta: { erfolg: "Angelegt" },
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

  const { data: materialListe } = useQuery({ queryKey: ["material"], queryFn: () => materialApi.list(), enabled: hatRecht("material", "sehen") });
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
    meta: { erfolg: "Gelöscht" },
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
    enabled: istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "sehen") && !!vorgang?.partner_id,
  });
  const partnerKommentarMoeglich = istModulAktiv(currentUser, "nachunternehmer") && !!vorgang?.partner_id;

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
    meta: { erfolg: "Gelöscht" },
    mutationFn: (bedarfId: string) => materialBedarfeApi.remove(bedarfId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["material-bedarfe", "vorgang", id] }),
    onError: meldeAktionsFehler,
  });

  const deleteVorgangMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: () => vorgaengeApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      navigate("/feed");
    },
    onError: meldeAktionsFehler,
  });

  const statusMutation = useMutation({
    meta: { erfolg: "Status geändert" },
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
    meta: { erfolg: "Angelegt" },
    mutationFn: (leistungstyp: Leistungstyp) => vorgaengeApi.folgeAuftrag(id!, leistungstyp),
    onSuccess: (result) => {
      setFolgeVorgangId(result.id);
      queryClient.invalidateQueries({ queryKey: ["vorgaenge", "folge", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
    onError: meldeAktionsFehler,
  });

  const uebernehmenMutation = useMutation({
    meta: { erfolg: "Übernommen" },
    mutationFn: () => vorgaengeApi.uebernehmen(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
    onError: meldeAktionsFehler,
  });

  const prioritaetMutation = useMutation({
    meta: { erfolg: "Gespeichert" },
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
          partner_sichtbar: partnerKommentarMoeglich && anPartner,
          client_uuid: crypto.randomUUID(),
        });
      } catch (err) {
        if (err instanceof ApiError) throw err; // echte Ablehnung, nicht queuen
        await queueKommentar(id!, comment, kundensichtbar, partnerKommentarMoeglich && anPartner); // Netzwerkfehler -> offline
        return null;
      }
    },
    onSuccess: () => {
      setComment("");
      setKundensichtbar(false);
      setAnPartner(false);
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
  if (!vorgang) return <DetailSkeleton />;

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
  const verlaufEintraege: VerlaufEintrag[] = [
    ...sichtbareEvents.map((event): VerlaufEintrag => ({ art: "event", zeit: event.created_at, event })),
    ...(kundenansicht ? [] : (emails ?? []).map((email): VerlaufEintrag => ({ art: "email", zeit: email.created_at, email }))),
  ].sort((a, b) => new Date(b.zeit).getTime() - new Date(a.zeit).getTime());
  const verlaufEintraegeGefiltert = verlaufEintraege.filter((eintrag) => {
    if (verlaufFilter === "alle") return true;
    if (eintrag.art === "email") return verlaufFilter === "email";
    if (verlaufFilter === "system") return eintrag.event.is_system || eintrag.event.event_type === "status_change";
    // "kommentare": alles Nutzergenerierte -- Kommentar, Foto, Unterschrift, Dokument.
    return !eintrag.event.is_system && eintrag.event.event_type !== "status_change";
  });
  const eigeneOutboxItemsGefiltert = eigeneOutboxItems.filter((item) => {
    if (verlaufFilter === "alle") return true;
    if (verlaufFilter === "email") return false; // Outbox kennt keine E-Mails.
    if (verlaufFilter === "system") return item.kind === "status";
    return item.kind !== "status";
  });

  const gesamtSekunden = (zeiterfassungListe ?? []).reduce((summe, e) => {
    if (!e.ende_at) return summe;
    return summe + (new Date(e.ende_at).getTime() - new Date(e.start_at).getTime()) / 1000;
  }, 0);
  const gesamtStunden = formatSekundenAlsHHMM(gesamtSekunden);
  const gesamtKm = (zeiterfassungListe ?? []).reduce((summe, e) => summe + (Number(e.km) || 0), 0);

  // Kennzahlen-Zeile auf der Uebersicht (nur "kompakt"+"voll", siehe unten) --
  // je ein kompakter Wert pro Abschnitt, verlinkt dorthin, damit man nicht
  // erst hineinklicken muss um zu wissen, ob dort ueberhaupt etwas ist.
  const naechsterTermin = (termine ?? [])
    .filter((t) => new Date(t.start_at).getTime() >= Date.now() && t.status !== "abgesagt")
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())[0];
  const offeneMaengelAnzahl = (maengel ?? []).filter((m) => m.status !== "behoben" && m.status !== "abgelehnt").length;
  const positionenAnzahl =
    (materialBedarfe?.length ?? 0) + (materialVerwendungen?.length ?? 0) + (lvVerwendungen?.length ?? 0);

  const timerLaeuftHier = laufenderTimer && laufenderTimer.vorgang_id === id;
  const timerLaeuftAnderswo = laufenderTimer && laufenderTimer.vorgang_id !== id;

  // Eine klare Primäraktion statt vieler gleich gewichteter Text-Links --
  // je nach Zustand des Vorgangs genau EIN naheliegender naechster Schritt,
  // als Sticky-Button am unteren Bildschirmrand (siehe primaryAktionBar
  // unten). Reihenfolge = Prioritaet: Zuweisung vor laufendem Timer vor
  // Abrechnung vor normaler Zeiterfassung.
  const primaerAktion: { label: string; onClick: () => void; disabled?: boolean } | null =
    !vorgang.zugewiesener_user_id && !VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status)
      ? {
          label: "Vorgang übernehmen",
          onClick: () => uebernehmenMutation.mutate(),
          disabled: uebernehmenMutation.isPending,
        }
      : timerLaeuftHier
        ? {
            label: "Zeit stoppen",
            onClick: () => stopTimerMutation.mutate(laufenderTimer!.id),
            disabled: stopTimerMutation.isPending,
          }
        : vorgang.status === "abgeschlossen" && kannDisponieren
          ? {
              label: "Rechnung erstellen",
              onClick: () => rechnungAusVorgangMutation.mutate(),
              disabled: rechnungAusVorgangMutation.isPending,
            }
          : !VORGANG_STATUS_ZEIT_GESPERRT.includes(vorgang.status)
            ? { label: "Zeit erfassen", onClick: () => navigate(`/vorgaenge/${id}/zeit`) }
            : null;

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
  async function handleBuchen() {
    const stunden = formatSekundenAlsHHMM(
      ausgewaehlteEintraege.reduce(
        (summe, e) => summe + (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000,
        0,
      ),
    );
    if (
      await bestaetigen({ titel: `${ausgewaehlteEintraege.length} Eintrag/Einträge mit insgesamt ${stunden} Std. buchen?`, text: `Gebuchte Einträge kannst du danach nicht mehr ändern.`, bestaetigenLabel: "Buchen", destruktiv: false })
    ) {
      buchenMutation.mutate([...ausgewaehlteZeitIds]);
    }
  }

  // Inhalt der Arbeitszeit-Ansicht -- im "dicht"-Layout einer von mehreren
  // echten Tabs (siehe ANCHOR_ABSCHNITTE), im "kompakt"-Layout dagegen eine
  // eigene Unterseite (Route /vorgaenge/:id/zeit, ansicht="zeit" unten) statt
  // eines Abschnitts auf der Hauptseite -- dort bleibt nur der "Zeit
  // erfassen"-Button. Als Variable statt direkt im JSX, weil beide Stellen
  // denselben Inhalt brauchen.
  const arbeitszeitInhalt = (
    <ArbeitszeitInhalt
      vorgang={vorgang}
      setZeitSheetModus={setZeitSheetModus}
      gesamtStunden={gesamtStunden}
      gesamtKm={gesamtKm}
      timerLaeuftHier={timerLaeuftHier}
      laufenderTimer={laufenderTimer}
      stopTimerMutation={stopTimerMutation}
      taetigkeit={taetigkeit}
      setTaetigkeit={setTaetigkeit}
      startTimerMutation={startTimerMutation}
      timerLaeuftAnderswo={timerLaeuftAnderswo}
      zeiterfassungListe={zeiterfassungListe}
      layout={layout}
      users={users}
      kannZeitAuswaehlen={kannZeitAuswaehlen}
      ausgewaehlteZeitIds={ausgewaehlteZeitIds}
      zeitCheckboxToggeln={zeitCheckboxToggeln}
      stornierenModus={stornierenModus}
      stornierenGrund={stornierenGrund}
      setStornierenGrund={setStornierenGrund}
      stornierenMutation={stornierenMutation}
      setStornierenModus={setStornierenModus}
      ausgewaehlterStatus={ausgewaehlterStatus}
      vormerkenMutation={vormerkenMutation}
      darfZeitenBuchen={darfZeitenBuchen}
      handleBuchen={handleBuchen}
      buchenMutation={buchenMutation}
      zurueckziehenMutation={zurueckziehenMutation}
      setAusgewaehlteZeitIds={setAusgewaehlteZeitIds}
    />
  );

  // Inhalt der Verlauf-Ansicht -- gleiches Prinzip wie arbeitszeitInhalt
  // oben: im "dicht"-Layout ein echter Tab, im "kompakt"-Layout eine eigene
  // Unterseite (Route /vorgaenge/:id/verlauf, ansicht="verlauf" unten)
  // statt eines immer sichtbaren Abschnitts auf der Hauptseite.
  const verlaufInhalt = (
    <VerlaufInhalt
      id={id}
      kunde={kunde}
      location={location}
      kundenansicht={kundenansicht}
      setKundenansicht={setKundenansicht}
      setVerlaufFilter={setVerlaufFilter}
      verlaufFilter={verlaufFilter}
      verlaufEintraegeGefiltert={verlaufEintraegeGefiltert}
      eigeneOutboxItemsGefiltert={eigeneOutboxItemsGefiltert}
      queryClient={queryClient}
      highlightMutation={highlightMutation}
      comment={comment}
      setComment={setComment}
      showMentionPicker={showMentionPicker}
      users={users}
      setShowMentionPicker={setShowMentionPicker}
      fileInputRef={fileInputRef}
      fotoMutation={fotoMutation}
      dokumentInputRef={dokumentInputRef}
      dokumentMutation={dokumentMutation}
      partnerKommentarMoeglich={partnerKommentarMoeglich}
      anPartner={anPartner}
      setAnPartner={setAnPartner}
      zugewiesenerPartner={zugewiesenerPartner}
      setShowUnterschriftPad={setShowUnterschriftPad}
      setKundensichtbar={setKundensichtbar}
      kundensichtbar={kundensichtbar}
      commentMutation={commentMutation}
      showUnterschriftPad={showUnterschriftPad}
      unterschriftMutation={unterschriftMutation}
    />
  );

  // Inhalt der Positionen-Ansicht -- gleiches Prinzip wie arbeitszeitInhalt/
  // verlaufInhalt oben: im "dicht"-Layout ein echter Tab, im "kompakt"-Layout
  // eine eigene Unterseite (Route /vorgaenge/:id/positionen, ansicht=
  // "positionen" unten) statt eines Abschnitts auf der Hauptseite.
  const positionenInhalt = (
    <PositionenInhalt
      setShowBedarfForm={setShowBedarfForm}
      showBedarfForm={showBedarfForm}
      setShowMaterialForm={setShowMaterialForm}
      showMaterialForm={showMaterialForm}
      setShowLeistungForm={setShowLeistungForm}
      showLeistungForm={showLeistungForm}
      bedarfMaterialId={bedarfMaterialId}
      setBedarfMaterialId={setBedarfMaterialId}
      materialListe={materialListe}
      bedarfNeuBezeichnung={bedarfNeuBezeichnung}
      setBedarfNeuBezeichnung={setBedarfNeuBezeichnung}
      bedarfNeuEinheit={bedarfNeuEinheit}
      setBedarfNeuEinheit={setBedarfNeuEinheit}
      bedarfNeuEinzelpreis={bedarfNeuEinzelpreis}
      setBedarfNeuEinzelpreis={setBedarfNeuEinzelpreis}
      bedarfNeuLieferantId={bedarfNeuLieferantId}
      setBedarfNeuLieferantId={setBedarfNeuLieferantId}
      lieferantenFuerNeuesMaterial={lieferantenFuerNeuesMaterial}
      bedarfMenge={bedarfMenge}
      setBedarfMenge={setBedarfMenge}
      bedarfZweck={bedarfZweck}
      setBedarfZweck={setBedarfZweck}
      bedarfNotiz={bedarfNotiz}
      setBedarfNotiz={setBedarfNotiz}
      materialBedarfMutation={materialBedarfMutation}
      materialBedarfe={materialBedarfe}
      layout={layout}
      bedarfEntfernenMutation={bedarfEntfernenMutation}
      materialVerwendungen={materialVerwendungen}
      lvVerwendungen={lvVerwendungen}
      lvVerwendungEntfernenMutation={lvVerwendungEntfernenMutation}
      kannDisponieren={kannDisponieren}
      angebotAusVorgangMutation={angebotAusVorgangMutation}
      rechnungAusVorgangMutation={rechnungAusVorgangMutation}
      materialId={materialId}
      setMaterialId={setMaterialId}
      setMaterialLagerId={setMaterialLagerId}
      meinFahrzeug={meinFahrzeug}
      materialLagerId={materialLagerId}
      lagerorte={lagerorte}
      materialMenge={materialMenge}
      setMaterialMenge={setMaterialMenge}
      materialVerwendenMutation={materialVerwendenMutation}
      leistungsverzeichnis={leistungsverzeichnis}
      lvPositionId={lvPositionId}
      setLvPositionId={setLvPositionId}
      lvMenge={lvMenge}
      setLvMenge={setLvMenge}
      leistungVerwendenMutation={leistungVerwendenMutation}
    />
  );

  // "Vollbild"-Layout (Office-Route /vorgaenge/:id/vollbild, siehe
  // OfficeApp.tsx): Verlauf steht dort als feste zweite Spalte staendig
  // sichtbar neben den uebrigen (weiterhin per Tab umschaltbaren)
  // Abschnitten, statt selbst ein Tab zu sein -- lohnt sich nur bei
  // echter Desktop-Breite, nicht in der schmalen Inspektor-Spalte
  // (VorgaengeListe.tsx), daher eigener "breit"-Prop statt an "dicht"
  // allein gekoppelt.
  const verlaufSpalteBreit = layout === "dicht" && breit;

  const dichtLinkeSpalteInhalt = (
    <>
      <div
        id="abschnitt-uebersicht"
        className={`scroll-mt-4 grid gap-4 ${istAktiverTab("abschnitt-uebersicht") ? "" : "hidden"}`}
        {...tabPanelProps("abschnitt-uebersicht")}
      >
      <div className="card-ap p-4">
        <div className="text-xs text-label2">{vorgang.vorgangsnummer}</div>
        <h1 className="font-heading text-lg font-semibold text-label">{vorgang.titel}</h1>
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

        <VorgangStatusAktionen
          status={vorgang.status}
          darfAendern={kannDisponieren}
          pending={statusMutation.isPending}
          onWaehle={(status) => {
            if (status === "wartet_kunde") {
              setWiedervorlageTage("");
              setShowWartetKundeDialog(true);
              return;
            }
            statusMutation.mutate({ status });
          }}
        />

        <div className="mt-2 flex flex-wrap items-center gap-2">
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
                onClick={async () => {
                  if (
                    vorgang.zugewiesener_user_id &&
                    vorgang.zugewiesener_user_id !== currentUser.id &&
                    !(await bestaetigen({ titel: `Dieser Vorgang ist bereits "${vorgang.zugewiesener_name}" zugewiesen. Trotzdem an mich übernehmen?`, bestaetigenLabel: "Übernehmen", destruktiv: false }))
                  ) {
                    return;
                  }
                  uebernehmenMutation.mutate();
                }}
                disabled={uebernehmenMutation.isPending || vorgang.zugewiesener_user_id === currentUser.id}
                className="btn-touch btn-ap-primary flex items-center gap-1 px-3 py-1.5 text-xs disabled:cursor-not-allowed"
              >
                <UserCheck size={13} strokeWidth={2} />
                {vorgang.zugewiesener_user_id === currentUser.id ? "Von mir übernommen" : "Vorgang übernehmen"}
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
      </div>

      </div>

      {layout === "dicht" && (
        <div
          id="abschnitt-zeit"
          className={`scroll-mt-4 card-ap p-3 ${istAktiverTab("abschnitt-zeit") ? "" : "hidden"}`}
          {...tabPanelProps("abschnitt-zeit")}
        >
          {arbeitszeitInhalt}
        </div>
      )}

      <TermineAbschnitt
        istAktiverTab={istAktiverTab}
        tabPanelProps={tabPanelProps}
        layout={layout}
        termine={termine}
        showTerminForm={showTerminForm}
        kannDisponieren={kannDisponieren}
        setShowTerminForm={setShowTerminForm}
        terminStart={terminStart}
        setTerminStart={setTerminStart}
        setTerminEnde={setTerminEnde}
        setTerminTechnikerId={setTerminTechnikerId}
        users={users}
        terminWarnungen={terminWarnungen}
        terminTitel={terminTitel}
        setTerminTitel={setTerminTitel}
        terminTechnikerId={terminTechnikerId}
        terminEnde={terminEnde}
        terminMutation={terminMutation}
        terminWocheOffset={terminWocheOffset}
        setTerminWocheOffset={setTerminWocheOffset}
        kannPapierkorbLoeschen={kannPapierkorbLoeschen}
        bestaetigen={bestaetigen}
        deleteTerminMutation={deleteTerminMutation}
      />

      {vorgang && (
        <div className={istAktiverTab("abschnitt-uebersicht") ? "" : "hidden"} {...tabPanelProps("abschnitt-uebersicht")}>
          <FormularAbschnitt vorgangId={vorgang.id} vorgangStatus={vorgang.status} />
        </div>
      )}

      <MaengelAbschnitt
        istAktiverTab={istAktiverTab}
        tabPanelProps={tabPanelProps}
        layout={layout}
        maengel={maengel}
        showMangelForm={showMangelForm}
        maengelProtokollMutation={maengelProtokollMutation}
        setShowMangelForm={setShowMangelForm}
        mangelBeschreibung={mangelBeschreibung}
        setMangelBeschreibung={setMangelBeschreibung}
        mangelSchweregrad={mangelSchweregrad}
        setMangelSchweregrad={setMangelSchweregrad}
        mangelMutation={mangelMutation}
        mangelErfassen={mangelErfassen}
        mangelStatusMutation={mangelStatusMutation}
        kannPapierkorbLoeschen={kannPapierkorbLoeschen}
        bestaetigen={bestaetigen}
        deleteMangelMutation={deleteMangelMutation}
        kannDisponieren={kannDisponieren}
        angebotAusMaengelnMutation={angebotAusMaengelnMutation}
      />

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

      {layout === "dicht" && (
        <div
          id="abschnitt-material"
          className={`scroll-mt-4 card-ap p-3 ${istAktiverTab("abschnitt-material") ? "" : "hidden"}`}
          {...tabPanelProps("abschnitt-material")}
        >
          {positionenInhalt}
        </div>
      )}

      <PartnerAbschnitt
        kannPartnerVerwalten={kannPartnerVerwalten}
        istAktiverTab={istAktiverTab}
        tabPanelProps={tabPanelProps}
        vorgang={vorgang}
        setShowPartnerForm={setShowPartnerForm}
        showPartnerForm={showPartnerForm}
        partnerWarnung={partnerWarnung}
        navigate={navigate}
        zugewiesenerPartner={zugewiesenerPartner}
        partnerAufhebenMutation={partnerAufhebenMutation}
        partnerAuswahl={partnerAuswahl}
        setPartnerAuswahl={setPartnerAuswahl}
        partnerListe={partnerListe}
        partnerHonorar={partnerHonorar}
        setPartnerHonorar={setPartnerHonorar}
        partnerZuweisenMutation={partnerZuweisenMutation}
      />
    </>
  );

  const verlaufAbschnittDiv = layout === "dicht" && (
    <div
      id="abschnitt-verlauf"
      className={verlaufSpalteBreit || istAktiverTab("abschnitt-verlauf") ? "" : "hidden"}
      {...tabPanelProps("abschnitt-verlauf")}
    >
      {verlaufInhalt}
    </div>
  );

  if (ansicht === "zeit" && layout !== "dicht") {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(`/vorgaenge/${id}`)} className="text-sm text-label2">
          ← Zurück zum Vorgang
        </button>
        <div className="card-ap p-3">
          <div className="text-xs text-label2">{vorgang.vorgangsnummer}</div>
          <h1 className="font-heading text-base font-semibold text-label">{vorgang.titel}</h1>
          {kunde && <p className="mt-0.5 text-xs text-label2">{kunde.name}</p>}
        </div>
        <div className="card-ap p-3">{arbeitszeitInhalt}</div>

        {zeitSheetModus && (
          <ZeiteintragSheet
            offen
            onClose={() => setZeitSheetModus(null)}
            vorgangId={id!}
            eintrag={zeitSheetModus === "neu" ? null : zeitSheetModus}
            onGespeichert={() => setZeitSheetModus(null)}
          />
        )}

        <Sheet
          offen={!!nachStoppenEintrag}
          onClose={() => setNachStoppenEintrag(null)}
          titel="Was hast du gemacht?"
          links={
            <button type="button" onClick={() => setNachStoppenEintrag(null)} className="text-[17px] text-tint">
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

  if (ansicht === "verlauf" && layout !== "dicht") {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(`/vorgaenge/${id}`)} className="text-sm text-label2">
          ← Zurück zum Vorgang
        </button>
        <div className="card-ap p-3">
          <div className="text-xs text-label2">{vorgang.vorgangsnummer}</div>
          <h1 className="font-heading text-base font-semibold text-label">{vorgang.titel}</h1>
          {kunde && <p className="mt-0.5 text-xs text-label2">{kunde.name}</p>}
        </div>
        <div className="card-ap p-3">{verlaufInhalt}</div>
      </div>
    );
  }

  if (ansicht === "positionen" && layout !== "dicht") {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(`/vorgaenge/${id}`)} className="text-sm text-label2">
          ← Zurück zum Vorgang
        </button>
        <div className="card-ap p-3">
          <div className="text-xs text-label2">{vorgang.vorgangsnummer}</div>
          <h1 className="font-heading text-base font-semibold text-label">{vorgang.titel}</h1>
          {kunde && <p className="mt-0.5 text-xs text-label2">{kunde.name}</p>}
        </div>
        <div className="card-ap p-3">{positionenInhalt}</div>
      </div>
    );
  }

  return (
    <div className={`space-y-4 ${layout !== "dicht" && primaerAktion ? "pb-20" : ""}`}>
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        {kannLoeschen && (
          <PulldownMenu
            ariaLabel="Weitere Aktionen"
            items={[
              {
                label: "Vorgang löschen",
                icon: Trash2,
                destruktiv: true,
                onSelect: async () => {
                  if (await bestaetigen({ titel: "Vorgang löschen?", text: "Verknüpfte Daten wandern in den Papierkorb.", bestaetigenLabel: "Löschen" })) {
                    deleteVorgangMutation.mutate();
                  }
                },
              },
            ]}
            trigger={({ offen, toggeln, triggerRef }) => (
              <button
                ref={triggerRef}
                type="button"
                onClick={toggeln}
                aria-haspopup="menu"
                aria-expanded={offen}
                aria-label="Weitere Aktionen"
                disabled={deleteVorgangMutation.isPending}
                className="btn-touch flex items-center justify-center text-label2 disabled:opacity-50"
              >
                <MoreHorizontal size={20} strokeWidth={2} aria-hidden="true" />
              </button>
            )}
          />
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
                vorgang.faelligkeit_am.slice(0, 10) < heuteIso() &&
                !VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status)
                  ? "border-st-fehlt text-st-fehlt"
                  : "border-sep text-label"
              }`}
            >
              <Clock size={13} strokeWidth={1.5} />
              {vorgang.faelligkeit_am.slice(0, 10) < heuteIso() &&
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
          {ANCHOR_ABSCHNITTE
            // Verlauf ist im "breit"-Layout keine umschaltbare Tab-Seite
            // mehr, sondern eine staendig sichtbare zweite Spalte (siehe
            // verlaufSpalteBreit/dichtLinkeSpalteInhalt) -- als Tab-Pille
            // wuerde er nur verwirren, weil ein Klick nichts umschaltet.
            .filter((a) => !(verlaufSpalteBreit && a.ziel === "abschnitt-verlauf"))
            .map((a) => (
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
        <nav aria-label="Vorgangs-Abschnitte" className="scrollbar-none -mx-3 flex gap-4 overflow-x-auto border-b border-sep px-3 text-sm [mask-image:linear-gradient(to_right,black_calc(100%-28px),transparent)]">
          {ANCHOR_ABSCHNITTE.map((a) => {
            // Abschnitte mit eigener Unterseite (siehe arbeitszeitInhalt/
            // verlaufInhalt oben) navigieren dorthin statt zum Anker zu
            // springen -- alle anderen bleiben Sprungmarken auf der
            // durchlaufenden Seite.
            const eigeneSeite = ABSCHNITT_ROUTE[a.ziel];
            return eigeneSeite ? (
              <button
                key={a.ziel}
                type="button"
                onClick={() => navigate(`/vorgaenge/${id}/${eigeneSeite}`)}
                className="inline-flex min-h-11 shrink-0 items-center whitespace-nowrap font-medium text-label2 hover:text-label"
              >
                {a.label}
              </button>
            ) : (
              <a
                key={a.ziel}
                href={`#${a.ziel}`}
                className="inline-flex min-h-11 shrink-0 items-center whitespace-nowrap font-medium text-label2 hover:text-label"
              >
                {a.label}
              </a>
            );
          })}
        </nav>
      )}

      {/* Kurzuebersicht: bisher Teil des Uebersicht-Tabs (nur dort sichtbar),
       * jetzt tab-uebergreifend oben angeheftet -- Status/Prioritaet/
       * Zustaendigkeit bleiben so auch auf Zeit/Termine/Maengel/Positionen/
       * Verlauf im Blick, ohne dafuer zurueck zu tabben. */}
      {layout === "dicht" && (
        <div className="card-ap mb-3 space-y-2.5 p-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm lg:grid-cols-4">
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
              <div key={label} className="flex items-baseline justify-between gap-2 lg:flex-col lg:items-start lg:gap-0.5">
                <dt className="text-xs text-label2">{label}</dt>
                <dd className="text-right font-medium text-label lg:text-left">{wert}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* Kennzahlen-Zeile: auf einen Blick, ob in den anderen Abschnitten
       * ueberhaupt etwas wartet, statt jeden einzeln aufklappen zu muessen
       * -- Zeit/Positionen/Verlauf verlinken zur eigenen Unterseite,
       * Termine/Maengel springen zum Abschnitt weiter unten. Nur im
       * "kompakt"-Layout auf der Hauptseite (die eigenen Unterseiten
       * brauchen sie nicht, "dicht" hat dafuer die echten Tabs). */}
      {layout !== "dicht" && ansicht === "voll" && (
        <div className="scrollbar-none -mx-3 flex gap-2 overflow-x-auto px-3 pb-1">
          <button
            type="button"
            onClick={() => navigate(`/vorgaenge/${id}/zeit`)}
            className="btn-touch flex shrink-0 flex-col items-start gap-0.5 border border-sep px-3 py-2 text-left hover:bg-fill"
          >
            <span className="text-[11px] text-label2">Zeit</span>
            <span className="text-sm font-semibold text-label">
              {gesamtStunden} Std.{gesamtKm > 0 && ` · ${gesamtKm.toFixed(1)} km`}
            </span>
          </button>
          <a
            href="#abschnitt-termine"
            className="btn-touch flex shrink-0 flex-col items-start gap-0.5 border border-sep px-3 py-2 text-left hover:bg-fill"
          >
            <span className="text-[11px] text-label2">Nächster Termin</span>
            <span className="text-sm font-semibold text-label">
              {naechsterTermin
                ? new Date(naechsterTermin.start_at).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })
                : "—"}
            </span>
          </a>
          <a
            href="#abschnitt-maengel"
            className="btn-touch flex shrink-0 flex-col items-start gap-0.5 border border-sep px-3 py-2 text-left hover:bg-fill"
          >
            <span className="text-[11px] text-label2">Mängel</span>
            <span className={`text-sm font-semibold ${offeneMaengelAnzahl > 0 ? "text-st-fehlt" : "text-label"}`}>
              {offeneMaengelAnzahl} offen
            </span>
          </a>
          <button
            type="button"
            onClick={() => navigate(`/vorgaenge/${id}/positionen`)}
            className="btn-touch flex shrink-0 flex-col items-start gap-0.5 border border-sep px-3 py-2 text-left hover:bg-fill"
          >
            <span className="text-[11px] text-label2">Positionen</span>
            <span className="text-sm font-semibold text-label">{positionenAnzahl}</span>
          </button>
          <button
            type="button"
            onClick={() => navigate(`/vorgaenge/${id}/verlauf`)}
            className="btn-touch flex shrink-0 flex-col items-start gap-0.5 border border-sep px-3 py-2 text-left hover:bg-fill"
          >
            <span className="text-[11px] text-label2">Verlauf</span>
            <span className="text-sm font-semibold text-label">{verlaufEintraege.length} Einträge</span>
          </button>
        </div>
      )}

      {verlaufSpalteBreit ? (
        <div className="flex items-start gap-4">
          <div className="min-w-0 flex-1 space-y-4">{dichtLinkeSpalteInhalt}</div>
          <div className="w-[380px] shrink-0">{verlaufAbschnittDiv}</div>
        </div>
      ) : (
        <>
          {dichtLinkeSpalteInhalt}
          {verlaufAbschnittDiv}
        </>
      )}

      {zeitSheetModus && (
        <ZeiteintragSheet
          offen
          onClose={() => setZeitSheetModus(null)}
          vorgangId={id!}
          eintrag={zeitSheetModus === "neu" ? null : zeitSheetModus}
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

      {layout !== "dicht" && ansicht === "voll" && primaerAktion && (
        <div className="fixed inset-x-0 z-30 flex justify-center px-3" style={{ bottom: "var(--klebe-abstand)" }}>
          <button
            type="button"
            onClick={primaerAktion.onClick}
            disabled={primaerAktion.disabled}
            className="btn-touch btn-ap-primary w-full max-w-md disabled:opacity-50"
          >
            {primaerAktion.label}
          </button>
        </div>
      )}
    </div>
  );
}
