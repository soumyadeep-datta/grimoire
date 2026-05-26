'use client'

/**
 * AuroraBackground — three slow-drifting warm gradient orbs.
 *
 * Renders fixed behind everything else. Champagne + sage + terracotta haze
 * that drifts over 32-44 second cycles. Inspired by Apple Vision Pro's
 * atmospheric backdrop, tuned to the Cigarettes After Sex at 2am mood.
 *
 * Pure CSS — no JavaScript animation loop, no performance cost beyond
 * the GPU compositor (which handles transform + filter on layers).
 */

export function AuroraBackground() {
  return (
    <div
      aria-hidden
      style={{
        position: 'fixed',
        inset: 0,
        overflow: 'hidden',
        pointerEvents: 'none',
        zIndex: 0,
      }}
    >
      {/* Champagne / warm gold haze — top left, largest */}
      <div
        style={{
          position: 'absolute',
          top: '-15%',
          left: '20%',
          width: '900px',
          height: '900px',
          borderRadius: '50%',
          background:
            'radial-gradient(circle, rgba(201, 177, 135, 0.38) 0%, rgba(180, 158, 109, 0.18) 30%, transparent 65%)',
          filter: 'blur(90px)',
          animation: 'grimoire-drift-1 38s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        }}
      />

      {/* Warm sage / dried herb — bottom right */}
      <div
        style={{
          position: 'absolute',
          bottom: '-20%',
          right: '5%',
          width: '800px',
          height: '800px',
          borderRadius: '50%',
          background:
            'radial-gradient(circle, rgba(138, 157, 125, 0.32) 0%, rgba(89, 117, 91, 0.14) 35%, transparent 65%)',
          filter: 'blur(100px)',
          animation: 'grimoire-drift-2 44s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        }}
      />

      {/* Deep terracotta accent — middle left, smaller */}
      <div
        style={{
          position: 'absolute',
          top: '35%',
          left: '5%',
          width: '550px',
          height: '550px',
          borderRadius: '50%',
          background:
            'radial-gradient(circle, rgba(165, 102, 72, 0.26) 0%, transparent 60%)',
          filter: 'blur(110px)',
          animation: 'grimoire-drift-3 32s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        }}
      />
    </div>
  )
}