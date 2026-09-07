import type { HTMLAttributes, ReactNode } from 'react';

/**
 * "Industry"-Design (siehe docs/DESIGN.md): Karten-Wrapper mit
 * Passermarken statt Schatten/Rundung. Rendert die vier .corner-Spans
 * und ueberlaesst Hintergrund/Padding dem Aufrufer via className.
 */
export default function Blueprint({
  children,
  className = '',
  ...rest
}: { children: ReactNode; className?: string } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`blueprint ${className}`} {...rest}>
      <i className="corner tl" aria-hidden="true" />
      <i className="corner tr" aria-hidden="true" />
      <i className="corner bl" aria-hidden="true" />
      <i className="corner br" aria-hidden="true" />
      {children}
    </div>
  );
}
