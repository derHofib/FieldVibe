import type { Role } from "../types";

export const ROLE_LABEL: Record<Role, string> = {
  super_admin: "Super-Admin",
  mandant_admin: "Mandanten-Admin",
  custom: "Account-Typ",
  loesch_ansicht: "Papierkorb (nur Ansicht)",
  loesch_operativ: "Papierkorb (operativ)",
};
