# SentiLab package view: agent twin (stub)

[View the normal site](?view=human)

This is the machine-readable twin of the human 3D view at `/sentilab/package/`. It is a stub: it lists the model the
view draws, not the layouts or temperatures on screen.

- `index.json` (`sentilab-twin/1`, content `model`): the CPU-DRAM case's model stack (eight layers, true thickness and
  z in mm), its eight dies (`tap-chiplet-0` to `tap-chiplet-7`, named C0 to C3 and D0 to D3 by the agent door) and
  the placement rules (0.5 mm centre lattice, 0.1 mm body gap, 0.5 mm edge clearance including the halo; CPU 0 or 90
  degrees, DRAM 0 only), with the sha256 of every file it was built from.
- Coordinates are assembled, in mm: origin at the interposer's lower-left corner on its bottom face, z up toward the
  cooler. Explode, readable thickening and section are view transforms. Every coordinate here is assembled.
- No temperatures are in this twin. Scored layouts, their simulated maps and the board metric are in the human view
  only. Simulated, not silicon.
