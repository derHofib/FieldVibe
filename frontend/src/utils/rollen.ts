import type { CurrentUser } from "../types";

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
