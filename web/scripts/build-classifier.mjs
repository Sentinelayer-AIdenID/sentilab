// Node 22.18+: remove types only; the upstream source and its .js imports stay unchanged.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";

const vendor = new URL("../src/vendor/aidenid-classifier/", import.meta.url);
const output = new URL("../src/generated/aidenid-classifier/", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("VENDORED.json", vendor)));
mkdirSync(output, { recursive: true });
for (const { path } of manifest.files) {
  const name = path.slice(4);
  if (name.endsWith(".d.mts")) continue;
  const source = readFileSync(new URL(path, vendor), "utf8");
  const runtime = name.endsWith(".ts") ? stripTypeScriptTypes(source, { mode: "strip" }) : source;
  writeFileSync(new URL(name.replace(/\.ts$/, ".js"), output), runtime);
}
