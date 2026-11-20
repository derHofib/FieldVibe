import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { heuteIso, statusMetaZeile } from "../../utils/format";
import { Bell, CheckCircle2, Clock, Inbox, MapPin, Map as MapIcon, MessageCircle, Play, Plus, Repeat, ScanLine, Search, Star, UserPlus, Users } from "lucide-react";
import { Suspense, lazy, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { anlagenApi, kundenApi, storiesApi, vorgaengeApi } from "../../api/endpoints";
import Blueprint from "../../components/Blueprint";
import { LaeuftPille } from "../../components/apple/LaeuftPille";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { StatusPille } from "../../components/apple/StatusPille";
import { statusDotFarbe, vorgangStatusZuToken } from "../../components/apple/status";
import { EmptyState } from "../../components/EmptyState";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import { QrScanner } from "../../components/QrScanner";
import type { FeedMapPunkt } from "../../components/MapboxFeedMap";
import { SkeletonList } from "../../components/Skeleton";
import { VorgaengeSortierMenue } from "../../components/VorgaengeSortierMenue";
import { GRUPPEN_LABEL, STATUS_LABEL, gruppiereNachFaelligkeit } from "../../config/vorgangDarstellung";
import { ALLE_STATUS, OFFENE_STATUS_FILTER, alteVorlageUmrechnen } from "../../config/vorgaengeFilter";
import { useAuth } from "../../context/AuthContext";
import { useAlleSeitenLaden, useVorgangsListe } from "../../hooks/useVorgangsListe";
import { useVorgaengeFilter } from "../../hooks/useVorgaengeFilter";
import { istModulAktiv } from "../../utils/module";
import { feedOrtZeile } from "../../utils/vorOrt";
import type { FeedCard, StoryItem, VorgangStatus } from "../../types";
import { FehlerZustand } from "../../components/FehlerZustand";
import { HauptkontaktZeile } from "./vorOrt/HauptkontaktZeile";

// Lazy statt statisch importiert: mapbox-gl allein ist ~1.8 MB und soll nur
// geladen werden, wenn die Kartenansicht tatsaechlich geoeffnet wird (siehe
// gleiche Begruendung bei MapboxMap.tsx in der Vorgang-Detailseite).
const MapboxFeedMap = lazy(() =>
  import("../../components/MapboxFeedMap").then((m) => ({ default: m.MapboxFeedMap })),
);

const LEISTUNGSTYP_LABEL: Record<string, string> = {
  installation: "Installation",
  pruefung: "Prüfung",
  wartung: "Wartung",
  stoerung: "Störung",
  beratung: "Beratung",
  planung: "Planung",
};

// Ampel-Symbol der Story-Kacheln -- kein Vorgangs-Status, sondern eine
// eigene Dringlichkeits-Ampel (siehe stories-Endpoint), deshalb ueber die
// Status-Kreis-Farben (nicht -Token) abgebildet statt eigener Paletten.
const AMPEL_VAR: Record<string, string> = {
  gruen: "var(--st-erledigt-dot)",
  gelb: "var(--st-arbeit-dot)",
  rot: "var(--st-fehlt-dot)",
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
        className="px-2.5 py-2.5"
        // .card-ap setzt den Rahmen als CSS-Shorthand (alle vier Seiten)
        // ausserhalb jedes @layer -- eine Tailwind-Randfarb-/-breiten-
        // Utility fuer nur die linke Kante koennte das nicht ueberschreiben.
        style={{ borderLeftWidth: 2, borderLeftColor: item.ampel ? AMPEL_VAR[item.ampel] : "var(--sepstrong)" }}
      >
        <span className="line-clamp-2 text-sekundaer font-semibold leading-tight text-label">{item.titel}</span>
        {item.subtitel && <span className="mt-0.5 block text-meta text-label2">{item.subtitel}</span>}
      </Blueprint>
    </button>
  );
}

