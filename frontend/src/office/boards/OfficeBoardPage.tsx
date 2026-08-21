import {
  addEdge,
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type OnConnect,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Compass,
  Copy,
  Frame,
  Image as ImageIcon,
  Link2,
  ListChecks,
  MapPin,
  MousePointer2,
  Paperclip,
  Save,
  Share2,
  Shapes,
  Smile,
  Square,
  Trash2,
  Type as TypeIcon,
  Upload,
  Workflow,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { boardsApi } from "../../api/endpoints";
import { ExportPanel } from "./ExportPanel";
import { BOARD_NODE_TYPES } from "./nodes";
import type {
  BoardEdge,
  BoardInhalt,
  BoardNode,
  BoardNodeTyp,
  KlebezettelFarbe,
} from "./types";
import { leeresInhalt } from "./types";

const KLEBEZETTEL_FARBEN: KlebezettelFarbe[] = ["gelb", "blau", "gruen", "rosa"];

function zufaelligeFarbe(): KlebezettelFarbe {
  return KLEBEZETTEL_FARBEN[Math.floor(Math.random() * KLEBEZETTEL_FARBEN.length)];
}

function neueNode(typ: BoardNodeTyp, position: { x: number; y: number }): BoardNode {
  const id = `${typ}-${Date.now()}-${Math.round(Math.random() * 1000)}`;
  const basis = { id, position, type: typ };
  switch (typ) {
    case "klebezettel":
      return { ...basis, data: { text: "", farbe: zufaelligeFarbe() } };
    case "form":
      return { ...basis, data: { label: "", form: "rechteck" } };
    case "text":
      return { ...basis, data: { text: "" } };
    case "rahmen":
      return { ...basis, data: { label: "" }, style: { width: 320, height: 220 }, zIndex: -1 };
    case "bild":
      return { ...basis, data: { url: "" } };
    case "vorgang_karte":
      return { ...basis, data: { vorgang_id: "" } };
    case "anlagen_pin":
      return { ...basis, data: { nummer: 1, anlage_id: null } };
    case "prozess_schritt":
      return { ...basis, data: { label: "" } };
    case "prozess_entscheidung":
      return { ...basis, data: { label: "" } };
    case "grundriss":
      return { ...basis, data: { url: "" }, draggable: false, selectable: false, zIndex: -2 };
    case "checkliste":
      return { ...basis, data: { titel: "", punkte: [] } };
    case "datei_anhang":
      return { ...basis, data: { dateiname: "", object_key: null } };
    case "sticker":
      return { ...basis, data: { icon: "" } };
  }
}

// Tiefe Kopie statt Referenz -- sonst teilen sich Original und Duplikat
// dasselbe data-Objekt und ein updateNodeData() am einen Node veraendert
// unbemerkt auch den anderen.
function kloneNode(node: BoardNode): BoardNode {
  const id = `${node.type}-${Date.now()}-${Math.round(Math.random() * 1000)}`;
  return {
    ...node,
    id,
    position: { x: node.position.x + 32, y: node.position.y + 32 },
    selected: false,
    data: JSON.parse(JSON.stringify(node.data)),
  };
}

const HINZUFUEGEN_WERKZEUGE: { typ: BoardNodeTyp; label: string; icon: typeof MousePointer2 }[] = [
  { typ: "klebezettel", label: "Klebezettel", icon: Square },
  { typ: "form", label: "Form", icon: Shapes },
  { typ: "text", label: "Text", icon: TypeIcon },
  { typ: "rahmen", label: "Rahmen", icon: Frame },
  { typ: "bild", label: "Bild", icon: ImageIcon },
  { typ: "vorgang_karte", label: "Vorgang verknüpfen", icon: Link2 },
  { typ: "checkliste", label: "Checkliste", icon: ListChecks },
  { typ: "datei_anhang", label: "Datei anhängen", icon: Paperclip },
  { typ: "sticker", label: "Sticker", icon: Smile },
];

function OfficeBoardCanvas({ boardId }: { boardId: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const grundrissInputRef = useRef<HTMLInputElement>(null);
  const { screenToFlowPosition } = useReactFlow();

  const { data: board } = useQuery({ queryKey: ["board", boardId], queryFn: () => boardsApi.get(boardId) });
  const { data: hintergrund } = useQuery({
    queryKey: ["board-hintergrund", boardId],
    queryFn: () => boardsApi.hintergrundUrl(boardId),
    enabled: board?.board_typ === "bauplanung",
  });

  const [nodes, setNodes, onNodesChange] = useNodesState<BoardNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<BoardEdge>([]);
  const [geladen, setGeladen] = useState(false);
  const [zeigeExport, setZeigeExport] = useState(false);
  const [kontextMenu, setKontextMenu] = useState<{ x: number; y: number; node: BoardNode } | null>(null);
  const zwischenablage = useRef<BoardNode[]>([]);

  // Board-Inhalt einmalig beim Laden in den React-Flow-Zustand uebernehmen.
  useEffect(() => {
    if (!board || geladen) return;
    const inhalt = (board.inhalt_json as Partial<BoardInhalt>) ?? leeresInhalt();
    setNodes(inhalt.nodes ?? []);
    setEdges(inhalt.edges ?? []);
    setGeladen(true);
  }, [board, geladen, setNodes, setEdges]);

  // Grundriss-Node synchron zum hochgeladenen Bild halten (eigener,
  // gesperrter Node statt Canvas-Hintergrund-CSS, damit er wie jedes andere
  // Element Teil von inhalt_json bleibt und beim Export mit erfasst wird).
  useEffect(() => {
    if (board?.board_typ !== "bauplanung") return;
    setNodes((aktuelle) => {
      const ohneGrundriss = aktuelle.filter((n) => n.type !== "grundriss");
      if (!hintergrund?.url) return ohneGrundriss;
      const bestehender = aktuelle.find((n) => n.type === "grundriss");
      const grundrissNode: BoardNode = {
        id: "grundriss",
        type: "grundriss",
        position: bestehender?.position ?? { x: 0, y: 0 },
        data: { url: hintergrund.url },
        draggable: false,
        selectable: false,
        zIndex: -2,
      };
      return [grundrissNode, ...ohneGrundriss];
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hintergrund?.url, board?.board_typ]);

  // Autosave: 1,2s nach der letzten Aenderung speichern, nicht bei jedem
  // einzelnen Tastenanschlag -- sonst ein PATCH pro Zeichen beim Tippen in
  // einer Notiz.
  const speichern = useMutation({
    mutationFn: (inhalt: BoardInhalt) => boardsApi.update(boardId, { inhalt_json: inhalt }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["boards"] }),
  });
  const speicherTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!geladen) return;
    if (speicherTimer.current) clearTimeout(speicherTimer.current);
    speicherTimer.current = setTimeout(() => {
      speichern.mutate({ nodes, edges });
    }, 1200);
    return () => {
      if (speicherTimer.current) clearTimeout(speicherTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, geladen]);

  const loeschen = useMutation({
    mutationFn: () => boardsApi.remove(boardId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["boards"] });
      navigate("/boards");
    },
  });

  const onConnect = useCallback<OnConnect>(
    (verbindung: Connection) => setEdges((es) => addEdge({ ...verbindung, type: "smoothstep" }, es)),
    [setEdges],
  );

  const werkzeugPlatzieren = useCallback(
    (typ: BoardNodeTyp) => {
      const rect = wrapperRef.current?.getBoundingClientRect();
      const mitte = rect
        ? screenToFlowPosition({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 })
        : { x: 200, y: 200 };
      const versatz = { x: mitte.x + (Math.random() - 0.5) * 60, y: mitte.y + (Math.random() - 0.5) * 60 };
      if (typ === "anlagen_pin") {
        const naechsteNummer = nodes.filter((n) => n.type === "anlagen_pin").length + 1;
        setNodes((ns) => [...ns, { ...neueNode(typ, versatz), data: { nummer: naechsteNummer, anlage_id: null } }]);
        return;
      }
      setNodes((ns) => [...ns, neueNode(typ, versatz)]);
    },
    [nodes, screenToFlowPosition, setNodes],
  );

  // Duplizieren per Strg/Cmd+D sowie Kopieren/Einfuegen per Strg/Cmd+C/V --
  // in eine interne Ref statt die System-Zwischenablage, damit kein
  // Berechtigungsdialog noetig ist und es unabhaengig vom Browser
  // funktioniert. Eingaben in Text-/Input-Feldern (z.B. beim Tippen einer
  // Notiz) werden bewusst ignoriert, sonst wuerde normales Text-Kopieren im
  // Feld ein Board-Element duplizieren.
  useEffect(() => {
    function tastenAktion(e: KeyboardEvent) {
      const ziel = e.target as HTMLElement;
      const tippt = ziel.tagName === "INPUT" || ziel.tagName === "TEXTAREA" || ziel.isContentEditable;
      if (tippt || (!e.ctrlKey && !e.metaKey)) return;

      const taste = e.key.toLowerCase();
      if (taste === "d") {
        const ausgewaehlt = nodes.filter((n) => n.selected && n.type !== "grundriss");
        if (ausgewaehlt.length === 0) return;
        e.preventDefault();
        const kopien = ausgewaehlt.map(kloneNode);
        setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), ...kopien]);
      } else if (taste === "c") {
        const ausgewaehlt = nodes.filter((n) => n.selected && n.type !== "grundriss");
        if (ausgewaehlt.length > 0) zwischenablage.current = ausgewaehlt;
      } else if (taste === "v") {
        if (zwischenablage.current.length === 0) return;
        e.preventDefault();
        const kopien = zwischenablage.current.map(kloneNode);
        zwischenablage.current = kopien; // wiederholtes Einfuegen versetzt jedes Mal weiter
        setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), ...kopien]);
      }
    }
    window.addEventListener("keydown", tastenAktion);
    return () => window.removeEventListener("keydown", tastenAktion);
  }, [nodes, setNodes]);

  const grundrissHochladen = async (file: File) => {
    await boardsApi.hintergrundUpload(boardId, file);
    queryClient.invalidateQueries({ queryKey: ["board-hintergrund", boardId] });
  };

  const nodeErsetzen = useCallback(
    (nodeId: string, vorgangId: string) => {
      setNodes((ns) =>
        ns.map((n) => (n.id === nodeId ? { ...n, type: "vorgang_karte", data: { vorgang_id: vorgangId } } : n)),
      );
    },
    [setNodes],
  );

  const exportPng = async () => {
    const { toPng } = await import("html-to-image");
    const viewport = wrapperRef.current?.querySelector<HTMLElement>(".react-flow__viewport");
    if (!viewport) return;
    const dataUrl = await toPng(viewport, { backgroundColor: "#f8fafc" });
    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = `${board?.name ?? "board"}.png`;
    a.click();
  };

  const exportPdf = async () => {
    const { toPng } = await import("html-to-image");
    const { default: jsPDF } = await import("jspdf");
    const viewport = wrapperRef.current?.querySelector<HTMLElement>(".react-flow__viewport");
    if (!viewport) return;
    const dataUrl = await toPng(viewport, { backgroundColor: "#f8fafc" });
    const bild = new Image();
    bild.src = dataUrl;
    await new Promise((resolve) => (bild.onload = resolve));
    const orientation = bild.width >= bild.height ? "l" : "p";
    const pdf = new jsPDF({ orientation, unit: "px", format: [bild.width, bild.height] });
    pdf.addImage(dataUrl, "PNG", 0, 0, bild.width, bild.height);
    pdf.save(`${board?.name ?? "board"}.pdf`);
  };

  const exportCsv = () => {
    const zeilen = nodes
      .filter((n) => n.type === "klebezettel" || n.type === "text")
      .map((n) => {
        const text = String((n.data as { text?: string }).text ?? "").replace(/"/g, '""');
        return `"${n.type}","${text}"`;
      });
    const csv = ["typ,text", ...zeilen].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${board?.name ?? "board"}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (!board) {
    return <p className="p-8 text-center text-sm text-slate-400 dark:text-stone-500">Lädt…</p>;
  }

  return (
    <div className="flex h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-xl border border-slate-200 dark:border-stone-800">
      <div className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-5 dark:border-stone-800 dark:bg-stone-900">
        <button
          onClick={() => navigate("/boards")}
          className="text-xs font-semibold text-slate-500 hover:text-slate-700 dark:text-stone-400 dark:hover:text-stone-200"
        >
          ← Boards
        </button>
        <div className="h-5 w-px bg-slate-200 dark:bg-stone-700" />
        <p className="text-sm font-bold text-slate-800 dark:text-stone-100">{board.name}</p>
        <span className="text-xs text-slate-400 dark:text-stone-500">
          {speichern.isPending ? "Speichert…" : "Gespeichert"}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {board.board_typ === "bauplanung" && (
            <>
              <input
                ref={grundrissInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) grundrissHochladen(file);
                  e.target.value = "";
                }}
              />
              <button
                onClick={() => grundrissInputRef.current?.click()}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:border-stone-700 dark:text-stone-300"
              >
                <Upload size={13} strokeWidth={2} /> Grundriss
              </button>
            </>
          )}
          <button
            onClick={() => setZeigeExport(true)}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:border-stone-700 dark:text-stone-300"
          >
            <Share2 size={13} strokeWidth={2} /> Exportieren
          </button>
          <button
            onClick={() => speichern.mutate({ nodes, edges })}
            className="btn-clay flex items-center gap-1.5 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-xs font-semibold text-white"
          >
            <Save size={13} strokeWidth={2} /> Speichern
          </button>
          <button
            onClick={() => {
              if (window.confirm(`Board "${board.name}" wirklich löschen?`)) loeschen.mutate();
            }}
            disabled={loeschen.isPending}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-red-600 disabled:opacity-50 dark:border-stone-700 dark:text-red-400"
          >
            <Trash2 size={13} strokeWidth={2} /> Löschen
          </button>
        </div>
      </div>

      <div ref={wrapperRef} className="relative flex-1">
        <ReactFlow<BoardNode, BoardEdge>
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={BOARD_NODE_TYPES}
          minZoom={0.2}
          maxZoom={2}
          onNodeContextMenu={(event, node) => {
            if (node.type === "grundriss") return;
            event.preventDefault();
            setKontextMenu({ x: event.clientX, y: event.clientY, node });
          }}
          onPaneClick={() => setKontextMenu(null)}
          onNodeClick={() => setKontextMenu(null)}
          onMoveStart={() => setKontextMenu(null)}
        >
          <Background gap={26} color="#cbd5e1" />
          <Controls showInteractive={false} />
        </ReactFlow>

        {kontextMenu && (
          <div
            className="fixed z-30 w-44 rounded-lg border border-slate-100 bg-white py-1 text-sm shadow-xl dark:border-stone-800 dark:bg-stone-900"
            style={{ left: kontextMenu.x, top: kontextMenu.y }}
            onMouseLeave={() => setKontextMenu(null)}
          >
            <button
              onClick={() => {
                const kopie = kloneNode(kontextMenu.node);
                setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), kopie]);
                setKontextMenu(null);
              }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-slate-600 hover:bg-slate-50 dark:text-stone-300 dark:hover:bg-stone-800"
            >
              <Copy size={13} strokeWidth={2} /> Duplizieren
            </button>
          </div>
        )}

        <div className="pointer-events-none absolute inset-y-0 left-5 z-10 flex items-center">
          <div className="pointer-events-auto flex flex-col gap-1 rounded-2xl border border-slate-100 bg-white p-2 shadow-xl dark:border-stone-800 dark:bg-stone-900">
            {HINZUFUEGEN_WERKZEUGE.map((w) => (
              <button
                key={w.typ}
                title={w.label}
                onClick={() => werkzeugPlatzieren(w.typ)}
                className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
              >
                <w.icon size={17} strokeWidth={2} />
              </button>
            ))}
            {board.board_typ === "bauplanung" && (
              <button
                title="Anlagen-Pin"
                onClick={() => werkzeugPlatzieren("anlagen_pin")}
                className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
              >
                <MapPin size={17} strokeWidth={2} />
              </button>
            )}
            {board.board_typ === "prozess" && (
              <>
                <button
                  title="Prozessschritt"
                  onClick={() => werkzeugPlatzieren("prozess_schritt")}
                  className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
                >
                  <Workflow size={17} strokeWidth={2} />
                </button>
                <button
                  title="Entscheidung"
                  onClick={() => werkzeugPlatzieren("prozess_entscheidung")}
                  className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
                >
                  <Compass size={17} strokeWidth={2} />
                </button>
              </>
            )}
            <div className="my-1 h-px bg-slate-100 dark:bg-stone-800" />
            <span title="Verbinden: von einem Punkt am Rand einer Karte zur naechsten ziehen" className="flex h-9 w-9 items-center justify-center text-slate-300 dark:text-stone-600">
              <ArrowUpRight size={17} strokeWidth={2} />
            </span>
            <span
              title="Duplizieren: Strg/Cmd+D oder Rechtsklick auf eine Karte · Kopieren/Einfügen: Strg/Cmd+C dann Strg/Cmd+V"
              className="flex h-9 w-9 items-center justify-center text-slate-300 dark:text-stone-600"
            >
              <Copy size={15} strokeWidth={2} />
            </span>
          </div>
        </div>
      </div>

      {zeigeExport && (
        <ExportPanel
          board={board}
          nodes={nodes}
          onClose={() => setZeigeExport(false)}
          onNodeErsetzen={nodeErsetzen}
          onExportPng={exportPng}
          onExportPdf={exportPdf}
          onExportCsv={exportCsv}
        />
      )}
    </div>
  );
}

export function OfficeBoardPage() {
  const { id } = useParams<{ id: string }>();
  if (!id) return null;
  return (
    <ReactFlowProvider>
      <OfficeBoardCanvas boardId={id} />
    </ReactFlowProvider>
  );
}
