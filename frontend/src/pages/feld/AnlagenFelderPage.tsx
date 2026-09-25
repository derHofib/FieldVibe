import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { anlagenApi, anlagenFeldDefinitionenApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import type { AnlagenFeldTyp } from "../../types";

const FELD_TYP_LABEL: Record<AnlagenFeldTyp, string> = {
  text: "Text",
  zahl: "Zahl",
  datum: "Datum",
};

export function AnlagenFelderPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [anlagentyp, setAnlagentyp] = useState("");
  const [feldName, setFeldName] = useState("");
  const [feldTyp, setFeldTyp] = useState<AnlagenFeldTyp>("text");
  const [error, setError] = useState<string | null>(null);

  const { data: definitionen } = useQuery({
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
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Feld konnte nicht angelegt werden"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => anlagenFeldDefinitionenApi.remove(id),
    onSuccess: invalidate,
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!anlagentyp.trim() || !feldName.trim()) {
      setError("Bitte Anlagentyp und Feldname angeben");
      return;
    }
    createMutation.mutate();
  }

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-label2">
        ← Zurück
      </button>

      <div>
        <h1 className="text-lg font-bold text-label">Anlagen-Zusatzfelder</h1>
        <p className="mt-1 text-sm text-label2">
          Lege je Anlagentyp (z. B. „Fahrzeug", „Ladestation", „Elektroanlage") eigene Felder fest, die
          beim Anlegen/Bearbeiten einer Anlage dieses Typs zusätzlich abgefragt werden.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="space-y-2 border border-sep bg-card p-4"
      >
        <div>
          <label className="mb-1 block text-sm font-medium text-label">Anlagentyp</label>
          <input
            list="bekannte-anlagentypen"
            value={anlagentyp}
            onChange={(e) => setAnlagentyp(e.target.value)}
            placeholder="z.B. Fahrzeug, Ladestation, Elektroanlage"
            className="btn-touch w-full border border-sep bg-transparent px-3 py-2 text-label"
          />
          <datalist id="bekannte-anlagentypen">
            {bekannteTypen.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </div>
        <div className="flex gap-2">
          <input
            value={feldName}
            onChange={(e) => setFeldName(e.target.value)}
            placeholder="Feldname, z.B. Kennzeichen"
            className="btn-touch flex-1 border border-sep bg-transparent px-3 py-2 text-label"
          />
          <select
            value={feldTyp}
            onChange={(e) => setFeldTyp(e.target.value as AnlagenFeldTyp)}
            className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
          >
            {Object.entries(FELD_TYP_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {error && <p className="text-sm text-st-fehlt ">{error}</p>}
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch w-full rounded-md btn-ap-primary py-2 text-sm font-medium disabled:opacity-50"
        >
          Feld hinzufügen
        </button>
      </form>

      {gruppen.length === 0 ? (
        <p className="text-center text-sm text-label2">Noch keine Zusatzfelder definiert.</p>
      ) : (
        <div className="space-y-3">
          {gruppen.map(([typ, felder]) => (
            <div
              key={typ}
              className="border border-sep bg-card p-4"
            >
              <h2 className="mb-2 text-sm font-semibold text-label2">{typ}</h2>
              <div className="space-y-1.5">
                {felder!.map((f) => (
                  <div
                    key={f.id}
                    className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 dark:bg-stone-800/60"
                  >
                    <span className="text-sm text-label">{f.feld_name}</span>
                    <div className="flex items-center gap-2">
                      <span className="border border-sep px-2 py-0.5 text-xs text-label">
                        {FELD_TYP_LABEL[f.feld_typ]}
                      </span>
                      <button
                        onClick={() => deleteMutation.mutate(f.id)}
                        className="btn-touch text-xs text-st-fehlt "
                      >
                        Entfernen
                      </button>
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
