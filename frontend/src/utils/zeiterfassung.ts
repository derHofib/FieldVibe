import type { StatusKey } from "../components/apple/status";
import type { ZeiterfassungBuchungsstatus, ZeiterfassungKategorie } from "../types";

// Muss mit ZEITERFASSUNG_KATEGORIE_LABEL in backend/app/schemas/zeiterfassung.py
// uebereinstimmen ("auftrag" hat bewusst kein Label -- dort steht die
// Vorgangsnummer statt einer Kategorie-Bezeichnung).
export const ZEITERFASSUNG_KATEGORIE_LABEL: Partial<Record<ZeiterfassungKategorie, string>> = {
  verwaltung: "Verwaltung",
  fahrzeit: "Fahrzeit",
  schulung: "Schulung",
  pause: "Pause",
  urlaub: "Urlaub",
  krankheit: "Krankheit",
  sonstiges: "Sonstiges",
};

// Muss mit ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT in
// backend/app/schemas/zeiterfassung.py uebereinstimmen.
export const ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT: ZeiterfassungKategorie[] = [
  "pause",
  "urlaub",
  "krankheit",
];

export function formatDauer(startAt: string, endeAt: string | null): number {
  if (!endeAt) return 0;
  return (new Date(endeAt).getTime() - new Date(startAt).getTime()) / 1000 / 3600;
}

/** Lokaler Kalendertag (nicht UTC) als sortierbarer YYYY-MM-DD-Schluessel --
 * ein Eintrag, der z.B. um 23:30 Ortszeit beginnt, soll auf DEM Tag
 * gruppiert werden, nicht auf dem naechsten UTC-Tag. */
export function lokalerTag(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function formatUhrzeit(iso: string): string {
  return new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

export function montagDerWoche(datum: Date): Date {
  const tag = datum.getDay();
  const diffZuMontag = tag === 0 ? -6 : 1 - tag;
  const montag = new Date(datum);
  montag.setDate(datum.getDate() + diffZuMontag);
  montag.setHours(0, 0, 0, 0);
  return montag;
}

export function toDateInput(d: Date): string {
  return d.toISOString().slice(0, 10);
}

// --- Buchungsablauf (Stufe 2, docs/konzepte/ZEITERFASSUNG.md) -----------

export const BUCHUNGSSTATUS_LABEL: Record<ZeiterfassungBuchungsstatus, string> = {
  vermerkt: "Vermerkt",
  vorgemerkt: "Vorgemerkt",
  gebucht: "Gebucht",
  abgerechnet: "Abgerechnet",
};

// Wiederverwendet die bestehenden sechs Status-Token statt eigener Farben
// (siehe fieldvibe-design-Skill, Checkliste Punkt 1: Status laeuft immer
// ueber StatusKey). vorgemerkt->neu (blau), gebucht/abgerechnet->erledigt
// (gruen, zusaetzlich mit Schloss-Icon in der UI), vermerkt->geplant (grau).
export function buchungsstatusZuToken(status: ZeiterfassungBuchungsstatus): StatusKey {
  switch (status) {
    case "vermerkt":
      return "geplant";
    case "vorgemerkt":
      return "neu";
    case "gebucht":
    case "abgerechnet":
      return "erledigt";
  }
}

// Ab hier ist ein Eintrag ueber PATCH/DELETE nicht mehr direkt bearbeitbar
// (muss erst zurueckgezogen bzw. storniert werden) -- spiegelt
// _BUCHUNGSSTATUS_BEARBEITBAR in backend/app/api/routes/zeiterfassung.py.
export function buchungsstatusGesperrt(status: ZeiterfassungBuchungsstatus): boolean {
  return status !== "vermerkt";
}
