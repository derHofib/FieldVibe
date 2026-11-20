import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ChevronDown,
  Folder,
  Forward,
  Inbox,
  Loader2,
  PenLine,
  Paperclip,
  Plus,
  RefreshCw,
  Reply,
  ReplyAll,
  Send,
  Settings,
  ShieldAlert,
  SquarePen,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { mailApi } from "../../api/endpoints";
import { Monogramm } from "../../components/apple/Monogramm";
import { PulldownMenu } from "../../components/apple/PulldownMenu";
import { SearchField } from "../../components/apple/SearchField";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import type { MailAccount, MailAttachment, MailFolder } from "../../types";
import { ComposePanel, type ComposeModus } from "./ComposePanel";
import { ROLLEN_LABEL, ROLLEN_REIHENFOLGE, ordnerRolle, type OrdnerRolle } from "./ordnerRolle";
import { abgleichStand, allenAntwortenEmpfaenger } from "./postfachHelfer";

const ROLLEN_ICON: Record<OrdnerRolle, LucideIcon> = {
  posteingang: Inbox,
  gesendet: Send,
  entwuerfe: PenLine,
  archiv: Archive,
  spam: ShieldAlert,
  papierkorb: Trash2,
};

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

function dateiTyp(dateiname: string): string {
  const punkt = dateiname.lastIndexOf(".");
  return punkt >= 0 ? dateiname.slice(punkt + 1, punkt + 5).toUpperCase() : "DATEI";
}

