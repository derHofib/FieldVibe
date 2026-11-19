import { Mail, Phone, PhoneIncoming, PhoneMissed, PhoneOutgoing } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "../../../components/EmptyState";
import { FehlerZustand } from "../../../components/FehlerZustand";
import { GroupedList, GroupedListRow } from "../../../components/apple/GroupedList";
import { StatusPille } from "../../../components/apple/StatusPille";
import { IconBadge } from "../../../components/IconBadge";
import { SkeletonList } from "../../../components/Skeleton";
import { useTelefonat } from "../../../components/telefonat/TelefonatProvider";
import { NEU_BUTTON_KLASSE } from "../../../components/FormularFeld";
import { useAuth } from "../../../context/AuthContext";
import { useKontaktverlauf } from "../../../hooks/useTelefonate";
import type { Ansprechpartner, KontaktverlaufEintrag, Telefonat, Vorgang } from "../../../types";
import { istAdminRolle } from "../../../utils/rollen";
import { TELEFONAT_ERGEBNIS_LABEL, TELEFONAT_RICHTUNG_LABEL, formatDauer } from "../../../utils/telefonat";

const ZEIT = { timeZone: "Europe/Berlin", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" } as const;

function VorgangChip({ id, nummer }: { id: string | null; nummer: string | null }) {
  const klasse = "inline-flex items-center rounded-[var(--radius-ap-pill)] bg-fill px-2 py-0.5 text-meta font-semibold";
  if (!id) return <span className={`${klasse} text-label2`}>ohne Vorgang</span>;
  return (
    <Link to={`/vorgaenge/${id}`} onClick={(e) => e.stopPropagation()} className={`${klasse} text-tint-text hover:underline`}>
      {nummer ?? "Vorgang"}
    </Link>
  );
}

function TelefonatZeile({ t, letzte, onOeffnen }: { t: Telefonat; letzte: boolean; onOeffnen?: () => void }) {
  const nichtErreicht = t.ergebnis !== "erreicht";
  const RichtungIcon = nichtErreicht ? PhoneMissed : t.richtung === "ausgehend" ? PhoneOutgoing : PhoneIncoming;
  const dauer = formatDauer(t.dauer_sekunden);
  const erledigt = !!t.rueckruf_erledigt_am;
  return (
    <GroupedListRow last={letzte} onClick={onOeffnen}>
      <IconBadge icon={Phone} tone="teal" size="sm" active={!nichtErreicht} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-1.5 text-zeile text-label">
          <RichtungIcon size={14} strokeWidth={2} className="shrink-0 text-label2" aria-label={TELEFONAT_RICHTUNG_LABEL[t.richtung]} role="img" />
          <span className="truncate font-medium">{t.partner_name}</span>
        </div>
        <div className="text-meta text-label2">
          {new Date(t.beginn).toLocaleString("de-DE", ZEIT)} · {TELEFONAT_ERGEBNIS_LABEL[t.ergebnis]}
          {dauer && !nichtErreicht && ` · ${dauer}`}
        </div>
        {t.notiz && <p className="mt-0.5 line-clamp-2 text-sekundaer text-label2">{t.notiz}</p>}
        {t.rueckruf_am && (
          <div className="mt-1">
            <StatusPille
              status={erledigt ? "erledigt" : "wartet"}
              label={erledigt ? "Rückruf erledigt" : `Rückruf ${new Date(t.rueckruf_am).toLocaleString("de-DE", { timeZone: "Europe/Berlin", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}`}
            />
          </div>
        )}
      </div>
      <VorgangChip id={t.vorgang_id} nummer={t.vorgang_nummer} />
    </GroupedListRow>
  );
}

function EmailZeile({ e, letzte }: { e: Extract<KontaktverlaufEintrag, { art: "email" }>["email"]; letzte: boolean }) {
  const zeit = e.gesendet_am ?? e.created_at;
  return (
    <GroupedListRow last={letzte}>
      <IconBadge icon={Mail} tone="sky" size="sm" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-zeile font-medium text-label">{e.betreff || "(ohne Betreff)"}</div>
        <div className="truncate text-meta text-label2">
          {zeit && `${new Date(zeit).toLocaleString("de-DE", ZEIT)} · `}an {e.empfaenger}
          {e.status === "fehler" && " · Fehler"}
        </div>
      </div>
      <VorgangChip id={e.vorgang_id} nummer={e.vorgang_nummer} />
    </GroupedListRow>
  );
}

/** Kontaktverlauf am Kunden (Tab "Kontakt"): Telefonate und E-Mails über alle Vorgänge hinweg, neueste oben. */
export function KundeKontaktverlauf({
  kundeId,
  ansprechpartner,
  vorgaenge,
}: {
  kundeId: string;
  ansprechpartner: Ansprechpartner[];
  vorgaenge: Pick<Vorgang, "id" | "vorgangsnummer" | "titel">[];
}) {
  const { currentUser, hatRecht } = useAuth();
  const kannErfassen = hatRecht("kunden", "sehen");
  const telefonat = useTelefonat();
  const { data, isLoading, isError, error, refetch } = useKontaktverlauf(kundeId);

  const erfassen = () => telefonat.erfassen({ kundeId, ansprechpartner, vorgaenge });
  const darfBearbeiten = (t: Telefonat) => !!currentUser && (t.erfasst_von === currentUser.id || istAdminRolle(currentUser));

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-fliess font-semibold text-label2">Kontaktverlauf</h2>
        {kannErfassen && (
          <button type="button" onClick={erfassen} className={NEU_BUTTON_KLASSE}>
            + Telefonat erfassen
          </button>
        )}
      </div>
      {isLoading ? (
        <SkeletonList count={3} />
      ) : isError ? (
        <FehlerZustand fehler={error} was="Der Kontaktverlauf" onErneut={() => void refetch()} />
      ) : (data ?? []).length === 0 ? (
        <EmptyState icon={Phone} text="Noch keine Telefonate oder E-Mails zu diesem Kunden." className="py-4" />
      ) : (
        <GroupedList>
          {data!.map((eintrag, i) =>
            eintrag.art === "telefonat" ? (
              <TelefonatZeile
                key={`t-${eintrag.telefonat.id}`}
                t={eintrag.telefonat}
                letzte={i === data!.length - 1}
                onOeffnen={darfBearbeiten(eintrag.telefonat) ? () => telefonat.bearbeiten(eintrag.telefonat) : undefined}
              />
            ) : (
              <EmailZeile key={`e-${eintrag.email.id}`} e={eintrag.email} letzte={i === data!.length - 1} />
            ),
          )}
        </GroupedList>
      )}
    </div>
  );
}
