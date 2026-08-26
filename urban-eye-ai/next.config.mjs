/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // SPA fallback: rewrite all non-Next-internal paths to / so React Router
  // can handle client-side navigation.
  // On Vercel this is also defined in vercel.json — both are fine together.
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
