import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCircle2, Clock, Inbox, List, Map as MapIcon, MessageCircle, Play, Repeat, Search, Star, UserPlus, X } from "lucide-react";
import { Suspense, lazy, useCallback, useState } from "react";
import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";

import { kundenApi, storiesApi, vorgaengeApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FilterVorlagenLeiste } from "../../components/FilterVorlagenLeiste";
import type { FeedMapPunkt } from "../../components/MapboxFeedMap";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { useAlleSeitenLaden, useVorgangsListe } from "../../hooks/useVorgangsListe";
import { istModulAktiv } from "../../utils/module";
import type { FeedCard, Kunde, StoryItem, VorgangStatus } from "../../types";

// Lazy statt statisch importiert: mapbox-gl allein ist ~1.8 MB und soll nur
// geladen werden, wenn die Kartenansicht tatsaechlich geoeffnet wird (siehe
// gleiche Begruendung bei MapboxMap.tsx in der Vorgang-Detailseite).
const MapboxFeedMap = lazy(() =>
  import("../../components/MapboxFeedMap").then((m) => ({ default: m.MapboxFeedMap })),
);

const STATUS_HEX: Record<VorgangStatus, string> = {
  neu: "#3b82f6",
  geplant: "#a855f7",
  in_arbeit: "#f59e0b",
  wartet_kunde: "#f97316",
  abgeschlossen: "#22c55e",
  abgerechnet: "#64748b",
  storniert: "#94a3b8",
};

// Etwas heller/weniger gesaettigt als STATUS_HEX -- dient als ausfadender
// Rahmen um die Feed-Karte (.card-soft), nicht als vollflaechige Farbe wie
// bei den Kartenpins, siehe Design-Vorschlag.
const STATUS_FRAME: Record<VorgangStatus, string> = {
  neu: "#60a5fa",
  geplant: "#c084fc",
  in_arbeit: "#fbbf24",
  wartet_kunde: "#fb923c",
  abgeschlossen: "#4ade80",
  abgerechnet: "#94a3b8",
  storniert: "#cbd5e1",
};

const LEISTUNGSTYP_LABEL: Record<string, string> = {
  installation: "Installation",
  pruefung: "Prüfung",
  wartung: "Wartung",
  stoerung: "Störung",
  beratung: "Beratung",
  planung: "Planung",
};

function heuteIso(offsetTage = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetTage);
  return d.toISOString().slice(0, 10);
}

const STATUS_LABEL: Record<VorgangStatus, string> = {
  neu: "Neu",
  geplant: "Geplant",
  in_arbeit: "In Arbeit",
  wartet_kunde: "Wartet auf Kunde",
  abgeschlossen: "Abgeschlossen",
  abgerechnet: "Abgerechnet",
  storniert: "Storniert",
};

const STATUS_BADGE: Record<VorgangStatus, string> = {
  neu: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300",
  geplant: "bg-purple-100 text-purple-800 dark:bg-purple-500/15 dark:text-purple-300",
  in_arbeit: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  wartet_kunde: "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300",
  abgeschlossen: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300",
  abgerechnet: "bg-slate-200 text-slate-700 dark:bg-stone-700 dark:text-stone-300",
  storniert: "bg-slate-100 text-slate-400 dark:bg-stone-800 dark:text-stone-500",
};

const AMPEL_COLOR: Record<string, string> = {
  gruen: "border-green-500",
  gelb: "border-amber-500",
  rot: "border-red-500",
};

const STORY_ZIEL_PFAD: Record<StoryItem["ziel_typ"], (id: string) => string> = {
  vorgang: (id) => `/vorgaenge/${id}`,
  anlage: (id) => `/anlagen/${id}`,
  // Pruefmittel hat keine eigene Detailseite -- die Verwaltungsliste ist
  // das naechstbeste Ziel (besser als eine falsche ID in eine fremde
  // Detailroute zu stecken).
  pruefmittel: () => "/pruefmittel",
};

