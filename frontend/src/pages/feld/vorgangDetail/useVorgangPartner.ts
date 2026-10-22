import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { partnerApi, vorgaengeApi } from "../../../api/endpoints";
import { useAuth } from "../../../context/AuthContext";
import type { Vorgang } from "../../../types";
import { istModulAktiv } from "../../../utils/module";

/** Nachunternehmer-Zuweisung und die Freigabe für Partner-Kommentare. */
export function useVorgangPartner({
  id,
  meldeAktionsFehler,
  vorgang,
}: {
  id: string | undefined;
  meldeAktionsFehler: (err: unknown) => void;
  vorgang: Vorgang | undefined;
}) {
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();
  const [showPartnerForm, setShowPartnerForm] = useState(false);
  const [partnerAuswahl, setPartnerAuswahl] = useState("");
  const [partnerHonorar, setPartnerHonorar] = useState("");
  const [partnerWarnung, setPartnerWarnung] = useState(false);
  const kannPartnerVerwalten =
    istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "bearbeiten");

  const { data: partnerListe } = useQuery({
    queryKey: ["partner"],
    queryFn: () => partnerApi.list(),
    enabled: showPartnerForm && kannPartnerVerwalten,
  });
  const { data: zugewiesenerPartner } = useQuery({
    queryKey: ["partner", vorgang?.partner_id],
    queryFn: () => partnerApi.get(vorgang!.partner_id!),
    enabled: istModulAktiv(currentUser, "nachunternehmer") && hatRecht("partner", "sehen") && !!vorgang?.partner_id,
  });
  const partnerKommentarMoeglich = istModulAktiv(currentUser, "nachunternehmer") && !!vorgang?.partner_id;

  const partnerZuweisenMutation = useMutation({
    mutationFn: () => vorgaengeApi.partnerZuweisen(id!, partnerAuswahl, partnerHonorar || undefined),
    onSuccess: (antwort) => {
      setShowPartnerForm(false);
      setPartnerAuswahl("");
      setPartnerHonorar("");
      setPartnerWarnung(antwort.freistellungsbescheinigung_warnung);
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
    },
    onError: meldeAktionsFehler,
  });

  const partnerAufhebenMutation = useMutation({
    mutationFn: () => vorgaengeApi.partnerZuweisen(id!, null),
    onSuccess: () => {
      setPartnerWarnung(false);
      queryClient.invalidateQueries({ queryKey: ["vorgang", id] });
    },
    onError: meldeAktionsFehler,
  });


  return {
    kannPartnerVerwalten,
    partnerAufhebenMutation,
    partnerAuswahl,
    partnerHonorar,
    partnerKommentarMoeglich,
    partnerListe,
    partnerWarnung,
    partnerZuweisenMutation,
    setPartnerAuswahl,
    setPartnerHonorar,
    setPartnerWarnung,
    setShowPartnerForm,
    showPartnerForm,
    zugewiesenerPartner,
  };
}

export type PartnerDaten = ReturnType<typeof useVorgangPartner>;
