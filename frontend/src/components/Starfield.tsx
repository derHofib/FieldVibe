import { useMemo } from "react";

interface Star {
  top: number;
  left: number;
  size: number;
  delay: number;
  duration: number;
}

function erzeugeSterne(anzahl: number): Star[] {
  return Array.from({ length: anzahl }, () => ({
    top: Math.random() * 100,
    left: Math.random() * 100,
    size: Math.random() < 0.15 ? 2.5 : Math.random() < 0.5 ? 1.5 : 1,
    delay: Math.random() * 4,
    duration: 2.5 + Math.random() * 3.5,
  }));
}

/**
 * Rein dekorativer, animierter Sternenhimmel-Hintergrund (CSS-only, kein Canvas).
 * Liegt per absolute/inset-0 hinter dem eigentlichen Seiteninhalt.
 */
export function Starfield() {
  const sterne = useMemo(() => erzeugeSterne(140), []);

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute -left-1/4 -top-1/3 h-[70%] w-[70%] animate-drift rounded-full bg-cyan-500/10 blur-3xl" />
      <div
        className="absolute -bottom-1/3 -right-1/4 h-[70%] w-[70%] animate-drift rounded-full bg-indigo-500/10 blur-3xl"
        style={{ animationDelay: "6s" }}
      />
      {sterne.map((s, i) => (
        <span
          key={i}
          className="absolute animate-twinkle rounded-full bg-white"
          style={{
            top: `${s.top}%`,
            left: `${s.left}%`,
            width: `${s.size}px`,
            height: `${s.size}px`,
            animationDelay: `${s.delay}s`,
            animationDuration: `${s.duration}s`,
          }}
        />
      ))}
    </div>
  );
}
