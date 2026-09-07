/**
 * Vercel Cron Job — keeps the Render backend warm so it never cold-starts.
 * Runs every 14 minutes (Render free tier sleeps after 15 min idle).
 *
 * Vercel cron schedule is defined in vercel.json.
 * This endpoint is called server-side by Vercel — not by the browser.
 */
export const runtime = 'edge'

export async function GET() {
  const backendUrl = process.env.NEXT_PUBLIC_API_URL
  if (!backendUrl) {
    return Response.json({ ok: false, reason: 'NEXT_PUBLIC_API_URL not set' }, { status: 500 })
  }

  try {
    const res = await fetch(`${backendUrl}/health`, {
      signal: AbortSignal.timeout(10_000),
    })
    const data = await res.json()
    return Response.json({ ok: true, status: res.status, backend: data })
  } catch (err) {
    return Response.json({ ok: false, error: String(err) }, { status: 502 })
  }
}
