import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCircle2, Clock, Filter, Inbox, Map as MapIcon, MessageCircle, Play, Repeat, Star, UserPlus, X } from "lucide-react";
import { Suspense, lazy, useCallback, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenApi, storiesApi, vorgaengeApi } from "../../api/endpoints";
import Blueprint from "../../components/Blueprint";
import { FilterChip } from "../../components/apple/FilterChip";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { StatusPille } from "../../components/apple/StatusPille";
import { statusDotFarbe, vorgangStatusZuToken } from "../../components/apple/status";
import { EmptyState } from "../../components/EmptyState";
import { FilterVorlagenLeiste } from "../../components/FilterVorlagenLeiste";
import type { FeedMapPunkt } from "../../components/MapboxFeedMap";
import { SkeletonList } from "../../components/Skeleton";
import { GRUPPEN_LABEL, STATUS_LABEL, filterChipLabel, gruppiereNachFaelligkeit } from "../../config/vorgangDarstellung";
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
        <span className="line-clamp-2 text-xs font-semibold leading-tight text-label">{item.titel}</span>
        {item.subtitel && <span className="mt-0.5 block text-[11px] text-label2">{item.subtitel}</span>}
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
            <div className="text-[10px] tracking-wide text-label2">{card.vorgangsnummer}</div>
            <div className="mt-0.5 font-semibold text-label">{card.titel}</div>
            <div className="text-xs text-label2">{card.kunde_name}</div>
            {(card.anlage_bezeichnung || card.standort_bezeichnung) && (
              <div className="text-xs text-label2">
                {[card.anlage_bezeichnung, card.standort_bezeichnung].filter(Boolean).join(" · ")}
              </div>
            )}
            {card.anlage_kurzadresse && <div className="text-xs text-label2">{card.anlage_kurzadresse}</div>}
            {card.ersteller_name && <div className="text-xs text-label2">von {card.ersteller_name}</div>}
            {!["abgeschlossen", "abgerechnet", "storniert"].includes(card.status) && (
              <div className="text-xs text-label2">
                {card.zugewiesener_name ? `Zugewiesen: ${card.zugewiesener_name}` : "Nicht zugewiesen"}
              </div>
            )}
          </div>
          <div className="flex flex-none flex-col items-end gap-1">
            {card.timer_laeuft && (
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-st-fehlt-dot" title="Timer läuft" />
            )}
            {card.dauerauftrag_id && (
              <span title="Dauerauftrag" className="text-st-arbeit">
                <Repeat size={14} strokeWidth={1.5} aria-hidden="true" />
              </span>
            )}
            <StatusPille status={vorgangStatusZuToken(card.status)} label={STATUS_LABEL[card.status]} />
            <span className="whitespace-nowrap text-xs text-label2">
              {LEISTUNGSTYP_LABEL[card.leistungstyp] ?? card.leistungstyp}
            </span>
          </div>
        </div>
        {card.status === "wartet_kunde" ? (
          <span className="flex items-center gap-1 text-xs text-label2">
            <MessageCircle size={13} strokeWidth={1.5} aria-hidden="true" /> Wartet auf Rückmeldung
          </span>
        ) : (
          faelligkeitIso && (
            <span className={`flex items-center gap-1 text-xs font-medium ${faelligkeitsFarbe(faelligkeitIso)}`}>
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
        {card.letztes_event_vorschau && (
          <p className="line-clamp-2 rounded-[var(--radius-ap-sm)] bg-fill px-2 py-1.5 text-sm text-label">
            {card.letztes_event_vorschau}
          </p>
        )}
        {card.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {card.tags.map((tag) => (
              <span key={tag} className="rounded-[var(--radius-ap-sm)] bg-fill px-2 py-0.5 text-xs text-label2">
                #{tag}
              </span>
            ))}
          </div>
        )}
      </button>
      {(zeigeUebernehmen || zeigeStarten || zeigeFertigMelden || zeigeNachfragen) && (
        <div className="flex items-center justify-end gap-1.5 border-t-[0.5px] border-sep px-3 py-2">
          {aktionFehlerText && <span className="mr-auto text-xs text-st-fehlt">{aktionFehlerText}</span>}
          {zeigeUebernehmen && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                zuweisenMutation.mutate();
              }}
              disabled={aktionLaeuft}
              className="btn-ap text-xs"
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
              className="btn-ap text-xs"
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
              className="btn-ap text-xs"
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
              className="btn-ap text-xs"
            >
              <Bell size={13} strokeWidth={1.5} aria-hidden="true" /> Nachfragen
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
  // Einstiegsfilter aus der URL (z. B. von der mobilen Projekte-Uebersicht
  // per Tippen auf ein Projekt, oder vom "Heute"-Tab der Tab-Bar) -- nur
  // beim ersten Rendern gelesen, danach lebt der Filter ausschliesslich im
  // lokalen State wie zuvor.
  const [searchParams] = useSearchParams();
  const [filter, setFilter] = useState<Record<string, string>>(() => {
    const uebernommen: Record<string, string> = {};
    for (const key of ["projekt_id", "faellig_von", "faellig_bis"]) {
      const wert = searchParams.get(key);
      if (wert) uebernommen[key] = wert;
    }
    return Object.keys(uebernommen).length > 0 ? uebernommen : LEER_FILTER;
  });
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
    .map((c) => ({
      id: c.id,
      lng: c.geo_lng as number,
      lat: c.geo_lat as number,
      farbe: statusDotFarbe(vorgangStatusZuToken(c.status)),
    }));
  const ohneKoordinatenAnzahl = cards.length - punkte.length;

  return (
    <div className="space-y-4">
      {istModulAktiv(currentUser, "highlights") && (
        <button
          onClick={() => navigate("/highlights")}
          className="btn-touch flex w-full items-center justify-center gap-2 rounded-[var(--radius-ap-input)] bg-fill py-2.5 text-sm font-medium text-st-arbeit"
        >
          <Star size={15} strokeWidth={1.5} aria-hidden="true" /> Highlights ansehen
        </button>
      )}

      <SegmentedControl
        ariaLabel="Vorgänge filtern"
        groesse="mobil"
        volleBreite
        wert={nurMeine ? "meine" : "alle"}
        optionen={[
          { wert: "meine", label: "Meine Vorgänge" },
          { wert: "alle", label: "Alle" },
        ]}
        onChange={(wert) => setField("nur_meine", wert === "meine" ? "true" : "")}
      />

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
          <FilterChip
            label="Überfällig"
            aktiv={filter.faellig_bis === heuteIso() && !filter.faellig_von}
            onClick={() => setField("faellig_bis", filter.faellig_bis === heuteIso() ? "" : heuteIso())}
          />
          <FilterChip
            label="Diese Woche fällig"
            aktiv={filter.faellig_bis === heuteIso(7)}
            onClick={() => setField("faellig_bis", filter.faellig_bis === heuteIso(7) ? "" : heuteIso(7))}
          />
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            onClick={() => setZeigeFilter((v) => !v)}
            title="Filter"
            aria-label="Filter"
            className={`btn-ap-toolbar relative ${zeigeFilter || aktiveFilterAnzahl > 0 ? "text-tint" : ""}`}
          >
            <Filter size={14} strokeWidth={2} aria-hidden="true" />
            {aktiveFilterAnzahl > 0 && (
              <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-tint-solid text-[9px] font-bold text-white">
                {aktiveFilterAnzahl}
              </span>
            )}
          </button>
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

      {filterChips.length > 0 && !zeigeFilter && (
        <div className="card-ap flex flex-wrap items-center gap-1.5 p-2.5">
          {filterChips.map((c) => (
            <span
              key={c.key}
              className="flex items-center gap-1.5 rounded-[13px] bg-fill py-1 pr-1.5 pl-2.5 text-xs font-medium text-label"
            >
              {c.label}
              <button
                onClick={() => setField(c.key, "")}
                aria-label={`${c.label} entfernen`}
                className="flex h-4 w-4 items-center justify-center rounded-full bg-fill2 text-label2"
              >
                <X size={9} strokeWidth={2.5} aria-hidden="true" />
              </button>
            </span>
          ))}
          <button onClick={() => setZeigeFilter(true)} className="ml-auto text-xs font-semibold text-tint">
            Bearbeiten
          </button>
        </div>
      )}

      {zeigeFilter && (
        <div className="card-ap space-y-2 p-3">
          <div>
            <div className="mb-1 text-xs font-medium text-label2">Status (Mehrfachauswahl möglich)</div>
            <div className="flex flex-wrap gap-1.5">
              {(Object.keys(STATUS_LABEL) as VorgangStatus[]).map((value) => {
                const aktiv = aktiveStatus.includes(value);
                return (
                  <FilterChip
                    key={value}
                    label={STATUS_LABEL[value]}
                    status={vorgangStatusZuToken(value)}
                    aktiv={aktiv}
                    onClick={() => toggleStatus(value)}
                  />
                );
              })}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <select
              value={filter.kunde_id ?? ""}
              onChange={(e) => setField("kunde_id", e.target.value)}
              className="field-ap"
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
              className="field-ap"
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
                className="field-ap"
              />
              <span className="text-xs text-label2">bis</span>
              <input
                type="date"
                value={filter.faellig_bis ?? ""}
                onChange={(e) => setField("faellig_bis", e.target.value)}
                title="Fällig bis"
                className="field-ap"
              />
            </div>
            <input
              value={filter.tag ?? ""}
              onChange={(e) => setField("tag", e.target.value)}
              placeholder="#Tag"
              className="field-ap"
            />
            <select
              value={filter.sort ?? "last_activity_at"}
              onChange={(e) => setField("sort", e.target.value)}
              className="field-ap"
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
          <div className="h-[65vh] w-full animate-pulse rounded-lg bg-fill" />
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
              <p className="text-center text-xs text-label2">
                {ohneKoordinatenAnzahl} von {cards.length} Vorgängen ohne Standort nicht auf der Karte angezeigt.
              </p>
            )}
            {hasNextPage && <p className="text-center text-xs text-label2">Lädt weitere Vorgänge…</p>}
          </>
        )
      ) : (
        <>
          {isLoading ? (
            <SkeletonList count={4} />
          ) : cards.length === 0 ? (
            <EmptyState
              icon={Inbox}
              text={aktiveFilterAnzahl > 0 ? "Keine Vorgänge für die aktuellen Filter." : "Keine Vorgänge gefunden."}
              action={
                aktiveFilterAnzahl > 0 && (
                  <button
                    onClick={() => setFilter((f) => (f.nur_meine ? { nur_meine: f.nur_meine } : LEER_FILTER))}
                    className="btn-ap mt-1 text-xs"
                  >
                    Filter zurücksetzen
                  </button>
                )
              }
            />
          ) : (
            <div className="space-y-5">
              {gruppiereNachFaelligkeit(cards).map(({ gruppe, cards: gruppenCards }) => (
                <div key={gruppe} className="space-y-3">
                  <div className="flex items-baseline gap-1.5 px-1">
                    <h3
                      className={`text-[10px] font-medium tracking-[0.14em] uppercase ${
                        gruppe === "ueberfaellig"
                          ? "text-st-fehlt"
                          : gruppe === "heute"
                            ? "text-st-arbeit"
                            : "text-label2"
                      }`}
                    >
                      {GRUPPEN_LABEL[gruppe]}
                    </h3>
                    <span className="text-xs text-label2">{gruppenCards.length}</span>
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
