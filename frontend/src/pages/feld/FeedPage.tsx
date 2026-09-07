import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCircle2, Clock, Filter, Inbox, List, Map as MapIcon, MessageCircle, Play, Repeat, Star, UserPlus, X } from "lucide-react";
import { Suspense, lazy, useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { kundenApi, storiesApi, vorgaengeApi } from "../../api/endpoints";
import Blueprint from "../../components/Blueprint";
import { EmptyState } from "../../components/EmptyState";
import { FilterVorlagenLeiste } from "../../components/FilterVorlagenLeiste";
import type { FeedMapPunkt } from "../../components/MapboxFeedMap";
import { SkeletonList } from "../../components/Skeleton";
import { GRUPPEN_LABEL, filterChipLabel, gruppiereNachFaelligkeit } from "../../config/vorgangDarstellung";
import { useAuth } from "../../context/AuthContext";
import { useAlleSeitenLaden, useVorgangsListe } from "../../hooks/useVorgangsListe";
import { istModulAktiv } from "../../utils/module";
import type { FeedCard, StoryItem, VorgangStatus } from "../../types";

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

// "Industry"-Design (siehe docs/DESIGN.md): Status-Tag als Haarlinien-
// Rahmen statt gefuellter Pastell-Pille (Rezept aus dem Feed-Mockup) --
// dieselben Semantik-Farben wie zuvor (siehe fieldvibe-design-Skill §8),
// nur Fuellung durch Rahmen+Text ersetzt.
const STATUS_BORDER: Record<VorgangStatus, string> = {
  neu: "border-blue-400 text-blue-700 dark:border-blue-600 dark:text-blue-300",
  geplant: "border-purple-400 text-purple-700 dark:border-purple-600 dark:text-purple-300",
  in_arbeit: "border-amber-400 text-amber-700 dark:border-amber-600 dark:text-amber-300",
  wartet_kunde: "border-orange-400 text-orange-700 dark:border-orange-600 dark:text-orange-300",
  abgeschlossen: "border-green-400 text-green-700 dark:border-green-600 dark:text-green-300",
  abgerechnet: "border-slate-400 text-slate-600 dark:border-stone-600 dark:text-stone-300",
  storniert: "border-slate-300 text-slate-400 dark:border-stone-700 dark:text-stone-500",
};

const AMPEL_COLOR: Record<string, string> = {
  gruen: "border-l-green-500",
  gelb: "border-l-amber-500",
  rot: "border-l-red-500",
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
    <button onClick={() => navigate(path)} className="btn-touch w-[120px] shrink-0 text-left">
      <Blueprint
        className={`border-l-2 bg-ind-bg px-2.5 py-2.5 ${
          item.ampel ? AMPEL_COLOR[item.ampel] : "border-l-ind-line-2"
        }`}
      >
        <span className="line-clamp-2 text-xs font-semibold leading-tight text-ind-ink">
          {item.titel}
        </span>
        {item.subtitel && (
          <span className="mt-0.5 block text-[11px] text-ind-ink-3">{item.subtitel}</span>
        )}
      </Blueprint>
    </button>
  );
}

function faelligkeitsFarbe(iso: string): string {
  const heute = heuteIso();
  if (iso < heute) return "text-red-600 dark:text-red-400";
  if (iso <= heuteIso(3)) return "text-amber-600 dark:text-amber-400";
  return "text-ind-ink-3";
}

