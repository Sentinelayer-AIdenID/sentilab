// The Content-Security-Policy every static asset response carries (web/src/worker.js adds it), so only our own scripts
// run on the verifier pages: a script the edge injects into the HTML on its way out (its analytics script), any inline
// script or inline style, eval, and any other origin are all refused by the browser. The pages hold no inline code (no
// <script> or <style> blocks, no on* or style="" attributes; styles set from script use the CSSOM).
// A module of its own on purpose: the Workers runtime treats every named export of the Worker's main module as an
// entry point, so worker.js exports nothing but its default handler.
export const CSP = "default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";
