import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, FileText, MapPin, PenLine, ScanLine } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { vorgangFormulareApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { QrScanner } from "../../components/QrScanner";
import type { Formularfeld } from "../../types";
import { openPdfBlob } from "../../utils/pdf";

interface FotoAntwort {
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

  function handlePointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    zeichnetRef.current = true;
    const ctx = getContext();
    const { x, y } = positionAus(e);
    ctx?.beginPath();
    ctx?.moveTo(x, y);
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

  return (
    <div className="space-y-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60">
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
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={() => (zeichnetRef.current = false)}
        onPointerLeave={() => (zeichnetRef.current = false)}
        className="h-36 w-full touch-none rounded-md border border-slate-300 bg-white"
      />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="btn-touch flex-1 rounded-md text-sm text-slate-500 dark:text-stone-400"
        >
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

function FeldRenderer({
  feld,
  value,
  onChange,
  readOnly,
  onUpload,
  hochladenPending,
}: {
  feld: Formularfeld;
  value: unknown;
  onChange: (value: unknown) => void;
  readOnly: boolean;
  onUpload: (feldId: string, file: Blob, filename: string) => void;
  hochladenPending: boolean;
}) {
  const [qrOffen, setQrOffen] = useState(false);
  const [unterschriftOffen, setUnterschriftOffen] = useState(false);
  const werte = Array.isArray(feld.optionen.werte) ? (feld.optionen.werte as string[]) : [];

  if (feld.feld_typ === "abschnitt") {
    return (
      <h3 className="pt-2 text-base font-semibold text-slate-700 dark:text-stone-200">{feld.label}</h3>
    );
  }

  const label = (
    <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-stone-200">
      {feld.label}
      {feld.pflichtfeld && <span className="ml-1 text-rose-500">*</span>}
    </label>
  );

  const wrapperClass =
    "rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800";
  const inputClass =
    "btn-touch w-full rounded-md border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-50 disabled:text-slate-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:disabled:bg-stone-800/50";

  switch (feld.feld_typ) {
    case "text":
      return (
        <div className={wrapperClass}>
          {label}
          <input
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={readOnly}
            className={inputClass}
          />
          {feld.hilfetext && <p className="mt-1 text-xs text-slate-400 dark:text-stone-500">{feld.hilfetext}</p>}
        </div>
      );

    case "textarea":
      return (
        <div className={wrapperClass}>
          {label}
          <textarea
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={readOnly}
            rows={3}
            className={`${inputClass} resize-none`}
          />
          {feld.hilfetext && <p className="mt-1 text-xs text-slate-400 dark:text-stone-500">{feld.hilfetext}</p>}
        </div>
      );

    case "zahl":
      return (
        <div className={wrapperClass}>
          {label}
          <input
            type="number"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={readOnly}
            className={inputClass}
          />
        </div>
      );

    case "datum":
      return (
        <div className={wrapperClass}>
          {label}
          <input
            type="date"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={readOnly}
            className={inputClass}
          />
        </div>
      );

    case "dropdown":
      return (
        <div className={wrapperClass}>
          {label}
          <select
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={readOnly}
            className={inputClass}
          >
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
          {label}
          <div className="space-y-1.5">
            {werte.map((w) => (
              <label key={w} className="flex items-center gap-2 text-sm text-slate-700 dark:text-stone-200">
                <input
                  type="checkbox"
                  disabled={readOnly}
                  checked={ausgewaehlt.includes(w)}
                  onChange={(e) =>
                    onChange(
                      e.target.checked ? [...ausgewaehlt, w] : ausgewaehlt.filter((x) => x !== w),
                    )
                  }
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
          {label}
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
                  value === opt.wert
                    ? "bg-cyan-600 text-white"
                    : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
                }`}
              >
                {opt.text}
              </button>
            ))}
          </div>
        </div>
      );

    case "bewertung": {
      const min = Number(feld.optionen.min ?? 1);
      const max = Number(feld.optionen.max ?? 5);
      const skala = Array.from({ length: max - min + 1 }, (_, i) => min + i);
      return (
        <div className={wrapperClass}>
          {label}
          <div className="flex gap-1.5">
            {skala.map((n) => (
              <button
                key={n}
                type="button"
                disabled={readOnly}
                onClick={() => onChange(n)}
                className={`btn-touch flex-1 rounded-md text-sm font-semibold disabled:opacity-60 ${
                  value === n
                    ? "bg-cyan-600 text-white"
                    : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
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
          {label}
          {gps ? (
            <p className="text-sm text-slate-600 dark:text-stone-300">
              {gps.lat.toFixed(6)}, {gps.lng.toFixed(6)}
            </p>
          ) : (
            <p className="text-sm text-slate-400 dark:text-stone-500">Noch kein Standort erfasst.</p>
          )}
          {!readOnly && (
            <button
              type="button"
              onClick={() =>
                navigator.geolocation.getCurrentPosition((pos) =>
                  onChange({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
                )
              }
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
          {label}
          <div className="flex gap-2">
            <input
              value={(value as string) ?? ""}
              onChange={(e) => onChange(e.target.value)}
              disabled={readOnly}
              placeholder="Gescannter Code"
              className={inputClass}
            />
            {!readOnly && (
              <button
                type="button"
                onClick={() => setQrOffen(true)}
                className="btn-touch shrink-0 rounded-md bg-slate-100 px-3 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
                aria-label="Scannen"
              >
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
      const foto = value as FotoAntwort | undefined;
      return (
        <div className={wrapperClass}>
          {label}
          {foto && <img src={foto.url} alt={feld.label} className="mb-2 max-h-48 rounded-md object-contain" />}
          {!readOnly && (
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
                  if (file) onUpload(feld.id, file, file.name);
                  e.target.value = "";
                }}
              />
            </label>
          )}
        </div>
      );
    }

    case "unterschrift": {
      const unterschrift = value as FotoAntwort | undefined;
      return (
        <div className={wrapperClass}>
          {label}
          {unterschrift && (
            <img
              src={unterschrift.url}
              alt="Unterschrift"
              className="mb-2 max-h-32 rounded-md border border-slate-200 bg-white object-contain dark:border-stone-700"
            />
          )}
          {!readOnly &&
            (unterschriftOffen ? (
              <UnterschriftCanvas
                onCancel={() => setUnterschriftOffen(false)}
                onSave={(blob) => {
                  onUpload(feld.id, blob, "unterschrift.png");
                  setUnterschriftOffen(false);
                }}
              />
            ) : (
              <button
                type="button"
                onClick={() => setUnterschriftOffen(true)}
                className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-2 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
              >
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

export function FormularAusfuellenPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [antworten, setAntworten] = useState<Record<string, unknown>>({});
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: vf, isLoading } = useQuery({
    queryKey: ["vorgang-formular", id],
    queryFn: () => vorgangFormulareApi.get(id!),
    enabled: !!id,
  });

  useEffect(() => {
    if (vf) setAntworten(vf.antworten);
  }, [vf]);

  const saveMutation = useMutation({
    mutationFn: () => vorgangFormulareApi.updateAntworten(id!, antworten),
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Speichern fehlgeschlagen"),
  });

  const abschliessenMutation = useMutation({
    mutationFn: async () => {
      await vorgangFormulareApi.updateAntworten(id!, antworten);
      return vorgangFormulareApi.abschliessen(id!);
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["vorgang-formular", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-formulare", result.vorgang_id] });
    },
    onError: (err) =>
      setFehler(err instanceof ApiError ? err.message : "Formular konnte nicht abgeschlossen werden"),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ feldId, file, filename }: { feldId: string; file: Blob; filename: string }) =>
      vorgangFormulareApi.uploadDatei(id!, feldId, file, filename),
    onSuccess: (result) =>
      setAntworten((a) => ({
        ...a,
        [result.feld_id]: { key: result.key, url: result.url, content_type: result.content_type },
      })),
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Upload fehlgeschlagen"),
  });

  const pdfMutation = useMutation({
    mutationFn: () => vorgangFormulareApi.pdf(id!),
    onSuccess: openPdfBlob,
  });

  // Speichert den aktuellen Stand vor dem Export, genau wie beim Abschliessen
  // -- sonst wuerde die Vorschau den zuletzt GESPEICHERTEN Stand zeigen statt
  // das, was gerade eben noch eingetippt wurde.
  const vorschauMutation = useMutation({
    mutationFn: async () => {
      await vorgangFormulareApi.updateAntworten(id!, antworten);
      return vorgangFormulareApi.pdf(id!);
    },
    onSuccess: openPdfBlob,
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Vorschau konnte nicht erzeugt werden"),
  });

  if (isLoading) return <p className="text-center text-sm text-slate-500 dark:text-stone-400">Lädt…</p>;
  if (!vf) return <EmptyState icon={FileText} text="Formular nicht gefunden." />;

  const readOnly = vf.status === "abgeschlossen";
  const felder = [...vf.formular_snapshot.felder].sort((a, b) => a.reihenfolge - b.reihenfolge);

  function handleAbschliessen() {
    const offen = felder.filter(
      (f) => f.pflichtfeld && f.feld_typ !== "abschnitt" && !antworten[f.id],
    );
    if (offen.length > 0) {
      setFehler(`Pflichtfelder fehlen: ${offen.map((f) => f.label).join(", ")}`);
      return;
    }
    setFehler(null);
    abschliessenMutation.mutate();
  }

  return (
    <div className="space-y-3 pb-24">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
        ← Zurück
      </button>

      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">{vf.formular_snapshot.name}</h1>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
            readOnly
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
              : "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
          }`}
        >
          {readOnly ? "Abgeschlossen" : "Offen"}
        </span>
      </div>

      <div className="space-y-2.5">
        {felder.map((feld) => (
          <FeldRenderer
            key={feld.id}
            feld={feld}
            value={antworten[feld.id]}
            onChange={(v) => setAntworten((a) => ({ ...a, [feld.id]: v }))}
            readOnly={readOnly}
            onUpload={(feldId, file, filename) => uploadMutation.mutate({ feldId, file, filename })}
            hochladenPending={uploadMutation.isPending}
          />
        ))}
      </div>

      {fehler && <p className="text-sm text-red-600 dark:text-red-400">{fehler}</p>}

      {readOnly ? (
        <button
          onClick={() => pdfMutation.mutate()}
          disabled={pdfMutation.isPending}
          className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          <FileText size={16} /> Als PDF öffnen
        </button>
      ) : (
        <>
          <button
            onClick={() => vorschauMutation.mutate()}
            disabled={vorschauMutation.isPending}
            className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-2 text-sm font-medium text-slate-600 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            <FileText size={16} /> PDF-Vorschau ansehen
          </button>
          <div className="fixed inset-x-0 bottom-16 z-10 flex gap-2 px-4">
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-white py-2 text-sm font-medium text-slate-700 shadow-md disabled:opacity-50 dark:bg-stone-800 dark:text-stone-200"
          >
            Speichern
          </button>
          <button
            onClick={handleAbschliessen}
            disabled={abschliessenMutation.isPending}
            className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white shadow-md disabled:opacity-50"
          >
            Abschließen
          </button>
          </div>
        </>
      )}
    </div>
  );
}
