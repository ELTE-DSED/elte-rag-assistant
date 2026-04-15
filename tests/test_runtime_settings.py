import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.runtime_settings import RuntimeSettingsStore, compose_system_prompt


def test_runtime_settings_migrates_legacy_embedding_fields(tmp_path):
    path = tmp_path / "runtime-settings.json"
    path.write_text(
        json.dumps(
            {
                "generator_model": "g",
                "reranker_model": "r",
                "system_prompt": "",
                "embedding_provider": "local",
                "embedding_model": "all-MiniLM-L6-v2",
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    store = RuntimeSettingsStore(path)
    settings = store.get()
    assert settings.embedding_profile == "local_minilm"
    assert settings.embedding_provider == "local"
    assert settings.embedding_model == "all-MiniLM-L6-v2"


def test_runtime_settings_updates_profile_and_model_consistently(tmp_path):
    store = RuntimeSettingsStore(tmp_path / "runtime-settings.json")
    updated = store.update(embedding_profile="openai_small")
    assert updated.embedding_profile == "openai_small"
    assert updated.embedding_provider == "openrouter"
    assert updated.embedding_model == "openai/text-embedding-3-small"


def test_runtime_settings_persists_llm_reranker_mode(tmp_path):
    path = tmp_path / "runtime-settings.json"
    store = RuntimeSettingsStore(path)
    updated = store.update(reranker_mode="llm")
    assert updated.reranker_mode == "llm"

    reloaded = RuntimeSettingsStore(path).get()
    assert reloaded.reranker_mode == "llm"


def test_runtime_settings_rejects_removed_local_mpnet_profile(tmp_path):
    store = RuntimeSettingsStore(tmp_path / "runtime-settings.json")
    with pytest.raises(ValueError, match="local_mpnet"):
        store.update(embedding_profile="local_mpnet")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("date_text", "expected_term"),
    [
        ("2026-01-20T10:00:00+01:00", "Autumn/Fall/1st semester"),
        ("2026-01-21T10:00:00+01:00", "Spring/2nd semester"),
        ("2026-07-31T10:00:00+02:00", "Spring/2nd semester"),
        ("2026-08-01T10:00:00+02:00", "Autumn/Fall/1st semester"),
    ],
)
def test_compose_system_prompt_uses_expected_term_boundaries(date_text, expected_term):
    mocked_now = datetime.fromisoformat(date_text).astimezone(ZoneInfo("Europe/Budapest"))
    prompt = compose_system_prompt("", now=mocked_now)
    assert f"- current_date: {mocked_now.strftime('%Y-%m-%d')}" in prompt
    assert f"- weekday: {mocked_now.strftime('%A')}" in prompt
    assert f"- current_term: {expected_term}" in prompt


def test_compose_system_prompt_includes_temporal_block_with_additional_instructions():
    mocked_now = datetime(2026, 3, 1, 11, 0, tzinfo=ZoneInfo("Europe/Budapest"))
    prompt = compose_system_prompt("Use concise bullets.", now=mocked_now)
    assert "Runtime temporal context (Europe/Budapest):" in prompt
    assert "- current_date: 2026-03-01" in prompt
    assert "- current_term: Spring/2nd semester" in prompt
    assert "Additional runtime instructions for this deployment:" in prompt
    assert "Use concise bullets." in prompt
