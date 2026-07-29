import jsQR from "jsqr";
import { useEffect, useRef, useState } from "react";

interface QrScannerProps {
  onScan: (code: string) => void;
  onClose: () => void;
}

/** Camera-based QR scanner with a manual-entry fallback. The fallback isn't
 * an afterthought: camera permission can be denied, the device may have no
 * camera, and headless/CI environments can never exercise getUserMedia --
 * without it, "QR-Scan an Anlagen" would be untestable and, for some
 * users, unusable. */
export function QrScanner({ onScan, onClose }: QrScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const [manualCode, setManualCode] = useState("");
  const [cameraError, setCameraError] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;

    async function startCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
        });
        if (stopped) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        tick();
      } catch {
        setCameraError("Kamera nicht verfügbar – bitte Code manuell eingeben.");
      }
    }

    function tick() {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (video && canvas && video.readyState === video.HAVE_ENOUGH_DATA) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const result = jsQR(imageData.data, imageData.width, imageData.height);
          if (result?.data) {
            onScan(result.data);
            return;
          }
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    }

    startCamera();

    return () => {
      stopped = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/90 p-4">
      <div className="flex items-center justify-between text-white">
        <h2 className="text-lg font-bold">QR-Code scannen</h2>
        <button onClick={onClose} className="btn-touch px-3 py-2 text-white">
          ✕
        </button>
      </div>

      <div className="mt-4 flex flex-1 items-center justify-center overflow-hidden rounded-lg bg-black">
        {cameraError ? (
          <p className="p-4 text-center text-sm text-slate-300">{cameraError}</p>
        ) : (
          <video ref={videoRef} className="max-h-full max-w-full" muted playsInline />
        )}
        <canvas ref={canvasRef} className="hidden" />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (manualCode.trim()) onScan(manualCode.trim());
        }}
        className="mt-4 flex gap-2"
      >
        <input
          value={manualCode}
          onChange={(e) => setManualCode(e.target.value)}
          placeholder="QR-Code manuell eingeben"
          className="btn-touch flex-1 rounded-md border border-slate-300 px-3 py-2"
        />
        <button
          type="submit"
          className="btn-touch rounded-md bg-white px-4 py-2 text-sm font-medium text-slate-900"
        >
          OK
        </button>
      </form>
    </div>
  );
}
