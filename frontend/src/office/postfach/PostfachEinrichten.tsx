import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Eye, EyeOff, Loader2, Lock, SlidersHorizontal } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { mailApi } from "../../api/endpoints";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import type { MailAnbieter } from "../../types";
import { LEERE_SERVERWERTE, ServerEinstellungen, werteAusAnbieter, type ServerWerte } from "./ServerEinstellungen";

const ANDERER = "anderer";
const EMAIL_MUSTER = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

interface Props {
  layout: "office" | "feld";
  onFertig: () => void;
  onAbbrechen?: () => void;
}

function domainVon(email: string): string {
  return email.split("@")[1]?.toLowerCase() ?? "";
}

function AnbieterKachel({
  anbieter,
  aktiv,
  onWaehlen,
}: {
  anbieter: MailAnbieter;
  aktiv: boolean;
  onWaehlen: () => void;
}) {
  const gesperrt = !anbieter.unterstuetzt;
  const appPasswort = !!anbieter.hinweis && anbieter.hinweis.includes("App-");
  return (
    <button
      type="button"
      aria-pressed={aktiv}
      aria-disabled={gesperrt || undefined}
      onClick={() => {
        if (!gesperrt) onWaehlen();
      }}
      className={`flex flex-col items-start gap-1 rounded-[var(--radius-ap-card)] p-3.5 text-left transition-colors ${
        aktiv ? "bg-tintbg ring-2 ring-tint" : "bg-card"
      } ${gesperrt ? "cursor-not-allowed opacity-60" : "hover:bg-fill"}`}
    >
      <span
        className="mb-1 flex h-10 w-10 items-center justify-center rounded-[10px] text-sekundaer font-bold text-white"
        style={{ backgroundColor: anbieter.farbe }}
        aria-hidden="true"
      >
        {anbieter.kuerzel}
      </span>
      <span className="text-fliess font-semibold text-label">{anbieter.name}</span>
      <span className="text-meta text-label2">{anbieter.beschreibung}</span>
      {gesperrt ? (
        <span className="text-meta font-medium text-st-arbeit">kommt später (Microsoft-Anmeldung)</span>
      ) : (
        appPasswort && <span className="text-meta font-medium text-st-arbeit">App-Passwort nötig</span>
      )}
    </button>
  );
}

/** Einrichten eines Postfachs: Adresse + Passwort genügen, der Anbieter wird
 * erkannt (oder per Kachel gewählt) und liefert die Servereinstellungen. Das
 * Anlegen testet serverseitig Posteingang und Postausgang und speichert nur
 * bei Erfolg. */
