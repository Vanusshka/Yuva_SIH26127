/**
 * Production configuration.
 * Single source of truth for API URL and timeouts.
 */

// Render free tier cold-start takes up to 50 seconds.
// All API calls must wait at least this long before timing out.
export const API_TIMEOUT_MS = 60000

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ||
  'https://urban-eye-backend-ssq1.onrender.com'
