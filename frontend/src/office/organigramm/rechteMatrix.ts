import type { RechteScope } from "../../types";
import type {
  HerkunftEintrag,
  PositionDetail,
  RechtOverride,
  RechtOverrideIn,
  RechteRegistry,
} from "../../types/organigramm";

// Reine Logik der Rechte-Matrix (Bereich x Aktion). Alles Wissen ueber gueltige
// Bereiche/Aktionen/Scopes stammt aus der Registry (GET /api/rechte/registry).

export type ZellenZustand =
  | { modus: "vorlage" }
  | { modus: "erlaubt"; scope: RechteScope }
  | { modus: "verweigert" };

export const SCOPE_RANG: Record<RechteScope, number> = { eigene: 0, team: 1, teilbaum: 2, bereich: 3, mandant: 4 };

export function schluessel(bereich: string, aktion: string): string {
  return `${bereich}.${aktion}`;
}

/** Spalten der Matrix: Vereinigung aller Aktionen in Registry-Reihenfolge (Basisaktionen zuerst). */
export function aktionsSpalten(registry: RechteRegistry): string[] {
  const gesehen = new Set<string>();
  for (const b of registry.bereiche) for (const a of b.aktionen) gesehen.add(a);
  return [...gesehen];
}

export function bereichKennt(registry: RechteRegistry, bereich: string, aktion: string): boolean {
  return registry.bereiche.find((b) => b.key === bereich)?.aktionen.includes(aktion) ?? false;
}

/** Waehlbare Scopes einer Zelle: nur die, die die Registry fuer den Bereich ausweist. */
export function scopeOptionen(registry: RechteRegistry, bereich: string): RechteScope[] {
  return registry.bereiche.find((b) => b.key === bereich)?.scopes ?? [];
}

export function zustaendeAusOverrides(overrides: RechtOverride[]): Map<string, ZellenZustand> {
  const karte = new Map<string, ZellenZustand>();
  for (const o of overrides) {
    karte.set(
      schluessel(o.bereich, o.aktion),
      o.wirkung === "verweigern" ? { modus: "verweigert" } : { modus: "erlaubt", scope: o.scope ?? "mandant" },
    );
  }
  return karte;
}

/**
 * Body fuer PUT /positionen/{id}/rechte. Zellen "aus Vorlage" erzeugen keinen Eintrag;
 * Kombinationen, die die Registry nicht kennt, werden verworfen (das Backend wuerde 422 liefern).
 */
export function overridesAusZustaenden(
  zustaende: ReadonlyMap<string, ZellenZustand>,
  registry: RechteRegistry,
): RechtOverrideIn[] {
  const ergebnis: RechtOverrideIn[] = [];
  for (const b of registry.bereiche) {
    for (const aktion of b.aktionen) {
      const z = zustaende.get(schluessel(b.key, aktion));
      if (!z || z.modus === "vorlage") continue;
      if (z.modus === "verweigert") {
        ergebnis.push({ bereich: b.key, aktion, wirkung: "verweigern" });
      } else if (b.scopes.includes(z.scope)) {
        ergebnis.push({ bereich: b.key, aktion, wirkung: "erlauben", scope: z.scope });
      }
    }
  }
  return ergebnis;
}

/** Scope je Zelle laut Typ-Vorlage (null = Vorlage erlaubt es nicht), abgeleitet aus Effektiv + Overrides + Diff. */
export function vorlagenScopes(detail: Pick<PositionDetail, "effektive_rechte" | "overrides" | "diff_zur_vorlage">): Map<string, RechteScope | null> {
  const karte = new Map<string, RechteScope | null>();
  const mitOverride = new Set(detail.overrides.map((o) => schluessel(o.bereich, o.aktion)));
  for (const e of detail.effektive_rechte) {
    const key = schluessel(e.bereich, e.aktion);
    // Ohne Override ist das Effektive die Vorlage; mit Override sagt der Diff, was die Vorlage hatte
    // (kein Diff-Eintrag = Override aendert nichts, Vorlage = Effektiv).
    if (!mitOverride.has(key)) karte.set(key, e.scope);
  }
  for (const key of mitOverride) {
    const diff = detail.diff_zur_vorlage.find((d) => schluessel(d.bereich, d.aktion) === key);
    if (diff) karte.set(key, diff.typ_scope);
    else karte.set(key, detail.effektive_rechte.find((e) => schluessel(e.bereich, e.aktion) === key)?.scope ?? null);
  }
  return karte;
}

