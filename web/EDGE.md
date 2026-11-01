# SentiLab edge routing

`src/worker.js` retains only its default export. `/api` and `/api/*` keep their
existing proxy and read-only refusal. Other requests pass through `src/edge.js`.

The unchanged AIdenID classifier (commit
`09b2ff466d0fadcb83b09b0f6f213d13f430c9e1`) identifies declared agents, crawlers,
scripts and browser automation. A browser needs its normal navigation headers,
not only a browser user agent. Unknown clients receive the human page. The shipped
Web Bot Auth verifier checks signed requests against the signer's public directory
(250 ms bound); a valid signature proves key control. Only its mapped OpenAI signer
gets an operator verification. User-agent names remain claims. No models run.

The classifier trade-off is intentional: generic automation counts as an agent
(`python-requests` does). A request with no User-Agent is classified as `automation`
(`empty_user_agent`) and gets the agent version on mapped pages, even with
`Accept: text/html`. This is intended: real browsers send a User-Agent. Normal-path
test fixtures explicitly use `UNRECOGNIZED_CLIENT_UA = "unrecognized-client"`, and a
test asserts that the pinned classifier labels that exact value `unknown`.

Safari needs a more precise distinction than just its name or missing Sec-Fetch.
Safari 15.6 with only its UA is `automation`; with the fuller navigation headers
below it is `unknown`, still without Sec-Fetch. The tested iPhone Safari navigation
and Instagram in-app browser are also `unknown` and receive the normal page
(including normal Accept negotiation). Header count, Accept/language, fetch headers
and Cloudflare metadata affect the result. Sparse iPhone or Android WebView requests
can also classify as automation; these are request shapes, not guarantees for every
request from a browser family.

These are the exact headers probed with `classifyRequest(new Request(url, { headers }))`
against the pinned classifier, using GET `/` and no Cloudflare metadata. No additional
headers were supplied. Edge tests also assert the corresponding asset selection.

| Request | Headers | Class / edge route |
| --- | --- | --- |
| Missing UA | `{}` or `{"accept":"text/html"}` | `automation` / agent |
| Fixture | `{"user-agent":"unrecognized-client"}` | `unknown` / normal |
| Script | `{"user-agent":"python-requests/2.31.0"}` | `automation` / agent |
| Safari 15.6, sparse | Safari UA below only | `automation` / agent |
| Safari 15.6, fuller | Safari UA plus all fuller headers below | `unknown` / normal |
| iPhone Safari | All iPhone headers below | `unknown` / normal |
| Instagram | Instagram UA below only | `unknown` / normal |

Safari UA (both probes):

```http
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Safari/605.1.15
```

Additional headers for the fuller Safari probe:

```http
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: en-US,en;q=0.9
Accept-Encoding: gzip
Connection: keep-alive
Upgrade-Insecure-Requests: 1
Cache-Control: max-age=0
```

Complete iPhone Safari probe:

```http
User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1
Accept: text/html
Accept-Language: en-US
Accept-Encoding: gzip
Connection: keep-alive
Upgrade-Insecure-Requests: 1
Cache-Control: max-age=0
```

Complete Instagram probe:

```http
User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 330.0.0.0.0
```

Classification has a 300 ms deadline. Exceptions, timeouts, directory failures,
invalid routing seams and failed agent asset responses fall back to the original
page. Missing or failing telemetry has no effect on routing or page responses.
`agentPathFor(pathname)` comes from forge's unchanged `src/agent-paths.js`
(PR #66, head `609d339d79cfa0c120806fc5132044b460db5cd3`). `/` and `/sentilab/` map
to `/agents/index.md`; `/sentilab/package/` maps to `/agents/physics.md`. Classified
agents call forge's `serveAgentVersion(request, env)` with the original request,
regardless of Accept. It selects JSON when preferred and available, otherwise markdown;
a null result uses the normal asset path. For other clients, the existing `asset()`
path keeps forge's Accept negotiation and alternate Link on the human page.
`/agents` and `/agents/` serve the agent index. Classification/routing errors bypass
negotiation and serve the original page. A failed classified asset falls back to
that page. Forge's source modules and every file under `web/public/` stay unchanged.
The integration test pins both module SHA-256 values:

- `agent-paths.js`: `cc43963e0b71c36320ec9ec91cacbc9cb291279c4ec87f8818c673aeb5836cb2`
- `agent-view.js`: `ae48a726abfd64eb9ce28e17312e9bae320067e0b27ba982040f54b7070f104d`

Human response bodies, status and unrelated headers are unchanged, apart from forge's
alternate Link on negotiated human pages. Static responses keep the CSP. Only
GET/HEAD paths with an agent version and responses setting the human cookie get `Cache-Control: private, no-store` plus `Vary` on
User-Agent, Accept, Signature, Signature-Input, Signature-Agent, Cookie, the
browser navigation/client-hint headers and Referer, preserving existing Vary
values through forge's `varyWith`. Other paths keep their original cache headers. Header count and Cloudflare metadata also influence classification;
no-store is required even with Vary. Agent markdown/JSON types come from forge's
`CONTENT_TYPES`; human asset content types pass through unchanged.

`?view=human` bypasses classification and sets
`sl_view=human; Max-Age=1800; Path=/; Secure; SameSite=Lax`. That exact cookie forces
the original page for 30 minutes, overriding both classification and Accept negotiation.
Existing Set-Cookie headers are preserved. These
requests are not observed.

**Agent door.** `worker.js` passes `serveAgent: serveWallOrAgentVersion` (`src/door/door.js`),
and `withEdge` hands it `{ identity, ctx }` as a third argument. With a usable
`DOOR_TOKEN_KEY`, a classified agent's GET or HEAD of a mapped page gets the wall ("What are
you here to do?": plain purpose links and a GET form) until it holds a valid scoped purpose
token of this host (`?t=`), and then the agent version above. Without the key the door is
closed and this section does not apply. The door's own routes (`/agents/intent`,
`/agents/engram`, `/agents/check`, `/agents/submit`, `/agents/status/<run_id>`,
`/agents/board`, `/s`) are answered before `withEdge`; `identityFor` gives them the same bounded
identity for arrivals. The `/api` proxy drops every `x-door-*` request header.

