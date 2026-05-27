import type { NextConfig } from 'next'

/**
 * Next.js config for Grimoire frontend.
 *
 * Key settings:
 *   - output: 'standalone' — emits .next/standalone for the Docker runner
 *     stage. Reduces final image size from ~1GB to ~150MB.
 *   - allowedDevOrigins — silences cross-origin warnings when accessing
 *     the dev server from another device on the LAN.
 */
const nextConfig: NextConfig = {
  output: 'standalone',
  allowedDevOrigins: ['192.168.1.75', 'localhost', '127.0.0.1'],
}

export default nextConfig