import { AlertTriangle, KeyRound, Pencil, Phone, Star, Trash2, UserRound } from "lucide-react";

import { AktionsMenue, type AktionsMenueEintrag } from "../../../components/AktionsMenue";
import { Monogramm } from "../../../components/apple/Monogramm";
import { PulldownMenu, type PulldownItem } from "../../../components/apple/PulldownMenu";
import { VOR_ORT_ROLLE_LABEL, type VorOrtKontaktZugeordnet, type VorOrtRolle, type VorOrtZiel } from "../../../types";
import { herkunftText, istAnonymisiert, kontaktAnzeigename, kontaktUnterzeile, telHref } from "../../../utils/vorOrt";

export function RollenChip({ rolle }: { rolle: VorOrtRolle }) {
  return (
    <span className="shrink-0 rounded-[var(--radius-ap-pill)] bg-fill px-2 py-0.5 text-meta font-medium text-label">
      {VOR_ORT_ROLLE_LABEL[rolle]}
    </span>
  );
}

export function HauptkontaktTag() {
  return (
    <span className="flex shrink-0 items-center gap-1 text-meta text-label2">
      <Star size={12} strokeWidth={2} className="fill-current text-st-arbeit-dot" aria-hidden="true" />
      Hauptkontakt
    </span>
  );
}

/** Anruf-Knopf als `tel:`-Link. Feld: grüner Kreis (44 px Tippfläche), Office: kompakter Link. */
export function AnrufKnopf({ telefon, name, layout }: { telefon: string; name: string; layout: "feld" | "office" }) {
  if (layout === "feld") {
    return (
      <a
        href={telHref(telefon)}
        aria-label={`${name} anrufen`}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-st-erledigt-bg text-st-erledigt"
      >
        <Phone size={20} strokeWidth={2} aria-hidden="true" />
      </a>
    );
  }
  return (
    <a
      href={telHref(telefon)}
      aria-label={`${name} anrufen`}
      className="inline-flex shrink-0 items-center gap-1.5 text-sekundaer font-medium text-tint-text hover:underline"
    >
      <Phone size={14} strokeWidth={2} aria-hidden="true" />
      {telefon}
    </a>
  );
}

/** Hinweise zum Schlüssel bekommen ein Schlüssel-Symbol, alle anderen das Warnzeichen. */
export function hinweisIstSchluessel(text: string): boolean {
  return /schl(ü|ue)ssel/i.test(text);
}

export function HinweisZeile({ text, layout }: { text: string; layout: "feld" | "office" }) {
  const Icon = hinweisIstSchluessel(text) ? KeyRound : AlertTriangle;
  return (
    <p
      className={
        layout === "feld"
          ? "flex items-start gap-2 rounded-[var(--radius-ap-md)] bg-st-arbeit-bg px-3 py-2 text-sekundaer text-st-arbeit"
          : "flex items-start gap-1.5 text-sekundaer text-st-arbeit"
      }
    >
      <Icon size={14} strokeWidth={2} className="mt-0.5 shrink-0" aria-hidden="true" />
      <span className="min-w-0">{text}</span>
    </p>
  );
}

