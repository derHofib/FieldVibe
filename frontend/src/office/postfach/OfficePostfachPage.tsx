import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { mailApi } from "../../api/endpoints";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import { SeitenKopf } from "../OfficeUi";
import { MailClient } from "./MailClient";
import { PostfachEinrichten } from "./PostfachEinrichten";

/** Orchestriert das Postfach: kein Konto -> Einrichten, sonst der
 * Drei-Flächen-Mailclient für das aktive Konto. Mehrere Postfächer werden
 * nicht gemischt angezeigt (ein Ordnerbaum pro Konto ist eindeutiger als ein
 * gemeinsamer Posteingang mit rätselhafter Herkunft je Nachricht); der
 * Kontoumschalter sitzt in der Ordnerspalte, die Auswahl steht in ?konto=. */
export function OfficePostfachPage() {
  const { data: accounts, isLoading, error, refetch } = useQuery({
    queryKey: ["mail-accounts"],
    queryFn: () => mailApi.accounts.list(),
  });
  const [params, setParams] = useSearchParams();
  const aktivesKonto = accounts?.find((a) => a.id === params.get("konto")) ?? accounts?.[0];

  if (isLoading) {
    return (
      <div>
        <SeitenKopf titel="Postfach" />
        <SkeletonList count={4} />
      </div>
    );
  }

  // Fehler darf nicht als "kein Konto" durchfallen, sonst erscheint das Einrichten.
  if (error) {
    return (
      <div>
        <SeitenKopf titel="Postfach" />
        <FehlerZustand fehler={error} was="Die Postfächer" onErneut={() => void refetch()} />
      </div>
    );
  }

  if (!accounts || accounts.length === 0 || !aktivesKonto) {
    return (
      <div>
        <SeitenKopf titel="Postfach" />
        <PostfachEinrichten layout="office" onFertig={() => void refetch()} />
      </div>
    );
  }

  return (
    <div>
      <SeitenKopf titel="Postfach" />
      <MailClient
        account={aktivesKonto}
        accounts={accounts}
        onKontoWechsel={(id) => setParams({ konto: id }, { replace: true })}
      />
    </div>
  );
}
