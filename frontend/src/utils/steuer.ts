import type { RechnungPosition, RechnungSteuerFelder, RechnungSteuerGruppe } from "../types";
import { formatIsoTag, tageZwischen } from "./format";

/** Auswahl der Steuer je Position in der UI. Eine Option bündelt, was die API
 * als {kategorie, satz, grund, grund_text} kennt. */
export type SteuerOption = "s19" | "s7" | "z_pv" | "ae_13b" | "e_befreit";

export const STEUER_OPTIONEN: { wert: SteuerOption; label: string; kurz: string }[] = [
  { wert: "s19", label: "19 %", kurz: "19 %" },
  { wert: "s7", label: "7 %", kurz: "7 %" },
  { wert: "z_pv", label: "0 % – Photovoltaik (§ 12 Abs. 3 UStG)", kurz: "0 % PV" },
  { wert: "ae_13b", label: "Reverse Charge (§ 13b UStG)", kurz: "Reverse Charge" },
  { wert: "e_befreit", label: "Steuerfrei (Begründung angeben)", kurz: "Steuerfrei" },
];

export const STEUER_TEXT_MIN = 3;
export const STEUER_TEXT_MAX = 200;

export type SteuerFelder = RechnungSteuerFelder;

export interface SteuerEingabe {
  option: SteuerOption;
  text: string;
}

type PositionSteuerFelder = Pick<
  RechnungPosition,
  "steuer_kategorie" | "steuer_satz" | "steuer_grund" | "steuer_grund_text"
>;

export function steuerOptionLabel(option: SteuerOption): string {
  return STEUER_OPTIONEN.find((o) => o.wert === option)?.label ?? option;
}

/** Option (+ Freitext bei "Steuerfrei") -> Felder für Create/PATCH. Der Text
 * wird getrimmt gesendet, wie ihn das Backend prüft. */
export function optionZuFelder(option: SteuerOption, text = ""): SteuerFelder {
  switch (option) {
    case "s19":
      return { steuer_kategorie: "S", steuer_satz: "19.00", steuer_grund: null, steuer_grund_text: null };
    case "s7":
      return { steuer_kategorie: "S", steuer_satz: "7.00", steuer_grund: null, steuer_grund_text: null };
    case "z_pv":
      return { steuer_kategorie: "Z", steuer_satz: "0.00", steuer_grund: "pv_12_3", steuer_grund_text: null };
    case "ae_13b":
      return {
        steuer_kategorie: "AE",
        steuer_satz: "0.00",
        steuer_grund: "reverse_charge_13b",
        steuer_grund_text: null,
      };
    case "e_befreit":
      return {
        steuer_kategorie: "E",
        steuer_satz: "0.00",
        steuer_grund: "sonstige_befreiung",
        steuer_grund_text: text.trim(),
      };
  }
}

/** Gespeicherte Position -> Eingabe. null bei Kleinunternehmer-Positionen
 * (E mit kleinunternehmer_19): die gibt es nur serverseitig erzwungen und
 * nicht als wählbare Option. */
export function positionZuEingabe(p: PositionSteuerFelder): SteuerEingabe | null {
  const satz = Number(p.steuer_satz ?? "19");
  switch (p.steuer_kategorie ?? "S") {
    case "S":
      return { option: satz === 7 ? "s7" : "s19", text: "" };
    case "Z":
      return { option: "z_pv", text: "" };
    case "AE":
      return { option: "ae_13b", text: "" };
    case "E":
      if (p.steuer_grund === "kleinunternehmer_19") return null;
      return { option: "e_befreit", text: p.steuer_grund_text ?? "" };
  }
}

/** Vorbelegung aus dem Beleg-Satz. Beleg 0 % ist Altverhalten ohne Grund und
 * kommt deshalb als "Steuerfrei" mit leerer Begründung, die der Nutzer
 * ausfüllen muss (das Backend verlangt sie spätestens beim Versand). */
export function vorbelegung(belegMwstSatz: string | number | null | undefined): SteuerEingabe {
  const satz = Number(belegMwstSatz ?? 19);
  if (satz === 7) return { option: "s7", text: "" };
  if (satz === 0) return { option: "e_befreit", text: "" };
  return { option: "s19", text: "" };
}

/** Fehlermeldung zur Eingabe oder null, wenn sie speicherbar ist. */
export function validiereSteuer(eingabe: SteuerEingabe): string | null {
  if (eingabe.option !== "e_befreit") return null;
  const laenge = eingabe.text.trim().length;
  if (laenge < STEUER_TEXT_MIN) return `Begründung angeben (mindestens ${STEUER_TEXT_MIN} Zeichen).`;
  if (laenge > STEUER_TEXT_MAX) return `Begründung ist zu lang (höchstens ${STEUER_TEXT_MAX} Zeichen).`;
  return null;
}

/** Kurztext für das schreibgeschützte Badge einer Position. */
export function steuerKurzlabel(p: PositionSteuerFelder): string {
  if (p.steuer_grund === "kleinunternehmer_19") return "§ 19 UStG";
  const eingabe = positionZuEingabe(p);
  if (!eingabe) return "Steuerfrei";
  return STEUER_OPTIONEN.find((o) => o.wert === eingabe.option)?.kurz ?? "";
}

