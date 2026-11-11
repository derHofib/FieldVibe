import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { kundenApi, usersApi } from "../../../api/endpoints";
import { ApiError } from "../../../api/client";
import { ERechnungFelder, zeigeERechnungFelder } from "../../../components/kunde/ERechnungFelder";
import { FehlerMeldung } from "../../../components/Hinweiskasten";
import { Nachweis13bFeld, Nachweis13bStatus } from "../../../components/kunde/Nachweis13b";
import { validiereDebitorenkonto } from "../../../utils/datev";
import { E_RECHNUNG_FORMAT_KURZ, type ERechnungFormat, leitwegIdFehler } from "../../../utils/eRechnungVersand";
import type { Adresse, User } from "../../../types";

function leereAdresse(adresse: Adresse | null): { strasse: string; plz: string; ort: string } {
  return { strasse: adresse?.strasse ?? "", plz: adresse?.plz ?? "", ort: adresse?.ort ?? "" };
}

export function Stammdaten({
  kundeId,
  adresse,
  notiz,
  typ,
  ustIdnr,
  ust13bBis,
  leitwegId,
  eRechnungFormat,
  debitorenkonto,
  kannVerwalten,
}: {
  kundeId: string;
  adresse: Adresse | null;
  notiz: string | null;
  typ: string | null;
  ustIdnr: string | null;
  ust13bBis: string | null;
  leitwegId: string | null;
  eRechnungFormat: ERechnungFormat | null;
  debitorenkonto: string | null;
  kannVerwalten: boolean;
}) {
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [form, setForm] = useState(() => ({
    ...leereAdresse(adresse),
    notiz: notiz ?? "",
    ustIdnr: ustIdnr ?? "",
    ust13bBis: ust13bBis ?? "",
    leitwegId: leitwegId ?? "",
    eRechnungFormat: (eRechnungFormat ?? "") as ERechnungFormat | "",
    debitorenkonto: debitorenkonto ?? "",
  }));
  const kontoFehler = validiereDebitorenkonto(form.debitorenkonto);
  const brauchtUstIdnr = typ === "gewerbe" || typ === "oeffentlich";

  const speichernMutation = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: () =>
      kundenApi.update(kundeId, {
        adresse:
          form.strasse || form.plz || form.ort
            ? { strasse: form.strasse || undefined, plz: form.plz || undefined, ort: form.ort || undefined }
            : null,
        notiz: form.notiz || null,
        ust_idnr: form.ustIdnr || null,
        ust_13b_nachweis_bis: form.ust13bBis || null,
        leitweg_id: form.leitwegId.trim() || null,
        e_rechnung_format: form.eRechnungFormat || null,
        debitorenkonto: form.debitorenkonto.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kundeId] });
      setBearbeiten(false);
    },
  });

  if (!bearbeiten) {
    const adressZeile = [adresse?.strasse, [adresse?.plz, adresse?.ort].filter(Boolean).join(" ")]
      .filter(Boolean)
      .join(", ");
    return (
      <div className="card-ap p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-label2">Stammdaten</h2>
          {kannVerwalten && (
            <button
              onClick={() => {
                setForm({
                  ...leereAdresse(adresse),
                  notiz: notiz ?? "",
                  ustIdnr: ustIdnr ?? "",
                  ust13bBis: ust13bBis ?? "",
                  leitwegId: leitwegId ?? "",
                  eRechnungFormat: (eRechnungFormat ?? "") as ERechnungFormat | "",
                  debitorenkonto: debitorenkonto ?? "",
                });
                speichernMutation.reset();
                setBearbeiten(true);
              }}
              className="btn-touch text-xs font-medium text-tint "
            >
              Bearbeiten
            </button>
          )}
        </div>
        {adressZeile ? (
          <p className="text-sm text-label">{adressZeile}</p>
        ) : (
          <p className="text-sm text-label2">Keine Adresse hinterlegt.</p>
        )}
        {notiz && <p className="mt-1 text-sm text-label2">{notiz}</p>}
        <p className="mt-1 text-sm text-label2">
          Debitorenkonto (DATEV):{" "}
          {debitorenkonto || <span className="text-label2">wird beim ersten Export vergeben</span>}
        </p>
        {brauchtUstIdnr && (
          <p className="mt-1 text-sm text-label2">
            USt-IdNr.:{" "}
            {ustIdnr || <span className="text-label2">nicht hinterlegt</span>}
          </p>
        )}
        {brauchtUstIdnr && (
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-label2">
            <span>§ 13b-Nachweis USt 1 TG:</span>
            <Nachweis13bStatus bis={ust13bBis} />
          </div>
        )}
        {(leitwegId || eRechnungFormat) && (
          <p className="mt-1.5 text-sm text-label2">
            E-Rechnung: {eRechnungFormat ? E_RECHNUNG_FORMAT_KURZ[eRechnungFormat] : "Format automatisch"}
            {leitwegId && ` · Leitweg-ID ${leitwegId}`}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2 card-ap p-4">
      <h2 className="text-sm font-semibold text-label2">Stammdaten bearbeiten</h2>
      <input
        value={form.strasse}
        onChange={(e) => setForm({ ...form, strasse: e.target.value })}
        placeholder="Straße + Hausnr."
        className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          value={form.plz}
          onChange={(e) => setForm({ ...form, plz: e.target.value })}
          placeholder="PLZ"
          className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
        />
        <input
          value={form.ort}
          onChange={(e) => setForm({ ...form, ort: e.target.value })}
          placeholder="Ort"
          className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
        />
      </div>
      {brauchtUstIdnr && (
        <input
          value={form.ustIdnr}
          onChange={(e) => setForm({ ...form, ustIdnr: e.target.value })}
          placeholder="USt-IdNr."
          className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
        />
      )}
      {brauchtUstIdnr && (
        <Nachweis13bFeld wert={form.ust13bBis} onChange={(ust13bBis) => setForm({ ...form, ust13bBis })} />
      )}
      {zeigeERechnungFelder(typ, form.leitwegId, form.eRechnungFormat) && (
        <ERechnungFelder
          leitwegId={form.leitwegId}
          format={form.eRechnungFormat}
          onChange={({ leitwegId: neueId, format }) => setForm({ ...form, leitwegId: neueId, eRechnungFormat: format })}
        />
      )}
      <div>
        <label htmlFor="kunde-debitorenkonto" className="mb-0.5 block text-xs text-label2">
          Debitorenkonto (DATEV, optional)
        </label>
        <input
          id="kunde-debitorenkonto"
          value={form.debitorenkonto}
          onChange={(e) => {
            setForm({ ...form, debitorenkonto: e.target.value });
            speichernMutation.reset();
          }}
          inputMode="numeric"
          maxLength={9}
          placeholder="leer = automatisch beim ersten Export"
          aria-invalid={!!kontoFehler}
          className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm tabular-nums text-label"
        />
        {kontoFehler && (
          <p role="alert" className="mt-0.5 text-xs text-st-fehlt">
            {kontoFehler}
          </p>
        )}
        <p className="mt-0.5 text-xs text-label2">
          Nach dem ersten DATEV-Import nicht mehr ändern, sonst passen die Buchungen nicht mehr zum Personenkonto.
        </p>
      </div>
      <textarea
        value={form.notiz}
        onChange={(e) => setForm({ ...form, notiz: e.target.value })}
        placeholder="Notiz"
        rows={2}
        className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
      />
      {speichernMutation.isError && (
        <FehlerMeldung
          alsKasten
          meldung={speichernMutation.error instanceof ApiError ? speichernMutation.error.message : "Speichern fehlgeschlagen"}
        />
      )}
      <div className="flex gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending || leitwegIdFehler(form.leitwegId) !== null || !!kontoFehler}
          className="btn-touch flex-1 rounded-md btn-ap-primary py-2 text-sm font-medium disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => setBearbeiten(false)}
          className="btn-touch flex-1 rounded-md border border-sep py-2 text-sm font-medium text-label "
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

export function TechnikerZuweisung({ kundeId, zugewiesen }: { kundeId: string; zugewiesen: User[] }) {
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [auswahl, setAuswahl] = useState<string[]>([]);

  const { data: alleUser } = useQuery({
    queryKey: ["users", "auswahl"],
    queryFn: usersApi.auswahl,
    enabled: bearbeiten,
  });
  const techniker = alleUser?.filter((u) => u.nur_zugewiesene_kunden) ?? [];

  const speichernMutation = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: () => kundenApi.technikerSetzen(kundeId, auswahl),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kundeId] });
      setBearbeiten(false);
    },
  });

  function toggle(userId: string) {
    setAuswahl((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]
    );
  }

  if (!bearbeiten) {
    return (
      <div>
        <h2 className="mb-2 text-sm font-semibold text-label2">Zugewiesene Techniker</h2>
        {zugewiesen.length === 0 ? (
          <p className="text-sm text-label2">Kein Techniker zugewiesen.</p>
        ) : (
          <div className="flex flex-wrap gap-1">
            {zugewiesen.map((t) => (
              <span key={t.id} className="border border-sep px-2 py-0.5 text-xs text-label">
                {t.name}
              </span>
            ))}
          </div>
        )}
        <button
          onClick={() => {
            setAuswahl(zugewiesen.map((t) => t.id));
            setBearbeiten(true);
          }}
          className="btn-touch mt-2 text-xs text-tint underline "
        >
          Bearbeiten
        </button>
      </div>
    );
  }

  return (
    <div className="border border-sepstrong p-3">
      <h2 className="mb-2 text-sm font-semibold text-label2">Zugewiesene Techniker</h2>
      {techniker.length === 0 ? (
        <p className="text-sm text-label2">Keine Techniker in diesem Mandanten angelegt.</p>
      ) : (
        <div className="space-y-1">
          {techniker.map((u) => (
            <label key={u.id} className="btn-touch flex items-center gap-2 text-sm text-label">
              <input
                type="checkbox"
                checked={auswahl.includes(u.id)}
                onChange={() => toggle(u.id)}
              />
              {u.name}
            </label>
          ))}
        </div>
      )}
      <div className="mt-2 flex gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending}
          className="btn-touch flex-1 rounded-md btn-ap-primary py-2 text-sm font-medium disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => setBearbeiten(false)}
          className="btn-touch flex-1 rounded-md border border-sep py-2 text-sm font-medium text-label "
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}
