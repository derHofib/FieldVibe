// WYSIWYG-Editor fuer die Felder/Gruppen eines Formular-Schemas (Felder-Tab
// von FormSchemaEditorPage.tsx): Kategorien-Palette links (Feldtypen als
// Drag-Quelle), Canvas in der Mitte (Formular-Vorschau via
// FormFieldRenderer, Felder/Gruppen per Drag&Drop einfuegen/umsortieren),
// feste Eigenschaften-Spalte rechts fuer das ausgewaehlte Feld/die Gruppe.
// Das Regeln-SeitenPanel bleibt unveraendert ein Overlay (siehe
// FormSchemaEditorPage.tsx) -- dieser Canvas oeffnet es nur ueber
// onRegelnOeffnen.
//
// reihenfolge-Modell: Root-Felder (group_key=null) und Gruppen teilen sich
// EINEN gemeinsamen Nummernraum (siehe CaptureRenderer.tsx, das beide beim
// Rendern zusammen nach reihenfolge sortiert) -- Einfuegen/Verschieben im
// Root-Canvas nummeriert daher Felder UND Gruppen gemeinsam durch. Felder
// innerhalb einer Gruppe haben ihren eigenen, unabhaengigen Nummernraum.
// Beim Verschieben wird nur die ZIEL-Liste neu durchnummeriert (0..n-1);
// Luecken in der reihenfolge der Quelle sind unschaedlich, da nur die
// relative Sortierung zaehlt.
import {
  closestCenter,
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, GripVertical, Layers, Rows3, SlidersHorizontal, Trash2, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { formModulApi } from "../../api/endpoints";
import type { FormFeldTyp, FormField, FormGroup, FormSchemaDetail } from "../../types";
import { FELD_TYP_KATALOG, FELD_TYP_LABEL } from "../../utils/feldTypKatalog";
import { FormFieldRenderer } from "./FormFieldRenderer";

const inputClass = "btn-touch w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink";

type Auswahl = { art: "feld"; id: string } | { art: "gruppe"; id: string } | null;
type RootEintrag =
  | { art: "feld"; reihenfolge: number; feld: FormField }
  | { art: "gruppe"; reihenfolge: number; gruppe: FormGroup };

function rootEintragId(e: RootEintrag): string {
  return e.art === "feld" ? `field:${e.feld.id}` : `group:${e.gruppe.id}`;
}

// --- Palette (Drag-Quelle) --------------------------------------------

// Abschnitt/Unterformular sind hier bewusst KEIN Sonderweg (eigener Button +
// Mini-Formular), sondern Kaestchen in der Palette wie jeder Feldtyp auch --
// "eine Gruppe ist wie ein Feld, in das ich andere Felder einfuegen und fuer
// das ich Regeln bestimmen kann" (Nutzer-Feedback). Eigene Kategorie
// "Struktur", da sie anders wirken (kein feld_typ, sondern ein Container).
const STRUKTUR_KATALOG: { dragId: string; label: string; icon: LucideIcon }[] = [
  { dragId: "struktur:abschnitt", label: "Abschnitt", icon: Layers },
  { dragId: "struktur:unterformular", label: "Unterformular", icon: Rows3 },
];

function PaletteItem({ dragId, label, icon: Icon }: { dragId: string; label: string; icon: LucideIcon }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: dragId,
    data: { kind: "palette" },
  });
  return (
    <button
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      type="button"
      style={{ touchAction: "none" }}
      className={`flex flex-col items-center gap-1 border border-ind-line p-2 text-center text-[11px] font-medium text-ind-ink-2 hover:bg-ind-hover ${
        isDragging ? "opacity-30" : ""
      }`}
    >
      <Icon size={18} strokeWidth={1.5} />
      {label}
    </button>
  );
}

