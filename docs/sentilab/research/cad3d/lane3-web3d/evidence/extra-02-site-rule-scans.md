# extra-02: our site rules run over the three.js r187 WebGL entry files

Inputs: `package/build/three.module.js` and `package/build/three.core.js` from the npm tarball three-0.187.0.tgz, whose sha512 matched `dist.integrity` (web-01). Read-only scan (Python, isolated mode); nothing was executed.

Rules applied, copied from our tests at 46791be360555d0e24b4ad5f906abafb71f07118:

```text
   20  export const NAMES = [
   21    // vendors, products and models
   22    "typesafe", "jev", "system\\s*one", "cloudflare", "openai", "chatgpt", "gpt", "claude", "anthropic", "grok", "kimi", "gemini",
   23    "deepseek", "qwen", "llama", "mistral", "microduck", "pollen",
   24    // internal agent handles
   25    "warden", "astra", "forge", "pocket-forge", "claude-warden", "gpt-astra", "aneta", "codex", "nightshift", "fable",
   26  ].map((n) => new RegExp(`(?<![\\w-])${n}(?![\\w])`, "i"));
```

```text
   12  const ALLOWED = new Set([0x09, 0x0a, 0x0d]);   // tab, LF, CR
   13  const BINARY = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".wasm", ".zip", ".gz", ".pdf"]);
```

## Results

```text
three.module.js  sha256=104f56145899722094556490d787aae0617cc2fc3382f31df02d724ea1aee341  bytes=658900
  control bytes other than tab/LF/CR: 0
  public-names hits: 0
three.core.js  sha256=613e370f76638fdef83926642bf256dc9615684922de1ce1f63a8583e5d78578  bytes=1474799
  control bytes other than tab/LF/CR: 0
  public-names hits: 1
    line 45192  pattern (?<![\w-])cloudflare(?![\w])  text: // https://github.com/cloudflare/workerd/issues/3657
```

Reading: three.module.js passes both rules. three.core.js has no control bytes but one public-names hit (a source comment naming a vendor's issue tracker), so serving it byte-identical would fail public-names.test.mjs unless the test gets a narrow, pinned exception, or a reproducible minify step strips comments while keeping the @license header.
