import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Link2, Plus, StickyNote, Trash2 } from "lucide-react";
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { boardsApi, vorgaengeApi } from "../../../api/endpoints";
import { STATUS_BADGE, STATUS_LABEL } from "../../../config/vorgangDarstellung";
import type {
  BoardEdge,
  BoardInhalt,
  BoardNode,
  KlebezettelDaten,
  KlebezettelFarbe,
  VorgangKarteDaten,
} from "../../../office/boards/types";
import { leeresInhalt } from "../../../office/boards/types";
import { NeueNotizSheet, NotizAktionSheet } from "./NotizSheet";

// @xyflow/react ist eine schwere Desktop-Bibliothek -- wird nur geladen,
// wenn tatsaechlich zur Canvas-Ansicht gewechselt wird (Liste ist der
// Standard). Gleiches Muster wie MapboxFeedMap in FeedPage.tsx.
const BoardCanvasAnsicht = lazy(() =>
  import("./BoardCanvasAnsicht").then((m) => ({ default: m.BoardCanvasAnsicht })),
);

const FARB_KLASSEN: Record<KlebezettelFarbe, string> = {
  gelb: "bg-amber-100 text-amber-900",
  blau: "bg-blue-100 text-blue-900",
  gruen: "bg-emerald-100 text-emerald-900",
  rosa: "bg-rose-100 text-rose-900",
};
const FARB_PUNKT: Record<KlebezettelFarbe, string> = {
  gelb: "bg-amber-400",
  blau: "bg-blue-400",
  gruen: "bg-emerald-400",
  rosa: "bg-rose-400",
};

function VorgangZeile({ vorgangId, onOeffnen }: { vorgangId: string; onOeffnen: () => void }) {
  const { data: vorgang } = useQuery({
    queryKey: ["vorgang", vorgangId],
    queryFn: () => vorgaengeApi.get(vorgangId),
    enabled: !!vorgangId,
  });
  return (
    <button
      onClick={onOeffnen}
      className="btn-touch flex w-full items-center gap-3 border border-ind-line bg-ind-bg p-3 text-left"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300">
        <Link2 size={15} strokeWidth={2} />
      </span>
      <span className="min-w-0 flex-1">
        {vorgang ? (
          <>
            <span className="block truncate text-sm font-bold text-ind-ink">{vorgang.titel}</span>
            <span className="block text-xs text-ind-ink-3">{vorgang.vorgangsnummer}</span>
          </>
        ) : (
          <span className="text-sm text-ind-ink-3">Lädt…</span>
        )}
      </span>
      {vorgang && (
        <span className={`shrink-0 px-2 py-0.5 text-[10px] font-bold whitespace-nowrap ${STATUS_BADGE[vorgang.status]}`}>
          {STATUS_LABEL[vorgang.status]}
        </span>
      )}
    </button>
  );
}

function notizDaten(node: BoardNode): KlebezettelDaten | null {
  if (node.type === "klebezettel") return node.data as KlebezettelDaten;
  if (node.type === "text") return { text: (node.data as { text: string }).text, farbe: "gelb" };
  return null;
}

/** Mobiles Gegenstueck zu office/boards/OfficeBoardPage.tsx. Volles
 * Maus-Editieren (Werkzeugleiste, Ziehen, Verbinden) ist am Handy kein
 * sinnvolles Interaktionsmodell -- hier gibt es stattdessen: Ansehen
 * (Canvas mit Pinch-Zoom/Pan, oder eine einfache Liste), gezieltes
 * Hinzufuegen einer Notiz per Sheet, und dieselbe Notiz-zu-Vorgang/Mangel-
 * Uebernahme wie am Desktop. Andere Node-Typen (Formen, Bauplanung-Pins,
 * Prozessschritte) lassen sich nur ansehen, nicht anlegen -- dafuer bleibt
 * es bei der Desktop-Ansicht. */
