import {
  BaseEdge,
  Controls,
  getSmoothStepPath,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import type { Position } from "../../types/organigramm";
import { nachfahren as nachfahrenVon, berechneLayout, type LayoutKnoten } from "./layout";
import {
  DiagrammKontext,
  PositionKnoten,
  type PositionKnotenTyp,
} from "./PositionKnoten";

// Linien-Kanten laufen als Sammelschiene knapp unter dem Elternknoten, damit sie nicht
// quer durch die Zwischenebene der Stabsstellen fuehren.
const KANTEN_STEP = 0.14;

function OrgKante(props: EdgeProps) {
  const stab = (props.data as { stab?: boolean } | undefined)?.stab === true;
  const [pfad] = getSmoothStepPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
    borderRadius: 10,
    stepPosition: stab ? 0.5 : KANTEN_STEP,
  });
  return (
    <BaseEdge
      id={props.id}
      path={pfad}
      style={{
        stroke: stab ? "var(--tint)" : "var(--sepstrong)",
        strokeWidth: 1.5,
        strokeDasharray: stab ? "6 4" : undefined,
      }}
    />
  );
}

const NODE_TYPES = { position: PositionKnoten };
const EDGE_TYPES = { org: OrgKante };

// Die React-Flow-Bedienelemente folgen ueber ihre Custom Properties den Design-Token (Hell/Dunkel).
const FLOW_STIL = {
  "--xy-controls-button-background-color-default": "var(--card)",
  "--xy-controls-button-background-color-hover-default": "var(--fill)",
  "--xy-controls-button-color-default": "var(--label)",
  "--xy-controls-button-border-color-default": "var(--sep)",
  "--xy-minimap-background-color-default": "var(--card)",
  "--xy-minimap-mask-background-color-default": "rgba(120,120,128,0.18)",
  "--xy-background-color-default": "transparent",
} as CSSProperties;

function knotenAusPunkt(x: number, y: number, ausser: string): string | null {
  for (const el of document.elementsFromPoint(x, y)) {
    const knoten = (el as HTMLElement).closest?.(".react-flow__node");
    const id = knoten?.getAttribute("data-id");
    if (id && id !== ausser) return id;
  }
  return null;
}

function zeiger(e: MouseEvent | TouchEvent): { x: number; y: number } {
  if ("changedTouches" in e && e.changedTouches.length > 0) {
    return { x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY };
  }
  const m = e as MouseEvent;
  return { x: m.clientX, y: m.clientY };
}

export interface OrganigrammDiagrammProps {
  positionen: Position[];
  // Positionen, die im Baum erscheinen (Filter: Treffer + Pfad); Rest wird ausgeblendet
  sichtbar: Set<string>;
  treffer: Set<string>;
  filterAktiv: boolean;
  eingeklappt: Set<string>;
  ausgewaehltId: string | null;
  darfUmhaengen: boolean;
  onWaehlen: (id: string) => void;
  onMenue: (position: Position, anker: { x: number; y: number }, umschalten?: boolean) => void;
  onUmschalten: (id: string) => void;
  onUmhaengen: (id: string, neuerParentId: string) => void;
  // Meldung, wenn das Umhaengen schon clientseitig als unmoeglich erkannt wird
  onUngueltigerDrop: (grund: string) => void;
}

