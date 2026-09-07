// Rendert ein einzelnes FormField anhand seines feld_typ -- Pendant zu
// FeldRenderer in pages/feld/FormularAusfuellenPage.tsx (altes Modell),
// aber key-basiert statt UUID-basiert und ohne Positions-/Seiten-Bezug
// (das ist Sache der jeweiligen View, nicht des Feld-Renderers selbst).
import { Camera, MapPin, PenLine, ScanLine } from "lucide-react";
import { useRef, useState } from "react";

import { QrScanner } from "../QrScanner";
import type { FormField } from "../../types";

interface DateiAntwort {
  key: string;
  url: string;
  content_type: string;
}

function UnterschriftCanvas({ onSave, onCancel }: { onSave: (blob: Blob) => void; onCancel: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const zeichnetRef = useRef(false);
  const [hatUnterschrift, setHatUnterschrift] = useState(false);

  function getContext(): CanvasRenderingContext2D | null {
    return canvasRef.current?.getContext("2d") ?? null;
  }
  function positionAus(e: React.PointerEvent<HTMLCanvasElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  return (
    <div className="space-y-2 border border-ind-line-2 p-2">
      <canvas
        ref={(node) => {
          canvasRef.current = node;
          if (node && node.width === 0) {
            const rect = node.getBoundingClientRect();
            node.width = rect.width;
            node.height = 140;
            const ctx = node.getContext("2d");
            if (ctx) {
              ctx.fillStyle = "#ffffff";
              ctx.fillRect(0, 0, node.width, node.height);
            }
          }
        }}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          zeichnetRef.current = true;
          const ctx = getContext();
          const { x, y } = positionAus(e);
          ctx?.beginPath();
          ctx?.moveTo(x, y);
        }}
        onPointerMove={(e) => {
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
        }}
        onPointerUp={() => (zeichnetRef.current = false)}
        onPointerLeave={() => (zeichnetRef.current = false)}
        className="h-36 w-full touch-none rounded-md border border-slate-300 bg-white"
      />
      <div className="flex gap-2">
        <button type="button" onClick={onCancel} className="btn-touch flex-1 rounded-md text-sm text-ind-ink-3">
          Abbrechen
        </button>
        <button
          type="button"
          disabled={!hatUnterschrift}
          onClick={() => canvasRef.current?.toBlob((blob) => blob && onSave(blob), "image/png")}
          className="btn-touch flex-1 rounded-md bg-slate-900 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-stone-700"
        >
          Übernehmen
        </button>
      </div>
    </div>
  );
}

