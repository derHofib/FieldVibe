import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { Rnd } from "react-rnd";
import { useState, type FormEvent } from "react";

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
const PX_PRO_MM = 4;

const SNAP_PRESETS: { label: string; mm: number | null }[] = [
  { label: "Aus", mm: null },
  { label: "Fein", mm: 2 },
  { label: "Mittel", mm: 5 },
  { label: "Grob", mm: 10 },
];

function randObenMm(seiteIndex: number): number {
  return seiteIndex === 0 ? RAND_OBEN_SEITE1_MM : RAND_OBEN_FOLGESEITE_MM;
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
    onSuccess: invalidate,
  });

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
    onError: invalidate, // Server-Stand statt optimistischem Layout wiederherstellen
  });

  function persistPosition(feldId: string, x_mm: number, y_mm: number, breite_mm: number, hoehe_mm: number) {
    const aktualisiert = formular.felder.map((f) =>
      f.id === feldId ? { ...f, x_mm: Math.max(x_mm, 0), y_mm: Math.max(y_mm, 0), breite_mm, hoehe_mm } : f,
    );
    positionenMutation.mutate(aktualisiert);
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

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 px-1">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
          Formular-Layout
        </h2>
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

      <div className="overflow-x-auto rounded-lg bg-slate-100 p-4 dark:bg-stone-950">
        <div
          className="relative mx-auto bg-white shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
          style={{ width: seitenBreitePx, height: seitenHoehePx }}
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
                dragGrid={snapGrid}
                resizeGrid={snapGrid}
                minWidth={10 * PX_PRO_MM}
                minHeight={5 * PX_PRO_MM}
                position={{ x: randLrPx + feld.x_mm * PX_PRO_MM, y: randObenPx + feld.y_mm * PX_PRO_MM }}
                size={{ width: feld.breite_mm * PX_PRO_MM, height: feld.hoehe_mm * PX_PRO_MM }}
                enableResizing={{ bottomRight: true }}
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
                  className={`flex h-full flex-col justify-between overflow-hidden rounded-md border bg-slate-50 p-1.5 dark:bg-stone-800/60 ${
                    hatUeberlappung
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
