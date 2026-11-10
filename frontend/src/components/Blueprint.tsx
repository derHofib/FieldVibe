import type { HTMLAttributes, ReactNode } from 'react';

/**
 * Karten-Wrapper (Abschnitt 4.1 "Karte") -- ehemals das "Industry"-Design
 * mit Passermarken-Ecken, seit dem Apple-Redesign schlicht `.card-ap`.
 * Eigener Name bleibt (viele Aufrufer erwarten diese Komponente), aber ohne
 * die frueheren .corner-Spans, deren Optik dem Apple-Stil widerspricht.
 */
export default function Blueprint({
  children,
  className = '',
  ...rest
}: { children: ReactNode; className?: string } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`card-ap ${className}`} {...rest}>
      {children}
    </div>
  );
}
