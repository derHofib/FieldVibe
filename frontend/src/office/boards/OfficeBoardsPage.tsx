import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Compass, LayoutGrid, Plus, StickyNote, Trash2, Workflow } from "lucide-react";
import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";

import { boardsApi } from "../../api/endpoints";
import { AktionsMenue } from "../../components/AktionsMenue";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import type { BoardTyp } from "../../types";
import { Karte, SeitenKopf } from "../OfficeUi";
import { FehlerZustand } from "../../components/FehlerZustand";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { Select } from "../../components/apple/Select";
import { SkeletonList } from "../../components/Skeleton";

const TYP_ICON: Record<BoardTyp, typeof LayoutGrid> = {
  frei: LayoutGrid,
  bauplanung: Compass,
  prozess: Workflow,
};

const TYP_LABEL: Record<BoardTyp, string> = {
  frei: "Freies Board",
  bauplanung: "Bauplanung",
  prozess: "Prozess",
};

const TYP_TON: Record<BoardTyp, string> = {
  frei: "bg-indigo-100 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300",
  bauplanung: "bg-st-arbeit-bg text-st-arbeit  ",
  prozess: "bg-st-erledigt-bg text-st-erledigt  ",
};

function relativeZeit(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diffMs / 60_000);
  if (min < 60) return min <= 1 ? "gerade eben" : `vor ${min} Min.`;
  const std = Math.floor(min / 60);
  if (std < 24) return `vor ${std} Std.`;
  const tage = Math.floor(std / 24);
  return tage === 1 ? "vor 1 Tag" : `vor ${tage} Tagen`;
}

export function OfficeBoardsPage() {
  const uid = useId();
  const bestaetigen = useBestaetigung();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [zeigeNeu, setZeigeNeu] = useState(false);
  const [name, setName] = useState("");
  const [typ, setTyp] = useState<BoardTyp>("frei");

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

  return (
    <div>
      <SeitenKopf titel="Boards" anzahl={boards?.length}>
        <button onClick={() => setZeigeNeu(true)} className={NEU_BUTTON_KLASSE}>
          <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
          Neues Board
        </button>
      </SeitenKopf>

      <AnlegenPanel offen={zeigeNeu} titel="Neues Board" onClose={() => setZeigeNeu(false)}>
        <form
          className="flex flex-col gap-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim() && !erstellen.isPending) erstellen.mutate();
          }}
        >
          <div>
            <label htmlFor={`${uid}-0`} className="mb-1 block text-fliess font-medium text-label">
              Name<span aria-hidden="true" className="text-st-fehlt"> *</span>
            </label>
            <input
              id={`${uid}-0`}
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z. B. Projektplanung Rheinblick"
              className="field-ap"
            />
          </div>
          <div>
            <label htmlFor={`${uid}-1`} className="mb-1 block text-fliess font-medium text-label">Art</label>
            <Select id={`${uid}-1`} value={typ} onChange={(e) => setTyp(e.target.value as BoardTyp)}>
              {(Object.keys(TYP_LABEL) as BoardTyp[]).map((t) => (
                <option key={t} value={t}>
                  {TYP_LABEL[t]}
                </option>
              ))}
            </Select>
          </div>
          {erstellen.isError && (
            <p role="alert" className="text-sekundaer text-st-fehlt">Das Board konnte nicht angelegt werden.</p>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setZeigeNeu(false)} className="btn-touch btn-ap px-4">
              Abbrechen
            </button>
            <button type="submit" disabled={!name.trim() || erstellen.isPending} className={NEU_BUTTON_KLASSE}>
              Anlegen
            </button>
          </div>
        </form>
      </AnlegenPanel>

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !boards ? (
        <FehlerZustand fehler={ladeFehler} was="Die Boards" onErneut={() => void neuLaden()} />
      ) : !boards || boards.length === 0 ? (
        <EmptyState
          icon={StickyNote}
          text="Noch keine Boards angelegt. Boards sind freie Flächen für Planung, Skizzen und Abläufe."
          action={
            <button type="button" onClick={() => setZeigeNeu(true)} className="btn-ap px-4 py-2 text-sekundaer">
              Neues Board
            </button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {boards.map((b) => {
            const Icon = TYP_ICON[b.board_typ];
            return (
              <div key={b.id} className="relative">
                <button onClick={() => navigate(`/boards/${b.id}`)} className="block w-full text-left">
                  <Karte className="overflow-hidden transition-colors hover:bg-fill">
                    <div
                      className="flex h-24 items-center justify-center bg-fill"
                      style={{ backgroundImage: "radial-gradient(var(--sepstrong) 1px, transparent 1px)", backgroundSize: "16px 16px" }}
                    >
                      <span className={`flex h-11 w-11 items-center justify-center rounded-xl ${TYP_TON[b.board_typ]}`}>
                        <Icon size={20} strokeWidth={2} aria-hidden="true" />
                      </span>
                    </div>
                    <div className="p-3.5">
                      <p className="truncate text-fliess font-bold text-label">{b.name}</p>
                      <div className="mt-1 flex items-center justify-between gap-2">
                        <span className="text-meta font-medium text-label2">{TYP_LABEL[b.board_typ]}</span>
                        <span className="text-meta text-label2">{relativeZeit(b.updated_at)}</span>
                      </div>
                    </div>
                  </Karte>
                </button>
                <div className="absolute top-2 right-2">
                  <AktionsMenue
                    label={`Aktionen für Board ${b.name}`}
                    eintraege={[
                      {
                        label: "Löschen",
                        icon: Trash2,
                        destruktiv: true,
                        onClick: async () => {
                          if (await bestaetigen({ titel: `Board "${b.name}" löschen?`, bestaetigenLabel: "Löschen" })) loeschen.mutate(b.id);
                        },
                      },
                    ]}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