function StoryChip({ item }: { item: StoryItem }) {
  const navigate = useNavigate();
  const path = STORY_ZIEL_PFAD[item.ziel_typ](item.ziel_id);
  return (
    <button
      onClick={() => navigate(path)}
      className={`card-interactive btn-touch flex w-40 shrink-0 flex-col items-start rounded-lg border-l-4 bg-white p-3 text-left shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800 ${
        item.ampel ? AMPEL_COLOR[item.ampel] : "border-slate-300 dark:border-stone-600"
      }`}
    >
      <span className="line-clamp-2 text-sm font-semibold text-slate-800 dark:text-stone-100">
        {item.titel}
      </span>
      {item.subtitel && (
        <span className="mt-1 text-xs text-slate-500 dark:text-stone-400">{item.subtitel}</span>
      )}
    </button>
  );
}

function faelligkeitsFarbe(iso: string): string {
  const heute = heuteIso();
  if (iso < heute) return "text-red-600 dark:text-red-400";
  if (iso <= heuteIso(3)) return "text-amber-600 dark:text-amber-400";
  return "text-slate-500 dark:text-stone-400";
}

type FaelligkeitsGruppe = "ueberfaellig" | "heute" | "diese_woche" | "ohne_frist";

const GRUPPEN_LABEL: Record<FaelligkeitsGruppe, string> = {
  ueberfaellig: "Überfällig",
  heute: "Heute fällig",
  diese_woche: "Diese Woche",
  ohne_frist: "Ohne Frist",
};

const GRUPPEN_REIHENFOLGE: FaelligkeitsGruppe[] = ["ueberfaellig", "heute", "diese_woche", "ohne_frist"];

function faelligkeitsGruppe(card: FeedCard): FaelligkeitsGruppe {
  const iso = card.faelligkeit_am?.slice(0, 10);
  if (!iso) return "ohne_frist";
  const heute = heuteIso();
  if (iso < heute) return "ueberfaellig";
  if (iso === heute) return "heute";
  return "diese_woche";
}

// "3 Tage überfällig" statt reinem Datum -- auf einen Blick erfassbar ohne
// Kopfrechnen (siehe Design-Vorschlag "Feed neu gedacht").
function tageUeberfaellig(iso: string): number {
  const heute = new Date(heuteIso());
  const faellig = new Date(iso);
  return Math.round((heute.getTime() - faellig.getTime()) / (1000 * 60 * 60 * 24));
}

// Karten nach Faelligkeit gruppieren, damit man beim Durchscrollen sofort
// sieht, was zuerst dran ist, statt jede Karte einzeln nach Datum abzusuchen
// (siehe Design-Vorschlag "Feed neu gedacht"). Reihenfolge innerhalb einer
// Gruppe bleibt wie vom Server sortiert (Aktivitaet/Prioritaet).
function gruppiereNachFaelligkeit(cards: FeedCard[]): { gruppe: FaelligkeitsGruppe; cards: FeedCard[] }[] {
  const buckets = new Map<FaelligkeitsGruppe, FeedCard[]>();
  for (const card of cards) {
    const gruppe = faelligkeitsGruppe(card);
    (buckets.get(gruppe) ?? buckets.set(gruppe, []).get(gruppe)!).push(card);
  }
  return GRUPPEN_REIHENFOLGE.filter((g) => buckets.has(g)).map((gruppe) => ({ gruppe, cards: buckets.get(gruppe)! }));
}

const OFFENE_STATUS: VorgangStatus[] = ["neu", "geplant"];

