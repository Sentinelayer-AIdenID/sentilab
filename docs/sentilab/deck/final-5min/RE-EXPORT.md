# Re-exporting the five-minute deck

The deck is built from `FINAL.json` in this folder by `scripts/build-deck-final.mjs`. The eleven figures in `figures/`
are aneta-claude's SVGs, byte for byte, beside two stills of our 3D package view: the full screenshot (backup) and a crop of its package render (slides 1 and 9). FINAL.json pins both, with the crop's box; the tests compare the crop with that box of the screenshot, pixel for pixel. Cut a new crop with an image tool from the reviewed screenshot only, never by editing pixels. The build writes the copies the deck serves to `deck/final-5min/figures/`, with
only the text edits `FINAL.json` declares (see `TIMELINE-VERIFY.md`). Never edit those served copies by hand. Never run
the contributed `make_figures.py` or `render.mjs`.

The three-minute deck in `../final-3min/` and `deck/final/` is preserved as exported at 00:12 UTC. The tests pin every
file, and the exporter refuses to write any of them.

## Script v3 and the slot

The main slides are script v3 (`PLAIN-SCRIPT.md`), and `--slot 3total` builds the short cut from
`PLAIN-SCRIPT-SHORT.md` over the same screens; `--slot 3+2` is the default. `--demo-status live|recorded` picks the
door's variant (RECORDED by default; LIVE needs the confirmed address, or `--demo-review` for a marked review render).
A real recorded run goes into the door's `runs` list with its date and room record. `plainTalk.namesOnStage` puts
names on the team slide once Carter says yes; it needs every person's and agent's name first.

## The plain talk (v2.5, kept as the fallback)

The nine main slides are the plain-language script in `PLAIN-SCRIPT.md`: `plainTalk` in `FINAL.json` holds each slide's
title and "Say" text word for word, its picture and its caption, and the tests compare them with the script. For a new
script version, replace `PLAIN-SCRIPT.md` with the file as sent, copy the changed lines into `plainTalk`, and update the
script's sha256 in `scripts/deck-final.test.mjs`. Every slide of the earlier five-minute deck follows as backup, unchanged.
No K, kelvin, formula, grid or "statistic" may appear on a main slide, in its notes or in its figure; the build refuses
one, so technical detail goes to the backup slides.

`plainTalk.numbersOnStage` is slide 8's switch, `false` by default: Carter decides. When it is `true`, slide 8 says the
script's bracketed numbers line and shows the three numbers. Money may appear only there and on backup B7.

Run every command from the repository root. `PLAYWRIGHT_DIR` must be a folder holding `node_modules/playwright`; on the
workstation, `C:/tmp/forge-skills-install` works.

## The export

```
PLAYWRIGHT_DIR=C:/tmp/forge-skills-install node scripts/build-deck-final.mjs --rederived --refresh-prs --cutoff <UTC time> --export --shots C:/tmp/deck-5min-shots
```

- Read both rooms first, then set `cutoff` in `FINAL.json` to the time you will declare. It is the reviewed cutoff the
  tests build at, and it cannot be earlier than the pull-request check time the refresh stamps.
- `--cutoff` is required with `--refresh-prs`. A pull-request refresh makes only those rows current. The cutoff
  declares that every other fact was checked too, so read the rooms first, then give a time no earlier than now (the
  refresh stamps the rows with the current minute).
- `--rederived` states the completed independent re-derivation (team room 57394). It is refused for anything but the
  recorded PASS.
- `--demo-status live|replay` picks slide 9's variant and its scripted lines. `replay` is the default, and the plain
  door has no `staging`. `live` is refused while `demo.urlIsPlaceholder` is true in `FINAL.json`: set it to false once
  the address is confirmed, which is also the only way a LIVE slide reaches a PDF.
- The PDF is written as `SentiLab-5min-<cutoff date>-<HHMM>-pass.pdf`. The exporter never deletes anything. If an
  earlier PDF is in this folder, remove it with `git rm` in the same commit, because the tests allow one PDF.

## The speaker script

Every export also writes `SCRIPT.md` here: each main slide's exact spoken words as the deck renders them (consent
names resolved, at the recorded result), with the word count and the seconds at 150 words a minute, slide 8 with its
numbers line named as on or off, both of the door's scripted lines (LIVE and REPLAY), and the clock at 150 and 135
words a minute. It is generated from the same data as the PDF, and `--check` and the tests compare
it with a fresh build. Keep it under 16,000 characters, so that it fits in one room message.

## Naming an outside team once it agrees

Each team in `FINAL.json` has one line, `"consent": null`. When a team says yes, replace `null` with its record on that
same line:

```
"consent": "32a841e5 seq 57490 at 2026-11-01T02:10:00Z"
```

This means the help room, the message's sequence number, and its UTC time. If the team asks to be named in a particular form, add it as `"credit"` beside its name (Delfie: `"Delfie (delphisci team)"`); the build uses it wherever it names the team, and the leak checks keep looking for the bare name. fig6 is aneta's drawing for one consent
set, `drawnFor` in `FINAL.json`. The build stops until she sends a redrawn fig6 for the new set; put it in
`figures/` and update its sha256 and `drawnFor`. Then export again with a cutoff no earlier than that time. Nothing
else moves on the slides. That team's name replaces "an outside team" in the text and in the figure
labels, and backup B21 lists who consented. The generated data keeps the room and sequence of each consent. Teams that
have not consented stay unnamed everywhere, and the build refuses any slide, note or figure that still names them.

## Review renders: the other gate outcomes and the LIVE door

```
node scripts/build-deck-final.mjs --gate not-run
node scripts/build-deck-final.mjs --gate fail --preview
node scripts/build-deck-final.mjs --rederived --demo-status live --demo-review
```

The first two keep the reviewer's wording for the gate slide (backup B4). Every slide is marked "REVIEW · not the
recorded result" or "PREVIEW · not a result". The third renders slide 9 LIVE before the address is confirmed, with every
slide marked "REVIEW · door variant, not the export". None of them can write a PDF or `SCRIPT.md`. To refresh
`variants/`, export screenshots with `--no-pdf --shots <dir>` after each build and copy `13-gate-1920x1080.png` as
`gate-<outcome>-1920x1080.png` and `09-talk9-1920x1080.png` as `slide9-live-1920x1080.png` (and, from the real export,
`slide9-replay-1920x1080.png` and `gate-pass-1920x1080.png`). Finish with the real export above, so that the committed
data is the recorded result.

## Checks

- The talk before the door (slides 1 to 8) is counted at 150 words a minute. With 15 s of transitions it must fit
  180 s. The door's spoken lines count inside the 120 s demo clock (root, team room 57481). The build refuses anything
  over, and prints the relaxed 135 words a minute (2.25 a second) beside it. Backup notes are not timed.
- The export fails on overflow, clipped text, main-slide text under 28 px, any text under 22 px (figure text included,
  at the scale it is drawn), contrast under 4.5:1, a figure that does not load, or a browser error.
- `node --test scripts/deck-data.test.mjs` runs this deck's tests with the others. `node scripts/build-deck-final.mjs
  --check` confirms that the committed data and figures are a fresh build.
