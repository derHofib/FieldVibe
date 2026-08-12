import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Inbox, List, Map as MapIcon, Repeat, Search, Star } from "lucide-react";
import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";

import { feedApi, kundenApi, storiesApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FilterVorlagenLeiste } from "../../components/FilterVorlagenLeiste";
import type { FeedMapPunkt } from "../../components/MapboxFeedMap";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { cacheFeedItems, getCachedFeedItems } from "../../offline/cache";
import { istModulAktiv } from "../../utils/module";
import type { FeedCard, FeedResponse, StoryItem, VorgangStatus } from "../../types";

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
      className={`card-interactive btn-touch flex w-40 shrink-0 flex-col items-start rounded-lg border-l-4 bg-white p-3 text-left shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800 ${
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

function FeedCardView({ card }: { card: FeedCard }) {
  const navigate = useNavigate();
  const faelligkeitIso = card.faelligkeit_am?.slice(0, 10);
  return (
    <div
      className={`card-soft ${card.status === "storniert" ? "opacity-60 grayscale" : ""}`}
      style={{ "--frame-color": STATUS_FRAME[card.status] } as CSSProperties}
    >
    <button
      onClick={() => navigate(`/vorgaenge/${card.id}`)}
      className="card-soft-inner btn-touch flex w-full flex-col gap-2 bg-white p-4 text-left dark:bg-stone-900"
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
          {faelligkeitIso && (
            <span className={`whitespace-nowrap text-xs font-medium ${faelligkeitsFarbe(faelligkeitIso)}`}>
              Fällig: {new Date(faelligkeitIso).toLocaleDateString("de-DE")}
            </span>
          )}
        </div>
      </div>
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
    </div>
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

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
  } = useInfiniteQuery({
    queryKey: ["feed", filter],
    queryFn: async ({ pageParam }: { pageParam: string | undefined }): Promise<FeedResponse> => {
      try {
        const result = await feedApi.get({
          ...filter,
          ...(pageParam ? { cursor: pageParam } : {}),
        });
        // Only the first page mirrors into the offline cache -- it's meant
        // to reflect "the feed as last seen", not accumulate every page a
        // user has ever scrolled through.
        if (!pageParam) await cacheFeedItems(result.items);
        return result;
      } catch (err) {
        if (!navigator.onLine && !pageParam) {
          const cached = await getCachedFeedItems();
          if (cached.length > 0) return { items: cached, next_cursor: null };
        }
        throw err;
      }
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  // Die Liste zeigt bewusst nur Seite fuer Seite ("Mehr laden"), aber die
  // Kartenansicht braucht alle zum aktuellen Filter passenden Vorgaenge auf
  // einmal, sonst wuerden Pins fehlen, die einfach noch nicht nachgeladen
  // wurden. hasNextPage/fetchNextPage per Ref, damit der Effekt nicht bei
  // jeder neu geladenen Seite neu startet, sondern einmalig pro
  // Ansicht-Wechsel durchlaeuft.
  const hasNextPageRef = useRef(hasNextPage);
  hasNextPageRef.current = hasNextPage;
  const fetchNextPageRef = useRef(fetchNextPage);
  fetchNextPageRef.current = fetchNextPage;
  useEffect(() => {
    if (ansicht !== "karte") return;
    let abgebrochen = false;
    (async () => {
      let seiten = 0;
      while (!abgebrochen && hasNextPageRef.current && seiten < 20) {
        await fetchNextPageRef.current();
        seiten++;
      }
    })();
    return () => {
      abgebrochen = true;
    };
  }, [ansicht]);

  const storyGroups = stories
    ? [...stories.wartet_kunde, ...stories.heute, ...stories.fristen]
    : [];
  const cards = data?.pages.flatMap((p) => p.items) ?? [];
  const aktiveFilterAnzahl = Object.keys(filter).length;
  const punkte: FeedMapPunkt[] = cards
    .filter((c) => c.geo_lat != null && c.geo_lng != null)
    .map((c) => ({ id: c.id, lng: c.geo_lng as number, lat: c.geo_lat as number, farbe: STATUS_HEX[c.status] }));
  const ohneKoordinatenAnzahl = cards.length - punkte.length;

  return (
    <div className="space-y-4">
      {istModulAktiv(currentUser, "highlights") && (
        <button
          onClick={() => navigate("/highlights")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-amber-700 shadow-sm dark:bg-stone-900 dark:text-amber-400 dark:shadow-none dark:ring-1 dark:ring-stone-800"
        >
          <Star size={15} strokeWidth={2} /> Highlights ansehen
        </button>
      )}

      {storyGroups.length > 0 && (
        <div className="-mx-3 flex gap-2 overflow-x-auto px-3 pb-1">
          {storyGroups.map((item) => (
            <StoryChip key={`${item.ziel_typ}-${item.ziel_id}`} item={item} />
          ))}
        </div>
      )}

      <div className="space-y-3 rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="flex items-center justify-between">
          <button
            onClick={() => setZeigeFilter((v) => !v)}
            className="btn-touch flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-stone-200"
          >
            <Search size={14} strokeWidth={2} /> Filter
            {aktiveFilterAnzahl > 0 && (
              <span className="rounded-full bg-cyan-500 px-1.5 py-0.5 text-xs font-semibold text-white">
                {aktiveFilterAnzahl}
              </span>
            )}
          </button>
          <div className="flex gap-1">
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
        </div>

        {zeigeFilter && (
          <div className="space-y-2">
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
                          ? "btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 text-white"
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
      </div>

      <div className="flex justify-end gap-1">
        <button
          onClick={() => setAnsicht("liste")}
          className={`btn-touch flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${
            ansicht === "liste"
              ? "btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 text-white"
              : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
          }`}
        >
          <List size={13} strokeWidth={2} /> Liste
        </button>
        <button
          onClick={() => setAnsicht("karte")}
          className={`btn-touch flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${
            ansicht === "karte"
              ? "btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 text-white"
              : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
          }`}
        >
          <MapIcon size={13} strokeWidth={2} /> Karte
        </button>
      </div>

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
            <div className="space-y-3">
              {cards.map((card) => (
                <FeedCardView key={card.id} card={card} />
              ))}
            </div>
          )}

          {hasNextPage && (
            <button
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              className="btn-touch w-full rounded-md bg-white py-2 text-sm font-medium text-slate-600 shadow-sm disabled:opacity-50 dark:bg-stone-900 dark:text-stone-300 dark:shadow-none dark:ring-1 dark:ring-stone-800"
            >
              {isFetchingNextPage ? "Lädt…" : "Mehr laden"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
