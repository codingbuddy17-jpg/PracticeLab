import io
import fitz  # pymupdf
from docx import Document
from PIL import Image
from typing import List, Tuple


def process_file(filename: str, file_bytes: bytes) -> List[Tuple[bytes, str, str]]:
    """
    Convert any uploaded file to a list of (png_bytes, mime_type, page_text) tuples — one per page.
    Returns PNG images regardless of input format.
    """
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "pdf":
        return _pdf_to_images(file_bytes)
    elif ext in ("png", "jpg", "jpeg", "tiff", "tif", "bmp", "webp"):
        return _image_to_png_with_text(file_bytes)
    elif ext in ("doc", "docx"):
        return _docx_to_images(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _pdf_to_images(data: bytes) -> List[Tuple[bytes, str, str]]:
    doc = fitz.open(stream=data, filetype="pdf")
    pages = []
    mat = fitz.Matrix(1.5, 1.5)  # 1.5x: ~44% smaller PNGs vs 2x, still sharp enough for chart viewing
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        text = page.get_text("text") or ""
        pages.append((pix.tobytes("png"), "image/png", text.strip()))
    doc.close()
    return pages


def _image_to_png_with_text(data: bytes) -> List[Tuple[bytes, str, str]]:
    img = Image.open(io.BytesIO(data))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return [(buf.getvalue(), "image/png", "")]




def _docx_to_images(data: bytes) -> List[Tuple[bytes, str, str]]:
    """
    Converts docx to PDF via libreoffice if available, falls back to
    extracting embedded images or rendering as plain text page.
    """
    try:
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(data)
            tmp_path = f.name

        out_dir = tempfile.mkdtemp()
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, tmp_path],
            capture_output=True, timeout=30
        )
        os.unlink(tmp_path)

        pdf_files = [f for f in os.listdir(out_dir) if f.endswith(".pdf")]
        if result.returncode == 0 and pdf_files:
            pdf_path = os.path.join(out_dir, pdf_files[0])
            with open(pdf_path, "rb") as pf:
                pdf_bytes = pf.read()
            os.unlink(pdf_path)
            os.rmdir(out_dir)
            return _pdf_to_images(pdf_bytes)  # type: ignore
    except Exception:
        pass

    # Fallback: extract embedded images from docx
    doc = Document(io.BytesIO(data))
    images = []
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            img_bytes = rel.target_part.blob
            try:
                img = Image.open(io.BytesIO(img_bytes))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                images.append((buf.getvalue(), "image/png", ""))
            except Exception:
                continue

    if images:
        return images

    # Last resort: render text content as an image
    text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    return _text_to_image(text)


def _text_to_image(text: str) -> List[Tuple[bytes, str, str]]:
    from PIL import ImageDraw, ImageFont
    img = Image.new("RGB", (1200, 1600), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 40), text[:3000], fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return [(buf.getvalue(), "image/png", text)]
