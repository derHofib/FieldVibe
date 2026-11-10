import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { kundeTypLabel } from "../../config/kundeDarstellung";
import { statusLabel } from "../../config/vorgangDarstellung";
import { Boxes, ClipboardList, Download, Inbox, MapPin, MoreHorizontal, Repeat, Trash2 } from "lucide-react";
import { useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  anlagenApi,
  dauerauftraegeApi,
  kundenApi,
  kundenportalZugaengeApi,
  leistungsverzeichnisApi,
  leistungsverzeichnisseApi,
  standorteApi,
  usersApi,
} from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { AnsprechpartnerVerwaltung } from "../../components/AnsprechpartnerVerwaltung";
import { PulldownMenu, type PulldownItem } from "../../components/apple/PulldownMenu";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { EmailSection } from "../../components/EmailSection";
import { EmptyState } from "../../components/EmptyState";
import { ERechnungFelder, zeigeERechnungFelder } from "../../components/kunde/ERechnungFelder";
import { FehlerMeldung } from "../../components/Hinweiskasten";
import { Nachweis13bFeld, Nachweis13bStatus } from "../../components/kunde/Nachweis13b";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import { validiereDebitorenkonto } from "../../utils/datev";
import { downloadBlob } from "../../utils/download";
import { E_RECHNUNG_FORMAT_KURZ, type ERechnungFormat, leitwegIdFehler } from "../../utils/eRechnungVersand";
import type {
  Adresse,
  Anlage,
  Kunde,
  KundenportalZugang,
  LeistungsverzeichnisPosition,
  Standort,
  User,
} from "../../types";
import { MIN_PASSWORT_LAENGE } from "../../utils/passwort";
import { FehlerZustand } from "../../components/FehlerZustand";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { DetailSkeleton } from "../../components/Skeleton";

function leereAdresse(adresse: Adresse | null): { strasse: string; plz: string; ort: string } {
  return { strasse: adresse?.strasse ?? "", plz: adresse?.plz ?? "", ort: adresse?.ort ?? "" };
}

