import { useRef, useState } from "react";

interface SignaturePadProps {
  onSave: (blob: Blob, unterzeichnerName: string) => void;
  onCancel: () => void;
  isSaving?: boolean;
}

export function SignaturePad({ onSave, onCancel, isSaving = false }: SignaturePadProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const zeichnetRef = useRef(false);
  const [hatUnterschrift, setHatUnterschrift] = useState(false);
  const [unterzeichnerName, setUnterzeichnerName] = useState("");

  function getContext(): CanvasRenderingContext2D | null {
    return canvasRef.current?.getContext("2d") ?? null;
  }

  function positionAus(e: React.PointerEvent<HTMLCanvasElement>): { x: number; y: number } {
    const rect = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function handlePointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    zeichnetRef.current = true;
    const ctx = getContext();
    const { x, y } = positionAus(e);
    if (ctx) {
      ctx.beginPath();
      ctx.moveTo(x, y);
    }
  }

  function handlePointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!zeichnetRef.current) return;
    const ctx = getContext();
    const { x, y } = positionAus(e);
    if (ctx) {
      ctx.lineTo(x, y);
      ctx.strokeStyle = "#1e293b";
      ctx.lineWidth = 2.5;
      ctx.lineCap = "round";
      ctx.stroke();
    }
    setHatUnterschrift(true);
  }

  function handlePointerUp() {
    zeichnetRef.current = false;
  }

  function leeren() {
    const canvas = canvasRef.current;
    const ctx = getContext();
    if (canvas && ctx) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    setHatUnterschrift(false);
  }

  function speichern() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (blob) onSave(blob, unterzeichnerName);
    }, "image/png");
  }

  return (
    <div className="space-y-2 rounded-md bg-slate-50 p-2">
      <input
        value={unterzeichnerName}
        onChange={(e) => setUnterzeichnerName(e.target.value)}
        placeholder="Name des Unterzeichners"
        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
      />
      <canvas
        ref={(node) => {
          canvasRef.current = node;
          if (node && node.width === 0) {
            // Erst hier auf die tatsaechliche CSS-Groesse skalieren, statt
            // eines festen width/height-Attributs -- sonst wuerde die
            // Zeichnung bei jedem Resize verzerrt/gestreckt.
            const rect = node.getBoundingClientRect();
            node.width = rect.width;
            node.height = 160;
            const ctx = node.getContext("2d");
            if (ctx) {
              ctx.fillStyle = "#ffffff";
              ctx.fillRect(0, 0, node.width, node.height);
            }
          }
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        className="h-40 w-full touch-none rounded-md border border-slate-300 bg-white"
      />
      <div className="flex gap-2">
        <button
          onClick={leeren}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm text-slate-600"
        >
          Löschen
        </button>
        <button
          onClick={speichern}
          disabled={!hatUnterschrift || !unterzeichnerName.trim() || isSaving}
          className="btn-touch flex-1 rounded-md bg-slate-900 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        <button onClick={onCancel} className="btn-touch flex-1 rounded-md text-sm text-slate-500">
          Abbrechen
        </button>
      </div>
    </div>
  );
}
