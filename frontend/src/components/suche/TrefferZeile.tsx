import { CornerDownLeft } from "lucide-react";
import type { ReactNode } from "react";

import { StatusPille } from "../apple/StatusPille";
import { SymbolKachel } from "../apple/SymbolKachel";
import { KATEGORIE_INFO, type SucheEintrag } from "./kategorien";

/** Tastenhinweis (Fußleiste, ↵-Marke an der gewählten Zeile). */
export function Taste({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <kbd
      aria-label={label}
      className="inline-flex h-5 min-w-5 items-center justify-center rounded-[5px] bg-fill px-[5px] font-sans text-meta font-semibold text-label2"
    >
      {children}
    </kbd>
  );
}

function maskiere(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Suchbegriff fett (nur Gewicht, keine Farbe). Mehrere Wörter werden einzeln hervorgehoben. */
export function Hervorhebung({ text, begriff }: { text: string; begriff: string }) {
  const woerter = begriff
    .replace(/^#/, "")
    .split(/\s+/)
    .filter(Boolean)
    .map(maskiere);
  if (woerter.length === 0 || !text) return <>{text}</>;
  const teile = text.split(new RegExp(`(${woerter.join("|")})`, "gi"));
  return (
    <>
      {teile.map((teil, i) =>
        // Ungerade Indizes sind die Treffer des Capture-Group-Splits.
        i % 2 === 1 ? (
          <mark key={i} className="bg-transparent font-semibold text-inherit">
            {teil}
          </mark>
        ) : (
          teil
        ),
      )}
    </>
  );
}

/** Inhalt einer Trefferzeile ohne Rahmen -- das Office-Fenster und die Feld-GroupedList legen ihr eigenes Gerüst darum. */
export function TrefferInhalt({
  eintrag,
  begriff,
  feld = false,
  rechtsExtra,
}: {
  eintrag: SucheEintrag;
  begriff: string;
  feld?: boolean;
  rechtsExtra?: ReactNode;
}) {
  const info = KATEGORIE_INFO[eintrag.kategorie];
  return (
    <>
      <SymbolKachel icon={info.icon} farbe={info.farbe} />
      <span className="min-w-0 flex-1">
        <span className={`block truncate text-label ${feld ? "text-zeile" : "text-fliess"}`}>
          <Hervorhebung text={eintrag.titel} begriff={begriff} />
        </span>
        {eintrag.untertitel && (
          <span className="block truncate text-sekundaer text-label2">
            <Hervorhebung text={eintrag.untertitel} begriff={begriff} />
          </span>
        )}
      </span>
      {eintrag.status && <StatusPille status={eintrag.status.token} label={eintrag.status.label} />}
      {rechtsExtra}
    </>
  );
}

/** Zeile im Office-Fenster (Option der Ergebnisliste). Der Fokus bleibt im Suchfeld (mouseDown wird abgefangen). */
export function TrefferZeile({
  eintrag,
  begriff,
  id,
  gewaehlt,
  onOeffnen,
  onZeiger,
}: {
  eintrag: SucheEintrag;
  begriff: string;
  id: string;
  gewaehlt: boolean;
  onOeffnen: (neuerTab: boolean) => void;
  onZeiger: () => void;
}) {
  return (
    <div
      id={id}
      role="option"
      aria-selected={gewaehlt}
      onMouseDown={(e) => e.preventDefault()}
      onMouseMove={onZeiger}
      onClick={(e) => onOeffnen(e.metaKey || e.ctrlKey)}
      className={`flex cursor-pointer items-center gap-[11px] rounded-[9px] px-2.5 py-[7px] ${gewaehlt ? "bg-tintbg" : ""}`}
    >
      <TrefferInhalt
        eintrag={eintrag}
        begriff={begriff}
        rechtsExtra={
          <span className={`shrink-0 ${gewaehlt ? "" : "invisible"}`} aria-hidden="true">
            <Taste>
              <CornerDownLeft size={11} strokeWidth={2.5} />
            </Taste>
          </span>
        }
      />
    </div>
  );
}
