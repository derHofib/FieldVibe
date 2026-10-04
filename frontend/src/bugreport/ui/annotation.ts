// Reine Logik des Annotation-Editors: Formen als Daten, Reduktion (hinzufügen/undo)
// und Zeichnen auf einen 2D-Kontext. Keine React-/DOM-Abhängigkeit, damit testbar.

export interface Punkt {
  x: number;
  y: number;
}

export type Werkzeug = "freihand" | "pfeil" | "rechteck" | "text" | "schwaerzen";

export type Form =
  | { typ: "freihand"; punkte: Punkt[] }
  | { typ: "pfeil"; von: Punkt; nach: Punkt }
  | { typ: "rechteck"; von: Punkt; nach: Punkt }
  | { typ: "text"; pos: Punkt; text: string }
  | { typ: "schwaerzen"; von: Punkt; nach: Punkt };

export const ANNOTATION_FARBE = "#ff3b30";

export function formHinzufuegen(formen: readonly Form[], form: Form): Form[] {
  return [...formen, form];
}

export function rueckgaengig(formen: readonly Form[]): Form[] {
  return formen.slice(0, -1);
}

export function zuruecksetzen(): Form[] {
  return [];
}

// Pointer-Koordinaten (Client) -> Bildpixel. Das Canvas wird per CSS auf Container-
// Breite skaliert, die Zeichenfläche hat aber die Originalauflösung.
export function clientZuBild(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
  bildBreite: number,
  bildHoehe: number,
): Punkt {
  if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 };
  const x = ((clientX - rect.left) / rect.width) * bildBreite;
  const y = ((clientY - rect.top) / rect.height) * bildHoehe;
  return { x: Math.min(Math.max(x, 0), bildBreite), y: Math.min(Math.max(y, 0), bildHoehe) };
}

export function normalisiereRechteck(von: Punkt, nach: Punkt): { x: number; y: number; breite: number; hoehe: number } {
  return {
    x: Math.min(von.x, nach.x),
    y: Math.min(von.y, nach.y),
    breite: Math.abs(nach.x - von.x),
    hoehe: Math.abs(nach.y - von.y),
  };
}

// Zu kleine Ziehbewegungen (versehentliches Antippen) ergeben keine Form.
export function istSinnvoll(form: Form, minPixel = 4): boolean {
  switch (form.typ) {
    case "freihand":
      return form.punkte.length > 1;
    case "text":
      return form.text.trim().length > 0;
    default: {
      const r = normalisiereRechteck(form.von, form.nach);
      return form.typ === "pfeil" ? Math.hypot(r.breite, r.hoehe) >= minPixel : r.breite >= minPixel && r.hoehe >= minPixel;
    }
  }
}

// Linien-/Schriftstärken skalieren mit der Bildbreite, damit Annotationen auf einem
// 2x-Retina-Screenshot genauso sichtbar sind wie auf einem kleinen.
export function strichBreite(bildBreite: number): number {
  return Math.max(3, Math.round(bildBreite / 300));
}

export function schriftGroesse(bildBreite: number): number {
  return Math.max(20, Math.round(bildBreite / 40));
}

export function pfeilSpitze(von: Punkt, nach: Punkt, laenge: number): [Punkt, Punkt] {
  const winkel = Math.atan2(nach.y - von.y, nach.x - von.x);
  const spreizung = Math.PI / 7;
  return [
    { x: nach.x - laenge * Math.cos(winkel - spreizung), y: nach.y - laenge * Math.sin(winkel - spreizung) },
    { x: nach.x - laenge * Math.cos(winkel + spreizung), y: nach.y - laenge * Math.sin(winkel + spreizung) },
  ];
}

export function zeichneFormen(ctx: CanvasRenderingContext2D, formen: readonly Form[], bildBreite: number): void {
  const breite = strichBreite(bildBreite);
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = breite;
  ctx.strokeStyle = ANNOTATION_FARBE;
  ctx.fillStyle = ANNOTATION_FARBE;
  for (const f of formen) {
    switch (f.typ) {
      case "freihand": {
        if (f.punkte.length === 0) break;
        ctx.beginPath();
        ctx.moveTo(f.punkte[0].x, f.punkte[0].y);
        for (const p of f.punkte.slice(1)) ctx.lineTo(p.x, p.y);
        ctx.stroke();
        break;
      }
      case "pfeil": {
        const [a, b] = pfeilSpitze(f.von, f.nach, breite * 5);
        ctx.beginPath();
        ctx.moveTo(f.von.x, f.von.y);
        ctx.lineTo(f.nach.x, f.nach.y);
        ctx.moveTo(f.nach.x, f.nach.y);
        ctx.lineTo(a.x, a.y);
        ctx.moveTo(f.nach.x, f.nach.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        break;
      }
      case "rechteck": {
        const r = normalisiereRechteck(f.von, f.nach);
        ctx.strokeRect(r.x, r.y, r.breite, r.hoehe);
        break;
      }
      case "text": {
        const groesse = schriftGroesse(bildBreite);
        ctx.font = `600 ${groesse}px -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif`;
        ctx.textBaseline = "top";
        // Weißer Rand statt Hintergrundfläche: bleibt auf hellem und dunklem Grund lesbar.
        ctx.lineWidth = Math.max(3, groesse / 6);
        ctx.strokeStyle = "#ffffff";
        ctx.strokeText(f.text, f.pos.x, f.pos.y);
        ctx.fillText(f.text, f.pos.x, f.pos.y);
        ctx.lineWidth = breite;
        ctx.strokeStyle = ANNOTATION_FARBE;
        break;
      }
      case "schwaerzen": {
        const r = normalisiereRechteck(f.von, f.nach);
        ctx.save();
        ctx.fillStyle = "#000000";
        ctx.fillRect(r.x, r.y, r.breite, r.hoehe);
        ctx.restore();
        break;
      }
    }
  }
  ctx.restore();
}
