// Bild-Hilfen für Screenshot-Export: Größenbegrenzung und Rendern der Annotationen.
import { zeichneFormen, type Form } from "./annotation";

export const MAX_BILD_BYTES = 5 * 1024 * 1024;

export function ladeBild(blob: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Bild konnte nicht geladen werden"));
    };
    img.src = url;
  });
}

function canvasZuBlob(canvas: HTMLCanvasElement, typ: string, qualitaet?: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Bild konnte nicht kodiert werden"))), typ, qualitaet);
  });
}

function zeichneAufCanvas(quelle: CanvasImageSource, breite: number, hoehe: number, formen: readonly Form[]): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(breite));
  canvas.height = Math.max(1, Math.round(hoehe));
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas nicht verfügbar");
  ctx.drawImage(quelle, 0, 0, canvas.width, canvas.height);
  if (formen.length > 0) zeichneFormen(ctx, formen, canvas.width);
  return canvas;
}

// PNG, bei Überschreitung JPEG 0.85 und danach schrittweise verkleinern, bis das Limit hält.
export async function kodiereBegrenzt(canvas: HTMLCanvasElement, maxBytes = MAX_BILD_BYTES): Promise<Blob> {
  const png = await canvasZuBlob(canvas, "image/png");
  if (png.size <= maxBytes) return png;
  let aktuell = canvas;
  for (let versuch = 0; versuch < 6; versuch++) {
    const jpeg = await canvasZuBlob(aktuell, "image/jpeg", 0.85);
    if (jpeg.size <= maxBytes) return jpeg;
    const kleiner = document.createElement("canvas");
    kleiner.width = Math.max(1, Math.round(aktuell.width * 0.75));
    kleiner.height = Math.max(1, Math.round(aktuell.height * 0.75));
    kleiner.getContext("2d")?.drawImage(aktuell, 0, 0, kleiner.width, kleiner.height);
    aktuell = kleiner;
  }
  return canvasZuBlob(aktuell, "image/jpeg", 0.6);
}

export async function begrenzeBlob(blob: Blob, maxBytes = MAX_BILD_BYTES): Promise<Blob> {
  if (blob.size <= maxBytes) return blob;
  const img = await ladeBild(blob);
  return kodiereBegrenzt(zeichneAufCanvas(img, img.naturalWidth, img.naturalHeight, []), maxBytes);
}

export async function rendereAnnotiert(bild: HTMLImageElement, formen: readonly Form[]): Promise<Blob> {
  return kodiereBegrenzt(zeichneAufCanvas(bild, bild.naturalWidth, bild.naturalHeight, formen));
}
