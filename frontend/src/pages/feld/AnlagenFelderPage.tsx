import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListPlus } from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { anlagenApi, anlagenFeldDefinitionenApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import type { AnlagenFeldTyp } from "../../types";
import { Select } from "../../components/apple/Select";
import { AktionsMenue } from "../../components/AktionsMenue";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { Feld, FELD_KLASSE, NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { SkeletonList } from "../../components/Skeleton";

const FELD_TYP_LABEL: Record<AnlagenFeldTyp, string> = {
  text: "Text",
  zahl: "Zahl",
  datum: "Datum",
};

export function AnlagenFelderPage() {
  const bestaetigen = useBestaetigung();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [anlagentyp, setAnlagentyp] = useState("");
  const [feldName, setFeldName] = useState("");
  const [feldTyp, setFeldTyp] = useState<AnlagenFeldTyp>("text");
  const [error, setError] = useState<string | null>(null);
  const [fehlerFeld, setFehlerFeld] = useState<"typ" | "name" | null>(null);
  const [panelOffen, setPanelOffen] = useState(false);

  const { data: definitionen, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["anlagen-feld-definitionen"],
    queryFn: () => anlagenFeldDefinitionenApi.list(),
  });
  const { data: anlagen } = useQuery({ queryKey: ["anlagen-alle"], queryFn: () => anlagenApi.list() });

  const bekannteTypen = useMemo(() => {
    const typen = new Set<string>();
    (anlagen ?? []).forEach((a) => a.anlagentyp && typen.add(a.anlagentyp));
    (definitionen ?? []).forEach((d) => typen.add(d.anlagentyp));
    return Array.from(typen).sort();
  }, [anlagen, definitionen]);

  const gruppen = useMemo(() => {
    const map = new Map<string, typeof definitionen>();
    (definitionen ?? []).forEach((d) => {
      const liste = map.get(d.anlagentyp) ?? [];
      liste.push(d);
      map.set(d.anlagentyp, liste as NonNullable<typeof definitionen>);
    });
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [definitionen]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["anlagen-feld-definitionen"] });

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () =>
      anlagenFeldDefinitionenApi.create({
        anlagentyp: anlagentyp.trim(),
        feld_name: feldName.trim(),
        feld_typ: feldTyp,
        reihenfolge: definitionen?.filter((d) => d.anlagentyp === anlagentyp.trim()).length ?? 0,
      }),
    onSuccess: () => {
      invalidate();
      setFeldName("");
      setError(null);
      setPanelOffen(false);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Feld konnte nicht angelegt werden"),
  });

  const deleteMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: (id: string) => anlagenFeldDefinitionenApi.remove(id),
    onSuccess: invalidate,
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFehlerFeld(null);
    if (!anlagentyp.trim()) {
      setError("Bitte einen Anlagentyp angeben");
      setFehlerFeld("typ");
      return;
    }
    if (!feldName.trim()) {
      setError("Bitte einen Feldnamen angeben");
      setFehlerFeld("name");
      return;
    }
    createMutation.mutate();
  }

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sekundaer text-label2">
        ← Zurück
      </button>

      <div>
        <h1 className="text-titel-mobil font-bold text-label">Anlagen-Zusatzfelder</h1>
        <p className="mt-1 text-sekundaer text-label2">
          Lege je Anlagentyp (z. B. „Fahrzeug", „Ladestation", „Elektroanlage") eigene Felder fest, die
          beim Anlegen/Bearbeiten einer Anlage dieses Typs zusätzlich abgefragt werden.
        </p>
      </div>

      <button type="button" onClick={() => setPanelOffen(true)} className={NEU_BUTTON_KLASSE}>
        + Neues Zusatzfeld
      </button>

      <AnlegenPanel offen={panelOffen} titel="Neues Zusatzfeld" onClose={() => setPanelOffen(false)}>
        <form onSubmit={handleSubmit} noValidate className="space-y-3 p-4">
          <Feld label="Anlagentyp" pflicht fehler={fehlerFeld === "typ" ? error : null}>
            {(p) => (
              <>
                <input
                  {...p}
                  list="bekannte-anlagentypen"
                  value={anlagentyp}
                  onChange={(e) => setAnlagentyp(e.target.value)}
                  placeholder="z.B. Fahrzeug, Ladestation, Elektroanlage"
                  className={FELD_KLASSE}
                />
                <datalist id="bekannte-anlagentypen">
                  {bekannteTypen.map((t) => (
                    <option key={t} value={t} />
                  ))}
                </datalist>
              </>
            )}
          </Feld>
          <Feld label="Feldname" pflicht fehler={fehlerFeld === "name" ? error : null}>
            {(p) => (
              <input
                {...p}
                value={feldName}
                onChange={(e) => setFeldName(e.target.value)}
                placeholder="z.B. Kennzeichen"
                className={FELD_KLASSE}
              />
            )}
          </Feld>
          <Feld label="Feldtyp">
            {(p) => (
              <Select {...p} value={feldTyp} onChange={(e) => setFeldTyp(e.target.value as AnlagenFeldTyp)}>
                {Object.entries(FELD_TYP_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            )}
          </Feld>
          {error && !fehlerFeld && (
            <p role="alert" className="text-fliess text-st-fehlt">
              {error}
            </p>
          )}
          <button type="submit" disabled={createMutation.isPending} className={`${NEU_BUTTON_KLASSE} w-full`}>
            Feld hinzufügen
          </button>
        </form>
      </AnlegenPanel>

      {isLoading ? (
        <SkeletonList count={3} />
      ) : ladeFehler && !definitionen ? (
        <FehlerZustand fehler={ladeFehler} was="Die Zusatzfelder" onErneut={() => void neuLaden()} />
      ) : gruppen.length === 0 ? (
        <EmptyState
          icon={ListPlus}
          text="Noch keine Zusatzfelder definiert. Lege ein Feld an, damit es bei Anlagen dieses Typs abgefragt wird."
          action={
            <button type="button" onClick={() => setPanelOffen(true)} className={NEU_BUTTON_KLASSE}>
              + Neues Zusatzfeld
            </button>
          }
        />
      ) : (
        <div className="space-y-3">
          {gruppen.map(([typ, felder]) => (
            <div
              key={typ}
              className="card-ap p-4"
            >
              <h2 className="mb-2 text-fliess font-semibold text-label2">{typ}</h2>
              <div className="space-y-1.5">
                {felder!.map((f) => (
                  <div
                    key={f.id}
                    className="flex items-center justify-between rounded-md bg-fill px-3 py-2"
                  >
                    <span className="text-fliess text-label">{f.feld_name}</span>
                    <div className="flex items-center gap-2">
                      <span className="border rounded-[var(--radius-ap-pill)] border-sep px-2 py-0.5 text-meta text-label">
                        {FELD_TYP_LABEL[f.feld_typ]}
                      </span>
                      <AktionsMenue
                        label={`Aktionen für ${f.feld_name}`}
                        eintraege={[
                          {
                            label: "Entfernen",
                            destruktiv: true,
                            onClick: async () => {
                              if (
                                await bestaetigen({
                                  titel: `Feld „${f.feld_name}“ entfernen?`,
                                  bestaetigenLabel: "Entfernen",
                                  destruktiv: true,
                                })
                              )
                                deleteMutation.mutate(f.id);
                            },
                          },
                        ]}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
