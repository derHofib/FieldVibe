import { domToBlob } from "modern-screenshot";

export const IGNORIEREN_ATTRIBUT = "data-fehlerbericht-ignorieren";

export function ignoriereWidgetKnoten(node: Node): boolean {
  return !(node instanceof Element && node.hasAttribute(IGNORIEREN_ATTRIBUT));
}

// Viewport-Ausschnitt: die Seite wird in Fenstergröße gerendert und um die
// Scrollposition verschoben, statt die gesamte Dokumenthöhe aufzunehmen.
export async function nimmScreenshot(): Promise<Blob> {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const hintergrund = getComputedStyle(document.body).backgroundColor;
  const blob = await domToBlob(document.documentElement, {
    type: "image/png",
    width: window.innerWidth,
    height: window.innerHeight,
    scale: dpr,
    filter: ignoriereWidgetKnoten,
    backgroundColor: hintergrund && hintergrund !== "rgba(0, 0, 0, 0)" ? hintergrund : "#ffffff",
    style: {
      transform: `translate(${-window.scrollX}px, ${-window.scrollY}px)`,
      transformOrigin: "0 0",
    },
  });
  if (!blob) throw new Error("Screenshot leer");
  return blob;
}

export function kannBildschirmFreigeben(): boolean {
  return typeof navigator !== "undefined" && typeof navigator.mediaDevices?.getDisplayMedia === "function";
}

// Fallback, wenn das DOM-Rendering scheitert: Nutzer gibt den Tab/Bildschirm frei,
// ein einzelnes Frame wird als PNG abgegriffen.
export async function nimmBildschirmfreigabe(): Promise<Blob> {
  const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
  try {
    const video = document.createElement("video");
    video.srcObject = stream;
    video.muted = true;
    await video.play();
    await new Promise((r) => setTimeout(r, 150));
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Bildschirmaufnahme leer"))), "image/png"),
    );
  } finally {
    stream.getTracks().forEach((t) => t.stop());
  }
}
