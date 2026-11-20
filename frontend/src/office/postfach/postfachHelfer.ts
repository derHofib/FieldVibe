/** "Abgeglichen vor N Min." -- null ohne bisherigen Abgleich. */
export function abgleichStand(iso: string | null, jetzt: Date = new Date()): string | null {
  if (!iso) return null;
  const minuten = Math.max(0, Math.round((jetzt.getTime() - new Date(iso).getTime()) / 60_000));
  if (minuten < 1) return "Abgeglichen gerade eben";
  if (minuten < 60) return `Abgeglichen vor ${minuten} Min.`;
  const stunden = Math.round(minuten / 60);
  if (stunden < 24) return `Abgeglichen vor ${stunden} Std.`;
  return `Abgeglichen am ${new Date(iso).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}`;
}

/** Kürzel für Monogramm/Kontokachel: die ersten Buchstaben des Namens. */
export function kuerzelAus(name: string): string {
  return name.trim().slice(0, 2).toUpperCase() || "?";
}

// Adressen kommen als "a@b.de" oder "Name <a@b.de>" -- verglichen wird nur die reine Adresse.
function reineAdresse(a: string): string {
  const m = a.match(/<([^>]+)>/);
  return (m ? m[1] : a).trim().toLowerCase();
}

/** Empfänger für „Allen antworten“: an = Absender, cc = übrige Empfänger
 * (an + cc) ohne die eigene Adresse und ohne den Absender, dedupliziert. */
export function allenAntwortenEmpfaenger(
  nachricht: { von_adresse: string | null; an: string[]; cc: string[] },
  eigeneAdresse: string,
): { an: string[]; cc: string[] } {
  const absender = nachricht.von_adresse ? reineAdresse(nachricht.von_adresse) : null;
  const ausgeschlossen = new Set([reineAdresse(eigeneAdresse), ...(absender ? [absender] : [])]);
  const cc: string[] = [];
  for (const adresse of [...nachricht.an, ...nachricht.cc]) {
    const roh = reineAdresse(adresse);
    if (!roh || ausgeschlossen.has(roh)) continue;
    ausgeschlossen.add(roh);
    cc.push(adresse);
  }
  return { an: nachricht.von_adresse ? [nachricht.von_adresse] : [], cc };
}