function FeedCardView({ card }: { card: FeedCard }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const faelligkeitIso = card.faelligkeit_am?.slice(0, 10);

  const invalidateFeed = () => queryClient.invalidateQueries({ queryKey: ["feed"] });
  const zuweisenMutation = useMutation({
    mutationFn: () => vorgaengeApi.uebernehmen(card.id),
    onSuccess: invalidateFeed,
  });
  const statusMutation = useMutation({
    mutationFn: (status: VorgangStatus) => vorgaengeApi.update(card.id, { status }),
    onSuccess: invalidateFeed,
  });

  // Genau eine Schnellaktion pro Karte -- der naechste sinnvolle Schritt im
  // Ablauf Uebernehmen -> Starten -> Fertig melden, statt aller theoretisch
  // moeglichen Optionen auf einmal (siehe Design-Vorschlag). "Starten" nur
  // bei bereits zugewiesenen Karten -- ein noch niemandem zugewiesener
  // Vorgang soll erst uebernommen werden, bevor jemand "startet".
  const zeigeUebernehmen = !card.zugewiesener_name && OFFENE_STATUS.includes(card.status);
  const zeigeStarten = !!card.zugewiesener_name && OFFENE_STATUS.includes(card.status);
  const zeigeFertigMelden = card.status === "in_arbeit";
  const zeigeNachfragen = card.status === "wartet_kunde";
  const aktionLaeuft = zuweisenMutation.isPending || statusMutation.isPending;
  const aktionFehler = zuweisenMutation.isError || statusMutation.isError;

  return (
    <div
      className={`card-soft ${card.status === "storniert" ? "opacity-60 grayscale" : ""}`}
      style={{ "--frame-color": STATUS_FRAME[card.status] } as CSSProperties}
    >
    <div className="card-soft-inner overflow-hidden bg-white dark:bg-stone-900">
    <button
      onClick={() => navigate(`/vorgaenge/${card.id}`)}
      className="btn-touch flex w-full flex-col gap-2 p-4 text-left"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs text-slate-400 dark:text-stone-500">{card.vorgangsnummer}</div>
          <div className="font-semibold text-slate-800 dark:text-stone-100">{card.titel}</div>
          <div className="text-sm text-slate-500 dark:text-stone-400">{card.kunde_name}</div>
          {(card.anlage_bezeichnung || card.standort_bezeichnung) && (
            <div className="text-xs text-slate-400 dark:text-stone-500">
              {[card.anlage_bezeichnung, card.standort_bezeichnung].filter(Boolean).join(" · ")}
            </div>
          )}
          {card.anlage_kurzadresse && (
            <div className="text-xs text-slate-400 dark:text-stone-500">{card.anlage_kurzadresse}</div>
          )}
          {card.ersteller_name && (
            <div className="text-xs text-slate-400 dark:text-stone-500">von {card.ersteller_name}</div>
          )}
          {!["abgeschlossen", "abgerechnet", "storniert"].includes(card.status) && (
            <div className="text-xs text-slate-400 dark:text-stone-500">
              {card.zugewiesener_name ? `Zugewiesen: ${card.zugewiesener_name}` : "Nicht zugewiesen"}
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          {card.timer_laeuft && (
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" title="Timer läuft" />
          )}
          {card.dauerauftrag_id && (
            <span title="Dauerauftrag" className="text-amber-500">
              <Repeat size={14} strokeWidth={2} />
            </span>
          )}
          <span className={`whitespace-nowrap rounded-full px-2 py-1 text-xs font-semibold ${STATUS_BADGE[card.status]}`}>
            {STATUS_LABEL[card.status]}
          </span>
          <span className="whitespace-nowrap text-xs text-slate-400 dark:text-stone-500">
            {LEISTUNGSTYP_LABEL[card.leistungstyp] ?? card.leistungstyp}
          </span>
        </div>
      </div>
      {card.status === "wartet_kunde" ? (
        <span className="flex items-center gap-1 text-xs text-slate-400 dark:text-stone-500">
          <MessageCircle size={13} strokeWidth={2} /> Wartet auf Rückmeldung
        </span>
      ) : (
        faelligkeitIso && (
          <span className={`flex items-center gap-1 text-xs font-medium ${faelligkeitsFarbe(faelligkeitIso)}`}>
            {faelligkeitIso < heuteIso() ? (
              <>
                <Clock size={13} strokeWidth={2} /> {tageUeberfaellig(faelligkeitIso)}{" "}
                {tageUeberfaellig(faelligkeitIso) === 1 ? "Tag" : "Tage"} überfällig
              </>
            ) : (
              <>Fällig: {new Date(faelligkeitIso).toLocaleDateString("de-DE")}</>
            )}
          </span>
        )
      )}
      {card.letztes_event_vorschau && (
        <p className="line-clamp-2 rounded-md bg-slate-50 px-2 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300">
          {card.letztes_event_vorschau}
        </p>
      )}
      {card.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {card.tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            >
              #{tag}
            </span>
          ))}
        </div>
      )}
    </button>
    {(zeigeUebernehmen || zeigeStarten || zeigeFertigMelden || zeigeNachfragen) && (
      <div className="flex items-center justify-end gap-1.5 border-t border-slate-100 px-4 py-2 dark:border-stone-800">
        {aktionFehler && (
          <span className="mr-auto text-xs text-red-600 dark:text-red-400">Aktion fehlgeschlagen</span>
        )}
        {zeigeUebernehmen && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              zuweisenMutation.mutate();
            }}
            disabled={aktionLaeuft}
            className="btn-touch flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            <UserPlus size={13} strokeWidth={2} /> Übernehmen
          </button>
        )}
        {zeigeStarten && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              statusMutation.mutate("in_arbeit");
            }}
            disabled={aktionLaeuft}
            className="btn-touch flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800 disabled:opacity-50 dark:bg-amber-500/15 dark:text-amber-300"
          >
            <Play size={13} strokeWidth={2} /> Starten
          </button>
        )}
        {zeigeFertigMelden && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              statusMutation.mutate("abgeschlossen");
            }}
            disabled={aktionLaeuft}
            className="btn-touch flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-1 text-xs font-medium text-green-800 disabled:opacity-50 dark:bg-green-500/15 dark:text-green-300"
          >
            <CheckCircle2 size={13} strokeWidth={2} /> Fertig melden
          </button>
        )}
        {zeigeNachfragen && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/vorgaenge/${card.id}#email`);
            }}
            className="btn-touch flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
          >
            <Bell size={13} strokeWidth={2} /> Nachfragen
          </button>
        )}
      </div>
    )}
    </div>
    </div>
  );
}

