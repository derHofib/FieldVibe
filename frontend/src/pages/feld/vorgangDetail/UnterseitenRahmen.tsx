import { useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import type { Kunde, Vorgang } from "../../../types";

interface UnterseitenRahmenProps {
  vorgang: Vorgang;
  kunde: Kunde | undefined;
  id: string | undefined;
  children: ReactNode;
}

/** Gemeinsamer Kopf der Unterseiten /vorgaenge/:id/zeit, /verlauf und /positionen (kompaktes Layout). */
export function UnterseitenRahmen({ vorgang, kunde, id, children }: UnterseitenRahmenProps) {
  const navigate = useNavigate();
  return (
    <div className="space-y-4">
      <button onClick={() => navigate(`/vorgaenge/${id}`)} className="text-sm text-label2">
        ← Zurück zum Vorgang
      </button>
      <div className="card-ap p-3">
        <div className="text-xs text-label2">{vorgang.vorgangsnummer}</div>
        <h1 className="font-heading text-base font-semibold text-label">{vorgang.titel}</h1>
        {kunde && <p className="mt-0.5 text-xs text-label2">{kunde.name}</p>}
      </div>
      {children}
    </div>
  );
}
