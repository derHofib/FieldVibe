import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { feedApi, storiesApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { cacheFeedItems, getCachedFeedItems } from "../../offline/cache";
import { istModulAktiv } from "../../utils/module";
import type { FeedCard, FeedResponse, StoryItem, VorgangStatus } from "../../types";

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
  abgerechnet: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300",
  storniert: "bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500",
};

const AMPEL_COLOR: Record<string, string> = {
  gruen: "border-green-500",
  gelb: "border-amber-500",
  rot: "border-red-500",
};

const STORY_ZIEL_PFAD: Record<StoryItem["ziel_typ"], (id: string) => string> = {
  vorgang: (id) => `/vorgaenge/${id}`,
  anlage: (id) => `/anlagen/${id}`,
  // Prüfmittel/Material haben keine eigene Detailseite -- die jeweilige
  // Verwaltungsliste ist das naechstbeste Ziel (besser als eine falsche
  // ID in eine fremde Detailroute zu stecken).
  pruefmittel: () => "/pruefmittel",
  material: () => "/geschaeft",
};

function StoryChip({ item }: { item: StoryItem }) {
  const navigate = useNavigate();
  const path = STORY_ZIEL_PFAD[item.ziel_typ](item.ziel_id);
  return (
    <button
      onClick={() => navigate(path)}
      className={`btn-touch flex w-40 shrink-0 flex-col items-start rounded-lg border-l-4 bg-white p-3 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800 ${
        item.ampel ? AMPEL_COLOR[item.ampel] : "border-slate-300 dark:border-slate-600"
      }`}
    >
      <span className="line-clamp-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
        {item.titel}
      </span>
      {item.subtitel && (
        <span className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.subtitel}</span>
      )}
    </button>
  );
}

function FeedCardView({ card }: { card: FeedCard }) {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate(`/vorgaenge/${card.id}`)}
      className={`btn-touch flex w-full flex-col gap-2 rounded-lg bg-white p-4 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800 ${
        card.status === "storniert" ? "opacity-60 grayscale" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs text-slate-400 dark:text-slate-500">{card.vorgangsnummer}</div>
          <div className="font-semibold text-slate-800 dark:text-slate-100">{card.titel}</div>
          <div className="text-sm text-slate-500 dark:text-slate-400">{card.kunde_name}</div>
          {card.anlage_kurzadresse && (
            <div className="text-xs text-slate-400 dark:text-slate-500">{card.anlage_kurzadresse}</div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          {card.timer_laeuft && (
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" title="Timer läuft" />
          )}
          {card.dauerauftrag_id && (
            <span title="Dauerauftrag" className="text-sm">
              🔁
            </span>
          )}
          <span className={`whitespace-nowrap rounded-full px-2 py-1 text-xs font-semibold ${STATUS_BADGE[card.status]}`}>
            {STATUS_LABEL[card.status]}
          </span>
        </div>
      </div>
      {card.letztes_event_vorschau && (
        <p className="line-clamp-2 rounded-md bg-slate-50 px-2 py-1.5 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {card.letztes_event_vorschau}
        </p>
      )}
      {card.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {card.tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            >
              #{tag}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

export function FeedPage() {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const [statusFilter, setStatusFilter] = useState<string>("");

  const { data: stories } = useQuery({ queryKey: ["stories"], queryFn: storiesApi.get });

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
  } = useInfiniteQuery({
    queryKey: ["feed", statusFilter],
    queryFn: async ({ pageParam }: { pageParam: string | undefined }): Promise<FeedResponse> => {
      try {
        const result = await feedApi.get({
          ...(statusFilter ? { status: statusFilter } : {}),
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

  const storyGroups = stories
    ? [...stories.wartet_kunde, ...stories.heute, ...stories.fristen, ...stories.material]
    : [];
  const cards = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="space-y-4">
      {istModulAktiv(currentUser, "highlights") && (
        <button
          onClick={() => navigate("/highlights")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-amber-700 shadow-sm dark:bg-slate-900 dark:text-amber-400 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          ⭐ Highlights ansehen
        </button>
      )}

      {storyGroups.length > 0 && (
        <div className="-mx-3 flex gap-2 overflow-x-auto px-3 pb-1">
          {storyGroups.map((item) => (
            <StoryChip key={`${item.ziel_typ}-${item.ziel_id}`} item={item} />
          ))}
        </div>
      )}

      <select
        value={statusFilter}
        onChange={(e) => setStatusFilter(e.target.value)}
        className="btn-touch w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        <option value="">Alle Status</option>
        {Object.entries(STATUS_LABEL).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>

      {isLoading ? (
        <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>
      ) : cards.length === 0 ? (
        <p className="text-center text-slate-500 dark:text-slate-400">Keine Vorgänge gefunden.</p>
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
          className="btn-touch w-full rounded-md bg-white py-2 text-sm font-medium text-slate-600 shadow-sm disabled:opacity-50 dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          {isFetchingNextPage ? "Lädt…" : "Mehr laden"}
        </button>
      )}
    </div>
  );
}
