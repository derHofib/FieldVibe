import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { Rnd } from "react-rnd";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { formulareApi } from "../../api/endpoints";
import { IconBadge } from "../../components/IconBadge";
import type { Formular, Formularfeld, FormularfeldDatenquelle, FormularfeldTyp } from "../../types";
import {
  DATENQUELLE_LABEL,
  FORMULARFELD_TYP_ICON,
  FORMULARFELD_TYP_LABEL,
  FORMULARFELD_TYPEN_MIT_DATENQUELLE,
} from "../../utils/formular";

const FELD_TYP_OPTIONEN = Object.entries(FORMULARFELD_TYP_LABEL) as [FormularfeldTyp, string][];

// Reale A4-Masse in mm, siehe backend/app/services/pdf_service.py
// (_FORMULAR_RAND_LR/_FORMULAR_RAND_OBEN_FOLGESEITE) -- der Canvas zeigt
// jede Seite in diesen Proportionen, damit WYSIWYG wirklich stimmt.
const A4_BREITE_MM = 210;
const A4_HOEHE_MM = 297;
const RAND_LR_MM = 15;
const RAND_OBEN_SEITE1_MM = 41; // Platz fuer Mandant/Formularname/Vorgang/Datum
const RAND_OBEN_FOLGESEITE_MM = 22; // schmale Kennzeile ab Seite 2
const RAND_UNTEN_MM = 15; // _FORMULAR_RAND_UNTEN
const PX_PRO_MM = 4;

// Bewusst abgeleitet statt hart notiert, damit die Grenzen der Zahlenfelder im
// Eigenschaften-Panel nicht gegen die Backend-Werte auseinanderlaufen
// (NUTZBARE_BREITE_MM / NUTZBARE_HOEHE_* in app/models/formular.py).
const NUTZBARE_BREITE_MM = A4_BREITE_MM - 2 * RAND_LR_MM;

const ZOOM_PRESETS: { label: string; wert: "fit" | number }[] = [
  { label: "Einpassen", wert: "fit" },
  { label: "50 %", wert: 0.5 },
  { label: "75 %", wert: 0.75 },
  { label: "100 %", wert: 1 },
];

// Platz, den Kopfzeile, Seiten-Tabs, Werkzeugleiste und der
// "Feld hinzufuegen"-Button oberhalb/unterhalb des Canvas belegen -- davon
// haengt ab, wie gross "Einpassen" die Seite skalieren darf.
const CHROME_HOEHE_PX = 230;

const SNAP_PRESETS: { label: string; mm: number | null }[] = [
  { label: "Aus", mm: null },
  { label: "Fein", mm: 2 },
  { label: "Mittel", mm: 5 },
  { label: "Grob", mm: 10 },
];

function randObenMm(seiteIndex: number): number {
  return seiteIndex === 0 ? RAND_OBEN_SEITE1_MM : RAND_OBEN_FOLGESEITE_MM;
}

function nutzbareHoeheMm(seiteIndex: number): number {
  return A4_HOEHE_MM - randObenMm(seiteIndex) - RAND_UNTEN_MM;
}

function ueberlappendeFelder(felder: Formularfeld[]): Set<string> {
  const result = new Set<string>();
  for (let i = 0; i < felder.length; i++) {
    const a = felder[i];
    for (let j = i + 1; j < felder.length; j++) {
      const b = felder[j];
      const ueberlapptX = a.x_mm < b.x_mm + b.breite_mm && b.x_mm < a.x_mm + a.breite_mm;
      const ueberlapptY = a.y_mm < b.y_mm + b.hoehe_mm && b.y_mm < a.y_mm + a.hoehe_mm;
      if (ueberlapptX && ueberlapptY) {
        result.add(a.id);
        result.add(b.id);
      }
    }
  }
  return result;
}

/** Zahlenfeld des Eigenschaften-Panels. Uebernimmt erst bei Blur/Enter statt
 *  bei jedem Tastendruck -- sonst loest jede Ziffer einen PUT aus, und ein
 *  Zwischenstand wie "1" beim Tippen von "120" wuerde das Feld im Canvas
 *  kurz springen lassen. Werte von aussen (Drag&Drop) werden uebernommen,
 *  solange das Feld nicht fokussiert ist. */
