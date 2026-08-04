import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { anlagenApi, kundenApi, standorteApi, vorgaengeApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { QrScanner } from "../../components/QrScanner";
import { queueVorgang } from "../../offline/outbox";
import type { Anlage, KundeTyp, Leistungstyp, VorgangAbrechnungsart } from "../../types";

const KUNDE_TYPEN: { value: KundeTyp; label: string }[] = [
  { value: "privat", label: "Privat" },
  { value: "gewerbe", label: "Gewerbe" },
  { value: "oeffentlich", label: "Öffentliche Hand" },
  { value: "hausverwaltung", label: "Hausverwaltung" },
];

const LEISTUNGSTYPEN: { value: Leistungstyp; label: string }[] = [
  { value: "stoerung", label: "Störung" },
  { value: "installation", label: "Installation" },
  { value: "wartung", label: "Wartung" },
  { value: "pruefung", label: "Prüfung" },
  { value: "beratung", label: "Beratung" },
  { value: "planung", label: "Planung" },
];

const ABRECHNUNGSARTEN: { value: VorgangAbrechnungsart; label: string }[] = [
  { value: "aufwand", label: "Nach Aufwand" },
  { value: "pauschale", label: "Pauschale" },
  { value: "festpreis", label: "Festpreis" },
  { value: "wartungsvertrag", label: "Wartungsvertrag" },
  { value: "gewaehrleistung", label: "Gewährleistung" },
];

export function NewVorgangPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [kundeId, setKundeId] = useState("");
  const [anlage, setAnlage] = useState<Anlage | null>(null);
  const [standortId, setStandortId] = useState("");
  const [weitereAnlagenIds, setWeitereAnlagenIds] = useState<Set<string>>(new Set());
  const [titel, setTitel] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [leistungstyp, setLeistungstyp] = useState<Leistungstyp>("stoerung");
  const [abrechnungsart, setAbrechnungsart] = useState<VorgangAbrechnungsart>("aufwand");
  const [showScanner, setShowScanner] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [showNewKunde, setShowNewKunde] = useState(false);
  const [newKundeName, setNewKundeName] = useState("");
  const [newKundeTyp, setNewKundeTyp] = useState<KundeTyp | "">("");
  const [newKundeError, setNewKundeError] = useState<string | null>(null);
  const [showNewAnlage, setShowNewAnlage] = useState(false);
  const [newAnlageBezeichnung, setNewAnlageBezeichnung] = useState("");
  const [newAnlageTyp, setNewAnlageTyp] = useState("");
  const [newAnlageError, setNewAnlageError] = useState<string | null>(null);

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });
  const { data: anlagenListe } = useQuery({
    queryKey: ["anlagen", kundeId, "aktiv"],
    queryFn: () => anlagenApi.list(kundeId, undefined, true),
    enabled: !!kundeId,
  });
  const { data: standorteListe } = useQuery({
    queryKey: ["standorte", kundeId, "aktiv"],
    queryFn: () => standorteApi.list(kundeId, true),
    enabled: !!kundeId,
  });
  const { data: standortAnlagen } = useQuery({
    queryKey: ["anlagen", "standort", standortId, "aktiv"],
    queryFn: () => anlagenApi.list(undefined, undefined, true, standortId),
    enabled: !!standortId,
  });

  // Beim Auswaehlen eines Standorts sind dessen Anlagen zunaechst alle
  // vorausgewaehlt -- einzelne lassen sich in der Checkliste abwaehlen.
  useEffect(() => {
    setWeitereAnlagenIds(new Set((standortAnlagen ?? []).map((a) => a.id)));
  }, [standortAnlagen]);

  const createAnlageMutation = useMutation({
    mutationFn: () =>
      anlagenApi.create({
        kunde_id: kundeId,
        bezeichnung: newAnlageBezeichnung,
        anlagentyp: newAnlageTyp || undefined,
      }),
    onSuccess: (neueAnlage) => {
      queryClient.invalidateQueries({ queryKey: ["anlagen", kundeId] });
      setAnlage(neueAnlage);
      setShowNewAnlage(false);
      setNewAnlageBezeichnung("");
      setNewAnlageTyp("");
      setNewAnlageError(null);
    },
    onError: (err) =>
      setNewAnlageError(err instanceof ApiError ? err.message : "Anlage konnte nicht angelegt werden"),
  });

  function handleCreateAnlage(e: FormEvent) {
    e.preventDefault();
    setNewAnlageError(null);
    if (!newAnlageBezeichnung.trim()) {
      setNewAnlageError("Bitte eine Bezeichnung eingeben");
      return;
    }
    createAnlageMutation.mutate();
  }

  const createKundeMutation = useMutation({
    mutationFn: () =>
      kundenApi.create({ name: newKundeName, typ: newKundeTyp || undefined }),
    onSuccess: (kunde) => {
      queryClient.invalidateQueries({ queryKey: ["kunden"] });
      setKundeId(kunde.id);
      setAnlage(null);
      setShowNewKunde(false);
      setNewKundeName("");
      setNewKundeTyp("");
      setNewKundeError(null);
    },
    onError: (err) =>
      setNewKundeError(err instanceof ApiError ? err.message : "Kunde konnte nicht angelegt werden"),
  });

  function handleCreateKunde(e: FormEvent) {
    e.preventDefault();
    setNewKundeError(null);
    if (!newKundeName.trim()) {
      setNewKundeError("Bitte einen Namen eingeben");
      return;
    }
    createKundeMutation.mutate();
  }

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        kunde_id: kundeId,
        anlage_id: anlage?.id ?? null,
        weitere_anlage_ids: Array.from(weitereAnlagenIds),
        standort_id: standortId || null,
        titel,
        beschreibung,
        abrechnungsart,
        leistungstyp,
      };
      try {
        return { online: true as const, vorgang: await vorgaengeApi.create(payload) };
      } catch (err) {
        if (err instanceof ApiError) throw err; // echte Ablehnung, nicht queuen
        await queueVorgang(payload); // Netzwerkfehler -> offline
        return { online: false as const };
      }
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      if (result.online) {
        navigate(`/vorgaenge/${result.vorgang.id}`);
      } else {
        navigate("/feed");
      }
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Fehler"),
  });

  async function handleScan(code: string) {
    setShowScanner(false);
    setScanError(null);
    try {
      const found = await anlagenApi.byQrCode(code);
      setAnlage(found);
      setKundeId(found.kunde_id ?? "");
      if (!titel) setTitel(`Vor-Ort-Termin: ${found.bezeichnung}`);
    } catch {
      setScanError(`Keine Anlage mit dem Code "${code}" gefunden.`);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!kundeId) {
      setError("Bitte einen Kunden auswählen");
      return;
    }
    createMutation.mutate();
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">Neuer Vorgang</h1>

      <button
        onClick={() => setShowScanner(true)}
        className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-3 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
      >
        📷 QR-Code an Anlage scannen
      </button>
      {scanError && <p className="text-sm text-red-700 dark:text-red-400">{scanError}</p>}
      {anlage && (
        <div className="flex items-center justify-between rounded-lg bg-blue-50 p-3 text-sm text-blue-900 dark:bg-blue-500/10 dark:text-blue-200">
          <span>
            Anlage erkannt: <strong>{anlage.bezeichnung}</strong>
          </span>
          <span className="flex gap-3">
            <button
              onClick={() => navigate(`/anlagen/${anlage.id}`)}
              className="btn-touch text-xs text-blue-700 underline dark:text-blue-400"
            >
              ansehen
            </button>
            <button
              onClick={() => setAnlage(null)}
              className="btn-touch text-xs text-blue-700 underline dark:text-blue-400"
            >
              entfernen
            </button>
          </span>
        </div>
      )}

      {showScanner && (
        <QrScanner onScan={handleScan} onClose={() => setShowScanner(false)} />
      )}

      <p className="text-sm text-slate-500 dark:text-slate-400">
        Zeiterfassung startest du direkt im Vorgang; Foto-Uploads laufen ebenfalls über den
        Vorgangs-Chat. Ohne Netzverbindung wird der Vorgang zwischengespeichert und synchronisiert
        sich automatisch, sobald wieder eine Verbindung besteht.
      </p>

      <form
        onSubmit={handleSubmit}
        className="space-y-3 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
      >
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Kunde</label>
          <select
            value={kundeId}
            onChange={(e) => {
              setKundeId(e.target.value);
              setAnlage(null);
              setStandortId("");
            }}
            className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="">Bitte wählen…</option>
            {kunden?.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name} ({k.kundennummer})
              </option>
            ))}
          </select>
          {!showNewKunde && (
            <button
              type="button"
              onClick={() => setShowNewKunde(true)}
              className="btn-touch mt-1 text-xs text-blue-700 underline dark:text-blue-400"
            >
              + Neuen Kunden anlegen
            </button>
          )}
        </div>

        {showNewKunde && (
          <div className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Name</label>
              <input
                autoFocus
                value={newKundeName}
                onChange={(e) => setNewKundeName(e.target.value)}
                className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Typ (optional)</label>
              <select
                value={newKundeTyp}
                onChange={(e) => setNewKundeTyp(e.target.value as KundeTyp | "")}
                className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="">Keine Angabe</option>
                {KUNDE_TYPEN.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            {newKundeError && <p className="text-sm text-red-700 dark:text-red-400">{newKundeError}</p>}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCreateKunde}
                disabled={createKundeMutation.isPending}
                className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                Kunde anlegen
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowNewKunde(false);
                  setNewKundeError(null);
                }}
                className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        {kundeId && standorteListe && standorteListe.length > 0 && (
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Standort (optional)
            </label>
            <select
              value={standortId}
              onChange={(e) => setStandortId(e.target.value)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="">Kein Standort</option>
              {standorteListe.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.bezeichnung}
                </option>
              ))}
            </select>
          </div>
        )}

        {standortId && standortAnlagen && standortAnlagen.length > 0 && (
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Anlagen an diesem Standort
            </label>
            <div className="space-y-1 rounded-md border border-slate-200 p-2 dark:border-slate-700">
              {standortAnlagen.map((a) => (
                <label key={a.id} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={weitereAnlagenIds.has(a.id)}
                    onChange={(e) =>
                      setWeitereAnlagenIds((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(a.id);
                        else next.delete(a.id);
                        return next;
                      })
                    }
                  />
                  {a.bezeichnung}
                </label>
              ))}
            </div>
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
              Alle angehakten Anlagen werden mit in den Vorgang aufgenommen.
            </p>
          </div>
        )}

        {kundeId && (
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Anlage (optional)</label>
            <select
              value={anlage?.id ?? ""}
              onChange={(e) =>
                setAnlage(anlagenListe?.find((a) => a.id === e.target.value) ?? null)
              }
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="">Keine Anlage</option>
              {anlagenListe?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.bezeichnung}
                </option>
              ))}
            </select>
            {!showNewAnlage && (
              <button
                type="button"
                onClick={() => setShowNewAnlage(true)}
                className="btn-touch mt-1 text-xs text-blue-700 underline dark:text-blue-400"
              >
                + Neue Anlage anlegen
              </button>
            )}
          </div>
        )}

        {showNewAnlage && (
          <div className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Bezeichnung</label>
              <input
                autoFocus
                value={newAnlageBezeichnung}
                onChange={(e) => setNewAnlageBezeichnung(e.target.value)}
                className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Typ (optional)</label>
              <input
                value={newAnlageTyp}
                onChange={(e) => setNewAnlageTyp(e.target.value)}
                placeholder="z.B. Hauptverteilung, PV-Anlage, Wallbox"
                className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            {newAnlageError && <p className="text-sm text-red-700 dark:text-red-400">{newAnlageError}</p>}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCreateAnlage}
                disabled={createAnlageMutation.isPending}
                className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                Anlage anlegen
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowNewAnlage(false);
                  setNewAnlageError(null);
                }}
                className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Titel</label>
          <input
            required
            value={titel}
            onChange={(e) => setTitel(e.target.value)}
            className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Beschreibung</label>
          <textarea
            value={beschreibung}
            onChange={(e) => setBeschreibung(e.target.value)}
            rows={3}
            className="w-full resize-none rounded-md border border-slate-300 p-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Leistungstyp</label>
            <select
              value={leistungstyp}
              onChange={(e) => setLeistungstyp(e.target.value as Leistungstyp)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              {LEISTUNGSTYPEN.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Abrechnungsart</label>
            <select
              value={abrechnungsart}
              onChange={(e) => setAbrechnungsart(e.target.value as VorgangAbrechnungsart)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              {ABRECHNUNGSARTEN.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch w-full rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-2 font-medium text-white disabled:opacity-50"
        >
          Vorgang anlegen
        </button>
      </form>
    </div>
  );
}
