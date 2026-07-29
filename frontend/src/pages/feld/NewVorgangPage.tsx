import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { anlagenApi, kundenApi, vorgaengeApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { QrScanner } from "../../components/QrScanner";
import { queueVorgang } from "../../offline/outbox";
import type { Anlage, Leistungstyp, VorgangAbrechnungsart } from "../../types";

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
  const [titel, setTitel] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [leistungstyp, setLeistungstyp] = useState<Leistungstyp>("stoerung");
  const [abrechnungsart, setAbrechnungsart] = useState<VorgangAbrechnungsart>("aufwand");
  const [showScanner, setShowScanner] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        kunde_id: kundeId,
        anlage_id: anlage?.id ?? null,
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
      setKundeId(found.kunde_id);
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
      <h1 className="text-lg font-bold text-slate-800">Neuer Vorgang</h1>

      <button
        onClick={() => setShowScanner(true)}
        className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-3 text-sm font-medium text-slate-700 shadow-sm"
      >
        📷 QR-Code an Anlage scannen
      </button>
      {scanError && <p className="text-sm text-red-700">{scanError}</p>}
      {anlage && (
        <div className="flex items-center justify-between rounded-lg bg-blue-50 p-3 text-sm text-blue-900">
          <span>
            Anlage erkannt: <strong>{anlage.bezeichnung}</strong>
          </span>
          <span className="flex gap-3">
            <button
              onClick={() => navigate(`/anlagen/${anlage.id}`)}
              className="btn-touch text-xs text-blue-700 underline"
            >
              ansehen
            </button>
            <button
              onClick={() => setAnlage(null)}
              className="btn-touch text-xs text-blue-700 underline"
            >
              entfernen
            </button>
          </span>
        </div>
      )}

      {showScanner && (
        <QrScanner onScan={handleScan} onClose={() => setShowScanner(false)} />
      )}

      <p className="text-sm text-slate-500">
        Zeiterfassung startest du direkt im Vorgang; Foto-Uploads laufen ebenfalls über den
        Vorgangs-Chat. Ohne Netzverbindung wird der Vorgang zwischengespeichert und synchronisiert
        sich automatisch, sobald wieder eine Verbindung besteht.
      </p>

      <form onSubmit={handleSubmit} className="space-y-3 rounded-lg bg-white p-4 shadow-sm">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Kunde</label>
          <select
            value={kundeId}
            onChange={(e) => {
              setKundeId(e.target.value);
              setAnlage(null);
            }}
            className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
          >
            <option value="">Bitte wählen…</option>
            {kunden?.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name} ({k.kundennummer})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Titel</label>
          <input
            required
            value={titel}
            onChange={(e) => setTitel(e.target.value)}
            className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Beschreibung</label>
          <textarea
            value={beschreibung}
            onChange={(e) => setBeschreibung(e.target.value)}
            rows={3}
            className="w-full resize-none rounded-md border border-slate-300 p-2"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Leistungstyp</label>
            <select
              value={leistungstyp}
              onChange={(e) => setLeistungstyp(e.target.value as Leistungstyp)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
            >
              {LEISTUNGSTYPEN.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Abrechnungsart</label>
            <select
              value={abrechnungsart}
              onChange={(e) => setAbrechnungsart(e.target.value as VorgangAbrechnungsart)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
            >
              {ABRECHNUNGSARTEN.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && <p className="text-sm text-red-700">{error}</p>}

        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch w-full rounded-md bg-slate-900 py-2 font-medium text-white disabled:opacity-50"
        >
          Vorgang anlegen
        </button>
      </form>
    </div>
  );
}
