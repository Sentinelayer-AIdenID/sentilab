// Browser copy of canonical() from aneta's resultcheck.mjs (CONTRACT v0.2, sha256 4fb7a64e...). That module
// imports node:crypto and uses Buffer, so it can't load in a browser; this file carries only canonical(), with
// the function body unchanged. web/test/sentilab-parity.test.mjs checks it against the original.
export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}
