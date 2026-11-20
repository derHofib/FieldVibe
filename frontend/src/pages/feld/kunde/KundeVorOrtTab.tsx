import { useQuery } from "@tanstack/react-query";
import { EyeOff, Info, Pencil, Phone, Trash2, Users } from "lucide-react";
import { useState } from "react";

import { standorteApi } from "../../../api/endpoints";
import { AktionsMenue, type AktionsMenueEintrag } from "../../../components/AktionsMenue";
import { AnlegenPanel } from "../../../components/AnlegenPanel";
import { Monogramm } from "../../../components/apple/Monogramm";
import { SearchField } from "../../../components/apple/SearchField";
import { Select } from "../../../components/apple/Select";
import { useBestaetigung } from "../../../components/ConfirmDialog";
import { EmptyState } from "../../../components/EmptyState";
import { FehlerZustand } from "../../../components/FehlerZustand";
import { NEU_BUTTON_KLASSE } from "../../../components/FormularFeld";
import { SkeletonList } from "../../../components/Skeleton";
import { useDebouncedValue } from "../../../hooks/useDebouncedValue";
import {
  useAnonymisierungMonate,
  useVorOrtAnonymisieren,
  useVorOrtKontaktAendern,
  useVorOrtKontaktAnlegen,
  useVorOrtKontaktLoeschen,
  useVorOrtKontakteFuerKunde,
} from "../../../hooks/useVorOrt";
import { VOR_ORT_ROLLEN, VOR_ORT_ROLLE_LABEL, type VorOrtKontakt, type VorOrtRolle } from "../../../types";
import {
  istAnonymisiert,
  kontaktAnzeigename,
  kontaktFormAus,
  kontaktFormZuBody,
  leereKontaktForm,
  monatJahr,
  nachStandortGruppieren,
  standortBegriff,
  telHref,
} from "../../../utils/vorOrt";
import { KontaktFormular } from "../vorOrt/KontaktFormular";
import { RollenChip } from "../vorOrt/KontaktZeile";

/** Reiter "Kontakte vor Ort" im Kundenprofil (Feld-App und Office-Detailpanel): alle Kontakte des Kunden, nach Standort
 * gruppiert; bei Hausverwaltungen heißen die Standorte "Liegenschaft". */
