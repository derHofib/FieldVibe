// Unbekannte Rohwerte (Enum-/Aktionsstrings aus dem Backend) werden lesbar gemacht statt roh angezeigt.
export function lesbarerWert(wert: string): string {
  const text = wert.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const ROLLEN: Record<string, string> = {
  super_admin: "Super-Admin",
  mandant_admin: "Mandanten-Admin",
  custom: "Account-Typ",
  loesch_ansicht: "Papierkorb (nur Ansicht)",
  loesch_operativ: "Papierkorb (operativ)",
};

export function rolleLabel(rolle: string | null | undefined): string {
  if (!rolle) return "–";
  return ROLLEN[rolle] ?? lesbarerWert(rolle);
}

const AKTIVITAETEN: Record<string, string> = {
  login: "Anmeldung",
  logout: "Abmeldung",
  login_failed: "Anmeldung fehlgeschlagen",
};

// Die Aktionsbezeichner sind offen (jede Route vergibt eigene): nur bekannte Rohwerte
// bekommen eine feste Bezeichnung, der Rest läuft durch die allgemeine Lesbarmachung.
export function aktivitaetLabel(aktion: string | null | undefined): string {
  if (!aktion) return "–";
  return AKTIVITAETEN[aktion] ?? lesbarerWert(aktion);
}
