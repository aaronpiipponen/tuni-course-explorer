"""Inference provenance identity tests."""

from __future__ import annotations

import pytest

from course_explorer.config import (
    InferenceRerankSettings,
    InferenceSettings,
    TranslationSettings,
    load_inference_settings,
)
from tests.config._support import set_inference_environment, set_translation_environment


def test_inference_settings_require_two_key_mix_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two-key MIX and exact translation/model/runtime/rerank identities derive."""
    set_inference_environment(monkeypatch)
    settings = InferenceSettings()
    first, second = settings.inference_local_variants
    assert (first.port, first.context_size) == (18140, 131072)
    assert (second.port, second.context_size) == (18160, 163840)
    assert first.mtp_draft_n_max == 2
    assert second.mtp_draft_n_max is None
    assert settings.primary_model_identity == (
        "Qwen/Qwen3.8-27B-FP8@017b9c7af6b5689d5dd426a76e0bc077eb5ca20a"
        ";artifact=vmarcelo/Qwen3.8-27B-MIX_GGUF"
        "@f922f9d9bbe67ede1c49e364d71737b8f067e49b/Qwen3.8-27B-IQ3-MIX.gguf"
        ";quant=IQ3_MIX"
        ";sha256=3089d39401e60551a03e0858d775d6b33f966f6e6513f31f75a011cfc8f56309"
    )
    assert settings.local_runtime_identity(first) == (
        "llama.cpp@4ff829ec2e2f526aa6afba529eebbfb3ef1f95ec"
        ";alias=qwen3.8-27b-iq3-mix-128k-mtp"
        ";context=131072"
        ";parallel=1"
        ";gpu_layers=all"
        ";kv_cache=q4_0"
        ";flash_attention=on"
        ";batch=256"
        ";ubatch=256"
        ";speculative=draft-mtp,ngram-mod"
        ";mtp_draft_n_max=2"
        ";threads=8"
        ";threads_batch=16"
        ";max_tokens=8192"
        ";generation_attempts=unbounded"
        ";initial_temperature=0.0"
        ";first_attempt_scope=cycle-target-calculation"
        ";retry_temperature=0.3"
        ";seed_base=0"
        ";seed_schedule=canonical-target-counter-calculation-first-v1"
        ";retry_backoff_seconds=1.0"
        ";retry_max_backoff_seconds=10.0"
        ";retry_poll_seconds=0.1"
        ';chat_template_kwargs={"enable_thinking":false}'
    )
    # The local retry policy is recorded in the local identity only. The deterministic cross-encoder
    # identity is unaffected by it.
    assert load_inference_settings() == settings

    rerank = InferenceRerankSettings()
    assert rerank.rerank_model_identity == (
        "BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
        ";artifact=gpustack/bge-reranker-v2-m3-GGUF"
        "@3093af03b1a635e67b084b1d8c03c5f5e020fd05/bge-reranker-v2-m3-Q8_0.gguf"
        ";quant=Q8_0"
        ";sha256=a43c7c9b11a4c1517e5bf95151960e1621d1b72f7a493364b01e386cf1aaa1d3"
    )
    assert rerank.rerank_runtime_identity == (
        "llama.cpp@4ff829ec2e2f526aa6afba529eebbfb3ef1f95ec"
        ";alias=bge-reranker-v2-m3-q8"
        ";context=8192"
        ";host=127.0.0.1"
        ";port=18083"
        ";embedding=true"
        ";pooling=rank"
        ";reranking=true"
        ";batch=2048"
        ";ubatch=2048"
        ";timeout=60"
    )

    # A changed retry temperature changes the local execution identity but never the rerank one.
    changed = settings.model_copy(update={"inference_retry_temperature": 0.7})
    assert changed.local_runtime_identity(first) != settings.local_runtime_identity(first)
    assert InferenceRerankSettings().rerank_runtime_identity == rerank.rerank_runtime_identity

    set_translation_environment(monkeypatch)
    assert TranslationSettings().provenance_model == (
        "google/translategemma-12b-it@d1b225e1caa17f1ddc7e62065d8637d0923f34e2"
        ";Q5_K_M;sha256:6a4cd9eae938fd869ceeb310ed9c8de2f44bacb0c2d79541a4f4dbf2b201c6da"
    )
