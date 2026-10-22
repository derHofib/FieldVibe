import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { angeboteApi, maengelApi, projektAufgabenApi } from "../../../api/endpoints";
import type { MangelSchweregrad, MangelStatus } from "../../../types";
import { openPdfBlob } from "../../../utils/pdf";

/** Mängel und verknüpfte Aufgaben. */
export function useVorgangMaengel({
  id,
  meldeAktionsFehler,
}: {
  id: string | undefined;
  meldeAktionsFehler: (err: unknown) => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [showMangelForm, setShowMangelForm] = useState(false);
  const [mangelBeschreibung, setMangelBeschreibung] = useState("");
  const [mangelSchweregrad, setMangelSchweregrad] = useState<MangelSchweregrad>("mittel");
  const { data: maengel } = useQuery({
    queryKey: ["maengel", "vorgang", id],
    queryFn: () => maengelApi.list({ vorgang_id: id! }),
    enabled: !!id,
  });

  // Kein Rechte-Gate hier: das Backend liefert bei vorgang_id-Filter
  // ohnehin nur Kanban-Aufgaben mit "projekte"-Recht plus die eigenen
  // privaten Aufgaben (siehe app/api/routes/projekte.py) -- Techniker ohne
  // Projekte-Recht sollen ihre privat verknuepften Aufgaben trotzdem sehen.
  const { data: verknuepfteAufgaben } = useQuery({
    queryKey: ["projekt-aufgaben", "vorgang", id],
    queryFn: () => projektAufgabenApi.list({ vorgang_id: id! }),
    enabled: !!id,
  });

  const mangelMutation = useMutation({
    mutationFn: () =>
      maengelApi.create({ vorgang_id: id!, beschreibung: mangelBeschreibung, schweregrad: mangelSchweregrad }),
    onSuccess: () => {
      setShowMangelForm(false);
      setMangelBeschreibung("");
      queryClient.invalidateQueries({ queryKey: ["maengel", "vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
    onError: meldeAktionsFehler,
  });
  // `mangelMutation.isPending` allein reicht nicht als Doppel-Submit-Schutz --
  // zwei sehr schnelle Klicks koennen beide feuern, bevor React nach dem
  // ersten mutate()-Aufruf neu gerendert hat (disabled greift dann zu spaet).
  // Ref ist synchron, unabhaengig vom Render-Zyklus.
  const mangelErfassenLaeuft = useRef(false);
  const mangelErfassen = () => {
    if (!mangelBeschreibung.trim() || mangelErfassenLaeuft.current) return;
    mangelErfassenLaeuft.current = true;
    mangelMutation.mutate(undefined, { onSettled: () => (mangelErfassenLaeuft.current = false) });
  };

  const mangelStatusMutation = useMutation({
    mutationFn: ({ mangelId, status }: { mangelId: string; status: MangelStatus }) =>
      maengelApi.update(mangelId, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["maengel", "vorgang", id] });
      queryClient.invalidateQueries({ queryKey: ["vorgang-events", id] });
    },
    onError: meldeAktionsFehler,
  });

  const deleteMangelMutation = useMutation({
    mutationFn: (mangelId: string) => maengelApi.remove(mangelId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["maengel", "vorgang", id] }),
    onError: meldeAktionsFehler,
  });

  const angebotAusMaengelnMutation = useMutation({
    mutationFn: (mangelIds: string[]) => angeboteApi.createFromMaengel(mangelIds),
    onSuccess: (angebot) => navigate(`/angebote/${angebot.id}`),
    onError: meldeAktionsFehler,
  });

  const maengelProtokollMutation = useMutation({
    mutationFn: () => maengelApi.protokollPdf(id!),
    onSuccess: openPdfBlob,
    onError: meldeAktionsFehler,
  });

  const offeneMaengelAnzahl = (maengel ?? []).filter((m) => m.status !== "behoben" && m.status !== "abgelehnt").length;

  return {
    angebotAusMaengelnMutation,
    deleteMangelMutation,
    maengel,
    maengelProtokollMutation,
    mangelBeschreibung,
    mangelErfassen,
    mangelErfassenLaeuft,
    mangelMutation,
    mangelSchweregrad,
    mangelStatusMutation,
    offeneMaengelAnzahl,
    setMangelBeschreibung,
    setMangelSchweregrad,
    setShowMangelForm,
    showMangelForm,
    verknuepfteAufgaben,
  };
}

export type MaengelDaten = ReturnType<typeof useVorgangMaengel>;
