import type { CurrentUser, MandantModul } from "../types";

// "Erlaubt, wenn mindestens eines der angegebenen Module aktiv ist" --
// analog zum Backend-Pendant require_module() (siehe app/api/deps.py),
// wichtig fuer Anlagen, die sowohl zu "kundenverwaltung" als auch zu
// "material" gehoeren koennen.
export function istModulAktiv(currentUser: CurrentUser | undefined, ...module: MandantModul[]): boolean {
  const deaktiviert = currentUser?.deaktivierte_module ?? [];
  return module.some((m) => !deaktiviert.includes(m));
}
