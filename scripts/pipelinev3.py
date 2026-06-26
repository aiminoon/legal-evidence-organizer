"""
Evidence Log Organizer - Integrated Single-File Pipeline
=========================================================
Takes a folder of images (screenshots, scanned docs, scene photos) and produces:
  1. A structured evidence log table (CSV) with full OCR text per item
  2. An HTML evidence report (styled, browser-viewable)
  3. Annotated images showing detected text regions (document layout viz)
  4. Before/after image-enhancement comparisons (one per image)
  5. A contact sheet / quality grid for the whole batch (triage at a glance)
  6. A beautiful, portable, vertical-scrolling A4 PDF Report with embedded images.

Usage:
  python pipelinev3.py <input_folder> <output_folder>
"""

import os
import sys
import csv
import cv2
import base64
import numpy as np
from html import escape as html_escape
from paddleocr import PaddleOCR

# ---------------------------------------------------------------------------
# CONFIG - tune these thresholds as you test with real images
# ---------------------------------------------------------------------------
BLUR_THRESHOLD = 100.0       # Laplacian variance below this = "blurry"
CONTRAST_THRESHOLD = 40.0    # std-dev of gray intensities below this = low contrast
                             # -> apply histogram equalization; otherwise leave as-is
STANDARD_WIDTH = 640         # resize images to this width before OCR
THUMBNAIL_WIDTH = 250        # size of each tile in the contact sheet

SUPPORTED_EXT = (".jpg", ".jpeg", ".png")

print("Loading PaddleOCR model (this may take a moment on first run)...")
OCR_ENGINE = PaddleOCR(
    lang="en",
    use_doc_orientation_classify=False,  
    use_doc_unwarping=False,             
    use_textline_orientation=False,      
    enable_mkldnn=False,                 
)

# ---------------------------------------------------------------------------
# UTILITIES & HELPERS FOR PORTABLE PDF GENERATION
# ---------------------------------------------------------------------------
try:
    from weasyprint import HTML as _WeasyHTML
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False


def _img_to_data_uri(path):
    """Read an image file and return a base64 data: URI, or None if missing."""
    if not path or not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _quality_badge(r):
    score = r["blur_score"]
    if r["blurry"]:
        return f'<span class="badge bad">Blurry ({score})</span>'
    if score < 300:
        return f'<span class="badge warn">Borderline ({score})</span>'
    return f'<span class="badge good">OK ({score})</span>'


# ---------------------------------------------------------------------------
# STEP 1: PREPROCESSING
# ---------------------------------------------------------------------------
def preprocess(img):
    h, w = img.shape[:2]
    scale = STANDARD_WIDTH / w
    resized = cv2.resize(img, (STANDARD_WIDTH, int(h * scale)))

    gray_before = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    contrast = float(gray_before.std())
    if contrast < CONTRAST_THRESHOLD:
        gray_after = cv2.equalizeHist(gray_before)
        enhanced = True
    else:
        gray_after = gray_before  
        enhanced = False

    return resized, gray_before, gray_after, enhanced


# ---------------------------------------------------------------------------
# STEP 2: BLUR / QUALITY CHECK
# ---------------------------------------------------------------------------
def is_blurry(gray_img, threshold=BLUR_THRESHOLD):
    variance = cv2.Laplacian(gray_img, cv2.CV_64F).var()
    return variance < threshold, variance


# ---------------------------------------------------------------------------
# STEP 3: OCR TEXT EXTRACTION
# ---------------------------------------------------------------------------
def extract_text(processed_img):
    if len(processed_img.shape) == 2:
        ocr_input = cv2.cvtColor(processed_img, cv2.COLOR_GRAY2BGR)
    else:
        ocr_input = processed_img

    result = OCR_ENGINE.predict(ocr_input)

    full_text_lines = []
    boxes = []

    if result:
        page = result[0]
        texts = page.get("rec_texts", [])
        polys = page.get("rec_polys", [])

        for text, quad_box in zip(texts, polys):
            full_text_lines.append(text)

            xs = [point[0] for point in quad_box]
            ys = [point[1] for point in quad_box]
            x, y = int(min(xs)), int(min(ys))
            w, h = int(max(xs) - x), int(max(ys) - y)

            boxes.append((text, x, y, w, h))

    full_text = "\n".join(full_text_lines)
    return full_text, boxes


# ---------------------------------------------------------------------------
# STEP 4: ANNOTATION
# ---------------------------------------------------------------------------
def annotate_image(resized_img, boxes, output_path):
    annotated = resized_img.copy()
    for word, x, y, w, h in boxes:
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 1)
    cv2.imwrite(output_path, annotated)