// Lesbare Kurzform je aktivem Filter-Schluessel fuer die Chip-Zusammenfassung
// -- ein unbekannter Schluessel faellt auf "Schluessel: Wert" zurueck statt
// zu verschwinden, damit ein spaeter ergaenzter Filter nie stillschweigend
// ohne Chip bleibt.
function filterChipLabel(key: string, value: string, kunden: Kunde[] | undefined): string {
  switch (key) {
    case "status":
      return `Status: ${value
        .split(",")
        .map((s) => STATUS_LABEL[s as VorgangStatus] ?? s)
        .join(", ")}`;
    case "kunde_id":
      return `Kunde: ${kunden?.find((k) => k.id === value)?.name ?? value}`;
    case "leistungstyp":
      return `Typ: ${LEISTUNGSTYP_LABEL[value] ?? value}`;
    case "faellig_von":
      return `Fällig ab ${new Date(value).toLocaleDateString("de-DE")}`;
    case "faellig_bis":
      return `Fällig bis ${new Date(value).toLocaleDateString("de-DE")}`;
    case "tag":
      return `#${value}`;
    case "sort":
      return `Sortierung: ${value === "prioritaet" ? "Priorität" : "Aktivität"}`;
    default:
      return `${key}: ${value}`;
  }
}

const LEER_FILTER: Record<string, string> = {};

