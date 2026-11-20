import { useQuery } from "@tanstack/react-query";
import { Star, UserCheck } from "lucide-react";
import { useMemo } from "react";

import { kundenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import type { Kunde } from "../../types";
import { betreuungFilterOptionen, betreuungFilterWert, hauptbetreuerFilterWert } from "../../utils/betreuung";
import type { FilterFeld } from "../filter/typen";

/** Filterfelder "Betreuung" (leer = ohne Betreuung) und "Hauptbetreuer" für Kundenlisten. */
export function betreuungFilterFelder(optionen: { wert: string; label: string }[]): FilterFeld<Kunde>[] {
  return [
    {
      key: "betreuung",
      label: "Betreuung",
      typ: "person",
      icon: UserCheck,
      wert: (k) => betreuungFilterWert(k.betreuung),
      optionen,
    },
    {
      key: "hauptbetreuer",
      label: "Hauptbetreuer",
      typ: "person",
      icon: Star,
      wert: (k) => hauptbetreuerFilterWert(k.betreuung),
      optionen,
    },
  ];
}

export function useBetreuungFilterFelder(kunden: Kunde[] | undefined): FilterFeld<Kunde>[] {
  const { currentUser, hatRecht } = useAuth();
  // Ohne kunden.bearbeiten fehlt die Kandidatenliste; die Optionen kommen dann aus den Betreuern der Kundenliste.
  const { data: kandidaten } = useQuery({
    queryKey: ["kunden", "betreuer-auswahl"],
    queryFn: kundenApi.betreuerAuswahl,
    enabled: hatRecht("kunden", "bearbeiten"),
  });
  return useMemo(
    () =>
      betreuungFilterFelder(
        betreuungFilterOptionen(
          currentUser?.id,
          kandidaten?.filter((k) => k.aktiv).map((k) => ({ id: k.user_id, name: k.name })),
          kunden,
        ),
      ),
    [currentUser?.id, kandidaten, kunden],
  );
}
