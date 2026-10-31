# Package 3D: requirement trace

**Companion to SPEC.md v0.2 (2026-10-31).** Every requirement in SPEC.md, PSEUDOCODE.md and ACCEPTANCE.md, mapped to
the source it comes from. Tags: `L1:` lane 1 and `L3:` lane 3 at `253ee4f74f998f52c06e437acf935f2bf7e63067`;
`A#57053`, `A#57059` astra's messages, `A#57218` root's (astra's) review of v0.1, and `A#57278`, `A#57288` root's
notes on the decisions and on the exact producer source map; `C#57177` the ChatGPT field-association/W4 review's
replies under #57177 and `C#57232` its fixture pack; `pr56:` PR #56's successor commit
`7f70baf56998cdeea9fcaa56954fc78f8f6c8071` (a separate source identity, pending review); `F#57046` the founder's ask;
`main:` origin/main at
`d25046256b4a712b529977f31e10b7e32248a9c0`; `pr66:` PR #66 head `609d339d79cfa0c120806fc5132044b460db5cd3` (open,
not merged); `task` the brief for this spec. "This spec" marks a design choice made here, with its reason.

## 1. Inputs and pins

| Input | Where read | sha256 of the bytes read |
|---|---|---|
| Founder's ask (#57046, verbatim) | local `C:/tmp/cad3d-carter-57046.md` | `218c398ee3889c88e1864439755de925f761760ec66e4db37937e078f19c6e23` |
| astra's #57053 and #57059 (verbatim) | local `C:/tmp/cad3d-astra-lane2.md` | `03b85a1315a94710655d020053d59258f7c02a4bdbd3689ff77cb02bd1b5e5f9` |
| astra's full independent report | retained by astra, not read | `cccbe9d165fc358a17108e23ab6cbf1d8bdc4739d049e5e2565a90d430614d97` (her stated seal) |
| Root's review of v0.1, A#57218 (verbatim room text) | local `C:/tmp/cad-w4-work/verbatim/msg-57218-gpt-astra-carter.txt` | `ec1345d39c5108aad558316d3e3c8a8fc1ece9421169d36bb8d2c0f042b538f3` |
| Root's full review of v0.1 and its seal | retained by root (`TASK/cad-spec-review-2137`), not read | review `a8c13fee0ef5a2824fab7f372f44ddfcf8130212a3d4f05d5c5acbf3182aa249`, seal `dffaec2f5ddf65df659621bc34da77fc37218049506205f65ccbca9b2a0371a8` (her stated values) |
| ChatGPT field-association/W4 review, field-contract portion (C#57177, reply action `383df803-be5f-4d23-a8ad-d499f67d944c`; C1-C4) | local `C:/tmp/cad-w4-work/verbatim/reply-57177-chatgpt-383df803.txt` | `66e7e50bd4fe2369adfe251cb14b6ef789a9eed713e5a2e0127b54950c812f9d` |
| ChatGPT field-association/W4 review, model-stack/source portion (C#57177, reply action `96f0434f-4f34-47cb-bd8a-8df2585c4574`; C5-C7) | local `C:/tmp/cad-w4-work/verbatim/reply-57177-chatgpt-96f0434f.txt` | `5ceb4c33fa06d8eea56a3f4449cc90366e49b847213051cade8411af972a722a` |
| ChatGPT's earlier inputs: §5/W4 source review v1 (`d3c13393…`), historical source comparison (`ad9f9aab…`), summary #57265 | local `C:/tmp/cad-w4-work/verbatim/` (three files) | `23e4c65ea00f8ab6f5bbacfefcedc416ed9b90dff719999391b6f07655f1fbeb`, `55416e1ec8df8fba2fa4a2e369d934ccac77aa7dfd9d2c03c9bba6333a6cfca8`, `bc955d324e403d2af826c51a77eb9e2868957f8fa2631bb78196ec2cc3f03992` |
| Root's notes A#57278 (decisions, confirmed source facts) and A#57288 (producer packet) | local `C:/tmp/cad-w4-work/verbatim/msg-57278-gpt-astra-carter.txt`, `msg-57288-gpt-astra-carter.txt` | `60a621905b74a5d675de0a25a86ab19024b88b59ca47d4e22b2da733def5e778`, `67970240a5cd27d2efa332a300b0db477b577d7bac25cf1ac2ea6aecffc02472` |
| Root's exact producer source map | review packet at sentilab `209dad7a43a2f10feaec8d83eb2242e0858953aa`, `docs/sentilab/review-packets/2026-10-31/current-thermal-producer-map-2232/` (README.md, PRODUCER-MAP.json: 17 facts, 57 excerpts; read with `git show`, no code run) | MANIFEST `8670d1e2634df835f33104e6736185c9b8ae628f24c4618011e1676a492f390f`, PRODUCER-MAP `d890443882cc318dd7190f95631d6952523b4f200585a87c4395eeff405c44d2` |
| Draft-pinned writer and C source (main `d250462`) | `git show d250462:<path>` | `sundai_tap/passive_interposer.py` `cecc5b85…` (the TRACE pin above, matched by root's map); `sundai_hotspot/temperature_grid.c` `1d50f58de5593b5620dfd26853a49f81a6ce6688218ce525b59af28b182441df` (the bytes the W4 review compared); `temperature_grid.h` `0b760dfe…`; `sundai_tap/util/fill_space.py` `645c0c37…`; `sundai_controller/controller.py` `963e3ba7…`; `sentilab_core/envelope.py` `2b038618…` |
| PR #56 successor, named separately (`pr56:`) | `git show 7f70baf:<path>` | `sundai_hotspot/slab049.py` `669aef97…`; `sundai_hotspot6/temperature_grid.c` `3ffb58e1…`, `.h` `c8d25c6b…`; `scripts/build_hotspot6.sh` `617ad089…`; `sundai_hotspot/temperature_grid.c` `80e60bf7…` (differs from main's file; its grid writer function is byte-identical) |
| The bytes root reviewed | review packet at sentilab `8f76089c`, `docs/sentilab/review-packets/2026-10-31/chip-knowledge-cad-2200/cad/source/` | all four files byte-identical to `da9b1ee` (SPEC `f581f57e…`, PSEUDOCODE `0976a6f7…`, ACCEPTANCE `80713adb…`, TRACE `012c9180…`), checked with `git show` |
| L1 REPORT.md | 253ee4f7 | `d81ddb2a4c2908f5433660b2a020acd654c9515face01fbb3031eef4f8233203` |
| L1 parts.json | 253ee4f7 | `365dcd0d776b4afca6b17a6ba840ac578b7e99d40e08d0d3b45fa571dc473a60` |
| L1 thermal_path.md | 253ee4f7 | `ef53402ee53ed858af45671bc009796166d662c3a4f40802cb906deac09e727f` |
| L1 our_model_mapping.md | 253ee4f7 | `730690ead071beacecc1e0e71d3b75eddc62c15b128af0bfa11a1c6e77106e59` |
| L1 SOURCES.md | 253ee4f7 | `b25df295695f12cbac30a39409c65c6a899d44f4b76c6348dde20ead90b4ecc9` |
| L1 EVIDENCE-NOT-IN-GIT.md | 253ee4f7 | `06269a676ec40b5ab563da32f0a3469086c26f9c66dd443db4c3e92c531c882f` |
| L3 ARCHITECTURE.md | 253ee4f7 | `6fb1701d2dc2f85fe2c5c5c9dce285e57751f5373e495ea4b44917ab9ac51afc` |
| L3 PSEUDOCODE.md | 253ee4f7 | `1042081818784f820b35b7adc2e084be66238dfd72066917fe9c0fbbbfc1e1ba` |
| L3 ACCEPTANCE.md | 253ee4f7 | `4e117196ff08969f10a957398d1df9998cb1fae972c9377bd2c4c0149ddb0bb5` |
| L3 RISKS.md | 253ee4f7 | `9f267456eb41da602dee00ff6a90a16deee4db81da9f80c20ab4b0092e4f2f8e` |
| L3 evidence/INDEX.md | 253ee4f7 | `3a174d4cf32f08896aaefd639f0d1a9cc5473e103bac2cd4e220dd04700d57d0` |
| web/public/temperature-label.mjs | main | `91628b18d48012a6243d39b9f4c663ddc5814f8eb44cdaf121f10b6733101abe` |
| web/src/csp.js | main | `71338e4e0294bbc0da37329a6fd35bf4ab884a210b5faab9ba83326047342b33` |
| web/src/worker.js | main | `a9a565bc88ef23d45e6a86f4411aecfbe85d190c9ac1be8f1322a399e9993c1d` |
| web/public/sentilab/package/package.js | main | `d5e3e4ffbaaeed56b071e6ce74118d7ac03a16fbdc7800ab4b33b0946c7e022d` |
| web/public/sentilab/package/scene.mjs | main | `8a7db9340d57c8a9069f328c539fdc8818b4758aab4e6a6a1da6ad7d93db3a87` |
| web/public/sentilab/package/source.mjs | main | `85059b5445a02f0da23b0a10a69d4191df584b2f045433f2ae54c38e54170192` |
| web/public/sentilab/package/playhead.mjs | main | `430d22a2ab25ff1f7d31f5941633e3796b853b6fa188f4300182f101506c408f` |
| web/public/sentilab/package/index.html | main | `013cc789e925df7228e6d0bc73110da2614364af0ae70b493927d93fe990f971` |
| web/public/sentilab/canonical.mjs | main | `1b1c1b2bfa77dc08957bf0651ba936a8a7cc3765fb7067cd4e78b143aa58428d` |
| web/public/sentilab/view-core.mjs | main | `dcbcc3e256a719ac708403bcff551559695d099e1994944e48f202dc09d98599` |
| web/public/verify-core.js | main | `6c4fc1f7d4b0c13cf92db2e0fabad9a9c15978ce4f941ef31410a0fc09899360` |
| web/public/app.js | main | `635f63f99e0dd350d46e12d164d1c482b3f4d83a8503a0126f1fa6f02a36e3fc` |
| web/public/replay/ascend910-seed11-32x32.json | main | `e9f643259dfd843d5f52edf244363a03bce2aed3e1a2dc12c0974b3fbabe65c1` |
| web/test/public-names.test.mjs | main | `9173d48de0e54f2647ef35b2ecd404e4bbb1eea7a93aac9bbb87265e2a6a46e7` |
| web/test/control-bytes.test.mjs | main | `bb9534de924e7355c0dcc059d4129bc50a6d60de1f47d2b47c520f39e9cdbce7` |
| web/test/worker-csp.test.mjs | main | `508164f0e324f6054fe603e5f1c68394fe445e8a9570987ef0acf132673563ce` |
| web/test/temperature-label.test.mjs | main | `ae5ce5365985543e01e801a4b1da9d7f8ed5f51a71b9c44f5e84ded07893c105` |
| web/test/per-value-provenance.test.mjs | main | `ea5605d968ced5b5766145085bb04064f64795545ba7132aa88f39ec25821222` |
| contracts/view-envelope-v0.5/VIEW-ENVELOPE.md | main | `7a92d88aca1e4911a5119dbdff15ad096922dc238a67349e087030d45ad53df6` |
| contracts/view-envelope-v0.6.2/VIEW-ENVELOPE.md | main | `a5a04e9c7207ced732889dd4cc06915c15c20a445f7f03e13e4ac2f05edce040` |
| sentilab_core/conductor.py | main | `e0f9139b4a20b4fe49c9ead80d94b2b65c3b8d9206cceaec6a30727ce674e3e3` |
| sundai_tap/passive_interposer.py | main | `cecc5b85f7dd8e6a3816c635879eb06193a270595f6bdbc71b76e4ef96f227df` |
| sundai_tap/util/hotspot.config | main | `1c92fb1c03d279a26ae0fd7a51ac4a9a0fef004223af0f5603c6619d75b949dc` |
| sundai_hotspot/tap_oracle_worker.py | main | `bf0266dba03d980565d337b7092f0ec0589e6f8438045c9860d1af8ea5e145dd` |
| sundai_hotspot/tap_oracle.py | main | `43eeb93ccc6ef6a89876c1efbefc02d43c2262b9b1068307474e69915043fe60` |
| docs/sentilab/references/README.md | main | `4d251cc65efe0231cb1139ac8c3a3fbac7cf2f9d792af60f14ddabf0701625e1` |
| docs/sentilab/references/ascend910-tap25d-fig6a.json | main | `0271e8324f1d4dcf17b7b5d5427c79ac5540f3888d573b96f2b9a5dcd0c11dd6` |
| docs/sentilab/references/ascend910-tap25d-fig6a-snap0p5.json | main | `ed7764052814e63ff224bc82cde33324b782b288e022a1f2a737afe29aa6a202` |
| docs/sentilab/references/micro150-tap25d-fig5a.json | main | `db1193ddb6ccc75cb67e9df9753ffe0ddd84d119cd422c4cb7f5e3c8552b2490` |
| docs/sentilab/references/micro150-tap25d-fig5a-snap0p5.json | main | `00ad046b932470343dac58a73e7c1def3f78b5292e2ae6920c6f84b26a25cb51` |

Checked while writing this spec (not only planned): all 7 schema blocks of SPEC.md parse, every `$ref` resolves, and
each passes the JSON Schema 2020-12 metaschema; 16 positive and negative quantity and result-value instances behave as
SPEC.md says; the temperature pattern of PSEUDOCODE §8 catches and passes exactly its listed controls in Node 22; and
verify-core.js `parseRaw` plus `canonical` reproduce all six stored layout `content_sha256` values (raw and 1 mm for
both references, and both 0.5 mm variants), while a plain `JSON.parse` route does not.

## 2. The brief's hard rules, and where each is encoded

| Rule (task) | Encoded in |
|---|---|
| 1. Withdrawn values; every temperature through the label states; never bare in pixels, DOM or twin | SPEC §3 (Temperatures row), §4.4, §7 PL-2 to PL-8, PL-4; PSEUDOCODE §8, §11 (`assertTwinLabels`); ACCEPTANCE AC-01 to AC-07; D2 |
| 2. Three kinds of content, separate in data and UI | SPEC §3 (X1 to X6), §5.2-§5.6, §6.8; PSEUDOCODE §2, §5; AC-08, AC-09 |
| 3. Unknowns explicit or render hints; stable instance ids, units, transforms; explode a view transform only | SPEC §5.0, §5.1 (`quantity`), §5.3, §6.3, PL-10 to PL-13; PSEUDOCODE §1, §2, §6; AC-10 to AC-14 |
| 4. Real time = the v0.6.2 LIVE rule; completed signed solves; "as of seq K"; SKETCH separate, no °C | SPEC §4.5, §4.9, PL-19, PL-20; PSEUDOCODE §10; AC-23 to AC-26, AC-39 |
| 5. Producer, pointer, API route, `hasTemperature()` as prerequisites, owners TBD | SPEC §8 P1 to P4 (and P5 to P11); W13/W14 gating; D3 records where the rule's wording and origin/main differ |
| 6. CAD per astra: primitives and manifests first; scriptable CAD later behind a trial; exact identities; SolveCraft unresolved | SPEC §10; W16; AC-38 |
| 7. No MicroDuck or Pollen material | SPEC NG8, PL-18; AC-30 |
| 8. No infrastructure vendor or mechanism names; product names an open founder decision | SPEC PL-17, D1, D10; AC-29 |
| 9. Every visual has an agent twin (JSON plus markdown under /agents/) with the same qualifications | SPEC §4.8, §5.8, §6.9, PL-22; PSEUDOCODE §11; AC-36, AC-37; D9 |

## 3. Lane 3 citations that moved between 46791be and d250462

Only `web/` changed between the two commits (`git diff --stat 46791be d250462`: 14 files, all under `web/`). The
moved citations below are the ones lane 3 or this spec use; everything else lane 3 cites is unchanged.

| File | Lane 3 cited (46791be) | Now (d250462) | What |
|---|---|---|---|
| web/public/temperature-label.mjs | :142 | :163 | `hasTemperature` |
| web/test/temperature-label.test.mjs | :320-337 | :320-341 | the notice and labels test |
| web/public/sentilab/package/package.js | :157-161 | :158-161 | rule 1 in `setCursor` |
| package.js | :235-237 | :243 | `requestDraw` (render on demand) |
| package.js | :280-283 | :297-300 | page notice |
| package.js | :407-409 | :428-430 | canvas `aria-label` |
| package.js | :616-620 | :644-648 | no WebCrypto: nothing drawn |
| package.js | :616-632 | :644-660 | trust and first load |
| package.js | :624-626 | :652-654 | `/api/replay/` URL |
| package.js | :634 | :662 | `__packageView` test hook |
| web/public/sentilab/package/scene.mjs | :226-229 | :230-233 | scale rounding |
| scene.mjs | :210-244 | :210-248 | `runFrame` and its comment |
| scene.mjs | :264-271 | :269-275 | `heatColor` |
| scene.mjs | :277-284 | :281-288 | `scaleTicks` |
| scene.mjs | :355-356 | :359-360 | stale state |
| scene.mjs | :373-378 | :377-382 | `metricFor` in the scene |
| web/public/sentilab/package/index.html | :86-101 | :86-102 | basis and schematic-stack blocks |
| package/index.html | :124-135 | :125-136 | Honest limits |
| package/index.html | :130 | :131 | "A glide is display only" |
| web/public/sentilab/package/package.css | :102 | :112 | the desktop grid |

Unchanged and still valid: `source.mjs` (all lines), `playhead.mjs`, `render.mjs`, `view-core.mjs`, `paging.mjs`,
`csp.js`, `worker.js`, `wrangler.jsonc`, the site tests other than the temperature-label test, `lab-model.mjs:124`,
`scene.mjs` lines 18, 23-35, 53, 58, 84-98, `package.js` lines 17, 21-35, 59, and every non-web file.

## 4. Requirement to source

### Goals, non-goals, ground truth (SPEC §1-§2)

| Req | Source |
|---|---|
| G1 page, 3D, exploded, labels, connections | F#57046; L3:ARCHITECTURE §0 (page `/sentilab/package3d/`) |
| G2 three kinds | task rule 2; A#57053 ("keep typical educational anatomy separate from both computational references") |
| G3 thermal part | F#57046 ("The thermal part"); L1:thermal_path.md; L1:our_model_mapping.md; L3:ARCHITECTURE §5 |
| G4 real time | task rule 4; L3:ARCHITECTURE §6.4 |
| G5 provenance, labels, unknowns | task rules 1, 3; A#57059 ("Global badges cannot replace per-value provenance") |
| G6 no WebGL, keyboard, touch, 320/390/1280, 200% | A#57059 (UX proposal); L3:ACCEPTANCE A-09, A-11, A-16; task (390, 1280) |
| G7 agent twin | task rule 9; A#57053 ("the accessible agent-readable twin must preserve the same qualifications") |
| G8 trust posture | L3:ARCHITECTURE §1-§2; main:web/src/csp.js:7; main:web/src/worker.js:51-56 |
| NG1 | L1:REPORT.md status block; L1:parts.json `status` |
| NG2 | main:web/public/temperature-label.mjs:26-28; A#57059 ("No mesh rendering success creates scientific acceptance") |
| NG3, D13 | L1:thermal_path.md §4 item 1 ("No public power map is captured in this pack") |
| NG4 | L3:ARCHITECTURE §6 ("Today's solver is steady state"), §6.4 |
| NG5, D7 | task rule 4; L3:ARCHITECTURE §6.3 |
| NG6 | main:web/src/worker.js:51-56; A#57059 ("viewing must not start a solver") |
| NG7 | L3:ARCHITECTURE §2.1, §7 |
| NG8 | task rule 7; main:docs/sentilab/CHIPLET-VISUAL-SCOPE-DISPOSITION.md:7 |
| NG9 | task rule 5 |
| NG10 | A#57053 ("No existing numerical or GB10 job is restarted by this research") |
| §2 rows | the citations in each row (all verified at main or pr66 while writing); the producer's signed `record.input_hashes`, `semantics.task_contract` and the unsigned argv: main:sentilab_core/conductor.py:337-347, :140-142, main:sentilab_core/envelope.py:233, main:sundai_hotspot/tap_oracle_worker.py:346-348, :372-375, main:sundai_hotspot/tap_oracle.py:874-895 (code reading for R6; no live envelope inspected) |
| §2 signed flight records with a chip-layer grid | main:web/public/replay/ascend910-seed11-32x32.json (`oracle_result` events with `signature` and `thermal.heatmap_c` 32 x 32, `solver_version` HotSpot-7:f18831e…); main:web/public/app.js:52, :63, :119-123, :139 |

### Content kinds (SPEC §3)

| Req | Source |
|---|---|
| Three columns and their data | task rule 2; A#57053; A#57059 ("typical anatomy and the two actual computational references need separate modes") |
| Banners (exact text) | this spec; wording from L1:REPORT.md status ("representative reconstruction … not any manufacturer's CAD and not silicon-validated"), L3:RISKS R-01/R-02 ("not manufacturer CAD", "Not silicon"), main:docs/sentilab/references/README.md:9-10 |
| X1 one kind per model | task rule 2; this spec |
| X2 `stands_for` only | L1:our_model_mapping.md §2 (the mapping), moved out of the anatomy (rule 2) |
| X3 fixture via `run.family` | main:sentilab_core/conductor.py:116; L3:ARCHITECTURE §5.3 ("not in the thermal model"); `family_match` separate from `run_inputs_verified`: A#57218 item 6 (R6, section 5) |
| X4 no cross-filling | task rule 2; A#57053; contrast L3:PSEUDOCODE §1 step 3 (D6); never the family's current manifest without verified inputs: A#57218 item 6 |
| X5 model values out of anatomy | L1:parts.json `in_our_model` and `heat_sink` entries; task rule 2 |
| X6 raw vs 0.5 mm identities | A#57059 ("Raw geometry and 0.5 mm snapped variants keep distinct identities and results"); main:docs/sentilab/references/README.md:18-24, :53-70 |

### Screens (SPEC §4)

| Req | Source |
|---|---|
| 4.0 notice slot markup | main:web/test/temperature-label.test.mjs:331-333; main:web/public/sentilab/package/index.html:48 |
| 4.0 keys | L3:ARCHITECTURE §9; main:web/public/sentilab/package/package.js:626-636 |
| 4.1 explode tween, reduced motion, on demand | L3:ARCHITECTURE §4.1; main:web/public/sentilab/package/render.mjs:19; package.js:17, :243 |
| 4.1 labels limits, DOM only | L3:ARCHITECTURE §4.4 |
| 4.1 assembled-only twin | A#57059 ("all lengths/field queries use assembled coordinates") |
| 4.2 panel contents | L1:parts.json fields; L3:ARCHITECTURE §4.3; main:web/public/sentilab/lab-model.mjs:124 (`metricFor`) |
| 4.3 heat, power, signal overlays | L1:parts.json `flows`; L1:REPORT §5; L1:thermal_path.md §3 (coupling paths, thm-026 vs thm-048); main:sundai_tap/util/hotspot.config:48; main:sundai_tap/passive_interposer.py:182-195; main:sundai_tap/configs/sys_ascend910_45mm.cfg:23-28; main:sentilab_core/conductor.py:345; main:docs/sentilab/references/README.md:105-108 |
| 4.3 no arrows in Results; qualifiers | A#57059 ("a heat arrow is not solved flux/Watts"; "A drawn wire is not routed wirelength or bandwidth") |
| 4.4 thermal path (anatomy) | L1:thermal_path.md §1-§3 |
| 4.4 thermal path (model) | L1:our_model_mapping.md §2 table, derived h_eff |
| 4.5 every row | the table's own citations; A#57059 (separate job status, replay position, physical time; "Frames/keepalives/backlog do not count as solves") |
| 4.5 definition of real time | L3:ARCHITECTURE §6.4 (quoted in substance) |
| 4.6 phone layout | L3:ARCHITECTURE §4.6; main:web/public/sentilab/package/package.js:59; A#57059 (320 px, 200% zoom) |
| 4.7 fallback, context loss | L3:ARCHITECTURE §9; A#57059 ("accessible part tree/details/results remain usable without WebGL") |
| 4.7 no WebCrypto | main:web/public/sentilab/package/package.js:644-648; D14 (this spec) |
| 4.8 twin files | task rule 9; L3:ARCHITECTURE §8; pr66 conventions (`omitted`, md + JSON); main:scripts/sentilab-scene.mjs:1-17 |
| 4.8 MCP later, same CLI | main:scripts/sentilab-scene.mjs:6-7; A#57059 ("CLI/MCP must share validation/artifacts") |
| 4.9 SKETCH | L3:ARCHITECTURE §6.3; L3:RISKS R-10; main:web/public/temperature-label.mjs:24-25, :48-51 |

### Data model (SPEC §5)

| Req | Source |
|---|---|
| 5.0 frame | main:docs/sentilab/references/README.md:53-59 ("origin at the interposer's lower-left corner, +x right, +y up"); main:sentilab_core/conductor.py:343 (`lower-left-mm`); z-axis: this spec |
| 5.0 units once; GLB metres +Y | A#57059 ("A 45 mm golden edge must become 0.045 m exactly once"); L3:evidence/extra-03 (glTF 2.0 section 3.4) |
| 5.0 ids authored, glTF names not relied on | task rule 3; A#57059 ("glTF names are not unique") |
| 5.0 basis tags | L3:PSEUDOCODE §1 `PROVENANCE`; L1:parts.json `conventions.thickness_um` (render_hint) |
| 5.0 hashes of bytes; Python-canonical identities | main:web/public/verify-core.js:5-6, :14, :103; main:docs/sentilab/references/README.md:53-59; main:web/public/sentilab/canonical.mjs:4-10 |
| 5.0 geometry preimage `sentilab-geometry/1` (sorted by stable id; no view state) | A#57218 item 3 (R3, section 5); main:web/public/sentilab/canonical.mjs:4-10 (keys sorted, arrays in order) |
| 5.1 quantity schema | task rule 3; L1:parts.json conventions; this spec |
| 5.0, 5.1 a sourced range keeps `value: null`; its drawn number is a `display` render hint with its derivation | A#57218 item 5 (R5, section 5); L1:parts.json `tim1`, `tim2`, `c4_underfill` (ranges, no typical), `bga_balls`, `substrate_core` (ranges with a lane-1 render hint) |
| 5.1 all-or-nothing readers | main:web/public/sentilab/package/scene.mjs:105-132 |
| 5.1 `label` object equals `LABELS[state]` | main:web/public/temperature-label.mjs:38-53 |
| 5.2 anatomy schema | L1:parts.json (shape kept where sound, section 5.9); task ("reuse lane 1's parts.json shape where sound") |
| 5.2 names policy fields | task rule 8; D1 |
| 5.2 flow qualifier | A#57059 |
| 5.3 assembly schema, instances, edges | task rule 3; A#57053 ("stable part-instance IDs and units/transforms") |
| 5.3 first assembly | L1:REPORT §1 (one or two compute dies, four to eight HBM stacks); L1:parts.json counts (12-high); D11 |
| 5.3 residual gaps, no stretching | task rule 3; this spec |
| 5.3 drawn/undrawn union; undrawn parts out of bounds, picking and field association | A#57218 item 1 (R1, section 5) |
| 5.4 model stack table | main:sundai_tap/passive_interposer.py:22-48, :50-149, :151-165, :182-195; main:sundai_tap/util/hotspot.config:11, :15-35, :48, :78, :82; main:sundai_hotspot/temperature_grid.h:46-48; main:sundai_hotspot/temperature_grid.c:523-552; L1:our_model_mapping.md §2; region properties from the generated floorplans before LCF defaults: C#57177 C6, confirmed by A#57278; main:sundai_hotspot/temperature_grid.c:387-400; main:sundai_tap/util/fill_space.py:18-20, :157-165; source identity (draft pin vs PR #56 successor): A#57278, A#57288 |
| 5.4 solver arguments | main:sundai_hotspot/tap_oracle_worker.py:356-369 |
| 5.4 role map | L1:FACTS thm-007 (TAP Table II); main:docs/sentilab/references/README.md:5-7, :86; main:sundai_tap/configs/sys_ascend910_45mm.cfg:19-28; sys_micro150_45mm.cfg:19-30; main:sundai_hotspot/tap_oracle.py:311; `expected_inputs` (what `run_inputs_verified` compares): A#57218 item 6; main:sundai_hotspot/tap_oracle_worker.py:356-369 |
| 5.4 simplifications S1-S9 | L1:our_model_mapping.md §4 |
| 5.4 index basis for layers 6-7 | L3:ARCHITECTURE §12 (open question to the producer); main:sundai_hotspot/temperature_grid.h:46-48; temperature_grid.c:529-530, :539-541, :550-552; qualified for detailed 3D (the package block-to-grid map replaced and its overrides cleared): temperature_grid.c:554-557, :999-1009; C#57177 C7, confirmed by A#57278 |
| 5.5 layouts | main:docs/sentilab/references/README.md:14-24, :46-70, :133-160; pr66:web/public/agents/references/ascend910-tap25d-fig6a.json:272-290 (omissions) |
| 5.5 turned footprints | main:sundai_tap/configs/sys_ascend910_45mm.cfg:19-20; the raw section's `rotated` and `footprints_mm` |
| 5.6 result schema and statistics | A#57059 ("Keep native center indices/weights, chip-layer peak/argmax, literal TAP selector, J, wire proxy and routed wire distinct"; "Results require exact geometry/material/power/layer/config/argv/executable identity"); main:docs/sentilab/references/README.md:105-119; main:sentilab_core/conductor.py:342-346; main:sundai_hotspot/tap_oracle_worker.py:368, :417-431; main:web/public/sentilab/package/scene.mjs:148-162; the `model` block's `family_match`, `run_inputs_verified` and their evidence, and the code-reading receipt states: A#57218 item 6; the warm max mapping and the gate-validation centre mapping kept apart: A#57278; main:sundai_hotspot/tap_oracle_worker.py:356-369; pr56:sundai_hotspot/slab049.py:981-987; main:sundai_hotspot/temperature_grid.c:1952-1967 |
| 5.6 geometry identity = envelope receipt | main:contracts/view-envelope-v0.5/VIEW-ENVELOPE.md:31 |
| 5.7 field artifact and pointer | L3:ARCHITECTURE §5.2; additions (+) from A#57059 and L3:ARCHITECTURE §5.2 item 1 ("whose hashes are already among the signed artifact_hashes"); validity is not association (`unassociated`): A#57218 item 6; the seven ordered gates (candidate and problem, units, layer ids, structure, grid, domain): C#57177 C1-C4; producer formats kept apart (native HotSpot 6 layer 0 vs the powered layer 4): A#57278, pr56:sundai_hotspot6/temperature_grid.c:1037-1082, :1140-1148 |
| 5.7 caps | main:sundai_hotspot/tap_oracle_worker.py:283-287; main:web/public/sentilab/package/scene.mjs:92-98; L3:PSEUDOCODE §6 |
| 5.8 twin schema | task rule 9; L3:ARCHITECTURE §8; L3:PSEUDOCODE §10; A#57059 ("GLB is a separately hashed render derivative") |
| 5.9 change table | L1:parts.json (each row read field by field); L3:PSEUDOCODE §1 (assumed schema); L1:SOURCES.md row 58 and the lane-1 sealed manifest (TAP PDF sha256 `b209f51a…`), main:docs/sentilab/references/README.md:79-80 |

### Rendering (SPEC §6)

| Req | Source |
|---|---|
| 6.1 own WebGL2, three.js alternative | L3:ARCHITECTURE §0, §2.2-§2.3; L3:PSEUDOCODE Appendix A; D5 |
| 6.1 CSP consequences | main:web/src/csp.js:7; L3:ARCHITECTURE §2.1; L3:evidence/web-06 (d) (per-property CSSOM: unverified) |
| 6.1 existing helper uses cssText | main:web/public/sentilab/package/package.js:29 |
| 6.2 one model per kind, three outputs | L3:ARCHITECTURE §3; task rule 2 (one kind per model: this spec) |
| 6.2 same data adapter | main:web/public/sentilab/package/source.mjs:1-12; playhead.mjs:1-13 |
| 6.3 frames and picking | task rule 3; A#57059; L3:ARCHITECTURE §4.2-§4.3; L3:PSEUDOCODE §1-§2 (`DRAW`) |
| 6.4 fields on 3D | L3:ARCHITECTURE §5.3-§5.5; main:web/public/sentilab/package/scene.mjs:230-233, :269-275; playhead.mjs:28-38; main:docs/sentilab/draft-0.5/REQUIREMENTS.md:179, :264 |
| 6.5 labels and DOM | L3:ARCHITECTURE §4.4, §9; main:web/public/sentilab/package/package.js:428-430 |
| 6.5 the qualified figure is the export boundary (and §3, §4.0) | A#57218 item 4 (R4, section 5) |
| 6.6 live transport | L3:ARCHITECTURE §6.2; main:web/public/sentilab/package/source.mjs:205-258, :256; main:web/src/worker.js:7, :26 |
| 6.7 disposal, stale fetches, budgets | A#57059 ("Explicitly dispose resources and test context loss/stale fetches"); L3:ARCHITECTURE §4.5, §10 |
| 6.8 deltas | each row's "Why" column |
| 6.9 /agents/ with or without PR #66 | pr66:web/src/agent-paths.js:4-8; pr66:web/public/agents/index.json:2; D9 |
| 6.10 renderer options (D5) | L3:ARCHITECTURE §2.2-§2.3; L3:evidence/extra-02; A#57218 (both scopes treated explicitly), A#57278 (root's vote, license inventory, warden resolves) |
| 6.11 measurement plan (D4, D5) | A#57218 (name workload, device and browser; preparation apart from end-to-present), A#57278 (targets, not limits) |

### Rules PL-1 to PL-24 (SPEC §7)

Each row of SPEC §7 carries its own source column; summary: PL-1 (L3 A-13, A#57059), PL-2 (task rule 1;
main:web/public/temperature-label.mjs:38-85; L3:PSEUDOCODE §5; serialized labels and their resolution: A#57218 item
2), PL-3 (A#57059; temperature-label.mjs:137-144; per-value-provenance.test.mjs), PL-4 (task rule 1; D2), PL-5
(L3:ARCHITECTURE §5.5; the figure as export boundary: A#57218 item 4) and PL-6 (L3:ARCHITECTURE §5.5), PL-7
(temperature-label.mjs:17-19, :145-153), PL-8 (package.js:297-300; temperature-label.mjs:163-170;
temperature-label.test.mjs:331-333), PL-9 (A#57059; references README.md:105-119), PL-10 to PL-13 (task rule 3;
A#57053; A#57059; PL-10's undrawn parts: A#57218 item 1; PL-12's geometry preimage: item 3), PL-14 to PL-16 (A#57059;
conductor.py:345; our_model_mapping.md §2), PL-17 (task rule 8), PL-18 (task rule 7), PL-19 (task rule 4;
L3:ARCHITECTURE §6.4; VIEW-ENVELOPE v0.6.2 rule 5), PL-20 (A#57053 "Display animation must distinguish verified
replay, new live receipts and illustrative behavior"; L3:RISKS R-08), PL-21 (A#57059 "no success fallback or
fabricated heatmap"; sentilab-scene.mjs:17), PL-22 (task rule 9; L3:ACCEPTANCE A-15), PL-23 (L3:RISKS R-02;
temperature-label.mjs:52), PL-24 (L1:SOURCES.md "How the facts were checked").

### Prerequisites (SPEC §8)

| Req | Source |
|---|---|
| P1 producer | task rule 5; L3:ARCHITECTURE §11 item 1; main:sundai_hotspot/tap_oracle_worker.py:91-100, :417-431; the `producer` block, candidate and problem hashes, and `null` for unbound values: C#57177 C1-C4 |
| P2 pointer | task rule 5; L3:ARCHITECTURE §5.2 item 2, §11 items 1 and 3; main:sentilab_core/conductor.py:344-346; VIEW-ENVELOPE v0.5:23-25 |
| P3 API route | task rule 5; L3:ARCHITECTURE §5.2 item 3, §11 item 2; main:app/view.py:90, :97, :186; main:web/src/worker.js:34-35 |
| P4 `hasTemperature()` | task rule 5; L3:ARCHITECTURE §5.5, §11 item 4; main:web/public/temperature-label.mjs:163 |
| P5 receipt completeness | A#57059; main:sentilab_core/conductor.py:346; main:sundai_hotspot/tap_oracle_worker.py:346-348, :356-369; the signed body's named map and the unsigned argv: main:sentilab_core/conductor.py:337-341, main:sundai_hotspot/tap_oracle_worker.py:372-375 (R6) |
| P6 replay artifacts | L3:ARCHITECTURE §6.1, §11 item 2; main:web/public/sentilab/package/package.js:652-654 |
| P7 grid layers 6-7 | L3:ARCHITECTURE §12 (producer questions); SPEC §5.4 reading |
| P8 acceptance | main:web/public/temperature-label.mjs:26-28; main:docs/sentilab/references/README.md:46 (SLAB-049) |
| P9 non-result temperatures | D2 |
| P10 doorbell | L3:ARCHITECTURE §6.2 |
| P11 PR #66 | pr66 (open) |

### Plan (SPEC §9)

| Req | Source |
|---|---|
| Phase 0 freeze | A#57059 ("Freeze schemas, operation names, no-result behavior and test mapping before the proposed Astra ultra author box"; "Forge owns joint spec/content; root independent evidence review; Warden concrete box/grant/ops"); F#57046 ("mint an Astra ultra box") |
| W0.2 41 cases | A#57059 ("30 web cases … and 11 anatomy cases: 41 source cases … ZERO executed") |
| W0.4 box | A#57053 ("Warden provisions the requested Astra ultra box"); main:scripts/export-deck-pdf.mjs:4; main:web/test/worker-boot.mjs:5-11, :22 |
| W1-W18 scopes | SPEC §5-§8; L3:PSEUDOCODE §0 (module list); L3:ARCHITECTURE §11 (site tests) |
| UI PRs with screenshots | L3:ACCEPTANCE A-09 ("the house rule for UI PRs: real-browser 1280 + 390 checks") |
| No new human +1 loop | A#57059 ("No new overall human +1 loop is proposed") |

### CAD (SPEC §10)

| Req | Source |
|---|---|
| Recommendation | A#57059 (first paragraph); L3:ARCHITECTURE §7.1-§7.2 |
| Identity table | A#57059 claims matrix, row by row (identities, licenses, caveats and pinned URLs copied) |
| Lane 3 offline tools | L3:ARCHITECTURE §7.2; L3:evidence/cad-01 to cad-05-12, web-10, extra-04 |
| No GPL | main:web/public/licenses.html:31 |
| Benchmarks | A#57059 (benchmark correction paragraph); F#57046 (the pasted 98% claim) |
| Contract if CAD is used | A#57059 (proposed technical contract paragraph); L3:ARCHITECTURE §7.2 (parity rule) |

### Open decisions (SPEC §11)

| Req | Source |
|---|---|
| D1 | task rule 8; main:web/public/index.html:28; main:web/public/replay/ascend910-seed11-32x32.json (`benchmark`); pr66:web/public/agents/index.json:19; generic representative labels with usable citations: A#57218, A#57278 |
| D2 | task rule 1; main:web/public/temperature-label.mjs:38-53; L1:thermal_path.md §3; L1:parts.json (temperature-conditioned keys); pr66:web/public/agents/math.md:168, :221-225; typed roles: A#57218, A#57278 |
| D3 | task rule 5 vs L3:ARCHITECTURE §0 and §5.1 vs main:web/public/replay/ascend910-seed11-32x32.json and main:web/public/app.js:52, :63, :139 |
| D4 | L3:ACCEPTANCE A-10 vs A#57059 (UX proposal paragraph); root's initial tier as measured targets: A#57218, A#57278 |
| D5 | L3:ARCHITECTURE §2.2-§2.3; root's vote for the vendored adapter, warden resolves in this draft: A#57218, A#57278 |
| D6 | L3:PSEUDOCODE §1 step 3 vs A#57053 and task rule 2; A#57218 item 6 (never a newer family manifest) |
| D7 | L3:ARCHITECTURE §6.3; task rule 4 |
| D8 | main:docs/sentilab/references/README.md:24; A#57059; main:sentilab_core/conductor.py:55; main:sundai_hotspot/tap_oracle.py:25; A#57218 item 6 (Results uses the run's signed geometry) |
| D9 | L3:ARCHITECTURE §8 vs pr66:web/public/agents/index.json:2 |
| D10 | task rule 8; main:web/test/public-names.test.mjs:20-26 |
| D11 | L1:REPORT §1; L1:parts.json `reference_layouts.generic_hbm3e_two_die` |
| D12 | A#57059; main:sentilab_core/conductor.py:346 |
| D13 | F#57046 ("every intricacies"); L1:thermal_path.md §4; the sourced conceptual inset: A#57218, A#57278 |
| D14 | main:web/public/sentilab/package/package.js:644-648; this spec |
| D15 | L3:evidence/cad-05-12-other-converters.md (cad-06, release 1.1.4 from the releases API) vs A#57059 (FreeCAD row) |
| D16 | A#57059 (41 cases; report seal) |
| D17 | A#57059 ("A steady-map fade is presentation"); this spec |
| D18 | L3:ARCHITECTURE §0; F#57046 ("simulation room") |
| Status of D1-D18; the product gate | A#57218 (root's resolutions); A#57278 (root-proposed, forge-adopted, warden co-sign pending, with no separate human confirmation; D5 root's vote and warden's resolution; D4's numbers as targets; Carter approves the rendered page before any deploy); section 5.4 |

### Acceptance (ACCEPTANCE.md)

| AC | Source |
|---|---|
| AC-01, AC-02 | L3:ACCEPTANCE A-01; main:web/public/temperature-label.mjs:38-53; main:web/test/temperature-label.test.mjs:320-341 |
| AC-03 | task rule 1; PL-4; PSEUDOCODE §8 (pattern checked in Node 22) |
| AC-04 | L3:ACCEPTANCE A-01 (browser part); main:web/test/temperature-label.test.mjs:28, :41; main:web/test/per-value-provenance.test.mjs:20-21, :59-120; temperature-label.mjs:57 |
| AC-05 | L3:ACCEPTANCE A-02; A#57218 item 4 (the figure as export boundary; pixel probes for patterns only) |
| AC-06 | task rule 9; L3:ACCEPTANCE A-15; main:scripts/sentilab-scene.mjs:17; A#57218 item 2 (serialized labels, full JSON path, altered identity, state and text) |
| AC-07 | main:web/test/per-value-provenance.test.mjs:73-91; temperature-label.mjs:139-144 |
| AC-08, AC-09 | task rule 2; A#57053 |
| AC-10, AC-11 | task rule 3; L1:REPORT §3.3 (lid thickness not sourced); L1:parts.json `die_side_caps` (no source); A#57218 item 1 (undrawn parts, AC-11) and item 5 (`display` refusals, AC-10; TIM1's range, AC-11; L1:parts.json `tim1.thickness_um`) |
| AC-12 | task rule 3; A#57059; L3:ACCEPTANCE A-13 |
| AC-13 | A#57059 (0.045 m once) |
| AC-14 | task rule 3; A#57059 (glTF names); A#57218 item 3 (order-free hash, golden preimage) |
| AC-15 | L3:ACCEPTANCE A-11 (parity) |
| AC-16 | main:sundai_tap/passive_interposer.py:37-48, :135-165; main:sundai_tap/util/hotspot.config:48; main:sundai_hotspot/tap_oracle.py:39; fresh directories, every region and config value, the stale-config test (C#57177 C5); region precedence (C6); confirmed by A#57278 |
| AC-17 | main:web/public/verify-core.js:5-6, :14, :103; main:docs/sentilab/references/README.md:61-68 |
| AC-18, AC-19 | A#57059; main:sentilab_core/conductor.py:342-346; main:docs/sentilab/references/README.md:18-24, :105-119; A#57218 item 6 (AC-19's separate predicates; AC-18's receipt states by code reading: main:sentilab_core/conductor.py:337-347) |
| AC-20 to AC-22 | L3:ACCEPTANCE A-03, A-04, A-07; L3:ARCHITECTURE §5.2 item 1 (input-source binding); AC-21's C1-C4 rows and AC-22's central-grid and mapping clauses: C#57177 C1-C4, C7; A#57278 |
| AC-23 to AC-25 | L3:ACCEPTANCE A-05, A-06; VIEW-ENVELOPE v0.6.2 rule 5 |
| AC-26 | task rule 4; A#57059 |
| AC-27 | L3:ACCEPTANCE A-08; main:web/test/worker-csp.test.mjs:20, :47-49; task ("CSP unchanged") |
| AC-28 | L3:ARCHITECTURE §11 item 5; main:web/test/worker-csp.test.mjs:38-43, :57; main:web/test/worker-boot.mjs:62; main:web/test/control-bytes.test.mjs:13 |
| AC-29, AC-30 | task rules 7-8; main:web/test/public-names.test.mjs:20-26, :49; pr66:web/test/public-names.test.mjs:49; AC-29 (c) copy-vs-source scope and (d) license inventory: D1, D10 (A#57218, A#57278) |
| AC-31 | A#57059; main:web/src/worker.js:51-56 |
| AC-32 | L3:ACCEPTANCE A-09; A#57059 (320 px, 200% zoom); main:scripts/export-deck-pdf.mjs:70-80 |
| AC-33 | L3:ACCEPTANCE A-16; A#57059 ("keyboard/touch select the same IDs") |
| AC-34 | L3:ACCEPTANCE A-10 and A#57059 (both columns); D4; targets, the named workload, device and browser, preparation apart from end-to-present: A#57218, A#57278 |
| AC-35 | L3:ACCEPTANCE A-11; main:web/public/sentilab/package/package.js:644-648 |
| AC-36, AC-37 | task rule 9; L3:ACCEPTANCE A-15; pr66 (`.md` scanning) |
| AC-38 | task rule 6; A#57059 |
| AC-39 | L3:ACCEPTANCE A-17 |
| AC-40 | L1:SOURCES.md (176 of 176 verified); L1:SOURCES.md row 58; main:docs/sentilab/references/README.md:79-80 |
| AC-41 | A#57218 item 6 (family match is not input verification; validity is not association); the §5/W4 review input under #57177 (bind the resolved config; field existence and eligibility are separate); case (h): C#57177 C1-C4 |

## 5. Review findings after v0.1 (`da9b1ee`) and their repairs

"Was" cites the exact draft root reviewed (`da9b1ee`, byte-identical to the review packet's copy: section 1). "Now"
cites this version. Each commit that moves a cited line refreshes this section, so its lines hold at the branch head.

### 5.1 Root's six specification repairs (A#57218)

| Finding | Was (`da9b1ee`) | Change | Now | ACs |
|---|---|---|---|---|
| R1 (item 1): a positive box was required even for `drawn: false`, although unknown dimensions must stay unknown | SPEC:561 (`box` required on every instance), :608-614; PSEUDOCODE:164 (box checked on every instance) | `instance` is a `oneOf` union: `drawnInstance` (box and basis required) or `undrawnInstance` (`dims` required; box, basis and array forbidden). The reader refuses a box on an undrawn part and an undrawn part whose every dimension is drawable. Undrawn parts keep id, parent, edges and null dims, and are left out of boxes, bounds, picking, sections and field association; flows add no point for them | SPEC:635, :669-685 (schema), :700-715 (reader rules), :220-222 (flows), :1347-1349 (picking), :1467 (PL-10); PSEUDOCODE:190-212 (`readAssembly`), :378-385 (RenderModel), :481-485 (`pick`); ACCEPTANCE:125-140 | AC-11 (rewritten), AC-36 |
| R2 (item 2): result values carried label copies while `formatTemp` and AC-06 accepted only canonical object identity, which no JSON round trip preserves | PSEUDOCODE:249, :263-264 (copies), :427-431 (identity check); ACCEPTANCE:65-70 (AC-06); SPEC:366-367 (`label_mismatch`), :1171 (PL-2) | Labels travel as serialized records `{state, text, short, title}` (`serializeLabel`, steps S1-S3). `resolveLabel()` recomputes `labelFor()` from the verified evaluator identity (page, CLI) or the recorded one (twin reader), requires exactly the four keys with equal strings, and returns the canonical `LABELS` object, the only input `formatTemp` takes (steps R1-R5); a value whose identity disagrees with its verified provenance is refused. `readTwin()` added; markdown is made from a read twin | SPEC:438-440 (`label_mismatch`), :1111-1112 (5.6 rule), :1459 (PL-2); PSEUDOCODE:313 (`resultView`), :523-557 (algorithm S1-S3, R1-R5), :735-741 (`readTwin`, `twinMarkdown`), :813-815 (page); ACCEPTANCE:74-89 | AC-06 (rewritten: result → JSON → reader → markdown, altered identity, state and text), AC-01 |
| R3 (item 3): AC-14 promised an order-independent `geometry_sha256`, but the reader hashed the unsorted instance array | PSEUDOCODE:172 (`canonical({ frame, instances })`); SPEC:282-284 (5.0), :613-614 (5.3); ACCEPTANCE:124-128 (AC-14) | A frozen, versioned preimage `sentilab-geometry/1`: `canonical()` of `{ v, frame, instances }` with one record per instance, `{ id, type, parent, variants (sorted), drawn, box (null if undrawn), array (geometry only) }`, sorted ascending by id; labels, bases, dims, edges and all view state are outside it; computed in JavaScript only. `geometryPreimage()` (ids.mjs) serves `readAssembly` and every RenderModel's `geometry_key`. AC-14 pins a golden fixture: 735 bytes, sha256 `0480119fc57ab1c48d8010c11c695ae593bf9b3775c6234a2b3cb1cd23fffbe9`, produced with main's `canonical()` and re-hashed in Python; reversed order, reversed variants and label, basis or dims edits keep the hash; a 0.001 mm box move, a re-parent, a drawn-to-undrawn change, a removed instance, a type or a variant membership change alter it (all ten checked) | SPEC:338-351 (5.0 preimage), :714-715 (5.3), :1469 (PL-12); PSEUDOCODE:143-155 (`geometryPreimage`), :213 (`readAssembly`), :386-387 (`geometry_key`); ACCEPTANCE:161-188 (AC-14), :146 (AC-12) | AC-14 (rewritten, golden vector), AC-12 |
| R4 (item 4): PL-5 and AC-05 treated a canvas crop as if it contained DOM chips | SPEC:1174 (PL-5), :88 (§3 "Chip inside the canvas"), :122-124 (§4.0 stage); ACCEPTANCE:58-63 (AC-05); PSEUDOCODE:17 (shell) | The qualified figure (`figure#p3d-figure`: canvas or SVG fallback, DOM chips, legend, source line with mode, run and `as of seq S`) is the export boundary: any image of the view is of the whole figure, and no canvas-only export (`toDataURL`, `toBlob`) exists. Pixel probes test only hatch and stipple; a separate figure check tests that the words are present, inside the figure, unclipped and uncovered | SPEC:122 (§3 chip), :161-165 (§4.0 stage), :1371-1379 (§6.5 figure), :1462 (PL-5); PSEUDOCODE:17-18 (shell), :818-820 (controller), :826 (test hook); ACCEPTANCE:61-72 (AC-05) | AC-05 (rewritten: (a) pixels, (b) figure) |
| R5 (item 5): `drawnMm` drew a sourced range at its midpoint and called the result `sourced` | PSEUDOCODE:98-105 (`drawnMm`, the midpoint at :103-104); SPEC:608-610 (5.3 "inside its range"), :1035 (5.9 thickness row), :274-277 (5.0 basis tags) | The quantity keeps its sourced range with `value: null`. The number drawn for it is a separate `display: { basis: "render_hint", value, derivation }` (5.1 schema: allowed only on a `sourced` quantity with `value: null`, inside `[min, max]`), authored in the reviewed source; lane 1's own render hints map into it. `drawnMm()` returns the value with its own basis, or the display with basis `render_hint` and its derivation, or `null`; it never invents a midpoint. The assembly reader requires the drawn basis to equal `drawnMm()`'s; the data build refuses a served `value` that differs from lane 1's `typical`. Panel: `min–max · sourced [facts] · drawn at X (display only: derivation)` | SPEC:325-329 (5.0 basis tags), :404-410 (5.1 `display`), :436 (`range_order`), :701-704 (5.3), :200 (4.2 panel), :1273 (5.9), :1467 (PL-10); PSEUDOCODE:108-119 (`drawnMm`), :98-102 (`readQuantity`), :206 (`readAssembly`), :763-765 (data build); ACCEPTANCE:120-121 (AC-10), :128-143 (AC-11) | AC-10 (display refusals), AC-11 (TIM1 range case) |
| R6 (item 6): `model.status` became `bound` from `run.family` alone, yet a shared family does not bind an old run to the current configuration | PSEUDOCODE:259 (`status: fixture ? "bound"`), :198-199 (`fixtureFor`), :321-326 (`resultBoxes`); SPEC:880-883 (`model` block), :96-98 (X3), :99-101 (X4), :951-954 (today's receipts); ACCEPTANCE:79-85 (AC-08), :153-160 (AC-18), :162-167 (AC-19) | `family_match` (reference context: role names, reference layouts, the manifest's stack as a labelled reference) is separate from `run_inputs_verified`, true only when the signed measurement names its inputs, the named `samplelayers.lcf` and resolved `new_hotspot.config` equal the fixture's new `expected_inputs` (recorded by W4), and the model-selecting flags are signed and equal. Only that permits the exact stack (`stack_basis`) or a field registration (`associateField`; otherwise status `unassociated`). Signed geometry and values stay shown with honest completeness states. Code-reading correction: v0.1 missed the signed body's named `record.input_hashes` (conductor.py:337-341); every current run still reads unverified because the flags are unsigned, and a run's producer and config receipt is confirmed, not assumed (P5). Field names coordinated with the §5/W4 review input under #57177 (bind the resolved config; field existence and eligibility are separate) | SPEC:130-140 (X3, X4), :103 (§2), :119 (§3), :202 (4.2), :848-854 (5.4 schema), :910-914 (5.4 text), :1016-1031 (5.6 `model`), :1113-1137 (5.6 text), :1076-1082 (`fieldStatus`), :1204-1210 (5.7), :1402 (6.8), :1491 (P5), :1626 (D6), :1628 (D8); PSEUDOCODE:239-255 (`fixtureFor`, `inputsVerification`), :289-292 (`signedInputsOf`), :323-327 (`resultView`), :391-397 (`resultBoxes`), :665-671 (`associateField`), :855-857 (Python); ACCEPTANCE:435-452 (AC-41), :233-239 (AC-19), :101-106 (AC-08), :225-229 (AC-18) | AC-41 (new), AC-19, AC-08, AC-18 |

### 5.2 The ChatGPT field-association/W4 review (C#57177), attributed separately

Seven revisions in two replies on the exact `da9b1ee` draft: the field contract (`383df803…`, C1-C4) and the model
stack and its source (`96f0434f…`, C5-C7). Root's exact source map at sentilab `209dad7a` confirms C5-C7 against the
draft-pinned source (A#57278, A#57288). Every original AC id is kept; rows were added or tightened.

| Finding | Was (`da9b1ee`) | Change | Now | ACs |
|---|---|---|---|---|
| C1: the field check never compared the declared candidate and problem, so a signed artifact could omit or contradict them | SPEC:968 (`candidate_hash`, `problem_hash` declared); PSEUDOCODE:488-492 (run, measurement, evaluator and three sources only); ACCEPTANCE:186-187 (AC-21) | The ref carries expectations from the verified envelopes: the measurement's signed `record.binding.candidate_id` (the candidate's canonical layout hash, main:sundai_controller/controller.py:152-165, equal to its candidate node's) and `semantics.task_contract` (the producer's problem hash, main:sundai_hotspot/tap_oracle.py:874-895; main:sentilab_core/conductor.py:91, :335, :342-343). A contradiction is `binding_mismatch`; a missing value leaves the field unassociated (`candidate_unbound`, `problem_unbound`) | SPEC:1171-1179 (gate 3); PSEUDOCODE:599-602 (`fieldRefs`), :626-628 (`checkFieldArtifact`); ACCEPTANCE:260 (AC-21 row) | AC-21 (new row), AC-41 (h) |
| C2: the pointer's unit and the artifact's were never compared, so C over K converted silently | SPEC:978 (`unit` in the pointer); PSEUDOCODE:494-497 (only the artifact's unit read) | Both units read, normalised through the documented aliases only (`K`; `C`, `°C`), compared before any conversion: `unit_conflict`; an undocumented unit `unit_not_supported`; `null` unassociated (`unit_unbound`); both declarations kept; converted once | SPEC:1180-1183 (gate 4); PSEUDOCODE:632-635; ACCEPTANCE:262 (AC-21 row) | AC-21 (`unit_conflict`, unit rows), AC-41 (h) |
| C3: declared solver layer ids were ignored and the field relabelled layers by array position | SPEC:971 (`layers[].index`); PSEUDOCODE:494 (count only), :499-508 (`index: L`) | Integer, unique, ascending ids in 0..15 equal to `producer.emitted_layer_ids` and the pointer's count; values bound to their record; the source id kept; malformed or ambiguous identity refused (`layer_ids`, `malformed`), never an advisory difference; well-formed differing tables still listed; `null` ids unassociated. Producer formats kept apart (section 5.3, K2) | SPEC:1184-1190 (gate 5); PSEUDOCODE:636-643; ACCEPTANCE:263-264 (AC-21 rows) | AC-21 (`layer_ids`, layer records), AC-41 (h) |
| C4: no structural or spatial contract: zero rows with empty arrays passed, a misspelled `extent_m` went unseen, and a package-sized extent was forwarded | PSEUDOCODE:486-495, :512 (`extent_mm` passed through); SPEC §5.7 (an example, not a schema) | Explicit gates instead of a schema: closed key sets with `null` for unbound values; real arrays; positive integer rows and cols within the caps and equal to the pointer's; finite extents with positive spans equal to the verified central grid domain (`extent`), never a package outline; row order and map mode declared; spreader and sink outlines beyond the grid stay `unmeasured` | SPEC:1168-1170 (gate 2), :1191-1199 (gates 6, 7); PSEUDOCODE:621-623, :644-649; ACCEPTANCE:258, :266 (AC-21 rows) | AC-21 (`malformed`, `dims`, `extent`), AC-22, AC-41 (h) |
| C5: the W4 check shared one directory across fixtures, checked the last fixture's config with a placeholder, and covered too little | PSEUDOCODE:660-671 (shared `tmp_path`; `config_bytes` after the loop); ACCEPTANCE:136-141 (AC-16) | A fresh directory per fixture (the writer creates `new_hotspot.config` only when absent: main:sundai_tap/passive_interposer.py:151-165); every region of all six floorplans, power and lateral flags, package thickness, conductivity and capacity, `r_convec`; each fixture's config pin inside the loop; a separate reused-directory test that exposes the stale config. Confirmed by A#57278 (root's map: `conditional_config_writer`) | PSEUDOCODE:830-863 (§14); ACCEPTANCE:196-210 (AC-16) | AC-16 |
| C6: "layer 3 the same footprints in the bump mix" could include whitespace, and the L1/L2 slabs need their floorplan mixtures, not LCF defaults | PSEUDOCODE:328-331 (`modelBoxes`) | Every region resolves from the generated floorplan before the LCF default (detailed 3D: main:sundai_hotspot/temperature_grid.c:387-400); C4 and interposer mixtures (passive_interposer.py:59-74); whitespace as `fill_space` writes it (main:sundai_tap/util/fill_space.py:18-20, :157-165); `Ubump_*` silicon with zero power; never inferred from a name. Confirmed by A#57278 (`material_precedence`, `coordinates_and_regions`) | SPEC:878-887 (5.4); PSEUDOCODE:400-409 (`modelBoxes`); ACCEPTANCE:196-210 (AC-16) | AC-16 |
| C7: "both reuse the TIM layer's floorplan mapping" is too broad for detailed 3D | SPEC:766-769; TRACE:195 | Qualified: spreader and sink keep the TIM floorplan extent and grid-to-block mapping (main:sundai_hotspot/temperature_grid.c:539-541, :550-552); in detailed 3D their block-to-grid map is replaced and its per-cell overrides cleared (:554-557, :999-1009), so package properties come from the spreader and sink configuration; their grids cover the interposer core, not the package footprint, and the grid output has no peripheral-node values. Confirmed by A#57278 (`package_layers_and_extent`) | SPEC:889-897 (5.4); ACCEPTANCE:281-284 (AC-22) | AC-22 |

### 5.3 Distinctions kept, and the receipt still owed (A#57278)

| Kept distinct | Source | Where in this version | ACs |
|---|---|---|---|
| K1: the warm oracle's max mapping (J) and the gate-validation centre mapping | A#57278; root's map facts `warm_oracle_overrides`, `gate_validation_command`, `native_centre_not_peak`; main:sundai_hotspot/tap_oracle_worker.py:356-369; pr56:sundai_hotspot/slab049.py:981-987; main:sundai_hotspot/temperature_grid.c:1952-1967 | SPEC 5.6 "Two mappings, never mixed" | AC-22, AC-18 |
| K2: native HotSpot 6 without the all-layers writer emits layer 0, the substrate, not the powered layer 4 | A#57278; facts `native_hotspot6_headerless`, `native6_evaluator_all_layers`; pr56:sundai_hotspot6/temperature_grid.c:1037-1082, :1107-1148; pr56:sundai_hotspot6/temperature_grid.h:35-50 | SPEC 5.7 "Producer formats are not interchangeable" | AC-21 (`layer_ids`), AC-41 (h) |
| K3: the current runtime association still needs its actual producer and config receipt | A#57278; A#57288 ("Source facts do not establish a runtime producer association") | SPEC 5.6 (family match), 5.7 (producer formats), P5 | AC-41 |
| K4: the draft-pinned writer is main `d250462` (`cecc5b85…`, the TRACE pin); PR #56's successor `7f70baf` is a separate identity | A#57278; A#57288 (`draftWriterPinMatched: true`); both hashes checked here with `git show` | SPEC 0 (tags), 5.4 (table intro); TRACE section 1 | AC-16 |

### 5.4 Decision resolutions (A#57218, A#57278)

Every resolution is recorded as root-proposed, forge-adopted, warden co-sign pending, with no separate human
confirmation (A#57278), except D5 (root's vote recorded; warden resolves in this draft), D15 (informational) and D16
(the test mapping, W0.2: section 5.5).

| Decision | Root's proposal | Recorded as | Now | ACs |
|---|---|---|---|---|
| D1 (root): names | Generic teaching labels keep usable source titles, publishers, URLs and capture hashes (A#57218); "generic representative labels with usable source citations" (A#57278) | Generic representative names in the teaching copy; source records keep their citations; a title holding a temperature is replaced and listed in `omitted`; `"named"` unused; W18 not planned | SPEC:1621 (D1), :597-599 (5.2), :1474 (PL-17), :1561 (W18); ACCEPTANCE:327-333 (AC-29) | AC-29 (c) |
| D2 (root): non-result temperatures | Distinguish model-input, material-condition, published-limit and computed-result quantities; only computed results use the four result states (A#57218); "typed non-result temperature roles" (A#57278) | Typed roles in `omitted` now (schema `role`); rendering waits for the role formatter (P9); PL-4 reworded | SPEC:1622 (D2), :333 (5.0), :378 (`omission.role`), :1461 (PL-4), :1495 (P9); ACCEPTANCE:45 (AC-03) | AC-03 |
| D3 (root): legacy withdrawn grids | Retain the fact that they exist; enable a 3D field only through an exact supported verifier and association path | As proposed; the legacy grids have no such path, so they are not drawn | SPEC:1623 (D3) | AC-41 |
| D4 (root): phone tier | 50,000 triangles, 60 calls, 1 MP buffer, 2 MiB derivative; name the workload, device and browser; measure preparation apart from end-to-present (A#57218); the numbers are prospective measurement targets (A#57278) | Targets, not limits; the measurement plan; AC-34 rewritten around it | SPEC:1624 (D4), :1434-1452 (6.11); ACCEPTANCE:360-386 (AC-34) | AC-34 |
| D5 (root): renderer | A pinned, locally vendored three.js adapter behind RenderModel, preserving original primitives, DOM/2D alternatives and the CSP; settle it within the three-owner document with both scopes treated (A#57218); with a license inventory, warden resolves (A#57278) | Root's vote recorded; warden resolves in this draft; both options' scope and the measurement plan written out; W9.5 measures both; W10 builds the pick | SPEC:1625 (D5), :1301-1305 (6.1), :1416-1432 (6.10), :1542-1543 (W9.5, W10), :76 (G8) | AC-34, AC-29 (d) |
| D6, D8, D12 (root): results | Never fill a run's unknown thickness from anatomy or a newer family manifest; default Model to the reviewed 45 mm raw reference; Results uses its recorded geometry; incomplete receipts may support qualified diagnostic display | As proposed (R6 implements D6) | SPEC:1626 (D6), :1628 (D8), :1632 (D12) | AC-08, AC-41 |
| D7, D9-D11, D14, D17, D18 (root) | Defer SKETCH and CAD-kernel adoption; keep `/agents/package3d/` with explicitly owned future MCP conformance; scoped copy-vs-source and license checks; one generic teaching assembly; a useful static fallback; hard-cut verified fields; `/sentilab/package3d/` linked from the simulation room | As proposed; the MCP owner is forge until the three owners hand it on | SPEC:1627, :1629, :1630, :1631, :1634, :1637, :1638 (D rows), :296 (4.8 MCP owner), :1640-1641 (CAD kernel) | AC-29, AC-35, AC-26 |
| D13 (root): die inset | A sourced conceptual compute, SRAM and interconnect inset, schematic, with no claimed manufacturer floorplan | As proposed; its facts are new W2 content | SPEC:1633 (D13), :84 (NG3), :204-206 (4.2); ACCEPTANCE:110-111 (AC-09) | AC-09, AC-40 |
| Product gate (A#57278) | Carter approves the rendered page, from real-browser screenshots, before any deploy; the spec text is not the gate | One line in section 11; W0.3; the ACCEPTANCE gate paragraph | SPEC:1616 (section 11), :1511 (W0.3); ACCEPTANCE:18-19 (gate paragraph) | gate paragraph |
