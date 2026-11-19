import { useQuery } from "@tanstack/react-query";
import { Star, UserCheck } from "lucide-react";
import { useMemo } from "react";

import { usersApi } from "../../api/endpoints";
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
  const { data: mitarbeiter } = useQuery({
    queryKey: ["users", "auswahl"],
    queryFn: usersApi.auswahl,
    enabled: hatRecht("mitarbeiterverwaltung", "sehen"),
  });
  return useMemo(
    () =>
      betreuungFilterFelder(
        betreuungFilterOptionen(
          currentUser?.id,
          mitarbeiter?.filter((u) => u.aktiv && (u.role === "mandant_admin" || u.role === "custom")),
          kunden,
        ),
      ),
    [currentUser?.id, mitarbeiter, kunden],
  );
}