function faelligkeitsFarbe(iso: string): string {
  const heute = heuteIso();
  if (iso < heute) return "text-st-fehlt";
  if (iso <= heuteIso(3)) return "text-st-arbeit";
  return "text-label2";
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
  // last_activity_at ist nur naeherungsweise der Zeitpunkt des Events (kein eigenes Feld im Feed).
  const statusMeta = statusMetaZeile(card.letztes_event_vorschau, card.last_activity_at);

  const invalidateFeed = () => queryClient.invalidateQueries({ queryKey: ["feed"] });
  const zuweisenMutation = useMutation({
    mutationFn: () => vorgaengeApi.uebernehmen(card.id),
    onSuccess: invalidateFeed,
  });
  const statusMutation = useMutation({
    meta: { erfolg: "Status geändert" },
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
  const aktionFehlerQuelle = zuweisenMutation.error ?? statusMutation.error;
  const aktionFehlerText =
    zuweisenMutation.isError || statusMutation.isError
      ? aktionFehlerQuelle instanceof ApiError
        ? aktionFehlerQuelle.message
        : "Keine Verbindung — bitte erneut versuchen"
      : null;

  return (
    <Blueprint className={card.status === "storniert" ? "opacity-60 grayscale" : ""}>
      <button
        onClick={() => navigate(`/vorgaenge/${card.id}`)}
        className="btn-touch flex w-full flex-col gap-2 p-3 text-left"
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-meta tracking-wide text-label2">{card.vorgangsnummer}</div>
            <div className="mt-0.5 font-semibold text-label">{card.titel}</div>
            <div className="text-meta text-label2">{card.kunde_name}</div>
            {card.anlage_bezeichnung && <div className="text-meta text-label2">{card.anlage_bezeichnung}</div>}
            {feedOrtZeile(card) && (
              <div className="flex items-start gap-1 text-sekundaer text-label2">
                <MapPin size={13} strokeWidth={1.5} className="mt-0.5 shrink-0" aria-hidden="true" />
                <span>{feedOrtZeile(card)}</span>
              </div>
            )}
            {card.ersteller_name && <div className="text-sekundaer text-label2">von {card.ersteller_name}</div>}
            {!["abgeschlossen", "abgerechnet", "storniert"].includes(card.status) && (
              <div className="text-sekundaer text-label2">
                {card.zugewiesener_name ? `Zugewiesen: ${card.zugewiesener_name}` : "Nicht zugewiesen"}
              </div>
            )}
          </div>
          <div className="flex flex-none flex-col items-end gap-1">
            {card.timer_laeuft && (
              <LaeuftPille />
            )}
            {card.dauerauftrag_id && (
              <span title="Dauerauftrag" className="text-st-arbeit">
                <Repeat size={14} strokeWidth={1.5} aria-hidden="true" />
              </span>
            )}
            <StatusPille status={vorgangStatusZuToken(card.status)} label={STATUS_LABEL[card.status]} />
            <span className="whitespace-nowrap text-sekundaer text-label2">
              {LEISTUNGSTYP_LABEL[card.leistungstyp] ?? card.leistungstyp}
            </span>
          </div>
        </div>
        {card.status === "wartet_kunde" ? (
          <span className="flex items-center gap-1 text-sekundaer text-label2">
            <MessageCircle size={13} strokeWidth={1.5} aria-hidden="true" /> Wartet auf Rückmeldung
          </span>
        ) : (
          faelligkeitIso && (
            <span className={`flex items-center gap-1 text-sekundaer font-medium ${faelligkeitsFarbe(faelligkeitIso)}`}>
              {faelligkeitIso < heuteIso() ? (
                <>
                  <Clock size={13} strokeWidth={1.5} aria-hidden="true" /> {tageUeberfaellig(faelligkeitIso)}{" "}
                  {tageUeberfaellig(faelligkeitIso) === 1 ? "Tag" : "Tage"} überfällig
                </>
              ) : (
                <>Fällig: {new Date(faelligkeitIso).toLocaleDateString("de-DE")}</>
              )}
            </span>
          )
        )}
        {statusMeta ? (
          <p className="text-sekundaer text-label2">{statusMeta}</p>
        ) : (
          card.letztes_event_vorschau &&
          card.letztes_event_vorschau !== "Status geändert" && (
            <p className="line-clamp-2 rounded-[var(--radius-ap-sm)] bg-fill px-2 py-1.5 text-fliess text-label">
              {card.letztes_event_vorschau}
            </p>
          )
        )}
        {card.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {card.tags.map((tag) => (
              <span key={tag} className="rounded-[var(--radius-ap-sm)] bg-fill px-2 py-0.5 text-meta text-label">
                #{tag}
              </span>
            ))}
          </div>
        )}
      </button>
      <HauptkontaktZeile kontakt={card.hauptkontakt_vor_ort} />
      {(zeigeUebernehmen || zeigeStarten || zeigeFertigMelden || zeigeNachfragen) && (
        <div className="flex items-center justify-end gap-1.5 border-t-[0.5px] border-sep px-3 py-2">
          {aktionFehlerText && <span className="mr-auto text-sekundaer text-st-fehlt">{aktionFehlerText}</span>}
          {zeigeUebernehmen && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                zuweisenMutation.mutate();
              }}
              disabled={aktionLaeuft}
              className="btn-ap text-sekundaer"
            >
              <UserPlus size={13} strokeWidth={1.5} aria-hidden="true" /> Übernehmen
            </button>
          )}
          {zeigeStarten && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                statusMutation.mutate("in_arbeit");
              }}
              disabled={aktionLaeuft}
              className="btn-ap text-sekundaer"
            >
              <Play size={13} strokeWidth={1.5} aria-hidden="true" /> Starten
            </button>
          )}
          {zeigeFertigMelden && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                statusMutation.mutate("abgeschlossen");
              }}
              disabled={aktionLaeuft}
              className="btn-ap text-sekundaer"
            >
              <CheckCircle2 size={13} strokeWidth={1.5} aria-hidden="true" /> Fertig melden
            </button>
          )}
          {zeigeNachfragen && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                navigate(`/vorgaenge/${card.id}#email`);
              }}
              className="btn-ap text-sekundaer"
            >
              <Bell size={13} strokeWidth={1.5} aria-hidden="true" /> Nachfragen
            </button>
          )}
        </div>
      )}
    </Blueprint>
  );
}