## Aquarium and privacy

**Posting is OFF by default.** `AQUARIUM_POST` must be exactly `"on"` to schedule any
observation. Keep it off until the aquarium gap below is fixed in AIdenID. With
posting enabled, only classified agents/automation visiting known public pages by
GET or HEAD are observed. People, unknown clients, arbitrary paths and asset fetches
are not posted.
An observation runs in `ctx.waitUntil`, uses only the `COLLECTOR` binding to
`aidenid-aquarium`, and POSTs to `https://aquarium.internal/api/aquarium/edge` with
`redirect: "manual"`. A 1200 ms deadline aborts the request and also settles the
task if a transport ignores abort. Every observation error is caught. There is no
retry or global-fetch ingest fallback. The operator installs the matching
`INGEST_TOKEN` Worker secret; it is never a plain var or committed value.

The gated future event contains `schemaVersion`, `siteId: "sentilab"`, `sessionId`,
`source`, `eventType`, the actual public `path`, `method` and `identity`. Identity contains the
classifier's operator, label, basis, confidence, verified flag and bounded triage;
signed requests also include status and the verifier's method/components/signer/
keyid. The unchanged upstream registry supplies `identity.observation` (category,
service, verification), so known services get the aquarium's own labels.

No raw IP, user-agent, cookie, query, authorization header, referrer, signature
bytes, request body or geographic detail is sent. A fresh random session UUID is
used per observed request: these are visits, not unique visitors or linked journeys.

## Aquarium gap

At the pinned commit, `projection.mjs`'s `edgeEvent` drops `site` and `siteId`, and
rejects `/sentilab/` and `/sentilab/package/`. `acceptEvent` retains no site on the
visitor/event either. Relabelling these as AIdenID's `/product` would create false
records. **There are no such aliases in this Worker and no production posts.**

Before enabling `AQUARIUM_POST`, AIdenID must validate and retain a site field
through `edgeEvent`, `acceptEvent`, storage and the public view; its path projection
must also accept the actual SentiLab public paths. Alternatively it needs an
explicit site-qualified path contract that truthfully retains the origin, including
the SentiLab homepage. That is a separate change in the AIdenID repo.

Once that schema exists, this is the proposed payload behind the flag:

```json
{
  "schemaVersion": 1,
  "siteId": "sentilab",
  "sessionId": "<fresh per-request UUID>",
  "source": "edge",
  "eventType": "page_view",
  "path": "/sentilab/package/",
  "method": "GET",
  "identity": "<classifier identity and registry observation described above>"
}
```

The known public paths (homepage, lab, package, their index/slashless aliases and
`/agents/index.md`) stay exactly as requested. Queries never leave the Worker.
The collector stamps its own ID/time and derives the section; unused
eventId/occurredAt/bucket fields are omitted. The fake-transport tests exercise
opt-in posting but are not proof the current live collector can record these visits.

## Reproduce and verify

Vendor sources are byte-for-byte copies with per-file SHA-256 in each
`src/vendor/*/VENDORED.json`. The classifier has `.ts` sources with `.js` imports;
`node web/scripts/build-classifier.mjs` uses Node 22.18+ type stripping only to
produce the committed `src/generated/aidenid-classifier` runtime. The provenance
test verifies both original hashes and exact runtime regeneration. No classifier
detection changes or additional package dependencies are introduced.

From the repo root:

```sh
PYTHON=.venv/bin/python node --test web/test/*.test.mjs
node web/test/worker-boot.mjs
node web/test/edge-mutants.mjs
node web/test/edge-ingest-contract.mjs /path/to/aidenid-reference
```

The final command uses the operator-supplied AIdenID reference at the pinned commit,
including the aquarium `projection.mjs` and its imports. It proves default-off
silence and inspects fake opt-in events against the real `edgeEvent` and
`acceptEvent`, proving the documented schema gap. Mutants change human bytes, route classifier errors to agents, wait for
ingest on the response path, and observe people. Each must fail its named assertion.
The full suite's existing verifier tests require the repo's Python dependencies
(`pip install -r requirements.txt` in `.venv`). The web subtree has no package manifest or npm gates; worker-boot runs the pinned
Wrangler dry-run build and real local Workers runtime.

After the content PR and operator deployment, request `/` with `User-Agent: GPTBot`
and check the agent asset's bytes/type, CSP and private cache policy. Request the
same page in a desktop browser and compare bytes against the original asset. Check
`?view=human` and then its cookie using the agent user agent. Confirm no aquarium
post with the default-off flag. After the separate collector fix, enable the flag
and confirm the claimed service arrival **at SentiLab**, with its real path;
people must create none. Repeat with the collector
unavailable and compare page bytes/headers/status. A response alone does not prove
ingest delivery. Live deployment and aquarium observation are operator checks.

Rollback: revert the edge hook and service binding (or deploy the previous Worker).
The human query/cookie is an immediate per-client escape hatch.
