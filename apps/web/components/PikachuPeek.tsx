/**
 * Decorative SVG mascot (original simplified art — not official Pokémon assets).
 */
export function PikachuPeek() {
  return (
    <>
      {/* Head + face peeking from bottom-right */}
      <div
        className="pointer-events-none fixed -bottom-2 -right-4 z-0 w-[min(42vw,11rem)] select-none sm:w-44 md:w-52"
        aria-hidden
      >
        <svg viewBox="0 0 200 180" className="drop-shadow-[3px_4px_0_#171717] dark:drop-shadow-[3px_4px_0_#000]" xmlns="http://www.w3.org/2000/svg">
          <title>Peek</title>
          {/* Body blob (mostly off-canvas bottom-right) */}
          <ellipse cx="148" cy="168" rx="88" ry="72" fill="#FDE047" stroke="#171717" strokeWidth="3" />
          {/* Left ear */}
          <path
            d="M 95 118 L 72 38 L 88 48 Z"
            fill="#FDE047"
            stroke="#171717"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <path d="M 78 52 L 72 38 L 84 44 Z" fill="#171717" />
          {/* Right ear */}
          <path
            d="M 155 108 L 178 32 L 162 44 Z"
            fill="#FDE047"
            stroke="#171717"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <path d="M 170 48 L 178 32 L 166 42 Z" fill="#171717" />
          {/* Face */}
          <ellipse cx="138" cy="125" rx="52" ry="48" fill="#FDE047" stroke="#171717" strokeWidth="3" />
          {/* Eyes */}
          <ellipse cx="118" cy="118" rx="8" ry="12" fill="#171717" />
          <ellipse cx="116" cy="114" rx="3" ry="4" fill="#fff" />
          <ellipse cx="158" cy="118" rx="8" ry="12" fill="#171717" />
          <ellipse cx="156" cy="114" rx="3" ry="4" fill="#fff" />
          {/* Cheeks */}
          <circle cx="92" cy="132" r="14" fill="#F87171" stroke="#171717" strokeWidth="2" />
          <circle cx="178" cy="132" r="14" fill="#F87171" stroke="#171717" strokeWidth="2" />
          {/* Smile */}
          <path
            d="M 125 142 Q 138 152 151 142"
            fill="none"
            stroke="#171717"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </svg>
      </div>

      {/* Tail zigzag poking from top-left */}
      <div
        className="pointer-events-none fixed -left-1 top-[4.5rem] z-0 w-24 select-none sm:top-20 sm:w-28 md:w-32"
        aria-hidden
      >
        <svg viewBox="0 0 120 140" className="drop-shadow-[2px_3px_0_#171717] dark:drop-shadow-[2px_3px_0_#000]" xmlns="http://www.w3.org/2000/svg">
          <path
            d="M 8 20 L 42 8 L 38 38 L 78 28 L 72 58 L 108 48 L 100 88 L 118 100 L 95 120 L 88 95 L 52 108 L 58 72 L 22 82 L 28 48 L 4 52 Z"
            fill="#CA8A04"
            stroke="#171717"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <path d="M 8 20 L 42 8 L 28 32 Z" fill="#422006" opacity="0.35" />
        </svg>
      </div>
    </>
  );
}
