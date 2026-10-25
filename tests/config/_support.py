"""Shared fixtures and explicit-environment helpers for the config settings tests.

Every family dictionary is projected from the shared composed public mapping by the real settings
classes' validation aliases, so the defaults live in exactly one place. The live
``set_*_environment`` wrappers below delegate to one clear/set loop and own the process environment
for the settings family under test.
"""

from __future__ import annotations

import pytest
from pydantic_settings import BaseSettings

from course_explorer.config import (
    AdministrativeDatasetSettings,
    AdminWebSettings,
    AdmissionSettings,
    CaptureSettings,
    DatabaseSettings,
    EmbeddingSettings,
    InferenceContextSettings,
    InferenceControllerSettings,
    InferenceRerankInputSettings,
    InferenceRerankSettings,
    InferenceSelectionSettings,
    InferenceSettings,
    KoriSettings,
    LocalLifecycleSettings,
    NormalizationSettings,
    SearchSettings,
    TranslationControllerSettings,
    TranslationSettings,
    WebSettings,
    WorkerConnectionSettings,
    WorkerGpuRebootSettings,
    WorkerRuntimeSettings,
    WorkerSetupSettings,
)
from tests.support import (
    REPO_ROOT,
    public_environment,
)

__all__ = ["REPO_ROOT"]

MACHINE_LOCAL_KEYS = {
    "TRANSLATION_CONTROLLER_SSH_TARGET",
    "TRANSLATION_CONTROLLER_WSL_DISTRIBUTION",
    "TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT",
    "ADMIN_SITE_WEB_SERVICE_UNIT",
    "ADMIN_SITE_ADMIN_SERVICE_UNIT",
    "ADMIN_SITE_WEB_SERVICE_SCOPE",
}
MACHINE_TEMPLATE_VALUES = {
    "TRANSLATION_CONTROLLER_SSH_TARGET": "replace-with-ssh-target",
    "TRANSLATION_CONTROLLER_WSL_DISTRIBUTION": "replace-with-wsl-distribution",
    "TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT": "/home/replace-with-user/tuni-course-explorer",
    "ADMIN_SITE_WEB_SERVICE_UNIT": "replace-with-web.service",
    "ADMIN_SITE_ADMIN_SERVICE_UNIT": "replace-with-admin.service",
    "ADMIN_SITE_WEB_SERVICE_SCOPE": "user",
}
LOCAL_TEMPLATE_KEYS = {"POSTGRES_PASSWORD"} | MACHINE_LOCAL_KEYS


def _keys(settings_type: type[BaseSettings]) -> dict[str, str]:
    """Project the composed public mapping by one settings class's required/aliased fields.

    Fields with no validation alias and a default are code-owned defaults, not missing public
    config, so they are omitted rather than looked up in the composed environment.
    """
    environment = public_environment()
    values: dict[str, str] = {}
    for name, field in settings_type.model_fields.items():
        if field.validation_alias is None and not field.is_required():
            continue
        alias = field.validation_alias
        alias = alias if isinstance(alias, str) else name
        values[alias] = environment[alias]
    return values


POSTGRES_KEYS = {
    **_keys(DatabaseSettings),
    "POSTGRES_PASSWORD": "local-password",
    "SELECTED_DATASET_ENABLED": "0",
}
ADMIN_DATASET_KEYS = {
    key: value
    for key, value in _keys(AdministrativeDatasetSettings).items()
    if key != "ADMIN_STATE_ROOT"
}
KORI_KEYS = _keys(KoriSettings)
CAPTURE_KEYS = _keys(CaptureSettings)
NORMALIZATION_KEYS = _keys(NormalizationSettings)
EMBEDDING_KEYS = _keys(EmbeddingSettings)
LOCAL_LIFECYCLE_KEYS = _keys(LocalLifecycleSettings)
SEARCH_KEYS = _keys(SearchSettings)
TRANSLATION_KEYS = _keys(TranslationSettings)
WORKER_CONNECTION_KEYS = _keys(WorkerConnectionSettings)
WORKER_SETUP_KEYS = _keys(WorkerSetupSettings)
WORKER_RUNTIME_KEYS = _keys(WorkerRuntimeSettings)
WORKER_GPU_REBOOT_KEYS = _keys(WorkerGpuRebootSettings)
WEB_KEYS = _keys(WebSettings)
ADMISSION_KEYS = _keys(AdmissionSettings)
ADMIN_WEB_KEYS = _keys(AdminWebSettings)
TRANSLATION_CONTROLLER_KEYS = {
    **_keys(TranslationControllerSettings),
    **WORKER_GPU_REBOOT_KEYS,
}
INFERENCE_KEYS = {
    key: value for key, value in _keys(InferenceSettings).items() if key not in WORKER_RUNTIME_KEYS
}
INFERENCE_CONTEXT_KEYS = _keys(InferenceContextSettings)
INFERENCE_SELECTION_KEYS = _keys(InferenceSelectionSettings)
INFERENCE_RERANK_INPUT_KEYS = _keys(InferenceRerankInputSettings)
INFERENCE_CONTROLLER_KEYS = {
    key: value
    for key, value in _keys(InferenceControllerSettings).items()
    if key not in WORKER_CONNECTION_KEYS
}
INFERENCE_RERANK_KEYS = {
    key: value
    for key, value in _keys(InferenceRerankSettings).items()
    if key != "INFERENCE_RUNTIME_REVISION"
}
INFERENCE_ALL_KEYS = {
    **INFERENCE_KEYS,
    **INFERENCE_CONTEXT_KEYS,
    **INFERENCE_SELECTION_KEYS,
    **INFERENCE_RERANK_KEYS,
    **INFERENCE_RERANK_INPUT_KEYS,
    **WORKER_RUNTIME_KEYS,
    **INFERENCE_CONTROLLER_KEYS,
}