/** Der Backend-Engine folgend: ein Override kann den Scope der Vorlage nur erweitern, nie verengen. */
export function wirksamerScope(z: ZellenZustand, vorlage: RechteScope | null): RechteScope | null {
  if (z.modus === "verweigert") return null;
  if (z.modus === "vorlage") return vorlage;
  return vorlage && SCOPE_RANG[vorlage] > SCOPE_RANG[z.scope] ? vorlage : z.scope;
}

export type ZellenArt = "vorlage_erlaubt" | "vorlage_nein" | "zusaetzlich" | "verweigert";

export function zellenArt(z: ZellenZustand, vorlage: RechteScope | null): ZellenArt {
  if (z.modus === "verweigert") return "verweigert";
  if (z.modus === "erlaubt") return "zusaetzlich";
  return vorlage ? "vorlage_erlaubt" : "vorlage_nein";
}

export const ZELLEN_ART_LABEL: Record<ZellenArt, string> = {
  vorlage_erlaubt: "Aus Vorlage",
  vorlage_nein: "Nicht erlaubt",
  zusaetzlich: "Zusätzlich erlaubt",
  verweigert: "Verweigert",
};

/** Select-Wert <-> Zustand */
export function zustandZuWert(z: ZellenZustand): string {
  return z.modus === "erlaubt" ? `erlauben:${z.scope}` : z.modus === "verweigert" ? "verweigern" : "vorlage";
}

export function wertZuZustand(wert: string): ZellenZustand {
  if (wert === "verweigern") return { modus: "verweigert" };
  if (wert.startsWith("erlauben:")) return { modus: "erlaubt", scope: wert.slice("erlauben:".length) as RechteScope };
  return { modus: "vorlage" };
}

export function zustaendeGleich(a: ReadonlyMap<string, ZellenZustand>, b: ReadonlyMap<string, ZellenZustand>): boolean {
  const norm = (m: ReadonlyMap<string, ZellenZustand>) =>
    [...m.entries()]
      .filter(([, z]) => z.modus !== "vorlage")
      .map(([k, z]) => `${k}=${zustandZuWert(z)}`)
      .sort()
      .join("|");
  return norm(a) === norm(b);
}

export interface HerkunftAufloeser {
  accountTyp?: (id: string) => string | undefined;
  position?: (id: string) => string | undefined;
}

/** Textuelle Herkunft eines effektiven Rechts fuer Tooltip/Popover. */
export function herkunftTexte(
  herkunft: HerkunftEintrag[],
  aufloeser: HerkunftAufloeser = {},
): string[] {
  return herkunft.map((h) => {
    const position = h.position_id ? aufloeser.position?.(h.position_id) : undefined;
    const ort = position ? ` an „${position}“` : "";
    switch (h.art) {
      case "account_typ": {
        const typ = h.account_typ_id ? aufloeser.accountTyp?.(h.account_typ_id) : undefined;
        return `${typ ? `Account-Typ „${typ}“` : "Account-Typ"}${ort ? ` (Position${ort})` : ""}`;
      }
      case "position_override":
        return `${h.wirkung === "verweigern" ? "Verweigert" : "Zusätzlich erlaubt"} (Override${ort || " an der Position"})`;
      case "user_override":
        return `${h.wirkung === "verweigern" ? "Verweigert" : "Zusätzlich erlaubt"} (Override am Nutzer)`;
      default:
        return h.art;
    }
  });
}
