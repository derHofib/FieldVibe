import { ArrowUpRight, EyeOff, Pencil, Square, Trash2, Type, Undo2, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import {
  clientZuBild,
  formHinzufuegen,
  istSinnvoll,
  rueckgaengig,
  schriftGroesse,
  zeichneFormen,
  zuruecksetzen,
  type Form,
  type Punkt,
  type Werkzeug,
} from "./annotation";

const WERKZEUGE: { key: Werkzeug; label: string; icon: LucideIcon }[] = [
  { key: "freihand", label: "Freihand", icon: Pencil },
  { key: "pfeil", label: "Pfeil", icon: ArrowUpRight },
  { key: "rechteck", label: "Rechteck", icon: Square },
  { key: "text", label: "Text", icon: Type },
  { key: "schwaerzen", label: "Schwärzen", icon: EyeOff },
];

/** Gesteuerte Komponente: die Formenliste gehört dem Aufrufer, damit der Export
 * beim Senden ohne Ref auskommt. */
export function AnnotationEditor({
  bild,
  formen,
  onFormen,
}: {
  bild: HTMLImageElement;
  formen: Form[];
  onFormen: (formen: Form[]) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [werkzeug, setWerkzeug] = useState<Werkzeug>("freihand");
  const [entwurf, setEntwurf] = useState<Form | null>(null);
  const [textPos, setTextPos] = useState<Punkt | null>(null);
  const [text, setText] = useState("");
  const breite = bild.naturalWidth;
  const hoehe = bild.naturalHeight;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, breite, hoehe);
    ctx.drawImage(bild, 0, 0, breite, hoehe);
    zeichneFormen(ctx, entwurf ? [...formen, entwurf] : formen, breite);
  }, [bild, formen, entwurf, breite, hoehe]);

  function punkt(e: ReactPointerEvent<HTMLCanvasElement>): Punkt {
    return clientZuBild(e.clientX, e.clientY, e.currentTarget.getBoundingClientRect(), breite, hoehe);
  }

  function textFestschreiben() {
    if (textPos && text.trim()) onFormen(formHinzufuegen(formen, { typ: "text", pos: textPos, text: text.trim() }));
    setTextPos(null);
    setText("");
  }

  function aufDruecken(e: ReactPointerEvent<HTMLCanvasElement>) {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    const p = punkt(e);
    if (werkzeug === "text") {
      textFestschreiben();
      setTextPos(p);
      return;
    }
    e.currentTarget.setPointerCapture?.(e.pointerId);
    setEntwurf(
      werkzeug === "freihand" ? { typ: "freihand", punkte: [p] } : { typ: werkzeug, von: p, nach: p },
    );
  }

  function aufBewegen(e: ReactPointerEvent<HTMLCanvasElement>) {
    if (!entwurf) return;
    const p = punkt(e);
    setEntwurf(entwurf.typ === "freihand" ? { ...entwurf, punkte: [...entwurf.punkte, p] } : entwurf.typ === "text" ? entwurf : { ...entwurf, nach: p });
  }

  function aufLoslassen() {
    if (entwurf && istSinnvoll(entwurf)) onFormen(formHinzufuegen(formen, entwurf));
    setEntwurf(null);
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1" role="toolbar" aria-label="Annotations-Werkzeuge">
        {WERKZEUGE.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            aria-pressed={werkzeug === key}
            aria-label={label}
            title={label}
            onClick={() => {
              textFestschreiben();
              setWerkzeug(key);
            }}
            className={`flex h-9 w-9 items-center justify-center rounded-[8px] ${
              werkzeug === key ? "bg-tint-solid text-white" : "bg-fill text-label"
            }`}
          >
            <Icon size={18} strokeWidth={2} aria-hidden="true" />
          </button>
        ))}
        <span className="mx-1 h-5 w-px bg-sep" aria-hidden="true" />
        <button
          type="button"
          aria-label="Rückgängig"
          title="Rückgängig"
          disabled={formen.length === 0}
          onClick={() => onFormen(rueckgaengig(formen))}
          className="flex h-9 w-9 items-center justify-center rounded-[8px] bg-fill text-label disabled:opacity-40"
        >
          <Undo2 size={18} strokeWidth={2} aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Alles zurücksetzen"
          title="Alles zurücksetzen"
          disabled={formen.length === 0}
          onClick={() => onFormen(zuruecksetzen())}
          className="flex h-9 w-9 items-center justify-center rounded-[8px] bg-fill text-label disabled:opacity-40"
        >
          <Trash2 size={18} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>

      <div className="relative overflow-hidden rounded-[var(--radius-ap-input)] bg-fill">
        <canvas
          ref={canvasRef}
          width={breite}
          height={hoehe}
          aria-label="Screenshot mit Annotationen"
          className="block h-auto w-full"
          style={{ touchAction: "none", cursor: werkzeug === "text" ? "text" : "crosshair" }}
          onPointerDown={aufDruecken}
          onPointerMove={aufBewegen}
          onPointerUp={aufLoslassen}
          onPointerCancel={() => setEntwurf(null)}
        />
        {textPos && (
          <input
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            onBlur={textFestschreiben}
            onKeyDown={(e) => {
              if (e.key === "Enter") textFestschreiben();
              if (e.key === "Escape") {
                e.stopPropagation();
                setTextPos(null);
                setText("");
              }
            }}
            aria-label="Annotationstext"
            placeholder="Text eingeben"
            className="absolute rounded-[6px] border border-sepstrong bg-card px-1.5 text-[16px] text-label"
            style={{
              left: `${(textPos.x / breite) * 100}%`,
              top: `${(textPos.y / hoehe) * 100}%`,
              minWidth: 120,
              // Schriftgröße im Eingabefeld bleibt 16px (iOS-Zoom), die Vorschau im Canvas skaliert mit dem Bild.
              height: Math.max(28, schriftGroesse(breite) / 2),
            }}
          />
        )}
      </div>
      <p className="mt-2 text-[13px] text-label2">Persönliche Daten bitte mit „Schwärzen“ abdecken.</p>
    </div>
  );
}
