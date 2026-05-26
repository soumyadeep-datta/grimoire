'use client'

/**
 * GrimoireMark — the five-petal grimoire flower symbol.
 *
 * Inspired by the grimoires from Black Clover, where each grimoire grants its
 * bearer power based on what's written inside. Grimoire (the app) makes
 * personal knowledge searchable and alive in the same way.
 *
 * Two source assets:
 *   - /icons/grimoire-mark.svg       — clean silhouette, used for all UI chrome
 *   - /icons/grimoire-mark-hero.svg  — textured/grunge version, used for the
 *                                       empty-state hero only
 *
 * Selection is automatic based on size (≥64px → hero variant) unless overridden
 * via the `variant` prop.
 */

interface GrimoireMarkProps {
  /** Pixel size — applies to both width and height (square). Default: 32 */
  size?: number
  /** Force a specific asset variant. Defaults to auto: clean below 64px, hero above. */
  variant?: 'auto' | 'clean' | 'hero'
  /** Optional tint preset. Only applies to the `clean` variant. */
  tint?: 'default' | 'champagne' | 'sage' | 'muted'
  /** Optional className passthrough */
  className?: string
  /** Optional inline style overrides */
  style?: React.CSSProperties
}

/**
 * CSS filter strings to tint the white grimoire-mark.svg into other colors.
 * Derived experimentally to match the warm palette.
 */
const tintFilters: Record<NonNullable<GrimoireMarkProps['tint']>, string> = {
  default: 'none',
  champagne: 'brightness(0) saturate(100%) invert(78%) sepia(22%) saturate(556%) hue-rotate(7deg) brightness(92%) contrast(86%)',
  sage: 'brightness(0) saturate(100%) invert(64%) sepia(8%) saturate(630%) hue-rotate(60deg) brightness(91%) contrast(86%)',
  muted: 'brightness(0) saturate(100%) invert(85%) sepia(10%) saturate(180%) hue-rotate(8deg) brightness(95%) contrast(82%) opacity(0.6)',
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
  const src = useHero ? '/icons/grimoire-mark-hero.svg' : '/icons/grimoire-mark.svg'

  // Tinting only applies to the clean variant — the hero artwork is meant
  // to be displayed as-is so its texture is preserved.
  const filter = useHero ? 'none' : tintFilters[tint]

  return (
    <img
      src={src}
      alt="Grimoire"
      width={size}
      height={size}
      className={className}
      style={{
        width: size,
        height: size,
        filter,
        userSelect: 'none',
        pointerEvents: 'none',
        ...style,
      }}
      draggable={false}
    />
  )
}