function Stammdaten({
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

const STATUS_BADGE: Record<string, string> = {
  neu: "border border-tint text-tint ",
  geplant: "border border-purple-400 text-purple-700 dark:border-purple-600 dark:text-purple-300",
  in_arbeit: "border border-st-arbeit text-st-arbeit ",
  wartet_kunde: "border border-st-wartet text-st-wartet",
  abgeschlossen: "border border-st-erledigt text-st-erledigt ",
  abgerechnet: "border border-sep text-label ",
  storniert: "border border-sep text-label2",
};

function TechnikerZuweisung({ kundeId, zugewiesen }: { kundeId: string; zugewiesen: User[] }) {
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

const FELD_KLASSE = "btn-touch w-full border border-sep bg-transparent px-3 py-2 text-label";
const NEU_BUTTON_KLASSE = "btn-touch btn-ap px-4 py-2 text-sm font-medium";

interface FeldProps {
  id: string;
  "aria-invalid": boolean;
  "aria-describedby"?: string;
}

/** Beschriftetes Formularfeld mit Pflichtstern und Feldfehler; das Eingabeelement bekommt id/aria über Render-Prop. */
function Feld({
  label,
  pflicht = false,
  fehler,
  children,
}: {
  label: string;
  pflicht?: boolean;
  fehler?: string | null;
  children: (props: FeldProps) => ReactNode;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-label">
        {label}
        {pflicht && <span aria-hidden="true" className="text-st-fehlt"> *</span>}
      </label>
      {children({ id, "aria-invalid": !!fehler, "aria-describedby": fehler ? `${id}-fehler` : undefined })}
      {fehler && (
        <p id={`${id}-fehler`} role="alert" className="mt-1 text-xs text-st-fehlt">
          {fehler}
        </p>
      )}
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
  const [bezeichnungFehler, setBezeichnungFehler] = useState<string | null>(null);
  const [standortFehler, setStandortFehler] = useState<string | null>(null);

  const neuerStandortMutation = useMutation({
    meta: { erfolg: "Angelegt" },
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
    meta: { erfolg: "Angelegt" },
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
      setBezeichnungFehler("Bitte eine Bezeichnung eingeben.");
      return;
    }
    setBezeichnungFehler(null);
    createMutation.mutate();
  }

  return (
    <>
      <button onClick={() => setZeigen(true)} className={NEU_BUTTON_KLASSE}>
        + Neue Anlage
      </button>
      <AnlegenPanel offen={zeigen} titel="Neue Anlage" onClose={() => setZeigen(false)}>
        <form onSubmit={handleSubmit} className="space-y-3 p-4">
          <Feld label="Bezeichnung" pflicht fehler={bezeichnungFehler}>
            {(p) => <input {...p} autoFocus value={bezeichnung} onChange={(e) => setBezeichnung(e.target.value)} className={FELD_KLASSE} />}
          </Feld>
          <Feld label="Typ (optional)">
            {(p) => (
              <input
                {...p}
                value={anlagentyp}
                onChange={(e) => setAnlagentyp(e.target.value)}
                placeholder="z.B. Hauptverteilung, PV-Anlage, Wallbox"
                className={FELD_KLASSE}
              />
            )}
          </Feld>
          {zeigeNeuerStandort ? (
            <Feld label="Neuer Standort" pflicht fehler={standortFehler}>
              {(p) => (
                <div className="flex gap-2">
                  <input
                    {...p}
                    autoFocus
                    value={neuerStandortName}
                    onChange={(e) => setNeuerStandortName(e.target.value)}
                    placeholder="z.B. Filiale Nord"
                    className="btn-touch flex-1 border border-sep bg-transparent px-3 py-2 text-label"
                  />
                  <button
                    type="button"
                    disabled={neuerStandortMutation.isPending}
                    onClick={() => {
                      if (!neuerStandortName.trim()) {
                        setStandortFehler("Bitte eine Bezeichnung eingeben.");
                        return;
                      }
                      setStandortFehler(null);
                      neuerStandortMutation.mutate();
                    }}
                    className="btn-touch btn-ap shrink-0 px-4 text-sm font-medium"
                  >
                    Anlegen
                  </button>
                  <button type="button" onClick={() => setZeigeNeuerStandort(false)} className="btn-touch btn-ap shrink-0 px-4 text-sm font-medium">
                    Abbrechen
                  </button>
                </div>
              )}
            </Feld>
          ) : (
            <Feld label="Standort (optional)">
              {(p) => (
                <div className="space-y-2">
                  <select {...p} value={standortId} onChange={(e) => setStandortId(e.target.value)} className={FELD_KLASSE}>
                    <option value="">Kein Standort</option>
                    {standorte.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.bezeichnung}
                      </option>
                    ))}
                  </select>
                  <button type="button" onClick={() => setZeigeNeuerStandort(true)} className={NEU_BUTTON_KLASSE}>
                    + Neuer Standort
                  </button>
                </div>
              )}
            </Feld>
          )}
          {error && (
            <p role="alert" className="text-sm text-st-fehlt">
              {error}
            </p>
          )}
          <button type="submit" disabled={createMutation.isPending} className="btn-touch btn-ap-primary w-full rounded-md py-2 text-sm font-medium">
            Anlegen
          </button>
        </form>
      </AnlegenPanel>
    </>
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
  const [bezeichnungFehler, setBezeichnungFehler] = useState<string | null>(null);

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
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
      setBezeichnungFehler("Bitte eine Bezeichnung eingeben.");
      return;
    }
    setBezeichnungFehler(null);
    createMutation.mutate();
  }

  return (
    <>
      <button onClick={() => setZeigen(true)} className={NEU_BUTTON_KLASSE}>
        + Neuer Standort
      </button>
      <AnlegenPanel offen={zeigen} titel="Neuer Standort" onClose={() => setZeigen(false)}>
        <form onSubmit={handleSubmit} className="space-y-3 p-4">
          <Feld label="Bezeichnung" pflicht fehler={bezeichnungFehler}>
            {(p) => (
              <input
                {...p}
                autoFocus
                value={bezeichnung}
                onChange={(e) => setBezeichnung(e.target.value)}
                placeholder="z.B. Filiale Nord"
                className={FELD_KLASSE}
              />
            )}
          </Feld>
          <Feld label="Straße und Hausnummer">
            {(p) => <input {...p} value={strasse} onChange={(e) => setStrasse(e.target.value)} className={FELD_KLASSE} />}
          </Feld>
          <div className="grid grid-cols-2 gap-3">
            <Feld label="PLZ">{(p) => <input {...p} value={plz} onChange={(e) => setPlz(e.target.value)} className={FELD_KLASSE} />}</Feld>
            <Feld label="Ort">{(p) => <input {...p} value={ort} onChange={(e) => setOrt(e.target.value)} className={FELD_KLASSE} />}</Feld>
          </div>
          {error && (
            <p role="alert" className="text-sm text-st-fehlt">
              {error}
            </p>
          )}
          <button type="submit" disabled={createMutation.isPending} className="btn-touch btn-ap-primary w-full rounded-md py-2 text-sm font-medium">
            Anlegen
          </button>
        </form>
      </AnlegenPanel>
    </>
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
      <h2 className="mb-2 text-sm font-semibold text-label2">Standorte</h2>
      {!standorte || standorte.length === 0 ? (
        <EmptyState icon={MapPin} text="Keine Standorte." className="py-4" />
      ) : (
        <div className="space-y-2">
          {standorte.map((s) => (
            <div
              key={s.id}
              className={`flex items-center justify-between card-ap p-3 ${
                s.aktiv ? "" : "opacity-60"
              }`}
            >
              <button
                onClick={() => navigate(`/standorte/${s.id}`)}
                className="btn-touch flex-1 text-left"
              >
                <div className="text-sm font-medium text-label hover:underline">
                  {s.bezeichnung}
                </div>
                {s.adresse?.ort && (
                  <div className="text-xs text-label2">
                    {[s.adresse.strasse, [s.adresse.plz, s.adresse.ort].filter(Boolean).join(" ")]
                      .filter(Boolean)
                      .join(", ")}
                  </div>
                )}
              </button>
              {kannVerwalten && (
                <button
                  onClick={() => toggleAktivMutation.mutate({ id: s.id, aktiv: !s.aktiv })}
                  className="btn-touch shrink-0 btn-ap px-3 py-1.5 text-xs font-semibold"
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

function NeueLvPosition({ kundeId, kundeName, zielLvId }: { kundeId: string; kundeName: string; zielLvId: string | undefined }) {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [bezeichnung, setBezeichnung] = useState("");
  const [einheit, setEinheit] = useState("Stk");
  const [einzelpreis, setEinzelpreis] = useState("");
  const [istStundensatz, setIstStundensatz] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bezeichnungFehler, setBezeichnungFehler] = useState<string | null>(null);

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    // Ohne bestehendes kundenspezifisches LV wird eines still angelegt --
    // die Seite bietet bewusst weiterhin das Anlegen "in einem Schritt", die
    // Zwei-Stufen-Struktur (erst LV, dann Position) ist nur auf der
    // eigenstaendigen Verwaltungsseite sichtbar (siehe
    // LeistungsverzeichnisDetailPage.tsx).
    mutationFn: async () => {
      const lvId =
        zielLvId ??
        (
          await leistungsverzeichnisseApi.create({
            name: `Kundenspezifisch – ${kundeName}`,
            kunden_ids: [kundeId],
          })
        ).id;
      return leistungsverzeichnisApi.create({
        leistungsverzeichnis_id: lvId,
        bezeichnung,
        einheit,
        einzelpreis: einzelpreis || undefined,
        ist_stundensatz: istStundensatz,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnis", kundeId] });
      queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnisse"] });
      setZeigen(false);
      setBezeichnung("");
      setEinheit("Stk");
      setEinzelpreis("");
      setIstStundensatz(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Position konnte nicht angelegt werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!bezeichnung.trim()) {
      setBezeichnungFehler("Bitte eine Bezeichnung eingeben.");
      return;
    }
    setBezeichnungFehler(null);
    createMutation.mutate();
  }

  return (
    <>
      <button onClick={() => setZeigen(true)} className={NEU_BUTTON_KLASSE}>
        + Neue Position
      </button>
      <AnlegenPanel offen={zeigen} titel="Neue Position" onClose={() => setZeigen(false)}>
        <form onSubmit={handleSubmit} className="space-y-3 p-4">
          <Feld label="Bezeichnung" pflicht fehler={bezeichnungFehler}>
            {(p) => (
              <input
                {...p}
                autoFocus
                value={bezeichnung}
                onChange={(e) => setBezeichnung(e.target.value)}
                placeholder="z.B. Stundensatz Monteur, Anfahrtspauschale"
                className={FELD_KLASSE}
              />
            )}
          </Feld>
          <div className="grid grid-cols-2 gap-3">
            <Feld label="Einheit">{(p) => <input {...p} value={einheit} onChange={(e) => setEinheit(e.target.value)} className={FELD_KLASSE} />}</Feld>
            <Feld label="Einzelpreis (€)">
              {(p) => <input {...p} type="number" step="0.01" value={einzelpreis} onChange={(e) => setEinzelpreis(e.target.value)} className={FELD_KLASSE} />}
            </Feld>
          </div>
          <label className="flex items-center gap-2 text-sm text-label">
            <input
              type="checkbox"
              checked={istStundensatz}
              onChange={(e) => setIstStundensatz(e.target.checked)}
              className="h-4 w-4 rounded border-sep "
            />
            Als Stundenverrechnungssatz in der Arbeitszeit wählbar
          </label>
          {error && (
            <p role="alert" className="text-sm text-st-fehlt">
              {error}
            </p>
          )}
          <button type="submit" disabled={createMutation.isPending} className="btn-touch btn-ap-primary w-full rounded-md py-2 text-sm font-medium">
            Anlegen
          </button>
        </form>
      </AnlegenPanel>
    </>
  );
}

function LvPositionZeile({ position, kundeId }: { position: LeistungsverzeichnisPosition; kundeId: string }) {
  const bestaetigen = useBestaetigung();
  const queryClient = useQueryClient();
  const removeMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: () => leistungsverzeichnisApi.remove(position.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnis", kundeId] }),
  });

  return (
    <div className="flex items-center justify-between card-ap p-3">
      <div>
        <div className="text-sm font-medium text-label">
          {position.bezeichnung}
          {position.ist_stundensatz && (
            <span className="ml-2 rounded-full bg-cyan-100 px-2 py-0.5 text-xs font-normal text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-400">
              SVS
            </span>
          )}
        </div>
        <div className="text-xs text-label2">
          {position.einzelpreis} € / {position.einheit}
        </div>
      </div>
      <button
        onClick={async () => {
          if (await bestaetigen({ titel: `"${position.bezeichnung}" löschen?`, bestaetigenLabel: "Löschen" })) removeMutation.mutate();
        }}
        disabled={removeMutation.isPending}
        className="btn-touch shrink-0 rounded-md bg-st-fehlt-bg px-3 py-1.5 text-xs font-semibold text-st-fehlt hover:bg-st-fehlt-bg dark:hover:bg-st-fehlt-dot"
      >
        Löschen
      </button>
    </div>
  );
}

function LeistungsverzeichnisVerwaltung({
  kundeId,
  kundeName,
  kannVerwalten,
}: {
  kundeId: string;
  kundeName: string;
  kannVerwalten: boolean;
}) {
  // Die Kunden-Zuweisung sitzt am Leistungsverzeichnis (LV), nicht mehr an
  // der einzelnen Position -- hier zaehlt daher nur, was aus einem diesem
  // Kunden zugewiesenen LV stammt; der komplette Katalog inkl. Verwaltung
  // der LVs selbst wird zentral unter "Leistungsverzeichnisse" gepflegt.
  const { data: lvs } = useQuery({
    queryKey: ["leistungsverzeichnisse"],
    queryFn: () => leistungsverzeichnisseApi.list(),
  });
  const zugewieseneLvs = (lvs ?? []).filter((lv) => lv.kunden_ids.includes(kundeId));
  const zugewieseneLvIds = new Set(zugewieseneLvs.map((lv) => lv.id));

  const { data: alle } = useQuery({
    queryKey: ["leistungsverzeichnis", kundeId],
    queryFn: () => leistungsverzeichnisApi.list(kundeId),
  });
  const positionen = alle?.filter((p) => zugewieseneLvIds.has(p.leistungsverzeichnis_id));

  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold text-label2">
        Leistungsverzeichnis
        <span className="ml-2 font-normal text-label2">(optional, kundenspezifisch)</span>
      </h2>
      {!positionen || positionen.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          text="Kein Leistungsverzeichnis angelegt."
          className="py-4"
        />
      ) : (
        <div className="space-y-2">
          {positionen.map((p) => (
            <LvPositionZeile key={p.id} position={p} kundeId={kundeId} />
          ))}
        </div>
      )}
      {kannVerwalten && (
        <div className="mt-2">
          <NeueLvPosition kundeId={kundeId} kundeName={kundeName} zielLvId={zugewieseneLvs[0]?.id} />
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
      className="btn-touch shrink-0 btn-ap px-3 py-1.5 text-xs font-semibold"
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
      className={`flex items-start justify-between card-ap p-3 ${
        zugang.aktiv ? "" : "opacity-60"
      }`}
    >
      <div>
        <div className="text-sm font-medium text-label">{zugang.name}</div>
        <div className="text-xs text-label2">{zugang.email}</div>
      </div>
      <button
        onClick={() => toggleMutation.mutate()}
        className="btn-touch shrink-0 btn-ap px-3 py-1.5 text-xs font-semibold"
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
    meta: { erfolg: "Hochgeladen" },
    mutationFn: (file: File) => kundenApi.logoUpload(kunde.id, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kunde.id] });
      queryClient.invalidateQueries({ queryKey: ["kunde-logo-url", kunde.id] });
    },
  });

  const removeMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
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
    <div className="card-ap p-4">
      <h2 className="mb-2 text-sm font-semibold text-label2">
        Portal-Link für {kunde.name}
      </h2>
      <p className="mb-2 text-xs text-label2">
        Ein Link für den ganzen Kunden -- jeder Mitarbeiter mit eigenem Kundenportal-Zugang meldet
        sich darüber mit seiner eigenen E-Mail und seinem eigenen Passwort an.
      </p>
      <div className="flex items-center gap-2 rounded-md bg-fill px-2 py-1.5">
        <span className="flex-1 truncate text-xs text-label2">{link}</span>
        <button
          onClick={kopieren}
          className="btn-touch shrink-0 text-xs font-medium text-tint "
        >
          {kopiert ? "Kopiert ✓" : "Link kopieren"}
        </button>
      </div>

      {istMandantAdmin && (
        <div className="mt-3 border-t border-sep pt-3 ">
          <h3 className="mb-2 text-xs font-semibold text-label2">
            Logo für die Portal-Login-Seite
          </h3>
          <div className="flex items-center gap-3">
            {kunde.logo_object_key && logoUrl?.url && (
              <img
                src={logoUrl.url}
                alt={`Logo ${kunde.name}`}
                className="h-12 w-12 rounded-md object-contain ring-1 ring-sep "
              />
            )}
            <label className="btn-touch cursor-pointer btn-ap px-3 py-1.5 text-xs font-semibold">
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
                className="btn-touch text-xs text-st-fehlt underline disabled:opacity-50 "
              >
                Entfernen
              </button>
            )}
          </div>
          {uploadMutation.isError && (
            <p className="mt-1 text-xs text-st-fehlt ">
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
  const [fehler, setFehler] = useState<{ name?: string; email?: string; passwort?: string }>({});

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
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
    const f = {
      name: name.trim() ? undefined : "Bitte einen Namen eingeben.",
      email: /\S+@\S+\.\S+/.test(email) ? undefined : "Bitte eine gültige E-Mail-Adresse eingeben.",
      passwort: password.length >= MIN_PASSWORT_LAENGE ? undefined : `Das Passwort braucht mindestens ${MIN_PASSWORT_LAENGE} Zeichen.`,
    };
    setFehler(f);
    if (f.name || f.email || f.passwort) return;
    createMutation.mutate();
  }

  return (
    <>
      <button onClick={() => setZeigen(true)} className={NEU_BUTTON_KLASSE}>
        + Neuer Zugang
      </button>
      <AnlegenPanel offen={zeigen} titel="Neuer Kundenportal-Zugang" onClose={() => setZeigen(false)}>
        <form onSubmit={handleSubmit} className="space-y-3 p-4" noValidate>
          <Feld label="Name des Ansprechpartners" pflicht fehler={fehler.name}>
            {(p) => <input {...p} autoFocus value={name} onChange={(e) => setName(e.target.value)} className={FELD_KLASSE} />}
          </Feld>
          <Feld label="E-Mail" pflicht fehler={fehler.email}>
            {(p) => <input {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={FELD_KLASSE} />}
          </Feld>
          <Feld label={`Passwort (mind. ${MIN_PASSWORT_LAENGE} Zeichen)`} pflicht fehler={fehler.passwort}>
            {(p) => (
              <input {...p} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={FELD_KLASSE} />
            )}
          </Feld>
          {error && (
            <p role="alert" className="text-sm text-st-fehlt">
              {error}
            </p>
          )}
          <button type="submit" disabled={createMutation.isPending} className="btn-touch btn-ap-primary w-full rounded-md py-2 text-sm font-medium">
            Anlegen
          </button>
        </form>
      </AnlegenPanel>
    </>
  );
}

function PortalZugaengeVerwaltung({ kundeId }: { kundeId: string }) {
  const { data: zugaenge } = useQuery({
    queryKey: ["portal-zugaenge", kundeId],
    queryFn: () => kundenportalZugaengeApi.list(kundeId),
  });

  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold text-label2">Kundenportal-Zugänge</h2>
      {!zugaenge || zugaenge.length === 0 ? (
        <p className="text-sm text-label2">Noch kein Zugang angelegt.</p>
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
      <h2 className="mb-2 text-sm font-semibold text-label2">Dauer-Aufträge</h2>
      {!dauerauftraege || dauerauftraege.length === 0 ? (
        <EmptyState icon={Repeat} text="Keine Dauer-Aufträge." className="py-4" />
      ) : (
        <div className="space-y-2">
          {dauerauftraege.map((d) => (
            <button
              key={d.id}
              onClick={() => navigate(`/dauerauftraege/${d.id}`)}
              className="card-interactive btn-touch flex w-full items-center justify-between card-ap p-3 text-left"
            >
              <div>
                <div className="text-sm font-medium text-label">
                  {d.titel}
                  {d.anzahl_ziele > 1 && (
                    <span className="ml-2 border border-sep px-2 py-0.5 text-xs font-normal text-label">
                      {d.anzahl_ziele} Anlagen
                    </span>
                  )}
                </div>
                <div className="text-xs text-label2">
                  alle {d.intervall_tage} Tage
                  {d.naechste_faelligkeit_am && ` · nächste Fälligkeit ${d.naechste_faelligkeit_am}`}
                </div>
              </div>
              {!d.aktiv && (
                <span className="border border-sep px-2 py-1 text-xs text-label">
                  pausiert
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      <button
        onClick={() => navigate(`/dauerauftraege/neu?kunde_id=${kundeId}`)}
        className={`${NEU_BUTTON_KLASSE} mt-2`}
      >
        + Neuer Dauerauftrag
      </button>
    </div>
  );
}

type KundeTab = "uebersicht" | "vorgaenge" | "anlagen" | "kommunikation";
const KUNDE_TABS: KundeTab[] = ["uebersicht", "vorgaenge", "anlagen", "kommunikation"];

export function KundeProfilePage() {
  const bestaetigen = useBestaetigung();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();
  const [anlageFilter, setAnlageFilter] = useState("");
  // Aktiver Tab im Query-Parameter, damit Reload/Deep-Link denselben Tab zeigen.
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab: KundeTab = KUNDE_TABS.includes(tabParam as KundeTab) ? (tabParam as KundeTab) : "uebersicht";

  const kundenverwaltungAktiv = istModulAktiv(currentUser, "kundenverwaltung");

  const { data: profil, isLoading: profilLoading, error: profilFehler, refetch: profilNeu } = useQuery({
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
    meta: { erfolg: "Gelöscht" },
    mutationFn: () => kundenApi.remove(id!),
    onSuccess: () => navigate("/kunden"),
    onError: (err) => setDeleteError(err instanceof ApiError ? err.message : "Löschen fehlgeschlagen"),
  });

  const datenexportMutation = useMutation({
    mutationFn: () => kundenApi.datenexport(id!),
    onSuccess: (blob) => downloadBlob(blob, `Datenexport-${kunde?.name ?? profil?.name ?? id}.json`),
  });

  if (!kundenverwaltungAktiv) {
    if (kundeLoading || !kunde) return <DetailSkeleton />;
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        <div className="card-ap p-4">
          <div className="text-xs text-label2">{kunde.kundennummer}</div>
          <h1 className="text-lg font-bold text-label">{kunde.name}</h1>
          {kunde.typ && <span className="text-sm text-label2">{kundeTypLabel(kunde.typ)}</span>}
        </div>
      </div>
    );
  }

  if (profilFehler && !profil)
    return <FehlerZustand fehler={profilFehler} was="Der Kunde" zurueck onErneut={() => void profilNeu()} className="py-6" />;
  if (profilLoading || !profil) return <DetailSkeleton />;

  const kannVerwalten = hatRecht("kunden", "bearbeiten");
  const kannLoeschen = hatRecht("kunden", "loeschen");
  const menueEintraege: PulldownItem[] = [
    ...(kannVerwalten
      ? [
          {
            label: "Datenexport (DSGVO)",
            icon: Download,
            onSelect: () => datenexportMutation.mutate(),
          },
        ]
      : []),
    ...(kannLoeschen
      ? [
          ...(kannVerwalten ? ["trenner" as const] : []),
          {
            label: "Kunde löschen",
            icon: Trash2,
            destruktiv: true,
            onSelect: async () => {
              if (await bestaetigen({ titel: `${profil.name} löschen?`, text: `Das kann nicht rückgängig gemacht werden.`, bestaetigenLabel: "Löschen" })) {
                deleteMutation.mutate();
              }
            },
          },
        ]
      : []),
  ];

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-label2">
        ← Zurück
      </button>

      <div className="card-ap p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-label2">{profil.kundennummer}</div>
            <h1 className="text-lg font-bold text-label">{profil.name}</h1>
            {profil.typ && <span className="text-sm text-label2">{kundeTypLabel(profil.typ)}</span>}
          </div>
          {menueEintraege.length > 0 && (
            <PulldownMenu
              ariaLabel="Weitere Aktionen"
              items={menueEintraege}
              trigger={({ offen, toggeln, triggerRef }) => (
                <button
                  ref={triggerRef}
                  type="button"
                  onClick={toggeln}
                  aria-haspopup="menu"
                  aria-expanded={offen}
                  aria-label="Weitere Aktionen"
                  className="btn-touch flex items-center justify-center text-label2"
                >
                  <MoreHorizontal size={20} strokeWidth={2} aria-hidden="true" />
                </button>
              )}
            />
          )}
        </div>
        {deleteError && <p className="mt-2 text-sm text-st-fehlt ">{deleteError}</p>}
        {profil.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {profil.tags.map((t) => (
              <span key={t.id} className="border border-sep px-2 py-0.5 text-xs text-label">
                #{t.label}
              </span>
            ))}
          </div>
        )}
      </div>

      <SegmentedControl
        ariaLabel="Kundenprofil"
        groesse="touch"
        volleBreite
        wert={tab}
        optionen={[
          { wert: "uebersicht", label: "Übersicht" },
          { wert: "vorgaenge", label: `Vorgänge${profil.vorgaenge.length > 0 ? ` (${profil.vorgaenge.length})` : ""}` },
          { wert: "anlagen", label: `Anlagen${profil.anlagen.length > 0 ? ` (${profil.anlagen.length})` : ""}` },
          { wert: "kommunikation", label: "Kontakt" },
        ]}
        onChange={(key) => setSearchParams(key === "uebersicht" ? {} : { tab: key }, { replace: true })}
      />

      {tab === "uebersicht" && (
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
      )}

      {tab === "kommunikation" && (
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
      )}

      {tab === "anlagen" && (
      <>
      <StandorteVerwaltung kundeId={id!} kannVerwalten={kannVerwalten} />

      <LeistungsverzeichnisVerwaltung kundeId={id!} kundeName={profil.name} kannVerwalten={kannVerwalten} />

      <div>
        <h2 className="mb-2 text-sm font-semibold text-label2">Anlagen</h2>
        {profil.anlagen.length === 0 ? (
          <EmptyState icon={Boxes} text="Keine Anlagen." className="py-4" />
        ) : (
          <div className="space-y-2">
            {profil.anlagen.map((a) => (
              <div
                key={a.id}
                className={`flex items-center justify-between card-ap p-3 ${
                  a.aktiv ? "" : "opacity-60"
                }`}
              >
                <button onClick={() => navigate(`/anlagen/${a.id}`)} className="btn-touch flex-1 text-left">
                  <div className="text-sm font-medium text-label">{a.bezeichnung}</div>
                  {a.anlagentyp && <div className="text-xs text-label2">{a.anlagentyp}</div>}
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

      </>
      )}

      {tab === "vorgaenge" && (
      <>
      {kannVerwalten && <DauerauftraegeUebersicht kundeId={id!} />}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-label2">Vorgänge</h2>
          {profil.anlagen.length > 0 && (
            <select
              value={anlageFilter}
              onChange={(e) => setAnlageFilter(e.target.value)}
              className="btn-touch border border-sep bg-transparent px-2 py-1 text-xs text-label"
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
                className={`card-interactive btn-touch flex w-full items-center justify-between card-ap p-3 text-left ${
                  v.status === "storniert" ? "opacity-60 grayscale" : ""
                }`}
              >
                <div>
                  <div className="text-xs text-label2">
                    {v.vorgangsnummer}
                    {v.anlage_id && anlageNameById.get(v.anlage_id) && ` · ${anlageNameById.get(v.anlage_id)}`}
                    {v.dauerauftrag_id && (
                      <>
                        {" · "}
                        <Repeat size={11} strokeWidth={2} className="inline text-st-arbeit" />
                      </>
                    )}
                  </div>
                  <div className="text-sm font-medium text-label">{v.titel}</div>
                </div>
                <span className={`px-2 py-1 text-xs font-semibold ${STATUS_BADGE[v.status]}`}>
                  {statusLabel(v.status)}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
      </>
      )}
    </div>
  );
}
