export type OrdnerRolle = "posteingang" | "gesendet" | "entwuerfe" | "archiv" | "spam" | "papierkorb";

/** Anzeigereihenfolge der Standardordner. */
export const ROLLEN_REIHENFOLGE: OrdnerRolle[] = ["posteingang", "gesendet", "entwuerfe", "archiv", "spam", "papierkorb"];

export const ROLLEN_LABEL: Record<OrdnerRolle, string> = {
  posteingang: "Posteingang",
  gesendet: "Gesendet",
  entwuerfe: "Entwürfe",
  archiv: "Archiv",
  spam: "Spam",
  papierkorb: "Papierkorb",
};

const NAMEN: Record<OrdnerRolle, string[]> = {
  posteingang: ["inbox", "posteingang"],
  gesendet: ["sent", "gesendet", "sent items", "sent messages", "gesendete objekte", "gesendete elemente"],
  entwuerfe: ["drafts", "entwürfe", "entwurf"],
  archiv: ["archive", "archiv"],
  spam: ["junk", "spam", "junk-e-mail"],
  papierkorb: ["trash", "papierkorb", "deleted", "deleted items", "gelöschte elemente", "gelöschte objekte"],
};

/** Leitet die Rolle aus dem letzten Pfadteil des IMAP-Namens ab (Delimiter "."
 * oder "/"), weil die SPECIAL-USE-Kennung des Servers nicht gespeichert wird. */
export function ordnerRolle(imapName: string): OrdnerRolle | null {
  const letzter = imapName.split(/[./]/).filter(Boolean).pop()?.trim().toLowerCase();
  if (!letzter) return null;
  for (const rolle of ROLLEN_REIHENFOLGE) {
    if (NAMEN[rolle].includes(letzter)) return rolle;
  }
  return null;
}
