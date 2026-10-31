// Node 22.18+: remove types only; the upstream source and its .js imports stay unchanged.
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";

const vendor = new URL("../src/vendor/aidenid-classifier/", import.meta.url);
const output = new URL("../src/generated/aidenid-classifier/", import.meta.url);
mkdirSync(output, { recursive: true });
for (const name of readdirSync(new URL("src/", vendor))) {
  if (name.endsWith(".d.mts")) continue;
  const source = readFileSync(new URL(`src/${name}`, vendor), "utf8");
  const runtime = name.endsWith(".ts") ? stripTypeScriptTypes(source, { mode: "strip" }) : source;
  writeFileSync(new URL(name.replace(/\.ts$/, ".js"), output), runtime);
}
