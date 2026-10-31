# Large evidence kept outside git

This directory holds the lane's text deliverables, the extracted facts and the check tools: every file under 512 KiB with a text extension, except the plain-text extractions of PDFs, which contain page-break and other control bytes and would trip the repo's control-byte guard. Large binary evidence (PDFs, saved HTML pages and page renders, 87 MB in total) stays sealed on the coordinator's workstation at `H:/sl-temp/rooms/cad3d-research/lane1-anatomy/`.

`SHA256SUMS` here is the complete manifest of that sealed directory, all 258 files, including the ones not committed. To check a committed file, compare its hash with the manifest line for the same path. Reviewers can ask for any large file by path and hash.