# ---------------------------------------------------------------------------
# STEP 5a: BEFORE / AFTER ENHANCEMENT COMPARISON
# ---------------------------------------------------------------------------
def make_before_after(gray_before, gray_after, output_path, enhanced=True):
    h, w = gray_before.shape

    left = cv2.cvtColor(gray_before, cv2.COLOR_GRAY2BGR)
    right = cv2.cvtColor(gray_after, cv2.COLOR_GRAY2BGR)

    divider = np.full((h, 4, 3), 255, dtype=np.uint8)
    combined = np.hstack([left, divider, right])

    after_label = "AFTER (contrast enhanced)" if enhanced else "AFTER (no enhancement needed)"
    cv2.putText(combined, "BEFORE", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    cv2.putText(combined, after_label, (w + 14, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    cv2.imwrite(output_path, combined)


# ---------------------------------------------------------------------------
# STEP 5b: CONTACT SHEET / QUALITY GRID
# ---------------------------------------------------------------------------
def make_contact_sheet(thumbnails, output_dir):
    if not thumbnails:
        return None

    cols = 3
    rows = (len(thumbnails) + cols - 1) // cols

    tile_h = int(THUMBNAIL_WIDTH * 0.75)
    label_h = 40
    cell_h = tile_h + label_h
    cell_w = THUMBNAIL_WIDTH

    sheet = np.full((rows * cell_h, cols * cell_w, 3), 255, dtype=np.uint8)

    for i, item in enumerate(thumbnails):
        r, c = divmod(i, cols)

        thumb = cv2.resize(item["image"], (THUMBNAIL_WIDTH, tile_h))

        border_color = (0, 0, 255) if item["blurry"] else (0, 200, 0)
        thumb = cv2.copyMakeBorder(thumb, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=border_color)
        thumb = cv2.resize(thumb, (THUMBNAIL_WIDTH, tile_h))

        y0, x0 = r * cell_h, c * cell_w
        sheet[y0:y0 + tile_h, x0:x0 + THUMBNAIL_WIDTH] = thumb

        label = f"{item['filename']}"
        score_label = f"blur: {item['blur_score']:.0f} {'(BLURRY)' if item['blurry'] else '(OK)'}"
        cv2.putText(sheet, label[:28], (x0 + 5, y0 + tile_h + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        cv2.putText(sheet, score_label, (x0 + 5, y0 + tile_h + 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

    sheet_path = os.path.join(output_dir, "contact_sheet.png")
    cv2.imwrite(sheet_path, sheet)
    return sheet_path


# ---------------------------------------------------------------------------
# STEP 6: HTML EVIDENCE REPORT (Local-use browser rendering fallback)
# ---------------------------------------------------------------------------
def generate_html_report(results, output_dir, contact_sheet_path):
    valid = [r for r in results if "error" not in r]
    total = len(valid)
    blurry_count = sum(1 for r in valid if r["blurry"])
    no_text_count = sum(1 for r in valid if not r["ocr_text"])

    table_rows = ""
    for i, r in enumerate(valid, 1):
        blur_score = r["blur_score"]
        if r["blurry"]:
            quality = f'<span class="badge bad">⚠️ Blurry ({blur_score})</span>'
        elif blur_score < 300:
            quality = f'<span class="badge warn">⚠️ Borderline ({blur_score})</span>'
        else:
            quality = f'<span class="badge good">✅ OK ({blur_score})</span>'

        if r["enhanced"]:
            enhanced_cell = '<span class="badge warn">enhanced</span>'
        else:
            enhanced_cell = '<span class="badge good">original</span>'

        ocr_preview = html_escape(r["ocr_text"][:120])
        if len(r["ocr_text"]) > 120:
            ocr_preview += "…"

        ocr_full = html_escape(r["ocr_text"]) if r["ocr_text"] else "<em>No text detected</em>"
        missing = html_escape(r["missing_info"])

        annotated_file = os.path.basename(r["annotated_image"])
        before_after_file = os.path.basename(r["before_after_image"])

        table_rows += f"""
        <tr>
          <td class="num">{i}</td>
          <td class="fname">{html_escape(r['filename'])}</td>
          <td class="score">{blur_score}</td>
          <td>{quality}</td>
          <td>{enhanced_cell}</td>
          <td class="ocr-cell">
            <div class="ocr-preview">{ocr_preview if ocr_preview else '<em>—</em>'}</div>
            <details>
              <summary>Full OCR text</summary>
              <pre class="ocr-full">{ocr_full}</pre>
            </details>
          </td>
          <td>{missing}</td>
          <td class="links">
            <a href="{annotated_file}">annotated</a><br>
            <a href="{before_after_file}">before/after</a>
          </td>
        </tr>"""

    contact_sheet_html = ""
    if contact_sheet_path and os.path.exists(contact_sheet_path):
        with open(contact_sheet_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        contact_sheet_html = f"""
        <section class="contact-sheet">
          <h2>📷 Contact Sheet — Batch Triage</h2>
          <p>Green border = OK quality. Red border = blurry. Blur scores shown per image.</p>
          <img src="data:image/png;base64,{b64}" alt="Contact sheet" style="max-width:100%;">
        </section>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Evidence Log Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f5f5f5; color: #222; padding: 24px; max-width: 1200px; margin: 0 auto;
  }}
  h1 {{ font-size: 1.5em; margin-bottom: 4px; }}
  h2 {{ font-size: 1.2em; margin: 24px 0 12px; color: #333; }}
  .meta {{ color: #666; font-size: 0.9em; margin-bottom: 20px; }}
  .stats {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .stat-card {{ background: #fff; border-radius: 8px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 140px; }}
  .stat-card .num {{ font-size: 2em; font-weight: 700; }}
  .stat-card .label {{ font-size: 0.85em; color: #666; }}
  .stat-card.alert .num {{ color: #d32f2f; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 8px; overflow: hidden; font-size: 0.88em; }}
  th {{ background: #2c3e50; color: #fff; padding: 10px 12px; text-align: left; font-weight: 600; white-space: nowrap; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
  tr:hover {{ background: #f9f9f9; }}
  td.num {{ text-align: center; font-weight: 700; width: 40px; }}
  td.fname {{ max-width: 200px; word-break: break-all; font-size: 0.85em; }}
  td.score {{ text-align: center; font-family: monospace; }}
  td.links a {{ color: #1976d2; text-decoration: none; font-size: 0.85em; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; white-space: nowrap; }}
  .badge.good {{ background: #e8f5e9; color: #2e7d32; }}
  .badge.warn {{ background: #fff3e0; color: #e65100; }}
  .badge.bad {{ background: #ffebee; color: #c62828; }}
  .ocr-cell {{ max-width: 300px; }}
  pre.ocr-full {{ background: #f5f5f5; padding: 8px; border-radius: 4px; white-space: pre-wrap; word-break: break-word; font-size: 0.8em; max-height: 200px; overflow-y: auto; }}
  .disclaimer {{ margin-top: 32px; padding: 16px; background: #fff3e0; border-left: 4px solid #ff9800; border-radius: 4px; font-size: 0.85em; color: #555; }}
</style>
</head>
<body>
<h1>📋 Evidence Log Report</h1>
<p class="meta">Generated by Evidence Log Organizer (CV pipeline)</p>
<div class="stats">
  <div class="stat-card"><div class="num">{total}</div><div class="label">Total items</div></div>
  <div class="stat-card {'alert' if blurry_count > 0 else ''}"><div class="num">{blurry_count}</div><div class="label">Blurry</div></div>
  <div class="stat-card {'alert' if no_text_count > 0 else ''}"><div class="num">{no_text_count}</div><div class="label">No text detected</div></div>
</div>
<h2>Evidence Log Table (CV-derived)</h2>
<table>
  <thead>
    <tr><th>#</th><th>Filename</th><th>Blur Score</th><th>Quality</th><th>Enhanced</th><th>OCR Text</th><th>Missing Info</th><th>Artifacts</th></tr>
  </thead>
  <tbody>{table_rows}</tbody>
</table>
{contact_sheet_html}
</body>
</html>"""

    html_path = os.path.join(output_dir, "evidence_report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html_path


# ---------------------------------------------------------------------------
# STEP 7: FIXED PORTABLE PDF REPORT (Stacked Cards Layout for Mobile/A4 Windows)
# ---------------------------------------------------------------------------
def generate_pdf_report(results, output_dir, contact_sheet_path, include_before_after=True):
    """
    Build evidence_report.pdf from the pipeline results using a structural card layout.
    Replaces squashed wide horizontal tables with clean, scalable vertical segments.
    """
    if not WEASYPRINT_AVAILABLE:
        print("  [PDF skipped] WeasyPrint unavailable natively.")
        return None

    valid = [r for r in results if "error" not in r]
    total = len(valid)
    blurry_count = sum(1 for r in valid if r["blurry"])
    no_text_count = sum(1 for r in valid if not r["ocr_text"])

    items_html = ""
    for i, r in enumerate(valid, 1):
        ocr = html_escape(r["ocr_text"]) if r["ocr_text"] else "<em>No text detected by OCR.</em>"
        enhanced = "enhanced" if r["enhanced"] else "original"
        missing = html_escape(r["missing_info"])

        imgs = ""
        ann = _img_to_data_uri(r.get("annotated_image"))
        if ann:
            imgs += (
                '<div class="imgwrap">'
                '<div class="imglabel">Annotated &mdash; detected text regions</div>'
                f'<img src="{ann}" alt="annotated">'
                '</div>'
            )
        if include_before_after:
            ba = _img_to_data_uri(r.get("before_after_image"))
            if ba:
                imgs += (
                    '<div class="imgwrap">'
                    '<div class="imglabel">Before / after enhancement</div>'
                    f'<img src="{ba}" alt="before after">'
                    '</div>'
                )

        items_html += f"""
        <section class="item">
          <div class="item-head">
            <span class="item-num">#{i}</span>
            <span class="item-name">{html_escape(r['filename'])}</span>
            {_quality_badge(r)}
            <span class="badge {'warn' if r['enhanced'] else 'good'}">{enhanced}</span>
          </div>
          <div class="kv"><span class="k">Blur score</span><span class="v">{r['blur_score']}</span></div>
          <div class="kv"><span class="k">Missing info</span><span class="v">{missing}</span></div>
          <div class="ocr-label">OCR text</div>
          <div class="ocr">{ocr}</div>
          {imgs}
        </section>"""

    contact_html = ""
    cs = _img_to_data_uri(contact_sheet_path)
    if cs:
        contact_html = f"""
        <section class="contact">
          <h2>Contact sheet &mdash; batch triage</h2>
          <p class="hint">Green border = OK quality, red border = blurry. Blur score shown per image.</p>
          <img src="{cs}" alt="contact sheet">
        </section>"""

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Evidence Log Report</title>
<style>
  @page {{
    size: A4;
    margin: 1.4cm 1.4cm 1.8cm 1.4cm;
    @bottom-center {{ content: "Page " counter(page) " of " counter(pages); font-size: 8.5pt; color: #999; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'DejaVu Sans', 'Noto Sans', Arial, sans-serif; font-size: 10.5pt; color: #222; line-height: 1.45; }}
  h1 {{ font-size: 17pt; margin: 0 0 2pt; }}
  h2 {{ font-size: 12.5pt; margin: 14pt 0 6pt; color: #2c3e50; }}
  .meta {{ color: #666; font-size: 8.5pt; margin-bottom: 12pt; }}
  .stats {{ margin-bottom: 14pt; }}
  .stat {{ display: inline-block; border: 1px solid #e2e2e2; border-radius: 6px; padding: 7pt 14pt; margin-right: 7pt; min-width: 86pt; vertical-align: top; }}
  .stat .n {{ font-size: 18pt; font-weight: 700; }}
  .stat .l {{ font-size: 8pt; color: #666; }}
  .stat.alert .n {{ color: #c62828; }}
  .item {{ border: 1px solid #e2e2e2; border-radius: 6px; padding: 10pt 12pt; margin-bottom: 10pt; break-inside: avoid; }}
  .item-head {{ margin-bottom: 6pt; }}
  .item-num {{ font-weight: 700; margin-right: 6pt; }}
  .item-name {{ font-family: monospace; font-size: 8.5pt; color: #444; margin-right: 6pt; word-break: break-all; }}
  .kv {{ font-size: 9pt; }}
  .kv .k {{ color: #888; display: inline-block; min-width: 72pt; }}
  .ocr-label {{ font-size: 8pt; color: #888; margin-top: 6pt; }}
  .ocr {{ background: #f6f6f6; border-radius: 4px; padding: 7pt 9pt; margin-top: 2pt; white-space: pre-wrap; word-break: break-word; font-size: 9pt; }}
  .imgwrap {{ margin-top: 8pt; break-inside: avoid; }}
  .imglabel {{ font-size: 8pt; color: #888; margin-bottom: 3pt; }}
  .imgwrap img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 4px; }}
  .badge {{ display: inline-block; padding: 1pt 6pt; border-radius: 4px; font-size: 8pt; font-weight: 700; }}
  .badge.good {{ background: #e8f5e9; color: #2e7d32; }}
  .badge.warn {{ background: #fff3e0; color: #e65100; }}
  .badge.bad  {{ background: #ffebee; color: #c62828; }}
  .contact {{ margin-top: 14pt; break-inside: avoid; }}
  .contact img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 4px; }}
  .hint {{ font-size: 8.5pt; color: #666; margin-bottom: 4pt; }}
  .disclaimer {{ margin-top: 16pt; padding: 10pt 12pt; background: #fff8ef; border-left: 3px solid #ff9800; border-radius: 4px; font-size: 8.5pt; color: #555; }}
  .disclaimer b {{ color: #e65100; }}
</style></head><body>
  <h1>Evidence Log Report</h1>
  <div class="meta">Generated by Evidence Log Organizer (CV pipeline).</div>
  <div class="stats">
    <div class="stat"><div class="n">{total}</div><div class="l">Total items</div></div>
    <div class="stat {'alert' if blurry_count else ''}"><div class="n">{blurry_count}</div><div class="l">Blurry</div></div>
    <div class="stat {'alert' if no_text_count else ''}"><div class="n">{no_text_count}</div><div class="l">No text detected</div></div>
  </div>
  {contact_html}
  <h2>Evidence items</h2>
  {items_html}
  <div class="disclaimer">
    <b>Disclaimer:</b> This report is AI-generated and organized via computer vision. It is intended solely for reference and review, does not constitute legal advice, and does not determine the authenticity, truth, or legal validity of any evidence.
  </div>
</body></html>"""

    pdf_path = os.path.join(output_dir, "evidence_report.pdf")
    try:
        _WeasyHTML(string=html, base_url=output_dir).write_pdf(pdf_path)
        return pdf_path
    except Exception as e:
        print(f"  [PDF skipped] WeasyPrint failed to render: {e}")
        return None


# ---------------------------------------------------------------------------
# MAIN PIPELINE EXECUTION
# ---------------------------------------------------------------------------
def process_image(filepath, output_dir):
    filename = os.path.basename(filepath)
    img = cv2.imread(filepath)

    if img is None:
        return {"filename": filename, "error": "could not read image"}, None

    resized, gray_before, gray_after, enhanced = preprocess(img)
    blurry, blur_score = is_blurry(gray_before)
    text, boxes = extract_text(gray_after)

    annotated_path = os.path.join(output_dir, f"annotated_{filename}")
    annotate_image(resized, boxes, annotated_path)

    before_after_path = os.path.join(output_dir, f"before_after_{filename}")
    make_before_after(gray_before, gray_after, before_after_path, enhanced)

    missing = []
    if blurry:
        missing.append("image too blurry for reliable OCR")
    if not text.strip():
        missing.append("no text detected by OCR")

    row = {
        "filename": filename,
        "blurry": blurry,
        "blur_score": round(blur_score, 1),
        "enhanced": enhanced,
        "ocr_text": text.strip().replace("\n", " "),
        "missing_info": "; ".join(missing) if missing else "none",
        "annotated_image": annotated_path,
        "before_after_image": before_after_path,
    }

    thumb_info = {
        "image": resized,
        "filename": filename,
        "blur_score": blur_score,
        "blurry": blurry,
    }

    return row, thumb_info


def write_csv(results, output_dir):
    csv_path = os.path.join(output_dir, "evidence_log.csv")
    fieldnames = [
        "filename", "blurry", "blur_score", "enhanced", "ocr_text",
        "missing_info", "annotated_image", "before_after_image"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            if "error" not in r:
                writer.writerow(r)
    return csv_path


def main(input_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    image_files = [
        os.path.join(input_dir, f) for f in sorted(os.listdir(input_dir))
        if f.lower().endswith(SUPPORTED_EXT)
    ]

    if not image_files:
        print(f"No images found in {input_dir} (supported: {SUPPORTED_EXT})")
        return

    print(f"Found {len(image_files)} image(s). Processing...")

    results = []
    thumbnails = []
    for fp in image_files:
        print(f"  - {os.path.basename(fp)}")
        row, thumb = process_image(fp, output_dir)
        results.append(row)
        if thumb is not None:
            thumbnails.append(thumb)

    csv_path = write_csv(results, output_dir)
    contact_sheet_path = make_contact_sheet(thumbnails, output_dir)
    html_path = generate_html_report(results, output_dir, contact_sheet_path)
    
    # Generate structured PDF using localized logic context seamlessly
    pdf_path = generate_pdf_report(results, output_dir, contact_sheet_path)

    print("\nDone!")
    print(f"  Evidence log CSV    : {csv_path}")
    print(f"  Evidence report HTML: {html_path}")
    if pdf_path:
        print(f"  Evidence report PDF : {pdf_path}")
    print(f"  Contact sheet       : {contact_sheet_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python pipelinev3.py <input_folder> <output_folder>")
        sys.exit(1)

    main(sys.argv[1], sys.argv[2])