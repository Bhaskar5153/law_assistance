import hashlib
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import Settings, get_settings
from app.models import ChatRequest, ChatResponse, UploadResponse
from app.rag.services import LegalRagService

router = APIRouter(prefix="/api")


def rag(settings: Settings = Depends(get_settings)) -> LegalRagService:
    return LegalRagService(settings)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, service: LegalRagService = Depends(rag)) -> ChatResponse:
    return service.answer(request)


@router.post("/cases", response_model=UploadResponse)
async def upload_case(file: UploadFile = File(...), service: LegalRagService = Depends(rag),
                      settings: Settings = Depends(get_settings)) -> UploadResponse:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(415, "Only PDF files are accepted")
    raw = await file.read()
    if not raw or len(raw) > 50 * 1024 * 1024:
        raise HTTPException(413, "PDF must be between 1 byte and 50 MB")
    session_id, digest = uuid.uuid4().hex, hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.pdf"
        path.write_bytes(raw)
        try:
            pages = PyPDFLoader(str(path)).load()
        except Exception as exc:
            raise HTTPException(422, "The PDF could not be parsed") from exc
    splitter = RecursiveCharacterTextSplitter(chunk_size=settings.chunk_size,
                                               chunk_overlap=settings.chunk_overlap)
    docs = splitter.split_documents(pages)
    for doc in docs:
        doc.metadata.update(source=file.filename or "uploaded.pdf", sha256=digest)
        doc.metadata["page"] = int(doc.metadata.get("page", 0)) + 1
    ids = [hashlib.sha256(f"{session_id}:{i}:{d.page_content}".encode()).hexdigest()
           for i, d in enumerate(docs)]
    service.store(f"upload-{session_id}").add_documents(docs, ids=ids)
    return UploadResponse(session_id=session_id, filename=file.filename or "uploaded.pdf",
                          pages=len(pages), sha256=digest)