export function FeedPage() {
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();
  const { felder, zustand, parameter, hatStatusBedingung, sortierung, setSortierung } = useVorgaengeFilter();
  const [ansicht, setAnsicht] = useState<"liste" | "karte">("liste");
  const [zeigeScanner, setZeigeScanner] = useState(false);
  const [scanFehler, setScanFehler] = useState<string | null>(null);

  const { data: stories } = useQuery({ queryKey: ["stories"], queryFn: storiesApi.get });
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list(), enabled: hatRecht("kunden", "sehen") });

  // Erledigte Vorgänge (abgeschlossen/abgerechnet/storniert) verdrängen sonst die offenen aus dem oberen
  // Feed-Bereich; ohne Status-Bedingung zeigt der Feed deshalb nur offene.
  const wirksamerFilter = useMemo(
    () => (hatStatusBedingung ? parameter : { ...parameter, status: OFFENE_STATUS_FILTER }),
    [parameter, hatStatusBedingung],
  );

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, error: ladeFehler, refetch: neuLaden } =
    useVorgangsListe(wirksamerFilter);

  const alleStatusZeigen = () => zustand.hinzufuegen({ feld: "status", op: "ist", wert: [...ALLE_STATUS] });
  const suchtext = zustand.sucheVerzoegert.trim();
  const nurOffene = !hatStatusBedingung;

  async function handleScan(code: string) {
    setZeigeScanner(false);
    setScanFehler(null);
    try {
      const anlage = await anlagenApi.byQrCode(code);
      navigate(`/anlagen/${anlage.id}`);
    } catch {
      setScanFehler(`Keine Anlage mit dem Code "${code}" gefunden.`);
    }
  }

  // Die Liste zeigt bewusst nur Seite fuer Seite ("Mehr laden"), aber die
  // Kartenansicht braucht alle zum aktuellen Filter passenden Vorgaenge auf
  // einmal, sonst wuerden Pins fehlen, die einfach noch nicht nachgeladen
  // wurden.
  useAlleSeitenLaden(ansicht === "karte", hasNextPage, fetchNextPage);

  const storyGroups = stories
    ? [...stories.wartet_kunde, ...stories.heute, ...stories.fristen]
    : [];
  const cards = data?.pages.flatMap((p) => p.items) ?? [];
  const punkte: FeedMapPunkt[] = cards
    .filter((c) => c.geo_lat != null && c.geo_lng != null)
    .map((c) => ({
      id: c.id,
      lng: c.geo_lng as number,
      lat: c.geo_lat as number,
      farbe: statusDotFarbe(vorgangStatusZuToken(c.status)),
    }));
  const ohneKoordinatenAnzahl = cards.length - punkte.length;

  const keinKundeZugewiesen =
    !!currentUser?.nur_zugewiesene_kunden && kunden !== undefined && kunden.length === 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        {hatRecht("vorgaenge", "erstellen") ? (
          <button onClick={() => navigate("/neu")} className="btn-touch btn-ap-primary px-4">
            <Plus size={16} strokeWidth={2} aria-hidden="true" /> Neuer Vorgang
          </button>
        ) : (
          <span />
        )}
        <div className="flex min-w-0 items-center gap-1">
          {istModulAktiv(currentUser, "highlights") && (
            <button
              onClick={() => navigate("/highlights")}
              aria-label="Highlights ansehen"
              className="btn-touch flex items-center gap-1 rounded-[13px] bg-fill px-2.5 text-sekundaer font-medium text-st-arbeit"
            >
              <Star size={14} strokeWidth={1.5} aria-hidden="true" /> Highlights
            </button>
          )}
          <button
            onClick={() => navigate("/suche")}
            aria-label="Suchen"
            title="Suchen"
            className="btn-touch btn-ap-toolbar"
          >
            <Search size={18} strokeWidth={2} aria-hidden="true" />
          </button>
          <button
            onClick={() => setZeigeScanner(true)}
            aria-label="QR-Code scannen"
            title="QR-Code scannen"
            className="btn-touch btn-ap-toolbar"
          >
            <ScanLine size={18} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      </div>

      {zeigeScanner && <QrScanner onScan={handleScan} onClose={() => setZeigeScanner(false)} />}
      {scanFehler && (
        <p role="alert" className="text-fliess text-st-fehlt">
          {scanFehler}
        </p>
      )}

      {storyGroups.length > 0 && (
        <div className="-mx-3 flex gap-2 overflow-x-auto px-3 pb-1">
          {storyGroups.map((item) => (
            <StoryChip key={`${item.ziel_typ}-${item.ziel_id}`} item={item} />
          ))}
        </div>
      )}

      <FilterLeiste
        felder={felder}
        zustand={zustand}
        suchPlatzhalter="Vorgang, Kunde, Anlage…"
        ansichten="vorgaenge"
        alteVorlageUmrechnen={alteVorlageUmrechnen}
      />
      <div className="flex items-center justify-end gap-1">
        <div className="flex shrink-0 items-center gap-1">
          <VorgaengeSortierMenue wert={sortierung} onWechsel={setSortierung} />
          <SegmentedControl
            ariaLabel="Ansicht"
            groesse="mobil"
            wert={ansicht}
            optionen={[
              { wert: "liste", label: "Liste" },
              { wert: "karte", label: "Karte" },
            ]}
            onChange={setAnsicht}
          />
        </div>
      </div>

      {nurOffene && (
        <p className="text-sekundaer text-label2">
          Nur offene Vorgänge ·{" "}
          <button type="button" onClick={alleStatusZeigen} className="font-medium text-tint-text">
            Alle zeigen
          </button>
        </p>
      )}

      {ansicht === "karte" ? (
        isLoading ? (
          <div className="h-[65vh] w-full animate-pulse rounded-lg bg-fill" />
        ) : ladeFehler && !data ? (
          <FehlerZustand fehler={ladeFehler} was="Die Vorgänge" onErneut={() => void neuLaden()} />
        ) : punkte.length === 0 ? (
          <EmptyState icon={MapIcon} text="Keine Vorgänge mit Standort gefunden." />
        ) : (
          <>
            <Suspense fallback={<div className="h-[65vh] w-full animate-pulse rounded-lg bg-fill" />}>
              <MapboxFeedMap
                punkte={punkte}
                onPunktClick={(id) => navigate(`/vorgaenge/${id}`)}
                className="h-[65vh] w-full rounded-lg"
              />
            </Suspense>
            {ohneKoordinatenAnzahl > 0 && (
              <p className="text-center text-sekundaer text-label2">
                {ohneKoordinatenAnzahl} von {cards.length} Vorgängen ohne Standort nicht auf der Karte angezeigt.
              </p>
            )}
            {hasNextPage && <p className="text-center text-sekundaer text-label2">Lädt weitere Vorgänge…</p>}
          </>
        )
      ) : (
        <>
          {isLoading ? (
            <SkeletonList count={4} />
          ) : ladeFehler && !data ? (
            <FehlerZustand fehler={ladeFehler} was="Die Vorgänge" onErneut={() => void neuLaden()} />
          ) : cards.length === 0 && keinKundeZugewiesen ? (
            <EmptyState
              icon={Users}
              text="Dir sind noch keine Kunden zugewiesen. Sobald das Büro dir Kunden zuweist, erscheinen hier deren Vorgänge."
            />
          ) : cards.length === 0 ? (
            <EmptyState
              icon={Inbox}
              text={
                suchtext
                  ? `Nichts gefunden für ‚${suchtext}‘`
                  : zustand.aktiveAnzahl > 0
                    ? "Keine Treffer für diese Filter"
                    : nurOffene
                      ? "Keine offenen Vorgänge. Erledigte und stornierte sind ausgeblendet."
                      : "Noch keine Vorgänge angelegt."
              }
              action={
                suchtext || zustand.aktiveAnzahl > 0 ? (
                  <button onClick={zustand.zuruecksetzen} className="btn-ap mt-1 text-sekundaer">
                    Filter zurücksetzen
                  </button>
                ) : (
                  nurOffene && (
                    <button onClick={alleStatusZeigen} className="btn-touch btn-ap mt-1">
                      Alle zeigen
                    </button>
                  )
                )
              }
            />
          ) : (
            <div className="space-y-5">
              {gruppiereNachFaelligkeit(cards).map(({ gruppe, cards: gruppenCards }) => (
                <div key={gruppe} className="space-y-3">
                  <div className="flex items-baseline gap-1.5 px-1">
                    <h2
                      className={`text-meta font-medium tracking-wide uppercase ${
                        gruppe === "ueberfaellig"
                          ? "text-st-fehlt"
                          : gruppe === "heute"
                            ? "text-st-arbeit"
                            : "text-label2"
                      }`}
                    >
                      {GRUPPEN_LABEL[gruppe]}
                    </h2>
                    <span className="text-sekundaer text-label2">{gruppenCards.length}</span>
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
              className="btn-ap w-full disabled:opacity-50"
            >
              {isFetchingNextPage ? "Lädt…" : "Mehr laden"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
