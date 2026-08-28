interface BrandMarkProps {
  className?: string;
  /** Decorative next to the wordmark; labelled when it stands alone. */
  title?: string;
}

/** The product's terminal mark: a prompt chevron and caret in a rounded chip.
 *
 *  Drawn rather than imported so it inherits the surrounding type scale, stays crisp
 *  at every size, and keeps one source of truth with `public/favicon.svg`. */
export function BrandMark({ className = 'h-7 w-7', title }: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}>

      <rect x="1" y="1" width="30" height="30" rx="8" className="fill-hull-800" />
      <rect
        x="1.75" y="1.75" width="28.5" height="28.5" rx="7.25"
        fill="none"
        strokeWidth="1.5"
        className="stroke-hull-400" />

      <g
        fill="none"
        strokeWidth="2.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-electric">

        <path d="M11 10.5 L16.5 16 L11 21.5" />
        <path d="M17.5 22 H22.5" />
      </g>
    </svg>);

}
