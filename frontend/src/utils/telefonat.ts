import type {
  Ansprechpartner,
  Telefonat,
  TelefonatCreate,
  TelefonatErgebnis,
  TelefonatRichtung,
  TelefonatUpdate,
} from "../types";

export const TELEFONAT_RICHTUNG_LABEL: Record<TelefonatRichtung, string> = {
  ausgehend: "Ausgehend",
  eingehend: "Eingehend",
};

export const TELEFONAT_ERGEBNIS_LABEL: Record<TelefonatErgebnis, string> = {
  erreicht: "Erreicht",
  nicht_erreicht: "Nicht erreicht",
  mailbox: "Mailbox",
};

/** Marker für "Andere Person" in der Partner-Auswahl (keine echte Ansprechpartner-ID). */
export const ANDERE_PERSON = "__andere__";

/** Präfix für Kontakte vor Ort in der Partner-Auswahl (Wert = `kontakt:<id>`); Ansprechpartner-IDs tragen keins. */
export const KONTAKT_PRAEFIX = "kontakt:";

export function kontaktAuswahlWert(kontaktId: string): string {
  return `${KONTAKT_PRAEFIX}${kontaktId}`;
}

/** ID des Kontakts vor Ort, wenn die Auswahl einer ist. */
export function kontaktIdAusAuswahl(auswahl: string): string | null {
  return auswahl.startsWith(KONTAKT_PRAEFIX) ? auswahl.slice(KONTAKT_PRAEFIX.length) : null;
}

/** Eine Rufnummer lässt sich erst ab fünf Ziffern sinnvoll zuordnen. */
export function nummerErkennbar(nummer: string): boolean {
  return nummer.replace(/\D/g, "").length >= 5;
}

