import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  anlagenApi,
  anlagenFeldDefinitionenApi,
  inventurzyklenApi,
  materialApi,
  pruefzyklenApi,
} from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import { formatStundenAlsHHMM } from "../../utils/duration";
import { istModulAktiv } from "../../utils/module";
import type { AnlageProfil, Adresse } from "../../types";

const STATUS_BADGE: Record<string, string> = {
  neu: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300",
  geplant: "bg-purple-100 text-purple-800 dark:bg-purple-500/15 dark:text-purple-300",
  in_arbeit: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  wartet_kunde: "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300",
  abgeschlossen: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300",
  abgerechnet: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300",
  storniert: "bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500",
};

function faelligkeitsFarbe(datum: string): string {
  const heute = new Date().toISOString().slice(0, 10);
  if (datum < heute) return "text-red-600 dark:text-red-400";
  const in7Tagen = new Date();
  in7Tagen.setDate(in7Tagen.getDate() + 7);
  if (datum <= in7Tagen.toISOString().slice(0, 10)) return "text-amber-600 dark:text-amber-400";
  return "text-slate-500 dark:text-slate-400";
}

function AdresseBearbeiten({
  anlageId,
  adresse,
  kannVerwalten,
}: {
  anlageId: string;
  adresse: Adresse;
  kannVerwalten: boolean;
}) {
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [form, setForm] = useState({
    strasse: adresse.strasse ?? "",
    plz: adresse.plz ?? "",
    ort: adresse.ort ?? "",
  });

  const speichernMutation = useMutation({
    mutationFn: () =>
      anlagenApi.update(anlageId, {
        adresse: { strasse: form.strasse || undefined, plz: form.plz || undefined, ort: form.ort || undefined },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["anlage-profil", anlageId] });
      setBearbeiten(false);
    },
  });

  if (!bearbeiten) {
    const zeile = [adresse.strasse, [adresse.plz, adresse.ort].filter(Boolean).join(" ")]
      .filter(Boolean)
      .join(", ");
    if (!zeile && !kannVerwalten) return null;
    return (
      <div className="mt-1 flex items-center gap-2">
        {zeile ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">{zeile}</p>
        ) : (
          kannVerwalten && <p className="text-sm text-slate-400 dark:text-slate-500">Keine Adresse hinterlegt.</p>
        )}
        {kannVerwalten && (
          <button
            onClick={() => {
              setForm({ strasse: adresse.strasse ?? "", plz: adresse.plz ?? "", ort: adresse.ort ?? "" });
              setBearbeiten(true);
            }}
            className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
          >
            Bearbeiten
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-slate-800/60">
      <input
        value={form.strasse}
        onChange={(e) => setForm({ ...form, strasse: e.target.value })}
        placeholder="Straße + Hausnr."
        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          value={form.plz}
          onChange={(e) => setForm({ ...form, plz: e.target.value })}
          placeholder="PLZ"
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <input
          value={form.ort}
          onChange={(e) => setForm({ ...form, ort: e.target.value })}
          placeholder="Ort"
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending}
          className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => setBearbeiten(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

const FELD_TYP_INPUT: Record<string, string> = { text: "text", zahl: "number", datum: "date" };

function DetailsBearbeiten({ profil, kannVerwalten }: { profil: AnlageProfil; kannVerwalten: boolean }) {
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [form, setForm] = useState({
    hersteller: profil.hersteller ?? "",
    modell: profil.modell ?? "",
    seriennummer: profil.seriennummer ?? "",
    anschaffungsdatum: profil.anschaffungsdatum ?? "",
    notiz: profil.notiz ?? "",
  });
  const [zusatzwerte, setZusatzwerte] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(profil.stammdaten ?? {}).map(([k, v]) => [k, String(v ?? "")])),
  );

  const { data: felder } = useQuery({
    queryKey: ["anlagen-feld-definitionen", profil.anlagentyp],
    queryFn: () => anlagenFeldDefinitionenApi.list(profil.anlagentyp!),
    enabled: !!profil.anlagentyp,
  });

  const speichernMutation = useMutation({
    mutationFn: () =>
      anlagenApi.update(profil.id, {
        hersteller: form.hersteller || null,
        modell: form.modell || null,
        seriennummer: form.seriennummer || null,
        anschaffungsdatum: form.anschaffungsdatum || null,
        notiz: form.notiz || null,
        stammdaten: zusatzwerte,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["anlage-profil", profil.id] });
      setBearbeiten(false);
    },
  });

  const universelleZeilen = [
    ["Hersteller", profil.hersteller],
    ["Modell", profil.modell],
    ["Seriennummer", profil.seriennummer],
    ["Anschaffungsdatum", profil.anschaffungsdatum ? new Date(profil.anschaffungsdatum).toLocaleDateString("de-DE") : null],
  ].filter(([, wert]) => wert) as [string, string][];
  const zusatzZeilen = (felder ?? [])
    .map((f) => [f.feld_name, profil.stammdaten?.[f.feld_name]] as [string, unknown])
    .filter(([, wert]) => wert !== undefined && wert !== null && wert !== "");

  if (!bearbeiten) {
    const hatDetails = universelleZeilen.length > 0 || zusatzZeilen.length > 0 || profil.notiz;
    return (
      <div className="mt-3 border-t border-slate-100 pt-3 dark:border-slate-800">
        <div className="mb-1 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400">Details</h3>
          {kannVerwalten && (
            <button onClick={() => setBearbeiten(true)} className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400">
              Bearbeiten
            </button>
          )}
        </div>
        {!hatDetails ? (
          <p className="text-sm text-slate-400 dark:text-slate-500">Keine Details hinterlegt.</p>
        ) : (
          <dl className="space-y-1 text-sm">
            {universelleZeilen.map(([label, wert]) => (
              <div key={label} className="flex justify-between gap-2">
                <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
                <dd className="text-right text-slate-800 dark:text-slate-100">{wert}</dd>
              </div>
            ))}
            {zusatzZeilen.map(([label, wert]) => (
              <div key={label} className="flex justify-between gap-2">
                <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
                <dd className="text-right text-slate-800 dark:text-slate-100">{String(wert)}</dd>
              </div>
            ))}
            {profil.notiz && (
              <div className="pt-1 text-slate-600 dark:text-slate-300">{profil.notiz}</div>
            )}
          </dl>
        )}
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-2 rounded-md border-t border-slate-100 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-800/60">
      <div className="grid grid-cols-2 gap-2">
        <input
          value={form.hersteller}
          onChange={(e) => setForm({ ...form, hersteller: e.target.value })}
          placeholder="Hersteller"
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <input
          value={form.modell}
          onChange={(e) => setForm({ ...form, modell: e.target.value })}
          placeholder="Modell"
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <input
          value={form.seriennummer}
          onChange={(e) => setForm({ ...form, seriennummer: e.target.value })}
          placeholder="Seriennummer"
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <input
          type="date"
          value={form.anschaffungsdatum}
          onChange={(e) => setForm({ ...form, anschaffungsdatum: e.target.value })}
          title="Anschaffungsdatum"
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
      </div>
      <textarea
        value={form.notiz}
        onChange={(e) => setForm({ ...form, notiz: e.target.value })}
        placeholder="Notiz"
        rows={2}
        className="w-full resize-none rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
      />
      {(felder ?? []).length > 0 && (
        <div className="space-y-2 border-t border-slate-200 pt-2 dark:border-slate-700">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Zusatzfelder für „{profil.anlagentyp}"
          </p>
          {felder!.map((f) => (
            <div key={f.id}>
              <label className="mb-0.5 block text-xs text-slate-500 dark:text-slate-400">{f.feld_name}</label>
              <input
                type={FELD_TYP_INPUT[f.feld_typ]}
                value={zusatzwerte[f.feld_name] ?? ""}
                onChange={(e) => setZusatzwerte({ ...zusatzwerte, [f.feld_name]: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending}
          className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => setBearbeiten(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

function MaterialInLager({ lagerId }: { lagerId: string }) {
  const { data: material } = useQuery({
    queryKey: ["material", "lager", lagerId],
    queryFn: () => materialApi.list(lagerId),
  });

  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-slate-400">Material an diesem Lagerort</h2>
      {!material || material.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">Kein Material an diesem Lagerort.</p>
      ) : (
        <div className="space-y-2">
          {material.map((m) => {
            const bestand = m.bestaende.find((b) => b.lager_id === lagerId);
            const unterbestand = bestand ? Number(bestand.menge) <= Number(m.mindestbestand) : false;
            return (
              <div
                key={m.id}
                className="flex items-center justify-between rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
              >
                <span className="text-sm font-medium text-slate-800 dark:text-slate-100">{m.bezeichnung}</span>
                <span
                  className={`text-sm font-medium ${
                    unterbestand ? "text-red-600 dark:text-red-400" : "text-slate-700 dark:text-slate-300"
                  }`}
                >
                  {bestand?.menge ?? "0"} {m.einheit}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function AnlageProfilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const kannVerwalten =
    currentUser?.role === "mandant_admin" || currentUser?.role === "disponent";

  const [showForm, setShowForm] = useState(false);
  const [bezeichnung, setBezeichnung] = useState("");
  const [intervall, setIntervall] = useState("12");
  const [inventurIntervallTage, setInventurIntervallTage] = useState("90");

  const { data: profil, isLoading } = useQuery({
    queryKey: ["anlage-profil", id],
    queryFn: () => anlagenApi.profil(id!),
    enabled: !!id,
  });
  const pruefzyklenAktiv = istModulAktiv(currentUser, "pruefzyklen");
  const fahrzeugeAktiv = istModulAktiv(currentUser, "fahrzeuge");
  const materialAktiv = istModulAktiv(currentUser, "material");

  const { data: pruefzyklen } = useQuery({
    queryKey: ["pruefzyklen", id],
    queryFn: () => pruefzyklenApi.list(id!),
    enabled: !!id && pruefzyklenAktiv,
  });
  const { data: inventurzyklen } = useQuery({
    queryKey: ["inventurzyklen", id],
    queryFn: () => inventurzyklenApi.list(id!),
    enabled: !!id && profil?.objekttyp !== "kundenanlage" && fahrzeugeAktiv,
  });
  const inventurzyklus = inventurzyklen?.[0];

  const createMutation = useMutation({
    mutationFn: pruefzyklenApi.create,
    onSuccess: () => {
      setShowForm(false);
      setBezeichnung("");
      setIntervall("12");
      queryClient.invalidateQueries({ queryKey: ["pruefzyklen", id] });
    },
  });

  const markiereGeprueftMutation = useMutation({
    mutationFn: (pruefzyklusId: string) =>
      pruefzyklenApi.update(pruefzyklusId, {
        letzte_pruefung_am: new Date().toISOString().slice(0, 10),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pruefzyklen", id] }),
  });

  const inventurAnlegenMutation = useMutation({
    mutationFn: () =>
      inventurzyklenApi.create({ lager_id: id!, intervall_tage: Number(inventurIntervallTage) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inventurzyklen", id] }),
  });

  const inventurDurchgefuehrtMutation = useMutation({
    mutationFn: () =>
      inventurzyklenApi.update(inventurzyklus!.id, {
        letzte_inventur_am: new Date().toISOString().slice(0, 10),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inventurzyklen", id] }),
  });

  const inventurAktivMutation = useMutation({
    mutationFn: () => inventurzyklenApi.update(inventurzyklus!.id, { aktiv: !inventurzyklus!.aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inventurzyklen", id] }),
  });

  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteMutation = useMutation({
    mutationFn: () => anlagenApi.remove(id!),
    onSuccess: () => navigate(profil?.kunde ? `/kunden/${profil.kunde.id}` : "/geschaeft"),
    onError: (err) => setDeleteError(err instanceof ApiError ? err.message : "Löschen fehlgeschlagen"),
  });

  if (isLoading || !profil) return <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-slate-400">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <div className="flex items-start justify-between">
          <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">{profil.bezeichnung}</h1>
          {kannVerwalten && (
            <button
              onClick={() => {
                if (
                  window.confirm(
                    `${profil.bezeichnung} wirklich löschen? Das kann nicht rückgängig gemacht werden.`
                  )
                ) {
                  deleteMutation.mutate();
                }
              }}
              className="btn-touch shrink-0 rounded-md bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 dark:bg-red-500/10 dark:text-red-400 dark:hover:bg-red-500/20"
            >
              Löschen
            </button>
          )}
        </div>
        {deleteError && <p className="mt-1 text-sm text-red-700 dark:text-red-400">{deleteError}</p>}
        {profil.kunde ? (
          <button
            onClick={() => navigate(`/kunden/${profil.kunde!.id}`)}
            className="text-sm text-blue-700 underline-offset-2 hover:underline dark:text-blue-400"
          >
            {profil.kunde.name}
          </button>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Internes Objekt (kein Kundenbezug)</p>
        )}
        <AdresseBearbeiten anlageId={id!} adresse={profil.adresse} kannVerwalten={kannVerwalten} />
        {profil.anlagentyp && <p className="text-xs text-slate-400 dark:text-slate-500">{profil.anlagentyp}</p>}
        {profil.qr_code && (
          <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">QR-Code: {profil.qr_code}</p>
        )}
        {profil.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {profil.tags.map((t) => (
              <span
                key={t.id}
                className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300"
              >
                #{t.label}
              </span>
            ))}
          </div>
        )}
        <DetailsBearbeiten profil={profil} kannVerwalten={kannVerwalten} />
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-slate-400">Auswertung</h2>
        <div className="flex flex-wrap gap-2">
          {Object.entries(profil.vorgaenge_nach_status).map(([status, anzahl]) => (
            <span
              key={status}
              className={`rounded-full px-2 py-1 text-xs font-semibold ${
                STATUS_BADGE[status] ?? "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
              }`}
            >
              {anzahl}× {status}
            </span>
          ))}
        </div>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Erfasste Zeit gesamt:{" "}
          <span className="font-medium">
            {formatStundenAlsHHMM(Number(profil.zeiterfassung_stunden_gesamt))} Std.
          </span>
        </p>
      </div>

      {profil.objekttyp !== "kundenanlage" && materialAktiv && <MaterialInLager lagerId={id!} />}

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-slate-400">Vorgänge</h2>
        {profil.vorgaenge.length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500">Keine Vorgänge.</p>
        ) : (
          <div className="space-y-2">
            {profil.vorgaenge.map((v) => (
              <button
                key={v.id}
                onClick={() => navigate(`/vorgaenge/${v.id}`)}
                className={`btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800 ${
                  v.status === "storniert" ? "opacity-60 grayscale" : ""
                }`}
              >
                <div>
                  <div className="text-xs text-slate-400 dark:text-slate-500">
                    {v.vorgangsnummer}
                    {v.dauerauftrag_id && " · 🔁"}
                  </div>
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{v.titel}</div>
                </div>
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${STATUS_BADGE[v.status]}`}>
                  {v.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {pruefzyklenAktiv && (
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">Prüfzyklen</h2>
          {kannVerwalten && (
            <button
              onClick={() => setShowForm((v) => !v)}
              className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
            >
              {showForm ? "Abbrechen" : "+ Neuer Zyklus"}
            </button>
          )}
        </div>

        {showForm && (
          <div className="mb-2 space-y-2 rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
            <input
              value={bezeichnung}
              onChange={(e) => setBezeichnung(e.target.value)}
              placeholder="z.B. E-Check ortsveränderliche Geräte"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-500 dark:text-slate-400">Intervall (Monate)</label>
              <input
                type="number"
                min={1}
                value={intervall}
                onChange={(e) => setIntervall(e.target.value)}
                className="w-20 rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
              <button
                disabled={!bezeichnung || createMutation.isPending}
                onClick={() =>
                  createMutation.mutate({
                    anlage_id: id!,
                    bezeichnung,
                    intervall_monate: Number(intervall),
                  })
                }
                className="btn-touch ml-auto rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Anlegen
              </button>
            </div>
          </div>
        )}

        {(pruefzyklen ?? []).length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500">Keine Prüfzyklen erfasst.</p>
        ) : (
          <div className="space-y-2">
            {pruefzyklen!.map((z) => (
              <div
                key={z.id}
                className="rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
              >
                <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{z.bezeichnung}</div>
                <div className="mt-1 flex items-center justify-between">
                  <span className={`text-sm font-medium ${faelligkeitsFarbe(z.naechste_pruefung_am)}`}>
                    Fällig: {new Date(z.naechste_pruefung_am).toLocaleDateString("de-DE")}
                  </span>
                  {kannVerwalten && (
                    <button
                      onClick={() => markiereGeprueftMutation.mutate(z.id)}
                      disabled={markiereGeprueftMutation.isPending}
                      className="btn-touch rounded-md bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
                    >
                      Prüfung erfolgt (heute)
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      )}

      {profil.objekttyp !== "kundenanlage" && fahrzeugeAktiv && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-slate-400">Inventur</h2>
          {!inventurzyklus ? (
            kannVerwalten ? (
              <div className="space-y-2 rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
                <p className="text-sm text-slate-400 dark:text-slate-500">
                  Noch kein Inventurzyklus für diesen Lagerort eingerichtet.
                </p>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-slate-500 dark:text-slate-400">Intervall (Tage)</label>
                  <input
                    type="number"
                    min={1}
                    value={inventurIntervallTage}
                    onChange={(e) => setInventurIntervallTage(e.target.value)}
                    className="w-20 rounded-md border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                  />
                  <button
                    disabled={inventurAnlegenMutation.isPending}
                    onClick={() => inventurAnlegenMutation.mutate()}
                    className="btn-touch ml-auto rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                  >
                    Einrichten
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-400 dark:text-slate-500">Kein Inventurzyklus eingerichtet.</p>
            )
          ) : (
            <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
              <div className="flex items-center justify-between">
                <span className={`text-sm font-medium ${faelligkeitsFarbe(inventurzyklus.naechste_inventur_am)}`}>
                  Fällig: {new Date(inventurzyklus.naechste_inventur_am).toLocaleDateString("de-DE")}
                </span>
                {!inventurzyklus.aktiv && (
                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                    pausiert
                  </span>
                )}
              </div>
              {inventurzyklus.letzte_inventur_am && (
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                  Zuletzt durchgeführt: {new Date(inventurzyklus.letzte_inventur_am).toLocaleDateString("de-DE")}
                </p>
              )}
              {kannVerwalten && (
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => inventurDurchgefuehrtMutation.mutate()}
                    disabled={inventurDurchgefuehrtMutation.isPending || !inventurzyklus.aktiv}
                    className="btn-touch flex-1 rounded-md bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
                  >
                    Inventur durchgeführt (heute)
                  </button>
                  <button
                    onClick={() => inventurAktivMutation.mutate()}
                    disabled={inventurAktivMutation.isPending}
                    className="btn-touch flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
                  >
                    {inventurzyklus.aktiv ? "Deaktivieren" : "Reaktivieren"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
