import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from app.rag_chain import RAGOutput
from app.runtime_settings import RuntimeSettings
from scripts.temp_gold_server import (
    GoldPreviewService,
    _resolve_openai_large_index_path,
    create_app,
)


class _FakeRetriever:
    def __init__(self, docs):
        self._docs = docs

    def invoke(self, _query):
        return list(self._docs)


class _FakeVectorStore:
    def __init__(self, docs):
        self._docs = docs
        self.docstore = type("DocStore", (), {"_dict": {str(i): doc for i, doc in enumerate(docs)}})()

    def as_retriever(self, **_kwargs):
        return _FakeRetriever(self._docs)


def _runtime_settings() -> RuntimeSettings:
    return RuntimeSettings(
        generator_model="mock-model",
        reranker_model="mock-reranker",
        system_prompt="",
        embedding_profile="openai_large",
        pipeline_mode="enhanced_v2",
        reranker_mode="off",
        chunk_profile="standard",
        parser_profile="docling_v1",
        max_chunks_per_doc=3,
        embedding_provider="openrouter",
        embedding_model="openai/text-embedding-3-large",
    )


def _service_with_docs(docs: list[Document]) -> GoldPreviewService:
    return GoldPreviewService(
        db=_FakeVectorStore(docs),  # type: ignore[arg-type]
        bm25_retriever=None,
        news_db=None,
        runtime_settings=_runtime_settings(),
        index_path=Path("data/indexes/demo__openai_large"),
        snapshot_manifest={"snapshot_id": "demo", "corpus_hash": "abcd1234"},
    )


@pytest.mark.asyncio
async def test_preview_query_returns_ranked_retrieval_and_answer_citations_subset():
    docs = [
        Document(
            page_content="Thesis deadline is April 15.",
            metadata={"source": "thesis_rules.pdf", "title": "Thesis Rules", "page": 3},
        ),
        Document(
            page_content="Late submission requires approval.",
            metadata={"source": "thesis_rules.pdf", "title": "Thesis Rules", "page": 4},
        ),
    ]
    service = _service_with_docs(docs)
    app = create_app(service=service)

    async def _structured_output(_input):
        return RAGOutput(
            reasoning="used context chunks",
            answer="Deadline is April 15. [C1]",
            cited_chunk_ids=["C1"],
            confidence="high",
        )

    fake_llm = type("FakeLLM", (), {"model_name": "fake-model"})()
    fake_llm.with_structured_output = lambda _schema, **_kwargs: RunnableLambda(_structured_output)

    with (
        patch("app.rag_chain.settings.retrieval_hybrid", False),
        patch("app.rag_chain.settings.retrieval_k", 2),
        patch("app.rag_chain.settings.retrieval_fetch_k", 4),
        patch("app.rag_chain.settings.default_pipeline_mode", "enhanced_v2"),
        patch("app.rag_chain.settings.default_reranker_mode", "off"),
        patch("app.rag_chain.get_llm", return_value=fake_llm),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.post("/preview/query", json={"query": "When is deadline?"})
        assert response.status_code == 200
        payload = response.json()

    final_ranked = payload["retrieval"]["stages"]["final_ranked"]
    assert final_ranked
    assert [item["rank"] for item in final_ranked] == [1, 2]
    required_fields = {"source", "document", "page", "snippet", "content", "rank", "citation_id"}
    for row in final_ranked:
        assert required_fields.issubset(set(row.keys()))

    cited_sources = payload["draft_answer"]["cited_sources"]
    final_ids = {row["citation_id"] for row in final_ranked}
    cited_ids = {row["citation_id"] for row in cited_sources}
    assert cited_ids.issubset(final_ids)


def test_preview_batch_writes_deterministic_output_and_continues_on_failure(tmp_path):
    docs = [
        Document(
            page_content="Exam period dates are in semester calendar.",
            metadata={"source": "exam_rules.pdf", "title": "Exam Rules", "page": 2},
        )
    ]

    class _FlakyService(GoldPreviewService):
        async def preview_query(self, request):
            if "fail" in request.query.lower():
                raise RuntimeError("intentional failure")
            return await super().preview_query(request)

    service = _FlakyService(
        db=_FakeVectorStore(docs),  # type: ignore[arg-type]
        bm25_retriever=None,
        news_db=None,
        runtime_settings=_runtime_settings(),
        index_path=Path("data/indexes/demo__openai_large"),
        snapshot_manifest={"snapshot_id": "demo", "corpus_hash": "abcd1234"},
    )
    app = create_app(service=service)

    single_turn_path = tmp_path / "questions.json"
    single_turn_path.write_text(
        '{"questions":["ok question","fail question"]}',
        encoding="utf-8",
    )
    multi_turn_path = tmp_path / "multi.json"
    multi_turn_path.write_text(
        '{"scenarios":[{"id":"mt-1","query":"ok multi","history":[]}]}',
        encoding="utf-8",
    )
    output_path = tmp_path / "gold_candidates.json"

    async def _structured_output(_input):
        return RAGOutput(
            reasoning="context based",
            answer="Answer from [C1]",
            cited_chunk_ids=["C1"],
            confidence="medium",
        )

    fake_llm = type("FakeLLM", (), {"model_name": "fake-model"})()
    fake_llm.with_structured_output = lambda _schema, **_kwargs: RunnableLambda(_structured_output)

    with (
        patch("app.rag_chain.settings.retrieval_hybrid", False),
        patch("app.rag_chain.settings.retrieval_k", 2),
        patch("app.rag_chain.settings.retrieval_fetch_k", 4),
        patch("app.rag_chain.settings.default_pipeline_mode", "enhanced_v2"),
        patch("app.rag_chain.settings.default_reranker_mode", "off"),
        patch("app.rag_chain.get_llm", return_value=fake_llm),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.post(
            "/preview/batch",
            json={
                "single_turn_path": str(single_turn_path),
                "multi_turn_path": str(multi_turn_path),
                "output_path": str(output_path),
            },
        )
        assert response.status_code == 200
        payload = response.json()

    assert payload["total_rows"] == 3
    assert payload["successful_rows"] == 2
    assert payload["failed_rows"] == 1
    assert output_path.exists()

    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert [row["item_id"] for row in artifact["rows"]] == [
        "single-001",
        "single-002",
        "multi-mt-1",
    ]
    assert artifact["rows"][1]["status"] == "error"


def test_resolve_openai_large_index_path_fails_fast_with_actionable_error():
    with patch("scripts.temp_gold_server.resolve_active_index_path", return_value=None):
        with pytest.raises(RuntimeError, match="No active snapshot found for embedding_profile='openai_large'"):
            _resolve_openai_large_index_path()
