import { useEffect, useState } from "react";

/** Verzögert einen schnell wechselnden Wert (Suchfeld), damit nicht jeder Tastendruck eine Anfrage auslöst. */
export function useDebouncedValue<T>(wert: T, verzoegerungMs = 300): T {
  const [verzoegert, setVerzoegert] = useState(wert);
  useEffect(() => {
    const t = window.setTimeout(() => setVerzoegert(wert), verzoegerungMs);
    return () => window.clearTimeout(t);
  }, [wert, verzoegerungMs]);
  return verzoegert;
}
