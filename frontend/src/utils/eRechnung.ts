// Empfang von E-Rechnungen (XRechnung/ZUGFeRD) im Rechnungseingang.

// Obergrenzen wie im Backend (e_rechnung_empfang_service): PDF 10 MB, XML 5 MB.
export const E_RECHNUNG_PDF_MAX_BYTES = 10 * 1024 * 1024;
export const E_RECHNUNG_XML_MAX_BYTES = 5 * 1024 * 1024;

const SYNTAX_LABEL: Record<string, string> = {
  cii: "XRechnung / ZUGFeRD (CII)",
  ubl: "XRechnung (UBL)",
};

/** Anzeigename der Syntax; null, wenn der Beleg keine E-Rechnung ist. */
export function eRechnungSyntaxLabel(syntax: string | null | undefined): string | null {
  if (!syntax) return null;
  return SYNTAX_LABEL[syntax] ?? "E-Rechnung";
}

/** import_hinweis (ein Hinweis je Zeile) als Liste; leere Zeilen entfallen. */
export function hinweisZeilen(hinweis: string | null | undefined): string[] {
  return (hinweis ?? "")
    .split("\n")
    .map((z) => z.trim())
    .filter((z) => z.length > 0);
}

/** Vorab-Prüfung der Datei im Browser; null = in Ordnung. Das Backend prüft
 * Inhalt und Größe verbindlich nochmals, das spart nur den Upload. */
export function pruefeERechnungDatei(datei: { name: string; size: number }): string | null {
  const name = datei.name.toLowerCase();
  const istXml = name.endsWith(".xml");
  const istPdf = name.endsWith(".pdf");
  if (!istXml && !istPdf) return "Bitte eine XML-Datei (XRechnung) oder ein PDF mit eingebetteter E-Rechnung (ZUGFeRD/Factur-X) wählen.";
  if (istXml && datei.size > E_RECHNUNG_XML_MAX_BYTES) return "Die XML-Datei ist zu groß (max. 5 MB).";
  if (istPdf && datei.size > E_RECHNUNG_PDF_MAX_BYTES) return "Die PDF-Datei ist zu groß (max. 10 MB).";
  return null;
}