function groesseText(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

function AnhangKachel({ messageId, anhang }: { messageId: string; anhang: MailAttachment }) {
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState(false);
  return (
    <div className="flex flex-col items-start gap-1">
      <button
        type="button"
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
        className="flex items-center gap-2.5 rounded-[var(--radius-ap-md)] bg-fill px-2.5 py-2 text-left hover:bg-fill2 disabled:opacity-50"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-card text-meta font-bold text-label2">
          {laedt ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : dateiTyp(anhang.dateiname)}
        </span>
        <span className="min-w-0">
          <span className="block max-w-56 truncate text-sekundaer font-semibold text-label">{anhang.dateiname}</span>
          <span className="block text-meta text-label2">{groesseText(anhang.groesse_bytes)}</span>
        </span>
      </button>
      {fehler && <span className="text-sekundaer text-st-fehlt">Anhang konnte nicht geöffnet werden.</span>}
    </div>
  );
}

interface OrdnerGruppen {
  standard: { rolle: OrdnerRolle; ordner: MailFolder }[];
  eigene: MailFolder[];
}

function gruppiere(ordner: MailFolder[]): OrdnerGruppen {
  const nachRolle = new Map<OrdnerRolle, MailFolder>();
  const eigene: MailFolder[] = [];
  for (const o of ordner) {
    const rolle = ordnerRolle(o.imap_name);
    if (rolle && !nachRolle.has(rolle)) nachRolle.set(rolle, o);
    else eigene.push(o);
  }
  const standard = ROLLEN_REIHENFOLGE.filter((r) => nachRolle.has(r)).map((rolle) => ({
    rolle,
    ordner: nachRolle.get(rolle)!,
  }));
  return { standard, eigene };
}

interface Props {
  account: MailAccount;
  accounts: MailAccount[];
  onKontoWechsel: (id: string) => void;
}

export function MailClient({ account, accounts, onKontoWechsel }: Props) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [aktiverOrdner, setAktiverOrdner] = useState<string | null>(null);
  const [aktiveNachricht, setAktiveNachricht] = useState<string | null>(null);
  const [sucheEingabe, setSuche] = useState("");
  const suche = useDebouncedValue(sucheEingabe);
  const [compose, setCompose] = useState<ComposeModus | null>(null);
  const [gesendetHinweis, setGesendetHinweis] = useState(false);

  // Kontowechsel: Auswahl zurücksetzen, sonst zeigt die Liste kurz den Ordner des alten Kontos
  useEffect(() => {
    setAktiverOrdner(null);
    setAktiveNachricht(null);
    setCompose(null);
    setSuche("");
  }, [account.id]);

  const {
    data: ordner,
    isLoading: ordnerLaden,
    error: ordnerFehler,
    refetch: ordnerNeu,
  } = useQuery({
    queryKey: ["mail-folders", account.id],
    queryFn: () => mailApi.folders(account.id),
  });
  const gruppen = useMemo(() => gruppiere(ordner ?? []), [ordner]);

  useEffect(() => {
    if (!aktiverOrdner && ordner && ordner.length > 0) {
      setAktiverOrdner((gruppen.standard[0]?.ordner ?? ordner[0]).id);
    }
  }, [ordner, gruppen, aktiverOrdner]);
  const aktuellerOrdner = ordner?.find((o) => o.id === aktiverOrdner);

  const {
    data: nachrichtenSeiten,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading: nachrichtenLaden,
    error: nachrichtenFehler,
    refetch: nachrichtenNeu,
  } = useInfiniteQuery({
    queryKey: ["mail-messages", aktiverOrdner, suche],
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      mailApi.messages(aktiverOrdner!, { ...(suche ? { suche } : {}), ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (letzte) => letzte.next_cursor ?? undefined,
    enabled: !!aktiverOrdner,
  });
  const nachrichten = nachrichtenSeiten?.pages.flatMap((s) => s.items) ?? [];

  const { data: detail, isLoading: detailLaden, error: detailFehler, refetch: detailNeu } = useQuery({
    queryKey: ["mail-message", aktiveNachricht],
    queryFn: () => mailApi.message(aktiveNachricht!),
    enabled: !!aktiveNachricht,
  });

  const alsGelesenMutation = useMutation({
    mutationFn: ({ id, gelesen }: { id: string; gelesen: boolean }) => mailApi.setGelesen(id, gelesen),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mail-messages"] });
      queryClient.invalidateQueries({ queryKey: ["mail-message", aktiveNachricht] });
      queryClient.invalidateQueries({ queryKey: ["mail-folders", account.id] });
    },
  });

  const waehleNachricht = (id: string, bereitsGelesen: boolean) => {
    setAktiveNachricht(id);
    setCompose(null);
    if (!bereitsGelesen) {
      alsGelesenMutation.mutate({ id, gelesen: true });
    }
  };

  const waehleOrdner = (id: string) => {
    setAktiverOrdner(id);
    setAktiveNachricht(null);
    setCompose(null);
  };

  const ordnerZeile = (o: MailFolder, label: string, Icon: LucideIcon) => {
    const aktiv = o.id === aktiverOrdner;
    return (
      <button
        key={o.id}
        type="button"
        title={label}
        aria-label={label}
        aria-current={aktiv ? "true" : undefined}
        onClick={() => waehleOrdner(o.id)}
        className={`flex w-full items-center gap-2.5 rounded-[var(--radius-ap-md)] px-2.5 py-1.5 text-left text-sekundaer font-medium xl:justify-start max-xl:justify-center ${
          aktiv ? "bg-tintbg text-tint-text" : "text-label hover:bg-fill"
        }`}
      >
        <span className="relative shrink-0">
          <Icon size={16} strokeWidth={2} aria-hidden="true" />
          {o.ungelesen > 0 && (
            <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-tint xl:hidden" aria-hidden="true" />
          )}
        </span>
        <span className="hidden min-w-0 flex-1 truncate xl:block">{label}</span>
        {o.ungelesen > 0 && (
          <span className="hidden text-meta font-semibold text-label2 xl:block">{o.ungelesen}</span>
        )}
      </button>
    );
  };

  const stand = abgleichStand(account.letzter_sync_am);

  const flaeche = "overflow-hidden rounded-xl bg-card";

  return (
    <div className="grid h-[calc(100vh-7.5rem)] grid-cols-[56px_minmax(280px,400px)_minmax(0,1fr)] gap-3 xl:grid-cols-[232px_440px_minmax(0,1fr)]">
      <aside aria-label="Ordner" className={`flex flex-col p-2 ${flaeche}`}>
        <PulldownMenu
          ariaLabel="Postfach wechseln"
          items={[
            ...accounts.map((a) => ({
              label: a.name,
              aktiv: a.id === account.id,
              onSelect: () => onKontoWechsel(a.id),
            })),
            "trenner" as const,
            {
              label: "Postfach-Einstellungen",
              icon: Settings,
              onSelect: () => navigate(`/postfach/einstellungen?konto=${account.id}`),
            },
            {
              label: "Weiteres Postfach verbinden",
              icon: Plus,
              onSelect: () => navigate("/postfach/einstellungen?neu=1"),
            },
          ]}
          trigger={({ toggeln, triggerRef, offen }) => (
            <button
              ref={triggerRef}
              type="button"
              onClick={toggeln}
              aria-haspopup="menu"
              aria-expanded={offen}
              title={`${account.name} · ${account.email_adresse}`}
              className="flex w-full items-center gap-2.5 rounded-[var(--radius-ap-md)] p-1.5 text-left hover:bg-fill max-xl:justify-center"
            >
              <Monogramm name={account.name} groesse={32} ringKlasse="ring-card" />
              <span className="hidden min-w-0 flex-1 xl:block">
                <span className="block truncate text-sekundaer font-semibold text-label">{account.name}</span>
                <span className="block truncate text-meta text-label2">{account.email_adresse}</span>
              </span>
              <ChevronDown size={14} className="hidden shrink-0 text-label2 xl:block" aria-hidden="true" />
            </button>
          )}
        />

        <button
          type="button"
          title="Neue E-Mail"
          aria-label="Neue E-Mail"
          onClick={() => {
            setCompose({ art: "neu", accountId: account.id });
            setAktiveNachricht(null);
          }}
          className="btn-ap-primary mt-2 flex w-full items-center justify-center gap-1.5 py-2"
        >
          <SquarePen size={14} strokeWidth={2} aria-hidden="true" />
          <span className="hidden xl:inline">Neue E-Mail</span>
        </button>

        <nav className="mt-3 flex-1 space-y-0.5 overflow-y-auto">
          {gruppen.standard.map(({ rolle, ordner: o }) => ordnerZeile(o, ROLLEN_LABEL[rolle], ROLLEN_ICON[rolle]))}
          {gruppen.eigene.length > 0 && (
            <>
              <p className="hidden px-2.5 pt-4 pb-1 text-meta font-semibold tracking-wide text-label2 uppercase xl:block">
                Ordner
              </p>
              <div className="max-xl:mt-3 max-xl:space-y-0.5">
                {gruppen.eigene.map((o) => ordnerZeile(o, o.anzeigename, Folder))}
              </div>
            </>
          )}
        </nav>

        <div className="mt-2 flex items-center gap-2 px-2 pt-2 text-meta max-xl:justify-center">
          {account.letzter_sync_fehler ? (
            <Link
              to={`/postfach/einstellungen?konto=${account.id}`}
              title={account.letzter_sync_fehler}
              className="flex items-center gap-2 text-st-fehlt"
            >
              <RefreshCw size={13} aria-hidden="true" />
              <span className="hidden xl:inline">Abgleich fehlgeschlagen – Einstellungen</span>
              <span className="sr-only xl:hidden">Abgleich fehlgeschlagen</span>
            </Link>
          ) : (
            <span className="flex items-center gap-2 text-label2" title={stand ?? "Noch nicht abgeglichen"}>
              <RefreshCw size={13} aria-hidden="true" />
              <span className="hidden xl:inline">{stand ?? "Noch nicht abgeglichen"}</span>
            </span>
          )}
        </div>
      </aside>

      <section aria-label="Nachrichten" className={`flex flex-col ${flaeche}`}>
        <div className="p-2">
          <SearchField
            value={sucheEingabe}
            onChange={setSuche}
            placeholder={`${aktuellerOrdner ? (ordnerRolle(aktuellerOrdner.imap_name) ? ROLLEN_LABEL[ordnerRolle(aktuellerOrdner.imap_name)!] : aktuellerOrdner.anzeigename) : "Postfach"} durchsuchen`}
            ariaLabel="Nachrichten suchen"
          />
        </div>
        {gesendetHinweis && (
          <p role="status" className="mx-2 mb-1 rounded-lg bg-st-erledigt-bg px-3 py-1.5 text-sekundaer font-medium text-st-erledigt">
            Nachricht gesendet.
          </p>
        )}
        <div className="flex-1 overflow-y-auto px-1.5 pb-1.5">
          {ordnerFehler ? (
            <FehlerZustand fehler={ordnerFehler} was="Die Ordner" onErneut={() => void ordnerNeu()} />
          ) : nachrichtenFehler ? (
            <FehlerZustand fehler={nachrichtenFehler} was="Die Nachrichten" onErneut={() => void nachrichtenNeu()} />
          ) : ordnerLaden || nachrichtenLaden ? (
            <SkeletonList count={4} />
          ) : nachrichten.length === 0 ? (
            <EmptyState
              icon={Inbox}
              text={suche ? `Keine Treffer für „${suche}“.` : "Keine Nachrichten."}
              action={
                suche && (
                  <button onClick={() => setSuche("")} className="btn-touch text-sekundaer font-medium text-tint ">
                    Suche zurücksetzen
                  </button>
                )
              }
            />
          ) : (
            nachrichten.map((n) => {
              const absender = n.von_name || n.von_adresse || "Unbekannt";
              const aktiv = n.id === aktiveNachricht;
              return (
                <button
                  key={n.id}
                  type="button"
                  aria-current={aktiv ? "true" : undefined}
                  onClick={() => waehleNachricht(n.id, n.gelesen)}
                  className={`relative flex w-full items-start gap-3 rounded-[var(--radius-ap-md)] py-2.5 pr-3 pl-5 text-left ${
                    aktiv ? "bg-tintbg" : "hover:bg-fill"
                  }`}
                >
                  {!n.gelesen && (
                    <span
                      className="absolute top-[22px] left-2 h-2 w-2 rounded-full bg-tint"
                      role="img"
                      aria-label="Ungelesen"
                    />
                  )}
                  <Monogramm name={absender} groesse={36} ringKlasse="ring-card" />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className={`truncate text-sekundaer text-label ${n.gelesen ? "font-medium" : "font-bold"}`}>
                        {absender}
                      </span>
                      <span className="flex shrink-0 items-center gap-1 text-meta text-label2">
                        {n.hat_anhang && <Paperclip size={11} strokeWidth={2} aria-label="Mit Anhang" />}
                        {relativesDatum(n.datum)}
                      </span>
                    </span>
                    <span className={`block truncate text-sekundaer text-label ${n.gelesen ? "" : "font-semibold"}`}>
                      {n.betreff || "(kein Betreff)"}
                    </span>
                    <span className="mt-0.5 line-clamp-2 text-sekundaer text-label2">{n.ausschnitt}</span>
                  </span>
                </button>
              );
            })
          )}
          {hasNextPage && (
            <button
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              className="w-full py-2.5 text-center text-sekundaer font-medium text-label2 hover:bg-fill"
            >
              {isFetchingNextPage ? "Lädt…" : "Weitere laden"}
            </button>
          )}
        </div>
      </section>

      <section aria-label="Lesebereich" className={flaeche}>
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
        ) : detailLaden ? (
          <SkeletonList count={2} className="p-4" />
        ) : detailFehler ? (
          <FehlerZustand fehler={detailFehler} was="Die Nachricht" onErneut={() => void detailNeu()} className="h-full" />
        ) : !detail ? (
          <EmptyState icon={Inbox} text="Nachricht auswählen." className="h-full justify-center" />
        ) : (
          <div className="flex h-full flex-col">
            <div className="flex flex-wrap items-center gap-2 p-3">
              <button
                type="button"
                onClick={() =>
                  setCompose({
                    art: "antworten",
                    messageId: detail.id,
                    an: detail.von_adresse ? [detail.von_adresse] : [],
                    betreff: detail.betreff,
                  })
                }
                className="btn-ap flex items-center gap-1.5"
              >
                <Reply size={14} strokeWidth={2} aria-hidden="true" /> Antworten
              </button>
              <button
                type="button"
                onClick={() => {
                  const { an, cc } = allenAntwortenEmpfaenger(detail, account.email_adresse);
                  setCompose({ art: "antworten", messageId: detail.id, an, cc, betreff: detail.betreff });
                }}
                className="btn-ap flex items-center gap-1.5"
              >
                <ReplyAll size={14} strokeWidth={2} aria-hidden="true" /> Allen antworten
              </button>
              <button
                type="button"
                onClick={() => setCompose({ art: "weiterleiten", messageId: detail.id, betreff: detail.betreff })}
                className="btn-ap flex items-center gap-1.5"
              >
                <Forward size={14} strokeWidth={2} aria-hidden="true" /> Weiterleiten
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 pb-5">
              <h2 className="ap-heading text-titel-mobil font-bold text-label">{detail.betreff || "(kein Betreff)"}</h2>
              <div className="mt-3 flex items-start gap-3">
                <Monogramm name={detail.von_name || detail.von_adresse || "?"} groesse={40} ringKlasse="ring-card" />
                <div className="min-w-0 flex-1">
                  <p className="text-fliess text-label">
                    <span className="font-semibold">{detail.von_name || detail.von_adresse}</span>
                    {detail.von_name && detail.von_adresse && (
                      <span className="ml-1.5 text-sekundaer text-label2">{detail.von_adresse}</span>
                    )}
                  </p>
                  {detail.an.length > 0 && (
                    <p className="text-sekundaer text-label2">An: {detail.an.join(", ")}</p>
                  )}
                  {detail.cc.length > 0 && <p className="text-sekundaer text-label2">Cc: {detail.cc.join(", ")}</p>}
                </div>
                <span className="shrink-0 text-sekundaer text-label2">
                  {detail.datum
                    ? new Date(detail.datum).toLocaleString("de-DE", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : ""}
                </span>
              </div>
              {detail.anhaenge.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {detail.anhaenge.map((a) => (
                    <AnhangKachel key={a.id} messageId={detail.id} anhang={a} />
                  ))}
                </div>
              )}
              {/* Helle Papierfläche auch im Dark Mode: fremde HTML-Mails sind fast immer für weißen Grund gestaltet. */}
              <div className="mt-4 min-h-[320px] overflow-hidden rounded-xl bg-white text-black">
                {detail.body_html ? (
                  // sandbox ohne allow-scripts/allow-same-origin: fremdes HTML darf weder Skripte
                  // ausführen noch auf die App zugreifen.
                  <iframe
                    title="Nachrichteninhalt"
                    sandbox=""
                    srcDoc={detail.body_html}
                    style={{ colorScheme: "light" }}
                    className="h-[60vh] w-full bg-white"
                  />
                ) : (
                  <p className="p-5 text-fliess whitespace-pre-wrap break-words">{detail.body_text}</p>
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
