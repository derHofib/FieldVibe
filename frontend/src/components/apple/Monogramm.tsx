function initialenAus(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .map((t) => t[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

/** Monogramm-Avatar (Abschnitt 4.2): fester Verlauf (einzige erlaubte
 * Farbflaeche neben Symbol-Kacheln), weiße Initialen. `ueberlappend` fuer
 * gestapelte Team-Avatare (-5px Versatz + Ring in --win/--cell). */
export function Monogramm({
  name,
  groesse = 22,
  ueberlappend = false,
  ringKlasse = "ring-win",
}: {
  name: string;
  groesse?: number;
  ueberlappend?: boolean;
  /** Ring-Farbe muss die Flaeche treffen, auf der der Avatar liegt (--win,
   * --cell, --card, ...) -- Default passt fuer Fensterhintergrund. */
  ringKlasse?: string;
}) {
  return (
    <span
      title={name}
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white ${
        ueberlappend ? `ring-[1.5px] ${ringKlasse}` : ""
      }`}
      style={{
        width: groesse,
        height: groesse,
        fontSize: Math.round(groesse * 0.41),
        marginLeft: ueberlappend ? -5 : undefined,
        backgroundImage: "linear-gradient(180deg, var(--mono-grad-1), var(--mono-grad-2))",
      }}
    >
      {initialenAus(name)}
    </span>
  );
}
