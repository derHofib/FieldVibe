import { Bug, ChevronDown, ImagePlus, Monitor } from "lucide-react";
import { useEffect, useId, useState, type ChangeEvent, type ComponentType, type FormEvent, type ReactNode } from "react";

import type { FehlerberichtKontext, Kategorie } from "../index";
import type { Form } from "./annotation";
import { AnnotationEditor } from "./AnnotationEditor";
import { begrenzeBlob, ladeBild, rendereAnnotiert } from "./bild";
import {
  baueFormular,
  fehlerText,
  KATEGORIEN,
  type FormularWerte,
  type ScreenshotDateien,
  type Schweregrad,
} from "./payload";
import { kannBildschirmFreigeben, nimmBildschirmfreigabe } from "./screenshot";

export interface MeldeErgebnis {
  id: string | number;
  duplikat_von_id?: string | number | null;
}

/** Strukturell identisch zu components/apple/Sheet, ohne es zu importieren. */
export type RahmenKomponente = ComponentType<{
  offen: boolean;
  onClose: () => void;
  titel: string;
  links?: ReactNode;
  rechts?: ReactNode;
  vollbild?: boolean;
  children: ReactNode;
}>;

export interface BerichtStart {
  kontext: FehlerberichtKontext;
  original: Blob | null;
  aufnahmeFehlgeschlagen: boolean;
}

const SCHWEREGRADE: { wert: Schweregrad; label: string }[] = [
  { wert: "niedrig", label: "Niedrig" },
  { wert: "mittel", label: "Mittel" },
  { wert: "hoch", label: "Hoch" },
  { wert: "blockierend", label: "Blockierend" },
];

function kurzinfo(key: Kategorie, kontext: FehlerberichtKontext): string {
  const wert = kontext[key];
  if (Array.isArray(wert)) {
    const einheit = key === "netzwerk" ? "Aufrufe" : key === "konsole" ? "Einträge" : "Schritte";
    return `${wert.length} ${einheit}`;
  }
  if (key === "umgebung") return "Browser, Gerät, App-Version";
  if (key === "sitzung") return "Rolle und IDs, keine Namen";
  if (key === "app_state") return `${Object.keys(wert ?? {}).length} Bereiche`;
  return "";
}

const labelKlasse = "mb-1 block text-[13px] font-medium text-label2";

