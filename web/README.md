# thermal.aidenid.com front door

A Cloudflare Worker (`thermal-flight-lab-web`) serves `public/` as static assets and proxies `/api/*` to the
thermal-api Azure Container App named in `wrangler.jsonc` (`API_ORIGIN`). Responses stream, so server-sent events
pass through unchanged. The custom domain is attached by the `routes` entry.

Deploy (warden): `npx wrangler deploy` from this directory. The frontend build (TFL-10) replaces `public/` with the
Vite output directory.
