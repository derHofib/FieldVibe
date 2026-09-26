import { useQuery } from "@tanstack/react-query";

import { zeiterfassungApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";

/** Anzahl mandantenweit zur Buchung vorgemerkter Zeiteintraege -- Badge an
 * der Seite "Zeiten buchen" (siehe navSeiten.ts, OfficeLayout.tsx,
 * MehrPage.tsx). Nur fuer Buchungsberechtigte relevant (siehe
 * darf_zeiten_buchen), sonst undefined -- kein Badge statt "0". */
export function useVorgemerkteZeitenAnzahl(): number | undefined {
  const { currentUser } = useAuth();
  const aktiv = !!currentUser?.darf_zeiten_buchen;
  const { data } = useQuery({
    queryKey: ["zeiterfassung-vorgemerkt-anzahl"],
    queryFn: () => zeiterfassungApi.listFuerZeitraum({ buchungsstatus: "vorgemerkt" }),
    enabled: aktiv,
    refetchInterval: 60_000,
  });
  return aktiv ? data?.length : undefined;
}
