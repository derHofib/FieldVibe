import { LogOut } from "lucide-react";

import { AbschnittskopfB } from "../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListValueRow } from "../components/apple/GroupedList";
import { usePartnerAuth } from "../context/PartnerAuthContext";

export function PartnerProfilPage() {
  const { currentPartner, logout } = usePartnerAuth();

  return (
    <main className="mx-auto max-w-2xl px-3 py-4 pb-10">
      <h1 className="ap-heading px-5 pt-2 pb-1 text-[26px] font-bold text-label">Profil</h1>

      <AbschnittskopfB titel="Zugang" />
      <div className="px-4">
        <GroupedList>
          <GroupedListValueRow label="Name" wert={currentPartner?.name} />
          <GroupedListValueRow label="E-Mail" wert={<span className="break-all">{currentPartner?.email}</span>} />
          <GroupedListValueRow label="Firma" wert={currentPartner?.partner_name} last />
        </GroupedList>
      </div>

      <div className="px-4 pt-6">
        <button onClick={logout} className="btn-ap-capsule btn-ap-capsule-secondary w-full">
          <LogOut size={16} aria-hidden="true" /> Abmelden
        </button>
      </div>
    </main>
  );
}