export function BoardMobilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: board } = useQuery({
    queryKey: ["board", id],
    queryFn: () => boardsApi.get(id!),
    enabled: !!id,
  });

  const [nodes, setNodes] = useState<BoardNode[]>([]);
  const [edges, setEdges] = useState<BoardEdge[]>([]);
  const [geladen, setGeladen] = useState(false);
  const [ansicht, setAnsicht] = useState<"liste" | "canvas">("liste");
  const [zeigeNeueNotiz, setZeigeNeueNotiz] = useState(false);
  const [offeneNotizId, setOffeneNotizId] = useState<string | null>(null);

  useEffect(() => {
    if (!board || geladen) return;
    const inhalt = (board.inhalt_json as Partial<BoardInhalt>) ?? leeresInhalt();
    setNodes(inhalt.nodes ?? []);
    setEdges(inhalt.edges ?? []);
    setGeladen(true);
  }, [board, geladen]);

  const speichern = useMutation({
    mutationFn: (inhalt: BoardInhalt) => boardsApi.update(id!, { inhalt_json: inhalt }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["boards"] }),
  });
  const speicherTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!geladen) return;
    if (speicherTimer.current) clearTimeout(speicherTimer.current);
    speicherTimer.current = setTimeout(() => speichern.mutate({ nodes, edges }), 1200);
    return () => {
      if (speicherTimer.current) clearTimeout(speicherTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, geladen]);

  const boardLoeschen = useMutation({
    mutationFn: () => boardsApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["boards"] });
      navigate("/boards");
    },
  });

  const notizErstellen = (daten: KlebezettelDaten) => {
    const versatz = nodes.length * 24;
    const neueId = `klebezettel-${Date.now()}`;
    setNodes((ns) => [
      ...ns,
      { id: neueId, type: "klebezettel", position: { x: 40 + (versatz % 200), y: 40 + versatz }, data: daten },
    ]);
    setZeigeNeueNotiz(false);
  };

  const notizAktualisieren = (nodeId: string, daten: KlebezettelDaten) => {
    setNodes((ns) => ns.map((n) => (n.id === nodeId ? { ...n, type: "klebezettel", data: daten } : n)));
    setOffeneNotizId(null);
  };

  const notizDuplizieren = (nodeId: string) => {
    const original = nodes.find((n) => n.id === nodeId);
    if (!original) return;
    const kopie: BoardNode = {
      ...original,
      id: `${original.type}-${Date.now()}`,
      position: { x: original.position.x + 24, y: original.position.y + 24 },
      data: JSON.parse(JSON.stringify(original.data)),
    };
    setNodes((ns) => [...ns, kopie]);
    setOffeneNotizId(null);
  };

  const notizLoeschen = (nodeId: string) => {
    setNodes((ns) => ns.filter((n) => n.id !== nodeId));
    setEdges((es) => es.filter((e) => e.source !== nodeId && e.target !== nodeId));
    setOffeneNotizId(null);
  };

  const notizUebernommen = (nodeId: string, vorgangId: string) => {
    setNodes((ns) => ns.map((n) => (n.id === nodeId ? { ...n, type: "vorgang_karte", data: { vorgang_id: vorgangId } } : n)));
    setOffeneNotizId(null);
  };

  const nodeTippen = (node: BoardNode) => {
    if (node.type === "klebezettel" || node.type === "text") {
      setOffeneNotizId(node.id);
    } else if (node.type === "vorgang_karte") {
      const { vorgang_id } = node.data as VorgangKarteDaten;
      if (vorgang_id) navigate(`/vorgaenge/${vorgang_id}`);
    }
  };

  const notizen = nodes.filter((n) => notizDaten(n) !== null || n.type === "vorgang_karte");
  const offenerNode = offeneNotizId ? nodes.find((n) => n.id === offeneNotizId) : null;

  if (!board) {
    return <p className="py-8 text-center text-sm text-ind-ink-3">Lädt…</p>;
  }

  return (
    <div className="space-y-3">
      <div>
        <div className="flex items-center justify-between">
          <button
            onClick={() => navigate("/boards")}
            className="btn-touch -ml-1 flex items-center gap-0.5 text-sm font-medium text-ind-ink-3"
          >
            <ChevronLeft size={16} strokeWidth={2.25} /> Boards
          </button>
          <button
            onClick={() => {
              if (window.confirm(`Board "${board.name}" wirklich löschen?`)) boardLoeschen.mutate();
            }}
            disabled={boardLoeschen.isPending}
            aria-label="Board löschen"
            className="btn-touch flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:text-red-600 disabled:opacity-50 dark:text-stone-500 dark:hover:text-red-400"
          >
            <Trash2 size={17} strokeWidth={2} />
          </button>
        </div>
        <div className="mt-0.5 flex items-baseline gap-2">
          <h1 className="truncate text-lg font-bold text-ind-ink">{board.name}</h1>
          <span className="shrink-0 text-xs text-ind-ink-3">
            {speichern.isPending ? "Speichert…" : "Gespeichert"}
          </span>
        </div>
      </div>

      <div className="inline-flex border border-ind-line">
        <button
          onClick={() => setAnsicht("liste")}
          className={`btn-touch px-4 py-1.5 text-xs font-semibold ${
            ansicht === "liste" ? "bg-ind-field text-ind-field-ink" : "text-ind-ink-3 hover:bg-ind-hover"
          }`}
        >
          Liste
        </button>
        <button
          onClick={() => setAnsicht("canvas")}
          className={`btn-touch border-l border-ind-line px-4 py-1.5 text-xs font-semibold ${
            ansicht === "canvas" ? "bg-ind-field text-ind-field-ink" : "text-ind-ink-3 hover:bg-ind-hover"
          }`}
        >
          Canvas
        </button>
      </div>

      {ansicht === "liste" ? (
        notizen.length === 0 ? (
          <p className="py-8 text-center text-sm text-ind-ink-3">
            Noch keine Notizen auf diesem Board.
          </p>
        ) : (
          <div className="space-y-2">
            {notizen.map((n) => {
              if (n.type === "vorgang_karte") {
                const { vorgang_id } = n.data as VorgangKarteDaten;
                if (!vorgang_id) return null;
                return <VorgangZeile key={n.id} vorgangId={vorgang_id} onOeffnen={() => nodeTippen(n)} />;
              }
              const daten = notizDaten(n)!;
              return (
                <button
                  key={n.id}
                  onClick={() => nodeTippen(n)}
                  className={`btn-touch flex w-full items-start gap-3 rounded-xl p-3 text-left shadow-xs ${FARB_KLASSEN[daten.farbe]}`}
                >
                  <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${FARB_PUNKT[daten.farbe]}`} />
                  <span className="min-w-0 flex-1 text-sm font-medium">
                    {daten.text || <span className="opacity-60">(leer)</span>}
                  </span>
                </button>
              );
            })}
          </div>
        )
      ) : (
        <div className="relative h-[calc(100dvh-280px)] min-h-[320px] overflow-hidden rounded-xl border border-ind-line">
          <Suspense
            fallback={<div className="flex h-full items-center justify-center text-sm text-ind-ink-3">Lädt…</div>}
          >
            <BoardCanvasAnsicht nodes={nodes} edges={edges} onNodeTap={nodeTippen} />
          </Suspense>
        </div>
      )}

      <button
        onClick={() => setZeigeNeueNotiz(true)}
        className="fixed right-4 bottom-24 z-30 flex items-center gap-2 border border-ind-line bg-ind-bg py-2 pr-4 pl-2.5 shadow-lg"
        style={{ marginBottom: "env(safe-area-inset-bottom)" }}
      >
        <span className="flex h-9 w-9 items-center justify-center bg-ind-btn-bg text-ind-btn-ink">
          <Plus size={18} strokeWidth={1.5} />
        </span>
        <span className="flex items-center gap-1.5 text-sm font-bold text-ind-ink">
          <StickyNote size={14} strokeWidth={2} /> Notiz
        </span>
      </button>

      {zeigeNeueNotiz && <NeueNotizSheet onAbbrechen={() => setZeigeNeueNotiz(false)} onErstellen={notizErstellen} />}

      {offenerNode && (
        <NotizAktionSheet
          daten={notizDaten(offenerNode)!}
          onAbbrechen={() => setOffeneNotizId(null)}
          onSpeichern={(daten) => notizAktualisieren(offenerNode.id, daten)}
          onLoeschen={() => notizLoeschen(offenerNode.id)}
          onVorgangErstellt={(vorgangId) => notizUebernommen(offenerNode.id, vorgangId)}
          onDuplizieren={() => notizDuplizieren(offenerNode.id)}
        />
      )}
    </div>
  );
}
