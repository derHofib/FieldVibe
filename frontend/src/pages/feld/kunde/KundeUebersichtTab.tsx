import type { KundeProfil } from "../../../types";
import { Stammdaten, TechnikerZuweisung } from "./KundeUebersicht";

export function KundeUebersichtTab({
  id,
  profil,
  kannVerwalten,
}: {
  id: string | undefined;
  profil: KundeProfil;
  kannVerwalten: boolean;
}) {
  return (
    <>
    <Stammdaten
      kundeId={id!}
      adresse={profil.adresse}
      notiz={profil.notiz}
      typ={profil.typ}
      ustIdnr={profil.ust_idnr}
      ust13bBis={profil.ust_13b_nachweis_bis ?? null}
      leitwegId={profil.leitweg_id ?? null}
      eRechnungFormat={profil.e_rechnung_format ?? null}
      debitorenkonto={profil.debitorenkonto ?? null}
      kannVerwalten={kannVerwalten}
    />

    {kannVerwalten && <TechnikerZuweisung kundeId={id!} zugewiesen={profil.techniker} />}
    </>
  );
}
