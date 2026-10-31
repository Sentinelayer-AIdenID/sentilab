# Third-party notices

This repository carries unmodified upstream source from two research projects. Their licenses are kept
unchanged next to the code; read them before redistributing anything, including a container image (an image is
binary distribution).

| Component | Path | Upstream | Commit | License |
|---|---|---|---|---|
| HotSpot thermal simulator | `sundai_hotspot/` | https://github.com/uvahotspot/HotSpot | `f18831e48cef5d62580585cca0d7fab6c71bc3cc` | Custom University of Virginia license, `sundai_hotspot/LICENSE` |
| TAP-2.5D chiplet placement | `sundai_tap/` | https://github.com/bu-icsg/TAP-2.5D | `3a3f4e5a4d019b2d9cda1f72d8d1755238845dbb` | Apache-2.0, `sundai_tap/LICENSE` |

Obligations we follow:

- HotSpot: its copyright line and license paragraphs travel with every copy, source or binary. No University of
  Virginia or contributor name is used to endorse or promote this product.
- TAP-2.5D: the Apache-2.0 license travels with every copy. Any TAP file we modify carries a prominent change
  notice at its top. Upstream has no NOTICE file. Derived TAP files outside the unmodified upstream copy, each with
  its change notice:
  - `sundai_hotspot/tap_router.py`: ported from TAP-2.5D `routing.py` (`get_input`, `solve_Cplex`), Copyright the
    TAP-2.5D authors, Apache-2.0. The pin-clump model, constraints and objective are TAP's. The solver (HiGHS
    through scipy instead of IBM CPLEX), the solver settings, the return value and the failure handling changed.
  - `sundai_tap/configs/sys_ascend910_45mm.cfg` and `sys_micro150_45mm.cfg`: derived from the upstream configs, with
    a 45 mm interposer and a SentiLab legality section.
- SuperLU (if a build links it): its BSD-style LBNL notice is reproduced in any binary distribution.
- No GPL code (for example 3D-ICE) enters this repository.

The starter's own new code (`sundai_controller/`, `sundai_thermal/`, the probe driver) carries no license yet;
all rights reserved by its owner until one is chosen.

Citations requested by the upstream authors:

- Y. Ma et al., "TAP-2.5D: A Thermally-Aware Chiplet Placement Methodology for 2.5D Systems," DATE 2021.
- R. Zhang, M. Stan, K. Skadron, "HotSpot 6.0: Validation, Acceleration and Extension," UVA TR CS-2015-04.
