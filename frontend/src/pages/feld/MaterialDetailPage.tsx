import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { lieferantenApi, materialApi, tagsApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";

export function MaterialDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { hatRecht } = useAuth();
  const kannLoeschen = hatRecht("material", "loeschen");

  const deleteMutation = useMutation({
    mutationFn: () => materialApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["material"] });
      navigate("/geschaeft");
    },
  });

  const [form, setForm] = useState({
    bezeichnung: "",
    einheit: "",
    mindestbestand: "",
    einzelpreis: "",
    lieferant_id: "",
    artikelnummer: "",
    bestell_url: "",
  });
  const [neuerTag, setNeuerTag] = useState("");

  const { data: material } = useQuery({
    queryKey: ["material-detail", id],
    queryFn: () => materialApi.get(id!),
    enabled: !!id,
  });
  const { data: lieferanten } = useQuery({ queryKey: ["lieferanten"], queryFn: () => lieferantenApi.list() });
  const { data: alleTags } = useQuery({ queryKey: ["tags"], queryFn: tagsApi.list });

  useEffect(() => {
    if (material) {
      setForm({
        bezeichnung: material.bezeichnung,
        einheit: material.einheit,
        mindestbestand: material.mindestbestand,
        einzelpreis: material.einzelpreis ?? "",
        lieferant_id: material.lieferant_id ?? "",
        artikelnummer: material.artikelnummer ?? "",
        bestell_url: material.bestell_url ?? "",
      });
    }
  }, [material]);

  const speichernMutation = useMutation({
    mutationFn: () =>
      materialApi.update(id!, {
        bezeichnung: form.bezeichnung,
        einheit: form.einheit,
        mindestbestand: form.mindestbestand,
        einzelpreis: form.einzelpreis || undefined,
        lieferant_id: form.lieferant_id || undefined,
        artikelnummer: form.artikelnummer || undefined,
        bestell_url: form.bestell_url || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["material-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["material"] });
    },
  });

  const tagHinzufuegenMutation = useMutation({
    mutationFn: async () => {
      const label = neuerTag.trim().toLowerCase().replace(/^#/, "");
      const bestehender = alleTags?.find((t) => t.label === label);
      const tagId = bestehender ? bestehender.id : (await tagsApi.create(label)).id;
      await tagsApi.assign(tagId, "material", id!);
    },
    onSuccess: () => {
      setNeuerTag("");
      queryClient.invalidateQueries({ queryKey: ["material-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["material"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });

  const tagEntfernenMutation = useMutation({
    mutationFn: (tagId: string) => tagsApi.unassign(tagId, "material", id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["material-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["material"] });
    },
  });

  if (!material) return <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>;

  const zugewieseneTags = (material.tag_ids ?? [])
    .map((tagId) => alleTags?.find((t) => t.id === tagId))
    .filter((t): t is NonNullable<typeof t> => !!t);
  const verfuegbareTags = (alleTags ?? []).filter((t) => !material.tag_ids.includes(t.id));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-slate-400">
          ← Zurück
        </button>
        {kannLoeschen && (
          <button
            onClick={() => {
              if (window.confirm("Material wirklich löschen? Es wandert in den Papierkorb.")) {
                deleteMutation.mutate();
              }
            }}
            disabled={deleteMutation.isPending}
            className="btn-touch text-sm font-medium text-red-700 disabled:opacity-50 dark:text-red-400"
          >
            Material löschen
          </button>
        )}
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">{material.bezeichnung}</h1>
        <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
          Gesamtbestand: {material.bestand_gesamt} {material.einheit}
        </p>
        {material.bestaende.length > 0 && (
          <div className="mt-2 space-y-1 border-t border-slate-100 pt-2 text-xs dark:border-slate-800">
            {material.bestaende.map((b) => (
              <div key={b.lager_id} className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                <span>{b.lager_bezeichnung}</span>
                <span>
                  {b.menge} {material.einheit}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">Stammdaten</h2>
        <div>
          <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Bezeichnung</label>
          <input
            value={form.bezeichnung}
            onChange={(e) => setForm({ ...form, bezeichnung: e.target.value })}
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Einheit</label>
            <input
              value={form.einheit}
              onChange={(e) => setForm({ ...form, einheit: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Mindestbestand</label>
            <input
              type="number"
              step="0.01"
              value={form.mindestbestand}
              onChange={(e) => setForm({ ...form, mindestbestand: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Artikelnummer</label>
            <input
              value={form.artikelnummer}
              onChange={(e) => setForm({ ...form, artikelnummer: e.target.value })}
              placeholder="z.B. 5SY4116-7"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
              Einkaufspreis (EUR, Richtwert)
            </label>
            <input
              type="number"
              step="0.01"
              value={form.einzelpreis}
              onChange={(e) => setForm({ ...form, einzelpreis: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <div className="col-span-2">
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">Lieferant</label>
            <select
              value={form.lieferant_id}
              onChange={(e) => setForm({ ...form, lieferant_id: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="">Kein Lieferant hinterlegt</option>
              {(lieferanten ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </div>
          <div className="col-span-2">
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">
              Bestell-Link (Lieferanten-/Produktseite)
            </label>
            <input
              type="url"
              value={form.bestell_url}
              onChange={(e) => setForm({ ...form, bestell_url: e.target.value })}
              placeholder="https://…"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            {material.bestell_url && (
              <a
                href={material.bestell_url}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-block text-xs text-blue-700 underline dark:text-blue-400"
              >
                Zum Bestell-Link →
              </a>
            )}
          </div>
        </div>
        <button
          disabled={!form.bezeichnung.trim() || speichernMutation.isPending}
          onClick={() => speichernMutation.mutate()}
          className="btn-touch w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        {speichernMutation.isSuccess && (
          <p className="text-center text-xs text-green-600 dark:text-green-400">Gespeichert.</p>
        )}
      </div>

      <div className="space-y-2 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">Tags</h2>
        <div className="flex flex-wrap gap-1.5">
          {zugewieseneTags.length === 0 && (
            <p className="text-sm text-slate-400 dark:text-slate-500">Noch keine Tags zugewiesen.</p>
          )}
          {zugewieseneTags.map((t) => (
            <span
              key={t.id}
              className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            >
              #{t.label}
              <button
                onClick={() => tagEntfernenMutation.mutate(t.id)}
                className="btn-touch text-slate-400 hover:text-red-600 dark:text-slate-500 dark:hover:text-red-400"
                aria-label={`Tag ${t.label} entfernen`}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            list="material-tag-vorschlaege"
            value={neuerTag}
            onChange={(e) => setNeuerTag(e.target.value)}
            placeholder="Tag hinzufügen…"
            className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
          <datalist id="material-tag-vorschlaege">
            {verfuegbareTags.map((t) => (
              <option key={t.id} value={t.label} />
            ))}
          </datalist>
          <button
            disabled={!neuerTag.trim() || tagHinzufuegenMutation.isPending}
            onClick={() => tagHinzufuegenMutation.mutate()}
            className="btn-touch shrink-0 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
          >
            + Hinzufügen
          </button>
        </div>
      </div>
    </div>
  );
}
