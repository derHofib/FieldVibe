import type { Position, PositionTyp, PositionUpdate } from "../../types/organigramm";

// Formularzustand als Strings (Eingabefelder); Umrechnung in den PATCH-Body bewusst getrennt und testbar.
export interface StammdatenForm {
  titel: string;
  typ: PositionTyp;
  ebene: string;
  orgEinheitId: string;
  accountTypId: string;
  geplant: boolean;
  sollBesetzung: string;
  gueltigAb: string;
  gueltigBis: string;
  reihenfolge: string;
}

export function formAusPosition(p: Position): StammdatenForm {
  return {
    titel: p.titel,
    typ: p.typ,
    ebene: p.ebene === null || p.ebene === undefined ? "" : String(p.ebene),
    orgEinheitId: p.org_einheit?.id ?? "",
    accountTypId: p.account_typ?.id ?? "",
    geplant: p.geplant ?? false,
    sollBesetzung: String(p.soll_besetzung ?? 1),
    gueltigAb: p.gueltig_ab ?? "",
    gueltigBis: p.gueltig_bis ?? "",
    reihenfolge: String(p.reihenfolge ?? 0),
  };
}

function zahlOderNull(text: string): number | null {
  const t = text.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

/** Nur geaenderte Felder (PATCH); geleerte optionale Felder werden als null gesendet. */
export function updateAusFormular(alt: Position, form: StammdatenForm): PositionUpdate {
  const neu = formAusPosition(alt);
  const u: PositionUpdate = {};
  if (form.titel.trim() !== neu.titel) u.titel = form.titel.trim();
  if (form.typ !== neu.typ) u.typ = form.typ;
  if (form.ebene !== neu.ebene) u.ebene = zahlOderNull(form.ebene);
  if (form.orgEinheitId !== neu.orgEinheitId) u.org_einheit_id = form.orgEinheitId || null;
  if (form.accountTypId !== neu.accountTypId) u.account_typ_id = form.accountTypId || null;
  if (form.geplant !== neu.geplant) u.geplant = form.geplant;
  if (form.sollBesetzung !== neu.sollBesetzung) u.soll_besetzung = Math.max(0, zahlOderNull(form.sollBesetzung) ?? 0);
  if (form.gueltigAb !== neu.gueltigAb) u.gueltig_ab = form.gueltigAb || null;
  if (form.gueltigBis !== neu.gueltigBis) u.gueltig_bis = form.gueltigBis || null;
  if (form.reihenfolge !== neu.reihenfolge) u.reihenfolge = zahlOderNull(form.reihenfolge) ?? 0;
  return u;
}