export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Nächster Werktag (Mo-Fr) um 9:00 Uhr lokal -- Standard für den Rückruf. */
export function naechsterWerktag9(jetzt: Date = new Date()): Date {
  const d = new Date(jetzt);
  d.setDate(d.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
  d.setHours(9, 0, 0, 0);
  return d;
}

/** Ansprechpartner-Auswahl: operative zuerst, sonst Reihenfolge der Liste. */
export function sortiereAnsprechpartner(liste: Ansprechpartner[]): Ansprechpartner[] {
  return [...liste].sort((a, b) => Number(b.operativ) - Number(a.operativ));
}

/** Anzeige in Minuten, aufgerundet auf volle Minuten (6:01 min -> "7 Min"); Sekunden gehen unverändert an die API. */
export function formatDauer(sekunden: number | null | undefined): string | null {
  if (sekunden == null) return null;
  if (sekunden <= 0) return "0 Min";
  return `${Math.ceil(sekunden / 60)} Min`;
}

export function dauerSichtbar(ergebnis: TelefonatErgebnis): boolean {
  return ergebnis === "erreicht";
}

export function arbeitszeitSichtbar(vorgangId: string | null | undefined, ergebnis: TelefonatErgebnis): boolean {
  return !!vorgangId && ergebnis === "erreicht";
}

export function istRueckrufOffen(t: Pick<Telefonat, "rueckruf_am" | "rueckruf_erledigt_am">): boolean {
  return !!t.rueckruf_am && !t.rueckruf_erledigt_am;
}

export interface TelefonatFormular {
  richtung: TelefonatRichtung;
  ergebnis: TelefonatErgebnis;
  /** ID eines Ansprechpartners oder ANDERE_PERSON. */
  partnerAuswahl: string;
  partnerName: string;
  partnerNummer: string;
  beginn: string; // datetime-local
  dauerMinuten: string;
  notiz: string;
  rueckrufAn: boolean;
  rueckrufAm: string; // datetime-local
  arbeitszeit: boolean;
  vorgangId: string; // "" = ohne Vorgang
}

export type TelefonatFehler = Partial<Record<"partner" | "notiz" | "dauer" | "rueckruf" | "beginn", string>>;

export function dauerSekunden(f: Pick<TelefonatFormular, "dauerMinuten" | "ergebnis">): number | undefined {
  if (!dauerSichtbar(f.ergebnis)) return undefined;
  const min = Number(f.dauerMinuten.replace(",", "."));
  if (!f.dauerMinuten.trim() || Number.isNaN(min) || min < 0) return undefined;
  return Math.round(min * 60);
}

export function validiereTelefonat(f: TelefonatFormular): TelefonatFehler {
  const fehler: TelefonatFehler = {};
  if (!f.partnerName.trim()) fehler.partner = "Bitte einen Gesprächspartner angeben.";
  if (f.ergebnis === "erreicht" && !f.notiz.trim()) fehler.notiz = "Bei erreichtem Gespräch ist eine Notiz Pflicht.";
  if (dauerSichtbar(f.ergebnis) && f.dauerMinuten.trim()) {
    const min = Number(f.dauerMinuten.replace(",", "."));
    if (Number.isNaN(min) || min < 0 || min * 60 > 86400) fehler.dauer = "Dauer zwischen 0 und 1440 Minuten.";
  }
  if (!f.beginn || Number.isNaN(new Date(f.beginn).getTime())) fehler.beginn = "Bitte einen Beginn angeben.";
  if (f.rueckrufAn && (!f.rueckrufAm || Number.isNaN(new Date(f.rueckrufAm).getTime()))) {
    fehler.rueckruf = "Bitte Datum und Uhrzeit für den Rückruf angeben.";
  }
  return fehler;
}

export function baueTelefonatCreate(
  f: TelefonatFormular,
  kontext: { vorgangId?: string; kundeId?: string },
  clientUuid?: string,
  // Exakte Sekunden aus der laufenden Uhr; das Minutenfeld rundet nur für die Anzeige.
  dauerOverride?: number | null,
): TelefonatCreate {
  const vorgangId = kontext.vorgangId ?? (f.vorgangId || undefined);
  const dauer = dauerSichtbar(f.ergebnis) ? (dauerOverride ?? dauerSekunden(f)) : undefined;
  const body: TelefonatCreate = {
    partner_name: f.partnerName.trim(),
    richtung: f.richtung,
    ergebnis: f.ergebnis,
    beginn: new Date(f.beginn).toISOString(),
  };
  // Bei vorgang_id setzt der Server kunde_id selbst; eine abweichende wäre ein 422.
  if (vorgangId) body.vorgang_id = vorgangId;
  else if (kontext.kundeId) body.kunde_id = kontext.kundeId;
  const kontaktId = kontaktIdAusAuswahl(f.partnerAuswahl);
  if (kontaktId) body.vor_ort_kontakt_id = kontaktId;
  else if (f.partnerAuswahl !== ANDERE_PERSON && f.partnerAuswahl) body.ansprechpartner_id = f.partnerAuswahl;
  if (f.partnerNummer.trim()) body.partner_nummer = f.partnerNummer.trim();
  if (dauer !== undefined) body.dauer_sekunden = dauer;
  if (f.notiz.trim()) body.notiz = f.notiz.trim();
  if (f.rueckrufAn && f.rueckrufAm) body.rueckruf_am = new Date(f.rueckrufAm).toISOString();
  if (vorgangId && arbeitszeitSichtbar(vorgangId, f.ergebnis) && f.arbeitszeit && (dauer ?? 0) > 0) {
    body.als_arbeitszeit_buchen = true;
  }
  if (clientUuid) body.client_uuid = clientUuid;
  return body;
}

export function baueTelefonatUpdate(f: TelefonatFormular, alt: Telefonat, dauerOverride?: number | null): TelefonatUpdate {
  const dauer = dauerSichtbar(f.ergebnis) ? (dauerOverride ?? dauerSekunden(f)) : undefined;
  const body: TelefonatUpdate = {
    partner_name: f.partnerName.trim(),
    partner_nummer: f.partnerNummer.trim() || null,
    ansprechpartner_id:
      f.partnerAuswahl !== ANDERE_PERSON && f.partnerAuswahl && !kontaktIdAusAuswahl(f.partnerAuswahl) ? f.partnerAuswahl : null,
    vor_ort_kontakt_id: kontaktIdAusAuswahl(f.partnerAuswahl),
    richtung: f.richtung,
    ergebnis: f.ergebnis,
    beginn: new Date(f.beginn).toISOString(),
    dauer_sekunden: dauer ?? null,
    notiz: f.notiz.trim() || null,
    rueckruf_am: f.rueckrufAn && f.rueckrufAm ? new Date(f.rueckrufAm).toISOString() : null,
  };
  // Ein neuer Rückruf-Termin hebt "erledigt" auf; unveränderter Termin lässt den Stand unberührt.
  if (body.rueckruf_am && body.rueckruf_am !== alt.rueckruf_am && alt.rueckruf_erledigt_am) {
    body.rueckruf_erledigt = false;
  }
  return body;
}

export function formularAusTelefonat(t: Telefonat, ansprechpartner: Ansprechpartner[]): TelefonatFormular {
  const bekannt = t.ansprechpartner_id && ansprechpartner.some((a) => a.id === t.ansprechpartner_id);
  return {
    richtung: t.richtung,
    ergebnis: t.ergebnis,
    partnerAuswahl: t.vor_ort_kontakt_id ? kontaktAuswahlWert(t.vor_ort_kontakt_id) : bekannt ? t.ansprechpartner_id! : ANDERE_PERSON,
    partnerName: t.partner_name,
    partnerNummer: t.partner_nummer ?? "",
    beginn: toLocalInputValue(new Date(t.beginn)),
    dauerMinuten: t.dauer_sekunden != null ? String(Math.round(t.dauer_sekunden / 60)) : "",
    notiz: t.notiz ?? "",
    rueckrufAn: !!t.rueckruf_am,
    rueckrufAm: toLocalInputValue(t.rueckruf_am ? new Date(t.rueckruf_am) : naechsterWerktag9()),
    arbeitszeit: !!t.zeiterfassung_id,
    vorgangId: t.vorgang_id ?? "",
  };
}

export function leeresFormular(opt: {
  richtung?: TelefonatRichtung;
  beginn?: Date;
  dauerSekunden?: number;
  partner?: { ansprechpartnerId?: string | null; name?: string; nummer?: string | null };
  vorgangId?: string;
}): TelefonatFormular {
  const dauerMin = opt.dauerSekunden != null ? String(Math.ceil(opt.dauerSekunden / 60)) : "";
  const beginn =
    opt.beginn ?? new Date(Date.now() - (opt.dauerSekunden != null ? opt.dauerSekunden * 1000 : 0));
  return {
    richtung: opt.richtung ?? "ausgehend",
    ergebnis: "erreicht",
    partnerAuswahl: opt.partner?.ansprechpartnerId ?? (opt.partner?.name ? ANDERE_PERSON : ""),
    partnerName: opt.partner?.name ?? "",
    partnerNummer: opt.partner?.nummer ?? "",
    beginn: toLocalInputValue(beginn),
    dauerMinuten: dauerMin,
    notiz: "",
    rueckrufAn: false,
    rueckrufAm: toLocalInputValue(naechsterWerktag9()),
    arbeitszeit: false,
    vorgangId: opt.vorgangId ?? "",
  };
}

/** Nummer für tel:-Links: nur Ziffern, + und führende Schreibweise; Leerzeichen/Klammern/Bindestriche stören manche Dialer. */
export function telefonHref(nummer: string): string {
  return `tel:${nummer.replace(/[^\d+]/g, "")}`;
}
