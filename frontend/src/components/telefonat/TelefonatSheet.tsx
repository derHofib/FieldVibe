import { useQuery } from "@tanstack/react-query";
import { Bell, PhoneIncoming, PhoneOutgoing, Timer } from "lucide-react";
import { type FormEvent, useEffect, useId, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { kundenApi, telefonateApi, vorgaengeApi } from "../../api/endpoints";
import { useVorOrtKontakteFuerKunde } from "../../hooks/useVorOrt";
import { useTelefonatAendern, useTelefonatAnlegen, useTelefonatLoeschen } from "../../hooks/useTelefonate";
import { VOR_ORT_ROLLE_LABEL, type Ansprechpartner, type Telefonat, type TelefonatErgebnis } from "../../types";
import {
  ANDERE_PERSON,
  TELEFONAT_ERGEBNIS_LABEL,
  kontaktAuswahlWert,
  kontaktIdAusAuswahl,
  nummerErkennbar,
  arbeitszeitSichtbar,
  baueTelefonatCreate,
  baueTelefonatUpdate,
  dauerSichtbar,
  formularAusTelefonat,
  leeresFormular,
  sortiereAnsprechpartner,
  toLocalInputValue,
  validiereTelefonat,
  type TelefonatFehler,
  type TelefonatFormular,
} from "../../utils/telefonat";
import { Select } from "../apple/Select";
import { GroupedList, GroupedListRow } from "../apple/GroupedList";
import { SegmentedControl } from "../apple/SegmentedControl";
import { Sheet } from "../apple/Sheet";
import { Switch } from "../apple/Switch";
import { useBestaetigung } from "../ConfirmDialog";
import { Feld, FELD_KLASSE } from "../FormularFeld";
import { IconBadge } from "../IconBadge";
import { SearchableSelect } from "../SearchableSelect";
import { Hinweiskasten } from "../Hinweiskasten";
import { formatUhr, uhrLoeschen, uhrSekunden, uhrStoppen, type AnrufUhr } from "./anrufUhr";

export interface TelefonatVorgangOption {
  id: string;
  vorgangsnummer: string;
  titel: string;
}

export interface TelefonatSheetProps {
  offen: boolean;
  onClose: () => void;
  /** Gesetzt = bearbeiten (PATCH) statt anlegen. */
  telefonat?: Telefonat | null;
  kundeId?: string;
  /** Am Vorgang geöffnet: fest, kein Vorgang-Auswahlfeld. */
  vorgangId?: string;
  /** Anzeige "V-00048 · Titel · Kunde" im Kopf der Sheet-Karte. */
  kontextText?: string;
  /** Office-Liste: Kunde muss erst gewählt werden. */
  kundeWaehlbar?: boolean;
  /** Vorgänge des Kunden für die optionale Zuordnung (sonst bei Bedarf geladen). */
  vorgaenge?: TelefonatVorgangOption[];
  /** Ansprechpartner des Kunden (sonst bei Bedarf über die Kunden-API geladen). */
  ansprechpartner?: Ansprechpartner[];
  vorbelegung?: {
    richtung?: "ausgehend" | "eingehend";
    partner?: { ansprechpartnerId?: string | null; name?: string; nummer?: string | null };
  };
  /** Laufende Anruf-Uhr (aus "Anrufen"); Stopp übernimmt die Dauer. */
  uhr?: AnrufUhr | null;
  onGespeichert?: (t: Telefonat | null) => void;
}

const FORM_ID = "telefonat-formular";

export function TelefonatSheet(props: TelefonatSheetProps) {
  if (!props.offen) return null;
  return <TelefonatSheetInhalt {...props} />;
}

function TelefonatSheetInhalt({
  onClose,
  telefonat,
  kundeId: kundeIdProp,
  vorgangId: vorgangIdProp,
  kontextText,
  kundeWaehlbar = false,
  vorgaenge: vorgaengeProp,
  ansprechpartner: ansprechpartnerProp,
  vorbelegung,
  uhr,
  onGespeichert,
}: TelefonatSheetProps) {
  const uid = useId();
  const bestaetigen = useBestaetigung();
  const istBearbeiten = !!telefonat;

  const [gewaehlterKunde, setGewaehlterKunde] = useState("");
  const kundeId = telefonat?.kunde_id ?? kundeIdProp ?? (gewaehlterKunde || undefined);
  const vorgangFest = telefonat?.vorgang_id ?? vorgangIdProp;

  const { data: kundenListe } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
    enabled: kundeWaehlbar && !telefonat,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", kundeId],
    queryFn: () => kundenApi.get(kundeId!),
    enabled: !!kundeId && !ansprechpartnerProp,
  });
  const ansprechpartner = useMemo(
    () => sortiereAnsprechpartner(ansprechpartnerProp ?? kunde?.ansprechpartner ?? []),
    [ansprechpartnerProp, kunde],
  );
  // Ohne Recht auf die Kontakte (oder ohne Netz) bleibt die Auswahl bei den Ansprechpartnern.
  const { data: kontakteVorOrt } = useVorOrtKontakteFuerKunde(kundeId ?? null, {}, !!kundeId);
  const kontakte = useMemo(() => (kontakteVorOrt ?? []).filter((k) => !k.anonymisiert_am), [kontakteVorOrt]);
  const { data: geladeneVorgaenge } = useQuery({
    queryKey: ["vorgaenge", "telefonat-auswahl", kundeId],
    queryFn: () => vorgaengeApi.list({ kunde_id: kundeId!, limit: "200" }),
    enabled: !!kundeId && !vorgangFest && !vorgaengeProp,
  });
  const vorgangOptionen: TelefonatVorgangOption[] = vorgaengeProp ?? geladeneVorgaenge ?? [];

  const [form, setForm] = useState<TelefonatFormular>(() =>
    telefonat
      ? formularAusTelefonat(telefonat, ansprechpartnerProp ?? [])
      : leeresFormular({
          richtung: vorbelegung?.richtung,
          partner: vorbelegung?.partner,
          beginn: uhr ? new Date(uhr.start) : undefined,
        }),
  );
  const [beginnManuell, setBeginnManuell] = useState(!!telefonat || !!uhr);
  // Exakte Sekunden aus der Uhr; sobald jemand die Minuten von Hand ändert, gilt wieder das Feld.
  const [exakt, setExakt] = useState<number | null>(telefonat?.dauer_sekunden ?? null);
  const [laeuft, setLaeuft] = useState(!!uhr);
  const [jetzt, setJetzt] = useState(() => Date.now());
  const [fehler, setFehler] = useState<TelefonatFehler>({});
  const [serverFehler, setServerFehler] = useState<string | null>(null);

  useEffect(() => {
    if (!laeuft) return;
    const timer = window.setInterval(() => setJetzt(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [laeuft]);

  // Beim Bearbeiten kommen die Ansprechpartner evtl. erst nach dem Laden; die Auswahl bleibt dann "Andere Person".
  useEffect(() => {
    if (!telefonat || ansprechpartnerProp) return;
    setForm((f) =>
      f.partnerAuswahl === ANDERE_PERSON && telefonat.ansprechpartner_id && ansprechpartner.some((a) => a.id === telefonat.ansprechpartner_id)
        ? { ...f, partnerAuswahl: telefonat.ansprechpartner_id }
        : f,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ansprechpartner.length]);

  // Ohne Vorbelegung: der operative Ansprechpartner ist die naheliegende Wahl.
  useEffect(() => {
    if (telefonat || form.partnerAuswahl || ansprechpartner.length === 0) return;
    waehlePartner(ansprechpartner[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ansprechpartner.length]);

  // Rufnummer-Erkennung: schlägt Kunde, Person (Ansprechpartner oder Kontakt vor Ort) und offene Vorgänge vor.
  const [nummerSuche, setNummerSuche] = useState(() => (telefonat ? "" : (vorbelegung?.partner?.nummer ?? "")));
  const { data: erkannt } = useQuery({
    queryKey: ["telefon-nummer-zuordnen", nummerSuche],
    queryFn: () => telefonateApi.nummerZuordnen(nummerSuche),
    enabled: !telefonat && nummerErkennbar(nummerSuche),
    retry: false,
  });
  const erkennungAnzeigen = !!erkannt && (!kundeId || kundeId === erkannt.kunde_id);

  function uebernimmErkennung() {
    if (!erkannt) return;
    if (kundeWaehlbar && !kundeIdProp) setGewaehlterKunde(erkannt.kunde_id);
    if (erkannt.vor_ort_kontakt_id) {
      setForm((f) => ({ ...f, partnerAuswahl: kontaktAuswahlWert(erkannt.vor_ort_kontakt_id!), partnerNummer: nummerSuche }));
    } else if (erkannt.ansprechpartner_id) {
      setForm((f) => ({ ...f, partnerAuswahl: erkannt.ansprechpartner_id!, partnerNummer: nummerSuche }));
    }
    // Genau ein offener Vorgang ist die naheliegende Zuordnung; bei mehreren wählt die Person selbst.
    if (!vorgangFest && erkannt.offene_vorgaenge.length === 1) {
      setForm((f) => ({ ...f, vorgangId: erkannt.offene_vorgaenge[0].id }));
    }
  }

  function aendere(teil: Partial<TelefonatFormular>) {
    setForm((f) => ({ ...f, ...teil }));
  }

  function waehlePartner(wert: string) {
    if (wert === ANDERE_PERSON || wert === "") {
      aendere({ partnerAuswahl: wert, partnerName: "", partnerNummer: "" });
      return;
    }
    const kontaktId = kontaktIdAusAuswahl(wert);
    if (kontaktId) {
      const k = kontakte.find((x) => x.id === kontaktId);
      aendere({ partnerAuswahl: wert, partnerName: k?.name ?? "", partnerNummer: k?.telefon ?? "" });
      return;
    }
    const a = ansprechpartner.find((x) => x.id === wert);
    aendere({ partnerAuswahl: wert, partnerName: a?.name ?? "", partnerNummer: a?.telefon ?? "" });
  }

  function setzeDauer(minuten: string) {
    setExakt(null);
    setForm((f) => {
      const min = Number(minuten.replace(",", "."));
      const beginn =
        !beginnManuell && !Number.isNaN(min) ? toLocalInputValue(new Date(Date.now() - min * 60_000)) : f.beginn;
      return { ...f, dauerMinuten: minuten, beginn };
    });
  }

  function stoppen() {
    if (!uhr) return;
    const { dauerSekunden, beginn } = uhrStoppen(uhr);
    setLaeuft(false);
    setExakt(dauerSekunden);
    setBeginnManuell(true);
    aendere({ dauerMinuten: String(Math.max(1, Math.ceil(dauerSekunden / 60))), beginn: toLocalInputValue(beginn) });
  }

  async function schliessen() {
    if (laeuft) {
      const ok = await bestaetigen({
        titel: "Anruf verwerfen?",
        text: "Die laufende Uhr wird gelöscht, das Telefonat nicht gespeichert.",
        bestaetigenLabel: "Verwerfen",
      });
      if (!ok) return;
      uhrLoeschen();
    }
    onClose();
  }

  const fertig = (t: Telefonat | null) => {
    if (uhr) uhrLoeschen();
    onGespeichert?.(t);
    onClose();
  };
  const meldeFehler = (err: unknown) =>
    setServerFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.");

  const anlegen = useTelefonatAnlegen({ onFertig: fertig });
  const aendern = useTelefonatAendern({ onFertig: fertig });
  const loeschen = useTelefonatLoeschen({ onFertig: () => fertig(null) });
  const speichert = anlegen.isPending || aendern.isPending;

  const effektivVorgang = vorgangFest ?? (form.vorgangId || undefined);
  const exaktAktiv = dauerSichtbar(form.ergebnis) ? exakt : null;

  function absenden(e: FormEvent) {
    e.preventDefault();
    setServerFehler(null);
    // Läuft die Uhr noch, zählt "Speichern" wie Stopp.
    let aktuell = form;
    let sek = exaktAktiv;
    if (laeuft && uhr) {
      const s = uhrStoppen(uhr);
      setLaeuft(false);
      sek = s.dauerSekunden;
      aktuell = { ...form, beginn: toLocalInputValue(s.beginn), dauerMinuten: String(Math.max(1, Math.ceil(s.dauerSekunden / 60))) };
      setForm(aktuell);
    }
    const f = validiereTelefonat(aktuell);
    setFehler(f);
    if (Object.keys(f).length > 0) return;
    if (telefonat) {
      aendern.mutate({ id: telefonat.id, body: baueTelefonatUpdate(aktuell, telefonat, sek) }, { onError: meldeFehler });
      return;
    }
    if (!effektivVorgang && !kundeId) {
      setServerFehler("Bitte einen Kunden wählen.");
      return;
    }
    anlegen.mutate(
      baueTelefonatCreate(aktuell, { vorgangId: effektivVorgang, kundeId }, crypto.randomUUID(), sek),
      { onError: meldeFehler },
    );
  }

  async function loescheTelefonat() {
    if (!telefonat) return;
    const ok = await bestaetigen({
      titel: "Telefonat löschen?",
      text: telefonat.zeiterfassung_id
        ? "Die dazu gebuchte Arbeitszeit wird mit gelöscht, solange sie noch nicht gebucht oder abgerechnet ist."
        : undefined,
      bestaetigenLabel: "Löschen",
    });
    if (ok) loeschen.mutate(telefonat.id, { onError: meldeFehler });
  }

  const dauerMin = Number(form.dauerMinuten.replace(",", "."));
  const zeigtArbeitszeit = arbeitszeitSichtbar(effektivVorgang, form.ergebnis);
  const titel = istBearbeiten ? "Telefonat bearbeiten" : "Telefonat erfassen";
  const kopfText = kontextText ?? [telefonat?.vorgang_nummer, telefonat?.vorgang_titel, telefonat?.kunde_name].filter(Boolean).join(" · ");

  return (
    <Sheet
      offen
      onClose={() => void schliessen()}
      titel={titel}
      links={
        <button type="button" onClick={() => void schliessen()} className="text-zeile text-tint">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form={FORM_ID}
          disabled={speichert}
          className="text-zeile font-semibold text-tint disabled:opacity-40"
        >
          Speichern
        </button>
      }
    >
      <form id={FORM_ID} onSubmit={absenden} noValidate className="space-y-4 p-4">
        {kopfText && <p className="text-sekundaer text-label2">{kopfText}</p>}
        {serverFehler && (
          <p role="alert" className="text-fliess text-st-fehlt">
            {serverFehler}
          </p>
        )}

        {uhr && (
          <div className="flex items-center justify-between gap-3 rounded-[var(--radius-ap-card)] bg-fill p-3" aria-live="off">
            <div>
              <div className="text-meta font-semibold uppercase tracking-wide text-label2">
                {laeuft ? "Gespräch läuft" : "Gespräch beendet"}
              </div>
              <div className="font-heading text-[28px] font-semibold tabular-nums text-label" data-testid="anruf-uhr">
                {formatUhr(laeuft ? uhrSekunden(uhr, jetzt) : (exakt ?? 0))}
              </div>
            </div>
            {laeuft && (
              <button type="button" onClick={stoppen} className="btn-touch btn-ap-primary px-5">
                Stopp
              </button>
            )}
          </div>
        )}

        {kundeWaehlbar && !telefonat && !kundeIdProp && (
          <Feld label="Rufnummer (optional)">
            {(p) => (
              <input
                {...p}
                type="tel"
                inputMode="tel"
                maxLength={50}
                placeholder="Nummer eintragen, Kunde wird erkannt"
                defaultValue={nummerSuche}
                onBlur={(e) => setNummerSuche(e.target.value.trim())}
                className={FELD_KLASSE}
              />
            )}
          </Feld>
        )}

        {erkennungAnzeigen && erkannt && (
          <Hinweiskasten ton="info" titel={`Nummer erkannt: ${erkannt.kunde_name}`}>
            {(erkannt.vor_ort_kontakt_id || erkannt.ansprechpartner_id) && (
              <p>
                {erkannt.vor_ort_kontakt_id
                  ? "Passt zu einem Kontakt vor Ort."
                  : "Passt zu einem Ansprechpartner des Kunden."}
              </p>
            )}
            {!vorgangFest && erkannt.offene_vorgaenge.length > 1 && (
              <p>
                Offene Vorgänge: {erkannt.offene_vorgaenge.map((v) => v.vorgangsnummer).join(", ")} – unten auswählen.
              </p>
            )}
            {!vorgangFest && erkannt.offene_vorgaenge.length === 1 && (
              <p>
                Offener Vorgang: {erkannt.offene_vorgaenge[0].vorgangsnummer} · {erkannt.offene_vorgaenge[0].titel}
              </p>
            )}
            <button type="button" onClick={uebernimmErkennung} className="btn-touch font-semibold underline-offset-2 hover:underline">
              Übernehmen
            </button>
          </Hinweiskasten>
        )}

        {kundeWaehlbar && !telefonat && !kundeIdProp && (
          <Feld label="Kunde" pflicht>
            {(p) => (
              <SearchableSelect
                id={p.id}
                value={gewaehlterKunde}
                onChange={(v) => {
                  setGewaehlterKunde(v);
                  aendere({ vorgangId: "", partnerAuswahl: "", partnerName: "", partnerNummer: "" });
                }}
                placeholder="Kunde wählen…"
                options={(kundenListe ?? []).map((k) => ({ value: k.id, label: k.name, sublabel: k.kundennummer }))}
              />
            )}
          </Feld>
        )}

        <div>
          <div className="mb-1 text-meta font-semibold uppercase tracking-wide text-label2">Gespräch</div>
          <SegmentedControl
            ariaLabel="Richtung"
            groesse="touch"
            volleBreite
            wert={form.richtung}
            onChange={(richtung) => aendere({ richtung })}
            optionen={[
              { wert: "ausgehend", label: "Ausgehend" },
              { wert: "eingehend", label: "Eingehend" },
            ]}
          />
          <div className="mt-1 flex items-center gap-1.5 text-meta text-label2" aria-hidden="true">
            {form.richtung === "ausgehend" ? <PhoneOutgoing size={13} /> : <PhoneIncoming size={13} />}
            {form.richtung === "ausgehend" ? "Wir rufen an" : "Anruf kam herein"}
          </div>
        </div>

        <Feld label="Gesprächspartner" pflicht fehler={fehler.partner}>
          {(p) => (
            <div className="space-y-2">
              <Select
                id={p.id}
                aria-invalid={p["aria-invalid"]}
                value={form.partnerAuswahl}
                onChange={(e) => waehlePartner(e.target.value)}
              >
                {!form.partnerAuswahl && <option value="">Bitte wählen…</option>}
                {kontakte.length > 0 ? (
                  <>
                    <optgroup label="Ansprechpartner">
                      {ansprechpartner.map((a) => (
                        <option key={a.id} value={a.id}>
                          {[a.name, a.position, a.telefon].filter(Boolean).join(" · ")}
                        </option>
                      ))}
                    </optgroup>
                    <optgroup label="Kontakte vor Ort">
                      {kontakte.map((k) => (
                        <option key={k.id} value={kontaktAuswahlWert(k.id)}>
                          {[k.name, VOR_ORT_ROLLE_LABEL[k.rolle], k.einheit, k.telefon].filter(Boolean).join(" · ")}
                        </option>
                      ))}
                    </optgroup>
                  </>
                ) : (
                  ansprechpartner.map((a) => (
                    <option key={a.id} value={a.id}>
                      {[a.name, a.position, a.telefon].filter(Boolean).join(" · ")}
                    </option>
                  ))
                )}
                <option value={ANDERE_PERSON}>Andere Person…</option>
              </Select>
              {form.partnerAuswahl === ANDERE_PERSON && (
                <div className="grid grid-cols-2 gap-3">
                  <input
                    aria-label="Name"
                    placeholder="Name"
                    value={form.partnerName}
                    maxLength={200}
                    onChange={(e) => aendere({ partnerName: e.target.value })}
                    className={FELD_KLASSE}
                  />
                  <input
                    aria-label="Telefonnummer"
                    placeholder="Nummer"
                    inputMode="tel"
                    value={form.partnerNummer}
                    maxLength={50}
                    onChange={(e) => aendere({ partnerNummer: e.target.value })}
                    onBlur={(e) => setNummerSuche(e.target.value.trim())}
                    className={FELD_KLASSE}
                  />
                </div>
              )}
            </div>
          )}
        </Feld>

        {kundeId && !vorgangFest && !istBearbeiten && (
          <Feld label="Vorgang (optional)">
            {(p) => (
              <Select id={p.id} value={form.vorgangId} onChange={(e) => aendere({ vorgangId: e.target.value })}>
                <option value="">Ohne Vorgang</option>
                {vorgangOptionen.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.vorgangsnummer} · {v.titel}
                  </option>
                ))}
              </Select>
            )}
          </Feld>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Feld label="Beginn" fehler={fehler.beginn}>
            {(p) => (
              <input
                {...p}
                type="datetime-local"
                value={form.beginn}
                onChange={(e) => {
                  setBeginnManuell(true);
                  aendere({ beginn: e.target.value });
                }}
                className={FELD_KLASSE}
              />
            )}
          </Feld>
          {dauerSichtbar(form.ergebnis) && (
            <Feld label="Dauer (Min)" fehler={fehler.dauer}>
              {(p) => (
                <div>
                  <input
                    {...p}
                    inputMode="numeric"
                    value={form.dauerMinuten}
                    onChange={(e) => setzeDauer(e.target.value)}
                    className={FELD_KLASSE}
                  />
                  <div className="mt-1.5 flex gap-1.5">
                    {[5, 10, 15].map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setzeDauer(String(m))}
                        className="min-h-8 rounded-[var(--radius-ap-pill)] bg-fill px-3 text-sekundaer font-medium text-label"
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </Feld>
          )}
        </div>

        <div>
          <div className="mb-1 text-meta font-semibold uppercase tracking-wide text-label2">Ergebnis</div>
          <SegmentedControl<TelefonatErgebnis>
            ariaLabel="Ergebnis"
            groesse="touch"
            volleBreite
            wert={form.ergebnis}
            onChange={(ergebnis) => aendere({ ergebnis })}
            optionen={(Object.keys(TELEFONAT_ERGEBNIS_LABEL) as TelefonatErgebnis[]).map((wert) => ({
              wert,
              label: TELEFONAT_ERGEBNIS_LABEL[wert],
            }))}
          />
        </div>

        <Feld label="Notiz" pflicht={form.ergebnis === "erreicht"} fehler={fehler.notiz}>
          {(p) => (
            <textarea
              {...p}
              rows={4}
              maxLength={10000}
              value={form.notiz}
              onChange={(e) => aendere({ notiz: e.target.value })}
              placeholder="Worum ging es, was wurde vereinbart?"
              className={`${FELD_KLASSE} resize-y`}
            />
          )}
        </Feld>

        <div>
          <div className="mb-1 text-meta font-semibold uppercase tracking-wide text-label2">Danach</div>
          <GroupedList>
            <GroupedListRow last={!zeigtArbeitszeit && !form.rueckrufAn}>
              <IconBadge icon={Bell} tone="violet" size="sm" />
              <div className="min-w-0 flex-1">
                <div id={`${uid}-rueckruf`} className="text-zeile text-label">Rückruf</div>
                <div className="text-meta text-label2">Erinnert dich und zeigt „Rückruf“ am Vorgang</div>
              </div>
              <Switch ariaLabel="Rückruf" checked={form.rueckrufAn} onChange={(rueckrufAn) => aendere({ rueckrufAn })} />
            </GroupedListRow>
            {form.rueckrufAn && (
              <GroupedListRow last={!zeigtArbeitszeit}>
                <label htmlFor={`${uid}-rueckruf-am`} className="shrink-0 text-sekundaer text-label2">
                  Am
                </label>
                <input
                  id={`${uid}-rueckruf-am`}
                  type="datetime-local"
                  value={form.rueckrufAm}
                  aria-invalid={!!fehler.rueckruf}
                  onChange={(e) => aendere({ rueckrufAm: e.target.value })}
                  className={`${FELD_KLASSE} flex-1`}
                />
              </GroupedListRow>
            )}
            {fehler.rueckruf && (
              <p role="alert" className="px-4 pb-2 text-sekundaer text-st-fehlt">
                {fehler.rueckruf}
              </p>
            )}
            {zeigtArbeitszeit && !istBearbeiten && (
              <GroupedListRow last>
                <IconBadge icon={Timer} tone="amber" size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="text-zeile text-label">Als Arbeitszeit buchen</div>
                  <div className="text-meta text-label2">
                    {!Number.isNaN(dauerMin) && dauerMin > 0 ? `${Math.ceil(dauerMin)} Min` : "Dauer eintragen"} auf diesen Vorgang, abrechenbar
                  </div>
                </div>
                <Switch ariaLabel="Als Arbeitszeit buchen" checked={form.arbeitszeit} onChange={(arbeitszeit) => aendere({ arbeitszeit })} />
              </GroupedListRow>
            )}
          </GroupedList>
          {istBearbeiten && telefonat?.zeiterfassung_id && (
            <p className="mt-1 text-meta text-label2">
              Arbeitszeit ist gebucht; Änderungen an Beginn und Dauer werden mitgezogen, solange sie nicht gebucht oder abgerechnet ist.
            </p>
          )}
        </div>

        {istBearbeiten && (
          <button
            type="button"
            onClick={() => void loescheTelefonat()}
            disabled={loeschen.isPending}
            className="btn-touch text-sekundaer font-medium text-st-fehlt disabled:opacity-50"
          >
            Telefonat löschen
          </button>
        )}
      </form>
    </Sheet>
  );
}
