// Rendert ein einzelnes FormField anhand seines feld_typ, key-basiert (nicht
// UUID-basiert) und ohne Positions-/Seiten-Bezug (das ist Sache der
// jeweiligen View, nicht des Feld-Renderers selbst).
import { useQuery } from "@tanstack/react-query";
import { Camera, FileText, MapPin, Paperclip, PenLine, PenTool, ScanLine, Slash, X } from "lucide-react";
import { useRef, useState } from "react";

import { planSymboleApi } from "../../api/endpoints";
import { QrScanner } from "../QrScanner";
import type { FormField, FotoPlanWert, PlanMarkierungLinie, PlanMarkierungSymbol } from "../../types";

interface DateiAntwort {
  key: string;
  url: string;
  content_type: string;
  // Nur bei feld_typ="datei" gefuellt/relevant (Anzeige, wenn keine
  // Bild-Vorschau moeglich ist, siehe Case "datei" unten).
  filename?: string | null;
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

// Werkzeugleiste + Zeichenflaeche fuer feld_typ="foto_plan": ein Foto, auf dem
// Techniker Anlagen-Symbole (Wallbox, LS-Schalter, ...) platzieren und
// Leitungswege einzeichnen. Eigene Komponente statt ein weiterer switch-case
// mit Hooks, weil die Platzier-/Zieh-/Zeichenlogik eigenen lokalen State
// braucht (Rules of Hooks).
function FotoPlanFeld({
  field,
  value,
  onChange,
  readOnly,
  onUpload,
  hochladenPending,
  label,
  labelNode,
  wrapperClass,
}: {
  field: FormField;
  value: FotoPlanWert | undefined;
  onChange: (value: FotoPlanWert) => void;
  readOnly: boolean;
  onUpload?: (fieldKey: string, file: Blob, filename: string) => void;
  hochladenPending?: boolean;
  label: string;
  labelNode: React.ReactNode;
  wrapperClass: string;
}) {
  // Volle Bibliothek laden (nicht nur die fuer dieses Feld erlaubten Symbole)
  // -- so werden auch schon platzierte Symbole korrekt angezeigt, falls die
  // Feld-Konfiguration nachtraeglich eingeschraenkt wurde.
  const { data: alleSymbole } = useQuery({
    queryKey: ["plan-symbole"],
    queryFn: () => planSymboleApi.list(),
  });
  const erlaubteIds = Array.isArray(field.optionen.symbol_ids) ? (field.optionen.symbol_ids as string[]) : [];
  const erlaubteSymbole = (alleSymbole ?? []).filter((s) => erlaubteIds.includes(s.id));
  const symbolNachId = new Map((alleSymbole ?? []).map((s) => [s.id, s]));

  const [werkzeug, setWerkzeug] = useState<{ art: "symbol"; symbolId: string } | { art: "linie" } | null>(null);
  const [linienPunkte, setLinienPunkte] = useState<{ x: number; y: number }[]>([]);
  const [ziehIndex, setZiehIndex] = useState<number | null>(null);
  const bildRef = useRef<HTMLDivElement | null>(null);

  const foto = value?.foto ?? null;
  const markierungen = value?.markierungen ?? [];

  function relPosition(e: { clientX: number; clientY: number }) {
    const rect = bildRef.current!.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height)),
    };
  }

  function bildKlick(e: React.MouseEvent<HTMLDivElement>) {
    if (readOnly || !werkzeug) return;
    const pos = relPosition(e);
    if (werkzeug.art === "symbol") {
      const neu: PlanMarkierungSymbol = { art: "symbol", symbol_id: werkzeug.symbolId, x: pos.x, y: pos.y, winkel: 0 };
      onChange({ foto, markierungen: [...markierungen, neu] });
      setWerkzeug(null);
    } else {
      setLinienPunkte((p) => [...p, pos]);
    }
  }

  function linieUebernehmen() {
    if (linienPunkte.length >= 2) {
      const neu: PlanMarkierungLinie = { art: "linie", punkte: linienPunkte, farbe: "#dc2626" };
      onChange({ foto, markierungen: [...markierungen, neu] });
    }
    setLinienPunkte([]);
    setWerkzeug(null);
  }

  function markierungLoeschen(index: number) {
    onChange({ foto, markierungen: markierungen.filter((_, i) => i !== index) });
  }

  function symbolZiehenStart(index: number, e: React.PointerEvent) {
    if (readOnly) return;
    e.stopPropagation();
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    setZiehIndex(index);
  }
  function symbolBewegen(e: React.PointerEvent<HTMLDivElement>) {
    if (ziehIndex === null) return;
    const pos = relPosition(e);
    onChange({
      foto,
      markierungen: markierungen.map((m, i) => (i === ziehIndex && m.art === "symbol" ? { ...m, x: pos.x, y: pos.y } : m)),
    });
  }

  if (!foto) {
    return (
      <div className={wrapperClass}>
        {labelNode}
        <div className="mb-2 flex h-24 items-center justify-center rounded-md border border-dashed border-slate-300 text-slate-400 dark:border-stone-700 dark:text-stone-500">
          <PenTool size={24} strokeWidth={1.3} />
        </div>
        {!readOnly && onUpload && (
          <label className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-2 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300">
            <Camera size={16} />
            {hochladenPending ? "Lädt hoch…" : "Foto aufnehmen"}
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

  return (
    <div className={wrapperClass}>
      {labelNode}

      {!readOnly && (
        <div className="mb-2 space-y-2">
          {erlaubteSymbole.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {erlaubteSymbole.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => {
                    setLinienPunkte([]);
                    setWerkzeug(werkzeug?.art === "symbol" && werkzeug.symbolId === s.id ? null : { art: "symbol", symbolId: s.id });
                  }}
                  className={`flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium ${
                    werkzeug?.art === "symbol" && werkzeug.symbolId === s.id
                      ? "border-ind-acc bg-ind-acc-soft text-ind-acc-txt"
                      : "border-ind-line text-ind-ink-2 hover:bg-ind-hover"
                  }`}
                >
                  <img src={s.url} alt="" className="h-4 w-4 object-contain" />
                  {s.name}
                </button>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => {
                setLinienPunkte([]);
                setWerkzeug(werkzeug?.art === "linie" ? null : { art: "linie" });
              }}
              className={`flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium ${
                werkzeug?.art === "linie" ? "border-ind-acc bg-ind-acc-soft text-ind-acc-txt" : "border-ind-line text-ind-ink-2 hover:bg-ind-hover"
              }`}
            >
              <Slash size={13} /> Leitungslinie
            </button>
            {werkzeug?.art === "linie" && (
              <>
                <button
                  type="button"
                  onClick={linieUebernehmen}
                  disabled={linienPunkte.length < 2}
                  className="rounded-md bg-emerald-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-40"
                >
                  Fertig
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setLinienPunkte([]);
                    setWerkzeug(null);
                  }}
                  className="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
                >
                  Abbrechen
                </button>
              </>
            )}
          </div>
          {werkzeug && (
            <p className="text-[11px] text-ind-ink-3">
              {werkzeug.art === "symbol" ? "Auf das Foto tippen, um das Symbol zu platzieren." : "Punkte entlang der Leitung antippen, dann „Fertig“."}
            </p>
          )}
        </div>
      )}

      <div
        ref={bildRef}
        onClick={bildKlick}
        onPointerMove={symbolBewegen}
        onPointerUp={() => setZiehIndex(null)}
        className={`relative mb-2 w-full overflow-hidden rounded-md border border-slate-200 bg-white dark:border-stone-700 ${
          werkzeug ? "cursor-crosshair" : ""
        }`}
      >
        <img src={foto.url} alt={label} className="block w-full select-none" draggable={false} />
        <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full">
          {markierungen.map((m, i) =>
            m.art === "linie" ? (
              <polyline
                key={i}
                points={m.punkte.map((p) => `${p.x},${p.y}`).join(" ")}
                fill="none"
                stroke={m.farbe}
                strokeWidth={2}
                vectorEffect="non-scaling-stroke"
              />
            ) : null,
          )}
          {linienPunkte.length > 0 && (
            <polyline
              points={linienPunkte.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke="#dc2626"
              strokeDasharray="4 3"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
        {markierungen.map((m, i) =>
          m.art === "symbol" ? (
            <div
              key={i}
              onPointerDown={(e) => symbolZiehenStart(i, e)}
              style={{ left: `${m.x * 100}%`, top: `${m.y * 100}%`, transform: `translate(-50%, -50%) rotate(${m.winkel}deg)` }}
              className="absolute"
            >
              <img src={symbolNachId.get(m.symbol_id)?.url} alt="" className="h-8 w-8 object-contain drop-shadow" draggable={false} />
              {!readOnly && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    markierungLoeschen(i);
                  }}
                  className="absolute -top-1.5 -right-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-rose-600 text-white"
                  aria-label="Symbol entfernen"
                >
                  <X size={10} strokeWidth={2.5} />
                </button>
              )}
            </div>
          ) : null,
        )}
      </div>

      {markierungen.some((m) => m.art === "linie") && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {markierungen.map((m, i) =>
            m.art === "linie" ? (
              <span key={i} className="flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600 dark:bg-stone-800 dark:text-stone-300">
                Leitung {i + 1}
                {!readOnly && (
                  <button type="button" onClick={() => markierungLoeschen(i)} aria-label="Leitung löschen" className="text-slate-400 hover:text-rose-600">
                    <X size={11} />
                  </button>
                )}
              </span>
            ) : null,
          )}
        </div>
      )}

      {!readOnly && onUpload && (
        <label className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-2 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300">
          <Camera size={16} />
          {hochladenPending ? "Lädt hoch…" : "Foto ersetzen"}
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
    case "email":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <input
            type="email"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={readOnly}
            className={inputClass}
          />
          {field.hilfetext && <p className="mt-1 text-xs text-ind-ink-3">{field.hilfetext}</p>}
        </div>
      );
    case "telefon":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <input
            type="tel"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={readOnly}
            className={inputClass}
          />
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
    case "betrag":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <div className="flex items-center gap-2">
            <input
              type="number"
              step="0.01"
              value={(value as string) ?? ""}
              onChange={(e) => onChange(e.target.value)}
              disabled={readOnly}
              className={inputClass}
            />
            <span className="shrink-0 text-sm text-ind-ink-3">€</span>
          </div>
        </div>
      );
    case "datum":
      return (
        <div className={wrapperClass}>
          {labelNode}
          <input type="date" value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} disabled={readOnly} className={inputClass} />
        </div>
      );
    case "adresse": {
      const adresse = (value as { strasse?: string; plz?: string; ort?: string } | undefined) ?? {};
      const setzen = (feld: "strasse" | "plz" | "ort", wert: string) => onChange({ ...adresse, [feld]: wert });
      return (
        <div className={wrapperClass}>
          {labelNode}
          <div className="space-y-1.5">
            <input
              value={adresse.strasse ?? ""}
              onChange={(e) => setzen("strasse", e.target.value)}
              disabled={readOnly}
              placeholder="Straße, Hausnummer"
              className={inputClass}
            />
            <div className="flex gap-1.5">
              <input
                value={adresse.plz ?? ""}
                onChange={(e) => setzen("plz", e.target.value)}
                disabled={readOnly}
                placeholder="PLZ"
                className={`${inputClass} w-24`}
              />
              <input
                value={adresse.ort ?? ""}
                onChange={(e) => setzen("ort", e.target.value)}
                disabled={readOnly}
                placeholder="Ort"
                className={inputClass}
              />
            </div>
          </div>
        </div>
      );
    }
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
          {foto ? (
            <img src={foto.url} alt={label} className="mb-2 max-h-48 rounded-md object-contain" />
          ) : (
            <div className="mb-2 flex h-24 items-center justify-center rounded-md border border-dashed border-slate-300 text-slate-400 dark:border-stone-700 dark:text-stone-500">
              <Camera size={24} strokeWidth={1.3} />
            </div>
          )}
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
    case "datei": {
      const datei = value as DateiAntwort | undefined;
      const istBild = Boolean(datei?.content_type?.startsWith("image/"));
      return (
        <div className={wrapperClass}>
          {labelNode}
          {datei ? (
            istBild ? (
              <img src={datei.url} alt={label} className="mb-2 max-h-48 rounded-md object-contain" />
            ) : (
              <a
                href={datei.url}
                target="_blank"
                rel="noreferrer"
                className="mb-2 flex items-center gap-2 border border-ind-line bg-ind-bg p-2 text-sm text-ind-acc-txt"
              >
                <FileText size={16} strokeWidth={1.5} className="shrink-0" />
                <span className="truncate">{datei.filename || "Datei ansehen"}</span>
              </a>
            )
          ) : (
            <div className="mb-2 flex h-24 items-center justify-center rounded-md border border-dashed border-slate-300 text-slate-400 dark:border-stone-700 dark:text-stone-500">
              <Paperclip size={24} strokeWidth={1.3} />
            </div>
          )}
          {!readOnly && onUpload && (
            <label className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-2 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300">
              <Paperclip size={16} />
              {hochladenPending ? "Lädt hoch…" : datei ? "Datei ersetzen" : "Datei anhängen"}
              <input
                type="file"
                accept="image/*,application/pdf"
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
    case "foto_plan":
      return (
        <FotoPlanFeld
          field={field}
          value={value as FotoPlanWert | undefined}
          onChange={onChange}
          readOnly={readOnly}
          onUpload={onUpload}
          hochladenPending={hochladenPending}
          label={label}
          labelNode={labelNode}
          wrapperClass={wrapperClass}
        />
      );
    case "unterschrift": {
      const unterschrift = value as DateiAntwort | undefined;
      return (
        <div className={wrapperClass}>
          {labelNode}
          {unterschrift ? (
            <img src={unterschrift.url} alt="Unterschrift" className="mb-2 max-h-32 rounded-md border border-slate-200 bg-white object-contain dark:border-stone-700" />
          ) : (
            <div className="mb-2 flex h-20 items-center justify-center rounded-md border border-dashed border-slate-300 text-slate-400 dark:border-stone-700 dark:text-stone-500">
              <PenLine size={22} strokeWidth={1.3} />
            </div>
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
