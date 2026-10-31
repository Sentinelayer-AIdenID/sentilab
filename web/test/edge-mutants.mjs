// Each mutant runs in a disposable copy; the working checkout is never modified.
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const mutations = [
  ["3: change human response bytes", "browser preserves original bytes", 'return new Response(response.body,', 'return new Response("mutated human bytes",'],
  ["6: classifier error selects agent", "classifier exception serves", 'catch { return null; }', 'catch { return { triage: { class: "declared_agent" } }; }'],
  ["7: wait for collector on response path", "collector rejection and timeout", 'ctx.waitUntil(observe(request, env, identity));', 'await observe(request, env, identity);'],
  ["8: observe people", "people and unknown clients", 'if (audience(identity) === "agent" && env.AQUARIUM_POST === "on" && typeof ctx?.waitUntil === "function")', 'if (env.AQUARIUM_POST === "on" && typeof ctx?.waitUntil === "function")'],
];
for (const [name, pattern, before, after] of mutations) {
  const dir = mkdtempSync(join(tmpdir(), "edge-mutant-"));
  try {
    cpSync(new URL("../src/", import.meta.url), join(dir, "src"), { recursive: true });
    mkdirSync(join(dir, "test"));
    cpSync(new URL("edge.test.mjs", import.meta.url), join(dir, "test", "edge.test.mjs"));
    const file = join(dir, "src", "edge.js");
    const source = readFileSync(file, "utf8");
    assert.equal(source.split(before).length, 2, `unique mutation point: ${name}`);
    writeFileSync(file, source.replace(before, after));
    const result = spawnSync(process.execPath, ["--test", `--test-name-pattern=${pattern}`, join(dir, "test", "edge.test.mjs")],
      { encoding: "utf8", timeout: 10000 });
    assert.equal(result.status, 1, `${name}: expected assertion failure, got ${result.status}\n${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /ERR_ASSERTION/, `${name}: must fail an assertion, not an import or syntax error`);
    console.log(`KILLED ${name}: ${result.stdout.split("\n").find((line) => line.startsWith("not ok"))}`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
console.log("PASS 4/4 requested mutants fail their behavioral assertions");
