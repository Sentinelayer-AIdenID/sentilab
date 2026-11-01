# Re-exporting the three-minute deck

The gate ran on 2026-10-31 between 23:41 and 23:44 UTC, and the operator reported **PASS** (team room message 57377):
75.48 C and 115.93 C against the paper's 75.48 C and 115.94 C. That result is recorded in `FINAL.json` (`gate.result`),
so a plain build now exports slide 4 as PASS. It quotes those values, the same-layout version comparison and the scope.
The verification line reads: "Verified by the operator; independent re-derivation by a second reviewer in progress".

Each command below is the whole job. It rebuilds the data, re-reads the pull requests, moves the deck's one cutoff to
now, and exports the PDF plus a fresh render of every page. The new PDF replaces the old one, so this folder always holds
one PDF.

Run from the repository root. `PLAYWRIGHT_DIR` must be a folder holding `node_modules/playwright`; on the workstation,
`C:/tmp/forge-skills-install` works.

## When the second reviewer confirms the re-derivation (the one-flag change)

```
PLAYWRIGHT_DIR=C:/tmp/forge-skills-install node scripts/build-deck-final.mjs --rederived --refresh-prs --export --shots C:/tmp/deck-final-shots
```

`--rederived` changes only the verification line, to "Verified by the operator and independently re-derived by a second
reviewer", and the matching sentence in the speaker notes. It is refused for anything but the recorded result.

## Refreshing the current state

```
PLAYWRIGHT_DIR=C:/tmp/forge-skills-install node scripts/build-deck-final.mjs --refresh-prs --export --shots C:/tmp/deck-final-shots
```

## If the recorded result changes

Edit `gate.result` in `FINAL.json`: the outcome, the two measured values, the records, the comparison and the
verification lines. Have it reviewed, then run the refresh command above. The build checks the new result against the
fixed rules:

- **PASS** needs both values within 1.0 K of 75.48 C and 115.94 C.
- **FAIL** needs at least one value outside 1.0 K. Its values replace `[values]` in the reviewed wording ("It missed:
  … C and … C.").
- **The comparison line** must quote both of its values and the rounded gaps to the paper that those values give.

**ERROR and INCOMPLETE** have no reviewed wording, so neither builds. A FAIL caused by something other than a missed
value (a replay that differs, or evidence that does not verify) also needs reviewed wording first.

## Other outcomes, for review only

- `--gate not-run`: the NOT RUN wording. It is kept for the record and is no longer true.
- `--gate fail --preview` and `--gate pass --preview`: no values. Every slide is marked "PREVIEW · not a result", and no
  PDF can be written.

## After any export

1. Look at the new PDF and at slide 4 in the shots folder.
2. Run `node --test scripts/deck-data.test.mjs`.
3. Commit `FINAL.json`, `deck/final/deck-data.json`, `deck/final/deck-data.js`, the new PDF and the removal of the old
   one. Then send the head for review.

The five main slides must stay within 165 s of speech. The build prints each slide's words and seconds, and refuses
anything over the budget. The export fails on any of these:

- overflow or clipped text;
- main-slide text under 28 px;
- contrast under 4.5:1;
- a missing value.
