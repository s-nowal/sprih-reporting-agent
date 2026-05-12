---
name: parser-skill
description: Convert files between any formats — PDF to Markdown, Markdown to Excel or PDF, CSV/Excel/DOCX/HTML/JSON/PPTX to Markdown, and more. Use this skill whenever a user wants to convert, extract, parse, or transform a file from one format to another, even if they phrase it casually (e.g. "turn this PDF into markdown", "make this into an Excel file", "extract text from this doc"). Always use this skill when a file conversion or parsing task is involved.
---

# Parser Skill

Convert files between any formats using the open-terminal container. This skill covers PDF → Markdown, Markdown → Excel/PDF, and all common document formats.

## Tools

### `upload_full_directory()`
Uploads the entire thread workspace (all subdirectories: `input/`, `output/`, `workspace/`, `reference/`) into the open-terminal container, preserving folder structure. Always call this first. Takes no arguments.

- Files land at their relative paths inside the container: e.g. a file at `input/report.pdf` in the workspace becomes `/input/report.pdf` in the container.

### `run_terminal_command(command, wait=300)`
Executes a shell command inside the container and returns stdout/stderr. Use this for installing packages, writing scripts, and running conversions.

- `command`: shell command string, e.g. `"python convert.py"` or `"pip install pymupdf --break-system-packages"`
- `wait`: max seconds to wait (default 300); increase for long-running jobs

### `add_file_to_local(env_path, local_filename)`
Fetches a file from the container and writes it into the thread's `workspace/parsed/` directory. Call this after the conversion to save the result back.

- `env_path`: path inside the container, e.g. `"/output.md"`
- `local_filename`: filename to save as, e.g. `"report_converted.md"`

---

## General Workflow

1. **Call `upload_full_directory()`** — stages all workspace files into the container
2. **Identify** the source file path inside the container (e.g. `/input/report.pdf`) and target format
3. **Write and run** a conversion script via `run_terminal_command`
4. **Install** dependencies as needed via `run_terminal_command("pip install <pkg> --break-system-packages")`
5. **Quality check** — inspect output with `run_terminal_command("wc -l /output.md")` etc.; re-run at a higher level if poor
6. **Call `add_file_to_local(env_path, local_filename)`** — pulls the result into `workspace/parsed/`

---

## Running Python

Always write scripts to a file first, then execute:

```bash
cat << 'EOF' > convert.py
# your code here
EOF
pip install <packages> --break-system-packages
python convert.py
```

---

## PDF → Markdown

Use progressive levels — try Level 1 first, escalate only if quality is poor.

**Quality check after each level:**
```bash
wc -l output.md          # too few lines = failure
head -50 output.md       # spot check structure
grep -c "^#" output.md   # heading count
```
Escalate if: fewer than 5 lines/page on average, no headings on a structured doc, tables are garbled, or most pages are blank.

### Level 1 — pymupdf (text-selectable PDFs)

```python
import fitz

doc = fitz.open("input.pdf")
chunks = [range(i, min(i+25, len(doc))) for i in range(0, len(doc), 25)]
all_md = []

for chunk in chunks:
    md = ""
    for page_num in chunk:
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] == 0:
                for line in block["lines"]:
                    for span in line["spans"]:
                        size = span["size"]
                        text = span["text"].strip()
                        if not text:
                            continue
                        if size >= 18:
                            md += f"# {text}\n"
                        elif size >= 14:
                            md += f"## {text}\n"
                        elif size >= 12:
                            md += f"### {text}\n"
                        else:
                            md += f"{text} "
                md += "\n"
    all_md.append(md)

with open("output.md", "w") as f:
    f.write("\n\n---\n\n".join(all_md))
```
```bash
pip install pymupdf --break-system-packages
```

### Level 2 — pdfplumber (table-heavy or complex layouts)

```python
import pdfplumber

all_md = []
with pdfplumber.open("input.pdf") as pdf:
    pages = pdf.pages
    chunks = [pages[i:i+25] for i in range(0, len(pages), 25)]
    for chunk in chunks:
        md = ""
        for page in chunk:
            for table in page.extract_tables():
                if not table:
                    continue
                headers = table[0]
                md += "| " + " | ".join(str(h or "") for h in headers) + " |\n"
                md += "| " + " | ".join("---" for _ in headers) + " |\n"
                for row in table[1:]:
                    md += "| " + " | ".join(str(c or "") for c in row) + " |\n"
                md += "\n"
            text = page.extract_text()
            if text:
                md += text + "\n"
        all_md.append(md)

with open("output.md", "w") as f:
    f.write("\n\n---\n\n".join(all_md))
```
```bash
pip install pdfplumber --break-system-packages
```

