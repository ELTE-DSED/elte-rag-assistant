import json

import httpx

from app.document_sync import run_documents_sync


def _typesense_response(
    *,
    global_hits: list[dict],
    article_hits: list[dict],
    found_global: int | None = None,
    found_article: int | None = None,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "results": [
                {
                    "found": found_global if found_global is not None else len(global_hits),
                    "hits": global_hits,
                },
                {
                    "found": found_article if found_article is not None else len(article_hits),
                    "hits": article_hits,
                },
            ]
        },
    )


def test_documents_sync_extracts_and_deduplicates_urls(tmp_path):
    endpoint = "https://typesense.elte.hu/multi_search"

    global_hit = {
        "document": {
            "id": "entity:node-1:en",
            "title": "Global PDF",
            "entity_url_domain": "https://www.inf.elte.hu/files/final.pdf",
            "content_type": "global_document",
            "created": 1772022012,
        }
    }
    article_hit = {
        "document": {
            "id": "entity:node-2:en",
            "title": "Article With Links",
            "entity_url_domain": "https://www.inf.elte.hu/en/node/2",
            "content_type": "article",
            "created": 1772022013,
            "processed_text": (
                '<p><a href="https://www.inf.elte.hu/files/redirect.pdf">Redirect</a></p>'
                '<p><a href="https://www.elte.hu/files/form.docx">DOCX</a></p>'
                '<p><a href="https://example.com/outside.pdf">Outside</a></p>'
                '<p><a href="http://https//www.elte.hu/bad.pdf">Malformed</a></p>'
                '<p><a href="https://www.inf.elte.hu/files/final.pdf">Duplicate</a></p>'
            ),
        }
    }

    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and url.startswith(endpoint):
            payload = json.loads(request.content.decode("utf-8"))
            page = payload["searches"][0]["page"]
            if page == 1:
                return _typesense_response(
                    global_hits=[global_hit],
                    article_hits=[article_hit],
                )
            return _typesense_response(global_hits=[], article_hits=[])

        if url == "https://www.inf.elte.hu/files/redirect.pdf":
            return httpx.Response(
                302,
                headers={"Location": "https://www.inf.elte.hu/files/final.pdf"},
            )
        if url == "https://www.inf.elte.hu/files/final.pdf":
            return httpx.Response(200, content=b"%PDF-1.4 sample", headers={"Content-Type": "application/pdf"})
        if url == "https://www.elte.hu/files/form.docx":
            return httpx.Response(
                200,
                content=b"PK\x03\x04docx",
                headers={
                    "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                },
            )

        raise AssertionError(f"Unexpected request: {request.method} {url}")

    client = httpx.Client(transport=httpx.MockTransport(_handler), follow_redirects=True)

    result = run_documents_sync(
        download_dir=tmp_path / "raw",
        state_path=tmp_path / "state.json",
        endpoint=endpoint,
        api_key="demo-key",
        client=client,
    )

    assert result["discovered_url_count"] == 5
    assert result["blocked_domain_count"] == 2
    assert result["eligible_url_count"] == 3
    assert result["duplicate_url_count"] == 1
    assert result["canonical_url_count"] == 2
    assert result["downloaded_count"] == 2
    assert result["downloaded_pdf_count"] == 1
    assert result["downloaded_docx_count"] == 1
    assert result["skipped_count"] == 0

    raw_files = list((tmp_path / "raw").iterdir())
    assert len(raw_files) == 2
    assert any(path.suffix == ".pdf" for path in raw_files)
    assert any(path.suffix == ".docx" for path in raw_files)

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert len(state["items"]) == 2

    final_pdf_entry = state["items"]["https://www.inf.elte.hu/files/final.pdf"]
    source_ref_ids = {item["record_id"] for item in final_pdf_entry["source_refs"]}
    assert source_ref_ids == {"entity:node-1:en", "entity:node-2:en"}


def test_documents_sync_skips_existing_and_redownloads_missing_file(tmp_path):
    endpoint = "https://typesense.elte.hu/multi_search"
    target_url = "https://www.inf.elte.hu/files/final.pdf"

    hit = {
        "document": {
            "id": "entity:node-100:en",
            "title": "Global PDF",
            "entity_url_domain": target_url,
            "content_type": "global_document",
            "created": 1772022012,
        }
    }

    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and url.startswith(endpoint):
            return _typesense_response(global_hits=[hit], article_hits=[])
        if url == target_url:
            return httpx.Response(200, content=b"%PDF-1.4 stable", headers={"Content-Type": "application/pdf"})
        raise AssertionError(f"Unexpected request: {request.method} {url}")

    client = httpx.Client(transport=httpx.MockTransport(_handler), follow_redirects=True)

    first = run_documents_sync(
        download_dir=tmp_path / "raw",
        state_path=tmp_path / "state.json",
        endpoint=endpoint,
        api_key="demo-key",
        client=client,
    )
    assert first["downloaded_count"] == 1
    assert first["skipped_count"] == 0

    second = run_documents_sync(
        download_dir=tmp_path / "raw",
        state_path=tmp_path / "state.json",
        endpoint=endpoint,
        api_key="demo-key",
        client=client,
    )
    assert second["downloaded_count"] == 0
    assert second["skipped_count"] == 1

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    file_name = state["items"][target_url]["file_name"]
    (tmp_path / "raw" / file_name).unlink()

    third = run_documents_sync(
        download_dir=tmp_path / "raw",
        state_path=tmp_path / "state.json",
        endpoint=endpoint,
        api_key="demo-key",
        client=client,
    )
    assert third["downloaded_count"] == 1
    assert third["skipped_count"] == 0


def test_documents_sync_tolerates_single_subsearch_error(tmp_path):
    endpoint = "https://typesense.elte.hu/multi_search"
    docx_url = "https://www.elte.hu/files/from-article.docx"

    article_hit = {
        "document": {
            "id": "entity:node-500:en",
            "title": "Article With DOCX",
            "entity_url_domain": "https://www.inf.elte.hu/en/node/500",
            "content_type": "article",
            "created": 1772022013,
            "processed_text": f'<p><a href="{docx_url}">DOCX</a></p>',
        }
    }

    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and url.startswith(endpoint):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"code": 404, "error": "global_document stream failed"},
                        {"found": 1, "hits": [article_hit]},
                    ]
                },
            )
        if url == docx_url:
            return httpx.Response(
                200,
                content=b"PK\x03\x04docx",
                headers={
                    "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {url}")

    client = httpx.Client(transport=httpx.MockTransport(_handler), follow_redirects=True)

    result = run_documents_sync(
        download_dir=tmp_path / "raw",
        state_path=tmp_path / "state.json",
        endpoint=endpoint,
        api_key="demo-key",
        client=client,
    )

    assert result["downloaded_count"] == 1
    assert result["downloaded_docx_count"] == 1
