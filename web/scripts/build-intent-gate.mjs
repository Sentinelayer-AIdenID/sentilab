// Node 22.18+: the AIdenID intent gate's runtime. Types are removed and nothing else changes, except that the one
// extensionless relative import (./agent-resources) gets its .js extension, which Node ESM needs and a bundler adds.
// The provenance test (web/test/door-vendor.test.mjs) regenerates both files and compares them byte for byte.
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { pathToFileURL } from "node:url";

const vendor = new URL("../src/vendor/aidenid-intent-gate/src/", import.meta.url);
const output = new URL("../src/generated/aidenid-intent-gate/", import.meta.url);

// The runtime module for one vendored TypeScript source.
export function runtimeOf(source) {
  return stripTypeScriptTypes(source, { mode: "strip" }).replace('from "./agent-resources";', 'from "./agent-resources.js";');
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  mkdirSync(output, { recursive: true });
  for (const name of readdirSync(vendor)) {
    writeFileSync(new URL(name.replace(/\.ts$/, ".js"), output), runtimeOf(readFileSync(new URL(name, vendor), "utf8")));
  }
}
