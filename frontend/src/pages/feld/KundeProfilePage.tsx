import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Inbox, MapPin, Repeat } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  anlagenApi,
  dauerauftraegeApi,
  kundenApi,
  kundenportalZugaengeApi,
  standorteApi,
  usersApi,
} from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { EmailSection } from "../../components/EmailSection";
import { EmptyState } from "../../components/EmptyState";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import { downloadBlob } from "../../utils/download";
import type {
  Adresse,
  Ansprechpartner,
  Anlage,
  Eskalationsstufe,
  Kunde,
  KundenportalZugang,
  Standort,
  User,
} from "../../types";

const ESKALATIONSSTUFE_LABEL: Record<Eskalationsstufe, string> = {
  1: "Stufe 1 – Erstkontakt",
  2: "Stufe 2 – Eskalation",
  3: "Stufe 3 – Geschäftsleitung/Notfall",
};

function leereAdresse(adresse: Adresse | null): { strasse: string; plz: string; ort: string } {
  return { strasse: adresse?.strasse ?? "", plz: adresse?.plz ?? "", ort: adresse?.ort ?? "" };
}

function Stammdaten({
  kundeId,
  adresse,
  notiz,
  typ,
  ustIdnr,
  kannVerwalten,
}: {
  kundeId: string;
  adresse: Adresse | null;
  notiz: string | null;
  typ: string | null;
  ustIdnr: string | null;
  kannVerwalten: boolean;
}) {
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [form, setForm] = useState(() => ({
    ...leereAdresse(adresse),
    notiz: notiz ?? "",
    ustIdnr: ustIdnr ?? "",
  }));
  const brauchtUstIdnr = typ === "gewerbe" || typ === "oeffentlich";

  const speichernMutation = useMutation({
    mutationFn: () =>
      kundenApi.update(kundeId, {
        adresse:
          form.strasse || form.plz || form.ort
            ? { strasse: form.strasse || undefined, plz: form.plz || undefined, ort: form.ort || undefined }
            : null,
        notiz: form.notiz || null,
        ust_idnr: form.ustIdnr || null,
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
      <div className="rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Stammdaten</h2>
          {kannVerwalten && (
            <button
              onClick={() => {
                setForm({ ...leereAdresse(adresse), notiz: notiz ?? "", ustIdnr: ustIdnr ?? "" });
                setBearbeiten(true);
              }}
              className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
            >
              Bearbeiten
            </button>
          )}
        </div>
        {adressZeile ? (
          <p className="text-sm text-slate-700 dark:text-stone-300">{adressZeile}</p>
        ) : (
          <p className="text-sm text-slate-400 dark:text-stone-500">Keine Adresse hinterlegt.</p>
        )}
        {notiz && <p className="mt-1 text-sm text-slate-500 dark:text-stone-400">{notiz}</p>}
        {brauchtUstIdnr && (
          <p className="mt-1 text-sm text-slate-500 dark:text-stone-400">
            USt-IdNr.:{" "}
            {ustIdnr || <span className="text-slate-400 dark:text-stone-500">nicht hinterlegt</span>}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Stammdaten bearbeiten</h2>
      <input
        value={form.strasse}
        onChange={(e) => setForm({ ...form, strasse: e.target.value })}
        placeholder="Straße + Hausnr."
        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          value={form.plz}
          onChange={(e) => setForm({ ...form, plz: e.target.value })}
          placeholder="PLZ"
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
        <input
          value={form.ort}
          onChange={(e) => setForm({ ...form, ort: e.target.value })}
          placeholder="Ort"
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
      </div>
      {brauchtUstIdnr && (
        <input
          value={form.ustIdnr}
          onChange={(e) => setForm({ ...form, ustIdnr: e.target.value })}
          placeholder="USt-IdNr."
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
      )}
      <textarea
        value={form.notiz}
        onChange={(e) => setForm({ ...form, notiz: e.target.value })}
        placeholder="Notiz"
        rows={2}
        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      <div className="flex gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending}
          className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => setBearbeiten(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

function leerFormular(): Omit<Ansprechpartner, "id"> {
  return { name: "", position: "", telefon: "", email: "", operativ: false, eskalationsstufe: null, notiz: "" };
}

function AnsprechpartnerForm({
  eintrag,
  onSpeichern,
  onAbbrechen,
  speichernLaeuft,
}: {
  eintrag: Omit<Ansprechpartner, "id">;
  onSpeichern: (eintrag: Omit<Ansprechpartner, "id">) => void;
  onAbbrechen: () => void;
  speichernLaeuft: boolean;
}) {
  const [form, setForm] = useState(eintrag);

  return (
    <div className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-stone-800/60">
      <input
        autoFocus
        value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })}
        placeholder="Name *"
        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      <input
        value={form.position ?? ""}
        onChange={(e) => setForm({ ...form, position: e.target.value })}
        placeholder="Position (z.B. Geschäftsführer, Hausmeister)"
        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          value={form.telefon ?? ""}
          onChange={(e) => setForm({ ...form, telefon: e.target.value })}
          placeholder="Telefon"
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
        <input
          type="email"
          value={form.email ?? ""}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          placeholder="E-Mail"
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
      </div>
      <select
        value={form.eskalationsstufe ?? ""}
        onChange={(e) =>
          setForm({ ...form, eskalationsstufe: e.target.value ? (Number(e.target.value) as Eskalationsstufe) : null })
        }
        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      >
        <option value="">Keine Eskalationsstufe</option>
        {([1, 2, 3] as Eskalationsstufe[]).map((stufe) => (
          <option key={stufe} value={stufe}>
            {ESKALATIONSSTUFE_LABEL[stufe]}
          </option>
        ))}
      </select>
      <label className="btn-touch flex items-center gap-2 text-sm text-slate-700 dark:text-stone-300">
        <input
          type="checkbox"
          checked={form.operativ}
          onChange={(e) => setForm({ ...form, operativ: e.target.checked })}
        />
        Operativer Ansprechpartner (Tagesgeschäft)
      </label>
      <div className="flex gap-2">
        <button
          disabled={!form.name.trim() || speichernLaeuft}
          onClick={() => onSpeichern(form)}
          className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={onAbbrechen}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

function AnsprechpartnerVerwaltung({
  kundeId,
  liste,
  kannVerwalten,
}: {
  kundeId: string;
  liste: Ansprechpartner[];
  kannVerwalten: boolean;
}) {
  const queryClient = useQueryClient();
  const [neuAnlegen, setNeuAnlegen] = useState(false);
  const [bearbeitenId, setBearbeitenId] = useState<string | null>(null);

  const speichernMutation = useMutation({
    mutationFn: (naechsteListe: Ansprechpartner[]) => kundenApi.update(kundeId, { ansprechpartner: naechsteListe }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kundeId] });
      setNeuAnlegen(false);
      setBearbeitenId(null);
    },
  });

  function hinzufuegen(eintrag: Omit<Ansprechpartner, "id">) {
    speichernMutation.mutate([...liste, { ...eintrag, id: crypto.randomUUID() }]);
  }

  function aktualisieren(id: string, eintrag: Omit<Ansprechpartner, "id">) {
    speichernMutation.mutate(liste.map((a) => (a.id === id ? { ...eintrag, id } : a)));
  }

  function entfernen(id: string) {
    speichernMutation.mutate(liste.filter((a) => a.id !== id));
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Ansprechpartner</h2>
        {kannVerwalten && !neuAnlegen && (
          <button onClick={() => setNeuAnlegen(true)} className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400">
            + Neu
          </button>
        )}
      </div>

      {liste.length === 0 && !neuAnlegen && (
        <p className="text-sm text-slate-400 dark:text-stone-500">Noch keine Ansprechpartner hinterlegt.</p>
      )}

      <div className="space-y-2">
        {liste.map((a) =>
          bearbeitenId === a.id ? (
            <AnsprechpartnerForm
              key={a.id}
              eintrag={a}
              onSpeichern={(eintrag) => aktualisieren(a.id, eintrag)}
              onAbbrechen={() => setBearbeitenId(null)}
              speichernLaeuft={speichernMutation.isPending}
            />
          ) : (
            <div
              key={a.id}
              className="rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-medium text-slate-800 dark:text-stone-100">{a.name}</div>
                  {a.position && <div className="text-xs text-slate-400 dark:text-stone-500">{a.position}</div>}
                </div>
                <div className="flex gap-1">
                  {a.operativ && (
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-500/15 dark:text-blue-300">
                      Operativ
                    </span>
                  )}
                  {a.eskalationsstufe && (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
                      Stufe {a.eskalationsstufe}
                    </span>
                  )}
                </div>
              </div>
              {(a.telefon || a.email) && (
                <div className="mt-1 text-xs text-slate-500 dark:text-stone-400">
                  {[a.telefon, a.email].filter(Boolean).join(" · ")}
                </div>
              )}
              {a.notiz && <p className="mt-1 text-xs text-slate-400 dark:text-stone-500">{a.notiz}</p>}
              {kannVerwalten && (
                <div className="mt-2 flex gap-3">
                  <button
                    onClick={() => setBearbeitenId(a.id)}
                    className="btn-touch text-xs text-blue-700 underline dark:text-blue-400"
                  >
                    Bearbeiten
                  </button>
                  <button
                    onClick={() => entfernen(a.id)}
                    disabled={speichernMutation.isPending}
                    className="btn-touch text-xs text-red-700 underline disabled:opacity-50 dark:text-red-400"
                  >
                    Entfernen
                  </button>
                </div>
              )}
            </div>
          )
        )}

        {neuAnlegen && kannVerwalten && (
          <AnsprechpartnerForm
            eintrag={leerFormular()}
            onSpeichern={hinzufuegen}
            onAbbrechen={() => setNeuAnlegen(false)}
            speichernLaeuft={speichernMutation.isPending}
          />
        )}
      </div>
    </div>
  );
}

const STATUS_BADGE: Record<string, string> = {
  neu: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300",
  geplant: "bg-purple-100 text-purple-800 dark:bg-purple-500/15 dark:text-purple-300",
  in_arbeit: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  wartet_kunde: "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300",
  abgeschlossen: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300",
  abgerechnet: "bg-slate-200 text-slate-700 dark:bg-stone-700 dark:text-stone-300",
  storniert: "bg-slate-100 text-slate-400 dark:bg-stone-800 dark:text-stone-500",
};

function TechnikerZuweisung({ kundeId, zugewiesen }: { kundeId: string; zugewiesen: User[] }) {
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [auswahl, setAuswahl] = useState<string[]>([]);

  const { data: alleUser } = useQuery({
    queryKey: ["users"],
    queryFn: usersApi.list,
    enabled: bearbeiten,
  });
  const techniker = alleUser?.filter((u) => u.nur_zugewiesene_kunden) ?? [];

  const speichernMutation = useMutation({
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
        <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">Zugewiesene Techniker</h2>
        {zugewiesen.length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-stone-500">Kein Techniker zugewiesen.</p>
        ) : (
          <div className="flex flex-wrap gap-1">
            {zugewiesen.map((t) => (
              <span key={t.id} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-stone-800 dark:text-stone-300">
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
          className="btn-touch mt-2 text-xs text-blue-700 underline dark:text-blue-400"
        >
          Bearbeiten
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-lg bg-slate-50 p-3 dark:bg-stone-800/60">
      <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">Zugewiesene Techniker</h2>
      {techniker.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-stone-500">Keine Techniker in diesem Mandanten angelegt.</p>
      ) : (
        <div className="space-y-1">
          {techniker.map((u) => (
            <label key={u.id} className="btn-touch flex items-center gap-2 text-sm text-slate-700 dark:text-stone-300">
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
          className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => setBearbeiten(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

function NeueAnlage({ kundeId, standorte }: { kundeId: string; standorte: Standort[] }) {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [bezeichnung, setBezeichnung] = useState("");
  const [anlagentyp, setAnlagentyp] = useState("");
  const [standortId, setStandortId] = useState("");
  const [neuerStandortName, setNeuerStandortName] = useState("");
  const [zeigeNeuerStandort, setZeigeNeuerStandort] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const neuerStandortMutation = useMutation({
    mutationFn: () => standorteApi.create({ kunde_id: kundeId, bezeichnung: neuerStandortName }),
    onSuccess: (standort) => {
      queryClient.invalidateQueries({ queryKey: ["standorte", kundeId] });
      setStandortId(standort.id);
      setNeuerStandortName("");
      setZeigeNeuerStandort(false);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Standort konnte nicht angelegt werden"),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      anlagenApi.create({
        kunde_id: kundeId,
        bezeichnung,
        anlagentyp: anlagentyp || undefined,
        standort_id: standortId || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kundeId] });
      setZeigen(false);
      setBezeichnung("");
      setAnlagentyp("");
      setStandortId("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Anlage konnte nicht angelegt werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!bezeichnung.trim()) {
      setError("Bitte eine Bezeichnung eingeben");
      return;
    }
    createMutation.mutate();
  }

  if (!zeigen) {
    return (
      <button onClick={() => setZeigen(true)} className="btn-touch text-xs text-blue-700 underline dark:text-blue-400">
        + Neue Anlage anlegen
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-stone-800/60">
      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-stone-300">Bezeichnung</label>
        <input
          autoFocus
          value={bezeichnung}
          onChange={(e) => setBezeichnung(e.target.value)}
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-stone-300">Typ (optional)</label>
        <input
          value={anlagentyp}
          onChange={(e) => setAnlagentyp(e.target.value)}
          placeholder="z.B. Hauptverteilung, PV-Anlage, Wallbox"
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
      </div>
      <div>
        <div className="mb-1 flex items-center justify-between">
          <label className="block text-sm font-medium text-slate-700 dark:text-stone-300">
            Standort (optional)
          </label>
          <button
            type="button"
            onClick={() => setZeigeNeuerStandort((v) => !v)}
            className="btn-touch text-xs text-blue-700 underline dark:text-blue-400"
          >
            {zeigeNeuerStandort ? "Abbrechen" : "+ Neuer Standort"}
          </button>
        </div>
        {zeigeNeuerStandort ? (
          <div className="flex gap-2">
            <input
              autoFocus
              value={neuerStandortName}
              onChange={(e) => setNeuerStandortName(e.target.value)}
              placeholder="Bezeichnung (z.B. Filiale Nord)"
              className="btn-touch flex-1 rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <button
              type="button"
              disabled={!neuerStandortName.trim() || neuerStandortMutation.isPending}
              onClick={() => neuerStandortMutation.mutate()}
              className="btn-touch shrink-0 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 text-sm font-medium text-white disabled:opacity-50"
            >
              Anlegen
            </button>
          </div>
        ) : (
          <select
            value={standortId}
            onChange={(e) => setStandortId(e.target.value)}
            className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          >
            <option value="">Kein Standort</option>
            {standorte.map((s) => (
              <option key={s.id} value={s.id}>
                {s.bezeichnung}
              </option>
            ))}
          </select>
        )}
      </div>
      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Anlegen
        </button>
        <button
          type="button"
          onClick={() => setZeigen(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
        >
          Abbrechen
        </button>
      </div>
    </form>
  );
}

function NeuerStandort({ kundeId }: { kundeId: string }) {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [bezeichnung, setBezeichnung] = useState("");
  const [strasse, setStrasse] = useState("");
  const [plz, setPlz] = useState("");
  const [ort, setOrt] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      standorteApi.create({
        kunde_id: kundeId,
        bezeichnung,
        adresse:
          strasse || plz || ort
            ? { strasse: strasse || undefined, plz: plz || undefined, ort: ort || undefined }
            : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["standorte", kundeId] });
      setZeigen(false);
      setBezeichnung("");
      setStrasse("");
      setPlz("");
      setOrt("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Standort konnte nicht angelegt werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!bezeichnung.trim()) {
      setError("Bitte eine Bezeichnung eingeben");
      return;
    }
    createMutation.mutate();
  }

  if (!zeigen) {
    return (
      <button onClick={() => setZeigen(true)} className="btn-touch text-xs text-blue-700 underline dark:text-blue-400">
        + Neuen Standort anlegen
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-stone-800/60">
      <input
        autoFocus
        value={bezeichnung}
        onChange={(e) => setBezeichnung(e.target.value)}
        placeholder="Bezeichnung (z.B. Filiale Nord)"
        className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      <input
        value={strasse}
        onChange={(e) => setStrasse(e.target.value)}
        placeholder="Straße + Hausnr."
        className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          value={plz}
          onChange={(e) => setPlz(e.target.value)}
          placeholder="PLZ"
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
        <input
          value={ort}
          onChange={(e) => setOrt(e.target.value)}
          placeholder="Ort"
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
        />
      </div>
      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Anlegen
        </button>
        <button
          type="button"
          onClick={() => setZeigen(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
        >
          Abbrechen
        </button>
      </div>
    </form>
  );
}

function StandorteVerwaltung({ kundeId, kannVerwalten }: { kundeId: string; kannVerwalten: boolean }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: standorte } = useQuery({
    queryKey: ["standorte", kundeId],
    queryFn: () => standorteApi.list(kundeId),
  });

  const toggleAktivMutation = useMutation({
    mutationFn: ({ id, aktiv }: { id: string; aktiv: boolean }) => standorteApi.update(id, { aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["standorte", kundeId] }),
  });

  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">Standorte</h2>
      {!standorte || standorte.length === 0 ? (
        <EmptyState icon={MapPin} text="Keine Standorte." className="py-4" />
      ) : (
        <div className="space-y-2">
          {standorte.map((s) => (
            <div
              key={s.id}
              className={`flex items-center justify-between rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800 ${
                s.aktiv ? "" : "opacity-60"
              }`}
            >
              <button
                onClick={() => navigate(`/standorte/${s.id}`)}
                className="btn-touch flex-1 text-left"
              >
                <div className="text-sm font-medium text-slate-800 dark:text-stone-100 hover:underline">
                  {s.bezeichnung}
                </div>
                {s.adresse?.ort && (
                  <div className="text-xs text-slate-400 dark:text-stone-500">
                    {[s.adresse.strasse, [s.adresse.plz, s.adresse.ort].filter(Boolean).join(" ")]
                      .filter(Boolean)
                      .join(", ")}
                  </div>
                )}
              </button>
              {kannVerwalten && (
                <button
                  onClick={() => toggleAktivMutation.mutate({ id: s.id, aktiv: !s.aktiv })}
                  className="btn-touch shrink-0 rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:bg-stone-800 dark:text-stone-300"
                >
                  {s.aktiv ? "Deaktivieren" : "Aktivieren"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {kannVerwalten && (
        <div className="mt-2">
          <NeuerStandort kundeId={kundeId} />
        </div>
      )}
    </div>
  );
}

function AnlageAktivToggle({ anlage, kundeId }: { anlage: Anlage; kundeId: string }) {
  const queryClient = useQueryClient();
  const toggleMutation = useMutation({
    mutationFn: () => anlagenApi.update(anlage.id, { aktiv: !anlage.aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["kunde-profil", kundeId] }),
  });

  return (
    <button
      onClick={() => toggleMutation.mutate()}
      disabled={toggleMutation.isPending}
      className="btn-touch shrink-0 rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:bg-stone-800 dark:text-stone-300"
    >
      {anlage.aktiv ? "Deaktivieren" : "Aktivieren"}
    </button>
  );
}

function PortalZugangZeile({ zugang, kundeId }: { zugang: KundenportalZugang; kundeId: string }) {
  const queryClient = useQueryClient();

  const toggleMutation = useMutation({
    mutationFn: () => kundenportalZugaengeApi.update(kundeId, zugang.id, { aktiv: !zugang.aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["portal-zugaenge", kundeId] }),
  });

  return (
    <div
      className={`flex items-start justify-between rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800 ${
        zugang.aktiv ? "" : "opacity-60"
      }`}
    >
      <div>
        <div className="text-sm font-medium text-slate-800 dark:text-stone-100">{zugang.name}</div>
        <div className="text-xs text-slate-400 dark:text-stone-500">{zugang.email}</div>
      </div>
      <button
        onClick={() => toggleMutation.mutate()}
        className="btn-touch shrink-0 rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:bg-stone-800 dark:text-stone-300"
      >
        {zugang.aktiv ? "Deaktivieren" : "Aktivieren"}
      </button>
    </div>
  );
}

function KundenPortalLinkUndLogo({ kunde }: { kunde: Kunde }) {
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const istMandantAdmin =
    currentUser?.role === "mandant_admin" || currentUser?.role === "loesch_operativ";
  const [kopiert, setKopiert] = useState(false);
  const link = `${window.location.origin}/portal/l/${kunde.portal_slug}`;

  const { data: logoUrl } = useQuery({
    queryKey: ["kunde-logo-url", kunde.id],
    queryFn: () => kundenApi.logoUrl(kunde.id),
    enabled: !!kunde.logo_object_key,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => kundenApi.logoUpload(kunde.id, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kunde.id] });
      queryClient.invalidateQueries({ queryKey: ["kunde-logo-url", kunde.id] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: () => kundenApi.logoRemove(kunde.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kunde.id] });
      queryClient.invalidateQueries({ queryKey: ["kunde-logo-url", kunde.id] });
    },
  });

  async function kopieren() {
    await navigator.clipboard.writeText(link);
    setKopiert(true);
    setTimeout(() => setKopiert(false), 2000);
  }

  return (
    <div className="rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">
        Portal-Link für {kunde.name}
      </h2>
      <p className="mb-2 text-xs text-slate-400 dark:text-stone-500">
        Ein Link für den ganzen Kunden -- jeder Mitarbeiter mit eigenem Kundenportal-Zugang meldet
        sich darüber mit seiner eigenen E-Mail und seinem eigenen Passwort an.
      </p>
      <div className="flex items-center gap-2 rounded-md bg-slate-50 px-2 py-1.5 dark:bg-stone-800/60">
        <span className="flex-1 truncate text-xs text-slate-500 dark:text-stone-400">{link}</span>
        <button
          onClick={kopieren}
          className="btn-touch shrink-0 text-xs font-medium text-blue-700 dark:text-blue-400"
        >
          {kopiert ? "Kopiert ✓" : "Link kopieren"}
        </button>
      </div>

      {istMandantAdmin && (
        <div className="mt-3 border-t border-slate-100 pt-3 dark:border-stone-800">
          <h3 className="mb-2 text-xs font-semibold text-slate-500 dark:text-stone-400">
            Logo für die Portal-Login-Seite
          </h3>
          <div className="flex items-center gap-3">
            {kunde.logo_object_key && logoUrl?.url && (
              <img
                src={logoUrl.url}
                alt={`Logo ${kunde.name}`}
                className="h-12 w-12 rounded-md object-contain ring-1 ring-slate-200 dark:ring-stone-700"
              />
            )}
            <label className="btn-touch cursor-pointer rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:bg-stone-800 dark:text-stone-300">
              {kunde.logo_object_key ? "Logo ersetzen" : "Logo hochladen"}
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) uploadMutation.mutate(file);
                  e.target.value = "";
                }}
              />
            </label>
            {kunde.logo_object_key && (
              <button
                onClick={() => removeMutation.mutate()}
                disabled={removeMutation.isPending}
                className="btn-touch text-xs text-red-700 underline disabled:opacity-50 dark:text-red-400"
              >
                Entfernen
              </button>
            )}
          </div>
          {uploadMutation.isError && (
            <p className="mt-1 text-xs text-red-700 dark:text-red-400">
              {uploadMutation.error instanceof ApiError ? uploadMutation.error.message : "Fehler beim Hochladen"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function NeuerPortalZugang({ kundeId }: { kundeId: string }) {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () => kundenportalZugaengeApi.create(kundeId, { name, email, password }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal-zugaenge", kundeId] });
      setZeigen(false);
      setName("");
      setEmail("");
      setPassword("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Zugang konnte nicht angelegt werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 10) {
      setError("Passwort muss mindestens 10 Zeichen haben");
      return;
    }
    createMutation.mutate();
  }

  if (!zeigen) {
    return (
      <button onClick={() => setZeigen(true)} className="btn-touch text-xs text-blue-700 underline dark:text-blue-400">
        + Neuen Zugang anlegen
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-stone-800/60">
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Name des Ansprechpartners"
        className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="E-Mail"
        className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Passwort (mind. 10 Zeichen)"
        className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
      />
      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Anlegen
        </button>
        <button
          type="button"
          onClick={() => setZeigen(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
        >
          Abbrechen
        </button>
      </div>
    </form>
  );
}

function PortalZugaengeVerwaltung({ kundeId }: { kundeId: string }) {
  const { data: zugaenge } = useQuery({
    queryKey: ["portal-zugaenge", kundeId],
    queryFn: () => kundenportalZugaengeApi.list(kundeId),
  });

  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">Kundenportal-Zugänge</h2>
      {!zugaenge || zugaenge.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-stone-500">Noch kein Zugang angelegt.</p>
      ) : (
        <div className="space-y-2">
          {zugaenge.map((z) => (
            <PortalZugangZeile key={z.id} zugang={z} kundeId={kundeId} />
          ))}
        </div>
      )}
      <div className="mt-2">
        <NeuerPortalZugang kundeId={kundeId} />
      </div>
    </div>
  );
}

function DauerauftraegeUebersicht({ kundeId }: { kundeId: string }) {
  const navigate = useNavigate();
  const { data: dauerauftraege } = useQuery({
    queryKey: ["dauerauftraege", kundeId],
    queryFn: () => dauerauftraegeApi.list(kundeId),
  });

  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">Dauer-Aufträge</h2>
      {!dauerauftraege || dauerauftraege.length === 0 ? (
        <EmptyState icon={Repeat} text="Keine Dauer-Aufträge." className="py-4" />
      ) : (
        <div className="space-y-2">
          {dauerauftraege.map((d) => (
            <button
              key={d.id}
              onClick={() => navigate(`/dauerauftraege/${d.id}`)}
              className="card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
            >
              <div>
                <div className="text-sm font-medium text-slate-800 dark:text-stone-100">
                  {d.titel}
                  {d.anzahl_ziele > 1 && (
                    <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-normal text-slate-500 dark:bg-stone-800 dark:text-stone-400">
                      {d.anzahl_ziele} Anlagen
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400 dark:text-stone-500">
                  alle {d.intervall_tage} Tage
                  {d.naechste_faelligkeit_am && ` · nächste Fälligkeit ${d.naechste_faelligkeit_am}`}
                </div>
              </div>
              {!d.aktiv && (
                <span className="rounded-full bg-slate-200 px-2 py-1 text-xs text-slate-600 dark:bg-stone-700 dark:text-stone-300">
                  pausiert
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      <button
        onClick={() => navigate(`/dauerauftraege/neu?kunde_id=${kundeId}`)}
        className="btn-touch mt-2 text-xs text-blue-700 underline dark:text-blue-400"
      >
        + Neuen Dauer-Auftrag anlegen
      </button>
    </div>
  );
}

export function KundeProfilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();
  const [anlageFilter, setAnlageFilter] = useState("");

  const kundenverwaltungAktiv = istModulAktiv(currentUser, "kundenverwaltung");

  const { data: profil, isLoading: profilLoading } = useQuery({
    queryKey: ["kunde-profil", id],
    queryFn: () => kundenApi.profil(id!),
    enabled: !!id && kundenverwaltungAktiv,
  });

  const { data: kunde, isLoading: kundeLoading } = useQuery({
    queryKey: ["kunde", id],
    queryFn: () => kundenApi.get(id!),
    enabled: !!id && !kundenverwaltungAktiv,
  });

  const { data: standorteFuerAnlagen } = useQuery({
    queryKey: ["standorte", id],
    queryFn: () => standorteApi.list(id!),
    enabled: !!id && kundenverwaltungAktiv,
  });

  const anlageNameById = useMemo(
    () => new Map((profil?.anlagen ?? []).map((a: Anlage) => [a.id, a.bezeichnung])),
    [profil?.anlagen]
  );
  const sichtbareVorgaenge = useMemo(
    () =>
      anlageFilter
        ? (profil?.vorgaenge ?? []).filter((v) => v.anlage_id === anlageFilter)
        : profil?.vorgaenge ?? [],
    [profil?.vorgaenge, anlageFilter]
  );

  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteMutation = useMutation({
    mutationFn: () => kundenApi.remove(id!),
    onSuccess: () => navigate("/geschaeft"),
    onError: (err) => setDeleteError(err instanceof ApiError ? err.message : "Löschen fehlgeschlagen"),
  });

  const datenexportMutation = useMutation({
    mutationFn: () => kundenApi.datenexport(id!),
    onSuccess: (blob) => downloadBlob(blob, `Datenexport-${kunde?.name ?? profil?.name ?? id}.json`),
  });

  if (!kundenverwaltungAktiv) {
    if (kundeLoading || !kunde) return <p className="text-center text-slate-500 dark:text-stone-400">Lädt…</p>;
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
          ← Zurück
        </button>
        <div className="rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <div className="text-xs text-slate-400 dark:text-stone-500">{kunde.kundennummer}</div>
          <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">{kunde.name}</h1>
          {kunde.typ && <span className="text-sm text-slate-500 dark:text-stone-400">{kunde.typ}</span>}
        </div>
      </div>
    );
  }

  if (profilLoading || !profil) return <p className="text-center text-slate-500 dark:text-stone-400">Lädt…</p>;

  const kannVerwalten = hatRecht("kunden", "bearbeiten");

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-slate-400 dark:text-stone-500">{profil.kundennummer}</div>
            <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">{profil.name}</h1>
            {profil.typ && <span className="text-sm text-slate-500 dark:text-stone-400">{profil.typ}</span>}
          </div>
          {kannVerwalten && (
            <div className="flex shrink-0 gap-2">
              <button
                onClick={() => datenexportMutation.mutate()}
                disabled={datenexportMutation.isPending}
                title="Alle personenbezogenen Daten zu diesem Kunden herunterladen (Art. 15/20 DSGVO)"
                className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700"
              >
                Datenexport
              </button>
              <button
                onClick={() => {
                  if (
                    window.confirm(
                      `${profil.name} wirklich löschen? Das kann nicht rückgängig gemacht werden.`
                    )
                  ) {
                    deleteMutation.mutate();
                  }
                }}
                className="btn-touch rounded-md bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 dark:bg-red-500/10 dark:text-red-400 dark:hover:bg-red-500/20"
              >
                Löschen
              </button>
            </div>
          )}
        </div>
        {deleteError && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{deleteError}</p>}
        {profil.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {profil.tags.map((t) => (
              <span key={t.id} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-stone-800 dark:text-stone-300">
                #{t.label}
              </span>
            ))}
          </div>
        )}
      </div>

      <Stammdaten
        kundeId={id!}
        adresse={profil.adresse}
        notiz={profil.notiz}
        typ={profil.typ}
        ustIdnr={profil.ust_idnr}
        kannVerwalten={kannVerwalten}
      />

      <AnsprechpartnerVerwaltung kundeId={id!} liste={profil.ansprechpartner} kannVerwalten={kannVerwalten} />

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

      {kannVerwalten && <TechnikerZuweisung kundeId={id!} zugewiesen={profil.techniker} />}

      <StandorteVerwaltung kundeId={id!} kannVerwalten={kannVerwalten} />

      {kannVerwalten && istModulAktiv(currentUser, "kundenportal") && (
        <>
          <KundenPortalLinkUndLogo kunde={profil} />
          <PortalZugaengeVerwaltung kundeId={id!} />
        </>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">Anlagen</h2>
        {profil.anlagen.length === 0 ? (
          <EmptyState icon={Boxes} text="Keine Anlagen." className="py-4" />
        ) : (
          <div className="space-y-2">
            {profil.anlagen.map((a) => (
              <div
                key={a.id}
                className={`flex items-center justify-between rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800 ${
                  a.aktiv ? "" : "opacity-60"
                }`}
              >
                <button onClick={() => navigate(`/anlagen/${a.id}`)} className="btn-touch flex-1 text-left">
                  <div className="text-sm font-medium text-slate-800 dark:text-stone-100">{a.bezeichnung}</div>
                  {a.anlagentyp && <div className="text-xs text-slate-400 dark:text-stone-500">{a.anlagentyp}</div>}
                </button>
                {kannVerwalten && (
                  <AnlageAktivToggle anlage={a} kundeId={id!} />
                )}
              </div>
            ))}
          </div>
        )}
        {kannVerwalten && (
          <div className="mt-2">
            <NeueAnlage
              kundeId={id!}
              standorte={(standorteFuerAnlagen ?? []).filter((s) => s.aktiv)}
            />
          </div>
        )}
      </div>

      {kannVerwalten && <DauerauftraegeUebersicht kundeId={id!} />}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Vorgänge</h2>
          {profil.anlagen.length > 0 && (
            <select
              value={anlageFilter}
              onChange={(e) => setAnlageFilter(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            >
              <option value="">Alle Anlagen</option>
              {profil.anlagen.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.bezeichnung}
                </option>
              ))}
            </select>
          )}
        </div>
        {sichtbareVorgaenge.length === 0 ? (
          <EmptyState icon={Inbox} text="Keine Vorgänge." className="py-4" />
        ) : (
          <div className="space-y-2">
            {sichtbareVorgaenge.map((v) => (
              <button
                key={v.id}
                onClick={() => navigate(`/vorgaenge/${v.id}`)}
                className={`card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800 ${
                  v.status === "storniert" ? "opacity-60 grayscale" : ""
                }`}
              >
                <div>
                  <div className="text-xs text-slate-400 dark:text-stone-500">
                    {v.vorgangsnummer}
                    {v.anlage_id && anlageNameById.get(v.anlage_id) && ` · ${anlageNameById.get(v.anlage_id)}`}
                    {v.dauerauftrag_id && (
                      <>
                        {" · "}
                        <Repeat size={11} strokeWidth={2} className="inline text-amber-500" />
                      </>
                    )}
                  </div>
                  <div className="text-sm font-medium text-slate-800 dark:text-stone-100">{v.titel}</div>
                </div>
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${STATUS_BADGE[v.status]}`}>
                  {v.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