export function FeedPage() {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const [filter, setFilter] = useState<Record<string, string>>(LEER_FILTER);
  const [zeigeFilter, setZeigeFilter] = useState(false);
  const [ansicht, setAnsicht] = useState<"liste" | "karte">("liste");

  const { data: stories } = useQuery({ queryKey: ["stories"], queryFn: storiesApi.get });
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });

  function setField(key: string, value: string) {
    setFilter((f) => {
      const next = { ...f };
      if (value) next[key] = value;
      else delete next[key];
      return next;
    });
  }

  const aktiveStatus = (filter.status ?? "").split(",").filter(Boolean);
  function toggleStatus(status: string) {
    const set = new Set(aktiveStatus);
    if (set.has(status)) set.delete(status);
    else set.add(status);
    setField("status", Array.from(set).join(","));
  }

  const anwendenFilter = useCallback((neu: Record<string, string>) => setFilter(neu), []);

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } =
    useVorgangsListe(filter);

  // Die Liste zeigt bewusst nur Seite fuer Seite ("Mehr laden"), aber die
  // Kartenansicht braucht alle zum aktuellen Filter passenden Vorgaenge auf
  // einmal, sonst wuerden Pins fehlen, die einfach noch nicht nachgeladen
  // wurden.
  useAlleSeitenLaden(ansicht === "karte", hasNextPage, fetchNextPage);

  const storyGroups = stories
    ? [...stories.wartet_kunde, ...stories.heute, ...stories.fristen]
    : [];
  const cards = data?.pages.flatMap((p) => p.items) ?? [];
  // "nur_meine" hat mit den Tabs oben eine eigene, immer sichtbare Steuerung
  // -- soll den Filter-Zaehler des Filter-Panels darunter nicht mitzaehlen.
  const aktiveFilterAnzahl = Object.keys(filter).filter((k) => k !== "nur_meine").length;
  const nurMeine = filter.nur_meine === "true";
  // Kompakte Chip-Zusammenfassung der aktiven Filter -- ersetzt das immer
  // sichtbare volle Formular durch eine schmale Leiste, die nur erscheint,
  // wenn tatsaechlich etwas aktiv ist (siehe Design-Vorschlag "Filterleiste
  // Varianten", Richtung B).
  const filterChips = Object.entries(filter)
    .filter(([key, value]) => key !== "nur_meine" && value)
    .map(([key, value]) => ({ key, label: filterChipLabel(key, value, kunden) }));
  const punkte: FeedMapPunkt[] = cards
    .filter((c) => c.geo_lat != null && c.geo_lng != null)
    .map((c) => ({ id: c.id, lng: c.geo_lng as number, lat: c.geo_lat as number, farbe: STATUS_HEX[c.status] }));
  const ohneKoordinatenAnzahl = cards.length - punkte.length;

  return (
    <div className="space-y-4">
      {istModulAktiv(currentUser, "highlights") && (
        <button
          onClick={() => navigate("/highlights")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-amber-700 shadow-xs dark:bg-stone-900 dark:text-amber-400 dark:shadow-none dark:ring-1 dark:ring-stone-800"
        >
          <Star size={15} strokeWidth={2} /> Highlights ansehen
        </button>
      )}

      <div className="flex gap-1 rounded-lg bg-white p-1 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <button
          onClick={() => setField("nur_meine", "true")}
          className={`btn-touch flex-1 rounded-md py-2 text-sm font-semibold ${
            nurMeine
              ? "bg-slate-100 text-slate-800 dark:bg-stone-800 dark:text-stone-100"
              : "text-slate-500 dark:text-stone-400"
          }`}
        >
          Meine Vorgänge
        </button>
        <button
          onClick={() => setField("nur_meine", "")}
          className={`btn-touch flex-1 rounded-md py-2 text-sm font-semibold ${
            !nurMeine
              ? "bg-slate-100 text-slate-800 dark:bg-stone-800 dark:text-stone-100"
              : "text-slate-500 dark:text-stone-400"
          }`}
        >
          Alle
        </button>
      </div>

      {storyGroups.length > 0 && (
        <div className="-mx-3 flex gap-2 overflow-x-auto px-3 pb-1">
          {storyGroups.map((item) => (
            <StoryChip key={`${item.ziel_typ}-${item.ziel_id}`} item={item} />
          ))}
        </div>
      )}

      {/* Filterleiste "Richtung B": Filter ist im Ruhezustand nur ein
          Icon-Button neben Liste/Karte, keine eigene Karte mehr -- die wird
          erst sichtbar, sobald tatsaechlich etwas aktiv ist oder das
          Formular explizit geoeffnet wird (siehe Design-Vorschlag
          "Filterleiste Varianten"). */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex gap-1.5">
          <button
            onClick={() => setField("faellig_bis", heuteIso())}
            className="btn-touch rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
          >
            Überfällig
          </button>
          <button
            onClick={() => setField("faellig_bis", heuteIso(7))}
            className="btn-touch rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
          >
            Diese Woche fällig
          </button>
        </div>
        <div className="flex shrink-0 gap-1">
          <button
            onClick={() => setZeigeFilter((v) => !v)}
            title="Filter"
            aria-label="Filter"
            className={`btn-touch relative flex h-8 w-8 items-center justify-center rounded-full ${
              zeigeFilter || aktiveFilterAnzahl > 0
                ? "btn-clay bg-linear-to-r from-cyan-500 to-blue-600 text-white"
                : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            }`}
          >
            <Search size={14} strokeWidth={2} />
            {aktiveFilterAnzahl > 0 && (
              <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white ring-2 ring-slate-100 dark:ring-stone-950">
                {aktiveFilterAnzahl}
              </span>
            )}
          </button>
          <button
            onClick={() => setAnsicht("liste")}
            className={`btn-touch flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${
              ansicht === "liste"
                ? "btn-clay bg-linear-to-r from-cyan-500 to-blue-600 text-white"
                : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            }`}
          >
            <List size={13} strokeWidth={2} /> Liste
          </button>
          <button
            onClick={() => setAnsicht("karte")}
            className={`btn-touch flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${
              ansicht === "karte"
                ? "btn-clay bg-linear-to-r from-cyan-500 to-blue-600 text-white"
                : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            }`}
          >
            <MapIcon size={13} strokeWidth={2} /> Karte
          </button>
        </div>
      </div>

      {filterChips.length > 0 && !zeigeFilter && (
        <div className="flex flex-wrap items-center gap-1.5 rounded-lg bg-white p-2.5 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          {filterChips.map((c) => (
            <span
              key={c.key}
              className="flex items-center gap-1.5 rounded-full bg-slate-100 py-1 pr-1.5 pl-2.5 text-xs font-medium text-slate-700 dark:bg-stone-800 dark:text-stone-200"
            >
              {c.label}
              <button
                onClick={() => setField(c.key, "")}
                aria-label={`${c.label} entfernen`}
                className="btn-touch flex h-4 w-4 items-center justify-center rounded-full bg-slate-200 text-slate-500 dark:bg-stone-700 dark:text-stone-400"
              >
                <X size={9} strokeWidth={3} />
              </button>
            </span>
          ))}
          <button
            onClick={() => setZeigeFilter(true)}
            className="btn-touch ml-auto text-xs font-semibold text-blue-700 dark:text-blue-400"
          >
            Bearbeiten
          </button>
        </div>
      )}

      {zeigeFilter && (
        <div className="space-y-2 rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <div>
            <div className="mb-1 text-xs font-medium text-slate-500 dark:text-stone-400">
              Status (Mehrfachauswahl möglich)
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(STATUS_LABEL).map(([value, label]) => {
                const aktiv = aktiveStatus.includes(value);
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => toggleStatus(value)}
                    className={`btn-touch rounded-full px-3 py-1.5 text-xs font-medium ${
                      aktiv
                        ? "btn-clay bg-linear-to-r from-cyan-500 to-blue-600 text-white"
                        : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <select
            value={filter.kunde_id ?? ""}
            onChange={(e) => setField("kunde_id", e.target.value)}
            className="btn-touch rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            <option value="">Alle Kunden</option>
            {(kunden ?? []).map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </select>
          <select
            value={filter.leistungstyp ?? ""}
            onChange={(e) => setField("leistungstyp", e.target.value)}
            className="btn-touch rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            <option value="">Alle Leistungstypen</option>
            {Object.entries(LEISTUNGSTYP_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <div className="col-span-2 flex items-center gap-2 sm:col-span-1">
            <input
              type="date"
              value={filter.faellig_von ?? ""}
              onChange={(e) => setField("faellig_von", e.target.value)}
              title="Fällig ab"
              className="btn-touch w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <span className="text-xs text-slate-400 dark:text-stone-500">bis</span>
            <input
              type="date"
              value={filter.faellig_bis ?? ""}
              onChange={(e) => setField("faellig_bis", e.target.value)}
              title="Fällig bis"
              className="btn-touch w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
          <input
            value={filter.tag ?? ""}
            onChange={(e) => setField("tag", e.target.value)}
            placeholder="#Tag"
            className="btn-touch rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
          <select
            value={filter.sort ?? "last_activity_at"}
            onChange={(e) => setField("sort", e.target.value)}
            className="btn-touch rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            <option value="last_activity_at">Sortiert nach Aktivität</option>
            <option value="prioritaet">Sortiert nach Priorität</option>
          </select>
          </div>
        </div>
      )}

      <FilterVorlagenLeiste entitaet="vorgaenge" filter={filter} onApply={anwendenFilter} />

      {ansicht === "karte" ? (
        isLoading ? (
          <div className="h-[65vh] w-full animate-pulse rounded-lg bg-slate-200 dark:bg-stone-700/60" />
        ) : punkte.length === 0 ? (
          <EmptyState icon={MapIcon} text="Keine Vorgänge mit Standort gefunden." />
        ) : (
          <>
            <Suspense
              fallback={<div className="h-[65vh] w-full animate-pulse rounded-lg bg-slate-200 dark:bg-stone-700/60" />}
            >
              <MapboxFeedMap
                punkte={punkte}
                onPunktClick={(id) => navigate(`/vorgaenge/${id}`)}
                className="h-[65vh] w-full rounded-lg"
              />
            </Suspense>
            {ohneKoordinatenAnzahl > 0 && (
              <p className="text-center text-xs text-slate-400 dark:text-stone-500">
                {ohneKoordinatenAnzahl} von {cards.length} Vorgängen ohne Standort nicht auf der Karte angezeigt.
              </p>
            )}
            {hasNextPage && (
              <p className="text-center text-xs text-slate-400 dark:text-stone-500">Lädt weitere Vorgänge…</p>
            )}
          </>
        )
      ) : (
        <>
          {isLoading ? (
            <SkeletonList count={4} />
          ) : cards.length === 0 ? (
            <EmptyState icon={Inbox} text="Keine Vorgänge gefunden." />
          ) : (
            <div className="space-y-5">
              {gruppiereNachFaelligkeit(cards).map(({ gruppe, cards: gruppenCards }) => (
                <div key={gruppe} className="space-y-3">
                  <div className="flex items-baseline gap-1.5 px-1">
                    <h3
                      className={`text-xs font-semibold tracking-wide uppercase ${
                        gruppe === "ueberfaellig"
                          ? "text-red-600 dark:text-red-400"
                          : gruppe === "heute"
                            ? "text-amber-600 dark:text-amber-400"
                            : "text-slate-400 dark:text-stone-500"
                      }`}
                    >
                      {GRUPPEN_LABEL[gruppe]}
                    </h3>
                    <span className="text-xs text-slate-300 dark:text-stone-600">{gruppenCards.length}</span>
                  </div>
                  <div className="space-y-3">
                    {gruppenCards.map((card) => (
                      <FeedCardView key={card.id} card={card} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {hasNextPage && (
            <button
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              className="btn-touch w-full rounded-md bg-white py-2 text-sm font-medium text-slate-600 shadow-xs disabled:opacity-50 dark:bg-stone-900 dark:text-stone-300 dark:shadow-none dark:ring-1 dark:ring-stone-800"
            >
              {isFetchingNextPage ? "Lädt…" : "Mehr laden"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
