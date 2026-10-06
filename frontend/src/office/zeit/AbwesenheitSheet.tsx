import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { abwesenheitenApi, usersApi } from "../../api/endpoints";
import { Sheet } from "../../components/apple/Sheet";
import { useAuth } from "../../context/AuthContext";
import type { AbwesenheitArt } from "../../types";
import { ABWESENHEIT_ARTEN, ABWESENHEIT_ART_LABEL } from "../../utils/abwesenheit";
import { toDateInput } from "../../utils/zeiterfassung";

const FORM_ID = "abwesenheit-formular";

export function AbwesenheitSheet({
  onClose,
  onGespeichert,
  vorbelegtesDatum,
  vorbelegterUserId,
}: {
  onClose: () => void;
  onGespeichert: () => void;
  /** YYYY-MM-DD; ohne Angabe heute. */
  vorbelegtesDatum?: string;
  vorbelegterUserId?: string;
}) {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();
  const darfVerwalten = !!currentUser?.darf_abwesenheiten_verwalten;
  const startTag = vorbelegtesDatum ?? toDateInput(new Date());

  const [art, setArt] = useState<AbwesenheitArt>("urlaub");
  const [von, setVon] = useState(startTag);
  const [bis, setBis] = useState(startTag);
  const [halbVon, setHalbVon] = useState(false);
  const [halbBis, setHalbBis] = useState(false);
  const [notiz, setNotiz] = useState("");
  const [userId, setUserId] = useState(vorbelegterUserId ?? currentUser?.id ?? "");
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: users } = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl, enabled: darfVerwalten });

  const eintagig = von === bis;

  const anlegen = useMutation({
    mutationFn: () =>
      abwesenheitenApi.anlegen({
        art,
        von,
        bis,
        halber_tag_von: halbVon,
        // Bei einem einzelnen Tag reicht ein Flag; das zweite wuerde nur doppelt gesetzt.
        halber_tag_bis: eintagig ? false : halbBis,
        notiz: notiz.trim() || null,
        ...(darfVerwalten && userId && userId !== currentUser?.id ? { user_id: userId } : {}),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["abwesenheiten"] });
      void queryClient.invalidateQueries({ queryKey: ["arbeitszeit-saldo"] });
      void queryClient.invalidateQueries({ queryKey: ["zeiterfassung-monat"] });
      onGespeichert();
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Antrag konnte nicht gespeichert werden."),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFehler(null);
    anlegen.mutate();
  }

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Abwesenheit beantragen"
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint-text">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form={FORM_ID}
          disabled={anlegen.isPending}
          className="text-[17px] font-semibold text-tint-text disabled:opacity-50"
        >
          Senden
        </button>
      }
    >
      <form id={FORM_ID} onSubmit={handleSubmit} className="space-y-3 p-4">
        {darfVerwalten && (
          <label className="block text-xs font-medium text-label2">
            Mitarbeiter
            <select className="field-ap mt-1" value={userId} onChange={(e) => setUserId(e.target.value)}>
              {(users ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
              {!users && currentUser && <option value={currentUser.id}>{currentUser.name}</option>}
            </select>
          </label>
        )}
        <label className="block text-xs font-medium text-label2">
          Art
          <select className="field-ap mt-1" value={art} onChange={(e) => setArt(e.target.value as AbwesenheitArt)}>
            {ABWESENHEIT_ARTEN.map((a) => (
              <option key={a} value={a}>
                {ABWESENHEIT_ART_LABEL[a]}
              </option>
            ))}
          </select>
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-xs font-medium text-label2">
            Von
            <input
              type="date"
              required
              className="field-ap mt-1"
              value={von}
              onChange={(e) => {
                setVon(e.target.value);
                if (bis < e.target.value) setBis(e.target.value);
              }}
            />
          </label>
          <label className="block text-xs font-medium text-label2">
            Bis
            <input
              type="date"
              required
              min={von}
              className="field-ap mt-1"
              value={bis}
              onChange={(e) => setBis(e.target.value)}
            />
          </label>
        </div>
        <div className="space-y-1.5 text-sm text-label">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={halbVon} onChange={(e) => setHalbVon(e.target.checked)} />
            {eintagig ? "Nur halber Tag" : "Erster Tag nur halb"}
          </label>
          {!eintagig && (
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={halbBis} onChange={(e) => setHalbBis(e.target.checked)} />
              Letzter Tag nur halb
            </label>
          )}
        </div>
        <label className="block text-xs font-medium text-label2">
          Notiz (optional)
          <textarea
            rows={3}
            maxLength={2000}
            className="field-ap mt-1"
            value={notiz}
            onChange={(e) => setNotiz(e.target.value)}
          />
        </label>
        {fehler && (
          <p role="alert" className="text-sm text-st-fehlt">
            {fehler}
          </p>
        )}
        <p className="text-xs text-label2">
          {darfVerwalten
            ? "Urlaub und Freizeitausgleich werden direkt genehmigt."
            : art === "krankheit"
              ? "Krankheit gilt sofort als genehmigt."
              : "Urlaub und Freizeitausgleich müssen vom Büro genehmigt werden."}{" "}
          Die Zahl der Tage ermittelt das System aus deinem Arbeitszeit-Soll und den Feiertagen.
        </p>
      </form>
    </Sheet>
  );
}
