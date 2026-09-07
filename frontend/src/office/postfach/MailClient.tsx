import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Forward, Inbox, Loader2, Paperclip, Reply, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { mailApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import type { MailAccount, MailAttachment } from "../../types";
import { ComposePanel, type ComposeModus } from "./ComposePanel";

function relativesDatum(iso: string | null): string {
  if (!iso) return "";
  const datum = new Date(iso);
  const heute = new Date();
  const gleicherTag = datum.toDateString() === heute.toDateString();
  if (gleicherTag) {
    return datum.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  }
  const diffTage = Math.round((heute.getTime() - datum.getTime()) / 86_400_000);
  if (diffTage < 7) return datum.toLocaleDateString("de-DE", { weekday: "short" });
  return datum.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

function AnhangZeile({ messageId, anhang }: { messageId: string; anhang: MailAttachment }) {
  const [laedt, setLaedt] = useState(false);
  return (
    <button
      disabled={laedt}
      onClick={async () => {
        setLaedt(true);
        try {
          const { url } = await mailApi.attachmentUrl(messageId, anhang.id);
          window.open(url, "_blank", "noopener,noreferrer");
        } finally {
          setLaedt(false);
        }
      }}
      className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800"
    >
      {laedt ? <Loader2 size={13} className="animate-spin" /> : <Paperclip size={13} strokeWidth={2} />}
      {anhang.dateiname}
    </button>
  );
}

export function MailClient({ account }: { account: MailAccount }) {
  const queryClient = useQueryClient();
  const [aktiverOrdner, setAktiverOrdner] = useState<string | null>(null);
  const [aktiveNachricht, setAktiveNachricht] = useState<string | null>(null);
  const [suche, setSuche] = useState("");
  const [compose, setCompose] = useState<ComposeModus | null>(null);

  const { data: ordner } = useQuery({
    queryKey: ["mail-folders", account.id],
    queryFn: () => mailApi.folders(account.id),
  });

  useEffect(() => {
    if (!aktiverOrdner && ordner && ordner.length > 0) {
      setAktiverOrdner(ordner[0].id);
    }
  }, [ordner, aktiverOrdner]);

  const {
    data: nachrichtenSeiten,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading: nachrichtenLaden,
  } = useInfiniteQuery({
    queryKey: ["mail-messages", aktiverOrdner, suche],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      mailApi.messages(aktiverOrdner!, { ...(suche ? { suche } : {}), ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (letzte) => letzte.next_cursor ?? undefined,
    enabled: !!aktiverOrdner,
  });
  const nachrichten = nachrichtenSeiten?.pages.flatMap((s) => s.items) ?? [];

  const { data: detail } = useQuery({
    queryKey: ["mail-message", aktiveNachricht],
    queryFn: () => mailApi.message(aktiveNachricht!),
    enabled: !!aktiveNachricht,
  });

  const alsGelesenMutation = useMutation({
    mutationFn: ({ id, gelesen }: { id: string; gelesen: boolean }) => mailApi.setGelesen(id, gelesen),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mail-messages"] });
      queryClient.invalidateQueries({ queryKey: ["mail-message", aktiveNachricht] });
    },
  });

  const waehleNachricht = (id: string, bereitsGelesen: boolean) => {
    setAktiveNachricht(id);
    setCompose(null);
    if (!bereitsGelesen) {
      alsGelesenMutation.mutate({ id, gelesen: true });
    }
  };

  const htmlSrcDoc = useMemo(() => {
    if (!detail?.body_html) return null;
    // sandbox ohne allow-scripts/allow-same-origin -- fremdes HTML darf
    // weder Skripte ausfuehren noch auf die App zugreifen. Externe Bilder
    // laden trotzdem (Tracking-Pixel-Risiko wie in jedem Mailclient,
    // kein FieldVibe-spezifisches Problem).
    return detail.body_html;
  }, [detail]);

  return (
    <div className="grid h-[calc(100vh-7.5rem)] grid-cols-[160px_300px_1fr] gap-3">
      <div className="overflow-y-auto rounded-xl border border-slate-200 bg-white py-2 dark:border-stone-800 dark:bg-stone-900">
        {(ordner ?? []).map((o) => (
          <button
            key={o.id}
            onClick={() => {
              setAktiverOrdner(o.id);
              setAktiveNachricht(null);
              setCompose(null);
            }}
            className={`block w-full truncate px-3 py-1.5 text-left text-[13px] font-medium ${
              o.id === aktiverOrdner
                ? "bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300"
                : "text-slate-600 hover:bg-slate-50 dark:text-stone-300 dark:hover:bg-stone-800/60"
            }`}
          >
            {o.anzeigename}
          </button>
        ))}
        <button
          onClick={() => {
            setCompose({ art: "neu", accountId: account.id });
            setAktiveNachricht(null);
          }}
          className="btn-clay mx-3 mt-2 w-[calc(100%-1.5rem)] rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 py-2 text-xs font-semibold text-white"
        >
          Neu
        </button>
      </div>

      <div className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-stone-800 dark:bg-stone-900">
        <div className="relative border-b border-slate-200 p-2 dark:border-stone-800">
          <Search
            size={13}
            strokeWidth={2}
            className="pointer-events-none absolute top-1/2 left-4.5 -translate-y-1/2 text-ind-ink-3"
          />
          <input
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            placeholder="Suchen…"
            className="w-full rounded-lg border border-slate-200 bg-slate-100 py-1.5 pr-2 pl-7 text-xs text-slate-700 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-200"
          />
        </div>
        <div className="flex-1 overflow-y-auto">
          {nachrichtenLaden ? (
            <p className="py-10 text-center text-sm text-ind-ink-3">Lädt…</p>
          ) : nachrichten.length === 0 ? (
            <EmptyState icon={Inbox} text="Keine Nachrichten." />
          ) : (
            nachrichten.map((n) => (
              <button
                key={n.id}
                onClick={() => waehleNachricht(n.id, n.gelesen)}
                className={`block w-full border-b border-slate-100 px-3 py-2.5 text-left last:border-b-0 dark:border-stone-800 ${
                  n.id === aktiveNachricht
                    ? "border-l-2 border-l-blue-500 bg-blue-50/60 pl-[10px] dark:bg-blue-500/10"
                    : "hover:bg-slate-50 dark:hover:bg-stone-800/50"
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <p
                    className={`truncate text-[13px] ${n.gelesen ? "font-medium text-ind-ink-2" : "font-bold text-slate-900 dark:text-white"}`}
                  >
                    {n.von_name || n.von_adresse || "Unbekannt"}
                  </p>
                  <span className="shrink-0 text-[10.5px] text-ind-ink-3">
                    {relativesDatum(n.datum)}
                  </span>
                </div>
                <p
                  className={`truncate text-[12.5px] ${n.gelesen ? "text-ind-ink-3" : "font-semibold text-ind-ink"}`}
                >
                  {n.betreff || "(kein Betreff)"}
                </p>
                <p className="mt-0.5 flex items-center gap-1 truncate text-[11.5px] text-ind-ink-3">
                  {n.hat_anhang && <Paperclip size={11} strokeWidth={2} />}
                  {n.ausschnitt}
                </p>
              </button>
            ))
          )}
          {hasNextPage && (
            <button
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              className="w-full py-2.5 text-center text-xs font-medium text-slate-500 hover:bg-slate-50 dark:text-stone-400 dark:hover:bg-stone-800/50"
            >
              {isFetchingNextPage ? "Lädt…" : "Weitere laden"}
            </button>
          )}
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-stone-800 dark:bg-stone-900">
        {compose ? (
          <ComposePanel modus={compose} onGesendet={() => setCompose(null)} onAbbrechen={() => setCompose(null)} />
        ) : !detail ? (
          <EmptyState icon={Inbox} text="Nachricht auswählen." className="h-full justify-center" />
        ) : (
          <div className="flex h-full flex-col">
            <div className="border-b border-slate-200 p-4 dark:border-stone-800">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h2 className="text-[15px] font-bold text-slate-900 dark:text-white">
                  {detail.betreff || "(kein Betreff)"}
                </h2>
                <div className="flex shrink-0 gap-1.5">
                  <button
                    onClick={() =>
                      setCompose({
                        art: "antworten",
                        messageId: detail.id,
                        an: detail.von_adresse ? [detail.von_adresse] : [],
                        betreff: detail.betreff,
                      })
                    }
                    className="flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800"
                  >
                    <Reply size={13} strokeWidth={2} /> Antworten
                  </button>
                  <button
                    onClick={() => setCompose({ art: "weiterleiten", messageId: detail.id, betreff: detail.betreff })}
                    className="flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800"
                  >
                    <Forward size={13} strokeWidth={2} /> Weiterleiten
                  </button>
                </div>
              </div>
              <p className="text-xs text-ind-ink-3">
                Von <span className="font-medium text-ind-ink">{detail.von_name || detail.von_adresse}</span>
                {detail.an.length > 0 && <> · An {detail.an.join(", ")}</>}
              </p>
              {detail.anhaenge.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {detail.anhaenge.map((a) => (
                    <AnhangZeile key={a.id} messageId={detail.id} anhang={a} />
                  ))}
                </div>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {htmlSrcDoc ? (
                <iframe
                  title="Nachrichteninhalt"
                  sandbox=""
                  srcDoc={htmlSrcDoc}
                  className="h-full w-full rounded-lg border border-slate-100 dark:border-stone-800"
                />
              ) : (
                <p className="text-sm whitespace-pre-wrap text-ind-ink">{detail.body_text}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
