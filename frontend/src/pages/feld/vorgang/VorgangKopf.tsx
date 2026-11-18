import { CalendarClock, ChevronDown, Clock, ExternalLink, Flag, GitBranch, Link2, MoreHorizontal, Pencil, Trash2, User, UserCheck } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { PulldownMenu, type PulldownItem } from "../../../components/apple/PulldownMenu";
import { VorgangStatusPille } from "../../../components/VorgangStatusPille";
import type { Adresse, Anlage, CurrentUser, Kunde, Standort, UserAuswahl, Vorgang, VorgangStatus } from "../../../types";
import { heuteIso } from "../../../utils/format";
import { PRIORITAET_OPTIONEN, VORGANG_STATUS_GESCHLOSSEN, adresseAlsZeile } from "./konstanten";
import { VorgangStatusAktionen } from "./VorgangStatusAktionen";

const CHIP = "inline-flex items-center gap-1.5 rounded-[var(--radius-ap-pill)] px-2.5 py-1 text-sekundaer font-medium whitespace-nowrap";
const CHIP_NEUTRAL = `${CHIP} bg-fill text-label`;
const CHIP_BUTTON = `min-h-11 md:min-h-8 ${CHIP_NEUTRAL} hover:bg-fill2`;

/** Kleines Popover für Chips mit Suche/Datum (PulldownMenu kann nur Einträge).
 * Esc und Klick außerhalb schließen; Esc gibt den Fokus an den Chip zurück. */
function ChipPopover({
  chip,
  label,
  children,
}: {
  chip: (p: { offen: boolean; toggeln: () => void }) => ReactNode;
  label: string;
  children: (schliessen: () => void) => ReactNode;
}) {
  const [offen, setOffen] = useState(false);
  const wurzel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!offen) return;
    const aussen = (e: MouseEvent) => {
      if (wurzel.current && !wurzel.current.contains(e.target as Node)) setOffen(false);
    };
    const taste = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation(); // Esc soll ein umgebendes Seitenpanel nicht mitschließen
      setOffen(false);
      wurzel.current?.querySelector<HTMLElement>("button")?.focus();
    };
    document.addEventListener("mousedown", aussen);
    document.addEventListener("keydown", taste);
    return () => {
      document.removeEventListener("mousedown", aussen);
      document.removeEventListener("keydown", taste);
    };
  }, [offen]);
  return (
    <div ref={wurzel} className="relative">
      {chip({ offen, toggeln: () => setOffen((v) => !v) })}
      {offen && (
        <div
          role="dialog"
          aria-label={label}
          className="absolute top-full left-0 z-40 mt-1 w-64 rounded-[10px] border-[0.5px] p-[5px]"
          style={{ backgroundColor: "var(--menu)", borderColor: "var(--sepstrong)", boxShadow: "0 10px 30px rgba(0,0,0,.22)" }}
        >
          {children(() => setOffen(false))}
        </div>
      )}
    </div>
  );
}

const POPOVER_EINTRAG =
  "flex min-h-[30px] w-full items-center gap-2 rounded-[6px] px-2 text-left text-sekundaer text-label hover:bg-tint-solid hover:text-white focus-visible:bg-tint-solid focus-visible:text-white focus-visible:outline-none disabled:opacity-40";

function tageUeberfaellig(faelligkeitAm: string): number {
  return Math.round((new Date().setHours(0, 0, 0, 0) - new Date(faelligkeitAm).setHours(0, 0, 0, 0)) / (1000 * 60 * 60 * 24));
}

