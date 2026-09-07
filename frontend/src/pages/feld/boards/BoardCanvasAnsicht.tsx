import { Background, Controls, ReactFlow, ReactFlowProvider, type NodeTypes, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useQuery } from "@tanstack/react-query";
import { Link2, Paperclip } from "lucide-react";

import { kundenApi, vorgaengeApi } from "../../../api/endpoints";
import { STATUS_BADGE, STATUS_LABEL } from "../../../config/vorgangDarstellung";
import { STICKER_ICONS } from "../../../office/boards/nodes/StickerNode";
import type {
  AnlagenPinDaten,
  BildDaten,
  BoardEdge,
  BoardNode,
  ChecklisteDaten,
  DateiAnhangDaten,
  FormDaten,
  KlebezettelDaten,
  KlebezettelFarbe,
  ProzessEntscheidungDaten,
  ProzessSchrittDaten,
  RahmenDaten,
  StickerDaten,
  TextDaten,
  VorgangKarteDaten,
} from "../../../office/boards/types";

/** Rein lesende Darstellung derselben Node-Typen wie in der Office-
 * Werkzeugleiste (office/boards/nodes/*.tsx) -- am Handy wird nicht per
 * Textfeld direkt im Canvas editiert (siehe BoardMobilePage.tsx), ein Tap
 * oeffnet stattdessen das Notiz-Sheet. Deshalb hier bewusst keine Handles/
 * Inputs, nur Anzeige + Klick-Weiterleitung an onNodeClick der ReactFlow-
 * Instanz. */
const FARB_KLASSEN: Record<KlebezettelFarbe, string> = {
  gelb: "bg-amber-100 text-amber-900",
  blau: "bg-blue-100 text-blue-900",
  gruen: "bg-emerald-100 text-emerald-900",
  rosa: "bg-rose-100 text-rose-900",
};

function VorgangKarteAnsicht({ data }: { data: VorgangKarteDaten }) {
  const { vorgang_id } = data;
  const { data: vorgang } = useQuery({
    queryKey: ["vorgang", vorgang_id],
    queryFn: () => vorgaengeApi.get(vorgang_id),
    enabled: !!vorgang_id,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", vorgang?.kunde_id],
    queryFn: () => kundenApi.get(vorgang!.kunde_id),
    enabled: !!vorgang?.kunde_id,
  });

  if (!vorgang_id) return null;
  return (
    <div className="relative w-[190px] overflow-hidden rounded-xl bg-white shadow-lg dark:bg-stone-900">
      <span className="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full border-2 border-white bg-indigo-100 text-indigo-600 dark:border-stone-900 dark:bg-indigo-500/20 dark:text-indigo-300">
        <Link2 size={11} strokeWidth={2.5} />
      </span>
      <div className="h-1 bg-linear-to-r from-cyan-500 to-blue-600" />
      <div className="p-3">
        {vorgang ? (
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[10px] font-bold text-ind-ink-3">{vorgang.vorgangsnummer}</p>
              <p className="mt-0.5 truncate text-[13px] font-bold text-ind-ink">{vorgang.titel}</p>
              {kunde && <p className="mt-0.5 truncate text-[11px] text-ind-ink-3">{kunde.name}</p>}
            </div>
            <span
              className={`shrink-0 px-2 py-0.5 text-[10px] font-bold whitespace-nowrap ${STATUS_BADGE[vorgang.status]}`}
            >
              {STATUS_LABEL[vorgang.status]}
            </span>
          </div>
        ) : (
          <p className="text-xs text-ind-ink-3">Lädt…</p>
        )}
      </div>
    </div>
  );
}

