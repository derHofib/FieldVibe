import { useId } from "react";

import { Select } from "../../components/apple/Select";
import type { MailAnbieter, MailVerschluesselung } from "../../types";

export interface ServerWerte {
  imap_host: string;
  imap_port: number;
  imap_verschluesselung: MailVerschluesselung;
  imap_benutzername: string;
  smtp_host: string;
  smtp_port: number;
  smtp_verschluesselung: MailVerschluesselung;
  smtp_benutzername: string;
}

export const LEERE_SERVERWERTE: ServerWerte = {
  imap_host: "",
  imap_port: 993,
  imap_verschluesselung: "ssl",
  imap_benutzername: "",
  smtp_host: "",
  smtp_port: 587,
  smtp_verschluesselung: "starttls",
  smtp_benutzername: "",
};

/** Vorgabewerte eines Anbieters; der Benutzername ist bei allen Anbietern die E-Mail-Adresse. */
export function werteAusAnbieter(anbieter: MailAnbieter, emailAdresse: string): ServerWerte {
  return {
    imap_host: anbieter.imap_host,
    imap_port: anbieter.imap_port,
    imap_verschluesselung: anbieter.imap_verschluesselung,
    imap_benutzername: emailAdresse,
    smtp_host: anbieter.smtp_host,
    smtp_port: anbieter.smtp_port,
    smtp_verschluesselung: anbieter.smtp_verschluesselung,
    smtp_benutzername: emailAdresse,
  };
}

const VERSCHLUESSELUNG_OPTIONEN: { wert: MailVerschluesselung; label: string }[] = [
  { wert: "ssl", label: "SSL/TLS" },
  { wert: "starttls", label: "STARTTLS" },
];

// "Keine" (Klartext-Login) wird nur angezeigt, solange der bestehende Wert sie
// noch hat -- das Backend lehnt sie beim Speichern ab.
function optionenFuer(aktuell: MailVerschluesselung) {
  return aktuell === "keine"
    ? [...VERSCHLUESSELUNG_OPTIONEN, { wert: "keine" as const, label: "Keine (unsicher)" }]
    : VERSCHLUESSELUNG_OPTIONEN;
}

function Geaendert({ zeigen }: { zeigen: boolean }) {
  if (!zeigen) return null;
  return (
    <span className="ml-1.5 rounded-full bg-tintbg px-1.5 py-0.5 text-meta font-semibold text-tint-text">geändert</span>
  );
}

function Feld({ label, geaendert, children }: { label: string; geaendert: boolean; children: (id: string) => React.ReactNode }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sekundaer font-medium text-label2">
        {label}
        <Geaendert zeigen={geaendert} />
      </label>
      {children(id)}
    </div>
  );
}

interface Props {
  werte: ServerWerte;
  onChange: (werte: ServerWerte) => void;
  /** Wenn gesetzt, werden abweichende Felder als „geändert“ markiert. */
  vorgabe?: ServerWerte | null;
}

/** IMAP-/SMTP-Felder als kontrollierte Komponente (Server, Port,
 * Verschlüsselung, Benutzername). Kennt weder Speichern noch Testen. */
export function ServerEinstellungen({ werte, onChange, vorgabe }: Props) {
  const setze = <K extends keyof ServerWerte>(feld: K, wert: ServerWerte[K]) => onChange({ ...werte, [feld]: wert });
  const abw = (feld: keyof ServerWerte) => !!vorgabe && vorgabe[feld] !== werte[feld];

  const abschnitt = (art: "imap" | "smtp", titel: string, platzhalter: string) => {
    const f = (s: string) => `${art}_${s}` as keyof ServerWerte;
    const verschluesselung = werte[f("verschluesselung")] as MailVerschluesselung;
    return (
      <div className="space-y-3">
        <p className="text-sekundaer font-semibold text-label">{titel}</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Feld label="Server" geaendert={abw(f("host"))}>
            {(id) => (
              <input
                id={id}
                className="field-ap"
                value={werte[f("host")] as string}
                placeholder={platzhalter}
                onChange={(e) => setze(f("host"), e.target.value as never)}
              />
            )}
          </Feld>
          <Feld label="Port" geaendert={abw(f("port"))}>
            {(id) => (
              <input
                id={id}
                type="number"
                className="field-ap"
                value={werte[f("port")] as number}
                onChange={(e) => setze(f("port"), Number(e.target.value) as never)}
              />
            )}
          </Feld>
          <Feld label="Verschlüsselung" geaendert={abw(f("verschluesselung"))}>
            {(id) => (
              <>
                <Select
                  id={id}
                  value={verschluesselung}
                  onChange={(e) => setze(f("verschluesselung"), e.target.value as never)}
                >
                  {optionenFuer(verschluesselung).map((o) => (
                    <option key={o.wert} value={o.wert}>
                      {o.label}
                    </option>
                  ))}
                </Select>
                {verschluesselung === "keine" && (
                  <span className="mt-1 block text-meta text-st-arbeit">
                    Unverschlüsselt nicht mehr erlaubt – bitte auf SSL/TLS oder STARTTLS umstellen.
                  </span>
                )}
              </>
            )}
          </Feld>
          <Feld label="Benutzername" geaendert={abw(f("benutzername"))}>
            {(id) => (
              <input
                id={id}
                className="field-ap"
                value={werte[f("benutzername")] as string}
                onChange={(e) => setze(f("benutzername"), e.target.value as never)}
              />
            )}
          </Feld>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-5">
      {abschnitt("imap", "Posteingang (IMAP)", "imap.anbieter.de")}
      {abschnitt("smtp", "Postausgang (SMTP)", "smtp.anbieter.de")}
    </div>
  );
}
