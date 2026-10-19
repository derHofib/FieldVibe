import { ArrowLeft, Info } from "lucide-react";
import type { ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { StatusPille } from "../components/apple/StatusPille";
import { usePortalSlugAusUrl, useRechtliches } from "../hooks/useRechtliches";
import type { RechtlichesAnbieter } from "../types";

// Platzhalter-Seiten für /impressum und /datenschutz, solange der Betreiber
// keine eigenen Rechtstexte (Firmendaten-URL oder VITE_*_URL) hinterlegt hat.
// Bewusst kein Rechtstext: nur die Firmenangaben aus den Firmendaten.

function Hinweiskasten() {
  return (
    <div role="note" className="flex items-start gap-3 rounded-[var(--radius-ap-card)] bg-st-arbeit-bg p-4">
      <Info size={18} strokeWidth={2} className="mt-0.5 shrink-0 text-st-arbeit" aria-hidden="true" />
      <div className="space-y-2">
        <StatusPille status="arbeit" label="Platzhalter" />
        <p className="text-sm text-label">
          Platzhalter – der rechtsgeprüfte Text wird vom Betreiber ergänzt. Bis dahin dienen diese
          Angaben nur der Orientierung.
        </p>
      </div>
    </div>
  );
}

function Block({ titel, children }: { titel: string; children: ReactNode }) {
  return (
    <section className="card-ap space-y-2 p-4">
      <h2 className="text-[13px] font-semibold tracking-wide text-label2 uppercase">{titel}</h2>
      {children}
    </section>
  );
}

function Fehlt() {
  return <p className="text-sm text-label2">Angaben noch nicht hinterlegt</p>;
}

function Zeilen({ zeilen }: { zeilen: Array<[string, string | null | undefined]> }) {
  const befuellt = zeilen.filter(([, wert]) => !!wert);
  if (befuellt.length === 0) return <Fehlt />;
  return (
    <dl className="space-y-1 text-[15px] text-label">
      {befuellt.map(([label, wert]) => (
        <div key={label} className="flex flex-wrap gap-x-2">
          <dt className="text-label2">{label}:</dt>
          <dd className="break-words">{wert}</dd>
        </div>
      ))}
    </dl>
  );
}

function anschrift(a: RechtlichesAnbieter): string[] {
  const ortszeile = [a.plz, a.ort].filter(Boolean).join(" ");
  return [a.strasse, ortszeile, a.land].filter((z): z is string => !!z);
}

function Anschrift({ anbieter }: { anbieter: RechtlichesAnbieter | null | undefined }) {
  const zeilen = anbieter ? anschrift(anbieter) : [];
  if (!anbieter || zeilen.length === 0) return <Fehlt />;
  return (
    <p className="text-[15px] text-label">
      {zeilen.map((z, i) => (
        <span key={i} className="block">
          {z}
        </span>
      ))}
    </p>
  );
}

function Rahmen({ titel, children }: { titel: string; children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const slug = usePortalSlugAusUrl();

  // Direkt aufgerufen (neuer Tab, kein History-Eintrag davor): zurück zur
  // passenden Anmeldung statt ins Leere.
  function zurueck() {
    if (location.key !== "default") navigate(-1);
    else navigate(slug ? `/portal/l/${encodeURIComponent(slug)}` : "/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-gbg text-label">
      <main className="mx-auto max-w-prose space-y-4 px-4 py-8">
        <button
          type="button"
          onClick={zurueck}
          className="btn-touch -ml-2 inline-flex items-center gap-1 rounded-md px-2 text-[15px] text-tint-text hover:opacity-80"
        >
          <ArrowLeft size={16} strokeWidth={2} aria-hidden="true" />
          Zurück
        </button>
        <h1 className="ap-heading text-2xl font-bold text-label">{titel}</h1>
        <Hinweiskasten />
        {children}
      </main>
    </div>
  );
}

export function ImpressumPage() {
  const slug = usePortalSlugAusUrl();
  const { data } = useRechtliches(slug);
  const a = data?.anbieter;

  return (
    <Rahmen titel="Impressum">
      <Block titel="Angaben gemäß § 5 DDG">
        {a ? <p className="text-[17px] font-semibold text-label">{a.name}</p> : <Fehlt />}
      </Block>
      <Block titel="Anschrift">
        <Anschrift anbieter={a} />
      </Block>
      <Block titel="Kontakt">
        <Zeilen
          zeilen={[
            ["Telefon", a?.telefon],
            ["E-Mail", a?.email],
            ["Website", a?.website],
          ]}
        />
      </Block>
      <Block titel="Vertretungsberechtigt">
        <Zeilen zeilen={[["Geschäftsführung", a?.geschaeftsfuehrung]]} />
      </Block>
      <Block titel="Handelsregister">
        <Zeilen zeilen={[["Eintrag", a?.handelsregister]]} />
      </Block>
      <Block titel="Umsatzsteuer-Identifikationsnummer">
        <Zeilen zeilen={[["USt-IdNr.", a?.ust_idnr]]} />
      </Block>
    </Rahmen>
  );
}

export function DatenschutzPage() {
  const slug = usePortalSlugAusUrl();
  const { data } = useRechtliches(slug);
  const a = data?.anbieter;

  return (
    <Rahmen titel="Datenschutzerklärung">
      <Block titel="Verantwortlicher">
        {a ? (
          <>
            <p className="text-[17px] font-semibold text-label">{a.name}</p>
            <Anschrift anbieter={a} />
            <Zeilen
              zeilen={[
                ["Telefon", a.telefon],
                ["E-Mail", a.email],
              ]}
            />
          </>
        ) : (
          <Fehlt />
        )}
      </Block>
      <Block titel="Erklärung">
        <p className="text-sm text-label2">
          Die Datenschutzerklärung dieses Angebots wird vom Betreiber noch bereitgestellt.
        </p>
      </Block>
    </Rahmen>
  );
}
