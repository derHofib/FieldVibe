import { useQuery } from "@tanstack/react-query";

import { eingangsrechnungenApi } from "../../api/endpoints";

/** Beleg einer Eingangsrechnung als eingebettete Vorschau (Entwurf-Bestätigung und Vollbild teilen sie). */
export function BelegVorschau({ id, iframeKlasse }: { id: string; iframeKlasse: string }) {
  const { data: belegUrl } = useQuery({
    queryKey: ["eingangsrechnung-beleg-url", id],
    queryFn: () => eingangsrechnungenApi.belegUrl(id),
  });
  return belegUrl?.url ? (
    <iframe title="Beleg" src={belegUrl.url} className={iframeKlasse} />
  ) : (
    <p className="p-4 text-sekundaer text-label2">Kein Beleg vorhanden.</p>
  );
}
