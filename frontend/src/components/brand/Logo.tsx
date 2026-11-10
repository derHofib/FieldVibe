import pinDunkel from "../../assets/brand/pin-dunkel.webp";
import pinHell from "../../assets/brand/pin-hell.webp";
import wortmarkeDunkel from "../../assets/brand/wortmarke-dunkel.webp";
import wortmarkeHell from "../../assets/brand/wortmarke-hell.webp";

const BILDER = {
  wortmarke: { hell: wortmarkeHell, dunkel: wortmarkeDunkel, breite: 1930, hoehe: 350, standardHoehe: 24 },
  pin: { hell: pinHell, dunkel: pinDunkel, breite: 273, hoehe: 350, standardHoehe: 28 },
} as const;

/** Beide Varianten liegen im DOM und werden per .dark-Klasse umgeschaltet --
 * so flackert nichts, wenn ThemeContext erst nach dem ersten Paint greift.
 * Die zweite ist aria-hidden, damit Screenreader die Marke nur einmal vorlesen. */
export function Logo({
  variante,
  className = "",
  hoehe,
}: {
  variante: "wortmarke" | "pin";
  className?: string;
  hoehe?: number;
}) {
  const b = BILDER[variante];
  const h = hoehe ?? b.standardHoehe;
  const stil = { height: h, width: "auto" } as const;
  return (
    <>
      <img
        src={b.hell}
        alt="FieldVibe"
        width={b.breite}
        height={b.hoehe}
        style={stil}
        className={`block shrink-0 dark:hidden ${className}`}
      />
      <img
        src={b.dunkel}
        alt=""
        aria-hidden="true"
        width={b.breite}
        height={b.hoehe}
        style={stil}
        className={`hidden shrink-0 dark:block ${className}`}
      />
    </>
  );
}
