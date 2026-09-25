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
  const [fehler, setFehler] = useState(false);
  return (
    <div className="flex flex-col items-start gap-1">
      <button
        disabled={laedt}
        onClick={async () => {
          setLaedt(true);
          setFehler(false);
          try {
            const { url } = await mailApi.attachmentUrl(messageId, anhang.id);
            window.open(url, "_blank", "noopener,noreferrer");
          } catch {
            setFehler(true);
          } finally {
            setLaedt(false);
          }
        }}
        className="flex items-center gap-1.5 rounded-lg border border-sep px-2.5 py-1.5 text-xs font-medium text-label hover:bg-fill disabled:opacity-50"
      >
        {laedt ? <Loader2 size={13} className="animate-spin" /> : <Paperclip size={13} strokeWidth={2} />}
        {anhang.dateiname}
      </button>
      {fehler && <span className="text-xs text-st-fehlt ">Anhang konnte nicht geöffnet werden.</span>}
    </div>
  );
}

export function MailClient({ account }: { account: MailAccount }) {
  const queryClient = useQueryClient();
  const [aktiverOrdner, setAktiverOrdner] = useState<string | null>(null);
  const [aktiveNachricht, setAktiveNachricht] = useState<string | null>(null);
  const [suche, setSuche] = useState("");
  const [compose, setCompose] = useState<ComposeModus | null>(null);
  const [gesendetHinweis, setGesendetHinweis] = useState(false);

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
    <div className="grid h-[calc(100vh-7.5rem)] grid-cols-[minmax(120px,160px)_minmax(220px,300px)_minmax(280px,1fr)] gap-3">
      <div className="overflow-y-auto rounded-xl border border-sep bg-card py-2">
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
                : "text-label hover:bg-fill"
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
          className="btn-ap-primary mx-3 mt-2 w-[calc(100%-1.5rem)] py-2 text-xs"
        >
          Neu
        </button>
      </div>

      <div className="flex flex-col overflow-hidden rounded-xl border border-sep bg-card">
        <div className="relative border-b border-sep p-2 ">
          <Search
            size={13}
            strokeWidth={2}
            className="pointer-events-none absolute top-1/2 left-4.5 -translate-y-1/2 text-label2"
          />
          <input
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            placeholder="Suchen…"
            className="w-full rounded-lg border border-sep bg-fill py-1.5 pr-2 pl-7 text-xs text-label "
          />
        </div>
        {gesendetHinweis && (
          <p className="border-b border-st-erledigt bg-st-erledigt-bg px-3 py-1.5 text-xs font-medium text-st-erledigt ">
            Nachricht gesendet.
          </p>
        )}
        <div className="flex-1 overflow-y-auto">
          {nachrichtenLaden ? (
            <p className="py-10 text-center text-sm text-label2">Lädt…</p>
          ) : nachrichten.length === 0 ? (
            <EmptyState
              icon={Inbox}
              text={suche ? `Keine Treffer für „${suche}“.` : "Keine Nachrichten."}
              action={
                suche && (
                  <button onClick={() => setSuche("")} className="btn-touch text-xs font-medium text-tint ">
                    Suche zurücksetzen
                  </button>
                )
              }
            />
          ) : (
            nachrichten.map((n) => (
              <button
                key={n.id}
                onClick={() => waehleNachricht(n.id, n.gelesen)}
                className={`block w-full border-b border-sep px-3 py-2.5 text-left last:border-b-0 ${
                  n.id === aktiveNachricht
                    ? "border-l-2 border-l-blue-500 bg-tintbg pl-[10px] "
                    : "hover:bg-fill"
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <p
                    className={`truncate text-[13px] ${n.gelesen ? "font-medium text-label" : "font-bold text-label dark:text-white"}`}
                  >
                    {n.von_name || n.von_adresse || "Unbekannt"}
                  </p>
                  <span className="shrink-0 text-[10.5px] text-label2">
                    {relativesDatum(n.datum)}
                  </span>
                </div>
                <p
                  className={`truncate text-[12.5px] ${n.gelesen ? "text-label2" : "font-semibold text-label"}`}
                >
                  {n.betreff || "(kein Betreff)"}
                </p>
                <p className="mt-0.5 flex items-center gap-1 truncate text-[11.5px] text-label2">
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
              className="w-full py-2.5 text-center text-xs font-medium text-label2 hover:bg-fill"
            >
              {isFetchingNextPage ? "Lädt…" : "Weitere laden"}
            </button>
          )}
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-sep bg-card">
        {compose ? (
          <ComposePanel
            modus={compose}
            onGesendet={() => {
              setCompose(null);
              setGesendetHinweis(true);
              window.setTimeout(() => setGesendetHinweis(false), 3000);
            }}
            onAbbrechen={() => setCompose(null)}
          />
        ) : !detail ? (
          <EmptyState icon={Inbox} text="Nachricht auswählen." className="h-full justify-center" />
        ) : (
          <div className="flex h-full flex-col">
            <div className="border-b border-sep p-4 ">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h2 className="text-[15px] font-bold text-label dark:text-white">
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
                    className="flex items-center gap-1 rounded-lg border border-sep px-2.5 py-1.5 text-xs font-medium text-label hover:bg-fill"
                  >
                    <Reply size={13} strokeWidth={2} /> Antworten
                  </button>
                  <button
                    onClick={() => setCompose({ art: "weiterleiten", messageId: detail.id, betreff: detail.betreff })}
                    className="flex items-center gap-1 rounded-lg border border-sep px-2.5 py-1.5 text-xs font-medium text-label hover:bg-fill"
                  >
                    <Forward size={13} strokeWidth={2} /> Weiterleiten
                  </button>
                </div>
              </div>
              <p className="text-xs text-label2">
                Von <span className="font-medium text-label">{detail.von_name || detail.von_adresse}</span>
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
                  className="h-full w-full rounded-lg border border-sep "
                />
              ) : (
                <p className="text-sm whitespace-pre-wrap break-words text-label">{detail.body_text}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
