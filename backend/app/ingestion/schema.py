import base64
import re

from langchain_core.documents import Document

from app.models import CanonicalPage, CaseMetadata


FIELD_PATTERNS = {
    "petitioner": re.compile(r"PETITIONER:\s*(.+?)(?:\n\s*Vs\.)", re.S | re.I),
    "respondent": re.compile(r"RESPONDENT:\s*(.*?)(?:\nDATE OF JUDGMENT)", re.S | re.I),
    "judgment_date": re.compile(r"DATE OF JUDGMENT\s*([0-9/.-]+)", re.I),
}


def _clean(value: str | None) -> str | None:
    return re.sub(r"\s+", " ", value).strip(" :") if value else None


def parse_case_metadata(first_pages: str, source_uri: str, sha256: str) -> CaseMetadata:
    values = {key: _clean(pattern.search(first_pages).group(1)) if pattern.search(first_pages) else None
              for key, pattern in FIELD_PATTERNS.items()}
    bench_block = re.search(r"BENCH:\s*(.*?)(?:\nCITATION:)", first_pages, re.S | re.I)
    citation_block = re.search(r"CITATION:\s*(.*?)(?:\nACT:)", first_pages, re.S | re.I)
    benches = re.findall(r"[A-Z][A-Z .,'()-]{3,}", bench_block.group(1)) if bench_block else []
    citations = [_clean(x) for x in (citation_block.group(1).splitlines() if citation_block else [])]
    title = " v. ".join(x for x in [values["petitioner"], values["respondent"]] if x)
    return CaseMetadata(
        title=title or None,
        petitioner=values["petitioner"], respondent=values["respondent"],
        judgment_date=values["judgment_date"], bench=[x for x in map(_clean, benches) if x],
        citations=[x for x in citations if x], source_uri=source_uri, document_sha256=sha256,
    )


def canonicalize_pages(pages: list[Document], metadata: CaseMetadata) -> list[CanonicalPage]:
    result = []
    for index, page in enumerate(pages, start=1):
        text = re.sub(r"[ \t]+", " ", page.page_content).strip()
        paragraph_ids = re.findall(r"(?m)^\s*(\d{1,3})[.)]", text)
        result.append(CanonicalPage(
            case=metadata, page_number=index, paragraph_ids=paragraph_ids, text=text,
            text_base64=base64.b64encode(text.encode("utf-8")).decode("ascii"),
        ))
    return result