/** Zeilenbeschriftung einer Steuergruppe im Summenblock. */
export function steuergruppeLabel(g: Pick<RechnungSteuerGruppe, "kategorie" | "satz">): string {
  switch (g.kategorie) {
    case "S":
      return `${Number(g.satz).toLocaleString("de-DE", { maximumFractionDigits: 2 })} % USt`;
    case "Z":
      return "0 % – Photovoltaik (§ 12 Abs. 3 UStG)";
    case "AE":
      return "Reverse Charge (§ 13b UStG)";
    case "E":
      return "Steuerfrei";
  }
}

/** Ob der Summenblock je Gruppe aufgeschlüsselt werden muss: bei mehreren
 * Gruppen oder wenn eine Gruppe einen Hinweis trägt; sonst bleibt es bei
 * Netto/Brutto. */
export function zeigeSteuergruppen(gruppen: RechnungSteuerGruppe[] | undefined): boolean {
  if (!gruppen) return false;
  return gruppen.length > 1 || gruppen.some((g) => !!g.hinweis || (g.hinweise?.length ?? 0) > 0);
}

// --- § 13b -------------------------------------------------------------------

export interface Kunde13b {
  ust_idnr?: string | null;
  ust_13b_nachweis_bis?: string | null;
}

/** Spiegel von steuer_service.pruefe_13b_voraussetzungen: Das Backend bleibt
 * maßgeblich, dies ist nur die Vorwarnung vor dem Speichern. Daten sind
 * ISO-Tage (YYYY-MM-DD), der Vergleich läuft deshalb als Zeichenkette und ohne
 * Zeitzonen. Ablauf = Leistungsdatum gilt noch als gültig. Ohne Leistungsdatum
 * zählt `heute`. */
export function pruefe13bVoraussetzungen(
  kunde: Kunde13b | null | undefined,
  leistungsdatum: string | null | undefined,
  heute: string,
): string[] {
  const probleme: string[] = [];
  if (!(kunde?.ust_idnr ?? "").trim()) {
    probleme.push("Beim Kunden fehlt die USt-IdNr.");
  }
  const bezugstag = leistungsdatum || heute;
  const nachweis = kunde?.ust_13b_nachweis_bis;
  if (!nachweis) {
    probleme.push("Beim Kunden fehlt das Ablaufdatum der Bescheinigung USt 1 TG.");
  } else if (nachweis < bezugstag) {
    const bezug = leistungsdatum ? `Leistungsdatum ${formatIsoTag(leistungsdatum)}` : `heute, ${formatIsoTag(heute)}`;
    probleme.push(`Die Bescheinigung USt 1 TG ist am ${formatIsoTag(nachweis)} abgelaufen (${bezug}).`);
  }
  return probleme;
}

export type NachweisArt = "fehlt" | "gueltig" | "laeuft_ab" | "abgelaufen";

export const NACHWEIS_WARNFRIST_TAGE = 30;

export interface NachweisStatus {
  art: NachweisArt;
  label: string;
}

/** Statuszeile zur Bescheinigung USt 1 TG im Kundenprofil. "Heute" ist der
 * letzte gültige Tag, "läuft ab" beginnt NACHWEIS_WARNFRIST_TAGE davor. */
export function nachweisStatus(bis: string | null | undefined, heute: string): NachweisStatus {
  if (!bis) return { art: "fehlt", label: "Kein Nachweis hinterlegt" };
  const tage = tageZwischen(heute, bis);
  if (tage < 0) return { art: "abgelaufen", label: `Abgelaufen am ${formatIsoTag(bis)}` };
  if (tage === 0) return { art: "laeuft_ab", label: "Läuft heute ab" };
  if (tage <= NACHWEIS_WARNFRIST_TAGE) {
    return { art: "laeuft_ab", label: `Läuft in ${tage} ${tage === 1 ? "Tag" : "Tagen"} ab` };
  }
  return { art: "gueltig", label: `Gültig bis ${formatIsoTag(bis)}` };
}

// --- Fehlertexte -------------------------------------------------------------

export interface ListenFehler {
  titel: string;
  punkte: string[];
}

/** Zerlegt die mehrzeilige Versand-Meldung "Titel:\n- Punkt 1\n- Punkt 2" des
 * Backends. Liefert null, wenn die Meldung keine Aufzählung enthält (dann
 * bleibt die einzeilige Anzeige). Getrennt wird nur an "\n- ". */
export function zerlegeListenFehler(meldung: string | null | undefined): ListenFehler | null {
  if (!meldung || !meldung.includes("\n- ")) return null;
  const [kopf, ...rest] = meldung.split("\n- ");
  const punkte = rest.map((p) => p.trim()).filter(Boolean);
  if (punkte.length === 0) return null;
  return { titel: kopf.trim().replace(/:$/, ""), punkte };
}

/** Meldung des DATEV-Exports, wenn für eine Steuerkategorie kein Erlöskonto
 * hinterlegt ist. */
export function istErloeskontoFehler(meldung: string | null | undefined): boolean {
  return !!meldung && meldung.includes("kein Erlöskonto hinterlegt");
}
