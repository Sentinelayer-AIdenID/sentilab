# Thermal producer source handoff

The draft-pinned source dependency is resolved: d25046256b4a712b529977f31e10b7e32248a9c0's writer exactly matches TRACE48 SHA256 cecc5b85f7dd8e6a3816c635879eb06193a270595f6bdbc71b76e4ef96f227df. Exact writer, template config, whitespace helper, native C/header and warm-wrapper files are in draft-d2504625/. The separately named PR56 successor7f70baf56998cdeea9fcaa56954fc78f8f6c8071 is in successor-7f70baf5/. Ten of12compared common paths are byte-identical. HotSpot7 C and Makefile differ; the steady-grid writer function itself is byte-identical at draft1261–1295 and successor1286–1320. No whole-commit or built-binary equivalence is claimed.

| Producer path | Effective mapping and output |
| --- | --- |
| Draft/current warm oracle | Requested grid dimensions (ordinary HotSpotOracle defaults32×32), CLI grid_map_mode=max, grid/detailed3D on. Headered layers0–7; worker returns layer4 heatmap. |
| PR56 gate-validation argv | Config64×64/center; grid32 overrides rows/cols only. Distinct from warm search-worker max mapping. |
| Native6 macro off | Headerless index/T_K, two decimals, one selected layer. With captured secondary0, that layer is0, not powered layer4. Other native secondary branches select3or5. |
| Native6 evaluator macro on | All Layer n: sections, two-decimal Kelvin; requires the named writer macro/build identity. |
| Native7 draft/successor | All Layer n: sections, two-decimal Kelvin. The top-layer source comment is stale. |

The six generated LCF layers are substrate200µm, C4/underfill70µm, interposer110µm, microbump/underfill10µm, chip150µm and TIM20µm. Only layer4 is power-enabled; only Chiplet units receive configured power. FLP material overrides matter: L4 Ubump-named regions are silicon, edge regions use bump mixture, and fill_space writes whitespace as underfill. Detailed3D resolves region properties before LCF fallbacks.

With this LCF and secondary0, native C appends spreader6 and sink7 without a second TIM. They retain the TIM floorplan extent and grid-to-block map; detailed3D replaces their block-to-grid map and clears material override flags. Their central grid is not the full sink/spreader footprint. Peripheral inode values occur in block-mapped steady output, not the grid dump. Native centre mapping (1,2or4distinct cells), active-layer peak and whole-dump selector remain different observables.

The config writer runs only when new_hotspot.config is absent. Both retained45mm reference configs contain sink0.18m, spreader0.09m and r_convec0.011111111111111112K/W. These are committed input bytes, not a new run. Fresh fixture directories are required to test generation; old saved configs cannot be inferred from the conditional source.

PRODUCER-MAP.json supplies 17 mapped facts and 57 exact line excerpts, each with its file digest and Git blob identity. Source bindings cover 49 retained files. CAD-SOURCE-REQUESTS.json retains ChatGPT's exact source-boundary requests. This supplies §5/W4 source facts; it changes no schema or acceptance decision. No source was executed, and no native build, solve, model, runtime loader or test ran. Current PR56 acceptance, actual executable/config/receipt binding and runtime field association remain unverified.