export function FormFieldRenderer({
  field,
  value,
  onChange,
  readOnly,
  required,
  onUpload,
  hochladenPending,
}: {
  field: FormField;
  value: unknown;
  onChange: (value: unknown) => void;
  readOnly: boolean;
  required: boolean;
  onUpload?: (fieldKey: string, file: Blob, filename: string) => void;
  hochladenPending?: boolean;
}) {
  const [qrOffen, setQrOffen] = useState(false);
  const [unterschriftOffen, setUnterschriftOffen] = useState(false);
  const werte = Array.isArray(field.optionen.werte) ? (field.optionen.werte as string[]) : [];
  const label = field.label.de ?? field.key;

  const labelNode = (
    <label className="mb-1 block text-sm font-medium text-ind-ink">
      {label}
      {required && <span className="ml-1 text-rose-500">*</span>}
    </label>
  );
  const wrapperClass = "border border-ind-line bg-ind-bg p-3";
  const inputClass =
    "btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-sm disabled:bg-slate-50 disabled:text-slate-500 text-ind-ink dark:disabled:bg-stone-800/50";

  switch (field.feld_typ) {
    case "text":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <input value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} disabled={readOnly} className={inputClass} />
          {field.hilfetext && <p className="mt-1 text-xs text-ind-ink-3">{field.hilfetext}</p>}
        </div>
      );
    case "textarea":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <textarea
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={readOnly}
            rows={3}
            className={`${inputClass} resize-none`}
          />
          {field.hilfetext && <p className="mt-1 text-xs text-ind-ink-3">{field.hilfetext}</p>}
        </div>
      );
    case "zahl":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <input type="number" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} disabled={readOnly} className={inputClass} />
        </div>
      );
    case "datum":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <input type="date" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} disabled={readOnly} className={inputClass} />
        </div>
      );
    case "dropdown":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <select value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} disabled={readOnly} className={inputClass}>
            <option value="">Bitte wählen…</option>
            {werte.map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
        </div>
      );
    case "mehrfachauswahl": {
      const ausgewaehlt = Array.isArray(value) ? (value as string[]) : [];
      return (
        <div className={wrapperClass}>
          {labelNode}
          <div className="space-y-1.5">
            {werte.map((w) => (
              <label key={w} className="flex items-center gap-2 text-sm text-ind-ink">
                <input
                  type="checkbox"
                  disabled={readOnly}
                  checked={ausgewaehlt.includes(w)}
                  onChange={(e) => onChange(e.target.checked ? [...ausgewaehlt, w] : ausgewaehlt.filter((x) => x !== w))}
                  className="h-4 w-4 rounded-xs border-slate-300 dark:border-stone-600"
                />
                {w}
              </label>
            ))}
          </div>
        </div>
      );
    }
    case "ja_nein":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <div className="flex gap-2">
            {[
              { wert: true, text: "Ja" },
              { wert: false, text: "Nein" },
            ].map((opt) => (
              <button
                key={opt.text}
                type="button"
                disabled={readOnly}
                onClick={() => onChange(opt.wert)}
                className={`btn-touch flex-1 rounded-md py-1.5 text-sm font-medium disabled:opacity-60 ${
                  value === opt.wert ? "bg-cyan-600 text-white" : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
                }`}
              >
                {opt.text}
              </button>
            ))}
          </div>
        </div>
      );
    case "bewertung": {
      const min = Number(field.optionen.min ?? 1);
      const max = Number(field.optionen.max ?? 5);
      const skala = Array.from({ length: max - min + 1 }, (_, i) => min + i);
      return (
        <div className={wrapperClass}>
          {labelNode}
          <div className="flex gap-1.5">
            {skala.map((n) => (
              <button
                key={n}
                type="button"
                disabled={readOnly}
                onClick={() => onChange(n)}
                className={`btn-touch flex-1 rounded-md text-sm font-semibold disabled:opacity-60 ${
                  value === n ? "bg-cyan-600 text-white" : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      );
    }
    case "gps": {
      const gps = value as { lat: number; lng: number } | undefined;
      return (
        <div className={wrapperClass}>
          {labelNode}
          {gps ? (
            <p className="text-sm text-ind-ink-2">
              {gps.lat.toFixed(6)}, {gps.lng.toFixed(6)}
            </p>
          ) : (
            <p className="text-sm text-ind-ink-3">Noch kein Standort erfasst.</p>
          )}
          {!readOnly && (
            <button
              type="button"
              onClick={() => navigator.geolocation.getCurrentPosition((pos) => onChange({ lat: pos.coords.latitude, lng: pos.coords.longitude }))}
              className="btn-touch mt-2 flex items-center gap-1.5 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            >
              <MapPin size={15} /> Standort erfassen
            </button>
          )}
        </div>
      );
    }
    case "qr_scan":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <div className="flex gap-2">
            <input value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} disabled={readOnly} placeholder="Gescannter Code" className={inputClass} />
            {!readOnly && (
              <button type="button" onClick={() => setQrOffen(true)} className="btn-touch shrink-0 rounded-md bg-slate-100 px-3 text-slate-600 dark:bg-stone-800 dark:text-stone-300" aria-label="Scannen">
                <ScanLine size={18} />
              </button>
            )}
          </div>
          {qrOffen && (
            <QrScanner
              onScan={(code) => {
                onChange(code);
                setQrOffen(false);
              }}
              onClose={() => setQrOffen(false)}
            />
          )}
        </div>
      );
    case "foto": {
      const foto = value as DateiAntwort | undefined;
      return (
        <div className={wrapperClass}>
          {labelNode}
          {foto && <img src={foto.url} alt={label} className="mb-2 max-h-48 rounded-md object-contain" />}
          {!readOnly && onUpload && (
            <label className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-2 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300">
              <Camera size={16} />
              {hochladenPending ? "Lädt hoch…" : foto ? "Foto ersetzen" : "Foto aufnehmen"}
              <input
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) onUpload(field.key, file, file.name);
                  e.target.value = "";
                }}
              />
            </label>
          )}
        </div>
      );
    }
    case "unterschrift": {
      const unterschrift = value as DateiAntwort | undefined;
      return (
        <div className={wrapperClass}>
          {labelNode}
          {unterschrift && (
            <img src={unterschrift.url} alt="Unterschrift" className="mb-2 max-h-32 rounded-md border border-slate-200 bg-white object-contain dark:border-stone-700" />
          )}
          {!readOnly && onUpload &&
            (unterschriftOffen ? (
              <UnterschriftCanvas
                onCancel={() => setUnterschriftOffen(false)}
                onSave={(blob) => {
                  onUpload(field.key, blob, "unterschrift.png");
                  setUnterschriftOffen(false);
                }}
              />
            ) : (
              <button type="button" onClick={() => setUnterschriftOffen(true)} className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-2 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300">
                <PenLine size={16} /> {unterschrift ? "Neu unterschreiben" : "Unterschreiben"}
              </button>
            ))}
        </div>
      );
    }
    default:
      return null;
  }
}
