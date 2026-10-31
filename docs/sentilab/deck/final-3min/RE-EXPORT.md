# Re-exporting the three-minute deck with the real gate result

The deck in this folder was exported with slide 4 at **NOT RUN**. The gate window closes 2026-11-01 12:00 UTC and the
slides are due at 18:00 UTC. Once the gate-zero result is reviewed, one command rebuilds the data, refreshes the pull
request states, moves the cutoff to now and exports the PDF plus a fresh render of every page.

## The command

Run it from the repository root, with Playwright available (`PLAYWRIGHT_DIR` is a folder holding
`node_modules/playwright`; on the workstation `C:/tmp/forge-skills-install` works).

**PASS**, with the two measured block-centre values, layout A (published 75.48 C) then layout B (published 115.94 C):

```
PLAYWRIGHT_DIR=C:/tmp/forge-skills-install node scripts/build-deck-final.mjs --gate pass --measured 75.61,116.02 --refresh-prs --export --shots C:/tmp/deck-final-shots
```

**FAIL**, the same with `--gate fail`. The values replace `[values]` in the reviewed wording ("It missed: 77.10 C and
116.02 C."):

```
PLAYWRIGHT_DIR=C:/tmp/forge-skills-install node scripts/build-deck-final.mjs --gate fail --measured 77.10,116.02 --refresh-prs --export --shots C:/tmp/deck-final-shots
```

**Still NOT RUN** at the deadline: drop `--gate` and `--measured`, and keep `--refresh-prs --export`.

The numbers above are placeholders. Use the values from the reviewed gate record, in C, with up to three decimals.

## What the command does, and what it refuses

- `--refresh-prs` re-reads every pull request on the backup slide with `gh pr view`, stamps the check time and makes
  that minute the deck's one cutoff. Without it, give `--cutoff <UTC time>` instead.
- `--gate pass` builds only if both values are within 1.0 K of their published references. `--gate fail` builds only if
  at least one is outside. NOT RUN takes no values.
- The gate code can also return **ERROR** or **INCOMPLETE**. Neither has reviewed wording, so neither builds. Do not
  export one of them as NOT RUN: "The test hasn't run" would be false. Write and review the wording first.
- A FAIL caused by something other than a missed value (a replay that differs, evidence that does not verify) also
  needs reviewed wording. "It missed" would not describe it.
- The five main slides must still fit 165 s of speech. The build reports the total; all three outcomes fit today.
- The export fails on any overflow, clipped text, main-slide text under 28 px, contrast under 4.5:1, or a missing value.

## After it runs

The export replaces the previous PDF in this folder, so it always holds one PDF with one cutoff (the test checks this).

1. Look at the new PDF and at slide 4 in the shots folder.
2. Run `node --test scripts/deck-data.test.mjs`.
3. Commit `FINAL.json`, `deck/final/deck-data.json`, `deck/final/deck-data.js`, the new PDF and the removal of the old
   one, and send the head for review.

To preview PASS or FAIL before a result exists, add `--preview` and leave out `--measured`. Every slide is then marked
"PREVIEW · not a result", the table shows `[measured]`, and no PDF can be written.
