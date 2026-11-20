/** Rechnungsempfänger; bei einem verwalteten Kunden (WEG) dahinter grau "c/o <Verwalter>". */
export function EmpfaengerMitCo({ name, verwaltetVonName }: { name: string; verwaltetVonName?: string | null }) {
  return (
    <>
      {name}
      {verwaltetVonName && <span className="font-normal text-label2"> c/o {verwaltetVonName}</span>}
    </>
  );
}
