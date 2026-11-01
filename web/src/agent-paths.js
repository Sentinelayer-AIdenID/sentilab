// Which file under web/public serves the agent version of a requested page. A module of its own so any part of the
// Worker can import it: worker.js may export nothing but its default handler (the Workers runtime treats every named
// export of the main module as an entry point).
const AGENT_PATHS = Object.freeze({
  "/": "/agents/index.md",
  "/sentilab/": "/agents/index.md",
  "/sentilab/package/": "/agents/physics.md",
});

// The agent version of a requested page, or null when the page has none: serve it unchanged.
export function agentPathFor(pathname) {
  return Object.hasOwn(AGENT_PATHS, pathname) ? AGENT_PATHS[pathname] : null;
}
