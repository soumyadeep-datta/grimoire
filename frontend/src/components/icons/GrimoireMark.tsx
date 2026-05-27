'use client'

/**
 * GrimoireMark — the five-petal grimoire flower symbol.
 *
 * Inspired by the grimoires from Black Clover, where each grimoire grants its
 * bearer power based on what's written inside. Grimoire (the app) makes
 * personal knowledge searchable and alive in the same way.
 *
 * Two source assets:
 *   - /icons/grimoire-mark.svg       — clean transparent symbol (uses
 *                                       currentColor) for all UI chrome
 *   - /icons/grimoire-mark-hero.svg  — textured/grunge full-color version
 *                                       for the empty-state hero only
 *
 * The clean variant inherits its color from CSS `color`, so tinting is just
 * a matter of setting `color: ...` via the `tint` prop or a parent style.
 * No filter tricks needed.
 */

interface GrimoireMarkProps {
  /** Pixel size — applies to both width and height (square). Default: 32 */
  size?: number
  /** Force a specific asset variant. Defaults to auto: clean below 64px, hero above. */
  variant?: 'auto' | 'clean' | 'hero'
  /** Tint preset for the clean variant. Ignored when using the hero asset. */
  tint?: 'default' | 'black' | 'gold' | 'sage' | 'cream' | 'muted'
  className?: string
  style?: React.CSSProperties
}

/**
 * Color presets for the clean SVG (which uses fill="currentColor").
 * 'default' lets the parent component or CSS decide via inherited color.
 */
const tintColors: Record<NonNullable<GrimoireMarkProps['tint']>, string | undefined> = {
  default: undefined,
  black: '#000000',
  gold: 'var(--grimoire-gold)',
  sage: 'var(--grimoire-sage)',
  cream: 'var(--grimoire-gold-soft)',
  muted: 'var(--grimoire-muted)',
}

export function GrimoireMark({
  size = 32,
  variant = 'auto',
  tint = 'default',
  className,
  style,
}: GrimoireMarkProps) {
  // Auto-pick: hero asset for large displays where its texture reads,
  // clean asset everywhere else.
  const useHero = variant === 'hero' || (variant === 'auto' && size >= 64)

  if (useHero) {
    // Hero is a static raster-traced texture, render via <img>
    return (
      <img
        src="/icons/grimoire-mark-hero.svg"
        alt="Grimoire"
        width={size}
        height={size}
        className={className}
        style={{
          width: size,
          height: size,
          userSelect: 'none',
          pointerEvents: 'none',
          ...style,
        }}
        draggable={false}
      />
    )
  }

  // Clean variant uses the base SVG with currentColor fills, so we can tint
  // it via CSS color. This makes it super flexible for use as UI chrome.
  
  const color = tintColors[tint]
  return (
    <span
      className={className}
      role="img"
      aria-label="Grimoire"
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        backgroundColor: color ?? 'currentColor',
        WebkitMaskImage: 'url(/icons/grimoire-mark.svg)',
        maskImage: 'url(/icons/grimoire-mark.svg)',
        WebkitMaskSize: 'contain',
        maskSize: 'contain',
        WebkitMaskRepeat: 'no-repeat',
        maskRepeat: 'no-repeat',
        WebkitMaskPosition: 'center',
        maskPosition: 'center',
        userSelect: 'none',
        pointerEvents: 'none',
        flexShrink: 0,
        ...style,
      }}
    />
  )
}