function MobileNodeAnsicht(props: NodeProps<BoardNode>) {
  const { type, data } = props;
  switch (type) {
    case "klebezettel": {
      const { text, farbe } = data as KlebezettelDaten;
      return (
        <div className={`w-[150px] rounded-lg p-2.5 text-xs font-medium shadow-md ${FARB_KLASSEN[farbe] ?? FARB_KLASSEN.gelb}`}>
          {text || <span className="opacity-50">Leere Notiz</span>}
        </div>
      );
    }
    case "text": {
      const { text } = data as TextDaten;
      return (
        <div className="w-[170px] text-sm font-semibold text-ind-ink">
          {text || <span className="text-ind-ink-3">Leerer Text</span>}
        </div>
      );
    }
    case "form": {
      const { label, form } = data as FormDaten;
      return (
        <div
          className={`flex h-[70px] w-[140px] items-center justify-center bg-violet-100 p-2 text-center text-xs font-semibold text-violet-800 shadow-md ${
            form === "kreis" ? "rounded-full" : "rounded-xl"
          }`}
        >
          {label}
        </div>
      );
    }
    case "rahmen": {
      const { label } = data as RahmenDaten;
      return (
        <div className="h-full w-full rounded-xl border-2 border-dashed border-slate-300 bg-slate-50/40 dark:border-stone-700 dark:bg-stone-800/20">
          <p className="m-2 text-xs font-bold tracking-wide text-slate-500 uppercase dark:text-stone-400">{label}</p>
        </div>
      );
    }
    case "bild": {
      const { url } = data as BildDaten;
      return (
        <div className="w-[180px] overflow-hidden rounded-lg shadow-md">
          {url ? (
            <img src={url} alt="" className="block w-full" draggable={false} />
          ) : (
            <div className="flex h-24 items-center justify-center bg-slate-100 text-xs text-slate-400 dark:bg-stone-800 dark:text-stone-500">
              Kein Bild
            </div>
          )}
        </div>
      );
    }
    case "vorgang_karte":
      return <VorgangKarteAnsicht data={data as VorgangKarteDaten} />;
    case "anlagen_pin": {
      const { nummer } = data as AnlagenPinDaten;
      return (
        <div className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-linear-to-r from-cyan-500 to-blue-600 text-xs font-extrabold text-white shadow-lg dark:border-stone-900">
          {nummer}
        </div>
      );
    }
    case "prozess_schritt": {
      const { label, sub } = data as ProzessSchrittDaten;
      return (
        <div className="w-[150px] rounded-xl border-[1.5px] border-slate-200 bg-white p-2.5 shadow-sm dark:border-stone-700 dark:bg-stone-900">
          <p className="text-[12px] font-bold text-ind-ink">{label}</p>
          {sub && <p className="mt-0.5 text-[10px] text-ind-ink-3">{sub}</p>}
        </div>
      );
    }
    case "prozess_entscheidung": {
      const { label } = data as ProzessEntscheidungDaten;
      return (
        <div className="relative flex h-[110px] w-[110px] items-center justify-center">
          <div className="absolute inset-0 rotate-45 rounded-2xl border-[1.5px] border-amber-300 bg-amber-50 dark:border-amber-500/40 dark:bg-amber-500/10" />
          <span className="relative z-10 w-20 text-center text-[11px] font-bold text-amber-800 dark:text-amber-200">
            {label}
          </span>
        </div>
      );
    }
    case "grundriss": {
      const { url } = data as { url: string };
      if (!url) return null;
      return <img src={url} alt="Grundriss" className="block max-w-none select-none" draggable={false} />;
    }
    case "checkliste": {
      const { titel, punkte } = data as ChecklisteDaten;
      const erledigt = punkte.filter((p) => p.erledigt).length;
      return (
        <div className="w-[170px] rounded-xl bg-white p-2.5 shadow-md dark:bg-stone-900">
          <p className="truncate text-[11px] font-bold text-ind-ink">{titel || "Checkliste"}</p>
          <p className="mt-0.5 text-[10px] text-ind-ink-3">
            {erledigt}/{punkte.length} erledigt
          </p>
        </div>
      );
    }
    case "datei_anhang": {
      const { dateiname } = data as DateiAnhangDaten;
      return (
        <div className="flex w-[150px] items-center gap-1.5 rounded-xl bg-white p-2.5 shadow-md dark:bg-stone-900">
          <Paperclip size={13} strokeWidth={2} className="shrink-0 text-cyan-600 dark:text-cyan-400" />
          <span className="truncate text-[11px] font-medium text-ind-ink-2">
            {dateiname || "Kein Anhang"}
          </span>
        </div>
      );
    }
    case "sticker": {
      const { icon } = data as StickerDaten;
      const Icon = STICKER_ICONS[icon];
      return (
        <div className="flex h-9 w-9 items-center justify-center rounded-2xl border-2 border-white bg-linear-to-br from-cyan-500 to-blue-600 text-white shadow-lg dark:border-stone-900">
          {Icon && <Icon size={16} strokeWidth={2} />}
        </div>
      );
    }
    default:
      return null;
  }
}

const MOBILE_NODE_TYPES: NodeTypes = {
  klebezettel: MobileNodeAnsicht,
  form: MobileNodeAnsicht,
  text: MobileNodeAnsicht,
  rahmen: MobileNodeAnsicht,
  bild: MobileNodeAnsicht,
  vorgang_karte: MobileNodeAnsicht,
  anlagen_pin: MobileNodeAnsicht,
  prozess_schritt: MobileNodeAnsicht,
  prozess_entscheidung: MobileNodeAnsicht,
  grundriss: MobileNodeAnsicht,
  checkliste: MobileNodeAnsicht,
  datei_anhang: MobileNodeAnsicht,
  sticker: MobileNodeAnsicht,
};

/** Nur Ansehen -- kein Dragging/Verbinden per Touch, das braeuchte eine
 * Maus-Werkzeugleiste wie am Desktop. Tippen auf eine Notiz/Vorgang-Karte
 * meldet sich ueber onNodeTap, statt selbst zu navigieren -- BoardMobilePage
 * entscheidet, ob das Notiz-Sheet oder direkt der Vorgang aufgeht. */
export function BoardCanvasAnsicht({
  nodes,
  edges,
  onNodeTap,
}: {
  nodes: BoardNode[];
  edges: BoardEdge[];
  onNodeTap: (node: BoardNode) => void;
}) {
  return (
    <ReactFlowProvider>
      <ReactFlow<BoardNode, BoardEdge>
        nodes={nodes}
        edges={edges}
        nodeTypes={MOBILE_NODE_TYPES}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnScroll={false}
        zoomOnScroll={false}
        zoomOnPinch
        panOnDrag
        minZoom={0.3}
        maxZoom={2}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        onNodeClick={(_event, node) => onNodeTap(node)}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={22} color="#cbd5e1" />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
    </ReactFlowProvider>
  );
}
