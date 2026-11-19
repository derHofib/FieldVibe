import type { MailAnbieter } from "../../types";

export const IONOS: MailAnbieter = {
  id: "ionos",
  name: "IONOS",
  kuerzel: "IO",
  farbe: "#003d8f",
  beschreibung: "eigene Domain",
  domains: [],
  imap_host: "imap.ionos.de",
  imap_port: 993,
  imap_verschluesselung: "ssl",
  smtp_host: "smtp.ionos.de",
  smtp_port: 587,
  smtp_verschluesselung: "starttls",
  hinweis: "Postfach-Passwort verwenden.",
  unterstuetzt: true,
};

export const STRATO: MailAnbieter = {
  ...IONOS,
  id: "strato",
  name: "STRATO",
  kuerzel: "ST",
  imap_host: "imap.strato.de",
  smtp_host: "smtp.strato.de",
  smtp_port: 465,
  smtp_verschluesselung: "ssl",
  hinweis: null,
};

export const GOOGLE: MailAnbieter = { ...IONOS, id: "google", name: "Gmail / Google", kuerzel: "G", hinweis: "App-Passwort nötig" };

export const MICROSOFT: MailAnbieter = {
  ...IONOS,
  id: "microsoft",
  name: "Microsoft 365 / Outlook",
  kuerzel: "M",
  imap_host: "",
  smtp_host: "",
  hinweis: null,
  unterstuetzt: false,
};
