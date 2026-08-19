import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Inbox, Paperclip, Plus } from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { mailApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { MailKontoFormular } from "../../office/postfach/MailKontoFormular";

function relativesDatum(iso: string | null): string {
  if (!iso) return "";
  const datum = new Date(iso);
  const heute = new Date();
  if (datum.toDateString() === heute.toDateString()) {
    return datum.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  }
  return datum.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
}

/** Schlanke Mobil-Ansicht: Liste + Lesen + Antworten, bewusst ohne
 * Ordner-Verwaltung -- zeigt immer den ersten (nach Sortierung: den
 * Posteingang-) Ordner des aktiven Kontos. Wer mehr braucht (Gesendet,
 * Papierkorb, mehrere Postfaecher gleichzeitig im Blick), wechselt auf
 * office.<domain>. Kontoeinrichtung nutzt dieselbe Komponente wie dort --
 * kein zweites Formular fuer dieselben zehn Felder. */
export function PostfachPage() {
  const navigate = useNavigate();
  const { data: accounts, isLoading: kontenLaden } = useQuery({
    queryKey: ["mail-accounts"],
    queryFn: () => mailApi.accounts.list(),
  });
  const aktivesKonto = accounts?.[0];

  const { data: ordner } = useQuery({
    queryKey: ["mail-folders", aktivesKonto?.id],
    queryFn: () => mailApi.folders(aktivesKonto!.id),
    enabled: !!aktivesKonto,
  });
  const posteingang = ordner?.[0];

  const {
    data: seiten,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading: nachrichtenLaden,
  } = useInfiniteQuery({
    queryKey: ["mail-messages", posteingang?.id],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      mailApi.messages(posteingang!.id, pageParam ? { cursor: pageParam } : {}),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (letzte) => letzte.next_cursor ?? undefined,
    enabled: !!posteingang,
  });
  const nachrichten = seiten?.pages.flatMap((s) => s.items) ?? [];

  // Beim Betreten der Seite reichlich vorladen, aber nicht endlos --
  // gleiches Prinzip wie bei den Office-Kanban-/Raster-Ansichten.
  const hasNextPageRef = { current: hasNextPage };
  hasNextPageRef.current = hasNextPage;
  useEffect(() => {
    if (!posteingang) return;
    let abgebrochen = false;
    (async () => {
      let seitenGeladen = 0;
      while (!abgebrochen && hasNextPageRef.current && seitenGeladen < 3) {
        await fetchNextPage();
        seitenGeladen++;
      }
    })();
    return () => {
      abgebrochen = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [posteingang?.id]);

  if (kontenLaden) {
    return <SkeletonList count={4} />;
  }

  if (!accounts || accounts.length === 0) {
    return (
      <div className="space-y-4">
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Postfach</h1>
        <MailKontoFormular onFertig={() => window.location.reload()} />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">
          {posteingang?.anzeigename ?? "Postfach"}
        </h1>
        <button
          onClick={() => navigate("/postfach/neu")}
          className="btn-touch flex items-center gap-1 rounded-full bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-xs font-semibold text-white"
        >
          <Plus size={14} strokeWidth={2.5} /> Neu
        </button>
      </div>

      {nachrichtenLaden ? (
        <SkeletonList count={5} />
      ) : nachrichten.length === 0 ? (
        <EmptyState icon={Inbox} text="Keine Nachrichten im Posteingang." />
      ) : (
        <div className="space-y-1.5">
          {nachrichten.map((n) => (
            <button
              key={n.id}
              onClick={() => navigate(`/postfach/${n.id}`)}
              className="card-interactive block w-full rounded-xl bg-white p-3 text-left shadow-sm dark:bg-stone-900"
            >
              <div className="flex items-baseline justify-between gap-2">
                <p
                  className={`truncate text-sm ${n.gelesen ? "font-medium text-slate-600 dark:text-stone-300" : "font-bold text-slate-900 dark:text-white"}`}
                >
                  {n.von_name || n.von_adresse || "Unbekannt"}
                </p>
                <span className="shrink-0 text-[11px] text-slate-400 dark:text-stone-500">
                  {relativesDatum(n.datum)}
                </span>
              </div>
              <p
                className={`truncate text-[13px] ${n.gelesen ? "text-slate-500 dark:text-stone-400" : "font-semibold text-slate-800 dark:text-stone-100"}`}
              >
                {n.betreff || "(kein Betreff)"}
              </p>
              <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-slate-400 dark:text-stone-500">
                {n.hat_anhang && <Paperclip size={11} strokeWidth={2} />}
                {n.ausschnitt}
              </p>
            </button>
          ))}
          {hasNextPage && (
            <button
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              className="btn-touch w-full py-2 text-center text-xs font-medium text-slate-500 dark:text-stone-400"
            >
              {isFetchingNextPage ? "Lädt…" : "Weitere laden"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
