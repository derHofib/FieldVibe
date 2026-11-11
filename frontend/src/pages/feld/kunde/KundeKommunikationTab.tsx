import { kundenApi } from "../../../api/endpoints";
import { AnsprechpartnerVerwaltung } from "../../../components/AnsprechpartnerVerwaltung";
import { EmailSection } from "../../../components/EmailSection";
import type { CurrentUser, KundeProfil } from "../../../types";
import { istModulAktiv } from "../../../utils/module";
import { KundenPortalLinkUndLogo, PortalZugaengeVerwaltung } from "./KundePortalZugaenge";
import type { QueryClient } from "@tanstack/react-query";

export function KundeKommunikationTab({
  profil,
  kannVerwalten,
  id,
  queryClient,
  currentUser,
}: {
  profil: KundeProfil;
  kannVerwalten: boolean;
  id: string | undefined;
  queryClient: QueryClient;
  currentUser: CurrentUser | undefined;
}) {
  return (
    <>
    <AnsprechpartnerVerwaltung
      liste={profil.ansprechpartner}
      kannVerwalten={kannVerwalten}
      onSpeichern={async (naechsteListe) => {
        await kundenApi.update(id!, { ansprechpartner: naechsteListe });
        queryClient.invalidateQueries({ queryKey: ["kunde-profil", id] });
      }}
    />

    {kannVerwalten && (
      <EmailSection
        queryKey={["kunde-emails", id]}
        listEmails={() => kundenApi.emails(id!)}
        sendEmail={(body) =>
          kundenApi.sendEmail(id!, {
            empfaenger: body.empfaenger,
            betreff: body.betreff ?? "",
            inhalt: body.inhalt ?? "",
          })
        }
        defaultEmpfaenger={profil.ansprechpartner.find((a) => a.email)?.email ?? undefined}
      />
    )}

    {kannVerwalten && istModulAktiv(currentUser, "kundenportal") && (
      <>
        <KundenPortalLinkUndLogo kunde={profil} />
        <PortalZugaengeVerwaltung kundeId={id!} />
      </>
    )}
    </>
  );
}
