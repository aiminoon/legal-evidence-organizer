# ⚖️ Legal Evidence Organizer

> Giving computers eyes to read evidence. 👁️

A Computer Vision + OCR pipeline that turns messy, image-based legal evidence
— WhatsApp screenshots, scanned documents, scene photos, police reports,
receipts, public notices — into an organized, review-ready evidence log.

Built at **FSKTM, Universiti Malaya** as part of the **OpenClaw / UMClaw**
project (WID3013 — Computer Vision and Pattern Recognition).

---

## What it does

Instead of relying only on text, the system *sees* the evidence first. It runs
a CV + OCR pipeline over a folder of images and produces:

- 📄 **`evidence_report.pdf`** — a portable, A4, vertical-scrolling report with embedded images (HTML fallback if PDF rendering is unavailable)
- 🌐 **`evidence_report.html`** — browser-viewable version of the same report
- 📊 **`evidence_log.csv`** — one row per image: filename, blur status, blur score, enhancement flag, OCR text, missing-info flags, and paths to the annotated/before-after images
- 🖼️ **`contact_sheet.png`** — a triage grid of the whole batch (green border = OK, red border = blurry)
- 📌 **`annotated_<name>.png`** — detected text regions boxed on each image
- 🔄 **`before_after_<name>.png`** — image-enhancement comparison per image

## How it works

The pipeline (`scripts/pipelinev3.py`) processes each image through:

1. **Preprocessing** — resize to a standard width; measure contrast and apply histogram equalization when contrast is low.
2. **Blur / quality check** — Laplacian variance flags blurry, low-reliability images.
3. **OCR extraction** — [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) reads text and returns bounding boxes.
4. **Annotation** — text regions are drawn back onto the image for layout visualization.
5. **Reporting** — a contact sheet, CSV log, HTML report, and WeasyPrint-rendered PDF are assembled.

A separate **OpenClaw skill** (`SKILL.md`) wraps the pipeline so users can
upload evidence via a **Telegram bot**: the agent runs the pipeline, reads only
the CSV, and replies with a TLDR, a missing-information list, a draft case
appendix, and the generated files.

## Tech stack

| Layer | Tools |
|-------|-------|
| Computer Vision | OpenCV, blur detection, image enhancement, layout visualization |
| OCR | PaddleOCR |
| Document processing | WeasyPrint (PDF), HTML/CSV generation |
| Agent / deployment | OpenClaw, OpenRouter LLM, Telegram bot, Python |

## Quick start

```bash
# 1. Clone
git clone https://github.com/<your-username>/legal-evidence-organizer.git
cd legal-evidence-organizer

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the pipeline on a folder of images
python scripts/pipelinev3.py <input_folder> <output_folder>
```

Supported input formats: `.jpg`, `.jpeg`, `.png`. Video, audio, and PDF are not supported.

> **Note:** On first run, PaddleOCR downloads its detection/recognition models,
> which can take a few minutes.

## Configuration

Thresholds can be tuned at the top of `scripts/pipelinev3.py`:

| Constant | Default | Meaning |
|----------|---------|---------|
| `BLUR_THRESHOLD` | `100.0` | Laplacian variance below this = blurry |
| `CONTRAST_THRESHOLD` | `40.0` | Gray std-dev below this triggers histogram equalization |
| `STANDARD_WIDTH` | `640` | Width images are resized to before OCR |
| `THUMBNAIL_WIDTH` | `250` | Tile size in the contact sheet |

## ⚠️ Scope & ethical boundary

This tool **only organizes and summarizes visible information.** It does **not**:

- judge guilt, fault, truth, authenticity, or legal validity,
- perform facial recognition (people are identified only by names already printed in the image text),
- produce final legal documents — every output is a **draft for human review.**

It removes the repetitive work of reviewing and organizing evidence so people
can focus on analysis, interpretation, and decision-making — not replace human
judgment. **Do not commit real case evidence to this repository.**

## Team

Developed at FSKTM, Universiti Malaya:

- Dennis
- Aiman Sharuddin
- Muhammad Imran bin Ilias
- Fairuz Anika Mysha

With thanks to **FSKTM UM** for the support. For details and collaborations:
`zum.lab@um.edu.my`.

## License

See [LICENSE](LICENSE).
