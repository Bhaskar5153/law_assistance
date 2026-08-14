import hashlib
import json
import tempfile
import time
from pathlib import Path

from google.cloud import storage
from langchain_community.document_loaders import PyPDFLoader
# from langchain_google_vertexai import VertexAIEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
#  Use [`GoogleGenerativeAIEmbeddings`][langchain_google_genai.GoogleGenerativeAIEmbeddings]
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter #, TokenTextSplitter, CharacterTextSplitter

from app.config import Settings
from app.ingestion.schema import canonicalize_pages, parse_case_metadata


def stable_split(items: list[dict], holdout_count: int) -> tuple[list[dict], list[dict]]:
    ordered = sorted(items, key=lambda x: (x["sha256"], x["uri"]))
    count = min(max(holdout_count, 0), len(ordered))
    return ordered[count:], ordered[:count]


class IngestionPipeline:
    def __init__(self, settings: Settings):
        self.s = settings
        self.client = storage.Client(project=self.s.gcp_project_id)

    def inventory(self) -> list[dict]:
        bucket = self.client.bucket(self.s.gcs_bucket)
        items = []
        for blob in self.client.list_blobs(bucket, prefix=self.s.gcs_prefix.rstrip("/") + "/"):
            if blob.name.lower().endswith(".pdf"):
                blob.reload()
                # Hash actual bytes so manifests, canonical records, and evaluation IDs agree.
                digest = hashlib.sha256(blob.download_as_bytes()).hexdigest()
                items.append({"uri": f"gs://{self.s.gcs_bucket}/{blob.name}", "name": blob.name,
                              "sha256": digest, "size": blob.size, "generation": blob.generation})
        return items

    def _write_jsonl(self, path: Path, records) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _add_documents_with_retry(self, vectorstore, docs, ids) -> None:
        """Add documents at a quota-safe pace and retry transient Vertex AI 429s."""
        batch_size = max(1, self.s.embedding_batch_size)
        attempts = max(1, self.s.embedding_retry_attempts)
        for start in range(0, len(docs), batch_size):
            batch_docs = docs[start:start + batch_size]
            batch_ids = ids[start:start + batch_size]
            for attempt in range(attempts):
                try:
                    vectorstore.add_documents(batch_docs, ids=batch_ids)
                    break
                except Exception as exc:
                    message = str(exc)
                    quota_error = "RESOURCE_EXHAUSTED" in message or "429" in message
                    if not quota_error or attempt == attempts - 1:
                        raise
                    delay = self.s.embedding_retry_delay_seconds * (2 ** attempt)
                    print(
                        f"Vertex AI embedding quota reached; retrying batch "
                        f"{start // batch_size + 1} in {delay:g}s "
                        f"({attempt + 1}/{attempts - 1})..."
                    )
                    time.sleep(delay)

    def run(self) -> dict:
        inventory = self.inventory()
        train, holdout = stable_split(inventory, self.s.holdout_count)
        manifests = self.s.data_dir / "manifests"
        self._write_jsonl(manifests / "train.jsonl", train)
        self._write_jsonl(manifests / "holdout.jsonl", holdout)

        embeddings = GoogleGenerativeAIEmbeddings(model=self.s.embedding_model,
                                        project=self.s.gcp_project_id, location=self.s.gcp_location, vertexai=True)
        splitter = RecursiveCharacterTextSplitter(chunk_size=self.s.chunk_size,
                                                  chunk_overlap=self.s.chunk_overlap)
        canonical_dir = self.s.data_dir / "canonical"
        canonical_dir.mkdir(parents=True, exist_ok=True)
        for split_name, split_items in (("train", train), ("holdout", holdout)):
            vectorstore = Chroma(collection_name=f"supreme-court-{split_name}",
                                 embedding_function=embeddings,
                                 persist_directory=str(self.s.data_dir / "chroma"))
            with (canonical_dir / f"{split_name}_pages.jsonl").open("w", encoding="utf-8") as output:
                for item in split_items:
                    self._ingest_item(item, split_name, output, vectorstore, splitter)
        return {"total": len(inventory), "train": len(train), "holdout": len(holdout)}

    def _ingest_item(self, item, split_name, output, vectorstore, splitter) -> None:
        blob = storage.Blob.from_string(item["uri"], client=self.client)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.pdf"
            blob.download_to_filename(path)
            raw = path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            if sha != item["sha256"]:
                raise ValueError(f"GCS object changed after inventory: {item['uri']}")
            pages = PyPDFLoader(str(path)).load()
            meta = parse_case_metadata("\n".join(x.page_content for x in pages[:2]), item["uri"], sha)
            records = canonicalize_pages(pages, meta)
            for record in records:
                output.write(record.model_dump_json() + "\n")
            docs = splitter.create_documents(
                [record.text for record in records],
                metadatas=[{"source": item["uri"], "page": record.page_number,
                            "sha256": sha, "split": split_name} for record in records],
            )
            ids = [hashlib.sha256(f"{sha}:{d.metadata['page']}:{i}:{d.page_content}".encode()).hexdigest()
                   for i, d in enumerate(docs)]
            self._add_documents_with_retry(vectorstore, docs, ids)
