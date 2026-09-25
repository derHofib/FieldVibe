import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, FileText, Inbox, Paperclip } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { eingangsrechnungenApi, lieferantenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import type { Eingangsrechnung, EingangsrechnungKategorie, EingangsrechnungStatus } from "../../types";

const STATUS_LABEL: Record<EingangsrechnungStatus, string> = {
  entwurf: "Entwurf (E-Mail-Import)",
  offen: "Offen",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

const KATEGORIE_LABEL: Record<EingangsrechnungKategorie, string> = {
  wareneinkauf: "Wareneinkauf",
  betriebskosten: "Betriebskosten",
  miete: "Miete",
  personal: "Personal",
  fahrzeug: "Fahrzeug",
  versicherung: "Versicherung",
  sonstiges: "Sonstiges",
};

function EntwurfBestaetigenView({ eingangsrechnung }: { eingangsrechnung: Eingangsrechnung }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [lieferantId, setLieferantId] = useState("");
  const [lieferantName, setLieferantName] = useState(eingangsrechnung.lieferant_name);
  const [rechnungsnummer, setRechnungsnummer] = useState(eingangsrechnung.rechnungsnummer_lieferant);
  const [rechnungsdatum, setRechnungsdatum] = useState(eingangsrechnung.rechnungsdatum.slice(0, 10));
  const [betragNetto, setBetragNetto] = useState(eingangsrechnung.betrag_netto);
  const [kategorie, setKategorie] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: lieferanten } = useQuery({ queryKey: ["lieferanten"], queryFn: () => lieferantenApi.list() });
  const { data: belegUrl } = useQuery({
    queryKey: ["eingangsrechnung-beleg-url", eingangsrechnung.id],
    queryFn: () => eingangsrechnungenApi.belegUrl(eingangsrechnung.id),
  });

  const bestaetigenMutation = useMutation({
    mutationFn: () =>
      eingangsrechnungenApi.update(eingangsrechnung.id, {
        lieferant_id: lieferantId || null,
        lieferant_name: lieferantId ? undefined : lieferantName,
        rechnungsnummer_lieferant: rechnungsnummer,
        rechnungsdatum,
        betrag_netto: betragNetto,
        kategorie: kategorie || undefined,
        status: "offen",
      }),
    onSuccess: () => {
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", eingangsrechnung.id] });
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Bestätigen fehlgeschlagen"),
  });

  const verwerfenMutation = useMutation({
    mutationFn: () => eingangsrechnungenApi.remove(eingangsrechnung.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
      navigate("/rechnungseingang");
    },
  });

  const inputClass =
    "w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label";

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-label2">
        ← Zurück
      </button>

      <div className="flex items-start gap-1.5 rounded-lg bg-st-arbeit-bg px-4 py-3 text-sm text-st-arbeit ">
        <Inbox size={15} strokeWidth={2} className="mt-0.5 shrink-0" />
        Per E-Mail importiert{eingangsrechnung.email_absender && ` von ${eingangsrechnung.email_absender}`}
        {eingangsrechnung.email_betreff && ` · "${eingangsrechnung.email_betreff}"`} -- bitte Angaben gegen den
        Beleg prüfen und bestätigen.
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="border border-sep bg-card p-2">
          {belegUrl?.url ? (
            <iframe title="Beleg" src={belegUrl.url} className="h-[70vh] w-full rounded-md" />
          ) : (
            <p className="p-4 text-sm text-label2">Kein Beleg vorhanden.</p>
          )}
        </div>

        <div className="space-y-3 border border-sep bg-card p-4">
          <div>
            <label className="mb-1 block text-xs text-label2">Lieferant</label>
            <select value={lieferantId} onChange={(e) => setLieferantId(e.target.value)} className={inputClass}>
              <option value="">Name manuell eintragen…</option>
              {(lieferanten ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </div>
          {!lieferantId && (
            <input
              value={lieferantName}
              onChange={(e) => setLieferantName(e.target.value)}
              placeholder="Name des Ausstellers"
              className={inputClass}
            />
          )}
          <div>
            <label className="mb-1 block text-xs text-label2">Rechnungsnummer</label>
            <input
              value={rechnungsnummer}
              onChange={(e) => setRechnungsnummer(e.target.value)}
              placeholder="Rechnungsnummer (vom Aussteller)"
              className={inputClass}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-label2">Rechnungsdatum</label>
              <input
                type="date"
                value={rechnungsdatum}
                onChange={(e) => setRechnungsdatum(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-label2">Betrag netto</label>
              <input
                type="number"
                step="0.01"
                value={betragNetto}
                onChange={(e) => setBetragNetto(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-label2">Kategorie</label>
            <select value={kategorie} onChange={(e) => setKategorie(e.target.value)} className={inputClass}>
              <option value="">Kategorie…</option>
              {Object.entries(KATEGORIE_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {fehler && <p className="text-xs text-st-fehlt ">{fehler}</p>}

          <div className="flex gap-2 pt-2">
            <button
              disabled={!rechnungsnummer || !betragNetto || Number(betragNetto) <= 0 || bestaetigenMutation.isPending}
              onClick={() => bestaetigenMutation.mutate()}
              className="btn-touch flex flex-1 items-center justify-center gap-1 rounded-md btn-ap-primary px-3 py-2 text-sm font-medium disabled:opacity-50"
            >
              <Check size={15} strokeWidth={2.25} /> Als Rechnung übernehmen
            </button>
            <button
              onClick={() => {
                if (window.confirm("Entwurf verwerfen (z.B. keine echte Rechnung)? Wandert in den Papierkorb.")) {
                  verwerfenMutation.mutate();
                }
              }}
              disabled={verwerfenMutation.isPending}
              className="btn-touch rounded-md bg-slate-100 px-3 py-2 text-sm font-medium text-st-fehlt disabled:opacity-50 dark:bg-stone-800 "
            >
              Verwerfen
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function EingangsrechnungDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const kannLoeschen = currentUser?.role === "loesch_operativ";
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ beschreibung: "", menge: "1", einheit: "Stk", einzelpreis: "0" });
  const [showZahlungForm, setShowZahlungForm] = useState(false);
  const [zahlungBetrag, setZahlungBetrag] = useState("");

  const { data: eingangsrechnung } = useQuery({
    queryKey: ["eingangsrechnung", id],
    queryFn: () => eingangsrechnungenApi.get(id!),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: () => eingangsrechnungenApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
      navigate("/rechnungseingang");
    },
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => eingangsrechnungenApi.update(id!, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] }),
  });

  const addPositionMutation = useMutation({
    mutationFn: () =>
      eingangsrechnungenApi.addPosition(id!, {
        beschreibung: form.beschreibung,
        menge: form.menge,
        einheit: form.einheit,
        einzelpreis: form.einzelpreis,
      }),
    onSuccess: () => {
      setShowForm(false);
      setForm({ beschreibung: "", menge: "1", einheit: "Stk", einzelpreis: "0" });
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] });
    },
  });

  const belegUploadMutation = useMutation({
    mutationFn: (file: File) => eingangsrechnungenApi.belegUpload(id!, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] }),
  });

  const belegRemoveMutation = useMutation({
    mutationFn: () => eingangsrechnungenApi.belegRemove(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] }),
  });

  const belegAnzeigenMutation = useMutation({
    mutationFn: () => eingangsrechnungenApi.belegUrl(id!),
    onSuccess: (res) => {
      if (res.url) window.open(res.url, "_blank");
    },
  });

  const addZahlungMutation = useMutation({
    mutationFn: () => eingangsrechnungenApi.addZahlung(id!, { betrag: zahlungBetrag }),
    onSuccess: () => {
      setShowZahlungForm(false);
      setZahlungBetrag("");
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnung", id] });
    },
  });

  if (!eingangsrechnung) return <p className="text-center text-label2">Lädt…</p>;

  if (eingangsrechnung.status === "entwurf") {
    return <EntwurfBestaetigenView eingangsrechnung={eingangsrechnung} />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        {kannLoeschen && eingangsrechnung.status === "offen" && (
          <button
            onClick={() => {
              if (window.confirm("Eingangsrechnung wirklich löschen? Sie wandert in den Papierkorb.")) {
                deleteMutation.mutate();
              }
            }}
            disabled={deleteMutation.isPending}
            className="btn-touch text-sm font-medium text-st-fehlt disabled:opacity-50 "
          >
            Löschen
          </button>
        )}
      </div>

      <div className="border border-sep bg-card p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-label2">
              {eingangsrechnung.rechnungsnummer_lieferant}
            </div>
            <h1 className="text-lg font-bold text-label">
              {eingangsrechnung.lieferant_name}
            </h1>
          </div>
          <span className="border border-sep px-2 py-1 text-xs font-semibold text-label">
            {STATUS_LABEL[eingangsrechnung.status]}
          </span>
        </div>
        <p className="mt-1 text-xs text-label2">
          Rechnungsdatum {new Date(eingangsrechnung.rechnungsdatum).toLocaleDateString("de-DE")}
        </p>
        {eingangsrechnung.faellig_am && (
          <p className="mt-1 text-xs text-label2">
            Fällig am {new Date(eingangsrechnung.faellig_am).toLocaleDateString("de-DE")}
          </p>
        )}
        {eingangsrechnung.kategorie && (
          <p className="mt-1 text-xs text-label2">
            Kategorie: {KATEGORIE_LABEL[eingangsrechnung.kategorie]}
          </p>
        )}
        {eingangsrechnung.notiz && (
          <p className="mt-2 text-sm text-label">{eingangsrechnung.notiz}</p>
        )}
        {eingangsrechnung.skonto_prozent && eingangsrechnung.skonto_frist && (
          <p className="mt-1 text-xs font-medium text-cyan-700 dark:text-cyan-400">
            Skonto {eingangsrechnung.skonto_prozent}% bis {new Date(eingangsrechnung.skonto_frist).toLocaleDateString("de-DE")}
            {" "}(Ersparnis {eingangsrechnung.skonto_betrag} EUR)
          </p>
        )}

        <div className="mt-3 text-right text-sm">
          <div className="text-label2">Netto: {eingangsrechnung.betrag_netto} EUR</div>
          <div className="font-semibold text-label">
            Brutto: {eingangsrechnung.betrag_brutto} EUR
          </div>
          {Number(eingangsrechnung.bezahlter_betrag) > 0 && (
            <div className="text-xs text-label2">
              Bezahlt: {eingangsrechnung.bezahlter_betrag} EUR · Offen: {eingangsrechnung.offener_betrag} EUR
            </div>
          )}
        </div>
      </div>

      <div className="border border-sep bg-card p-4">
        <h2 className="mb-2 text-sm font-semibold text-label2">Beleg</h2>
        {eingangsrechnung.beleg_object_key ? (
          <div className="flex gap-2">
            <button
              onClick={() => belegAnzeigenMutation.mutate()}
              disabled={belegAnzeigenMutation.isPending}
              className="btn-touch flex flex-1 items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-label disabled:opacity-50 dark:bg-stone-800 "
            >
              <FileText size={14} strokeWidth={2} /> Beleg anzeigen
            </button>
            {eingangsrechnung.status === "offen" && (
              <button
                onClick={() => belegRemoveMutation.mutate()}
                disabled={belegRemoveMutation.isPending}
                className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-st-fehlt disabled:opacity-50 dark:bg-stone-800 "
              >
                Entfernen
              </button>
            )}
          </div>
        ) : (
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf,image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) belegUploadMutation.mutate(file);
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={belegUploadMutation.isPending}
              className="btn-touch flex w-full items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-label disabled:opacity-50 dark:bg-stone-800 "
            >
              <Paperclip size={14} strokeWidth={2} /> Beleg hochladen
            </button>
          </div>
        )}
      </div>

      <div className="border border-sep bg-card p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-label2">Positionen</h2>
          {eingangsrechnung.status === "offen" && (
            <button
              onClick={() => setShowForm((v) => !v)}
              className="btn-touch text-xs font-medium text-tint "
            >
              {showForm ? "Abbrechen" : "+ Position"}
            </button>
          )}
        </div>

        {showForm && (
          <div className="mb-3 space-y-2 border border-sepstrong p-3">
            <input
              value={form.beschreibung}
              onChange={(e) => setForm({ ...form, beschreibung: e.target.value })}
              placeholder="Beschreibung"
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                step="0.01"
                value={form.menge}
                onChange={(e) => setForm({ ...form, menge: e.target.value })}
                placeholder="Menge"
                className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <input
                value={form.einheit}
                onChange={(e) => setForm({ ...form, einheit: e.target.value })}
                placeholder="Einheit"
                className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <input
                type="number"
                step="0.01"
                value={form.einzelpreis}
                onChange={(e) => setForm({ ...form, einzelpreis: e.target.value })}
                placeholder="Preis"
                className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
            <button
              disabled={!form.beschreibung || addPositionMutation.isPending}
              onClick={() => addPositionMutation.mutate()}
              className="btn-touch w-full rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Hinzufügen
            </button>
          </div>
        )}

        {eingangsrechnung.positionen.length === 0 ? (
          <p className="text-sm text-label2">
            Keine eigenen Positionen -- Betrag wurde als Gesamtsumme angelegt.
          </p>
        ) : (
          <div className="space-y-1.5">
            {eingangsrechnung.positionen.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60"
              >
                <div>
                  <div className="text-label">{p.beschreibung}</div>
                  <div className="text-xs text-label2">
                    {p.menge} {p.einheit} × {p.einzelpreis} EUR
                  </div>
                </div>
                <div className="font-medium text-label">{p.gesamt} EUR</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border border-sep bg-card p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-label2">Zahlungen</h2>
          {eingangsrechnung.status === "offen" && (
            <button
              onClick={() => {
                setZahlungBetrag(eingangsrechnung.offener_betrag);
                setShowZahlungForm((v) => !v);
              }}
              className="btn-touch text-xs font-medium text-tint "
            >
              {showZahlungForm ? "Abbrechen" : "+ Zahlung"}
            </button>
          )}
        </div>

        {showZahlungForm && (
          <div className="mb-3 space-y-2 border border-sepstrong p-3">
            <input
              type="number"
              step="0.01"
              value={zahlungBetrag}
              onChange={(e) => setZahlungBetrag(e.target.value)}
              placeholder="Betrag"
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            {addZahlungMutation.isError && (
              <p className="text-xs text-st-fehlt ">
                Zahlung übersteigt den offenen Betrag oder ist ungültig.
              </p>
            )}
            <button
              disabled={!zahlungBetrag || addZahlungMutation.isPending}
              onClick={() => addZahlungMutation.mutate()}
              className="btn-touch w-full rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Zahlung erfassen
            </button>
          </div>
        )}

        {eingangsrechnung.zahlungen.length === 0 ? (
          <p className="text-sm text-label2">Noch keine Zahlung erfasst.</p>
        ) : (
          <div className="space-y-1.5">
            {eingangsrechnung.zahlungen.map((z) => (
              <div
                key={z.id}
                className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60"
              >
                <span className="text-label2">
                  {new Date(z.datum).toLocaleDateString("de-DE")}
                </span>
                <span className="font-medium text-label">{z.betrag} EUR</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {eingangsrechnung.status === "offen" && (
        <button
          onClick={() => {
            if (window.confirm("Diese Eingangsrechnung stornieren?")) statusMutation.mutate("storniert");
          }}
          disabled={statusMutation.isPending}
          className="btn-touch w-full rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-label disabled:opacity-50 dark:bg-stone-800 "
        >
          Stornieren
        </button>
      )}
    </div>
  );
}
