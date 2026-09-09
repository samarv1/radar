// Preview deployments intentionally fall through to VERCEL_URL so their metadata
// points at themselves. Keep NEXT_PUBLIC_SITE_URL scoped to Production only.
export const siteUrl = process.env.NEXT_PUBLIC_SITE_URL
  ? process.env.NEXT_PUBLIC_SITE_URL
  : process.env.VERCEL_URL
  ? `https://${process.env.VERCEL_URL}`
  : "http://localhost:3000";