### Level 3 — PaddleOCR (scanned/image-only PDFs)

```bash
pip install paddleocr paddlepaddle pymupdf pillow --break-system-packages
```
```python
import fitz
from PIL import Image
from paddleocr import PaddleOCR
import io

ocr = PaddleOCR(use_angle_cls=True, lang="en")
doc = fitz.open("input.pdf")
all_md = []

for page_num in range(len(doc)):
    page = doc[page_num]
    pix = page.get_pixmap(dpi=200)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    img.save(f"page_{page_num}.png")
    result = ocr.ocr(f"page_{page_num}.png", cls=True)
    page_text = "\n".join([line[1][0] for line in result[0]]) if result[0] else ""
    all_md.append(page_text)

with open("output.md", "w") as f:
    f.write("\n\n---\n\n".join(all_md))
```

---

## Markdown → Excel

```bash
pip install openpyxl --break-system-packages
```
```python
import re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

wb = Workbook()
wb.remove(wb.active)

with open("input.md") as f:
    content = f.read()

sections = re.split(r'\n(?=#{1,2} )', content)

for section in sections:
    lines = section.strip().splitlines()
    if not lines:
        continue
    title_match = re.match(r'^#{1,2} (.+)', lines[0])
    sheet_name = title_match.group(1)[:31] if title_match else "Sheet"
    ws = wb.create_sheet(title=sheet_name)
    row_cursor = 1
    ws.cell(row=row_cursor, column=1, value=sheet_name).font = Font(bold=True, size=14)
    row_cursor += 2

    table_lines = [l for l in lines if l.startswith("|")]
    if table_lines:
        headers = [h.strip() for h in table_lines[0].split("|") if h.strip()]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=row_cursor, column=col, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="2E86AB")
        row_cursor += 1
        for trow in table_lines[2:]:
            cols = [c.strip() for c in trow.split("|") if c.strip()]
            for col, val in enumerate(cols, 1):
                ws.cell(row=row_cursor, column=col, value=val)
            row_cursor += 1
    else:
        for line in lines[1:]:
            if line.strip():
                ws.cell(row=row_cursor, column=1, value=line.strip())
                row_cursor += 1

    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

wb.save("output.xlsx")
```

---

## Markdown → PDF

**Option A — pandoc (preferred):**
```bash
apt-get install -y pandoc texlive-xetex texlive-fonts-recommended 2>/dev/null
pandoc input.md -o output.pdf --pdf-engine=xelatex -V geometry:margin=1in -V fontsize=12pt
```

**Option B — weasyprint (if pandoc unavailable):**
```bash
pip install markdown weasyprint --break-system-packages
```
```python
import markdown
from weasyprint import HTML

with open("input.md") as f:
    md_text = f.read()

html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
full_html = f"""<html><head><style>
  body {{ font-family: Arial, sans-serif; margin: 60px; font-size: 13px; }}
  h1 {{ color: #2E86AB; border-bottom: 2px solid #2E86AB; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ background: #2E86AB; color: white; padding: 8px; }}
  td {{ border: 1px solid #ccc; padding: 6px; }}
</style></head><body>{html_body}</body></html>"""
HTML(string=full_html).write_pdf("output.pdf")
```

---

## Other Format Conversions

| Source | Target | Library |
|---|---|---|
| CSV / TSV | Markdown, Excel | `pandas` |
| Excel (.xlsx) | Markdown, CSV | `openpyxl`, `pandas` |
| DOCX | Markdown | `python-docx` or pandoc |
| HTML | Markdown | `markdownify` or pandoc |
| JSON / YAML | Markdown table | `pandas` + `json`/`yaml` |
| PowerPoint | Markdown | `python-pptx` |
| Images | Markdown (OCR) | `paddleocr` |

For any unlisted format: identify the extension, find the best Python library, extract → structure → write to target.

---

## Saving Output

Write output files anywhere inside the container (e.g. `/output.md`, `/output.xlsx`), then call `add_file_to_local` to persist them:

```
add_file_to_local(env_path="/output.md", local_filename="report_converted.md")
```

The file is written to `workspace/parsed/report_converted.md` in the thread workspace. Name output files clearly: `originalname_converted.ext`.