/** Eine Zeile der Kontaktliste. Geerbte Einträge (Herkunft ≠ Ziel) tragen eine Herkunftszeile und kein Menü. */
export function KontaktZeile({
  eintrag,
  ziel,
  layout,
  darfBearbeiten,
  darfKorrigieren = false,
  onHauptkontakt,
  onBearbeiten,
  onEntfernen,
  herkunftAusblenden = false,
}: {
  eintrag: VorOrtKontaktZugeordnet;
  ziel: VorOrtZiel;
  layout: "feld" | "office";
  darfBearbeiten: boolean;
  darfKorrigieren?: boolean;
  onHauptkontakt: (haupt: boolean) => void;
  onBearbeiten: () => void;
  onEntfernen: () => void;
  /** Die Herkunft steht schon in der Fußnote des Abschnitts ("Vom Auftrag … übernommen"). */
  herkunftAusblenden?: boolean;
}) {
  const k = eintrag.kontakt;
  const anonym = istAnonymisiert(k);
  const name = kontaktAnzeigename(k);
  const unterzeile = anonym ? [k.einheit].filter(Boolean).join("") : kontaktUnterzeile(k);
  const herkunftVoll = herkunftText(eintrag, ziel);
  const eigen = herkunftVoll === null;
  const herkunft = herkunftAusblenden ? null : herkunftVoll;
  const feld = layout === "feld";

  // Wer nur korrigieren darf, sieht allein "Bearbeiten" -- auch an geerbten Einträgen, weil der Kontakt selbst geändert wird.
  const nurKorrigieren = darfKorrigieren && !(eigen && darfBearbeiten);
  const menueKorrigieren: AktionsMenueEintrag[] = [{ label: "Bearbeiten", icon: Pencil, onClick: onBearbeiten }];
  const menue: (AktionsMenueEintrag | "trenner")[] = [
    ...(!anonym
      ? [
          {
            label: eintrag.ist_hauptkontakt ? "Hauptkontakt aufheben" : "Als Hauptkontakt setzen",
            icon: Star,
            onClick: () => onHauptkontakt(!eintrag.ist_hauptkontakt),
          },
          { label: "Bearbeiten", icon: Pencil, onClick: onBearbeiten },
          "trenner" as const,
        ]
      : []),
    { label: "Entfernen", icon: Trash2, destruktiv: true, onClick: onEntfernen },
  ];

  const eintraege = nurKorrigieren && !anonym ? menueKorrigieren : !nurKorrigieren && eigen && darfBearbeiten ? menue : null;
  // Feld: Die Zeile selbst öffnet das Menü, damit die Textspalte neben dem Anruf-Knopf die volle Breite bekommt.
  const zeileAlsMenue = feld && eintraege !== null;

  const textspalte = (
    <>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className={`${feld ? "text-zeile" : "text-fliess"} font-medium ${anonym ? "text-label3" : "text-label"}`}>{name}</span>
        <RollenChip rolle={k.rolle} />
        {eintrag.ist_hauptkontakt && <HauptkontaktTag />}
      </div>
      {unterzeile && <p className="text-sekundaer text-label2">{unterzeile}</p>}
      {herkunft && <p className="text-meta text-label2">{herkunft}</p>}
      {!anonym && k.hinweis && <HinweisZeile text={k.hinweis} layout={layout} />}
      {!anonym && k.telefon && !feld && <AnrufKnopf telefon={k.telefon} name={name} layout={layout} />}
    </>
  );

  return (
    <li className={`flex items-start gap-3 ${feld ? "py-3" : "py-2.5"}`}>
      {anonym ? (
        <span
          className="flex shrink-0 items-center justify-center rounded-full bg-fill text-label3"
          style={{ width: feld ? 40 : 32, height: feld ? 40 : 32 }}
          aria-hidden="true"
        >
          <UserRound size={feld ? 20 : 16} strokeWidth={1.75} />
        </span>
      ) : (
        <Monogramm name={name} groesse={feld ? 40 : 32} ringKlasse="ring-card" />
      )}
      {zeileAlsMenue ? (
        <PulldownMenu
          ariaLabel={`Aktionen für ${name}`}
          items={eintraege.map((e): PulldownItem => (e === "trenner" ? e : { ...e, onSelect: e.onClick }))}
          trigger={({ offen, toggeln, triggerRef }) => (
            <button
              ref={triggerRef}
              type="button"
              onClick={toggeln}
              aria-label={`Aktionen für ${name}`}
              aria-haspopup="menu"
              aria-expanded={offen}
              className="min-w-0 flex-1 space-y-1 text-left"
            >
              {textspalte}
            </button>
          )}
        />
      ) : (
        <div className="min-w-0 flex-1 space-y-1">{textspalte}</div>
      )}
      {!anonym && k.telefon && feld && <AnrufKnopf telefon={k.telefon} name={name} layout={layout} />}
      {!feld && eintraege && <AktionsMenue label={`Aktionen für ${name}`} eintraege={eintraege} />}
    </li>
  );
}
