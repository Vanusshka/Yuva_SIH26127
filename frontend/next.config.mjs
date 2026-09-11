/** @type {import('next').NextConfig} */
// Build: 2026-09-11c

const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // SPA fallback: rewrite all non-Next paths to / so React Router handles them
  async rewrites() {
    return [
      {
        source: '/((?!api|_next|static|favicon|public).*)',
        destination: '/',
      },
    ]
  },
}

export default nextConfig