// "3 Tage überfällig" statt reinem Datum -- auf einen Blick erfassbar ohne
// Kopfrechnen (siehe Design-Vorschlag "Feed neu gedacht").
function tageUeberfaellig(iso: string): number {
  const heute = new Date(heuteIso());
  const faellig = new Date(iso);
  return Math.round((heute.getTime() - faellig.getTime()) / (1000 * 60 * 60 * 24));
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
    <Blueprint className={`bg-ind-bg ${card.status === "storniert" ? "opacity-60 grayscale" : ""}`}>
      <button
        onClick={() => navigate(`/vorgaenge/${card.id}`)}
        className="btn-touch flex w-full flex-col gap-2 p-3 text-left"
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-[10px] tracking-wide text-ind-ink-3">{card.vorgangsnummer}</div>
            <div className="mt-0.5 font-semibold text-ind-ink">{card.titel}</div>
            <div className="text-xs text-ind-ink-2">{card.kunde_name}</div>
            {(card.anlage_bezeichnung || card.standort_bezeichnung) && (
              <div className="text-xs text-ind-ink-3">
                {[card.anlage_bezeichnung, card.standort_bezeichnung].filter(Boolean).join(" · ")}
              </div>
            )}
            {card.anlage_kurzadresse && <div className="text-xs text-ind-ink-3">{card.anlage_kurzadresse}</div>}
            {card.ersteller_name && <div className="text-xs text-ind-ink-3">von {card.ersteller_name}</div>}
            {!["abgeschlossen", "abgerechnet", "storniert"].includes(card.status) && (
              <div className="text-xs text-ind-ink-3">
                {card.zugewiesener_name ? `Zugewiesen: ${card.zugewiesener_name}` : "Nicht zugewiesen"}
              </div>
            )}
          </div>
          <div className="flex flex-none flex-col items-end gap-1">
            {card.timer_laeuft && (
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" title="Timer läuft" />
            )}
            {card.dauerauftrag_id && (
              <span title="Dauerauftrag" className="text-ind-warn">
                <Repeat size={14} strokeWidth={1.5} />
              </span>
            )}
            <span
              className={`whitespace-nowrap border px-2 py-0.5 text-[10px] font-medium tracking-wide uppercase ${STATUS_BORDER[card.status]}`}
            >
              {STATUS_LABEL[card.status]}
            </span>
            <span className="whitespace-nowrap text-xs text-ind-ink-3">
              {LEISTUNGSTYP_LABEL[card.leistungstyp] ?? card.leistungstyp}
            </span>
          </div>
        </div>
        {card.status === "wartet_kunde" ? (
          <span className="flex items-center gap-1 text-xs text-ind-ink-3">
            <MessageCircle size={13} strokeWidth={1.5} /> Wartet auf Rückmeldung
          </span>
        ) : (
          faelligkeitIso && (
            <span className={`flex items-center gap-1 text-xs font-medium ${faelligkeitsFarbe(faelligkeitIso)}`}>
              {faelligkeitIso < heuteIso() ? (
                <>
                  <Clock size={13} strokeWidth={1.5} /> {tageUeberfaellig(faelligkeitIso)}{" "}
                  {tageUeberfaellig(faelligkeitIso) === 1 ? "Tag" : "Tage"} überfällig
                </>
              ) : (
                <>Fällig: {new Date(faelligkeitIso).toLocaleDateString("de-DE")}</>
              )}
            </span>
          )
        )}
        {card.letztes_event_vorschau && (
          <p className="line-clamp-2 border border-ind-line-2 px-2 py-1.5 text-sm text-ind-ink-2">
            {card.letztes_event_vorschau}
          </p>
        )}
        {card.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {card.tags.map((tag) => (
              <span key={tag} className="border border-ind-line px-2 py-0.5 text-xs text-ind-ink-3">
                #{tag}
              </span>
            ))}
          </div>
        )}
      </button>
      {(zeigeUebernehmen || zeigeStarten || zeigeFertigMelden || zeigeNachfragen) && (
        <div className="flex items-center justify-end gap-1.5 border-t border-ind-line px-3 py-2">
          {aktionFehler && <span className="mr-auto text-xs text-red-600 dark:text-red-400">Aktion fehlgeschlagen</span>}
          {zeigeUebernehmen && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                zuweisenMutation.mutate();
              }}
              disabled={aktionLaeuft}
              className="btn-touch flex items-center gap-1.5 border border-ind-line-2 px-2.5 py-1 text-xs font-medium text-ind-ink hover:bg-ind-hover disabled:opacity-50"
            >
              <UserPlus size={13} strokeWidth={1.5} /> Übernehmen
            </button>
          )}
          {zeigeStarten && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                statusMutation.mutate("in_arbeit");
              }}
              disabled={aktionLaeuft}
              className="btn-touch flex items-center gap-1.5 border border-ind-line-2 px-2.5 py-1 text-xs font-medium text-ind-ink hover:bg-ind-hover disabled:opacity-50"
            >
              <Play size={13} strokeWidth={1.5} /> Starten
            </button>
          )}
          {zeigeFertigMelden && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                statusMutation.mutate("abgeschlossen");
              }}
              disabled={aktionLaeuft}
              className="btn-touch flex items-center gap-1.5 border border-ind-line-2 px-2.5 py-1 text-xs font-medium text-ind-ink hover:bg-ind-hover disabled:opacity-50"
            >
              <CheckCircle2 size={13} strokeWidth={1.5} /> Fertig melden
            </button>
          )}
          {zeigeNachfragen && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                navigate(`/vorgaenge/${card.id}#email`);
              }}
              className="btn-touch flex items-center gap-1.5 border border-ind-line-2 px-2.5 py-1 text-xs font-medium text-ind-ink hover:bg-ind-hover"
            >
              <Bell size={13} strokeWidth={1.5} /> Nachfragen
            </button>
          )}
        </div>
      )}
    </Blueprint>
  );
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
          className="btn-touch flex w-full items-center justify-center gap-2 border border-ind-line py-2.5 text-sm font-medium text-ind-warn hover:bg-ind-hover"
        >
          <Star size={15} strokeWidth={1.5} /> Highlights ansehen
        </button>
      )}

      <div className="flex border border-ind-line">
        <button
          onClick={() => setField("nur_meine", "true")}
          className={`btn-touch flex-1 py-2 text-sm font-semibold ${
            nurMeine ? "bg-ind-field text-ind-field-ink" : "text-ind-ink-2 hover:bg-ind-hover"
          }`}
        >
          Meine Vorgänge
        </button>
        <button
          onClick={() => setField("nur_meine", "")}
          className={`btn-touch flex-1 border-l border-ind-line py-2 text-sm font-semibold ${
            !nurMeine ? "bg-ind-field text-ind-field-ink" : "text-ind-ink-2 hover:bg-ind-hover"
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
            className="btn-touch border border-ind-line px-2.5 py-1 text-xs font-medium text-ind-ink-2 hover:bg-ind-hover"
          >
            Überfällig
          </button>
          <button
            onClick={() => setField("faellig_bis", heuteIso(7))}
            className="btn-touch border border-ind-line px-2.5 py-1 text-xs font-medium text-ind-ink-2 hover:bg-ind-hover"
          >
            Diese Woche fällig
          </button>
        </div>
        <div className="flex shrink-0 border border-ind-line">
          <button
            onClick={() => setZeigeFilter((v) => !v)}
            title="Filter"
            aria-label="Filter"
            className={`btn-touch relative flex h-8 w-8 items-center justify-center ${
              zeigeFilter || aktiveFilterAnzahl > 0
                ? "bg-ind-field text-ind-field-ink"
                : "text-ind-ink-2 hover:bg-ind-hover"
            }`}
          >
            <Filter size={14} strokeWidth={1.5} />
            {aktiveFilterAnzahl > 0 && (
              <span className="absolute -top-1.5 -right-1.5 flex h-3.5 w-3.5 items-center justify-center border border-ind-bg bg-ind-acc text-[9px] font-bold text-ind-btn-ink">
                {aktiveFilterAnzahl}
              </span>
            )}
          </button>
          <button
            onClick={() => setAnsicht("liste")}
            className={`btn-touch flex items-center gap-1.5 border-l border-ind-line px-3 py-1.5 text-xs font-medium ${
              ansicht === "liste" ? "bg-ind-field text-ind-field-ink" : "text-ind-ink-2 hover:bg-ind-hover"
            }`}
          >
            <List size={13} strokeWidth={1.5} /> Liste
          </button>
          <button
            onClick={() => setAnsicht("karte")}
            className={`btn-touch flex items-center gap-1.5 border-l border-ind-line px-3 py-1.5 text-xs font-medium ${
              ansicht === "karte" ? "bg-ind-field text-ind-field-ink" : "text-ind-ink-2 hover:bg-ind-hover"
            }`}
          >
            <MapIcon size={13} strokeWidth={1.5} /> Karte
          </button>
        </div>
      </div>

      {filterChips.length > 0 && !zeigeFilter && (
        <div className="flex flex-wrap items-center gap-1.5 border border-ind-line-2 p-2.5">
          {filterChips.map((c) => (
            <span
              key={c.key}
              className="flex items-center gap-1.5 border border-ind-line-2 py-1 pr-1.5 pl-2.5 text-xs font-medium text-ind-ink-2"
            >
              {c.label}
              <button
                onClick={() => setField(c.key, "")}
                aria-label={`${c.label} entfernen`}
                className="btn-touch flex h-4 w-4 items-center justify-center text-ind-ink-3 hover:text-ind-ink"
              >
                <X size={9} strokeWidth={2.5} />
              </button>
            </span>
          ))}
          <button onClick={() => setZeigeFilter(true)} className="btn-touch ml-auto text-xs font-semibold text-ind-acc-txt">
            Bearbeiten
          </button>
        </div>
      )}

      {zeigeFilter && (
        <div className="space-y-2 border border-ind-line p-3">
          <div>
            <div className="mb-1 text-xs font-medium text-ind-ink-3">Status (Mehrfachauswahl möglich)</div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(STATUS_LABEL).map(([value, label]) => {
                const aktiv = aktiveStatus.includes(value);
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => toggleStatus(value)}
                    className={`btn-touch border px-3 py-1.5 text-xs font-medium ${
                      aktiv
                        ? "border-ind-field bg-ind-field text-ind-field-ink"
                        : "border-ind-line text-ind-ink-2 hover:bg-ind-hover"
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
            className="input-industry btn-touch"
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
            className="input-industry btn-touch"
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
              className="input-industry btn-touch"
            />
            <span className="text-xs text-ind-ink-3">bis</span>
            <input
              type="date"
              value={filter.faellig_bis ?? ""}
              onChange={(e) => setField("faellig_bis", e.target.value)}
              title="Fällig bis"
              className="input-industry btn-touch"
            />
          </div>
          <input
            value={filter.tag ?? ""}
            onChange={(e) => setField("tag", e.target.value)}
            placeholder="#Tag"
            className="input-industry btn-touch"
          />
          <select
            value={filter.sort ?? "last_activity_at"}
            onChange={(e) => setField("sort", e.target.value)}
            className="input-industry btn-touch"
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
                      className={`text-[10px] font-medium tracking-[0.14em] uppercase ${
                        gruppe === "ueberfaellig"
                          ? "text-red-600 dark:text-red-400"
                          : gruppe === "heute"
                            ? "text-amber-600 dark:text-amber-400"
                            : "text-ind-ink-3"
                      }`}
                    >
                      {GRUPPEN_LABEL[gruppe]}
                    </h3>
                    <span className="text-xs text-ind-ink-3">{gruppenCards.length}</span>
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
              className="btn-touch w-full border border-ind-line py-2 text-sm font-medium text-ind-ink-2 hover:bg-ind-hover disabled:opacity-50"
            >
              {isFetchingNextPage ? "Lädt…" : "Mehr laden"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
