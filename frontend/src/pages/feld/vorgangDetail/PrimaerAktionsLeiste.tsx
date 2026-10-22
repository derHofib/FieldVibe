

interface PrimaerAktionsLeisteProps {
  ansicht: "voll" | "zeit" | "verlauf" | "positionen";
  layout: "kompakt" | "dicht";
  primaerAktion: { label: string; onClick: () => void; disabled?: boolean } | null;
}

/** Klebende Primäraktion am unteren Rand der kompakten Hauptseite. */
export function PrimaerAktionsLeiste({ ansicht, layout, primaerAktion }: PrimaerAktionsLeisteProps) {
  return (
    <>
      {layout !== "dicht" && ansicht === "voll" && primaerAktion && (
        <div className="fixed inset-x-0 z-30 flex justify-center px-3" style={{ bottom: "var(--klebe-abstand)" }}>
          <button
            type="button"
            onClick={primaerAktion.onClick}
            disabled={primaerAktion.disabled}
            className="btn-touch btn-ap-primary w-full max-w-md disabled:opacity-50"
          >
            {primaerAktion.label}
          </button>
        </div>
      )}
    </>
  );
}
