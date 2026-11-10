import type { CurrentUser, RechteAktion, RechteBereich } from "../types";

// loesch_operativ erbt im Backend ueberall die Rechte eines mandant_admin
// (siehe require_roles in app/api/deps.py), zaehlt hier also mit.
export function istAdminRolle(user: CurrentUser | undefined): boolean {
  const rolle = user?.role;
  return rolle === "super_admin" || rolle === "mandant_admin" || rolle === "loesch_operativ";
}

// Endpunkte mit require_roles("mandant_admin", "custom"): die Feinsteuerung fuer
// custom laeuft zusaetzlich ueber hatRecht(...).
export function istAdminOderCustom(user: CurrentUser | undefined): boolean {
  return istAdminRolle(user) || user?.role === "custom";
}

// Backend (account_typen._verwalter): Admin-Rollen immer, custom nur mit dem Recht
// "rechte_verwalten" im Organigramm oder in der Mitarbeiterverwaltung.
export function darfRechteVerwalten(
  user: CurrentUser | undefined,
  hatRecht: (bereich: RechteBereich, aktion: RechteAktion) => boolean,
): boolean {
  if (istAdminRolle(user)) return true;
  return user?.role === "custom" && (hatRecht("organigramm", "rechte_verwalten") || hatRecht("mitarbeiterverwaltung", "rechte_verwalten"));
}
