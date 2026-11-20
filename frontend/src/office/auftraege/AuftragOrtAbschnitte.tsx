import { useQuery } from "@tanstack/react-query";
import { Phone } from "lucide-react";
import { useState } from "react";

import { kundenApi, standorteApi } from "../../api/endpoints";
import { Select } from "../../components/apple/Select";
import type { Auftrag } from "../../types";
import { adresseAlsZeile } from "../../pages/feld/vorgang/konstanten";
import { ABSCHNITT_AKTION, Abschnitt } from "../../pages/feld/vorgang/Abschnitt";
import { standortBegriff, telHref } from "../../utils/vorOrt";

type AuftragAenderung = {
  ansprechpartner_id?: string | null;
  kunden_referenz?: string | null;
  standort_id?: string | null;
  einheit?: string | null;
};

interface Props {
  auftrag: Auftrag;
  /** Speichert per PATCH; `onFertig` schließt das Bearbeiten erst nach Erfolg. */
  speichern: (body: AuftragAenderung, onFertig: () => void) => void;
  laeuft: boolean;
}

const ZEILE = "flex items-baseline justify-between gap-3";

function Bearbeiten({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={ABSCHNITT_AKTION}>
      Bearbeiten
    </button>
  );
}

function Knoepfe({ laeuft, onAbbrechen, onSpeichern }: { laeuft: boolean; onAbbrechen: () => void; onSpeichern: () => void }) {
  return (
    <div className="flex justify-end gap-2">
      <button type="button" onClick={onAbbrechen} className="btn-touch btn-ap px-3 text-sekundaer">
        Abbrechen
      </button>
      <button type="button" disabled={laeuft} onClick={onSpeichern} className="btn-touch btn-ap-primary px-3 text-sekundaer">
        Speichern
      </button>
    </div>
  );
}

/** Abschnitt "Auftraggeber": Kunde, Sachbearbeitung (Ansprechpartner des Kunden) und dessen Zeichen (kunden_referenz). */
export function AuftragAuftraggeberAbschnitt({ auftrag, speichern, laeuft }: Props) {
  const [bearbeiten, setBearbeiten] = useState(false);
  const [ansprechpartnerId, setAnsprechpartnerId] = useState("");
  const [zeichen, setZeichen] = useState("");
  const { data: kunde } = useQuery({
    queryKey: ["kunde", auftrag.kunde_id],
    queryFn: () => kundenApi.get(auftrag.kunde_id!),
    enabled: !!auftrag.kunde_id && bearbeiten,
  });
  const sach = auftrag.ansprechpartner ?? null;

  return (
    <Abschnitt
      titel="Auftraggeber"
      aktion={
        auftrag.kunde_id && !bearbeiten ? (
          <Bearbeiten
            onClick={() => {
              setAnsprechpartnerId(auftrag.ansprechpartner_id ?? "");
              setZeichen(auftrag.kunden_referenz ?? "");
              setBearbeiten(true);
            }}
          />
        ) : undefined
      }
    >
      {bearbeiten ? (
        <div className="space-y-2">
          <label className="block text-sekundaer text-label2">
            Sachbearbeitung
            <Select className="mt-1 w-full" value={ansprechpartnerId} onChange={(e) => setAnsprechpartnerId(e.target.value)}>
              <option value="">Keine Angabe</option>
              {(kunde?.ansprechpartner ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                  {a.position ? ` (${a.position})` : ""}
                </option>
              ))}
            </Select>
          </label>
          <label className="block text-sekundaer text-label2">
            Zeichen des Auftraggebers
            <input
              value={zeichen}
              onChange={(e) => setZeichen(e.target.value)}
              placeholder="Auftragsnummer / Ihr Zeichen"
              className="field-ap mt-1"
            />
          </label>
          <Knoepfe
            laeuft={laeuft}
            onAbbrechen={() => setBearbeiten(false)}
            onSpeichern={() =>
              speichern({ ansprechpartner_id: ansprechpartnerId || null, kunden_referenz: zeichen.trim() || null }, () => setBearbeiten(false))
            }
          />
        </div>
      ) : !auftrag.kunde_id ? (
        <p className="text-fliess text-label2">Kein Auftraggeber gesetzt. Kunde über „Details“ wählen.</p>
      ) : (
        <dl className="space-y-1.5 text-fliess">
          <div className={ZEILE}>
            <dt className="text-label2">Kunde</dt>
            <dd className="text-right font-medium text-label">{auftrag.kunde_name ?? "—"}</dd>
          </div>
          <div className={ZEILE}>
            <dt className="text-label2">Sachbearbeitung</dt>
            <dd className="flex items-center gap-2 text-right font-medium text-label">
              {sach ? sach.name : "—"}
              {sach?.telefon && (
                <a
                  href={telHref(sach.telefon)}
                  aria-label={`${sach.name} anrufen`}
                  className="inline-flex items-center gap-1 text-sekundaer font-medium text-tint-text hover:underline"
                >
                  <Phone size={13} strokeWidth={2} aria-hidden="true" />
                  {sach.telefon}
                </a>
              )}
            </dd>
          </div>
          <div className={ZEILE}>
            <dt className="text-label2">Zeichen des Auftraggebers</dt>
            <dd className="text-right font-medium text-label">{auftrag.kunden_referenz || "—"}</dd>
          </div>
        </dl>
      )}
    </Abschnitt>
  );
}

