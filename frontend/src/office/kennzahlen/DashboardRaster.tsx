import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, rectSortingStrategy, sortableKeyboardCoordinates, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import type { ReactNode } from "react";

import type { DashboardWidget, WidgetGroesse } from "../../types/kennzahlen";

// Vollständige Klassennamen (keine zusammengesetzten): Tailwind findet nur, was als Text im Quelltext steht.
// ≥1280px: S=3, M=4, L=6, XL=12 von 12 Spalten; 768-1279px: S/M halbe Breite, L/XL ganze; darunter eine Spalte.
const SPANNE: Record<WidgetGroesse, string> = {
  s: "col-span-12 md:col-span-6 xl:col-span-3",
  m: "col-span-12 md:col-span-6 xl:col-span-4",
  l: "col-span-12 xl:col-span-6",
  xl: "col-span-12",
};

export interface RasterKontext {
  /** Ziehgriff; nur im Bearbeiten-Modus gesetzt. */
  griff: ReactNode;
}

interface Props {
  widgets: DashboardWidget[];
  bearbeiten: boolean;
  onReihenfolge: (ids: string[]) => void;
  renderWidget: (widget: DashboardWidget, kontext: RasterKontext) => ReactNode;
}

const RASTER_KLASSE = "grid grid-flow-dense grid-cols-12 gap-4";

/** 12-Spalten-Raster über die volle Breite. Die Reihenfolge der Liste ist die Position; im Bearbeiten-Modus
 * sortiert dnd-kit per Maus und Tastatur (Griff fokussieren, Leertaste, Pfeiltasten). Feste Größen statt freier
 * Platzierung: ein x/y-Raster bräche bei anderen Bildschirmbreiten und wäre per Tastatur kaum bedienbar. */
export function DashboardRaster({ widgets, bearbeiten, onReihenfolge, renderWidget }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  if (!bearbeiten) {
    return (
      <div className={RASTER_KLASSE}>
        {widgets.map((widget) => (
          <div key={widget.id} className={SPANNE[widget.groesse]}>
            {renderWidget(widget, { griff: null })}
          </div>
        ))}
      </div>
    );
  }

  function dragEnde({ active, over }: DragEndEvent) {
    if (!over || active.id === over.id) return;
    const ids = widgets.map((w) => w.id);
    const von = ids.indexOf(String(active.id));
    const nach = ids.indexOf(String(over.id));
    if (von < 0 || nach < 0) return;
    onReihenfolge(arrayMove(ids, von, nach));
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={dragEnde}>
      <SortableContext items={widgets.map((w) => w.id)} strategy={rectSortingStrategy}>
        <div className={RASTER_KLASSE}>
          {widgets.map((widget) => (
            <SortierbaresWidget key={widget.id} widget={widget} renderWidget={renderWidget} />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}

function SortierbaresWidget({ widget, renderWidget }: { widget: DashboardWidget; renderWidget: Props["renderWidget"] }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: widget.id,
  });
  return (
    <div
      ref={setNodeRef}
      className={`${SPANNE[widget.groesse]} ${isDragging ? "relative z-10 opacity-80" : ""}`}
      style={{ transform: CSS.Transform.toString(transform), transition }}
    >
      {renderWidget(widget, {
        griff: (
          <button
            type="button"
            ref={setActivatorNodeRef}
            aria-label="Widget verschieben"
            title="Ziehen zum Sortieren"
            className="btn-ap-toolbar shrink-0 cursor-grab touch-none text-label2"
            onClick={(e) => e.stopPropagation()}
            {...attributes}
            {...listeners}
          >
            <GripVertical size={15} strokeWidth={2} aria-hidden="true" />
          </button>
        ),
      })}
    </div>
  );
}
