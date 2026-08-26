/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // SPA fallback: only rewrite non-API, non-static, non-Next internal paths
  // This allows React Router to handle client-side navigation
  // while keeping /api/* and /_next/* routes working correctly
  async rewrites() {
    return [
      {
        // Rewrite any non-file path to / so React Router can take over
        source: '/((?!api|_next|static|favicon|public).*)',
        destination: '/',
      },
    ]
  },
}

export default nextConfig