export function PostfachEinrichten({ layout, onFertig, onAbbrechen }: Props) {
  const queryClient = useQueryClient();
  const office = layout === "office";
  const feldId = useId();

  const [email, setEmail] = useState("");
  const [passwort, setPasswort] = useState("");
  const [zeigePasswort, setZeigePasswort] = useState(false);
  const [name, setName] = useState("");
  const [nameManuell, setNameManuell] = useState(false);
  const [gewaehlt, setGewaehlt] = useState<string | null>(null);
  // Adresse, für die der Nutzer per Kachel entschieden hat -- "*" gilt für
  // eine Wahl vor der Adresseingabe. Spätere Erkennung überstimmt sie nicht.
  const [manuellFuer, setManuellFuer] = useState<string | null>(null);
  const [expertenOffen, setExpertenOffen] = useState(false);
  const [werte, setWerte] = useState<ServerWerte>(LEERE_SERVERWERTE);
  const [benutzernameManuell, setBenutzernameManuell] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<"idle" | "ok" | "fehler">("idle");
  const [testFehler, setTestFehler] = useState<string | null>(null);

  const emailGueltig = EMAIL_MUSTER.test(email.trim());
  const emailEntprellt = useDebouncedValue(email.trim().toLowerCase(), 400);
  const erkennenAktiv = EMAIL_MUSTER.test(emailEntprellt);

  const { data: anbieterListe } = useQuery({
    queryKey: ["mail-anbieter"],
    queryFn: () => mailApi.anbieter(),
    staleTime: Infinity,
  });
  const { data: erkennung, isFetching: erkennt } = useQuery({
    queryKey: ["mail-anbieter-erkennen", emailEntprellt],
    queryFn: () => mailApi.anbieterErkennen(emailEntprellt),
    enabled: erkennenAktiv,
    staleTime: Infinity,
  });

  // Erkennung wählt die Kachel, solange der Nutzer für diese Adresse nicht selbst gewählt hat.
  useEffect(() => {
    if (!erkennung || !erkennenAktiv) return;
    if (manuellFuer === "*" || manuellFuer === emailEntprellt) return;
    setGewaehlt(erkennung.anbieter?.id ?? null);
  }, [erkennung, erkennenAktiv, emailEntprellt, manuellFuer]);

  const anbieter: MailAnbieter | null =
    gewaehlt && gewaehlt !== ANDERER
      ? (anbieterListe?.find((a) => a.id === gewaehlt) ??
        (erkennung?.anbieter?.id === gewaehlt ? erkennung.anbieter : null))
      : null;
  const erkannt = erkennung?.anbieter && erkennenAktiv && erkennung.anbieter.id === gewaehlt ? erkennung : null;
  const emailTrim = email.trim();

  // Anbieterwechsel setzt die Serverwerte auf dessen Vorgabe zurück.
  useEffect(() => {
    if (anbieter) setWerte(werteAusAnbieter(anbieter, emailTrim));
    else if (gewaehlt === ANDERER) setWerte({ ...LEERE_SERVERWERTE, imap_benutzername: emailTrim, smtp_benutzername: emailTrim });
    // emailTrim bewusst nicht in den Abhängigkeiten: Adressänderungen laufen im Effekt darunter
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anbieter?.id, gewaehlt]);

  useEffect(() => {
    if (benutzernameManuell) return;
    setWerte((w) => ({ ...w, imap_benutzername: emailTrim, smtp_benutzername: emailTrim }));
  }, [emailTrim, benutzernameManuell]);

  useEffect(() => {
    if (nameManuell) return;
    setName(anbieter?.name ?? domainVon(emailTrim));
  }, [anbieter, emailTrim, nameManuell]);

  const waehleKachel = (id: string) => {
    setGewaehlt(id);
    setManuellFuer(emailGueltig ? emailTrim.toLowerCase() : "*");
    setTestStatus("idle");
    if (id === ANDERER) setExpertenOffen(true);
  };

  const aendereWerte = (neu: ServerWerte) => {
    if (neu.imap_benutzername !== emailTrim || neu.smtp_benutzername !== emailTrim) setBenutzernameManuell(true);
    setWerte(neu);
    setTestStatus("idle");
  };

  const verbindenMutation = useMutation({
    mutationFn: () =>
      mailApi.accounts.create({
        name: name.trim(),
        email_adresse: emailTrim,
        ...werte,
        passwort,
      }),
    onMutate: () => setFehler(null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mail-accounts"] });
      onFertig();
    },
    onError: (err: Error) => setFehler(err.message),
  });

  const testMutation = useMutation({
    mutationFn: () => mailApi.testVerbindung({ ...werte, passwort }),
    onMutate: () => {
      setTestStatus("idle");
      setTestFehler(null);
    },
    onSuccess: () => setTestStatus("ok"),
    onError: (err: Error) => {
      setTestStatus("fehler");
      setTestFehler(err.message);
    },
  });

  const nichtUnterstuetzt = !!anbieter && !anbieter.unterstuetzt;
  const kannVerbinden =
    emailGueltig &&
    !!passwort &&
    !!name.trim() &&
    !!werte.imap_host.trim() &&
    !!werte.smtp_host.trim() &&
    !!werte.imap_benutzername.trim() &&
    !!werte.smtp_benutzername.trim() &&
    !nichtUnterstuetzt;

  const kacheln = (
    <section aria-labelledby={`${feldId}-kacheln`} className="min-w-0">
      <div className="mb-2 flex items-baseline justify-between gap-2 px-1">
        <h2 id={`${feldId}-kacheln`} className="text-meta font-semibold tracking-wide text-label2 uppercase">
          Oder Anbieter auswählen
        </h2>
        {office && <span className="text-meta text-label2">Passt keiner, „Anderer Anbieter“ wählen</span>}
      </div>
      <div className={`grid grid-cols-2 gap-3 ${office ? "md:grid-cols-3 xl:grid-cols-4" : ""}`}>
        {(anbieterListe ?? []).map((a) => (
          <AnbieterKachel key={a.id} anbieter={a} aktiv={gewaehlt === a.id} onWaehlen={() => waehleKachel(a.id)} />
        ))}
        <button
          type="button"
          aria-pressed={gewaehlt === ANDERER}
          onClick={() => waehleKachel(ANDERER)}
          className={`flex flex-col items-start gap-1 rounded-[var(--radius-ap-card)] p-3.5 text-left transition-colors ${
            gewaehlt === ANDERER ? "bg-tintbg ring-2 ring-tint" : "bg-card hover:bg-fill"
          }`}
        >
          <span
            className="mb-1 flex h-10 w-10 items-center justify-center rounded-[10px] bg-fill text-label2"
            aria-hidden="true"
          >
            <SlidersHorizontal size={18} strokeWidth={2} />
          </span>
          <span className="text-fliess font-semibold text-label">Anderer Anbieter</span>
          <span className="text-meta text-label2">Server selbst eintragen</span>
        </button>
      </div>
      {office && (
        <div className="mt-3">
          <Hinweiskasten ton="info">
            Eigene Domain (z. B. @meinbetrieb.de)? Dann erkennt FieldVibe den Anbieter am Mailserver der Domain. Bei GMX
            und WEB.DE muss der Zugriff per IMAP einmal im Postfach des Anbieters erlaubt werden; der Hinweis erscheint
            nach der Auswahl.
          </Hinweiskasten>
        </div>
      )}
    </section>
  );

  const formular = (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (kannVerbinden && !verbindenMutation.isPending) verbindenMutation.mutate();
      }}
      className="card-ap space-y-4 p-5"
    >
      <div>
        <h2 className="text-zeile font-semibold text-label">Postfach verbinden</h2>
        <p className="mt-1 text-sekundaer text-label2">
          E-Mail-Adresse und Passwort genügen. Die Servereinstellungen kennt FieldVibe für die gängigen Anbieter.
        </p>
      </div>

      <div>
        <label htmlFor={`${feldId}-email`} className="mb-1 block text-sekundaer font-medium text-label2">
          E-Mail-Adresse
        </label>
        <input
          id={`${feldId}-email`}
          type="email"
          autoComplete="off"
          className="field-ap"
          value={email}
          placeholder="technik@meinbetrieb.de"
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>

      {erkannt?.anbieter ? (
        <div role="status" className="flex items-start gap-2.5 rounded-[var(--radius-ap-md)] bg-st-erledigt-bg p-3 text-sekundaer text-st-erledigt">
          <Check size={16} strokeWidth={2.5} className="mt-px shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <p className="font-semibold">Anbieter erkannt: {erkannt.anbieter.name}</p>
            <p>
              {erkannt.quelle === "mx"
                ? `Die Domain ${domainVon(emailTrim)} nimmt Mails bei ${erkannt.anbieter.name} an.`
                : `Die Adresse gehört zu ${erkannt.anbieter.name}.`}{" "}
              Server, Ports und Verschlüsselung werden übernommen.
            </p>
          </div>
        </div>
      ) : (
        erkennung &&
        !erkennung.anbieter &&
        erkennenAktiv &&
        !anbieter &&
        gewaehlt !== ANDERER && (
          <Hinweiskasten ton="info">
            Anbieter nicht erkannt. Bitte rechts auswählen oder die Servereinstellungen selbst festlegen.
          </Hinweiskasten>
        )
      )}
      {erkennt && emailGueltig && !erkannt && (
        <p className="flex items-center gap-1.5 text-sekundaer text-label2">
          <Loader2 size={13} className="animate-spin" aria-hidden="true" /> Anbieter wird gesucht…
        </p>
      )}

      <div>
        <label htmlFor={`${feldId}-pw`} className="mb-1 block text-sekundaer font-medium text-label2">
          Passwort
        </label>
        <div className="relative">
          <input
            id={`${feldId}-pw`}
            type={zeigePasswort ? "text" : "password"}
            autoComplete="new-password"
            className="field-ap pr-10"
            value={passwort}
            onChange={(e) => setPasswort(e.target.value)}
          />
          <button
            type="button"
            onClick={() => setZeigePasswort((z) => !z)}
            aria-label={zeigePasswort ? "Passwort verbergen" : "Passwort anzeigen"}
            className="absolute top-1/2 right-1 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-label2 hover:bg-fill"
          >
            {zeigePasswort ? <EyeOff size={16} strokeWidth={2} /> : <Eye size={16} strokeWidth={2} />}
          </button>
        </div>
        {anbieter?.hinweis && <p className="mt-1 text-meta text-label2">{anbieter.hinweis}</p>}
      </div>

      <div>
        <label htmlFor={`${feldId}-name`} className="mb-1 block text-sekundaer font-medium text-label2">
          Name (nur für dich sichtbar)
        </label>
        <input
          id={`${feldId}-name`}
          className="field-ap"
          value={name}
          placeholder="z. B. Geschäftlich"
          onChange={(e) => {
            setName(e.target.value);
            setNameManuell(true);
          }}
        />
      </div>

      {nichtUnterstuetzt && (
        <Hinweiskasten ton="warnung">
          {anbieter.name} lässt die Anmeldung per Passwort nicht mehr zu. Die Anmeldung über Microsoft kommt später;
          bis dahin kann dieses Postfach nicht verbunden werden.
        </Hinweiskasten>
      )}

      {expertenOffen && (
        <div className="space-y-4 rounded-[var(--radius-ap-md)] bg-fill p-4">
          <ServerEinstellungen
            werte={werte}
            onChange={aendereWerte}
            vorgabe={anbieter ? werteAusAnbieter(anbieter, emailTrim) : null}
          />
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={!passwort || !werte.imap_host || !werte.smtp_host || testMutation.isPending}
              onClick={() => testMutation.mutate()}
              className="btn-ap flex items-center gap-1.5 disabled:opacity-40"
            >
              {testMutation.isPending && <Loader2 size={13} className="animate-spin" aria-hidden="true" />}
              Verbindung testen
            </button>
            {testStatus === "ok" && <span className="text-sekundaer font-medium text-st-erledigt">Verbindung erfolgreich.</span>}
          </div>
          {testStatus === "fehler" && testFehler && <Hinweiskasten ton="fehler">{testFehler}</Hinweiskasten>}
        </div>
      )}

      {fehler && <Hinweiskasten ton="fehler">{fehler}</Hinweiskasten>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setExpertenOffen((o) => !o)}
          aria-expanded={expertenOffen}
          className="flex items-center gap-1.5 text-sekundaer font-medium text-tint"
        >
          <SlidersHorizontal size={14} strokeWidth={2} aria-hidden="true" />
          Servereinstellungen selbst festlegen
        </button>
        <div className="flex items-center gap-2">
          {onAbbrechen && (
            <button type="button" onClick={onAbbrechen} className="btn-ap">
              Abbrechen
            </button>
          )}
          <button
            type="submit"
            disabled={!kannVerbinden || verbindenMutation.isPending}
            className="btn-ap-primary flex items-center gap-1.5 px-4 disabled:opacity-40"
          >
            {verbindenMutation.isPending && <Loader2 size={13} className="animate-spin" aria-hidden="true" />}
            {verbindenMutation.isPending ? "Verbinde…" : "Verbinden"}
          </button>
        </div>
      </div>

      <div className="flex items-start gap-2 rounded-[var(--radius-ap-md)] bg-fill p-3 text-sekundaer text-label2">
        <Lock size={14} strokeWidth={2} className="mt-0.5 shrink-0" aria-hidden="true" />
        <p>
          Beim Verbinden prüft FieldVibe zuerst Posteingang und Postausgang. Das Passwort wird verschlüsselt gespeichert
          und ist für niemanden im Betrieb sichtbar.
        </p>
      </div>
    </form>
  );

  if (!office) {
    return (
      <div className="space-y-5">
        {formular}
        {kacheln}
      </div>
    );
  }

  return (
    <div className="grid max-w-[1400px] grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,520px)_minmax(0,1fr)]">
      {formular}
      {kacheln}
    </div>
  );
}