export function VorgangKopf({
  vorgang,
  kunde,
  anlage,
  standort,
  anzeigeAdresse,
  layout,
  primaerAktionKlebt,
  kannDisponieren,
  kannLoeschen,
  currentUser,
  users,
  naechsterTermin,
  navigate,
  onZurueck,
  onGanzeSeite,
  onLinkKopieren,
  onPrioritaet,
  onZuweisen,
  onUebernehmen,
  uebernehmenPending,
  onFaelligkeit,
  onTerminOeffnen,
  statusPending,
  onStatusWaehle,
  rechnung,
  onZeitErfassen,
  onFolgeVorgang,
  onZuordnungAendern,
  onLoeschen,
  loeschenPending,
  children,
}: {
  vorgang: Vorgang;
  kunde: Kunde | undefined;
  anlage: Anlage | undefined;
  standort: Standort | undefined;
  anzeigeAdresse: Adresse | null;
  layout: "kompakt" | "dicht";
  /** Feld-App: die klebende Leiste ist die Hauptaktion, die Aktionsleiste hier wird sekundär. */
  primaerAktionKlebt: boolean;
  kannDisponieren: boolean;
  kannLoeschen: boolean;
  currentUser: CurrentUser | undefined;
  users: UserAuswahl[] | undefined;
  naechsterTermin: { start_at: string } | undefined;
  navigate: (to: string) => void;
  onZurueck: () => void;
  onGanzeSeite?: () => void;
  onLinkKopieren: () => void;
  onPrioritaet: (prioritaet: number) => void;
  onZuweisen: (userId: string | null) => void;
  onUebernehmen: () => void;
  uebernehmenPending: boolean;
  onFaelligkeit: (datum: string | null) => void;
  onTerminOeffnen: () => void;
  statusPending: boolean;
  onStatusWaehle: (status: VorgangStatus) => void;
  /** Gesetzt, wenn die Seite "Rechnung erstellen" anbietet (abgeschlossen + Recht). */
  rechnung: { onClick: () => void; pending: boolean } | null;
  /** Gesetzt, wenn Zeit erfassbar ist (nicht bei gesperrten Status). */
  onZeitErfassen: (() => void) | null;
  onFolgeVorgang: () => void;
  onZuordnungAendern: () => void;
  onLoeschen: () => void;
  loeschenPending: boolean;
  children?: ReactNode;
}) {
  const dicht = layout === "dicht";
  const geschlossen = VORGANG_STATUS_GESCHLOSSEN.includes(vorgang.status);
  const istMir = !!currentUser && vorgang.zugewiesener_user_id === currentUser.id;
  const adresseText = adresseAlsZeile(anzeigeAdresse);

  const menue: PulldownItem[] = [
    ...(onGanzeSeite ? [{ label: "In ganzer Seite öffnen", icon: ExternalLink, onSelect: onGanzeSeite }] : []),
    { label: "Link kopieren", icon: Link2, onSelect: onLinkKopieren },
    { label: "Folge-Vorgang anlegen", icon: GitBranch, onSelect: onFolgeVorgang },
    { label: "Kunde / Anlage ändern", icon: Pencil, onSelect: onZuordnungAendern },
    ...(kannLoeschen ? (["trenner", { label: "Vorgang löschen", icon: Trash2, destruktiv: true, onSelect: onLoeschen }] as PulldownItem[]) : []),
  ];

  // Priorität
  const prioChip = vorgang.dauerauftrag_id ? (
    <span title="Wird beim Dauerauftrag automatisch anhand der Fälligkeit berechnet" className={CHIP_NEUTRAL}>
      <Flag size={13} strokeWidth={1.5} aria-hidden="true" />
      {dicht ? `Priorität ${vorgang.prioritaet} · automatisch` : `Prio ${vorgang.prioritaet}`}
    </span>
  ) : geschlossen ? (
    <span className={CHIP_NEUTRAL}>
      <Flag size={13} strokeWidth={1.5} aria-hidden="true" />
      {dicht ? `Priorität ${vorgang.prioritaet}` : `Prio ${vorgang.prioritaet}`}
    </span>
  ) : (
    <PulldownMenu
      ariaLabel="Priorität ändern"
      items={PRIORITAET_OPTIONEN.map((p) => ({
        label: `Priorität ${p}`,
        aktiv: p === vorgang.prioritaet,
        onSelect: () => onPrioritaet(p),
      }))}
      trigger={({ offen, toggeln, triggerRef }) => (
        <button ref={triggerRef} type="button" onClick={toggeln} aria-haspopup="menu" aria-expanded={offen} className={CHIP_BUTTON}>
          <Flag size={13} strokeWidth={1.5} aria-hidden="true" />
          {dicht ? `Priorität ${vorgang.prioritaet}` : `Prio ${vorgang.prioritaet}`}
          <ChevronDown size={13} strokeWidth={2} aria-hidden="true" />
        </button>
      )}
    />
  );

  // Zuständig: Personenauswahl nur mit Disporecht + geladener Nutzerliste,
  // sonst bleibt "Mir zuweisen" (Selbstübernehmen) als einziger Weg.
  const darfAnderenZuweisen = kannDisponieren && !!users;
  const darfMirZuweisen = !!currentUser?.darf_vorgaenge_selbst_uebernehmen && !istMir;
  const zustaendigText = istMir && !dicht ? "Ich" : vorgang.zugewiesener_name ?? "Nicht zugewiesen";
  const zustaendigInhalt = (
    <>
      <User size={13} strokeWidth={1.5} aria-hidden="true" />
      <span className={vorgang.zugewiesener_user_id ? "" : "text-label2"}>{zustaendigText}</span>
    </>
  );
  const zustaendigChip =
    geschlossen || (!darfAnderenZuweisen && !darfMirZuweisen) ? (
      <span className={CHIP_NEUTRAL}>{zustaendigInhalt}</span>
    ) : (
      <ZustaendigPopover
        chipInhalt={zustaendigInhalt}
        users={darfAnderenZuweisen ? users! : []}
        aktuellId={vorgang.zugewiesener_user_id}
        darfMirZuweisen={darfMirZuweisen}
        darfEntfernen={darfAnderenZuweisen}
        onMir={onUebernehmen}
        onWaehle={onZuweisen}
      />
    );

  // Fälligkeit
  const ueberfaellig = !!vorgang.faelligkeit_am && vorgang.faelligkeit_am.slice(0, 10) < heuteIso() && !geschlossen;
  const faelligText = !vorgang.faelligkeit_am
    ? "Keine Fälligkeit"
    : ueberfaellig
      ? `${tageUeberfaellig(vorgang.faelligkeit_am)} Tage überfällig`
      : `${dicht ? "Fällig " : ""}${new Date(vorgang.faelligkeit_am).toLocaleDateString("de-DE")}`;
  const faelligInhalt = (
    <>
      <Clock size={13} strokeWidth={1.5} aria-hidden="true" />
      <span className={!vorgang.faelligkeit_am ? "text-label2" : ""}>{faelligText}</span>
    </>
  );
  const faelligKlasse = ueberfaellig ? `${CHIP} bg-st-fehlt-bg text-st-fehlt` : CHIP_NEUTRAL;
  const faelligChip = !dicht && !vorgang.faelligkeit_am ? null : !kannDisponieren || geschlossen ? (
    <span className={faelligKlasse}>{faelligInhalt}</span>
  ) : (
    <ChipPopover
      label="Fälligkeit ändern"
      chip={({ offen, toggeln }) => (
        <button
          type="button"
          onClick={toggeln}
          aria-haspopup="dialog"
          aria-expanded={offen}
          className={`min-h-11 md:min-h-8 ${faelligKlasse} ${ueberfaellig ? "" : "hover:bg-fill2"}`}
        >
          {faelligInhalt}
          <ChevronDown size={13} strokeWidth={2} aria-hidden="true" />
        </button>
      )}
    >
      {(schliessen) => (
        <div className="space-y-2 p-1">
          <input
            type="date"
            aria-label="Fälligkeitsdatum"
            autoFocus
            defaultValue={vorgang.faelligkeit_am?.slice(0, 10) ?? ""}
            onChange={(e) => {
              if (!e.target.value) return;
              onFaelligkeit(e.target.value);
              schliessen();
            }}
            className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
          />
          {vorgang.faelligkeit_am && (
            <button
              type="button"
              onClick={() => {
                onFaelligkeit(null);
                schliessen();
              }}
              className={`${POPOVER_EINTRAG} text-st-fehlt hover:bg-st-fehlt-bg hover:text-st-fehlt`}
            >
              Fälligkeit entfernen
            </button>
          )}
        </div>
      )}
    </ChipPopover>
  );

  const terminChip =
    dicht && naechsterTermin ? (
      <button type="button" onClick={onTerminOeffnen} className={CHIP_BUTTON}>
        <CalendarClock size={13} strokeWidth={1.5} aria-hidden="true" />
        <span className="text-label2">Termin</span>
        {new Date(naechsterTermin.start_at).toLocaleString("de-DE", {
          weekday: "short",
          day: "2-digit",
          month: "2-digit",
          hour: "numeric",
          minute: "2-digit",
        })}
      </button>
    ) : null;

  const aktionsleiste = (
    <VorgangStatusAktionen
      status={vorgang.status}
      darfAendern={kannDisponieren}
      pending={statusPending}
      primaer={!primaerAktionKlebt}
      onWaehle={onStatusWaehle}
      ersatzSchritt={rechnung ? { label: "Rechnung erstellen", onClick: rechnung.onClick, disabled: rechnung.pending } : undefined}
    >
      {!primaerAktionKlebt && (vorgang.status === "neu" || vorgang.status === "geplant") && darfMirZuweisen && (
        <button type="button" onClick={onUebernehmen} disabled={uebernehmenPending} className="min-h-11 md:min-h-8 btn-ap text-sekundaer whitespace-nowrap px-3">
          <UserCheck size={14} strokeWidth={2} aria-hidden="true" /> Übernehmen
        </button>
      )}
      {!primaerAktionKlebt && vorgang.status === "in_arbeit" && onZeitErfassen && (
        <button type="button" onClick={onZeitErfassen} className="min-h-11 md:min-h-8 btn-ap text-sekundaer whitespace-nowrap px-3">
          <Clock size={14} strokeWidth={2} aria-hidden="true" /> Zeit erfassen
        </button>
      )}
    </VorgangStatusAktionen>
  );

  return (
    <>
      <div className={`flex items-center justify-between ${dicht ? "gap-2 border-b-[0.5px] border-sep pb-2" : ""}`}>
        <button onClick={onZurueck} className="text-sekundaer text-label2">
          ← Zurück
        </button>
        <div className="flex items-center gap-1">
          {dicht && onGanzeSeite && (
            <button
              type="button"
              onClick={onGanzeSeite}
              aria-label="Ganze Seite"
              title="Ganze Seite"
              className="btn-touch flex items-center justify-center text-label2 hover:text-label"
            >
              <ExternalLink size={18} strokeWidth={2} aria-hidden="true" />
            </button>
          )}
          <PulldownMenu
            ariaLabel="Weitere Aktionen"
            ausrichtung="rechts"
            items={menue}
            trigger={({ offen, toggeln, triggerRef }) => (
              <button
                ref={triggerRef}
                type="button"
                onClick={toggeln}
                aria-haspopup="menu"
                aria-expanded={offen}
                aria-label="Weitere Aktionen"
                disabled={loeschenPending}
                className="btn-touch flex items-center justify-center text-label2 hover:text-label disabled:opacity-50"
              >
                <MoreHorizontal size={20} strokeWidth={2} aria-hidden="true" />
              </button>
            )}
          />
        </div>
      </div>

      <div>
        <div className="flex items-center gap-2">
          <span className="text-sekundaer text-label2">{vorgang.vorgangsnummer}</span>
          <VorgangStatusPille status={vorgang.status} />
        </div>
        <h1 className="font-heading text-titel-mobil font-bold text-label">{vorgang.titel}</h1>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-fliess">
          {kunde && (
            <button onClick={() => navigate(`/kunden/${kunde.id}`)} className="text-tint-text underline-offset-2 hover:underline">
              {kunde.name}
            </button>
          )}
          {anlage ? (
            <>
              <span className="text-label2">·</span>
              <button onClick={() => navigate(`/anlagen/${anlage.id}`)} className="text-tint-text underline-offset-2 hover:underline">
                {anlage.bezeichnung}
              </button>
            </>
          ) : (
            standort && (
              <>
                <span className="text-label2">·</span>
                <span className="text-label">{standort.bezeichnung}</span>
              </>
            )
          )}
          {adresseText && (
            <>
              <span className="text-label2">·</span>
              <span className="text-label2">{adresseText}</span>
            </>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {prioChip}
        {zustaendigChip}
        {faelligChip}
        {terminChip}
      </div>

      {aktionsleiste}

      {children}
    </>
  );
}

function ZustaendigPopover({
  chipInhalt,
  users,
  aktuellId,
  darfMirZuweisen,
  darfEntfernen,
  onMir,
  onWaehle,
}: {
  chipInhalt: ReactNode;
  users: UserAuswahl[];
  aktuellId: string | null;
  darfMirZuweisen: boolean;
  darfEntfernen: boolean;
  onMir: () => void;
  onWaehle: (userId: string | null) => void;
}) {
  const [suche, setSuche] = useState("");
  const treffer = users.filter((u) => u.aktiv && u.name.toLowerCase().includes(suche.trim().toLowerCase()));
  return (
    <ChipPopover
      label="Zuständig ändern"
      chip={({ offen, toggeln }) => (
        <button type="button" onClick={toggeln} aria-haspopup="dialog" aria-expanded={offen} className={CHIP_BUTTON}>
          {chipInhalt}
          <ChevronDown size={13} strokeWidth={2} aria-hidden="true" />
        </button>
      )}
    >
      {(schliessen) => (
        <div className="space-y-1">
          {users.length > 0 && (
            <input
              autoFocus
              value={suche}
              onChange={(e) => setSuche(e.target.value)}
              placeholder="Person suchen…"
              aria-label="Person suchen"
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1 text-sekundaer text-label"
            />
          )}
          {darfMirZuweisen && (
            <button
              type="button"
              onClick={() => {
                onMir();
                schliessen();
              }}
              className={`${POPOVER_EINTRAG} font-medium`}
            >
              <UserCheck size={14} strokeWidth={2} aria-hidden="true" /> Mir zuweisen
            </button>
          )}
          <div className="max-h-56 overflow-y-auto">
            {treffer.map((u) => (
              <button
                key={u.id}
                type="button"
                onClick={() => {
                  if (u.id !== aktuellId) onWaehle(u.id);
                  schliessen();
                }}
                className={POPOVER_EINTRAG}
              >
                <span className="flex-1">{u.name}</span>
                {u.id === aktuellId && <span aria-hidden="true">✓</span>}
              </button>
            ))}
            {users.length > 0 && treffer.length === 0 && <p className="px-2 py-1 text-sekundaer text-label2">Keine Treffer.</p>}
          </div>
          {darfEntfernen && aktuellId && (
            <button
              type="button"
              onClick={() => {
                onWaehle(null);
                schliessen();
              }}
              className={`${POPOVER_EINTRAG} text-st-fehlt hover:bg-st-fehlt-bg hover:text-st-fehlt`}
            >
              Zuweisung entfernen
            </button>
          )}
        </div>
      )}
    </ChipPopover>
  );
}
