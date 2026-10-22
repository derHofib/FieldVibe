import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { termineApi } from "../../../api/endpoints";
import type { TerminWarnung } from "../../../types";

/** Termine des Vorgangs und deren Planung. */
export function useVorgangTermine({
  id,
  meldeAktionsFehler,
}: {
  id: string | undefined;
  meldeAktionsFehler: (err: unknown) => void;
}) {
  const queryClient = useQueryClient();
  const [showTerminForm, setShowTerminForm] = useState(false);
  const [terminWarnungen, setTerminWarnungen] = useState<TerminWarnung[]>([]);
  const [terminTechnikerId, setTerminTechnikerId] = useState("");
  const [terminTitel, setTerminTitel] = useState("");
  const [terminStart, setTerminStart] = useState("");
  const [terminEnde, setTerminEnde] = useState("");
  const [terminWocheOffset, setTerminWocheOffset] = useState(0);
  const { data: termine } = useQuery({
    queryKey: ["termine", "vorgang", id],
    queryFn: () => termineApi.list({ vorgang_id: id! }),
    enabled: !!id,
  });

  const terminMutation = useMutation({
    mutationFn: () =>
      termineApi.create({
        vorgang_id: id!,
        techniker_id: terminTechnikerId,
        titel: terminTitel,
        start_at: new Date(terminStart).toISOString(),
        ende_at: new Date(terminEnde).toISOString(),
      }),
    onSuccess: (result) => {
      setTerminWarnungen(result.warnungen);
      setShowTerminForm(false);
      setTerminTitel("");
      queryClient.invalidateQueries({ queryKey: ["termine", "vorgang", id] });
    },
    onError: meldeAktionsFehler,
  });

  const deleteTerminMutation = useMutation({
    mutationFn: (terminId: string) => termineApi.remove(terminId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["termine", "vorgang", id] }),
    onError: meldeAktionsFehler,
  });

  // Kennzahlen-Zeile auf der Uebersicht (nur "kompakt"+"voll", siehe KennzahlenZeile) --
  // je ein kompakter Wert pro Abschnitt, verlinkt dorthin, damit man nicht
  // erst hineinklicken muss um zu wissen, ob dort ueberhaupt etwas ist.
  const naechsterTermin = (termine ?? [])
    .filter((t) => new Date(t.start_at).getTime() >= Date.now() && t.status !== "abgesagt")
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())[0];

  return {
    deleteTerminMutation,
    naechsterTermin,
    setShowTerminForm,
    setTerminEnde,
    setTerminStart,
    setTerminTechnikerId,
    setTerminTitel,
    setTerminWarnungen,
    setTerminWocheOffset,
    showTerminForm,
    terminEnde,
    terminMutation,
    terminStart,
    terminTechnikerId,
    terminTitel,
    terminWarnungen,
    terminWocheOffset,
    termine,
  };
}

export type TermineDaten = ReturnType<typeof useVorgangTermine>;