export function FehlerberichtDialog({
  start,
  onClose,
  Rahmen,
  apiUpload,
  route,
  appVersion,
  commitSha,
}: {
  start: BerichtStart;
  onClose: () => void;
  Rahmen: RahmenKomponente;
  apiUpload: (formData: FormData) => Promise<MeldeErgebnis>;
  route?: string;
  appVersion?: string;
  commitSha?: string;
}) {
  const formId = useId();
  const [original, setOriginal] = useState<Blob | null>(start.original);
  const [bild, setBild] = useState<HTMLImageElement | null>(null);
  const [formen, setFormen] = useState<Form[]>([]);
  const [mitScreenshot, setMitScreenshot] = useState(true);
  const [werte, setWerte] = useState<FormularWerte>({
    titel: "",
    beschreibung: "",
    erwartet: "",
    schritte: "",
    schweregrad: "mittel",
  });
  const [auswahl, setAuswahl] = useState<Set<Kategorie>>(
    () => new Set(KATEGORIEN.filter((k) => start.kontext[k.key] !== undefined).map((k) => k.key)),
  );
  const [vorschau, setVorschau] = useState<Set<Kategorie>>(new Set());
  const [schritteOffen, setSchritteOffen] = useState(false);
  const [bildFehler, setBildFehler] = useState<string | null>(null);
  const [sendet, setSendet] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [ergebnis, setErgebnis] = useState<MeldeErgebnis | null>(null);

  useEffect(() => {
    if (!original) {
      setBild(null);
      return;
    }
    let aktiv = true;
    ladeBild(original)
      .then((img) => aktiv && setBild(img))
      .catch(() => aktiv && setBildFehler("Das Bild konnte nicht angezeigt werden."));
    return () => {
      aktiv = false;
    };
  }, [original]);

  function neuesBild(blob: Blob) {
    setOriginal(blob);
    setFormen([]);
    setBildFehler(null);
    setMitScreenshot(true);
  }

  async function freigeben() {
    try {
      neuesBild(await nimmBildschirmfreigabe());
    } catch {
      setBildFehler("Die Bildschirmfreigabe wurde abgebrochen oder ist fehlgeschlagen.");
    }
  }

  function dateiGewaehlt(e: ChangeEvent<HTMLInputElement>) {
    const datei = e.target.files?.[0];
    if (datei) neuesBild(datei);
    e.target.value = "";
  }

  function schalte(menge: Set<Kategorie>, setter: (s: Set<Kategorie>) => void, key: Kategorie) {
    const neu = new Set(menge);
    if (!neu.delete(key)) neu.add(key);
    setter(neu);
  }

  const kannSenden = werte.titel.trim() !== "" && werte.beschreibung.trim() !== "" && !sendet;

  async function senden(e: FormEvent) {
    e.preventDefault();
    if (!kannSenden) return;
    setSendet(true);
    setFehler(null);
    try {
      let screenshot: ScreenshotDateien | null = null;
      if (mitScreenshot && original && bild) {
        const begrenzt = await begrenzeBlob(original);
        screenshot = {
          original: begrenzt,
          annotiert: formen.length > 0 ? await rendereAnnotiert(bild, formen) : begrenzt,
        };
      }
      const fd = baueFormular({ werte, kontext: start.kontext, auswahl, screenshot, route, appVersion, commitSha });
      setErgebnis(await apiUpload(fd));
    } catch (err) {
      setFehler(fehlerText(err));
    } finally {
      setSendet(false);
    }
  }

  const schliessen = (
    <button type="button" onClick={onClose} className="text-[17px] text-tint-text">
      {ergebnis ? "Fertig" : "Abbrechen"}
    </button>
  );

  return (
    <Rahmen
      offen
      onClose={onClose}
      titel="Fehler melden"
      vollbild
      links={schliessen}
      rechts={
        ergebnis ? undefined : (
          <button type="submit" form={formId} disabled={!kannSenden} className="text-[17px] font-semibold text-tint-text disabled:opacity-40">
            {sendet ? "Sendet…" : "Senden"}
          </button>
        )
      }
    >
      <div data-fehlerbericht-ignorieren className="px-4 py-4">
        {ergebnis ? (
          <div className="py-8 text-center" role="status">
            <Bug size={32} strokeWidth={2} className="mx-auto mb-3 text-tint" aria-hidden="true" />
            <p className="text-[17px] font-semibold text-label">Danke! Fehler #{String(ergebnis.id)} gemeldet.</p>
            {ergebnis.duplikat_von_id != null && (
              <p className="mt-2 text-[15px] text-label2">
                Dieses Problem ist bereits bekannt (#{String(ergebnis.duplikat_von_id)}). Deine Meldung wurde zugeordnet.
              </p>
            )}
            <button type="button" onClick={onClose} className="btn-ap-capsule btn-ap-capsule-primary mt-6">
              Schließen
            </button>
          </div>
        ) : (
          <form id={formId} onSubmit={senden} className="space-y-5">
            <section aria-label="Screenshot">
              {original && bild ? (
                <>
                  <label className="mb-2 flex items-center gap-2 text-[15px] text-label">
                    <input
                      type="checkbox"
                      checked={mitScreenshot}
                      onChange={(e) => setMitScreenshot(e.target.checked)}
                      style={{ accentColor: "var(--tint)" }}
                      className="h-5 w-5"
                    />
                    Screenshot mitsenden
                  </label>
                  {mitScreenshot && <AnnotationEditor bild={bild} formen={formen} onFormen={setFormen} />}
                </>
              ) : (
                <div className="rounded-[var(--radius-ap-card)] bg-fill p-3">
                  <p className="text-[15px] text-label">
                    {original
                      ? "Bild wird geladen…"
                      : start.aufnahmeFehlgeschlagen
                        ? "Der Screenshot konnte nicht automatisch aufgenommen werden."
                        : "Kein Screenshot vorhanden."}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {kannBildschirmFreigeben() && (
                      <button type="button" onClick={freigeben} className="btn-ap inline-flex h-9 items-center gap-1.5 px-3 text-[13px]">
                        <Monitor size={15} strokeWidth={2} aria-hidden="true" />
                        Bildschirm freigeben
                      </button>
                    )}
                    <label className="btn-ap inline-flex h-9 cursor-pointer items-center gap-1.5 px-3 text-[13px]">
                      <ImagePlus size={15} strokeWidth={2} aria-hidden="true" />
                      Bild hochladen
                      <input type="file" accept="image/*" className="sr-only" onChange={dateiGewaehlt} />
                    </label>
                  </div>
                  <p className="mt-2 text-[13px] text-label2">Du kannst auch ganz ohne Bild melden.</p>
                </div>
              )}
              {bildFehler && <p className="mt-2 text-[13px] text-st-fehlt">{bildFehler}</p>}
            </section>

            <div>
              <label htmlFor={`${formId}-titel`} className={labelKlasse}>
                Titel
              </label>
              <input
                id={`${formId}-titel`}
                className="field-ap"
                required
                maxLength={200}
                value={werte.titel}
                onChange={(e) => setWerte({ ...werte, titel: e.target.value })}
              />
            </div>
            <div>
              <label htmlFor={`${formId}-beschreibung`} className={labelKlasse}>
                Beschreibung
              </label>
              <textarea
                id={`${formId}-beschreibung`}
                className="field-ap min-h-24"
                required
                placeholder="Was ist passiert?"
                value={werte.beschreibung}
                onChange={(e) => setWerte({ ...werte, beschreibung: e.target.value })}
              />
            </div>
            <div>
              <label htmlFor={`${formId}-erwartet`} className={labelKlasse}>
                Was hast du erwartet?
              </label>
              <textarea
                id={`${formId}-erwartet`}
                className="field-ap min-h-16"
                value={werte.erwartet}
                onChange={(e) => setWerte({ ...werte, erwartet: e.target.value })}
              />
            </div>

            <fieldset>
              <legend className={labelKlasse}>Schweregrad</legend>
              <div role="group" aria-label="Schweregrad" className="flex w-full rounded-[9px] bg-fill p-0.5">
                {SCHWEREGRADE.map((s) => {
                  const aktiv = werte.schweregrad === s.wert;
                  return (
                    <button
                      key={s.wert}
                      type="button"
                      aria-pressed={aktiv}
                      onClick={() => setWerte({ ...werte, schweregrad: s.wert })}
                      className={`h-8 flex-1 rounded-[7px] px-1 text-[13px] ${
                        aktiv ? "bg-thumb font-semibold text-label shadow-[0_1px_3px_rgba(0,0,0,.14)]" : "font-medium text-label"
                      }`}
                    >
                      {s.label}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <div>
              <button
                type="button"
                aria-expanded={schritteOffen}
                onClick={() => setSchritteOffen(!schritteOffen)}
                className="flex items-center gap-1 text-[15px] text-tint-text"
              >
                <ChevronDown size={16} strokeWidth={2} className={schritteOffen ? "" : "-rotate-90"} aria-hidden="true" />
                Schritte zur Reproduktion (optional)
              </button>
              {schritteOffen && (
                <textarea
                  aria-label="Schritte zur Reproduktion"
                  className="field-ap mt-2 min-h-20"
                  placeholder={"1. …\n2. …"}
                  value={werte.schritte}
                  onChange={(e) => setWerte({ ...werte, schritte: e.target.value })}
                />
              )}
            </div>

            <section aria-label="Mitgesendete technische Daten">
              <h3 className="mb-1 text-[13px] font-semibold tracking-wide text-label2 uppercase">Mitgesendete technische Daten</h3>
              <p className="mb-2 text-[13px] text-label2">
                Diese Daten helfen bei der Fehlersuche. Passwörter, Tokens und Kontodaten sind bereits entfernt. Du siehst
                hier genau, was gesendet wird.
              </p>
              <div className="overflow-hidden rounded-[var(--radius-ap-card)] bg-cell">
                {KATEGORIEN.filter((k) => start.kontext[k.key] !== undefined).map((k, i, liste) => {
                  const offen = vorschau.has(k.key);
                  return (
                    <div key={k.key} className="relative px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          id={`${formId}-${k.key}`}
                          checked={auswahl.has(k.key)}
                          onChange={() => schalte(auswahl, setAuswahl, k.key)}
                          style={{ accentColor: "var(--tint)" }}
                          className="h-5 w-5 shrink-0"
                        />
                        <label htmlFor={`${formId}-${k.key}`} className="min-w-0 flex-1">
                          <span className="block text-[15px] text-label">{k.label}</span>
                          <span className="block text-[13px] text-label2">{kurzinfo(k.key, start.kontext)}</span>
                        </label>
                        <button
                          type="button"
                          aria-expanded={offen}
                          aria-label={`Vorschau ${k.label}`}
                          onClick={() => schalte(vorschau, setVorschau, k.key)}
                          className="shrink-0 text-[13px] text-tint-text"
                        >
                          {offen ? "Ausblenden" : "Vorschau"}
                        </button>
                      </div>
                      {offen && (
                        <pre className="mt-2 max-h-52 overflow-auto rounded-[8px] bg-fill p-2 text-[11px] leading-snug whitespace-pre-wrap break-all text-label">
                          {JSON.stringify(start.kontext[k.key], null, 2)}
                        </pre>
                      )}
                      {i < liste.length - 1 && <span className="absolute right-0 bottom-0 left-4 h-px bg-sep" aria-hidden="true" />}
                    </div>
                  );
                })}
              </div>
            </section>

            {fehler && (
              <p role="alert" className="rounded-[var(--radius-ap-input)] bg-st-fehlt-bg p-3 text-[14px] text-st-fehlt">
                {fehler}
              </p>
            )}
            <button type="submit" disabled={!kannSenden} className="btn-ap-capsule btn-ap-capsule-primary w-full">
              {sendet ? "Sendet…" : "Fehler senden"}
            </button>
          </form>
        )}
      </div>
    </Rahmen>
  );
}