function FeldTypPalette() {
  const [offeneKategorien, setOffeneKategorien] = useState<Set<string>>(new Set(["Struktur", FELD_TYP_KATALOG[0].name]));

  function toggeln(name: string) {
    setOffeneKategorien((bisher) => {
      const neu = new Set(bisher);
      if (neu.has(name)) neu.delete(name);
      else neu.add(name);
      return neu;
    });
  }

  const kategorien = [{ name: "Struktur", typen: STRUKTUR_KATALOG }, ...FELD_TYP_KATALOG.map((k) => ({ name: k.name, typen: k.typen.map((t) => ({ dragId: `palette:${t.typ}`, label: t.label, icon: t.icon })) }))];

  return (
    <div className="w-64 shrink-0 space-y-1.5 border-r border-ind-line pr-4">
      <p className="text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">Feldtypen — ziehen &amp; ablegen</p>
      {kategorien.map((kat) => {
        const offen = offeneKategorien.has(kat.name);
        return (
          <div key={kat.name} className="border border-ind-line-2">
            <button
              onClick={() => toggeln(kat.name)}
              className="flex w-full items-center gap-2 p-2 text-left text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase hover:bg-ind-hover"
            >
              {offen ? <ChevronDown size={14} strokeWidth={1.5} /> : <ChevronRight size={14} strokeWidth={1.5} />}
              {kat.name}
            </button>
            {offen && (
              <div className="grid grid-cols-2 gap-1.5 p-2 pt-0">
                {kat.typen.map(({ dragId, label, icon }) => (
                  <PaletteItem key={dragId} dragId={dragId} label={label} icon={icon} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// --- Canvas (Sortable) --------------------------------------------------

function FeldKarte({ field, ausgewaehlt, onSelect }: { field: FormField; ausgewaehlt: boolean; onSelect: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: `field:${field.id}`,
    data: { kind: "field" },
  });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, touchAction: "none" }}
      onClick={onSelect}
      className={`relative flex cursor-pointer items-start gap-1.5 border p-1 ${
        ausgewaehlt ? "border-ind-acc bg-ind-acc-soft" : "border-transparent hover:border-ind-line"
      } ${isDragging ? "opacity-30" : ""}`}
    >
      <button
        {...attributes}
        {...listeners}
        type="button"
        onClick={(e) => e.stopPropagation()}
        aria-label="Feld verschieben"
        className="mt-3 shrink-0 cursor-grab text-ind-ink-3 hover:text-ind-ink-2"
      >
        <GripVertical size={15} strokeWidth={1.5} />
      </button>
      <div className="min-w-0 flex-1">
        <FormFieldRenderer field={field} value={undefined} onChange={() => {}} readOnly required={field.pflichtfeld} />
      </div>
      <span className="absolute top-1.5 right-1.5 border border-ind-line bg-ind-bg px-1.5 py-0.5 text-[10px] text-ind-ink-3">
        {field.feld_typ}
      </span>
    </div>
  );
}

function GruppenKarte({
  gruppe,
  felder,
  ausgewaehlt,
  onSelect,
  ausgewaehltesFeldId,
  onFeldSelect,
}: {
  gruppe: FormGroup;
  felder: FormField[];
  ausgewaehlt: boolean;
  onSelect: () => void;
  ausgewaehltesFeldId: string | null;
  onFeldSelect: (id: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: `group:${gruppe.id}`,
    data: { kind: "group" },
  });
  const { setNodeRef: setDropRef, isOver } = useDroppable({ id: `group-body:${gruppe.id}` });
  const itemIds = felder.map((f) => `field:${f.id}`);

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, touchAction: "none" }}
      className={`border ${ausgewaehlt ? "border-ind-acc" : "border-ind-line-2"} ${isDragging ? "opacity-30" : ""}`}
    >
      <div onClick={onSelect} className="flex cursor-pointer items-center gap-2 border-b border-ind-line p-2">
        <button
          {...attributes}
          {...listeners}
          type="button"
          onClick={(e) => e.stopPropagation()}
          aria-label="Gruppe verschieben"
          className="shrink-0 cursor-grab text-ind-ink-3 hover:text-ind-ink-2"
        >
          <GripVertical size={15} strokeWidth={1.5} />
        </button>
        <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-ind-ink">{gruppe.label.de ?? gruppe.key}</h3>
        <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300">
          {gruppe.repeatable ? "Unterformular" : "Abschnitt"}
        </span>
      </div>
      <div ref={setDropRef} className={`space-y-1 p-2 ${isOver ? "bg-ind-acc-soft" : ""}`}>
        <SortableContext items={itemIds} strategy={verticalListSortingStrategy}>
          {felder.map((f) => (
            <FeldKarte key={f.id} field={f} ausgewaehlt={ausgewaehltesFeldId === f.id} onSelect={() => onFeldSelect(f.id)} />
          ))}
        </SortableContext>
        {felder.length === 0 && (
          <div className="border border-dashed border-ind-line-2 p-3 text-center text-xs text-ind-ink-3">Feld hierher ziehen</div>
        )}
      </div>
    </div>
  );
}

function Canvas({
  rootEntries,
  rootItemIds,
  gruppenFelder,
  ausgewaehlt,
  onSelectFeld,
  onSelectGruppe,
}: {
  rootEntries: RootEintrag[];
  rootItemIds: string[];
  gruppenFelder: (gruppeKey: string) => FormField[];
  ausgewaehlt: Auswahl;
  onSelectFeld: (id: string) => void;
  onSelectGruppe: (id: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: "root" });
  return (
    <div ref={setNodeRef} className={`mx-auto min-h-full max-w-md space-y-2 px-1 ${isOver ? "bg-ind-acc-soft/30" : ""}`}>
      <SortableContext items={rootItemIds} strategy={verticalListSortingStrategy}>
        {rootEntries.map((e) =>
          e.art === "feld" ? (
            <FeldKarte
              key={e.feld.id}
              field={e.feld}
              ausgewaehlt={ausgewaehlt?.art === "feld" && ausgewaehlt.id === e.feld.id}
              onSelect={() => onSelectFeld(e.feld.id)}
            />
          ) : (
            <GruppenKarte
              key={e.gruppe.id}
              gruppe={e.gruppe}
              felder={gruppenFelder(e.gruppe.key)}
              ausgewaehlt={ausgewaehlt?.art === "gruppe" && ausgewaehlt.id === e.gruppe.id}
              onSelect={() => onSelectGruppe(e.gruppe.id)}
              ausgewaehltesFeldId={ausgewaehlt?.art === "feld" ? ausgewaehlt.id : null}
              onFeldSelect={onSelectFeld}
            />
          ),
        )}
      </SortableContext>
      {rootEntries.length === 0 && (
        <div className="border border-dashed border-ind-line-2 p-10 text-center text-sm text-ind-ink-3">
          Feldtyp aus der Palette hierher ziehen
        </div>
      )}
    </div>
  );
}

// --- Eigenschaften-Spalte -------------------------------------------------

function InspectorLeer() {
  return <div className="p-4 text-sm text-ind-ink-3">Feld oder Gruppe im Formular auswählen, um Eigenschaften zu bearbeiten.</div>;
}

function InspectorFeld({
  feld,
  regelnAnzahl,
  onRegelnOeffnen,
  onLabelSpeichern,
  onPflichtfeldToggle,
  onLoeschen,
}: {
  feld: FormField;
  regelnAnzahl: number;
  onRegelnOeffnen: () => void;
  onLabelSpeichern: (label: string) => void;
  onPflichtfeldToggle: () => void;
  onLoeschen: () => void;
}) {
  const [label, setLabel] = useState(feld.label.de ?? feld.key);
  return (
    <div className="space-y-4 p-4">
      <div>
        <p className="mb-1 text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">Ausgewähltes Feld</p>
        <p className="text-sm font-semibold text-ind-ink">{FELD_TYP_LABEL[feld.feld_typ]}</p>
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-ind-ink-2">Bezeichnung</label>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onBlur={() => {
            const getrimmt = label.trim();
            if (getrimmt && getrimmt !== (feld.label.de ?? feld.key)) onLabelSpeichern(getrimmt);
          }}
          className={inputClass}
        />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-ind-ink-2">Feldschlüssel</label>
        <p className="border border-ind-line bg-ind-hover px-2 py-1.5 text-sm text-ind-ink-3">{feld.key}</p>
      </div>
      <label className="flex items-center justify-between border-b border-ind-line py-2 text-sm text-ind-ink-2">
        Pflichtfeld
        <input type="checkbox" checked={feld.pflichtfeld} onChange={onPflichtfeldToggle} className="h-4 w-4" />
      </label>
      <div>
        <p className="mb-1 text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">Regeln &amp; Formel</p>
        <button
          onClick={onRegelnOeffnen}
          className="flex w-full items-center justify-between border border-ind-line px-2 py-1.5 text-sm text-ind-ink-2 hover:bg-ind-hover"
        >
          <span className="flex items-center gap-1.5">
            <SlidersHorizontal size={13} strokeWidth={1.5} /> Regeln bearbeiten
          </span>
          {regelnAnzahl > 0 && <span className="text-ind-ink-3">{regelnAnzahl}</span>}
        </button>
      </div>
      <button
        onClick={onLoeschen}
        className="flex w-full items-center justify-center gap-1.5 border border-ind-line py-1.5 text-sm text-ind-ink-3 hover:border-rose-400 hover:text-rose-600"
      >
        <Trash2 size={14} strokeWidth={1.5} /> Feld löschen
      </button>
    </div>
  );
}

function InspectorGruppe({
  gruppe,
  regelnAnzahl,
  onRegelnOeffnen,
  onLabelSpeichern,
  onMinMaxSpeichern,
  onLoeschen,
}: {
  gruppe: FormGroup;
  regelnAnzahl: number;
  onRegelnOeffnen: () => void;
  onLabelSpeichern: (label: string) => void;
  onMinMaxSpeichern: (minItems: number | null, maxItems: number | null) => void;
  onLoeschen: () => void;
}) {
  const [label, setLabel] = useState(gruppe.label.de ?? gruppe.key);
  const [minItems, setMinItems] = useState(gruppe.min_items?.toString() ?? "");
  const [maxItems, setMaxItems] = useState(gruppe.max_items?.toString() ?? "");

  function minMaxSpeichern() {
    onMinMaxSpeichern(minItems ? Number(minItems) : null, maxItems ? Number(maxItems) : null);
  }

  return (
    <div className="space-y-4 p-4">
      <div>
        <p className="mb-1 text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">Ausgewählte Gruppe</p>
        <p className="text-sm font-semibold text-ind-ink">{gruppe.repeatable ? "Unterformular" : "Abschnitt"}</p>
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-ind-ink-2">Bezeichnung</label>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onBlur={() => {
            const getrimmt = label.trim();
            if (getrimmt && getrimmt !== (gruppe.label.de ?? gruppe.key)) onLabelSpeichern(getrimmt);
          }}
          className={inputClass}
        />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-ind-ink-2">Schlüssel</label>
        <p className="border border-ind-line bg-ind-hover px-2 py-1.5 text-sm text-ind-ink-3">{gruppe.key}</p>
      </div>
      {gruppe.repeatable && (
        <div>
          <label className="mb-1 block text-xs font-medium text-ind-ink-2">Einträge (optional)</label>
          <div className="grid grid-cols-2 gap-2">
            <input
              value={minItems}
              onChange={(e) => setMinItems(e.target.value)}
              onBlur={minMaxSpeichern}
              placeholder="Min."
              type="number"
              min={0}
              className={inputClass}
            />
            <input
              value={maxItems}
              onChange={(e) => setMaxItems(e.target.value)}
              onBlur={minMaxSpeichern}
              placeholder="Max."
              type="number"
              min={0}
              className={inputClass}
            />
          </div>
        </div>
      )}
      <div>
        <p className="mb-1 text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">Regeln</p>
        <button
          onClick={onRegelnOeffnen}
          className="flex w-full items-center justify-between border border-ind-line px-2 py-1.5 text-sm text-ind-ink-2 hover:bg-ind-hover"
        >
          <span className="flex items-center gap-1.5">
            <SlidersHorizontal size={13} strokeWidth={1.5} /> Regeln bearbeiten
          </span>
          {regelnAnzahl > 0 && <span className="text-ind-ink-3">{regelnAnzahl}</span>}
        </button>
      </div>
      <button
        onClick={onLoeschen}
        className="flex w-full items-center justify-center gap-1.5 border border-ind-line py-1.5 text-sm text-ind-ink-3 hover:border-rose-400 hover:text-rose-600"
      >
        <Trash2 size={14} strokeWidth={1.5} /> Gruppe löschen
      </button>
    </div>
  );
}