/** Abschnitt "Leistungsort": Standort (bei Hausverwaltungen "Liegenschaft") des Kunden plus Einheit. */
export function AuftragLeistungsortAbschnitt({ auftrag, speichern, laeuft }: Props) {
  const [bearbeiten, setBearbeiten] = useState(false);
  const [standortId, setStandortId] = useState("");
  const [einheit, setEinheit] = useState("");
  const { data: kunde } = useQuery({
    queryKey: ["kunde", auftrag.kunde_id],
    queryFn: () => kundenApi.get(auftrag.kunde_id!),
    enabled: !!auftrag.kunde_id,
  });
  const { data: standorte } = useQuery({
    queryKey: ["standorte", auftrag.kunde_id, "aktiv"],
    queryFn: () => standorteApi.list(auftrag.kunde_id!, true),
    enabled: !!auftrag.kunde_id && bearbeiten,
  });
  const begriff = standortBegriff(kunde?.typ);
  const adresse = adresseAlsZeile(auftrag.standort?.adresse ?? null);

  return (
    <Abschnitt
      titel="Leistungsort"
      aktion={
        auftrag.kunde_id && !bearbeiten ? (
          <Bearbeiten
            onClick={() => {
              setStandortId(auftrag.standort_id ?? "");
              setEinheit(auftrag.einheit ?? "");
              setBearbeiten(true);
            }}
          />
        ) : undefined
      }
    >
      {bearbeiten ? (
        <div className="space-y-2">
          <label className="block text-sekundaer text-label2">
            {begriff}
            <Select className="mt-1 w-full" value={standortId} onChange={(e) => setStandortId(e.target.value)}>
              <option value="">Kein {begriff}</option>
              {(standorte ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.bezeichnung}
                </option>
              ))}
            </Select>
          </label>
          <label className="block text-sekundaer text-label2">
            Einheit
            <input value={einheit} onChange={(e) => setEinheit(e.target.value)} placeholder="z. B. Whg. 3, 2. OG links" className="field-ap mt-1" />
          </label>
          <Knoepfe
            laeuft={laeuft}
            onAbbrechen={() => setBearbeiten(false)}
            onSpeichern={() => speichern({ standort_id: standortId || null, einheit: einheit.trim() || null }, () => setBearbeiten(false))}
          />
        </div>
      ) : !auftrag.kunde_id ? (
        <p className="text-fliess text-label2">Erst einen Auftraggeber setzen.</p>
      ) : (
        <dl className="space-y-1.5 text-fliess">
          <div className={ZEILE}>
            <dt className="text-label2">{begriff}</dt>
            <dd className="text-right font-medium text-label">
              {auftrag.standort?.bezeichnung ?? "—"}
              {adresse && <span className="block text-sekundaer font-normal text-label2">{adresse}</span>}
            </dd>
          </div>
          <div className={ZEILE}>
            <dt className="text-label2">Einheit</dt>
            <dd className="text-right font-medium text-label">{auftrag.einheit || "—"}</dd>
          </div>
        </dl>
      )}
    </Abschnitt>
  );
}