FIXTURE_VALUES: dict[str, str] = {
    **POSTGRES_KEYS,
    **KORI_KEYS,
    **CAPTURE_KEYS,
    **LOCAL_LIFECYCLE_KEYS,
    **NORMALIZATION_KEYS,
    **EMBEDDING_KEYS,
    **SEARCH_KEYS,
    **TRANSLATION_KEYS,
    **TRANSLATION_CONTROLLER_KEYS,
    **WORKER_SETUP_KEYS,
    **ADMIN_DATASET_KEYS,
    **INFERENCE_KEYS,
    **INFERENCE_CONTEXT_KEYS,
    **INFERENCE_SELECTION_KEYS,
    **INFERENCE_RERANK_KEYS,
    **INFERENCE_RERANK_INPUT_KEYS,
    **WORKER_RUNTIME_KEYS,
    **INFERENCE_CONTROLLER_KEYS,
    **WEB_KEYS,
    **ADMISSION_KEYS,
    **ADMIN_WEB_KEYS,
}
PUBLIC_ALIASES = FIXTURE_VALUES.keys() - LOCAL_TEMPLATE_KEYS


def _set_environment(
    monkeypatch: pytest.MonkeyPatch, values: dict[str, str], overrides: dict[str, str]
) -> None:
    """Clear every known fixture alias, then set the family values followed by the overrides."""
    for alias in FIXTURE_VALUES.keys() | LOCAL_TEMPLATE_KEYS:
        monkeypatch.delenv(alias, raising=False)
    for key, value in {**values, **overrides}.items():
        monkeypatch.setenv(key, value)


def set_database_environment(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    """Set only explicit settings inputs for one configuration test."""
    _set_environment(monkeypatch, POSTGRES_KEYS, overrides)


def set_embedding_environment(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    """Set only explicit embedding inputs for one configuration test."""
    _set_environment(monkeypatch, EMBEDDING_KEYS, overrides)


def set_translation_environment(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    """Set only explicit translation inputs for one configuration test."""
    _set_environment(monkeypatch, TRANSLATION_KEYS, overrides)


def set_administrative_controller_environment(
    monkeypatch: pytest.MonkeyPatch, **overrides: str
) -> None:
    """Set the shared administrative inputs: admin root, derived prefixes, and stage roots.

    The administrative state root plus the four stage roots resolve from these process-environment
    values. Tests point the owning module's ``repository_root`` at their temporary repository and
    override the one stage root under test here.
    """
    values = {
        "ADMIN_STATE_ROOT": POSTGRES_KEYS["ADMIN_STATE_ROOT"],
        **ADMIN_DATASET_KEYS,
        **LOCAL_LIFECYCLE_KEYS,
        **TRANSLATION_CONTROLLER_KEYS,
        **INFERENCE_CONTROLLER_KEYS,
    }
    _set_environment(monkeypatch, values, overrides)


def set_inference_environment(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    """Set only explicit inference inputs and clear the other settings families."""
    values = {
        **INFERENCE_KEYS,
        **INFERENCE_CONTEXT_KEYS,
        **INFERENCE_SELECTION_KEYS,
        **INFERENCE_RERANK_KEYS,
        **INFERENCE_RERANK_INPUT_KEYS,
        **WORKER_RUNTIME_KEYS,
    }
    _set_environment(monkeypatch, values, overrides)
