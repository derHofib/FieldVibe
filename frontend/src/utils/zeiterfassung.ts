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
  freizeitausgleich: "Freizeitausgleich",
  sonstiges: "Sonstiges",
};

// Muss mit ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT in
// backend/app/schemas/zeiterfassung.py uebereinstimmen.
export const ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT: ZeiterfassungKategorie[] = [
  "pause",
  "urlaub",
  "krankheit",
  "freizeitausgleich",
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

// Bewusst NICHT d.toISOString().slice(0, 10) -- toISOString() rechnet immer
// auf UTC um, bei lokaler Mitternacht in einer Zeitzone oestlich von UTC
// (z.B. Europe/Berlin) landet das noch auf dem VORTAG und verschiebt damit
// z.B. einen Wochenfilter (von/bis) komplett um einen Tag. Gleiches Prinzip
// wie lokalerTag() oben: lokale Datumsfelder direkt auslesen.
export function toDateInput(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
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

// --- Monatsansicht (Office, /statistik) ---------------------------------

export interface MonatsTag {
  /** Lokaler Kalendertag als YYYY-MM-DD, identisch zu lokalerTag(). */
  tag: string;
  tagNr: number;
  /** 0 = Montag ... 6 = Sonntag (Wochenanzeige beginnt in DE am Montag). */
  wochentag: number;
  istWochenende: boolean;
}

/** Alle Kalendertage eines Monats (monat0 = 0..11). Ueber Date(jahr, monat+1, 0)
 * statt fester Tabellen, damit Schaltjahre automatisch stimmen. */
export function tageDesMonats(jahr: number, monat0: number): MonatsTag[] {
  const anzahl = new Date(jahr, monat0 + 1, 0).getDate();
  const tage: MonatsTag[] = [];
  for (let tagNr = 1; tagNr <= anzahl; tagNr++) {
    const d = new Date(jahr, monat0, tagNr);
    const wochentag = (d.getDay() + 6) % 7;
    tage.push({ tag: toDateInput(d), tagNr, wochentag, istWochenende: wochentag >= 5 });
  }
  return tage;
}

/** Erster und letzter Tag des Monats als YYYY-MM-DD fuer von/bis-Filter. */
export function monatsGrenzen(jahr: number, monat0: number): { von: string; bis: string } {
  return {
    von: toDateInput(new Date(jahr, monat0, 1)),
    bis: toDateInput(new Date(jahr, monat0 + 1, 0)),
  };
}

type MitZeitraum = { start_at: string; ende_at: string | null; kategorie: ZeiterfassungKategorie };

/** Gruppiert nach lokalem Kalendertag, je Tag nach Startzeit sortiert. */
export function eintraegeJeTag<T extends MitZeitraum>(eintraege: T[]): Map<string, T[]> {
  const map = new Map<string, T[]>();
  for (const e of eintraege) {
    const tag = lokalerTag(e.start_at);
    const liste = map.get(tag);
    if (liste) liste.push(e);
    else map.set(tag, [e]);
  }
  for (const liste of map.values()) liste.sort((a, b) => a.start_at.localeCompare(b.start_at));
  return map;
}

/** Arbeitsstunden ohne Pause/Urlaub/Krankheit/Freizeitausgleich; laufende Eintraege zaehlen 0. */
export function arbeitsstunden(eintraege: MitZeitraum[]): number {
  return eintraege.reduce(
    (summe, e) =>
      ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT.includes(e.kategorie)
        ? summe
        : summe + formatDauer(e.start_at, e.ende_at),
    0,
  );
}
