// Baukasten-Tab "Visualisierung": links die Ansichten der Vorlage (mit verständlichen
// Namen), in der Mitte eine Vorschau mit Beispieldaten, rechts die Eigenschaften eines
// Feldes der Druckansicht (Seite, Position und Breite in mm). Freies Ziehen mit der Maus
// gibt es bewusst nicht -- die Zahlenfelder reichen für Korrekturen am Druck-Layout.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Globe, List, Plus, Printer, Smartphone, Table2, Trash2, Wand2, type LucideIcon } from "lucide-react";
import { useId, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { formModulApi, formSubmissionsApi } from "../../api/endpoints";
import { beispielWerte } from "../../office/formulare/beispielwerte";
import { PdfVorschau } from "../../office/formulare/PdfVorschau";
import { useSchemaDaten } from "../../office/formulare/useSchemaDaten";
import type { FormSchemaDetail, FormView, FormViewFieldLayout, FormViewTyp } from "../../types";
import { FORM_VIEW_TYP_BESCHREIBUNG, FORM_VIEW_TYP_LABEL } from "../../utils/formular";
import { openPdfBlob } from "../../utils/pdf";
import { AktionsMenue } from "../AktionsMenue";
import { type KachelFarbe, SymbolKachel } from "../apple/SymbolKachel";
import { Select } from "../apple/Select";
import { useBestaetigung } from "../ConfirmDialog";
import { EmptyState } from "../EmptyState";
import { CaptureRenderer } from "./CaptureRenderer";
import { SummaryRenderer } from "./SummaryRenderer";

const ALLE_TYPEN: FormViewTyp[] = ["capture", "summary", "print", "table", "public"];
const KACHEL: Record<FormViewTyp, { icon: LucideIcon; farbe: KachelFarbe }> = {
  capture: { icon: Smartphone, farbe: "blue" },
  summary: { icon: List, farbe: "green" },
  print: { icon: Printer, farbe: "indigo" },
  table: { icon: Table2, farbe: "gray" },
  public: { icon: Globe, farbe: "orange" },
};

const PLATZHALTER = "__platzhalter__";
const nichts = () => {};
const zahlKlasse = "w-full rounded-[var(--radius-ap-input)] bg-fill px-2 py-1 text-right text-fliess tabular-nums text-label";

export function VisualisierungTab({
  schemaId,
  schema,
  onGeaendert,
  setFehler,
}: {
  schemaId: string;
  schema: FormSchemaDetail;
  onGeaendert: () => void;
  setFehler: (m: string | null) => void;
}) {
  const bestaetigen = useBestaetigung();
  const queryClient = useQueryClient();
  const { views, rules, capture, summary, captureId, summaryId, printId } = useSchemaDaten(schemaId);
  const liste = useMemo(() => [...(views.data ?? [])].sort((a, b) => ALLE_TYPEN.indexOf(a.type) - ALLE_TYPEN.indexOf(b.type)), [views.data]);
  const [gewaehlt, setGewaehlt] = useState<string | null>(null);
  const aktiv: FormView | undefined = liste.find((v) => v.id === gewaehlt) ?? liste[0];
  const [beispielId, setBeispielId] = useState(PLATZHALTER);

  const druck = useQuery({
    queryKey: ["form-view-resolved", printId],
    queryFn: () => formModulApi.getView(schemaId, printId!),
    enabled: !!printId,
  });

  const fehlend = ALLE_TYPEN.filter((t) => !liste.some((v) => v.type === t));

  const protokolle = useQuery({
    queryKey: ["form-submissions-uebersicht", { schema_id: schemaId, status: "abgeschlossen" }, 1],
    queryFn: () => formSubmissionsApi.uebersicht({ schema_id: schemaId, status: "abgeschlossen" }),
  });
  const eintraege = protokolle.data?.eintraege ?? [];
  // Beispiel-Auswahl immer gültig halten: ein nicht mehr vorhandenes Protokoll fällt auf Platzhalter zurück.
  const echtesId = beispielId !== PLATZHALTER && eintraege.some((e) => e.id === beispielId) ? beispielId : null;
  const echtes = useQuery({
    queryKey: ["form-submission", echtesId],
    queryFn: () => formSubmissionsApi.get(echtesId!),
    enabled: !!echtesId,
  });
  const platzhalter = useMemo(() => beispielWerte(schema.fields, schema.groups), [schema.fields, schema.groups]);
  const werte = echtesId && echtes.data ? echtes.data.values : platzhalter;

  const createView = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: (typ: FormViewTyp) => formModulApi.createView(schemaId, { type: typ, name: FORM_VIEW_TYP_LABEL[typ] }),
    onSuccess: (v) => {
      setGewaehlt(v.id);
      onGeaendert();
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Die Ansicht konnte nicht angelegt werden"),
  });
  const deleteView = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: (viewId: string) => formModulApi.deleteView(schemaId, viewId),
    onSuccess: () => {
      setGewaehlt(null);
      onGeaendert();
    },
  });

  const layoutErneuern = () => {
    onGeaendert();
    if (printId) queryClient.invalidateQueries({ queryKey: ["form-view-resolved", printId] });
    queryClient.invalidateQueries({ queryKey: ["form-vorschau-pdf", schemaId] });
  };
  const speichereLayouts = useMutation({
    mutationFn: (layouts: Omit<FormViewFieldLayout, "id">[]) => formModulApi.replaceLayouts(schemaId, printId!, layouts),
    onSuccess: layoutErneuern,
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Das Layout konnte nicht gespeichert werden"),
  });
  const layoutAusFeldern = () => {
    const root = schema.fields.filter((f) => f.group_key === null).sort((a, b) => a.reihenfolge - b.reihenfolge);
    speichereLayouts.mutate(root.map((f, i) => ({ field_key: f.key, seite: 0, x_mm: 0, y_mm: i * 12, breite_mm: 85, hoehe_mm: 10 })));
  };

  const pdfOeffnen = useMutation({
    mutationFn: () => formModulApi.vorschauPdf(schemaId, printId!, echtesId ?? undefined),
    onSuccess: openPdfBlob,
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Die PDF-Vorschau konnte nicht erzeugt werden"),
  });

  async function loeschen(v: FormView) {
    const ok = await bestaetigen({
      titel: `Ansicht „${FORM_VIEW_TYP_LABEL[v.type]}“ löschen?`,
      text: "Die Felder bleiben erhalten; nur diese Darstellung und ihr Layout entfallen.",
      bestaetigenLabel: "Löschen",
    });
    if (ok) deleteView.mutate(v.id);
  }

  if (views.isLoading) return <EmptyState icon={Eye} text="Ansichten werden geladen …" />;

  const istDruck = aktiv?.type === "print";
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[260px_minmax(0,1fr)] xl:grid-cols-[260px_minmax(0,1fr)_300px]">
      {/* Ansichten */}
      <section aria-label="Ansichten" className="card-ap p-3">
        <h2 className="mb-2 px-1 text-meta font-semibold tracking-wide text-label2 uppercase">Ansichten</h2>
        <ul className="space-y-1">
          {liste.map((v) => {
            const k = KACHEL[v.type];
            const ist = v.id === aktiv?.id;
            return (
              <li key={v.id} className={`group flex items-center rounded-[var(--radius-ap-md)] ${ist ? "bg-tintbg" : "hover:bg-fill"}`}>
                <button type="button" aria-pressed={ist} onClick={() => setGewaehlt(v.id)} className="flex min-w-0 flex-1 items-center gap-3 p-2 text-left">
                  <SymbolKachel icon={k.icon} farbe={k.farbe} />
                  <span className="min-w-0">
                    <span className="block text-fliess font-semibold text-label">{FORM_VIEW_TYP_LABEL[v.type]}</span>
                    <span className="block text-meta text-label2">{FORM_VIEW_TYP_BESCHREIBUNG[v.type]}</span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => void loeschen(v)}
                  aria-label={`Ansicht ${FORM_VIEW_TYP_LABEL[v.type]} löschen`}
                  className="mr-1 rounded-full p-1.5 text-label2 hover:text-st-fehlt focus-visible:opacity-100 md:opacity-0 md:group-hover:opacity-100"
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
        {fehlend.length > 0 && (
          <div className="mt-2">
            <AktionsMenue
              label="Ansicht hinzufügen"
              eintraege={fehlend.map((t) => ({ label: FORM_VIEW_TYP_LABEL[t], icon: Plus, onClick: () => createView.mutate(t) }))}
              ausloeser={() => (
                <span className="flex items-center gap-2 px-1 py-1 text-fliess text-label2">
                  <Plus size={16} aria-hidden="true" /> Ansicht hinzufügen
                </span>
              )}
            />
          </div>
        )}
        <p className="mt-3 border-t-[0.5px] border-sep px-1 pt-3 text-sekundaer text-label2">
          Jede Ansicht zeigt dieselben Daten anders. Änderungen an Feldern wirken in allen Ansichten.
        </p>
      </section>

      {/* Vorschau */}
      <section aria-label="Vorschau" className="card-ap min-w-0 p-3">
        {!aktiv ? (
          <EmptyState
            icon={Eye}
            text="Diese Vorlage hat noch keine Ansicht. Lege links eine an, um eine Vorschau zu sehen."
            action={
              <button type="button" onClick={() => createView.mutate("print")} className="btn-ap px-4 py-2 text-sekundaer">
                Druckansicht anlegen
              </button>
            }
          />
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <label htmlFor="beispiel-auswahl" className="text-sekundaer text-label2">
                Beispieldaten
              </label>
              <div className="min-w-[200px]">
                <Select id="beispiel-auswahl" value={echtesId ?? PLATZHALTER} onChange={(e) => setBeispielId(e.target.value)}>
                  <option value={PLATZHALTER}>Platzhalter</option>
                  {eintraege.map((e) => (
                    <option key={e.id} value={e.id}>
                      Protokoll {e.vorgangsnummer}
                      {e.kunde_name ? ` · ${e.kunde_name}` : ""}
                    </option>
                  ))}
                </Select>
              </div>
              {istDruck && (
                <div className="ml-auto flex gap-2">
                  <button
                    type="button"
                    onClick={layoutAusFeldern}
                    disabled={speichereLayouts.isPending}
                    className="btn-ap inline-flex h-8 items-center gap-1.5 px-3 text-sekundaer disabled:opacity-50"
                  >
                    <Wand2 size={14} aria-hidden="true" /> Layout aus Feldern
                  </button>
                  <button
                    type="button"
                    onClick={() => pdfOeffnen.mutate()}
                    disabled={pdfOeffnen.isPending}
                    className="btn-ap inline-flex h-8 items-center gap-1.5 px-3 text-sekundaer disabled:opacity-50"
                  >
                    <Eye size={14} aria-hidden="true" /> PDF-Vorschau
                  </button>
                </div>
              )}
            </div>
            {schema.fields.length === 0 && !istDruck ? (
              <EmptyState icon={Eye} text="Noch keine Felder: Im Tab Felder anlegen, dann erscheint hier die Vorschau." />
            ) : aktiv.type === "capture" ? (
              <CaptureRenderer
                fields={schema.fields}
                groups={schema.groups}
                rules={rules.data ?? []}
                elements={capture.data?.elements ?? []}
                values={werte}
                onChange={nichts}
                readOnly
                viewId={captureId ?? null}
              />
            ) : aktiv.type === "summary" ? (
              <SummaryRenderer
                fields={schema.fields}
                groups={schema.groups}
                rules={rules.data ?? []}
                elements={summary.data?.elements ?? []}
                values={werte}
                viewId={summaryId ?? null}
              />
            ) : istDruck ? (
              <PdfVorschau schemaId={schemaId} viewId={aktiv.id} submissionId={echtesId ?? undefined} hoehe="h-[720px]" />
            ) : (
              <EmptyState icon={Eye} text={`Für die Ansicht „${FORM_VIEW_TYP_LABEL[aktiv.type]}“ gibt es noch keine Vorschau.`} />
            )}
          </>
        )}
      </section>

      {/* Eigenschaften (nur Druck) */}
      {istDruck && aktiv && (
        <LayoutEigenschaften
          schema={schema}
          layouts={druck.data?.layouts}
          onSpeichern={(l) => speichereLayouts.mutate(l)}
          pending={speichereLayouts.isPending}
        />
      )}
    </div>
  );
}

/** Position und Breite eines Feldes im A4-Layout. Auswahl per Feldliste statt Klick ins
 * Blatt: die Vorschau ist ein PDF und kennt keine Elemente. */
function LayoutEigenschaften({
  schema,
  layouts,
  onSpeichern,
  pending,
}: {
  schema: FormSchemaDetail;
  layouts: FormViewFieldLayout[] | undefined;
  onSpeichern: (l: Omit<FormViewFieldLayout, "id">[]) => void;
  pending: boolean;
}) {
  const uid = useId();
  const felder = schema.fields.filter((f) => f.group_key === null);
  const [key, setKey] = useState<string>("");
  const feld = felder.find((f) => f.key === key) ?? felder[0];
  const layout = layouts?.find((l) => l.field_key === feld?.key);

  const ohneId = (l: FormViewFieldLayout): Omit<FormViewFieldLayout, "id"> => ({
    field_key: l.field_key,
    seite: l.seite,
    x_mm: l.x_mm,
    y_mm: l.y_mm,
    breite_mm: l.breite_mm,
    hoehe_mm: l.hoehe_mm,
  });

  function aendern(teil: Partial<Omit<FormViewFieldLayout, "id" | "field_key">>) {
    if (!feld || !layouts || !layout) return;
    onSpeichern(layouts.map((l) => (l.id === layout.id ? { ...ohneId(l), ...teil } : ohneId(l))));
  }
  function hinzufuegen() {
    if (!feld || !layouts) return;
    const unten = layouts.reduce((m, l) => Math.max(m, l.y_mm + l.hoehe_mm), 0);
    onSpeichern([...layouts.map(ohneId), { field_key: feld.key, seite: 0, x_mm: 0, y_mm: unten + 2, breite_mm: 85, hoehe_mm: 10 }]);
  }

  return (
    <section aria-label="Eigenschaften" className="card-ap p-4 lg:col-span-2 xl:col-span-1">
      <h2 className="mb-2 text-meta font-semibold tracking-wide text-label2 uppercase">Ausgewählt</h2>
      {felder.length === 0 ? (
        <p className="text-sekundaer text-label2">Noch keine Felder.</p>
      ) : (
        <div className="space-y-3">
          <div>
            <label htmlFor={`${uid}-feld`} className="sr-only">
              Feld wählen
            </label>
            <Select id={`${uid}-feld`} value={feld?.key ?? ""} onChange={(e) => setKey(e.target.value)}>
              {felder.map((f) => (
                <option key={f.id} value={f.key}>
                  {f.label.de ?? f.key}
                </option>
              ))}
            </Select>
          </div>
          {!layouts ? null : !layout ? (
            <div className="space-y-2">
              <p className="text-sekundaer text-label2">Dieses Feld steht noch nicht im Druck-Layout.</p>
              <button type="button" onClick={hinzufuegen} disabled={pending} className="btn-ap h-8 px-3 text-sekundaer disabled:opacity-50">
                Zum Layout hinzufügen
              </button>
            </div>
          ) : (
            <dl className="space-y-2" key={`${layout.id}-${layout.seite}-${layout.x_mm}-${layout.y_mm}-${layout.breite_mm}`}>
              <ZahlZeile id={`${uid}-seite`} label="Seite" wert={layout.seite + 1} min={1} schritt={1} onFertig={(n) => aendern({ seite: Math.max(0, Math.round(n) - 1) })} />
              <ZahlZeile id={`${uid}-x`} label="Position x (mm)" wert={layout.x_mm} onFertig={(n) => aendern({ x_mm: n })} />
              <ZahlZeile id={`${uid}-y`} label="Position y (mm)" wert={layout.y_mm} onFertig={(n) => aendern({ y_mm: n })} />
              <ZahlZeile id={`${uid}-b`} label="Breite (mm)" wert={layout.breite_mm} min={1} onFertig={(n) => aendern({ breite_mm: n })} />
            </dl>
          )}
        </div>
      )}
    </section>
  );
}

function ZahlZeile({ id, label, wert, min = 0, schritt = 0.5, onFertig }: { id: string; label: string; wert: number; min?: number; schritt?: number; onFertig: (n: number) => void }) {
  const [text, setText] = useState(String(wert));
  function fertig() {
    const n = Number(text.replace(",", "."));
    if (!Number.isFinite(n) || n < min) {
      setText(String(wert));
      return;
    }
    if (n !== wert) onFertig(n);
  }
  return (
    <div className="flex items-center justify-between gap-3 border-b-[0.5px] border-sep pb-2 last:border-b-0">
      <label htmlFor={id} className="text-fliess text-label">
        {label}
      </label>
      <input
        id={id}
        inputMode="decimal"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={fertig}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        step={schritt}
        className={`${zahlKlasse} max-w-[90px]`}
      />
    </div>
  );
}
