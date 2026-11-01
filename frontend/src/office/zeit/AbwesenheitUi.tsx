import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";

import { StatusPille } from "../../components/apple/StatusPille";
import type { Abwesenheit, Urlaubskonto } from "../../types";
import {
  ABWESENHEIT_ART_LABEL,
  ABWESENHEIT_STATUS_LABEL,
  abwesenheitStatusZuToken,
  formatTage,
  formatTageMitEinheit,
  formatZeitraum,
  kontoHinweis,
  resturlaubHinweis,
} from "../../utils/abwesenheit";
import { KennzahlKarte } from "../OfficeUi";

export function AbwesenheitStatusPille({ status }: { status: Abwesenheit["status"] }) {
  return <StatusPille status={abwesenheitStatusZuToken(status)} label={ABWESENHEIT_STATUS_LABEL[status]} />;
}

/** Eine Zeile mit Art, Zeitraum, Tagen und Status; Aktionen/Zusatz kommen vom Aufrufer. */
export function AbwesenheitZeile({
  a,
  mitName = false,
  children,
}: {
  a: Abwesenheit;
  mitName?: boolean;
  children?: ReactNode;
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
      {mitName && <span className="font-semibold text-label">{a.user_name}</span>}
      <span className="font-medium text-label">{ABWESENHEIT_ART_LABEL[a.art]}</span>
      <span className="tabular-nums text-label2">{formatZeitraum(a)}</span>
      <span className="tabular-nums text-label">{formatTageMitEinheit(a.tage)}</span>
      <AbwesenheitStatusPille status={a.status} />
      {a.notiz && <span className="min-w-0 max-w-xs truncate text-label2">„{a.notiz}“</span>}
      {a.antwort && <span className="min-w-0 max-w-xs truncate text-label2">Antwort: {a.antwort}</span>}
      <span className="ml-auto flex items-center gap-2">{children}</span>
    </li>
  );
}

/** Urlaubskonto als Kennzahl-Kacheln; negatives "verbleibend" als Warnung. */
export function UrlaubskontoKacheln({ konto }: { konto: Urlaubskonto }) {
  const hinweis = kontoHinweis(konto);
  const rest = resturlaubHinweis(konto);
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <KennzahlKarte label="Anspruch" wert={formatTage(konto.anspruch)} zusatz="Tage" />
        <KennzahlKarte label="Resturlaub" wert={formatTage(konto.resturlaub)} zusatz={rest ?? "Tage"} />
        <KennzahlKarte label="Genommen" wert={formatTage(konto.genommen)} zusatz="Tage, genehmigt" />
        <KennzahlKarte label="Beantragt" wert={formatTage(konto.beantragt)} zusatz="Tage, offen" />
        <KennzahlKarte
          label="Verbleibend"
          wert={formatTage(konto.verbleibend)}
          wertKlasse={hinweis.ueberzogen ? "text-st-fehlt" : "text-label"}
          zusatz={hinweis.ueberzogen ? "überzogen" : "Tage"}
          ton={hinweis.ueberzogen ? "warnung" : "neutral"}
        />
      </div>
      {hinweis.text && (
        <p role="alert" className="flex items-center gap-1.5 text-sm font-medium text-st-fehlt">
          <AlertTriangle size={15} strokeWidth={2} aria-hidden="true" />
          {hinweis.text}
        </p>
      )}
    </div>
  );
}