export function KundeVorOrtTab({
  kundeId,
  kundeTyp,
  kannVerwalten,
}: {
  kundeId: string;
  kundeTyp: string | null;
  kannVerwalten: boolean;
}) {
  const bestaetigen = useBestaetigung();
  const begriff = standortBegriff(kundeTyp);
  const [suche, setSuche] = useState("");
  const [rolle, setRolle] = useState<VorOrtRolle | "">("");
  const [anlegen, setAnlegen] = useState(false);
  const [bearbeiten, setBearbeiten] = useState<VorOrtKontakt | null>(null);
  const q = useDebouncedValue(suche.trim());
  const monate = useAnonymisierungMonate();

  const { data, isLoading, error, refetch } = useVorOrtKontakteFuerKunde(kundeId, {
    q: q || undefined,
    rolle: rolle || undefined,
    mit_anonymisierten: true,
  });
  const { data: standorte } = useQuery({ queryKey: ["standorte", kundeId], queryFn: () => standorteApi.list(kundeId) });
  const anlegenMutation = useVorOrtKontaktAnlegen(kundeId);
  const aendern = useVorOrtKontaktAendern();
  const loeschen = useVorOrtKontaktLoeschen();
  const anonymisieren = useVorOrtAnonymisieren();

  const gefiltert = !!q || !!rolle;
  const gruppen = nachStandortGruppieren(data ?? []);

  const menue = (k: VorOrtKontakt): (AktionsMenueEintrag | "trenner")[] => {
    const name = kontaktAnzeigename(k);
    return [
      ...(kannVerwalten && !istAnonymisiert(k)
        ? [
            { label: "Bearbeiten", icon: Pencil, onClick: () => setBearbeiten(k) },
            {
              label: "Sofort anonymisieren",
              icon: EyeOff,
              onClick: async () => {
                if (
                  await bestaetigen({
                    titel: `${name} sofort anonymisieren?`,
                    text: "Name, Telefon, E-Mail und Hinweise werden unwiderruflich gelöscht. Rolle und Einheit bleiben.",
                    bestaetigenLabel: "Anonymisieren",
                    destruktiv: true,
                  })
                ) {
                  anonymisieren.mutate(k.id);
                }
              },
            },
            "trenner" as const,
          ]
        : []),
      ...(kannVerwalten
        ? [
            {
              label: "Löschen",
              icon: Trash2,
              destruktiv: true,
              onClick: async () => {
                if (
                  await bestaetigen({
                    titel: `${name} löschen?`,
                    text: "Der Kontakt wird auch von allen Aufträgen und Vorgängen entfernt.",
                    bestaetigenLabel: "Löschen",
                    destruktiv: true,
                  })
                ) {
                  loeschen.mutate(k.id);
                }
              },
            },
          ]
        : []),
    ];
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <SearchField
          className="min-w-40 flex-1"
          value={suche}
          onChange={setSuche}
          placeholder="Name, Telefon, Einheit"
          ariaLabel="Kontakte vor Ort suchen"
          groesse="mobil"
        />
        <Select
          className="w-auto"
          aria-label="Rolle filtern"
          value={rolle}
          onChange={(e) => setRolle(e.target.value as VorOrtRolle | "")}
          groesse="kompakt"
        >
          <option value="">Alle Rollen</option>
          {VOR_ORT_ROLLEN.map((r) => (
            <option key={r} value={r}>
              {VOR_ORT_ROLLE_LABEL[r]}
            </option>
          ))}
        </Select>
        {kannVerwalten && (
          <button type="button" onClick={() => setAnlegen(true)} className={`${NEU_BUTTON_KLASSE} text-sekundaer`}>
            + Kontakt vor Ort
          </button>
        )}
      </div>

      {isLoading ? (
        <SkeletonList count={3} />
      ) : error && !data ? (
        <FehlerZustand fehler={error} was="Die Kontakte vor Ort" onErneut={() => void refetch()} className="py-6" />
      ) : gruppen.length === 0 ? (
        <EmptyState
          icon={Users}
          text={
            gefiltert
              ? "Kein Kontakt vor Ort gefunden."
              : "Noch keine Kontakte vor Ort. Sie entstehen an Aufträgen und Vorgängen oder hier direkt am Kunden."
          }
        />
      ) : (
        gruppen.map((g) => (
          <section key={g.standortId ?? "ohne"} aria-label={g.titel ?? `Ohne ${begriff}`} className="card-ap p-4">
            <h2 className="mb-1 text-sekundaer font-semibold tracking-wide text-label2 uppercase">
              {g.titel ? `${begriff}: ${g.titel}` : `Ohne ${begriff}`}
              <span className="ml-2 font-normal">{g.kontakte.length}</span>
            </h2>
            <ul className="divide-y-[0.5px] divide-sep">
              {g.kontakte.map((k) => {
                const anonym = istAnonymisiert(k);
                const name = kontaktAnzeigename(k);
                const letzter = monatJahr(k.letzter_einsatz_am);
                const eintraege = menue(k);
                return (
                  <li key={k.id} className={`flex items-start gap-3 py-2.5 ${anonym ? "opacity-60" : ""}`}>
                    <Monogramm name={anonym ? "?" : name} groesse={32} ringKlasse="ring-card" />
                    <div className="min-w-0 flex-1 space-y-0.5">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className={`text-fliess font-medium ${anonym ? "text-label3" : "text-label"}`}>{name}</span>
                        <RollenChip rolle={k.rolle} />
                      </div>
                      {(k.einheit || (!anonym && k.telefon)) && (
                        <p className="text-sekundaer text-label2">
                          {k.einheit}
                          {k.einheit && !anonym && k.telefon && " · "}
                          {!anonym && k.telefon && (
                            <a href={telHref(k.telefon)} className="inline-flex items-center gap-1 text-tint-text hover:underline">
                              <Phone size={12} strokeWidth={2} aria-hidden="true" />
                              {k.telefon}
                            </a>
                          )}
                        </p>
                      )}
                      <p className="text-meta text-label2">
                        {k.zuordnungen_anzahl} {k.zuordnungen_anzahl === 1 ? "Auftrag" : "Aufträge"}
                        {letzter && ` · Letzter Einsatz ${letzter}`}
                        {anonym && ` · anonymisiert ${monatJahr(k.anonymisiert_am) ?? ""}`}
                      </p>
                    </div>
                    {eintraege.length > 0 && <AktionsMenue label={`Aktionen für ${name}`} eintraege={eintraege} touch />}
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}

      <p className="flex items-start gap-2 rounded-[var(--radius-ap-md)] bg-tintbg px-3 py-2 text-sekundaer text-label">
        <Info size={16} strokeWidth={2} className="mt-0.5 shrink-0 text-tint" aria-hidden="true" />
        Kontakte werden {monate} Monate nach dem letzten Einsatz anonymisiert, sofern sie keinem offenen Auftrag zugeordnet sind.
      </p>

      <AnlegenPanel offen={anlegen} titel="Kontakt vor Ort" onClose={() => setAnlegen(false)}>
        <div className="p-4">
          <KontaktFormular
            start={leereKontaktForm()}
            standorte={standorte}
            standortBegriff={begriff}
            laeuft={anlegenMutation.isPending}
            fehler={anlegenMutation.error}
            submitLabel="Anlegen"
            onAbbrechen={() => setAnlegen(false)}
            onSubmit={(w) => anlegenMutation.mutate(kontaktFormZuBody(w, true), { onSuccess: () => setAnlegen(false) })}
            fussnote={`Wird ${monate} Monate nach dem letzten Einsatz anonymisiert.`}
          />
        </div>
      </AnlegenPanel>
      <AnlegenPanel offen={!!bearbeiten} titel="Kontakt bearbeiten" onClose={() => setBearbeiten(null)}>
        {bearbeiten && (
          <div className="p-4">
            <KontaktFormular
              start={kontaktFormAus(bearbeiten)}
              standorte={standorte}
              standortBegriff={begriff}
              laeuft={aendern.isPending}
              fehler={aendern.error}
              submitLabel="Speichern"
              onAbbrechen={() => setBearbeiten(null)}
              onSubmit={(w) =>
                aendern.mutate({ id: bearbeiten.id, body: kontaktFormZuBody(w, true) }, { onSuccess: () => setBearbeiten(null) })
              }
            />
          </div>
        )}
      </AnlegenPanel>
    </div>
  );
}
