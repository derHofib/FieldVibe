import { abweichung, formatWert } from "../format";
import type { DarstellungProps } from "./gemeinsam";

// Das Backend nennt das Bezugsdatum als Spaltenname; nur bekannte Namen werden als Hinweis gezeigt.
const DATUMSBEZUG: Record<string, string> = {
  erstellt_am: "nach Erstelldatum",
  abgeschlossen_am: "nach Abschlussdatum",
};

/** Gesamtwert groß, darunter die Abweichung zur Vorperiode. Gut/schlecht färbt nur bei Kennzahlen mit klarer
 * Richtung (siehe richtungFuer); der Pfeil steht zusätzlich als Text im Satz. */
export function Zahl({ daten, vergleich, vorLabel }: Pick<DarstellungProps, "daten" | "vergleich" | "vorLabel">) {
  const abw = vergleich
    ? abweichung(daten.kennzahl, daten.einheit, daten.gesamt, daten.vorperiode_gesamt, vorLabel)
    : null;
  const bezug = daten.datumsbezug ? DATUMSBEZUG[daten.datumsbezug] : undefined;
  const farbe = abw?.gut === true ? "text-st-erledigt" : abw?.gut === false ? "text-st-fehlt" : "text-label2";

  return (
    <div className="flex flex-col gap-1">
      <p className="ap-heading text-titel-desktop font-semibold tabular-nums text-label">
        {formatWert(daten.gesamt, daten.einheit)}
      </p>
      {abw && <p className={`text-sekundaer font-semibold ${farbe}`}>{abw.text}</p>}
      {bezug && <p className="text-sekundaer text-label2">{bezug}</p>}
    </div>
  );
}