function MmFeld({
  label,
  wert,
  min = 0,
  max,
  onCommit,
}: {
  label: string;
  wert: number;
  min?: number;
  max?: number;
  onCommit: (wert: number) => void;
}) {
  // Gerundet anzeigen: freies Ziehen ohne Einrasthilfe liefert Werte wie
  // 53.19402985074625, die im Zahlenfeld unlesbar sind.
  const gerundet = (n: number) => Math.round(n * 10) / 10;
  const [draft, setDraft] = useState(String(gerundet(wert)));
  const [fokussiert, setFokussiert] = useState(false);

  useEffect(() => {
    if (!fokussiert) setDraft(String(Math.round(wert * 10) / 10));
  }, [wert, fokussiert]);

  function commit() {
    setFokussiert(false);
    const zahl = Number(draft.replace(",", "."));
    if (!Number.isFinite(zahl)) {
      setDraft(String(gerundet(wert)));
      return;
    }
    let begrenzt = Math.max(zahl, min);
    if (max !== undefined) begrenzt = Math.min(begrenzt, max);
    begrenzt = gerundet(begrenzt);
    setDraft(String(begrenzt));
    if (begrenzt !== gerundet(wert)) onCommit(begrenzt);
  }

  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-slate-500 dark:text-stone-400">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        step="1"
        value={draft}
        onFocus={() => setFokussiert(true)}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            e.currentTarget.blur();
          }
        }}
        className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm tabular-nums dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
    </label>
  );
}

/** Eigenschaften-Panel im Access-Stil: zeigt Groesse/Position des markierten
 *  Felds als Zahlenfelder, damit exakte Werte tippbar sind statt nur per Maus
 *  gezogen. Alle Grenzen sind aus den A4-Massen abgeleitet -- das Backend
 *  clampt zusaetzlich (siehe FormularfeldPosition._clamp_auf_seite). */
