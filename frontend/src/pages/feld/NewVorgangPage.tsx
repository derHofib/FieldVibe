import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ScanLine } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { anlagenApi, auftraegeApi, kundenApi, projekteApi, standorteApi, vorgaengeApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { Sheet } from "../../components/apple/Sheet";
import { QrScanner } from "../../components/QrScanner";
import { SearchableSelect } from "../../components/SearchableSelect";
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

const PRIORITAET_OPTIONEN = [
  { value: 1, label: "1 – Niedrig" },
  { value: 2, label: "2" },
  { value: 3, label: "3 – Normal" },
  { value: 4, label: "4" },
  { value: 5, label: "5 – Hoch" },
];

// Sheet-DOM-Wurzel liegt ausserhalb des <form> (Sheet.tsx portalt die Kopf-
// zeile mit den Aktionen als Geschwister statt als Vorfahre des Inhalts) --
// das HTML-Attribut form="..." verknuepft den Kopfzeilen-Button trotzdem
// mit dem Formular, ganz ohne eigenen State fuer den Submit-Klick.
const FORM_ID = "neuer-vorgang-formular";

/** "Neuer Vorgang" (Abschnitt 5.3): frueher eigene Vollbild-Route, jetzt ein
 * Sheet (mobil von unten, Desktop/Office als 540px-Dialog) -- Inhalt/
 * Funktionsumfang unveraendert, nur die Praesentation. Abbrechen fuehrt
 * zurueck zur aufrufenden Seite (Feed oder Office-Vorgangsliste) statt zu
 * einer fest verdrahteten Route. */
export function NewVorgangPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // "+ Neuer Vorgang" aus ProjektDetailPanel.tsx/AuftragDetailPanel.tsx
  // verlinkt hierher mit ?projekt_id=.../?auftrag_id=..., damit der neue
  // Vorgang direkt der richtigen Ebene zugeordnet ist -- beide Felder
  // bleiben trotzdem per SearchableSelect aenderbar (siehe dort unten).
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [kundeId, setKundeId] = useState("");
  const [projektId, setProjektId] = useState(searchParams.get("projekt_id") ?? "");
  const [auftragId, setAuftragId] = useState(searchParams.get("auftrag_id") ?? "");
  const [anlage, setAnlage] = useState<Anlage | null>(null);
  const [standortId, setStandortId] = useState("");
  const [weitereAnlagenIds, setWeitereAnlagenIds] = useState<Set<string>>(new Set());
  const [titel, setTitel] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [leistungstyp, setLeistungstyp] = useState<Leistungstyp>("stoerung");
  const [abrechnungsart, setAbrechnungsart] = useState<VorgangAbrechnungsart>("aufwand");
  const [prioritaet, setPrioritaet] = useState(3);
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
  const [adrStrasse, setAdrStrasse] = useState("");
  const [adrPlz, setAdrPlz] = useState("");
  const [adrOrt, setAdrOrt] = useState("");

  function schliessen() {
    navigate(-1);
  }

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });
  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list() });
  const { data: auftraege } = useQuery({ queryKey: ["auftraege"], queryFn: () => auftraegeApi.list() });
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
        projekt_id: projektId || null,
        auftrag_id: auftragId || null,
        titel,
        beschreibung,
        abrechnungsart,
        leistungstyp,
        prioritaet,
        adresse:
          adrStrasse || adrPlz || adrOrt
            ? { strasse: adrStrasse || undefined, plz: adrPlz || undefined, ort: adrOrt || undefined }
            : undefined,
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
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
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
    if (!titel.trim()) {
      setError("Bitte einen Titel eingeben");
      return;
    }
    createMutation.mutate();
  }

  return (
    <Sheet
      offen
      onClose={schliessen}
      titel="Neuer Vorgang"
      links={
        <button type="button" onClick={schliessen} className="text-[17px] text-tint">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form={FORM_ID}
          disabled={createMutation.isPending}
          className="text-[17px] font-semibold text-tint disabled:opacity-40"
        >
          Anlegen
        </button>
      }
    >
      <form id={FORM_ID} onSubmit={handleSubmit} className="space-y-4 p-4">
        <button
          type="button"
          onClick={() => setShowScanner(true)}
          className="btn-ap-capsule btn-ap-capsule-secondary w-full"
        >
          <ScanLine size={16} strokeWidth={2} aria-hidden="true" /> QR-Code an Anlage scannen
        </button>
        {scanError && <p className="text-sm text-st-fehlt">{scanError}</p>}
        {anlage && (
          <div className="flex items-center justify-between rounded-[var(--radius-ap-input)] bg-tintbg p-3 text-sm text-tint">
            <span>
              Anlage erkannt: <strong>{anlage.bezeichnung}</strong>
            </span>
            <span className="flex gap-3">
              <button type="button" onClick={() => navigate(`/anlagen/${anlage.id}`)} className="text-xs underline">
                ansehen
              </button>
              <button type="button" onClick={() => setAnlage(null)} className="text-xs underline">
                entfernen
              </button>
            </span>
          </div>
        )}

        {showScanner && <QrScanner onScan={handleScan} onClose={() => setShowScanner(false)} />}

        <p className="text-sm text-label2">
          Zeiterfassung startest du direkt im Vorgang; Foto-Uploads laufen ebenfalls über den
          Vorgangs-Chat. Ohne Netzverbindung wird der Vorgang zwischengespeichert und synchronisiert
          sich automatisch, sobald wieder eine Verbindung besteht.
        </p>

        <div>
          <label className="mb-1 block text-sm font-medium text-label">Kunde</label>
          <select
            value={kundeId}
            onChange={(e) => {
              setKundeId(e.target.value);
              setAnlage(null);
              setStandortId("");
            }}
            className="field-ap"
          >
            <option value="">Bitte wählen…</option>
            {kunden?.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name} ({k.kundennummer})
              </option>
            ))}
          </select>
          {!showNewKunde && (
            <button type="button" onClick={() => setShowNewKunde(true)} className="mt-1 text-xs text-tint underline">
              + Neuen Kunden anlegen
            </button>
          )}
        </div>

        {showNewKunde && (
          <div className="space-y-2 rounded-[var(--radius-ap-input)] bg-fill p-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-label">Name</label>
              <input
                autoFocus
                value={newKundeName}
                onChange={(e) => setNewKundeName(e.target.value)}
                className="field-ap"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-label">Typ (optional)</label>
              <select
                value={newKundeTyp}
                onChange={(e) => setNewKundeTyp(e.target.value as KundeTyp | "")}
                className="field-ap"
              >
                <option value="">Keine Angabe</option>
                {KUNDE_TYPEN.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            {newKundeError && <p className="text-sm text-st-fehlt">{newKundeError}</p>}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCreateKunde}
                disabled={createKundeMutation.isPending}
                className="btn-ap-primary flex-1"
              >
                Kunde anlegen
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowNewKunde(false);
                  setNewKundeError(null);
                }}
                className="btn-ap flex-1"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        {kundeId && standorteListe && standorteListe.length > 0 && (
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Standort (optional)</label>
            <select value={standortId} onChange={(e) => setStandortId(e.target.value)} className="field-ap">
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
            <label className="mb-1 block text-sm font-medium text-label">Anlagen an diesem Standort</label>
            <div className="space-y-1 rounded-[var(--radius-ap-input)] bg-fill p-2">
              {standortAnlagen.map((a) => (
                <label key={a.id} className="flex items-center gap-2 text-sm text-label">
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
            <p className="mt-1 text-xs text-label2">
              Alle angehakten Anlagen werden mit in den Vorgang aufgenommen.
            </p>
          </div>
        )}

        {kundeId && (
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Anlage (optional)</label>
            <select
              value={anlage?.id ?? ""}
              onChange={(e) => setAnlage(anlagenListe?.find((a) => a.id === e.target.value) ?? null)}
              className="field-ap"
            >
              <option value="">Keine Anlage</option>
              {anlagenListe?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.bezeichnung}
                </option>
              ))}
            </select>
            {!showNewAnlage && (
              <button type="button" onClick={() => setShowNewAnlage(true)} className="mt-1 text-xs text-tint underline">
                + Neue Anlage anlegen
              </button>
            )}
          </div>
        )}

        {showNewAnlage && (
          <div className="space-y-2 rounded-[var(--radius-ap-input)] bg-fill p-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-label">Bezeichnung</label>
              <input
                autoFocus
                value={newAnlageBezeichnung}
                onChange={(e) => setNewAnlageBezeichnung(e.target.value)}
                className="field-ap"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-label">Typ (optional)</label>
              <input
                value={newAnlageTyp}
                onChange={(e) => setNewAnlageTyp(e.target.value)}
                placeholder="z.B. Hauptverteilung, PV-Anlage, Wallbox"
                className="field-ap"
              />
            </div>
            {newAnlageError && <p className="text-sm text-st-fehlt">{newAnlageError}</p>}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCreateAnlage}
                disabled={createAnlageMutation.isPending}
                className="btn-ap-primary flex-1"
              >
                Anlage anlegen
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowNewAnlage(false);
                  setNewAnlageError(null);
                }}
                className="btn-ap flex-1"
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Projekt (optional)</label>
            <SearchableSelect
              value={projektId}
              onChange={setProjektId}
              placeholder="Kein Projekt"
              options={(projekte ?? []).map((p) => ({ value: p.id, label: p.name }))}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Auftrag (optional)</label>
            <SearchableSelect
              value={auftragId}
              onChange={setAuftragId}
              placeholder="Kein Auftrag"
              options={(auftraege ?? []).map((a) => ({ value: a.id, label: a.titel }))}
            />
          </div>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-label">Titel</label>
          <input required value={titel} onChange={(e) => setTitel(e.target.value)} className="field-ap" />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-label">Beschreibung</label>
          <textarea value={beschreibung} onChange={(e) => setBeschreibung(e.target.value)} rows={3} className="field-ap" />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-label">Adresse (optional)</label>
          <p className="mb-1 text-xs text-label2">
            Nur nötig, wenn kein Standort ausgewählt ist -- damit weiß der Ausführende, wo er hin muss.
          </p>
          <input
            value={adrStrasse}
            onChange={(e) => setAdrStrasse(e.target.value)}
            placeholder="Straße + Hausnr."
            className="field-ap mb-2"
          />
          <div className="grid grid-cols-2 gap-2">
            <input value={adrPlz} onChange={(e) => setAdrPlz(e.target.value)} placeholder="PLZ" className="field-ap" />
            <input value={adrOrt} onChange={(e) => setAdrOrt(e.target.value)} placeholder="Ort" className="field-ap" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Leistungstyp</label>
            <select
              value={leistungstyp}
              onChange={(e) => setLeistungstyp(e.target.value as Leistungstyp)}
              className="field-ap"
            >
              {LEISTUNGSTYPEN.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Abrechnungsart</label>
            <select
              value={abrechnungsart}
              onChange={(e) => setAbrechnungsart(e.target.value as VorgangAbrechnungsart)}
              className="field-ap"
            >
              {ABRECHNUNGSARTEN.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Priorität</label>
            <select value={prioritaet} onChange={(e) => setPrioritaet(Number(e.target.value))} className="field-ap">
              {PRIORITAET_OPTIONEN.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && <p className="text-sm text-st-fehlt">{error}</p>}

        {/* Primäraktion liegt in der Kopfzeile (rechts="Anlegen"); dieser
            Button bleibt als zweite, gut sichtbare Erreichbarkeit am Ende
            des langen Formulars -- sonst müsste nach dem Ausfüllen wieder
            ganz nach oben gescrollt werden. */}
        <button type="submit" disabled={createMutation.isPending} className="btn-ap-primary w-full">
          Vorgang anlegen
        </button>
      </form>
    </Sheet>
  );
}
