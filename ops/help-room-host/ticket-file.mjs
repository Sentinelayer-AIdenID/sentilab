// Files one help-room ticket for a participant through the CLI's own authenticated transport (the same credential,
// trusted-destination check and idempotent mutation path `sl session ticket claim` uses). The CLI 0.46.5 has no
// `ticket create` command, so the host files tickets for people until it ships.
// Usage: node ticket-file.mjs <sessionId> <requestJson>  (requestJson: {title, body, sourceSequenceId, idempotencyKey})
// Prints one JSON line: {"ok":true,"id":...} or {"ok":false,"error":...}. Never prints a credential.
import process from "node:process";
const CLI = "file:///H:/sl-temp/sl-cli-0465/node_modules/sentinelayer-cli/src";
const { checkedTransport, credentialFor, isAuthenticated } = await import(`${CLI}/auth/credential-destinations.js`);
const { requestJsonMutation } = await import(`${CLI}/auth/http.js`);
const { resolveActiveAuthSession } = await import(`${CLI}/auth/service.js`);
const { urlPathSegment } = await import(`${CLI}/net/url-path.js`);

const [sessionId, raw] = process.argv.slice(2);
try {
  const req = JSON.parse(raw);
  const title = String(req.title || "").trim().slice(0, 200);
  const body = String(req.body || "").trim().slice(0, 7500);
  if (!title || !body) throw new Error("title and body are required");
  const session = await resolveActiveAuthSession({ cwd: process.cwd(), env: process.env, autoRotate: false });
  if (!isAuthenticated(session) || !session?.apiUrl) throw new Error("not authenticated");
  const credential = await credentialFor(session);
  const url = `${String(session.apiUrl).replace(/\/+$/, "")}/api/v1/sessions/${urlPathSegment(sessionId, { label: "sessionId" })}/tickets`;
  const key = String(req.idempotencyKey || "");
  const response = await checkedTransport(requestJsonMutation)(url, {
    method: "POST",
    operationName: "session.ticket_create",
    idempotencyKey: key,
    credential,
    headers: key ? { "Idempotency-Key": key } : {},
    body: { title, body, agent_id: "sentilab-host", ...(req.sourceSequenceId ? { source_sequence_id: Number(req.sourceSequenceId) } : {}) },
  });
  const t = response?.ticket || response;
  console.log(JSON.stringify({ ok: Boolean(t?.id), id: t?.id || null, status: t?.status || null }));
} catch (err) {
  console.log(JSON.stringify({ ok: false, error: String(err?.message || err).slice(0, 300) }));
}
