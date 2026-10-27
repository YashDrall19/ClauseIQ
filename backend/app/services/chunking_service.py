from dataclasses import asdict, dataclass
import re
from uuid import uuid4

from app.config import get_settings
from app.services.document_service import PageText


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    page: int
    text: str
    section_title: str | None = None


def chunk_pages(pages: list[PageText]) -> list[TextChunk]:
    settings = get_settings()
    chunks: list[TextChunk] = []
    for page in pages:
        words = page.text.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            end = min(start + settings.chunk_words, len(words))
            text = " ".join(words[start:end])
            section = None
            if start == 0:
                heading = re.search(r"(?m)^\s*(?:\d+(?:\.\d+)*[.)]?\s+)?([A-Z][A-Z0-9 ,&/()'-]{3,100})\s*$", page.text)
                if heading:
                    section = heading.group(1).strip()
            chunks.append(TextChunk(str(uuid4()), page.page, text, section))
            if end == len(words):
                break
            start = max(end - settings.chunk_overlap_words, start + 1)
    return chunks


def chunk_to_dict(chunk: TextChunk) -> dict[str, str | int | None]:
    return asdict(chunk)
