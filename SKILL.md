---
name: evidence-log-organizer
description: Organizes messy legal evidence images (screenshots, scanned documents, scene photos) into a structured evidence log. Trigger when the user uploads a folder or batch of images and asks to "organize evidence", "create an evidence log", "log these documents/screenshots", or similar. Legal, journalism, or case-preparation contexts only.
---

# Evidence Log Organizer

Takes a folder of evidence images, runs a CV + OCR pipeline (`pipelinev3.py`), and delivers an organized evidence log (PDF, HTML, CSV, contact sheet) back to the user over Telegram. The pipeline does all the image work. You do the language work by reading the CSV it produces — you never open the images yourself.

## Inputs

Accepted: image files (`.jpg`, `.jpeg`, `.png`) — chat screenshots, photographed documents, scene photos, public notices.

Not supported: video, audio, PDF. If the user sends these, tell them plainly they are not supported. Do not silently skip them.

## Inbound images

For each image the user sends, the framework gives you a local file path to the downloaded image. Use that path exactly as given.

- Do not build a path out of a `media:` URI. Never prepend the skill directory or any other folder to a `media:` string.
- If a path you were given does not exist on disk, reply: "Could not read image — it may not have downloaded correctly. Please resend." Do not try other paths.

## 1. Create the run folder

Make one timestamped folder and keep everything for this run inside it:

```bash
OUTPUT_DIR="{baseDir}/evidence_output/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR/input"
```

Copy the inbound images into `$OUTPUT_DIR/input/`. All output must stay under `{baseDir}` — files outside it cannot be sent to Telegram.

## 2. Run the pipeline

Do not run `pip install`. All dependencies are already in `{baseDir}/.venv`. If that venv is missing, stop and tell the user — do not rebuild it.

```bash
source {baseDir}/.venv/bin/activate && python {baseDir}/scripts/pipelinev3.py "$OUTPUT_DIR/input" "$OUTPUT_DIR"
```

This writes into `$OUTPUT_DIR`:

- `evidence_report.pdf` — primary deliverable (HTML fallback if PDF generation is unavailable)
- `evidence_report.html`
- `evidence_log.csv` — one row per image: `filename, blurry, blur_score, enhanced, ocr_text, missing_info, annotated_image, before_after_image`
- `contact_sheet.png` — triage grid of all images with blur scores
- `annotated_<name>.png`, `before_after_<name>.png` — per image

## 3. Read the results — CSV only, never the images

Find the run folder and print its path (a later shell will not remember `$OUTPUT_DIR`):

```bash
OUTPUT_DIR="$(ls -dt {baseDir}/evidence_output/*/ | head -1)"; OUTPUT_DIR="${OUTPUT_DIR%/}"; echo "$OUTPUT_DIR"
```

Read only `"$OUTPUT_DIR/evidence_log.csv"`. Do not open, read, or view any `.jpg`, `.png`, or `.pdf` file in this skill — the pipeline already did the vision work and put everything you need in the CSV. Opening images wastes time and causes path errors.

From the CSV (mainly the `ocr_text` column), identify where present: image type, dates/times, phone numbers, reference/case numbers, and names of people, organizations, and places. Mark every one of these as "detected — for review", and state plainly when something is not found. Never invent a value.

## 4. Send the results

Send every message and file with the `message` tool — OpenClaw's built-in action for replying and attaching media on the active channel. These are replies in the current conversation, so you do not need to look up a chat id: OpenClaw routes a Telegram reply back to the same chat automatically. Do not use `MEDIA:` directives — they render only in webchat and silently fail on Telegram.

The `message` tool must be available to this agent. If it is not, the tool profile has removed it — stop and report that plainly, rather than falling back to `MEDIA:` or describing files you cannot actually send.

Send these as separate messages, in order.

**Message 1 — TLDR.** One short paragraph, under 500 characters, no table, no bullets: what the batch is about, total items processed, how many flagged blurry or missing text, key names/dates/locations/reference numbers, and any urgent flag.

```
📋 TLDR — 7 images processed. Motor vehicle accident on 14 Jun 2026 ~11:53 AM, Jalan Tun Razak / Jalan Ampang. Danial (Perodua Myvi WVK8842) rear-ended by Mr. Lim Chee Keong (Honda City VBA3271). Both Allianz insured. No injuries. 0 blurry, 1 scene photo needs review. Police report #15050020 — file within 24h.
```

**Message 2 — Missing Information.** One `•` line per issue.

```
🔍 Missing Information:
• #4 — Scene photo, minimal OCR. Needs human review.
• #1 — Report date/time not visible in OCR. Confirm against the copy.
• #2–7 — No phone numbers detected in any screenshot.
```

**Message 3 — Draft Case Appendix.** Prose blocks, clearly marked draft.

```
📑 DRAFT CASE APPENDIX — requires human review

Item 1 — Police Report Reference
Screenshot of a Polis Diraja Malaysia document. Report #15050020. Confirm details against the physical copy.

Items 2–3 — Initial Accident Report
WhatsApp chat: Danial reports a rear-end collision at ~11:53 AM, 14 Jun 2026...
```

Consecutive screenshots from the same conversation may be grouped. Scene photos and documents are always separate entries.

**Then the files.** Attach each one as media with the `message` tool. Print the run folder first so you have the absolute paths:

```bash
ls -dt {baseDir}/evidence_output/*/ | head -1
```

From that folder, send:

- `evidence_report.pdf` as a document — send `evidence_report.html` instead **ONLY** if the PDF was not generated.
- `contact_sheet.png` as a photo — mandatory every run.
- `evidence_log.csv` as a document.
- For 5 or fewer images, also send each `annotated_<name>.png` and `before_after_<name>.png` as photos. For more than 5, send only the contact sheet and tell the user the rest are in the output folder — give the folder name only (e.g. `20260626_124803`), never the full path.

## Do not

- Do not open, read, or view any image or PDF — read only the CSV.
- Do not use `MEDIA:` directives.
- Do not write output outside `{baseDir}`.
- Do not paste the full table or full OCR text into chat — those live in the PDF and CSV.
- Do not show the user absolute or home paths — say "the output folder" or give only the folder name.
- Do not end a run having sent only text. At minimum `evidence_report.pdf` and `contact_sheet.png` must be uploaded.

## Ethical boundary

This skill only organizes and summarizes visible information. It does not judge guilt, fault, truth, authenticity, or legal validity. It does no facial recognition and identifies people only by names already printed in the image text. Every output is a draft for the user to review, not a final legal document.

## Limitations

- Blurry image or empty OCR: say so, recommend re-taking, do not guess the content.
- Image type and all extracted fields are detected candidates for review, not confirmed facts.
- Video, audio, and PDF are not supported.
- If the folder has no supported images, report that clearly and produce no report.