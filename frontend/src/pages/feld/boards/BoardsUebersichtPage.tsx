import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Compass, LayoutGrid, StickyNote, Workflow } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { boardsApi } from "../../../api/endpoints";
import { AktionsMenue } from "../../../components/AktionsMenue";
import { AnlegenPanel } from "../../../components/AnlegenPanel";
import { EmptyState } from "../../../components/EmptyState";
import type { BoardTyp } from "../../../types";
import { FehlerZustand } from "../../../components/FehlerZustand";
import { useBestaetigung } from "../../../components/ConfirmDialog";
import { Feld, FELD_KLASSE, NEU_BUTTON_KLASSE } from "../../../components/FormularFeld";
import { SkeletonList } from "../../../components/Skeleton";
import { SegmentedControl } from "../../../components/apple/SegmentedControl";
import { SymbolKachel, type KachelFarbe } from "../../../components/apple/SymbolKachel";
import { Select } from "../../../components/apple/Select";

const TYP_ICON: Record<BoardTyp, typeof LayoutGrid> = {
  frei: LayoutGrid,
  bauplanung: Compass,
  prozess: Workflow,
};

const TYP_LABEL: Record<BoardTyp, string> = {
  frei: "Frei",
  bauplanung: "Bauplanung",
  prozess: "Prozess",
};

const TYP_FARBE: Record<BoardTyp, KachelFarbe> = {
  frei: "indigo",
  bauplanung: "orange",
  prozess: "green",
};

const FILTER_OPTIONEN: { wert: "alle" | BoardTyp; label: string }[] = [
  { wert: "alle", label: "Alle" },
  { wert: "frei", label: "Frei" },
  { wert: "bauplanung", label: "Bauplanung" },
  { wert: "prozess", label: "Prozess" },
];

function relativeZeit(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diffMs / 60_000);
  if (min < 60) return min <= 1 ? "gerade eben" : `vor ${min} Min.`;
  const std = Math.floor(min / 60);
  if (std < 24) return `vor ${std} Std.`;
  const tage = Math.floor(std / 24);
  return tage === 1 ? "vor 1 Tag" : `vor ${tage} Tagen`;
}

/** Mobiles Gegenstueck zu office/boards/OfficeBoardsPage.tsx -- Liste statt
 * Karten-Raster (schmaler Bildschirm), sonst dieselbe Datenquelle
 * (boardsApi). Das Anlegen bleibt bewusst simpel (nur Name + Art), volles
 * Bearbeiten/Werkzeuge gibt es erst nach dem Oeffnen. */
export function BoardsUebersichtPage() {
  const bestaetigen = useBestaetigung();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<"alle" | BoardTyp>("alle");
  const [zeigeNeu, setZeigeNeu] = useState(false);
  const [name, setName] = useState("");
  const [typ, setTyp] = useState<BoardTyp>("frei");
  const [nameVersucht, setNameVersucht] = useState(false);

  const { data: boards, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({ queryKey: ["boards"], queryFn: () => boardsApi.list() });

  const erstellen = useMutation({
    mutationFn: () => boardsApi.create({ name: name.trim(), board_typ: typ }),
    onSuccess: (board) => navigate(`/boards/${board.id}`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["boards"] }),
  });

  const loeschen = useMutation({
    mutationFn: (id: string) => boardsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["boards"] }),
  });

  const gefiltert = (boards ?? []).filter((b) => filter === "alle" || b.board_typ === filter);

  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-2">
        <h1 className="text-titel-mobil font-bold text-label">Boards</h1>
        <span className="text-sekundaer font-medium text-label2">{boards?.length ?? 0}</span>
      </div>

      <button type="button" onClick={() => setZeigeNeu(true)} className={NEU_BUTTON_KLASSE}>
        + Neues Board
      </button>

      <AnlegenPanel offen={zeigeNeu} titel="Neues Board" onClose={() => {
          setZeigeNeu(false);
          setNameVersucht(false);
        }}>
        <form
          noValidate
          className="space-y-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            setNameVersucht(true);
            if (name.trim()) erstellen.mutate();
          }}
        >
          <Feld label="Name" pflicht fehler={nameVersucht && !name.trim() ? "Bitte einen Namen angeben" : null}>
            {(p) => (
              <input
                {...p}
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z. B. Projektplanung Rheinblick"
                className={FELD_KLASSE}
              />
            )}
          </Feld>
          <Feld label="Art">
            {(p) => (
              <Select {...p} value={typ} onChange={(e) => setTyp(e.target.value as BoardTyp)}>
                {(Object.keys(TYP_LABEL) as BoardTyp[]).map((t) => (
                  <option key={t} value={t}>
                    {TYP_LABEL[t]}
                  </option>
                ))}
              </Select>
            )}
          </Feld>
          <button type="submit" disabled={erstellen.isPending} className={`${NEU_BUTTON_KLASSE} w-full`}>
            Anlegen
          </button>
        </form>
      </AnlegenPanel>

      <SegmentedControl ariaLabel="Boardart" optionen={FILTER_OPTIONEN} wert={filter} onChange={setFilter} groesse="mobil" volleBreite />

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !boards ? (
        <FehlerZustand fehler={ladeFehler} was="Die Boards" onErneut={() => void neuLaden()} />
      ) : gefiltert.length === 0 ? (
        <EmptyState
          icon={StickyNote}
          text={
            boards && boards.length > 0
              ? "Keine Boards dieser Art."
              : "Noch keine Boards angelegt. Ein Board sammelt Notizen und Vorgänge für ein Vorhaben."
          }
          action={
            boards && boards.length > 0 ? undefined : (
              <button type="button" onClick={() => setZeigeNeu(true)} className={NEU_BUTTON_KLASSE}>
                + Neues Board
              </button>
            )
          }
        />
      ) : (
        <div className="space-y-2.5">
          {gefiltert.map((b) => {
            const Icon = TYP_ICON[b.board_typ];
            return (
              <div key={b.id} className="card-interactive card-ap flex items-center gap-1 pr-1">
                <button
                  onClick={() => navigate(`/boards/${b.id}`)}
                  className="btn-touch flex min-w-0 flex-1 items-center gap-3 p-3 text-left"
                >
                  <SymbolKachel icon={Icon} farbe={TYP_FARBE[b.board_typ]} groesse={36} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-fliess font-bold text-label">{b.name}</p>
                    <p className="mt-0.5 text-meta text-label2">
                      {TYP_LABEL[b.board_typ]} &middot; {relativeZeit(b.updated_at)}
                    </p>
                  </div>
                </button>
                <AktionsMenue
                  label={`Aktionen für ${b.name}`}
                  eintraege={[
                    {
                      label: "Löschen",
                      destruktiv: true,
                      onClick: async () => {
                        if (await bestaetigen({ titel: `Board "${b.name}" löschen?`, bestaetigenLabel: "Löschen" })) loeschen.mutate(b.id);
                      },
                    },
                  ]}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
