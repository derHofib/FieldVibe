import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from "react";

import { Package } from "lucide-react";

import { VORGANG_STATUS_LABEL, vorgangStatusZuToken } from "../../../components/apple/status";
import type { StatusKey } from "../../../components/apple/status";
import type { ZeitplanElement } from "../../../types";
import {
  PX_PRO_TAG,
  formatBereich,
  formatKurz,
  formatTag,
  kritischInfo,
  terminAusserhalb,
  terminLabel,
  terminTag,
  type BalkenRechteck,
  type Zeitraum,
  type Zoom,
  type ZiehArt,
} from "./zeitplanLogik";

// Volle Klassennamen (kein String-Bau), damit Tailwind sie beim Scannen findet.
const DOT_FUELLUNG: Record<StatusKey, string> = {
  neu: "fill-st-neu-dot",
  geplant: "fill-st-geplant-dot",
  arbeit: "fill-st-arbeit-dot",
  fehlt: "fill-st-fehlt-dot",
  erledigt: "fill-st-erledigt-dot",
  wartet: "fill-st-wartet-dot",
};

export const PARTNER_STREIFEN_ID = "gantt-partner-streifen";

const TYP_LABEL = { phase: "Phase", schritt: "Schritt", meilenstein: "Meilenstein" } as const;

export function balkenBeschreibung(e: ZeitplanElement, z: Zeitraum): string {
  const bereich = e.typ === "meilenstein" ? formatKurz(z.start) : formatBereich(formatTag(z.start), formatTag(z.ende));
  const extra = [
    e.vorgang ? `Vorgang ${e.vorgang.vorgangsnummer}` : null,
    e.partner ? `Fremdgewerk ${e.partner.name}` : null,
    e.bestellung ? `Lieferung ${e.bestellung.bestellnummer}` : null,
  ].filter(Boolean);
  return `${e.bestellung ? "Lieferung" : TYP_LABEL[e.typ]} ${e.titel}, ${bereich}${e.erledigt ? ", erledigt" : ""}${extra.length ? `, ${extra.join(", ")}` : ""}`;
}

/** Ein Balken (Schritt), Sammelbalken (Phase) oder eine Raute (Meilenstein)
 * in der Zeitleiste. Ziehen/Resize/Verbinden laufen ueber Pointer-Events,
 * die der Tab auf window verfolgt (siehe ZeitplanTab.tsx); die Tastatur
 * nutzt dieselbe PATCH-Logik. */