function Flaeche(props: OrganigrammDiagrammProps) {
  const { positionen, sichtbar, treffer, filterAktiv, eingeklappt, darfUmhaengen } = props;
  const { fitView } = useReactFlow();
  const [dropZielId, setDropZielId] = useState<string | null>(null);

  const knoten = useMemo(() => positionen.filter((p) => sichtbar.has(p.id)), [positionen, sichtbar]);
  const layoutKnoten: LayoutKnoten[] = useMemo(
    () => knoten.map((p) => ({ id: p.id, parentId: p.parent_id, typ: p.typ })),
    [knoten],
  );
  // Mit aktivem Filter alles aufgeklappt, sonst waeren Treffer unter zugeklappten Knoten unsichtbar.
  const effektivEingeklappt = useMemo(() => (filterAktiv ? new Set<string>() : eingeklappt), [filterAktiv, eingeklappt]);
  const layout = useMemo(() => berechneLayout(layoutKnoten, effektivEingeklappt), [layoutKnoten, effektivEingeklappt]);

  const flowKnoten = useMemo<PositionKnotenTyp[]>(() => {
    return knoten
      .filter((p) => layout.positionen.has(p.id))
      .map((p) => ({
        id: p.id,
        type: "position" as const,
        position: layout.positionen.get(p.id)!,
        draggable: darfUmhaengen && !p.kontext && p.parent_id !== null,
        selectable: false,
        // React Flow setzt sonst pointer-events:none auf nicht ziehbare Knoten (Wurzel, Pfadknoten, ohne Recht) -- ihre Buttons waeren tot.
        style: { pointerEvents: "all" as const },
        data: {
          position: p,
          kinder: layout.kinderAnzahl.get(p.id) ?? 0,
          zugeklappt: !filterAktiv && eingeklappt.has(p.id),
          gedimmt: filterAktiv && !treffer.has(p.id),
        },
      }));
  }, [knoten, layout, darfUmhaengen, filterAktiv, eingeklappt, treffer]);

  const flowKanten = useMemo<Edge[]>(
    () =>
      layout.kanten.map((k) => ({
        id: k.id,
        source: k.quelle,
        target: k.ziel,
        type: "org",
        sourceHandle: k.stab ? "r" : "b",
        targetHandle: k.stab ? "l" : "t",
        data: { stab: k.stab },
        focusable: false,
      })),
    [layout],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<PositionKnotenTyp>(flowKnoten);
  useEffect(() => setNodes(flowKnoten), [flowKnoten, setNodes]);

  // Einmal einpassen, sobald erstmals Knoten da sind (die Daten kommen asynchron).
  const eingepasst = useRef(false);
  useEffect(() => {
    if (eingepasst.current || flowKnoten.length === 0) return;
    eingepasst.current = true;
    const frame = requestAnimationFrame(() => fitView({ padding: 0.2, maxZoom: 1 }));
    return () => cancelAnimationFrame(frame);
  }, [flowKnoten.length, fitView]);

  const kontextWert = useMemo(
    () => ({
      ausgewaehltId: props.ausgewaehltId,
      dropZielId,
      onWaehlen: props.onWaehlen,
      onMenue: props.onMenue,
      onUmschalten: props.onUmschalten,
    }),
    [props.ausgewaehltId, dropZielId, props.onWaehlen, props.onMenue, props.onUmschalten],
  );

  return (
    <DiagrammKontext.Provider value={kontextWert}>
      <div className="h-full w-full" style={FLOW_STIL}>
        <ReactFlow<PositionKnotenTyp>
          nodes={nodes}
          edges={flowKanten}
          onNodesChange={onNodesChange}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          minZoom={0.15}
          maxZoom={1.6}
          nodesConnectable={false}
          elementsSelectable={false}
          onNodeContextMenu={(event, node) => {
            event.preventDefault();
            if (!node.data.position.kontext) props.onMenue(node.data.position, { x: event.clientX, y: event.clientY });
          }}
          onNodeDrag={(event, node) => {
            const z = zeiger(event as MouseEvent | TouchEvent);
            const ziel = knotenAusPunkt(z.x, z.y, node.id);
            setDropZielId((alt) => (alt === ziel ? alt : ziel));
          }}
          onNodeDragStop={(event, node) => {
            const z = zeiger(event as MouseEvent | TouchEvent);
            const zielId = knotenAusPunkt(z.x, z.y, node.id);
            setDropZielId(null);
            // Position springt in jedem Fall zurueck; bei Erfolg liefert die neu geladene Liste das neue Layout.
            setNodes(flowKnoten);
            if (!zielId) return;
            const quelle = knoten.find((p) => p.id === node.id);
            const ziel = knoten.find((p) => p.id === zielId);
            if (!quelle || !ziel || ziel.kontext) {
              if (ziel?.kontext) props.onUngueltigerDrop("Auf einen ausgegrauten Pfadknoten kann nichts verschoben werden.");
              return;
            }
            if (quelle.parent_id === ziel.id) return;
            if (nachfahrenVon(layoutKnoten, quelle.id).has(ziel.id)) {
              props.onUngueltigerDrop("Eine Position kann nicht unter ihre eigenen Unterpositionen gehängt werden.");
              return;
            }
            props.onUmhaengen(quelle.id, ziel.id);
          }}
          aria-label="Organigramm"
        >
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable ariaLabel="Übersicht des Organigramms" nodeStrokeWidth={2} />
        </ReactFlow>
      </div>
    </DiagrammKontext.Provider>
  );
}

export function OrganigrammDiagramm(props: OrganigrammDiagrammProps) {
  return (
    <ReactFlowProvider>
      <Flaeche {...props} />
    </ReactFlowProvider>
  );
}
