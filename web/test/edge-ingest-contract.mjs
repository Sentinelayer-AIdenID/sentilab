// Integration proof against the actual pinned AIdenID reference, supplied separately.
// node web/test/edge-ingest-contract.mjs /path/to/aidenid-reference
import assert from "node:assert/strict";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { withEdge } from "../src/edge.js";

if (!process.argv[2]) throw new Error("Pass the AIdenID 09b2ff46 reference directory");
const { edgeEvent, acceptEvent } = await import(pathToFileURL(resolve(process.argv[2], "workers/aquarium/src/projection.mjs")));
const now = Date.now();
let checks = 0;
for (const ua of ["GPTBot", "ClaudeBot", "PerplexityBot", "ChatGPT-User", "Google-Extended", "curl/8.4.0"]) {
  for (const path of ["/", "/sentilab/", "/sentilab/package/"]) {
    const pending = [], posted = [];
    const env = { INGEST_TOKEN: "test-only", COLLECTOR: { async fetch(url, init) {
        posted.push(JSON.parse(init.body));
        return new Response(null, { status: 202 });
      } } };
    const req = new Request(`https://sentilab.aidenid.com${path}?private=query`, { headers: { "user-agent": ua } });
    const ctx = { waitUntil(promise) { pending.push(promise); } };
    const options = { agentPathFor: (value) => value, serve: async () => new Response("page") };
    await withEdge(req, env, ctx, options);
    assert.equal(pending.length, 0, "default configuration must send nothing");
    assert.equal(posted.length, 0);
    env.AQUARIUM_POST = "on"; // Fake transport only: inspect the future payload, never send it live.
    await withEdge(req, env, ctx, options);
    await Promise.all(pending);
    assert.equal(posted.length, 1);
    const body = posted[0];
    assert.equal(body.siteId, "sentilab");
    assert.equal(body.path, path);
    const projected = edgeEvent(body, now, "collector-id");
    if (path !== "/") {
      assert.equal(projected, null, "collector currently rejects the real SentiLab product path");
      checks++;
      continue;
    }
    assert.ok(projected);
    assert.equal(projected.visitorId, `edge:${body.sessionId}`);
    assert.equal(projected.path, path);
    assert.equal(projected.identity.label, body.identity.label);
    assert.deepEqual(projected.identity.observation, body.identity.observation);
    const data = { visitors: [], events: [] };
    assert.equal(acceptEvent(data, projected, now), true);
    assert.equal(data.visitors.length, 1);
    assert.equal(data.visitors[0].siteId, undefined, "site attribution is lost in acceptEvent too");
    // These are schema limits, not assumptions: site metadata is discarded and raw site paths refused.
    assert.deepEqual(edgeEvent({ ...body, siteId: "sentilab", site: "sentilab" }, now, "collector-id"), projected);
    assert.equal(edgeEvent({ ...body, path: "/sentilab/package/" }, now, "collector-id"), null);
    assert.equal(edgeEvent({ ...body, sessionId: "invalid" }, now, "collector-id"), null);
    const signed = { ...body, identity: { ...body.identity, operator: "openai", status: "verified", verified: true,
      basis: "web_bot_auth", verification: { method: "web_bot_auth", signer: "https://chatgpt.com", keyid: "test-key-id",
        components: ["@authority", "signature-agent"] } } };
    assert.equal(edgeEvent(signed, now, "collector-id").identity.status, "verified");
    assert.notEqual(edgeEvent({ ...signed, identity: { ...signed.identity, status: undefined } }, now, "collector-id").identity.status, "verified");
    checks++;
  }
}
console.log(`PASS ${checks} default-off visits send nothing; fake opt-in preserves real site and path`);
console.log("PASS current collector gap: site/siteId discarded by edgeEvent/acceptEvent; SentiLab paths rejected; identity/session contract checked");