export function GanttBalken({
  element,
  zeitraum,
  rechteck,
  zoom,
  aktiv,
  verbindenAktiv,
  istZiel,
  kritischModus,
  onZiehStart,
  onVerbindenStart,
  onTaste,
}: {
  element: ZeitplanElement;
  zeitraum: Zeitraum;
  rechteck: BalkenRechteck;
  zoom: Zoom;
  aktiv: boolean;
  verbindenAktiv: boolean;
  istZiel: boolean;
  /** Kritischer Pfad hervorheben: kritische Elemente in Fehlerfarbe, uebrige gedaempft. */
  kritischModus: boolean;
  onZiehStart: (e: ReactPointerEvent, art: ZiehArt) => void;
  onVerbindenStart: (e: ReactPointerEvent, seite: "anfang" | "ende") => void;
  onTaste: (e: ReactKeyboardEvent) => void;
}) {
  const { x, y, w, h, cy, rechts, links } = rechteck;
  const istPhase = element.typ === "phase";
  const istMeilenstein = element.typ === "meilenstein";
  const fortschritt = Math.min(100, Math.max(0, element.fortschritt));
  const clipId = `gantt-clip-${element.id}`;
  const istPartner = element.typ === "schritt" && !!element.partner;
  const istLieferung = istMeilenstein && !!element.bestellung;
  const gesperrt = element.datum_gesperrt;
  const kritischHervor = kritischModus && element.kritisch;
  const gedaempft = kritischModus && !element.kritisch;
  const kritischText = kritischModus ? kritischInfo(element) : null;
  const phaseFuellung = kritischHervor ? "fill-st-fehlt-dot" : "fill-tone-indigo";
  const amberFuellung = kritischHervor ? "fill-st-fehlt-dot" : "fill-tone-amber";
  const sperrText = gesperrt && element.bestellung ? `Datum aus Bestellung ${element.bestellung.bestellnummer} (Liefertermin)` : null;
  const vorgangDot = element.typ === "schritt" && element.vorgang && w >= 28 ? vorgangStatusZuToken(element.vorgang.status) : null;
  const titelVersatz = vorgangDot ? 14 : 0;

  // Titel im Balken, wenn er (grob geschaetzt, 6.3 px je Zeichen bei 11 px) hineinpasst.
  const titelBreite = element.titel.length * 6.3 + 14 + titelVersatz;
  const imBalken = element.typ === "schritt" && w >= titelBreite;
  const titelDaneben = !imBalken;
  const labelX = rechts + (istMeilenstein || istPhase ? 14 : 16);
  const px = PX_PRO_TAG[zoom];
  const ziehCursor = gesperrt ? "cursor-not-allowed" : "cursor-grab";
  const ziehStart = (e: ReactPointerEvent, art: ZiehArt) => {
    if (gesperrt) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    onZiehStart(e, art);
  };

  return (
    <g
      className="group outline-none"
      role="button"
      tabIndex={0}
      aria-label={balkenBeschreibung(element, zeitraum)}
      aria-description={
        gesperrt
          ? "Das Datum kommt aus dem Liefertermin der Bestellung und kann hier nicht verschoben werden."
          : "Pfeiltasten links und rechts verschieben um einen Tag, mit Umschalt um eine Woche, mit Umschalt und Alt wird die Dauer geändert."
      }
      onKeyDown={gesperrt ? undefined : onTaste}
      opacity={element.erledigt ? 0.55 : gedaempft ? 0.5 : 1}
      style={{ touchAction: "none" }}
    >
      {kritischText && <title>{`${element.titel}: ${kritischText}`}</title>}
      {/* Fokusring: stroke statt outline, SVG-Elemente bekommen keinen CSS-Outline-Ring. */}
      <rect
        x={x - 3}
        y={y - 3}
        width={w + 6}
        height={h + 6}
        rx={istMeilenstein ? 4 : 9}
        className="fill-none stroke-tint opacity-0 group-focus-visible:opacity-100"
        strokeWidth={2}
        pointerEvents="none"
      />

      {istPhase ? (
        <>
          <rect
            x={x}
            y={cy - 6}
            width={w}
            height={7}
            rx={2}
            className={`cursor-grab ${phaseFuellung}`}
            onPointerDown={(e) => ziehStart(e, "verschieben")}
          />
          <polygon points={`${x},${cy + 1} ${x + 8},${cy + 1} ${x},${cy + 8}`} className={phaseFuellung} pointerEvents="none" />
          <polygon points={`${x + w},${cy + 1} ${x + w - 8},${cy + 1} ${x + w},${cy + 8}`} className={phaseFuellung} pointerEvents="none" />
        </>
      ) : istLieferung ? (
        <>
          <rect
            x={x}
            y={y}
            width={w}
            height={h}
            rx={4}
            className={`${ziehCursor} ${istZiel ? `${amberFuellung} stroke-tint` : amberFuellung}`}
            strokeWidth={istZiel ? 2 : 0}
            onPointerDown={(e) => ziehStart(e, "verschieben")}
          >
            {sperrText && <title>{sperrText}</title>}
          </rect>
          <Package x={x + 3} y={y + 3} width={h - 6} height={h - 6} strokeWidth={2.2} color={kritischHervor ? "#fff" : "#1c1c1e"} pointerEvents="none" aria-hidden="true" />
        </>
      ) : istMeilenstein ? (
        <polygon
          points={`${x + w / 2},${y} ${x + w},${cy} ${x + w / 2},${y + h} ${x},${cy}`}
          className={`${ziehCursor} ${istZiel ? `${amberFuellung} stroke-tint` : amberFuellung}`}
          strokeWidth={istZiel ? 2 : 0}
          onPointerDown={(e) => ziehStart(e, "verschieben")}
        />
      ) : (
        <>
          <clipPath id={clipId}>
            <rect x={x} y={y} width={w} height={h} rx={6} />
          </clipPath>
          <rect
            x={x}
            y={y}
            width={w}
            height={h}
            rx={6}
            className={`cursor-grab ${kritischHervor ? "fill-st-fehlt-dot" : istPartner ? "fill-tone-violet" : "fill-tint-solid"} ${istZiel ? "stroke-label" : ""}`}
            strokeWidth={istZiel ? 2 : 0}
            onPointerDown={(e) => onZiehStart(e, "verschieben")}
          />
          {istPartner && (
            <>
              {/* Abdunkeln fuer Kontrast zu weissem Text, Streifen als Nicht-Farb-Merkmal. */}
              <rect x={x} y={y} width={w} height={h} fill="#000" fillOpacity={0.14} clipPath={`url(#${clipId})`} pointerEvents="none" />
              <rect x={x} y={y} width={w} height={h} fill={`url(#${PARTNER_STREIFEN_ID})`} clipPath={`url(#${clipId})`} pointerEvents="none" />
            </>
          )}
          {fortschritt > 0 && (
            <rect x={x} y={y} width={(w * fortschritt) / 100} height={h} fill="#000" fillOpacity={0.28} clipPath={`url(#${clipId})`} pointerEvents="none" />
          )}
          {vorgangDot && element.vorgang && (
            <circle cx={x + 10} cy={cy} r={4.5} strokeWidth={1.5} className={`${DOT_FUELLUNG[vorgangDot]} stroke-white`} pointerEvents="all">
              <title>{`Vorgang ${element.vorgang.vorgangsnummer} · ${element.vorgang.titel} (${VORGANG_STATUS_LABEL[element.vorgang.status]})`}</title>
            </circle>
          )}
          {imBalken && (
            <text x={x + 8 + titelVersatz} y={cy + 4} fontSize={11} fontWeight={600} className="fill-white" pointerEvents="none">
              {element.erledigt ? "✓ " : ""}
              {element.titel}
            </text>
          )}
          {/* Greifer am rechten Rand: Dauer aendern (min. 1 Tag). */}
          <rect
            x={x + w - 6}
            y={y}
            width={6}
            height={h}
            className="cursor-ew-resize fill-transparent"
            onPointerDown={(e) => onZiehStart(e, "dauer")}
          />
        </>
      )}

      {titelDaneben && (
        <text
          x={labelX}
          y={cy + 4}
          fontSize={11}
          fontWeight={istPhase ? 700 : 500}
          className="fill-label"
          pointerEvents="none"
          textDecoration={element.erledigt ? "line-through" : undefined}
        >
          {element.erledigt ? "✓ " : ""}
          {element.titel}
        </text>
      )}

      {element.typ === "schritt" &&
        element.termine.map((t) => {
          const aus = terminAusserhalb(t, zeitraum);
          const tx = x + (terminTag(t) - zeitraum.start) * px + px / 2;
          return (
            <circle
              key={t.id}
              cx={tx}
              cy={cy + h / 2}
              r={3.5}
              strokeWidth={1.5}
              className={aus ? "fill-st-fehlt-dot stroke-card" : "fill-card stroke-label"}
            >
              <title>{`${terminLabel(t)}${aus ? " – liegt außerhalb des Plans" : ""}`}</title>
            </circle>
          );
        })}

      {!istPhase && (
        <>
          <circle
            cx={links - 5}
            cy={cy}
            r={4}
            strokeWidth={2}
            className={`cursor-crosshair fill-card stroke-tint ${
              verbindenAktiv || aktiv ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
            }`}
            onPointerDown={(e) => onVerbindenStart(e, "anfang")}
          >
            <title>Vom Anfang ziehen: Anfang → Anfang (auf den Anfang des Ziels)</title>
          </circle>
          <circle
            cx={rechts + 5}
            cy={cy}
            r={5}
            strokeWidth={2}
            className={`cursor-crosshair fill-card stroke-tint ${
              verbindenAktiv || aktiv ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
            }`}
            onPointerDown={(e) => onVerbindenStart(e, "ende")}
          >
            <title>Vom Ende ziehen: Ende → Anfang (linke Hälfte des Ziels) oder Ende → Ende (rechte Hälfte)</title>
          </circle>
        </>
      )}
    </g>
  );
}