function EigenschaftenPanel({
  feld,
  anzahlSeiten,
  onGeometrie,
  onBearbeiten,
}: {
  feld: Formularfeld | null;
  anzahlSeiten: number;
  onGeometrie: (patch: Partial<Formularfeld>) => void;
  onBearbeiten: () => void;
}) {
  if (!feld) {
    return (
      <div className="rounded-lg bg-white p-3 shadow-sm lg:w-56 dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
          Eigenschaften
        </h3>
        <p className="mt-2 text-xs text-slate-400 dark:text-stone-500">
          Feld im Layout antippen, um Größe und Position exakt einzugeben.
        </p>
      </div>
    );
  }

  const maxHoehe = nutzbareHoeheMm(feld.seite);
  return (
    <div className="space-y-3 rounded-lg bg-white p-3 shadow-sm lg:w-56 dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
          Eigenschaften
        </h3>
        <p className="mt-1 truncate text-sm font-medium text-slate-800 dark:text-stone-100">{feld.label}</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <MmFeld
          label="Breite (mm)"
          wert={feld.breite_mm}
          min={5}
          max={NUTZBARE_BREITE_MM - feld.x_mm}
          onCommit={(breite_mm) => onGeometrie({ breite_mm })}
        />
        <MmFeld
          label="Höhe (mm)"
          wert={feld.hoehe_mm}
          min={5}
          max={maxHoehe - feld.y_mm}
          onCommit={(hoehe_mm) => onGeometrie({ hoehe_mm })}
        />
        <MmFeld
          label="X (mm)"
          wert={feld.x_mm}
          max={NUTZBARE_BREITE_MM - feld.breite_mm}
          onCommit={(x_mm) => onGeometrie({ x_mm })}
        />
        <MmFeld
          label="Y (mm)"
          wert={feld.y_mm}
          max={maxHoehe - feld.hoehe_mm}
          onCommit={(y_mm) => onGeometrie({ y_mm })}
        />
      </div>

      {anzahlSeiten > 1 && (
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-500 dark:text-stone-400">Seite</span>
          <select
            value={feld.seite}
            onChange={(e) => onGeometrie({ seite: Number(e.target.value) })}
            className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            {Array.from({ length: anzahlSeiten }, (_, i) => (
              <option key={i} value={i}>
                Seite {i + 1}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => onGeometrie({ breite_mm: NUTZBARE_BREITE_MM, x_mm: 0 })}
          className="btn-touch rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
        >
          Volle Breite
        </button>
        <button
          onClick={() => onGeometrie({ breite_mm: NUTZBARE_BREITE_MM / 2 })}
          className="btn-touch rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
        >
          Halbe Breite
        </button>
      </div>

      <button
        onClick={onBearbeiten}
        className="btn-touch flex w-full items-center justify-center gap-1 rounded-md bg-slate-100 py-1.5 text-xs font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
      >
        <Pencil size={12} /> Inhalt bearbeiten
      </button>
    </div>
  );
}

interface FeldFormValues {
  feld_typ: FormularfeldTyp;
  label: string;
  hilfetext: string;
  pflichtfeld: boolean;
  werte: string;
  min: string;
  max: string;
  datenquelle: FormularfeldDatenquelle | "";
}

function leereWerte(feld?: Formularfeld): FeldFormValues {
  const optionen = feld?.optionen ?? {};
  return {
    feld_typ: feld?.feld_typ ?? "text",
    label: feld?.label ?? "",
    hilfetext: feld?.hilfetext ?? "",
    pflichtfeld: feld?.pflichtfeld ?? false,
    werte: Array.isArray(optionen.werte) ? (optionen.werte as string[]).join("\n") : "",
    min: optionen.min !== undefined ? String(optionen.min) : "1",
    max: optionen.max !== undefined ? String(optionen.max) : "5",
    datenquelle: feld?.datenquelle ?? "",
  };
}

function baueOptionen(values: FeldFormValues): Record<string, unknown> {
  if (values.feld_typ === "dropdown" || values.feld_typ === "mehrfachauswahl") {
    return {
      werte: values.werte
        .split("\n")
        .map((w) => w.trim())
        .filter(Boolean),
    };
  }
  if (values.feld_typ === "bewertung") {
    return { min: Number(values.min) || 1, max: Number(values.max) || 5 };
  }
  return {};
}

function FeldForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
  isPending,
}: {
  initial?: Formularfeld;
  submitLabel: string;
  onSubmit: (values: FeldFormValues) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [values, setValues] = useState<FeldFormValues>(leereWerte(initial));

  function set<K extends keyof FeldFormValues>(key: K, value: FeldFormValues[K]) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!values.label.trim()) return;
    onSubmit(values);
  }

  const datenquelleErlaubt = FORMULARFELD_TYPEN_MIT_DATENQUELLE.includes(values.feld_typ);

  return (
    <form
      onSubmit={submit}
      className="space-y-3 rounded-lg bg-cyan-50/60 p-3 dark:bg-cyan-500/5 dark:ring-1 dark:ring-cyan-500/20"
    >
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">Feldtyp</label>
        <select
          value={values.feld_typ}
          onChange={(e) => set("feld_typ", e.target.value as FormularfeldTyp)}
          className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        >
          {FELD_TYP_OPTIONEN.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">
          {values.feld_typ === "abschnitt" ? "Überschrift" : "Frage / Label"}
        </label>
        <input
          value={values.label}
          onChange={(e) => set("label", e.target.value)}
          autoFocus
          placeholder={values.feld_typ === "abschnitt" ? "z.B. Sicherheitscheck" : "z.B. Anlagenbezeichnung"}
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
      </div>

      {values.feld_typ !== "abschnitt" && (
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">
            Hilfetext (optional)
          </label>
          <input
            value={values.hilfetext}
            onChange={(e) => set("hilfetext", e.target.value)}
            placeholder="Erklärung, die der Techniker beim Ausfüllen sieht"
            className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </div>
      )}

      {(values.feld_typ === "dropdown" || values.feld_typ === "mehrfachauswahl") && (
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">
            Auswahlmöglichkeiten (eine je Zeile)
          </label>
          <textarea
            value={values.werte}
            onChange={(e) => set("werte", e.target.value)}
            rows={3}
            placeholder={"z.B.\nIn Ordnung\nMangel festgestellt\nNicht prüfbar"}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />
        </div>
      )}

      {values.feld_typ === "bewertung" && (
        <div className="flex gap-2">
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">Skala von</label>
            <input
              type="number"
              value={values.min}
              onChange={(e) => set("min", e.target.value)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">bis</label>
            <input
              type="number"
              value={values.max}
              onChange={(e) => set("max", e.target.value)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
        </div>
      )}

      {datenquelleErlaubt && (
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">
            Automatisch befüllen aus (optional)
          </label>
          <select
            value={values.datenquelle}
            onChange={(e) => set("datenquelle", e.target.value as FormularfeldDatenquelle | "")}
            className="btn-touch w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            <option value="">Kein Auto-Fill -- manuell ausfüllen</option>
            {Object.entries(DATENQUELLE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slate-400 dark:text-stone-500">
            Wird beim Starten der Ausfüllung vorbefüllt, bleibt aber für den Techniker änderbar.
          </p>
        </div>
      )}

      {values.feld_typ !== "abschnitt" && (
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-stone-300">
          <input
            type="checkbox"
            checked={values.pflichtfeld}
            onChange={(e) => set("pflichtfeld", e.target.checked)}
            className="h-4 w-4 rounded border-slate-300 dark:border-stone-600"
          />
          Pflichtfeld
        </label>
      )}

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300"
        >
          Abbrechen
        </button>
        <button
          type="submit"
          disabled={isPending}
          className="btn-touch btn-clay rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {submitLabel}
        </button>
      </div>
    </form>
  );
}

export function FormularRasterEditor({ formular }: { formular: Formular }) {
  const queryClient = useQueryClient();
  const [aktiveSeite, setAktiveSeite] = useState(0);
  const [neuesFeldOffen, setNeuesFeldOffen] = useState(false);
  const [bearbeitenId, setBearbeitenId] = useState<string | null>(null);
  const [markiertId, setMarkiertId] = useState<string | null>(null);
  const [zoomWahl, setZoomWahl] = useState<"fit" | number>("fit");
  const [ansichtHoehe, setAnsichtHoehe] = useState(0);
  // Tatsaechliche Breite des Canvas-Bereichs (Content-Box, Padding schon
  // abgezogen) -- per ResizeObserver statt geschaetzt aus der Fensterbreite.
  // Reagiert dadurch sofort und exakt auf jede Ursache einer Breitenaenderung
  // (Fenster resize, Panel ein/ausblenden, Scrollbalken erscheint nach dem
  // Laden der Formulardaten) statt nur auf ein "resize"-Event des Fensters,
  // das bei einem nachtraeglich erscheinenden Scrollbalken gar nicht feuert.
  const [canvasBreite, setCanvasBreite] = useState(0);
  const canvasWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function messenHoehe() {
      setAnsichtHoehe(Math.max(window.innerHeight - CHROME_HOEHE_PX, 260));
    }
    messenHoehe();
    window.addEventListener("resize", messenHoehe);
    return () => window.removeEventListener("resize", messenHoehe);
  }, []);

  useEffect(() => {
    const el = canvasWrapRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setCanvasBreite(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["formular", formular.id] });

  const seitenMutation = useMutation({
    mutationFn: (anzahlSeiten: number) => formulareApi.update(formular.id, { anzahl_seiten: anzahlSeiten }),
    onSuccess: invalidate,
  });

  const snapMutation = useMutation({
    mutationFn: (mm: number | null) => formulareApi.update(formular.id, { snap_mm: mm }),
    onSuccess: invalidate,
  });

  const createFeldMutation = useMutation({
    mutationFn: (values: FeldFormValues) =>
      formulareApi.createFeld(formular.id, {
        feld_typ: values.feld_typ,
        label: values.label.trim(),
        hilfetext: values.hilfetext.trim() || undefined,
        pflichtfeld: values.pflichtfeld,
        optionen: baueOptionen(values),
        datenquelle: values.datenquelle || null,
        seite: aktiveSeite,
      }),
    onSuccess: () => {
      invalidate();
      setNeuesFeldOffen(false);
    },
  });

  const updateFeldMutation = useMutation({
    mutationFn: ({ feldId, values }: { feldId: string; values: FeldFormValues }) =>
      formulareApi.updateFeld(formular.id, feldId, {
        feld_typ: values.feld_typ,
        label: values.label.trim(),
        hilfetext: values.hilfetext.trim() || null,
        pflichtfeld: values.pflichtfeld,
        optionen: baueOptionen(values),
        datenquelle: values.datenquelle || null,
      }),
    onSuccess: () => {
      invalidate();
      setBearbeitenId(null);
    },
  });

  const deleteFeldMutation = useMutation({
    mutationFn: (feldId: string) => formulareApi.deleteFeld(formular.id, feldId),
    onSuccess: (_daten, feldId) => {
      if (markiertId === feldId) setMarkiertId(null);
      invalidate();
    },
  });

  const setFelderImCache = (felder: Formularfeld[]) =>
    queryClient.setQueryData<Formular>(["formular", formular.id], (alt) =>
      alt ? { ...alt, felder } : alt,
    );

  const positionenMutation = useMutation({
    mutationFn: (alleFelder: Formularfeld[]) =>
      formulareApi.updatePositionen(
        formular.id,
        alleFelder.map((f) => ({
          id: f.id,
          seite: f.seite,
          x_mm: f.x_mm,
          y_mm: f.y_mm,
          breite_mm: f.breite_mm,
          hoehe_mm: f.hoehe_mm,
        })),
      ),
    // Die Rnd-Boxen sind voll controlled aus formular.felder. Ohne sofortiges
    // Cache-Update setzt react-rnd das Element beim Loslassen auf den alten
    // Prop-Wert zurueck -- das Feld springt sichtbar zurueck, obwohl der
    // Request laeuft und gleich erfolgreich sein wird.
    onMutate: setFelderImCache,
    // Der Server clampt auf den Seitenrand, seine Antwort ist die Wahrheit --
    // sonst zeigt der Canvas eine Position, die so nie gespeichert wurde.
    onSuccess: setFelderImCache,
    onError: invalidate, // Server-Stand statt optimistischem Layout wiederherstellen
  });

  /** Aendert Geometrie/Seite eines Felds und schickt den kompletten Satz an
   *  den Bulk-Endpoint (der erwartet alle Felder des Formulars). */
  function persistGeometrie(feldId: string, patch: Partial<Formularfeld>) {
    const aktualisiert = formular.felder.map((f) =>
      f.id === feldId
        ? {
            ...f,
            ...patch,
            x_mm: Math.max(patch.x_mm ?? f.x_mm, 0),
            y_mm: Math.max(patch.y_mm ?? f.y_mm, 0),
          }
        : f,
    );
    positionenMutation.mutate(aktualisiert);
  }

  function persistPosition(feldId: string, x_mm: number, y_mm: number, breite_mm: number, hoehe_mm: number) {
    persistGeometrie(feldId, { x_mm, y_mm, breite_mm, hoehe_mm });
  }

  const feldById = new Map(formular.felder.map((f) => [f.id, f]));
  const felderAufSeite = formular.felder.filter((f) => f.seite === aktiveSeite);
  const ueberlappungen = ueberlappendeFelder(felderAufSeite);
  const fehlerText = (err: unknown) =>
    err instanceof ApiError ? err.message : "Änderung konnte nicht gespeichert werden";

  const seitenBreitePx = A4_BREITE_MM * PX_PRO_MM;
  const seitenHoehePx = A4_HOEHE_MM * PX_PRO_MM;
  const randLrPx = RAND_LR_MM * PX_PRO_MM;
  const randObenPx = randObenMm(aktiveSeite) * PX_PRO_MM;
  const snapGrid: [number, number] | undefined = formular.snap_mm
    ? [formular.snap_mm * PX_PRO_MM, formular.snap_mm * PX_PRO_MM]
    : undefined;

  // "Einpassen" skaliert die Seite so, dass sie KOMPLETT sichtbar ist -- also
  // nach Breite UND Hoehe, sonst bleibt die A4-Hoehe (1188px bei 4px/mm)
  // weiterhin ausserhalb des Viewports. canvasBreite kommt vom ResizeObserver
  // oben und ist bereits die tatsaechliche Content-Box (Panel/Umbruch schon
  // beruecksichtigt) -- vor der ersten Messung (canvasBreite === 0) auf 100%
  // ausweichen statt durch 0 zu teilen.
  const fitFaktor =
    canvasBreite > 0 ? Math.min(canvasBreite / seitenBreitePx, ansichtHoehe / seitenHoehePx, 1) : 1;
  const zoomFaktor = zoomWahl === "fit" ? Math.max(fitFaktor, 0.2) : zoomWahl;

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 px-1">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
          Formular-Layout
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-slate-400 dark:text-stone-500">Ansicht:</span>
            {ZOOM_PRESETS.map((preset) => (
              <button
                key={preset.label}
                onClick={() => setZoomWahl(preset.wert)}
                className={`btn-touch rounded-md px-2 py-1 text-xs font-medium ${
                  zoomWahl === preset.wert
                    ? "bg-cyan-600 text-white"
                    : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-slate-400 dark:text-stone-500">Einrasthilfe:</span>
            {SNAP_PRESETS.map((preset) => (
              <button
                key={preset.label}
                onClick={() => snapMutation.mutate(preset.mm)}
                className={`btn-touch rounded-md px-2 py-1 text-xs font-medium ${
                  formular.snap_mm === preset.mm
                    ? "bg-cyan-600 text-white"
                    : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mb-2 flex items-center gap-1.5 px-1">
        {Array.from({ length: formular.anzahl_seiten }, (_, i) => i).map((seite) => (
          <button
            key={seite}
            onClick={() => setAktiveSeite(seite)}
            className={`btn-touch rounded-md px-3 py-1.5 text-sm font-medium ${
              aktiveSeite === seite
                ? "bg-cyan-600 text-white"
                : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            }`}
          >
            Seite {seite + 1}
          </button>
        ))}
        <button
          onClick={() => seitenMutation.mutate(formular.anzahl_seiten + 1)}
          className="btn-touch flex items-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
        >
          <Plus size={14} /> Seite
        </button>
        {formular.anzahl_seiten > 1 && aktiveSeite === formular.anzahl_seiten - 1 && (
          <button
            onClick={() => {
              if (window.confirm(`Seite ${aktiveSeite + 1} wirklich entfernen?`)) {
                setAktiveSeite(aktiveSeite - 1);
                seitenMutation.mutate(formular.anzahl_seiten - 1);
              }
            }}
            className="btn-touch rounded-md p-1.5 text-slate-400 hover:text-red-600 dark:text-stone-500 dark:hover:text-red-400"
            aria-label="Letzte Seite entfernen"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>

      {/* Bricht rein per CSS aus dem max-w-2xl-Elternrahmen aus (main in
          FeldLayout) -- eine A4-Seite braucht mehr Platz, als das enge
          Formular-Layout sonst zulaesst. Kein gemessenes Fenstermass mehr:
          der Browser rechnet das bei jedem Reflow selbst neu, reagiert also
          auch sofort, wenn z.B. nach dem Laden der Formulardaten ein
          Scrollbalken erscheint (dabei feuert kein "resize"-Event). */}
      <div className="lg:relative lg:left-1/2 lg:right-1/2 lg:-mx-[50vw] lg:w-screen">
      {/* Zweite Ebene: NUR der Canvas wird zentriert (mx-auto ueber die volle
          Breite). Das Panel teilt sich ab lg absichtlich NICHT die Breite mit
          dem Canvas -- sonst zentriert sich die eigentliche Seite nur inner-
          halb des Rests, der nach Abzug der Panel-Spalte uebrig bleibt, und
          landet dadurch sichtbar links von der echten Bildschirmmitte. */}
      <div className="flex flex-col gap-3 lg:block lg:px-4">
      <div
        ref={canvasWrapRef}
        className="min-w-0 flex-1 overflow-auto rounded-lg bg-slate-100 p-4 dark:bg-stone-950 lg:mx-auto lg:max-w-[912px]"
      >
        {/* Aeusserer Kasten in der SKALIERTEN Groesse -- transform:scale
            aendert den Platzbedarf im Layout nicht, ohne ihn bliebe unter der
            Seite bei <100% ein grosser Leerraum stehen. */}
        <div
          className="mx-auto"
          style={{ width: seitenBreitePx * zoomFaktor, height: seitenHoehePx * zoomFaktor }}
        >
        <div
          className="relative bg-white shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
          style={{
            width: seitenBreitePx,
            height: seitenHoehePx,
            transform: `scale(${zoomFaktor})`,
            transformOrigin: "top left",
          }}
        >
          {/* Kopfzeilen-Platzhalter -- entspricht der tatsaechlichen PDF-Kopfzeile */}
          <div
            className="absolute inset-x-0 top-0 flex items-center border-b border-dashed border-slate-200 bg-slate-50/60 px-3 text-xs text-slate-400 dark:border-stone-700 dark:bg-stone-800/40 dark:text-stone-500"
            style={{ height: randObenPx }}
          >
            {aktiveSeite === 0 ? "Mandant / Formularname / Vorgang / Datum" : "Mandant · Formular · Vorgang · Seite"}
          </div>

          {felderAufSeite.map((feld) => {
            const Icon = FORMULARFELD_TYP_ICON[feld.feld_typ];
            const hatUeberlappung = ueberlappungen.has(feld.id);
            return (
              <Rnd
                key={feld.id}
                bounds="parent"
                // Ohne scale rechnet react-rnd die Maus-Deltas in Bildschirm-
                // pixeln gegen unskalierte Positionen -- das Feld laeuft dem
                // Zeiger dann weg, sobald der Zoom nicht 100% ist.
                scale={zoomFaktor}
                dragGrid={snapGrid}
                resizeGrid={snapGrid}
                minWidth={10 * PX_PRO_MM}
                minHeight={5 * PX_PRO_MM}
                position={{ x: randLrPx + feld.x_mm * PX_PRO_MM, y: randObenPx + feld.y_mm * PX_PRO_MM }}
                size={{ width: feld.breite_mm * PX_PRO_MM, height: feld.hoehe_mm * PX_PRO_MM }}
                enableResizing={{ bottomRight: true }}
                onDragStart={() => setMarkiertId(feld.id)}
                onResizeStart={() => setMarkiertId(feld.id)}
                onDragStop={(_e, d) =>
                  persistPosition(
                    feld.id,
                    (d.x - randLrPx) / PX_PRO_MM,
                    (d.y - randObenPx) / PX_PRO_MM,
                    feld.breite_mm,
                    feld.hoehe_mm,
                  )
                }
                onResizeStop={(_e, _dir, ref, _delta, position) =>
                  persistPosition(
                    feld.id,
                    (position.x - randLrPx) / PX_PRO_MM,
                    (position.y - randObenPx) / PX_PRO_MM,
                    ref.offsetWidth / PX_PRO_MM,
                    ref.offsetHeight / PX_PRO_MM,
                  )
                }
              >
                <div
                  onPointerDown={() => setMarkiertId(feld.id)}
                  className={`flex h-full flex-col justify-between overflow-hidden rounded-md border bg-slate-50 p-1.5 dark:bg-stone-800/60 ${
                    markiertId === feld.id
                      ? "border-cyan-500 ring-2 ring-cyan-500 dark:border-cyan-400 dark:ring-cyan-400"
                      : hatUeberlappung
                      ? "border-amber-400 ring-1 ring-amber-400 dark:border-amber-500 dark:ring-amber-500"
                      : "border-slate-200 dark:border-stone-700"
                  }`}
                >
                  <div className="flex items-start gap-1.5">
                    <IconBadge icon={Icon} tone="cyan" size="sm" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-medium text-slate-800 dark:text-stone-100">
                        {feld.label}
                        {feld.pflichtfeld && <span className="ml-1 text-rose-500">*</span>}
                      </div>
                      {feld.datenquelle && (
                        <div className="flex items-center gap-0.5 text-[10px] text-cyan-600 dark:text-cyan-400">
                          <Sparkles size={10} /> Auto
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center justify-end gap-0.5">
                    <button
                      onClick={() => setBearbeitenId(feld.id)}
                      className="btn-touch rounded-md p-1 text-slate-400 hover:text-cyan-600 dark:text-stone-500 dark:hover:text-cyan-400"
                      aria-label="Bearbeiten"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={() => {
                        if (window.confirm(`Feld "${feld.label}" wirklich entfernen?`)) {
                          deleteFeldMutation.mutate(feld.id);
                        }
                      }}
                      className="btn-touch rounded-md p-1 text-slate-400 hover:text-red-600 dark:text-stone-500 dark:hover:text-red-400"
                      aria-label="Entfernen"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              </Rnd>
            );
          })}

          {felderAufSeite.length === 0 && (
            <p
              className="absolute inset-x-0 text-center text-sm text-slate-400 dark:text-stone-500"
              style={{ top: randObenPx + 24 }}
            >
              Noch keine Felder auf dieser Seite -- füge das erste Feld hinzu.
            </p>
          )}
        </div>
        </div>
      </div>

      {/* lg:fixed statt Teil der Flex-Zeile: das Panel reserviert dadurch
          keine Breite mehr, ueber die sich der Canvas mit ihm teilen muesste
          (das war die Ursache der Linksverschiebung oben), UND bleibt beim
          Scrollen durch ein hohes/mehrseitiges Formular sichtbar und
          bedienbar, statt mit dem Inhalt aus dem Bild zu laufen. */}
      <div className="lg:fixed lg:right-4 lg:top-16 lg:z-20 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto">
        <EigenschaftenPanel
          feld={markiertId ? feldById.get(markiertId) ?? null : null}
          anzahlSeiten={formular.anzahl_seiten}
          onBearbeiten={() => markiertId && setBearbeitenId(markiertId)}
          onGeometrie={(patch) => {
            if (!markiertId) return;
            // Bei Seitenwechsel mitspringen, sonst verschwindet das gerade
            // bearbeitete Feld unsichtbar auf eine andere Seite.
            if (patch.seite !== undefined) setAktiveSeite(patch.seite);
            persistGeometrie(markiertId, patch);
          }}
        />
      </div>
      </div>
      </div>

      {(updateFeldMutation.isError || createFeldMutation.isError || positionenMutation.isError) && (
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">
          {fehlerText(updateFeldMutation.error ?? createFeldMutation.error ?? positionenMutation.error)}
        </p>
      )}

      <div className="mt-3">
        {bearbeitenId && feldById.has(bearbeitenId) ? (
          <FeldForm
            initial={feldById.get(bearbeitenId)}
            submitLabel="Speichern"
            isPending={updateFeldMutation.isPending}
            onCancel={() => setBearbeitenId(null)}
            onSubmit={(values) => updateFeldMutation.mutate({ feldId: bearbeitenId, values })}
          />
        ) : neuesFeldOffen ? (
          <FeldForm
            submitLabel="Feld hinzufügen"
            isPending={createFeldMutation.isPending}
            onCancel={() => setNeuesFeldOffen(false)}
            onSubmit={(values) => createFeldMutation.mutate(values)}
          />
        ) : (
          <button
            onClick={() => setNeuesFeldOffen(true)}
            className="btn-touch flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-100 py-2 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300"
          >
            <Plus size={15} /> Feld hinzufügen
          </button>
        )}
      </div>
    </div>
  );
}
