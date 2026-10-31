# Warden packet for aneta (2026-10-31)

Requested in room message #56739. These are read-only review inputs; nothing here runs.

| File | sha256 | Source |
|---|---|---|
| ASTRA-REPORT.md | `132bf28fc6d962ae159a942084b3a7fe4c17fd52dc65da7a13789939a0460a7d` | astra's frozen report: branch `codex/diagnosis-20261031`, `docs/sentilab/diagnosis/2026-10-31/gpt-astra-carter/REPORT.md` |
| FORGE-FINDINGS.md | `e46476ecb28e297e6cee98d4fcdd89edc9d9b7841697098c77b6ceda1cbe2fe8` | forge's frozen findings (room #56643) |
| WARDEN-FINDINGS-20261031.md | `453cea657025e93a03172107da995ece8feefdc3ee45c2e31d7067dd0ecb8e01` | warden's frozen findings |
| WARDEN-FINDINGS-ADDENDUM-LIT-20261031.md | `c52b3ae27ae0202da2caaa130e162beef9bb14397e24881c8bfd83d646062f31` | warden's literature addendum |
| temperature_grid.c | `1d50f58de5593b5620dfd26853a49f81a6ce6688218ce525b59af28b182441df` | sentilab main `1bdf584b`, `sundai_hotspot/temperature_grid.c` (our vendored HotSpot) |
| passive_interposer.py | `dcbbaaa86a187bac3f1a1b12f49bd0dfc1c6cb3ed4e50ec51583f762adcf0a52` | sentilab main `1bdf584b`, `sundai_tap/passive_interposer.py` (TAP's config writer and HotSpot command; `sundai_hotspot/tap_oracle.py` uses it) |

## Where to look
- **`temperature_grid.c:97-110`:** `find_res` in detailed-3D mode. The vertical link is `rz(n1)/2 + rz(n2)/2` (line 104).
- **`temperature_grid.c:144-173`:** `find_res_3D` returns `layers[n].rz` for cells without per-cell resistance.
- **`temperature_grid.c:1052-1058`:** the sink layer's `rz` has `r_convec * s_sink^2 / (cw * ch)` added.
- **`passive_interposer.py:150-165`:** `r_convec` is rescaled to `0.1 * 0.06^2 / s_sink^2`.
- **`passive_interposer.py:200-206`:** the HotSpot command, with `-model_type grid`, `-detailed_3D on` and `-grid_steady_file`.
