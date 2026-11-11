import { useId, type ReactNode } from "react";

export const FELD_KLASSE = "btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label";
/**
 * Anlegen-Button ("+ Neuer X"): die eine gefüllte Primäraktion einer Liste/Ansicht (wie "Neuer Vorgang" im Feed),
 * damit sie sich von sekundären Buttons (Export, Import, Filter, Ansichtswechsel -- `btn-ap`) abhebt.
 * Feld-App-Mobil und Office-Desktop nutzen bewusst dieselbe Klasse: `.btn-ap-primary` bringt die Höhe je
 * Kontext mit, `btn-touch` hält die Tippfläche mobil bei 44 px.
 */
export const NEU_BUTTON_KLASSE = "btn-touch btn-ap-primary px-4";

export interface FeldProps {
  id: string;
  "aria-invalid": boolean;
  "aria-describedby"?: string;
}

/** Beschriftetes Formularfeld mit Pflichtstern und Feldfehler; das Eingabeelement bekommt id/aria über Render-Prop. */
export function Feld({
  label,
  pflicht = false,
  fehler,
  children,
}: {
  label: string;
  pflicht?: boolean;
  fehler?: string | null;
  children: (props: FeldProps) => ReactNode;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-label">
        {label}
        {pflicht && <span aria-hidden="true" className="text-st-fehlt"> *</span>}
      </label>
      {children({ id, "aria-invalid": !!fehler, "aria-describedby": fehler ? `${id}-fehler` : undefined })}
      {fehler && (
        <p id={`${id}-fehler`} role="alert" className="mt-1 text-xs text-st-fehlt">
          {fehler}
        </p>
      )}
    </div>
  );
}
