import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { useState, type FormEvent } from "react";

import { leistungsverzeichnisApi, leistungsverzeichnisseApi } from "../../../api/endpoints";
import { ApiError } from "../../../api/client";
import { AnlegenPanel } from "../../../components/AnlegenPanel";
import { Feld, FELD_KLASSE, NEU_BUTTON_KLASSE } from "../../../components/FormularFeld";
import { EmptyState } from "../../../components/EmptyState";
import type { LeistungsverzeichnisPosition } from "../../../types";
import { useBestaetigung } from "../../../components/ConfirmDialog";

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

export function LeistungsverzeichnisVerwaltung({
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
