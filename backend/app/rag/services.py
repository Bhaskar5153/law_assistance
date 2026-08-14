import re

from langchain_chroma import Chroma
from langchain_core.documents import Document
# from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
# [`ChatGoogleGenerativeAI`][langchain_google_genai.ChatGoogleGenerativeAI]

from app.config import Settings
from app.models import ChatRequest, ChatResponse, Citation
from app.rag.prompts import legal_prompt

# from google import genai

# client = genai.Client(project=project_id)

# response = client.generate_content(
#     content=prompt,
#     temperatute=0.1
# )


class LegalRagService:
    def __init__(self, settings: Settings):
        self.s = settings
        self.embeddings = GoogleGenerativeAIEmbeddings(model=settings.embedding_model,
                                             project=settings.gcp_project_id,
                                             location=settings.gcp_location,
                                             vertexai=True)
        llm_options = {
            "project": settings.gcp_project_id,
            "location": settings.gcp_location,
            "vertexai": True,
            "temperature": 0.15,
            "max_retries": 3,
        }
        self.llm = ChatGoogleGenerativeAI(model=settings.gemini_model, **llm_options)
        self.fallback_llm = ChatGoogleGenerativeAI(
            model=settings.gemini_fallback_model, **llm_options
        )

    def _invoke_llm(self, message):
        try:
            return self.llm.invoke(message)
        except Exception as exc:
            error = str(exc)
            quota_error = "RESOURCE_EXHAUSTED" in error or "429" in error
            if not quota_error:
                raise
            print(
                f"Quota exhausted for {self.s.gemini_model}; "
                f"falling back to {self.s.gemini_fallback_model}."
            )
            return self.fallback_llm.invoke(message)

    def store(self, collection: str = "supreme-court-train") -> Chroma:
        return Chroma(collection_name=collection, embedding_function=self.embeddings,
                      persist_directory=str(self.s.data_dir / "chroma"))

    @staticmethod
    def _document_key(doc: Document) -> tuple[str, int, str]:
        return (str(doc.metadata.get("source", "")), int(doc.metadata.get("page", 0)),
                doc.page_content)

    def _uploaded_case_docs(self, store: Chroma, question: str) -> list[Document]:
        """Combine exact and semantic matches and retain the case caption page."""
        semantic = store.similarity_search(question, k=self.s.retrieval_k)
        stored = store.get(include=["documents", "metadatas"])
        all_docs = [Document(page_content=text, metadata=metadata or {})
                    for text, metadata in zip(stored.get("documents", []),
                                              stored.get("metadatas", []))]
        terms = {term for term in re.findall(r"[a-z0-9]+", question.lower())
                 if len(term) > 2}
        lexical = sorted(
            all_docs,
            key=lambda doc: sum(doc.page_content.lower().count(term) for term in terms),
            reverse=True,
        )
        opening = sorted(all_docs, key=lambda doc: int(doc.metadata.get("page", 0)))[:1]
        selected, seen = [], set()
        for doc in opening + lexical[:self.s.retrieval_k] + semantic:
            key = self._document_key(doc)
            if key not in seen:
                selected.append(doc)
                seen.add(key)
            if len(selected) >= self.s.retrieval_k:
                break
        return selected

    def answer(self, request: ChatRequest, collections: list[str] | None = None) -> ChatResponse:
        if request.session_id:
            store = self.store(f"upload-{request.session_id}")
            docs = self._uploaded_case_docs(store, request.question)
        else:
            stores = [self.store(name) for name in (collections or ["supreme-court-train"])]
            docs = []
            for store in stores:
                docs.extend(store.similarity_search(request.question, k=self.s.retrieval_k))
            docs = docs[:self.s.retrieval_k]
        if not docs:
            return ChatResponse(answer="No indexed evidence was found. Upload a case or run ingestion first.", citations=[])
        context, citations = [], []
        for index, doc in enumerate(docs, start=1):
            page = int(doc.metadata.get("page", 0))
            source = str(doc.metadata.get("source", "unknown"))
            context.append(f"[S{index} p.{page}] {source}\n{doc.page_content}")
            citations.append(Citation(source=source, page=page, excerpt=doc.page_content[:280]))
        recent = request.conversation[-6:]
        conversation = "\n".join(
            f"{item.get('role', 'user')}: {item.get('text', '')[:1000]}" for item in recent
        ) or "No prior conversation."
        message = legal_prompt().invoke({"side": request.side.value, "question": request.question,
                                         "conversation": conversation,
                                         "context": "\n\n".join(context)})
        return ChatResponse(answer=str(self._invoke_llm(message).content), citations=citations)
