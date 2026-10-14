import asyncio
import io
import zipfile
from pathlib import PurePath

import pytesseract
from docx import Document
from PIL import Image
from pypdf import PdfReader

Image.MAX_IMAGE_PIXELS = 20_000_000
ALLOWED = {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".docx", ".txt"}


def extract_sync(data: bytes, filename: str, limit: int) -> str:
    if len(data) > limit:
        raise ValueError("Файл превышает лимит")
    extension = PurePath(filename.lower()).suffix
    if extension not in ALLOWED:
        raise ValueError("Неподдерживаемый формат")
    if extension == ".txt":
        return data.decode("utf-8-sig", errors="replace")[:16000]
    if extension in {".jpg", ".jpeg", ".png", ".webp"}:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return pytesseract.image_to_string(image, lang="rus+eng", timeout=20)[:16000]
    if extension == ".docx":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 30_000_000:
                raise ValueError("Слишком большой распакованный документ")
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)[:16000]
    if not data.startswith(b"%PDF"):
        raise ValueError("Неверная сигнатура PDF")
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted or len(reader.pages) > 30:
        raise ValueError("PDF зашифрован или содержит больше 30 страниц")
    return "\n".join(page.extract_text() or "" for page in reader.pages)[:16000]


async def extract(data: bytes, filename: str, limit: int) -> str:
    # Parsing is off the event loop. Container resource limits complement input bounds.
    return await asyncio.wait_for(asyncio.to_thread(extract_sync, data, filename, limit), timeout=30)