// --- Hauptkomponente ------------------------------------------------------

interface FormBuilderCanvasProps {
  schemaId: string;
  schema: FormSchemaDetail;
  regelnAnzahl: (key: string) => number;
  onRegelnOeffnen: (ziel: { key: string; label: string }) => void;
  invalidate: () => void;
  setFehler: (msg: string | null) => void;
}

export function FormBuilderCanvas({ schemaId, schema, regelnAnzahl, onRegelnOeffnen, invalidate, setFehler }: FormBuilderCanvasProps) {
  const [ausgewaehlt, setAusgewaehlt] = useState<Auswahl>(null);
  const [aktivId, setAktivId] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const rootEntries: RootEintrag[] = useMemo(() => {
    const felder: RootEintrag[] = schema.fields
      .filter((f) => f.group_key === null)
      .map((feld) => ({ art: "feld" as const, reihenfolge: feld.reihenfolge, feld }));
    const gruppen: RootEintrag[] = schema.groups.map((gruppe) => ({ art: "gruppe" as const, reihenfolge: gruppe.reihenfolge, gruppe }));
    return [...felder, ...gruppen].sort((a, b) => a.reihenfolge - b.reihenfolge);
  }, [schema]);
  const rootItemIds = useMemo(() => rootEntries.map(rootEintragId), [rootEntries]);

  function gruppenFelder(gruppeKey: string): FormField[] {
    return schema.fields.filter((f) => f.group_key === gruppeKey).sort((a, b) => a.reihenfolge - b.reihenfolge);
  }

  // --- Mutations ---
  const createFieldMutation = useMutation({
    mutationFn: (body: Parameters<typeof formModulApi.createField>[1]) => formModulApi.createField(schemaId, body),
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Feld konnte nicht angelegt werden"),
  });
  const updateFieldMutation = useMutation({
    mutationFn: ({ fieldId, body }: { fieldId: string; body: Partial<FormField> }) => formModulApi.updateField(schemaId, fieldId, body),
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Feld konnte nicht gespeichert werden"),
  });
  const deleteFieldMutation = useMutation({
    mutationFn: (fieldId: string) => formModulApi.deleteField(schemaId, fieldId),
    onSuccess: () => {
      setAusgewaehlt(null);
      invalidate();
    },
  });
  const createGroupMutation = useMutation({
    mutationFn: (body: Parameters<typeof formModulApi.createGroup>[1]) => formModulApi.createGroup(schemaId, body),
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Gruppe konnte nicht angelegt werden"),
  });
  const updateGroupMutation = useMutation({
    mutationFn: ({ groupId, body }: { groupId: string; body: Partial<FormGroup> }) => formModulApi.updateGroup(schemaId, groupId, body),
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Gruppe konnte nicht gespeichert werden"),
  });
  const deleteGroupMutation = useMutation({
    mutationFn: (groupId: string) => formModulApi.deleteGroup(schemaId, groupId),
    onSuccess: () => {
      setAusgewaehlt(null);
      invalidate();
    },
  });

  function generiereKey(praefix: string): string {
    const vorhandene = new Set([...schema.fields.map((f) => f.key), ...schema.groups.map((g) => g.key)]);
    let n = 1;
    let kandidat = `${praefix}_${n}`;
    while (vorhandene.has(kandidat)) {
      n += 1;
      kandidat = `${praefix}_${n}`;
    }
    return kandidat;
  }

  function aufloesen(overId: string): { containerId: string; index: number } {
    if (overId === "root") return { containerId: "root", index: rootEntries.length };
    if (overId.startsWith("group-body:")) {
      const groupId = overId.slice("group-body:".length);
      const gruppe = schema.groups.find((g) => g.id === groupId);
      return { containerId: overId, index: gruppe ? gruppenFelder(gruppe.key).length : 0 };
    }
    if (overId.startsWith("field:")) {
      const fieldId = overId.slice("field:".length);
      const feld = schema.fields.find((f) => f.id === fieldId);
      if (!feld) return { containerId: "root", index: rootEntries.length };
      if (feld.group_key) {
        const gruppe = schema.groups.find((g) => g.key === feld.group_key)!;
        const liste = gruppenFelder(gruppe.key);
        return { containerId: `group-body:${gruppe.id}`, index: Math.max(0, liste.findIndex((f) => f.id === fieldId)) };
      }
      return { containerId: "root", index: Math.max(0, rootItemIds.indexOf(`field:${fieldId}`)) };
    }
    if (overId.startsWith("group:")) {
      return { containerId: "root", index: Math.max(0, rootItemIds.indexOf(overId)) };
    }
    return { containerId: "root", index: rootEntries.length };
  }

  async function feldEinfuegen(typ: FormFeldTyp, containerId: string, index: number) {
    const gruppe = containerId === "root" ? null : schema.groups.find((g) => `group-body:${g.id}` === containerId) ?? null;
    if (containerId !== "root" && !gruppe) return;

    // Bestehende Eintraege AB der Einfuegeposition ruecken eins nach hinten
    // -- alles davor behaelt seine reihenfolge unveraendert.
    const nachfolgerIds: string[] =
      containerId === "root" ? rootItemIds.slice(index) : gruppenFelder(gruppe!.key).slice(index).map((f) => `field:${f.id}`);

    try {
      const neuesFeld = await createFieldMutation.mutateAsync({
        key: generiereKey(typ),
        feld_typ: typ,
        label: { de: FELD_TYP_LABEL[typ] },
        group_key: gruppe?.key ?? null,
        reihenfolge: index,
      });
      await Promise.all(
        nachfolgerIds.map((rid, i) => {
          const zielIndex = index + 1 + i;
          if (rid.startsWith("group:")) {
            const gid = rid.slice("group:".length);
            return updateGroupMutation.mutateAsync({ groupId: gid, body: { reihenfolge: zielIndex } });
          }
          const fid = rid.slice("field:".length);
          return updateFieldMutation.mutateAsync({ fieldId: fid, body: { reihenfolge: zielIndex } });
        }),
      );
      invalidate();
      setAusgewaehlt({ art: "feld", id: neuesFeld.id });
    } catch {
      // Fehler wurde bereits ueber die Mutation-onError-Handler gesetzt.
    }
  }

  // Abschnitt/Unterformular aus der Palette -- immer root-level (Gruppen
  // koennen nicht verschachtelt werden), sonst analog zu feldEinfuegen.
  async function gruppeEinfuegen(repeatable: boolean, index: number) {
    const nachfolgerIds = rootItemIds.slice(index);
    try {
      const neueGruppe = await createGroupMutation.mutateAsync({
        key: generiereKey(repeatable ? "unterformular" : "abschnitt"),
        label: { de: repeatable ? "Neues Unterformular" : "Neuer Abschnitt" },
        repeatable,
        reihenfolge: index,
      });
      await Promise.all(
        nachfolgerIds.map((rid, i) => {
          const zielIndex = index + 1 + i;
          if (rid.startsWith("group:")) {
            const gid = rid.slice("group:".length);
            return updateGroupMutation.mutateAsync({ groupId: gid, body: { reihenfolge: zielIndex } });
          }
          const fid = rid.slice("field:".length);
          return updateFieldMutation.mutateAsync({ fieldId: fid, body: { reihenfolge: zielIndex } });
        }),
      );
      invalidate();
      setAusgewaehlt({ art: "gruppe", id: neueGruppe.id });
    } catch {
      // Fehler wurde bereits ueber die Mutation-onError-Handler gesetzt.
    }
  }

  async function feldVerschieben(fieldId: string, zielContainerId: string, zielIndex: number) {
    const feld = schema.fields.find((f) => f.id === fieldId);
    if (!feld) return;
    const zielGruppe = zielContainerId === "root" ? null : schema.groups.find((g) => `group-body:${g.id}` === zielContainerId) ?? null;
    if (zielContainerId !== "root" && !zielGruppe) return;

    const zielIds: string[] =
      zielContainerId === "root"
        ? rootItemIds.filter((rid) => rid !== `field:${fieldId}`)
        : gruppenFelder(zielGruppe!.key)
            .filter((f) => f.id !== fieldId)
            .map((f) => `field:${f.id}`);
    zielIds.splice(Math.min(zielIndex, zielIds.length), 0, `field:${fieldId}`);

    try {
      await Promise.all(
        zielIds.map((rid, i) => {
          if (rid.startsWith("group:")) {
            const gid = rid.slice("group:".length);
            const aktuelle = schema.groups.find((g) => g.id === gid)!;
            return aktuelle.reihenfolge === i ? null : updateGroupMutation.mutateAsync({ groupId: gid, body: { reihenfolge: i } });
          }
          const fid = rid.slice("field:".length);
          const istVerschobenes = fid === fieldId;
          const aktuelles = istVerschobenes ? feld : schema.fields.find((f) => f.id === fid)!;
          const neueGruppeKey = zielGruppe?.key ?? null;
          const aendertSich = istVerschobenes ? aktuelles.group_key !== neueGruppeKey || aktuelles.reihenfolge !== i : aktuelles.reihenfolge !== i;
          if (!aendertSich) return null;
          return updateFieldMutation.mutateAsync({
            fieldId: fid,
            body: istVerschobenes ? { group_key: neueGruppeKey, reihenfolge: i } : { reihenfolge: i },
          });
        }),
      );
      invalidate();
    } catch {
      // Fehler wurde bereits ueber die Mutation-onError-Handler gesetzt.
    }
  }

  async function gruppeVerschieben(groupId: string, zielIndex: number) {
    const zielIds = rootItemIds.filter((rid) => rid !== `group:${groupId}`);
    zielIds.splice(Math.min(zielIndex, zielIds.length), 0, `group:${groupId}`);
    try {
      await Promise.all(
        zielIds.map((rid, i) => {
          if (rid.startsWith("group:")) {
            const gid = rid.slice("group:".length);
            const aktuelle = schema.groups.find((g) => g.id === gid)!;
            return aktuelle.reihenfolge === i ? null : updateGroupMutation.mutateAsync({ groupId: gid, body: { reihenfolge: i } });
          }
          const fid = rid.slice("field:".length);
          const aktuelles = schema.fields.find((f) => f.id === fid)!;
          return aktuelles.reihenfolge === i ? null : updateFieldMutation.mutateAsync({ fieldId: fid, body: { reihenfolge: i } });
        }),
      );
      invalidate();
    } catch {
      // Fehler wurde bereits ueber die Mutation-onError-Handler gesetzt.
    }
  }

  function handleDragStart(event: DragStartEvent) {
    setAktivId(String(event.active.id));
  }

  async function handleDragEnd(event: DragEndEvent) {
    setAktivId(null);
    const { active, over } = event;
    if (!over) return;
    const activeId = String(active.id);
    const overId = String(over.id);
    if (activeId === overId) return;

    if (activeId.startsWith("struktur:")) {
      const { containerId, index } = aufloesen(overId);
      // Abschnitt/Unterformular koennen nicht in einer anderen Gruppe
      // liegen -- landet man ueber einem Gruppen-Innenraum, faellt die
      // Position auf "Ende der Wurzel-Liste" zurueck statt den Drop zu
      // verwerfen (fuehlt sich beim Ziehen sonst wie ein Bug an).
      const zielIndex = containerId === "root" ? index : rootEntries.length;
      await gruppeEinfuegen(activeId === "struktur:unterformular", zielIndex);
      return;
    }
    if (activeId.startsWith("palette:")) {
      const typ = activeId.slice("palette:".length) as FormFeldTyp;
      const { containerId, index } = aufloesen(overId);
      await feldEinfuegen(typ, containerId, index);
      return;
    }
    if (activeId.startsWith("field:")) {
      const fieldId = activeId.slice("field:".length);
      const { containerId, index } = aufloesen(overId);
      await feldVerschieben(fieldId, containerId, index);
      return;
    }
    if (activeId.startsWith("group:")) {
      const { containerId, index } = aufloesen(overId);
      if (containerId !== "root") return; // Gruppen koennen nicht verschachtelt werden
      await gruppeVerschieben(activeId.slice("group:".length), index);
    }
  }

  const ausgewaehltesFeld = ausgewaehlt?.art === "feld" ? schema.fields.find((f) => f.id === ausgewaehlt.id) ?? null : null;
  const ausgewaehlteGruppe = ausgewaehlt?.art === "gruppe" ? schema.groups.find((g) => g.id === ausgewaehlt.id) ?? null : null;

  return (
    // Durchbricht das mx-auto max-w-2xl der Feld-App-Shell (FeldLayout.tsx)
    // -- die ist auf schmale, mobile Listen-Seiten ausgelegt, der WYSIWYG-
    // Builder mit drei Spalten braucht dagegen die volle Breite. Betrifft
    // bewusst nur diesen Tab, nicht die restlichen Feld-App-Seiten. Ueber
    // negative Margins statt left-1/2 + transform: dnd-kit's DragOverlay
    // ist NICHT in einem Portal (position:fixed, inline im Baum) -- ein
    // transform auf einem Vorfahren macht diesen zum Containing-Block fuer
    // position:fixed und hat den Overlay weit vom Cursor weg gerissen.
    <div className="mx-[calc(50%-50vw)] w-screen max-w-none space-y-2 px-3 sm:px-6">
      <p className="mx-auto max-w-[1400px] text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">Formular</p>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="mx-auto flex max-w-[1400px] gap-4 border border-ind-line bg-ind-bg" style={{ minHeight: 520 }}>
          <div className="p-3">
            <FeldTypPalette />
          </div>
          <div className="max-h-[70vh] flex-1 overflow-y-auto py-3">
            <Canvas
              rootEntries={rootEntries}
              rootItemIds={rootItemIds}
              gruppenFelder={gruppenFelder}
              ausgewaehlt={ausgewaehlt}
              onSelectFeld={(id) => setAusgewaehlt({ art: "feld", id })}
              onSelectGruppe={(id) => setAusgewaehlt({ art: "gruppe", id })}
            />
          </div>
          <div className="w-72 shrink-0 border-l border-ind-line">
            {ausgewaehltesFeld ? (
              <InspectorFeld
                key={ausgewaehltesFeld.id}
                feld={ausgewaehltesFeld}
                regelnAnzahl={regelnAnzahl(ausgewaehltesFeld.key)}
                onRegelnOeffnen={() => onRegelnOeffnen({ key: ausgewaehltesFeld.key, label: ausgewaehltesFeld.label.de ?? ausgewaehltesFeld.key })}
                onLabelSpeichern={(label) => updateFieldMutation.mutate({ fieldId: ausgewaehltesFeld.id, body: { label: { de: label } } }, { onSuccess: invalidate })}
                onPflichtfeldToggle={() =>
                  updateFieldMutation.mutate(
                    { fieldId: ausgewaehltesFeld.id, body: { pflichtfeld: !ausgewaehltesFeld.pflichtfeld } },
                    { onSuccess: invalidate },
                  )
                }
                onLoeschen={() => deleteFieldMutation.mutate(ausgewaehltesFeld.id)}
              />
            ) : ausgewaehlteGruppe ? (
              <InspectorGruppe
                key={ausgewaehlteGruppe.id}
                gruppe={ausgewaehlteGruppe}
                regelnAnzahl={regelnAnzahl(ausgewaehlteGruppe.key)}
                onRegelnOeffnen={() => onRegelnOeffnen({ key: ausgewaehlteGruppe.key, label: ausgewaehlteGruppe.label.de ?? ausgewaehlteGruppe.key })}
                onLabelSpeichern={(label) =>
                  updateGroupMutation.mutate({ groupId: ausgewaehlteGruppe.id, body: { label: { de: label } } }, { onSuccess: invalidate })
                }
                onMinMaxSpeichern={(minItems, maxItems) =>
                  updateGroupMutation.mutate(
                    { groupId: ausgewaehlteGruppe.id, body: { min_items: minItems, max_items: maxItems } },
                    { onSuccess: invalidate },
                  )
                }
                onLoeschen={() => deleteGroupMutation.mutate(ausgewaehlteGruppe.id)}
              />
            ) : (
              <InspectorLeer />
            )}
          </div>
        </div>
        <DragOverlay>
          {aktivId?.startsWith("struktur:") && (
            <div className="border border-ind-acc bg-ind-bg px-3 py-2 text-sm text-ind-ink shadow-lg">
              {aktivId === "struktur:unterformular" ? "Unterformular" : "Abschnitt"}
            </div>
          )}
          {aktivId?.startsWith("palette:") && (
            <div className="border border-ind-acc bg-ind-bg px-3 py-2 text-sm text-ind-ink shadow-lg">
              {FELD_TYP_LABEL[aktivId.slice("palette:".length) as FormFeldTyp]}
            </div>
          )}
          {aktivId?.startsWith("field:") &&
            (() => {
              const f = schema.fields.find((x) => x.id === aktivId.slice("field:".length));
              return f ? <div className="border border-ind-acc bg-ind-bg px-3 py-2 text-sm text-ind-ink shadow-lg">{f.label.de ?? f.key}</div> : null;
            })()}
          {aktivId?.startsWith("group:") &&
            (() => {
              const g = schema.groups.find((x) => x.id === aktivId.slice("group:".length));
              return g ? (
                <div className="border border-ind-acc bg-ind-bg px-3 py-2 text-sm font-semibold text-ind-ink shadow-lg">{g.label.de ?? g.key}</div>
              ) : null;
            })()}
        </DragOverlay>
      </DndContext>
    </div>
  );
}
