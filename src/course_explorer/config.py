"""Validated database, source, capture, web, normalization, embedding, search, translation, and inference config."""

import json
import math
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from sqlalchemy.engine import URL

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.enums import TeachingTextField
from course_explorer.validation import (
    require_nonblank_text as _require_nonblank_text,
)
from course_explorer.validation import (
    require_sha256,
)

_ANY_HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


def _academic_year_start(value: str) -> int:
    """Validate consecutive academic-year syntax and return its starting year."""
    match = re.fullmatch(r"([0-9]{4})-([0-9]{4})", value)
    if match is None or int(match.group(2)) != int(match.group(1)) + 1:
        raise ValueError("academic years must match YYYY-YYYY with consecutive years")
    return int(match.group(1))


def _require_nonblank_secret(value: SecretStr, *, message: str) -> SecretStr:
    """Reject a blank secret while keeping it wrapped and never rendering it."""
    if not value.get_secret_value().strip():
        raise ValueError(message)
    return value


def _require_tcp_port(value: int, *, setting_name: str) -> int:
    """Require a valid inclusive TCP port."""
    if not 1 <= value <= 65535:
        raise ValueError(f"{setting_name} must be between 1 and 65535")
    return value


def _require_loopback_host(value: str, *, setting_name: str) -> str:
    """Permit only the loopback address a local service may bind."""
    if value != "127.0.0.1":
        raise ValueError(f"{setting_name} must be 127.0.0.1")
    return value


# Process-handoff marker. When a short-lived launcher hands a closed environment to a
# long-lived child (or a test supplies synthetic input), this marker restricts the settings layer
# to the constructor and process sources.
SETTINGS_SOURCE_MARKER = "COURSE_EXPLORER_SETTINGS_SOURCE"
ENVIRONMENT_ONLY_SETTINGS_SOURCE = "environment"


def _project_public_values(
    settings_cls: type[BaseSettings], public: dict[str, object]
) -> dict[str, object]:
    """Project merged public values onto the requested settings class's aliases only."""
    values: dict[str, object] = {}
    for name, field in settings_cls.model_fields.items():
        alias = field.validation_alias if isinstance(field.validation_alias, str) else name
        if alias in public:
            values[alias] = public[alias]
    return values


def _settings_aliases(settings_cls: type[BaseSettings]) -> tuple[str, ...]:
    """Return every validation alias the requested settings class reads from public values."""
    return tuple(
        field.validation_alias if isinstance(field.validation_alias, str) else name
        for name, field in settings_cls.model_fields.items()
    )


class ConfiguredSettings(BaseSettings):
    """Base for every settings family: automatic tracked TOML plus the device-local ignored ``.env``.

    The standard Pydantic source hook composes, in descending precedence: native constructor
    inputs, intentional process-environment overrides, the device-local ignored ``.env``, and the
    tracked public TOML files, over each class's own code defaults. Setting the
    ``COURSE_EXPLORER_SETTINGS_SOURCE=environment`` marker returns only the constructor and process
    sources for an isolated child or a synthetic test. Configuration
    errors hide their inputs so a secret can never be rendered by a validation failure.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="", hide_input_in_errors=True)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource | Callable[[], dict[str, object]], ...]:
        """Compose automatic file-backed sources, or only constructor/process when marked."""
        if os.environ.get(SETTINGS_SOURCE_MARKER) == ENVIRONMENT_ONLY_SETTINGS_SOURCE:
            return (init_settings, env_settings)
        from course_explorer import configuration

        def public_values() -> dict[str, object]:
            return _project_public_values(
                settings_cls,
                configuration.read_public_configuration(
                    configuration.repository_root(),
                    aliases=_settings_aliases(settings_cls),
                ),
            )

        return (
            init_settings,
            env_settings,
            configuration.LocalConfigurationSource(settings_cls),
            public_values,
        )


class WebSettings(ConfiguredSettings):
    """Validated loopback bind, process count and browser-drawing settings for HTTP serving."""

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    web_host: str = Field(validation_alias="WEB_HOST")
    web_port: int = Field(validation_alias="WEB_PORT")
    web_workers: int = Field(validation_alias="WEB_WORKERS", gt=0)
    prerequisite_graph_max_elements: int = Field(
        validation_alias="PREREQUISITE_GRAPH_MAX_ELEMENTS", gt=0
    )

    @field_validator("web_host")
    @classmethod
    def require_loopback_host(cls, value: str) -> str:
        """Require a loopback host."""
        return _require_loopback_host(value, setting_name="WEB_HOST")

    @field_validator("web_port")
    @classmethod
    def validate_web_port(cls, value: int) -> int:
        """Require a valid TCP port."""
        return _require_tcp_port(value, setting_name="WEB_PORT")


def load_web_settings() -> WebSettings:
    """Read web bind settings through the automatic public/local configuration composition."""
    return WebSettings()


class DatabaseSettings(ConfiguredSettings):
    """PostgreSQL connection components shared with the local Compose service."""

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    postgres_host: str = Field(validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(validation_alias="POSTGRES_PORT")
    postgres_db: str = Field(validation_alias="POSTGRES_DB")
    postgres_user: str = Field(validation_alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(validation_alias="POSTGRES_PASSWORD")
    selected_dataset_enabled: bool = Field(validation_alias="SELECTED_DATASET_ENABLED")
    admin_state_root: Path = Field(validation_alias="ADMIN_STATE_ROOT")

    @field_validator("postgres_host", "postgres_db", "postgres_user")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        """Reject missing meaningful connection components without normalizing them."""
        return _require_nonblank_text(
            value, message="database connection text values must not be blank"
        )

    @field_validator("admin_state_root", mode="before")
    @classmethod
    def validate_admin_state_root(cls, value: object) -> object:
        """Require one nonblank repository-relative admin state root without dot components."""
        return _require_relative_path(value, setting_name="ADMIN_STATE_ROOT", reject_percent=True)

    @field_validator("postgres_password")
    @classmethod
    def reject_blank_password(cls, value: SecretStr) -> SecretStr:
        """Reject blank passwords while keeping the secret wrapped."""
        return _require_nonblank_secret(value, message="postgres password must not be blank")

    @field_validator("postgres_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        """Require a valid TCP port."""
        return _require_tcp_port(value, setting_name="postgres port")

    @property
    def sqlalchemy_url(self) -> URL:
        """Build the sole application connection URL from shared components."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


def load_raw_database_settings() -> DatabaseSettings:
    """Read the raw configured database settings without resolving the selected-dataset pointer."""
    return DatabaseSettings()


def load_database_settings() -> DatabaseSettings:
    """Read database settings through the automatic public/local configuration composition.

    With ``SELECTED_DATASET_ENABLED=0`` the raw configured database is returned. Otherwise the
    selected dataset is resolved through its repository-relative admin state root and its
    database name replaces ``POSTGRES_DB``. The raw name alone never opts out, and no dotenv or
    process-global value is mutated.
    """
    settings = DatabaseSettings()
    if not settings.selected_dataset_enabled:
        return settings
    from course_explorer.administration import repository_root
    from course_explorer.datasets import resolve_selected_dataset

    receipt = resolve_selected_dataset(repository_root() / settings.admin_state_root)
    return settings.model_copy(update={"postgres_db": receipt.database_name})


class CaptureSettings(ConfiguredSettings):
    """Repository-relative location and checkpoint policy for raw capture evidence."""

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    raw_data_root: Path = Field(validation_alias="RAW_DATA_ROOT")
    capture_checkpoint_response_count: int = Field(
        validation_alias="CAPTURE_CHECKPOINT_RESPONSE_COUNT", ge=1, le=1000
    )

    @field_validator("raw_data_root", mode="before")
    @classmethod
    def validate_raw_data_root(cls, value: Path | str) -> Path:
        """Require one non-empty relative path without traversal components."""
        return Path(_require_relative_path(value, setting_name="RAW_DATA_ROOT"))


def load_capture_settings() -> CaptureSettings:
    """Read capture settings through the automatic public/local configuration composition."""
    return CaptureSettings()


def _require_relative_path(
    value: object, *, setting_name: str, reject_percent: bool = False
) -> object:
    """Require one nonblank repository-relative path without dot components.

    Runs before Pydantic converts to ``Path`` because ``pathlib`` collapses ``.`` components
    during construction, which would hide the raw input segments this contract must reject. The
    raw value is returned as-is so every artifact path and state root shares one
    predicate. State roots additionally refuse cmd-unsafe percent characters.
    """
    raw = str(value)
    path = Path(raw)
    if (
        not raw.strip()
        or not path.parts
        or path.is_absolute()
        or any(part in {".", ".."} for part in path.parts)
        or any(part in {".", ".."} for part in raw.split("/"))
        or (reject_percent and "%" in raw)
    ):
        raise ValueError(
            f"{setting_name} must be a non-empty repository-relative path without dot components"
        )
    return value


class LocalLifecycleSettings(ConfiguredSettings):
    """Validated state locations and cooperative lifecycle policy for the local admin stages.

    These values describe *where* the two local stage state roots live and *how* every
    local detached-worker startup, polling, and stop acknowledgement is bounded. They are portable
    policy: a different device keeps the same repository-relative state roots and the same timing
    bounds, so the roots live in the tracked ``config/curriculum.toml``/``config/search.toml`` and
    the shared timing keys live in the tracked ``config/worker.toml``. Loading composes the tracked public TOML and the
    device-local ignored ``.env`` automatically. There is no code default.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    ingestion_state_root: Path = Field(validation_alias="INGESTION_CONTROLLER_STATE_ROOT")
    embedding_state_root: Path = Field(validation_alias="EMBEDDING_CONTROLLER_STATE_ROOT")
    startup_attempts: int = Field(validation_alias="ADMIN_STARTUP_ATTEMPTS", ge=1, le=600)
    poll_interval_seconds: float = Field(
        validation_alias="ADMIN_POLL_INTERVAL_SECONDS",
        gt=0,
        le=30,
        allow_inf_nan=False,
    )
    stop_timeout_seconds: float = Field(
        validation_alias="ADMIN_STOP_TIMEOUT_SECONDS",
        gt=0,
        le=3600,
        allow_inf_nan=False,
    )

    @field_validator("ingestion_state_root", mode="before")
    @classmethod
    def validate_ingestion_state_root(cls, value: object) -> object:
        """Require one nonblank repository-relative state root without dot or cmd-expand characters."""
        return _require_relative_path(
            value, setting_name="INGESTION_CONTROLLER_STATE_ROOT", reject_percent=True
        )

    @field_validator("embedding_state_root", mode="before")
    @classmethod
    def validate_embedding_state_root(cls, value: object) -> object:
        """Require one nonblank repository-relative state root without dot or cmd-expand characters."""
        return _require_relative_path(
            value, setting_name="EMBEDDING_CONTROLLER_STATE_ROOT", reject_percent=True
        )


def load_local_lifecycle_settings() -> LocalLifecycleSettings:
    """Read local lifecycle settings through the automatic public/local configuration composition."""
    return LocalLifecycleSettings()


class KoriSettings(ConfiguredSettings):
    """Validated settings for the anonymous public Kori source."""

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    kori_base_url: AnyHttpUrl = Field(validation_alias="KORI_BASE_URL")
    tuni_university_id: str = Field(validation_alias="TUNI_UNIVERSITY_ID")
    kori_first_academic_year: str = Field(validation_alias="KORI_FIRST_ACADEMIC_YEAR")
    current_academic_year: str = Field(validation_alias="CURRENT_ACADEMIC_YEAR")
    kori_search_page_size: int = Field(validation_alias="KORI_SEARCH_PAGE_SIZE", ge=1, le=1000)
    kori_batch_size: int = Field(validation_alias="KORI_BATCH_SIZE", ge=1, le=100)
    kori_request_timeout_seconds: float = Field(
        validation_alias="KORI_REQUEST_TIMEOUT_SECONDS", gt=0, le=120
    )
    kori_max_attempts: int = Field(validation_alias="KORI_MAX_ATTEMPTS", ge=1, le=5)
    kori_retry_backoff_seconds: float = Field(
        validation_alias="KORI_RETRY_BACKOFF_SECONDS", ge=0, le=10
    )
    kori_concurrency: int = Field(validation_alias="KORI_CONCURRENCY", ge=1, le=8)
    kori_max_partition_depth: int = Field(validation_alias="KORI_MAX_PARTITION_DEPTH", ge=1, le=12)

    @field_validator("tuni_university_id")
    @classmethod
    def reject_blank_university_id(cls, value: str) -> str:
        """Require a meaningful university root identifier without changing it."""
        return _require_nonblank_text(value, message="TUNI_UNIVERSITY_ID must not be blank")

    @field_validator("kori_base_url")
    @classmethod
    def validate_kori_base_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        """Allow only the canonical anonymous HTTPS Kori base URL."""
        if (
            value.scheme != "https"
            or value.host != "sisu.tuni.fi"
            or value.port not in (None, 443)
            or value.username is not None
            or value.password is not None
            or value.query is not None
            or value.fragment is not None
            or value.path.removesuffix("/") != "/kori"
        ):
            raise ValueError("KORI_BASE_URL must be canonical https://sisu.tuni.fi/kori")
        return value

    @field_validator("kori_first_academic_year", "current_academic_year")
    @classmethod
    def validate_academic_year(cls, value: str) -> str:
        """Require consecutive four-digit academic-year bounds."""
        _academic_year_start(value)
        return value

    @model_validator(mode="after")
    def validate_academic_year_order(self) -> Self:
        """Reject a first academic year after the configured current year."""
        if self.first_academic_year_start > self.current_academic_year_start:
            raise ValueError("first academic year must not exceed current academic year")
        return self

    @property
    def first_academic_year_start(self) -> int:
        """Return first academic year start without deriving a Kori period ID."""
        return _academic_year_start(self.kori_first_academic_year)

    @property
    def current_academic_year_start(self) -> int:
        """Return current academic year start without deriving a Kori period ID."""
        return _academic_year_start(self.current_academic_year)


def load_kori_settings() -> KoriSettings:
    """Read public Kori settings through the automatic public/local configuration composition."""
    return KoriSettings()


class NormalizationSettings(ConfiguredSettings):
    """Validated settings for curriculum normalization."""

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    current_academic_year: str = Field(validation_alias="CURRENT_ACADEMIC_YEAR")
    active_academic_year_window: int = Field(
        validation_alias="ACTIVE_ACADEMIC_YEAR_WINDOW", ge=1, le=100
    )
    course_guide_base_url: AnyHttpUrl = Field(validation_alias="COURSE_GUIDE_BASE_URL")

    @field_validator("current_academic_year")
    @classmethod
    def validate_current_academic_year(cls, value: str) -> str:
        """Reuse the shared academic-year syntax and semantics."""
        _academic_year_start(value)
        return value

    @field_validator("course_guide_base_url")
    @classmethod
    def validate_course_guide_base_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        """Require the canonical HTTPS course-guide base without URL decorations."""
        return validate_course_guide_base_url(value)

    @property
    def current_academic_year_start(self) -> int:
        """Return configured current academic-year start."""
        return _academic_year_start(self.current_academic_year)


def validate_course_guide_base_url(value: object) -> AnyHttpUrl:
    """Validate and return the canonical HTTPS course-guide base URL."""
    value = _ANY_HTTP_URL_ADAPTER.validate_python(value)
    if (
        value.scheme != "https"
        or value.host != "sisu.tuni.fi"
        or value.port not in (None, 443)
        or value.username is not None
        or value.password is not None
        or value.query is not None
        or value.fragment is not None
        or value.path.removesuffix("/") != "/student/courseunit"
    ):
        raise ValueError(
            "COURSE_GUIDE_BASE_URL must be canonical https://sisu.tuni.fi/student/courseunit"
        )
    return value


def load_normalization_settings() -> NormalizationSettings:
    """Read normalization settings through the automatic public/local configuration composition."""
    return NormalizationSettings()


_EMBEDDING_IMAGE_PATTERN = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")


def _require_artifact_sha256(value: str, *, setting_name: str) -> str:
    """Require a full lowercase SHA-256 artifact identity."""
    return require_sha256(value, setting_name)


class EmbeddingRuntimeSettings(ConfiguredSettings):
    """Validated loopback contract for the one pinned CPU embedding runtime and its generation.

    This is the runtime/generation projection of the embedding contract, so the one generation
    lifecycle (and the Compose bridge) can run before a fresh dataset's similarity hubs exist. The
    full similarity contract that search, comparison, recommendations and the web
    process require is :class:`EmbeddingSettings`, which adds the two required hub fields. A
    similarity read fails loudly when a hub is missing. Both classes are projections of the
    same one file/source owner, never a second configuration path.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    embedding_host: str = Field(validation_alias="EMBEDDING_HOST")
    embedding_port: int = Field(validation_alias="EMBEDDING_PORT")
    embedding_model: str = Field(validation_alias="EMBEDDING_MODEL")
    embedding_dimension: Literal[COURSE_EMBEDDING_DIMENSION] = COURSE_EMBEDDING_DIMENSION
    embedding_pooling: Literal["cls", "mean", "last"] = Field(validation_alias="EMBEDDING_POOLING")
    embedding_normalization: int = Field(validation_alias="EMBEDDING_NORMALIZATION", ge=-1)
    embedding_threads: int = Field(validation_alias="EMBEDDING_THREADS")
    embedding_context_size: int = Field(validation_alias="EMBEDDING_CONTEXT_SIZE")
    embedding_request_timeout_seconds: float = Field(
        validation_alias="EMBEDDING_REQUEST_TIMEOUT_SECONDS", gt=0, le=600, allow_inf_nan=False
    )
    embedding_max_attempts: int = Field(validation_alias="EMBEDDING_MAX_ATTEMPTS", ge=1, le=5)
    embedding_retry_backoff_seconds: float = Field(
        validation_alias="EMBEDDING_RETRY_BACKOFF_SECONDS", ge=0, le=10, allow_inf_nan=False
    )
    embedding_generation_batch_size: int = Field(
        validation_alias="EMBEDDING_GENERATION_BATCH_SIZE", ge=1, le=128
    )
    embedding_chunk_max_characters: int = Field(
        validation_alias="EMBEDDING_CHUNK_MAX_CHARACTERS", ge=2, le=8192
    )
    embedding_chunk_overlap_characters: int = Field(
        validation_alias="EMBEDDING_CHUNK_OVERLAP_CHARACTERS", ge=0
    )
    embedding_artifact_url: AnyHttpUrl = Field(validation_alias="EMBEDDING_ARTIFACT_URL")
    embedding_artifact_path: Path = Field(validation_alias="EMBEDDING_ARTIFACT_PATH")
    embedding_artifact_sha256: str = Field(validation_alias="EMBEDDING_ARTIFACT_SHA256")
    embedding_server_image: str = Field(validation_alias="EMBEDDING_SERVER_IMAGE")
    embedding_runtime_revision: str = Field(validation_alias="EMBEDDING_RUNTIME_REVISION")

    @field_validator("embedding_host")
    @classmethod
    def require_loopback_host(cls, value: str) -> str:
        """Permit only the loopback address the local service may bind."""
        return _require_loopback_host(value, setting_name="EMBEDDING_HOST")

    @field_validator("embedding_port")
    @classmethod
    def validate_embedding_port(cls, value: int) -> int:
        """Require a valid TCP port."""
        return _require_tcp_port(value, setting_name="EMBEDDING_PORT")

    @field_validator("embedding_model")
    @classmethod
    def reject_blank_model(cls, value: str) -> str:
        """Require a meaningful model identity without normalizing it."""
        return _require_nonblank_text(value, message="EMBEDDING_MODEL must not be blank")

    @field_validator("embedding_threads", "embedding_context_size")
    @classmethod
    def require_positive_integer(cls, value: int) -> int:
        """Require positive thread and context-size counts."""
        if value <= 0:
            raise ValueError("embedding threads and context size must be positive")
        return value

    @field_validator("embedding_artifact_url")
    @classmethod
    def validate_artifact_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        """Require a credential-free HTTPS artifact location without decorations."""
        if (
            value.scheme != "https"
            or value.username is not None
            or value.password is not None
            or value.query is not None
            or value.fragment is not None
        ):
            raise ValueError(
                "EMBEDDING_ARTIFACT_URL must be HTTPS without credentials, query, or fragment"
            )
        return value

    @field_validator("embedding_artifact_path", mode="before")
    @classmethod
    def validate_artifact_path(cls, value: object) -> object:
        """Require a raw nonblank artifact path before Pydantic coerces it to `Path`."""
        _require_nonblank_text(str(value), message="EMBEDDING_ARTIFACT_PATH must not be blank")
        return value

    @field_validator("embedding_artifact_sha256")
    @classmethod
    def validate_artifact_sha256(cls, value: str) -> str:
        """Require a full lowercase SHA-256 identity."""
        return _require_artifact_sha256(value, setting_name="EMBEDDING_ARTIFACT_SHA256")

    @field_validator("embedding_runtime_revision")
    @classmethod
    def validate_runtime_revision(cls, value: str) -> str:
        """Require a full lowercase pinned runtime commit identity."""
        return _require_revision(
            value, message="EMBEDDING_RUNTIME_REVISION must be 40 lowercase hexadecimal characters"
        )

    @field_validator("embedding_server_image")
    @classmethod
    def validate_server_image(cls, value: str) -> str:
        """Require an immutable digest-pinned OCI reference."""
        if _EMBEDDING_IMAGE_PATTERN.fullmatch(value) is None:
            raise ValueError(
                "EMBEDDING_SERVER_IMAGE must be an OCI reference pinned by @sha256 digest"
            )
        return value

    @property
    def base_url(self) -> AnyHttpUrl:
        """Derive the sole provider base URL from configured loopback host and port."""
        return _ANY_HTTP_URL_ADAPTER.validate_python(
            f"http://{self.embedding_host}:{self.embedding_port}"
        )

    @model_validator(mode="after")
    def validate_chunk_overlap_bound(self) -> Self:
        """Require deterministic forward chunk progress (overlap below the window)."""
        if self.embedding_chunk_overlap_characters >= self.embedding_chunk_max_characters:
            raise ValueError(
                "EMBEDDING_CHUNK_OVERLAP_CHARACTERS must be smaller than "
                "EMBEDDING_CHUNK_MAX_CHARACTERS"
            )
        return self


class EmbeddingSettings(EmbeddingRuntimeSettings):
    """Validated similarity contract: the embedding runtime plus both required hub vectors.

    Request-time similarity consumers subtract these hubs before cosine, so they must resolve from
    their tracked derived artifacts. A missing or malformed hub fails that read loudly.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    embedding_hub_vector: tuple[float, ...] = Field(validation_alias="EMBEDDING_HUB_VECTOR")
    embedding_outcomes_hub_vector: tuple[float, ...] = Field(
        validation_alias="EMBEDDING_OUTCOMES_HUB_VECTOR"
    )

    @field_validator("embedding_hub_vector", "embedding_outcomes_hub_vector")
    @classmethod
    def validate_hub_vector(
        cls, value: tuple[float, ...], info: ValidationInfo
    ) -> tuple[float, ...]:
        """Require one finite hub vector at the fixed embedding dimension.

        The failure message names the field under validation, so a malformed value reports the
        setting it came from.
        """
        setting_name = (info.field_name or "").upper()
        if len(value) != COURSE_EMBEDDING_DIMENSION:
            raise ValueError(
                f"{setting_name} must have exactly {COURSE_EMBEDDING_DIMENSION} components"
            )
        if any(not math.isfinite(component) for component in value):
            raise ValueError(f"{setting_name} components must be finite")
        return value


def load_embedding_runtime_settings() -> EmbeddingRuntimeSettings:
    """Read runtime/generation embedding settings without resolving either similarity hub."""
    return EmbeddingRuntimeSettings()


def load_embedding_settings() -> EmbeddingSettings:
    """Read the full similarity embedding settings through the automatic configuration composition."""
    return EmbeddingSettings()


_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_GPU_LAYERS_PATTERN = re.compile(r"^(?:all|[0-9]+)$")


def _require_revision(value: str, *, message: str) -> str:
    """Require a full lowercase pinned commit identity."""
    if _REVISION_PATTERN.fullmatch(value) is None:
        raise ValueError(message)
    return value


class TranslationSettings(ConfiguredSettings):
    """Validated loopback contract for the one pinned offline translation runtime.

    Deployment, model, runtime, and request values stay out of provider and worker mechanics.
    The request alias, immutable model/runtime identities, and provenance model string are all
    derived or validated here so untrusted model output is bound to one known configuration.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    translation_host: str = Field(validation_alias="TRANSLATION_HOST")
    translation_port: int = Field(validation_alias="TRANSLATION_PORT")
    translation_model_alias: str = Field(validation_alias="TRANSLATION_MODEL_ALIAS")
    translation_model_repository: str = Field(validation_alias="TRANSLATION_MODEL_REPOSITORY")
    translation_model_revision: str = Field(validation_alias="TRANSLATION_MODEL_REVISION")
    translation_artifact_path: Path = Field(validation_alias="TRANSLATION_ARTIFACT_PATH")
    translation_artifact_sha256: str = Field(validation_alias="TRANSLATION_ARTIFACT_SHA256")
    translation_artifact_quant: Literal["Q5_K_M", "Q4_K_M"] = Field(
        validation_alias="TRANSLATION_ARTIFACT_QUANT"
    )
    translation_runtime_revision: str = Field(validation_alias="TRANSLATION_RUNTIME_REVISION")
    translation_context_size: int = Field(validation_alias="TRANSLATION_CONTEXT_SIZE")
    translation_parallel: int = Field(validation_alias="TRANSLATION_PARALLEL")
    translation_gpu_layers: str = Field(validation_alias="TRANSLATION_GPU_LAYERS")
    translation_request_timeout_seconds: float = Field(
        validation_alias="TRANSLATION_REQUEST_TIMEOUT_SECONDS",
        gt=0,
        le=600,
        allow_inf_nan=False,
    )
    translation_max_attempts: int = Field(validation_alias="TRANSLATION_MAX_ATTEMPTS", ge=1, le=5)
    translation_retry_backoff_seconds: float = Field(
        validation_alias="TRANSLATION_RETRY_BACKOFF_SECONDS", ge=0, le=10, allow_inf_nan=False
    )
    translation_max_tokens: int = Field(validation_alias="TRANSLATION_MAX_TOKENS")
    translation_temperature: float = Field(
        validation_alias="TRANSLATION_TEMPERATURE", ge=0, le=2, allow_inf_nan=False
    )

    @field_validator("translation_host")
    @classmethod
    def require_loopback_host(cls, value: str) -> str:
        """Permit only the loopback address the local runtime may bind."""
        return _require_loopback_host(value, setting_name="TRANSLATION_HOST")

    @field_validator("translation_port")
    @classmethod
    def validate_translation_port(cls, value: int) -> int:
        """Require a valid TCP port."""
        return _require_tcp_port(value, setting_name="TRANSLATION_PORT")

    @field_validator("translation_model_alias", "translation_model_repository")
    @classmethod
    def reject_blank_identity(cls, value: str) -> str:
        """Require meaningful runtime and model identities without normalizing them."""
        return _require_nonblank_text(
            value, message="translation model alias and repository must not be blank"
        )

    @field_validator("translation_model_revision", "translation_runtime_revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        """Require a full lowercase pinned commit identity."""
        return _require_revision(
            value,
            message=(
                "translation model and runtime revisions must be 40 lowercase hexadecimal characters"
            ),
        )

    @field_validator("translation_artifact_path", mode="before")
    @classmethod
    def validate_artifact_path(cls, value: object) -> object:
        """Require a raw nonblank artifact path before Pydantic coerces it to `Path`."""
        _require_nonblank_text(str(value), message="TRANSLATION_ARTIFACT_PATH must not be blank")
        return value

    @field_validator("translation_artifact_sha256")
    @classmethod
    def validate_artifact_sha256(cls, value: str) -> str:
        """Require a full lowercase SHA-256 identity."""
        return _require_artifact_sha256(value, setting_name="TRANSLATION_ARTIFACT_SHA256")

    @field_validator("translation_context_size", "translation_parallel", "translation_max_tokens")
    @classmethod
    def require_positive_integer(cls, value: int) -> int:
        """Require positive runtime and output counts."""
        if value <= 0:
            raise ValueError("translation context, parallel, and max tokens must be positive")
        return value

    @field_validator("translation_gpu_layers")
    @classmethod
    def validate_gpu_layers(cls, value: str) -> str:
        """Require full offload or one nonnegative layer count."""
        if _GPU_LAYERS_PATTERN.fullmatch(value) is None:
            raise ValueError("TRANSLATION_GPU_LAYERS must be 'all' or a nonnegative integer")
        return value

    @property
    def base_url(self) -> AnyHttpUrl:
        """Derive the sole provider base URL from configured loopback host and port."""
        return _ANY_HTTP_URL_ADAPTER.validate_python(
            f"http://{self.translation_host}:{self.translation_port}"
        )

    @property
    def provenance_model(self) -> str:
        """Return the immutable model identity persisted on derived translation rows."""
        return (
            f"{self.translation_model_repository}@{self.translation_model_revision}"
            f";{self.translation_artifact_quant};sha256:{self.translation_artifact_sha256}"
        )

    @model_validator(mode="after")
    def validate_max_tokens_below_context(self) -> Self:
        """Require the output cap to stay strictly below the served text context size."""
        if self.translation_max_tokens >= self.translation_context_size:
            raise ValueError("TRANSLATION_MAX_TOKENS must be smaller than TRANSLATION_CONTEXT_SIZE")
        return self


def load_translation_settings() -> TranslationSettings:
    """Read translation settings through the automatic public/local configuration composition."""
    return TranslationSettings()


_INFERENCE_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_INFERENCE_REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$"
)
_INFERENCE_GGUF_FILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.gguf$")


class InferenceLocalVariantSettings(BaseModel):
    """One ordered local fit key: loopback port, context, KV, batch, and MTP.

    Both configured variants serve the one pinned shared artifact. Each names one measured fit
    key. ``mtp_draft_n_max`` is present only on the first (MTP) key so the request tokenizer
    authority is unambiguous, and ``achieved_max_context`` is the largest context the
    measurement achieved for that key. These are validated configuration, never
    provider mechanics.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    alias: str
    port: int
    context_size: int
    kv_cache_type: Literal["q4_0"]
    batch_size: int
    ubatch_size: int
    speculative_type: str
    mtp_draft_n_max: int | None = None
    achieved_max_context: int

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, value: str) -> str:
        """Require one short request alias without whitespace or path characters."""
        if _INFERENCE_ALIAS_PATTERN.fullmatch(value) is None:
            raise ValueError("inference local variant alias must be a short ASCII alias")
        return value

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        """Require a valid loopback TCP port."""
        return _require_tcp_port(value, setting_name="INFERENCE_LOCAL_VARIANTS port")

    @field_validator("context_size", "batch_size", "ubatch_size", "achieved_max_context")
    @classmethod
    def require_positive(cls, value: int) -> int:
        """Require positive context and physical batch geometry."""
        if value <= 0:
            raise ValueError("inference local variant context and batch values must be positive")
        return value

    @field_validator("mtp_draft_n_max")
    @classmethod
    def validate_mtp_draft(cls, value: int | None) -> int | None:
        """Require a positive MTP draft count when the key carries MTP speculation."""
        if value is not None and value <= 0:
            raise ValueError("inference local variant MTP draft count must be positive")
        return value

    @field_validator("speculative_type")
    @classmethod
    def validate_speculative_type(cls, value: str) -> str:
        """Require one nonblank speculative-decoding type string without rewriting it."""
        return _require_nonblank_text(
            value, message="inference local variant speculative type must not be blank"
        )

    @model_validator(mode="after")
    def validate_variant_bounds(self) -> Self:
        """Require ubatch not to exceed batch and context not to exceed its achieved maximum."""
        if self.ubatch_size > self.batch_size:
            raise ValueError("inference local variant ubatch must not exceed batch")
        if self.context_size > self.achieved_max_context:
            raise ValueError(
                "inference local variant context must not exceed its achieved maximum context"
            )
        return self


class WorkerRuntimeSettings(ConfiguredSettings):
    """The portable generation CPU geometry shared by every local llama.cpp generation launch.

    These two values are the measured launcher geometry (`-t`/`--threads-batch`) recorded as
    execution provenance. They never gate scheduling, invalidate retained work, or appear in the
    cross-encoder runtime identity. They are device-independent, so they live in the
    tracked ``config/worker.toml`` rather than the ignored per-device ``.env``.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    worker_runtime_threads: int = Field(validation_alias="WORKER_RUNTIME_THREADS")
    worker_runtime_threads_batch: int = Field(validation_alias="WORKER_RUNTIME_THREADS_BATCH")

    @field_validator("worker_runtime_threads", "worker_runtime_threads_batch", mode="before")
    @classmethod
    def validate_runtime_threads(cls, value: object, info: ValidationInfo) -> int:
        """Require one non-boolean decimal thread count inside the inclusive serving bound.

        Runs before Pydantic coercion, so a boolean, a fractional string, or a float input is
        rejected instead of silently truncated. An environment value is a decimal string.
        """
        setting_name = (info.field_name or "").upper()
        return _require_decimal_int(value, setting_name=setting_name, minimum=1, maximum=256)


class WorkerGpuRebootSettings(ConfiguredSettings):
    """The one validated portable checkpoint-reboot interval shared by every worker GPU mode.

    A worker GPU mode (translation generation and inference cross-encoder scoring/whole-target
    generation) reboots the Windows worker at a completed atomic unit or a committed failed
    generation attempt once its loaded-GPU time reaches this interval. The value is device-independent
    policy owned by tracked
    ``config/worker.toml`` and is never a per-mode duplicate or a CLI flag. Loading composes the tracked public TOML and the
    device-local ignored ``.env`` automatically. There is no code default.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    worker_gpu_reboot_interval_minutes: int = Field(
        validation_alias="WORKER_GPU_REBOOT_INTERVAL_MINUTES", ge=1
    )


def load_worker_gpu_reboot_settings() -> WorkerGpuRebootSettings:
    """Read the shared checkpoint-reboot interval through the automatic public/local configuration composition."""
    return WorkerGpuRebootSettings()


# The fixed implementation-contract label of the deterministic generation-attempt schedule:
# one greedy attempt per cycle-target calculation, then deterministic-seed retries driven by the
# durable lifetime counter. A different schedule carries a different label, so recorded evidence
# names the schedule that produced it.
_GENERATION_ATTEMPT_SCHEDULE = "canonical-target-counter-calculation-first-v1"


class InferenceSettings(WorkerRuntimeSettings):
    """Validated loopback contract for the solo fit-only MIX inference runtime.

    One shared pinned source-model/artifact identity is served by the pinned llama.cpp runtime at
    two measured ordered local fit keys. The first key carries MTP speculation and is the request
    tokenizer authority. The second key is the larger no-MTP fallback. A packet that fits neither
    configured key has no configured route and fails as one target capacity failure, unless a
    caller injects its own explicit oversize route. Provider mechanics
    hardcode none of these values, and the closed routing/recommendation/filter policy keys carry
    exactly the solo/no-cutoff/retained-recommendation policy with no second-model,
    recommendation-skip, or cutoff configuration path. `INFERENCE_PROPOSAL_VERSION` is the
    separate result proposal composition version that binds one proposal identity together
    with the official snapshot and its source attempt.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    inference_host: str = Field(validation_alias="INFERENCE_HOST")
    inference_local_variants: tuple[InferenceLocalVariantSettings, ...] = Field(
        validation_alias="INFERENCE_LOCAL_VARIANTS"
    )
    inference_primary_model_repository: str = Field(
        validation_alias="INFERENCE_PRIMARY_MODEL_REPOSITORY"
    )
    inference_primary_model_revision: str = Field(
        validation_alias="INFERENCE_PRIMARY_MODEL_REVISION"
    )
    inference_primary_artifact_repository: str = Field(
        validation_alias="INFERENCE_PRIMARY_ARTIFACT_REPOSITORY"
    )
    inference_primary_artifact_revision: str = Field(
        validation_alias="INFERENCE_PRIMARY_ARTIFACT_REVISION"
    )
    inference_primary_artifact_file: str = Field(validation_alias="INFERENCE_PRIMARY_ARTIFACT_FILE")
    inference_primary_artifact_path: Path = Field(
        validation_alias="INFERENCE_PRIMARY_ARTIFACT_PATH"
    )
    inference_primary_artifact_sha256: str = Field(
        validation_alias="INFERENCE_PRIMARY_ARTIFACT_SHA256"
    )
    inference_primary_artifact_quant: Literal["IQ3_MIX"] = Field(
        validation_alias="INFERENCE_PRIMARY_ARTIFACT_QUANT"
    )
    inference_runtime_revision: str = Field(validation_alias="INFERENCE_RUNTIME_REVISION")
    inference_parallel: int = Field(validation_alias="INFERENCE_PARALLEL", gt=0)
    inference_gpu_layers: str = Field(validation_alias="INFERENCE_GPU_LAYERS")
    inference_flash_attention: Literal["on"] = Field(validation_alias="INFERENCE_FLASH_ATTENTION")
    inference_request_timeout_seconds: float = Field(
        validation_alias="INFERENCE_REQUEST_TIMEOUT_SECONDS",
        gt=0,
        le=600,
        allow_inf_nan=False,
    )
    inference_max_attempts: int = Field(validation_alias="INFERENCE_MAX_ATTEMPTS", ge=1, le=5)
    inference_retry_backoff_seconds: float = Field(
        validation_alias="INFERENCE_RETRY_BACKOFF_SECONDS", ge=0, le=10, allow_inf_nan=False
    )
    inference_retry_max_backoff_seconds: float = Field(
        validation_alias="INFERENCE_RETRY_MAX_BACKOFF_SECONDS", gt=0, le=600, allow_inf_nan=False
    )
    inference_retry_poll_seconds: float = Field(
        validation_alias="INFERENCE_RETRY_POLL_SECONDS", gt=0, le=1, allow_inf_nan=False
    )
    inference_max_tokens: int = Field(validation_alias="INFERENCE_MAX_TOKENS", gt=0)
    inference_fit_headroom_tokens: int = Field(
        validation_alias="INFERENCE_FIT_HEADROOM_TOKENS", gt=0
    )
    inference_temperature: float = Field(
        validation_alias="INFERENCE_TEMPERATURE", ge=0, le=0, allow_inf_nan=False
    )
    inference_retry_temperature: float = Field(
        validation_alias="INFERENCE_RETRY_TEMPERATURE", gt=0, le=2, allow_inf_nan=False
    )
    inference_seed: int = Field(validation_alias="INFERENCE_SEED", ge=0)
    inference_chat_template_kwargs: dict[str, bool] = Field(
        validation_alias="INFERENCE_CHAT_TEMPLATE_KWARGS"
    )
    inference_routing_policy: Literal["solo_fit_only"] = Field(
        validation_alias="INFERENCE_ROUTING_POLICY"
    )
    inference_recommendation_policy: Literal["include"] = Field(
        validation_alias="INFERENCE_RECOMMENDATION_POLICY"
    )
    inference_finding_filter_policy: Literal["none"] = Field(
        validation_alias="INFERENCE_FINDING_FILTER_POLICY"
    )
    inference_prompt_version: Literal["v9"] = Field(validation_alias="INFERENCE_PROMPT_VERSION")
    inference_schema_version: Literal["v2"] = Field(validation_alias="INFERENCE_SCHEMA_VERSION")
    inference_pipeline_version: Literal["v1"] = Field(validation_alias="INFERENCE_PIPELINE_VERSION")
    inference_proposal_version: Literal["v1"] = Field(validation_alias="INFERENCE_PROPOSAL_VERSION")

    @field_validator("inference_host")
    @classmethod
    def require_loopback_host(cls, value: str) -> str:
        """Permit only the loopback address the worker runtime may bind."""
        return _require_loopback_host(value, setting_name="INFERENCE_HOST")

    @field_validator("inference_primary_model_repository", "inference_primary_artifact_repository")
    @classmethod
    def validate_repository(cls, value: str) -> str:
        """Require one ordered public ``namespace/name`` repository identity."""
        if _INFERENCE_REPOSITORY_PATTERN.fullmatch(value) is None:
            raise ValueError("inference repositories must match namespace/name")
        return value

    @field_validator(
        "inference_primary_model_revision",
        "inference_primary_artifact_revision",
        "inference_runtime_revision",
    )
    @classmethod
    def validate_revision(cls, value: str) -> str:
        """Require a full lowercase pinned commit identity."""
        return _require_revision(
            value, message="inference revisions must be 40 lowercase hexadecimal characters"
        )

    @field_validator("inference_primary_artifact_sha256")
    @classmethod
    def validate_artifact_sha256(cls, value: str) -> str:
        """Require a full lowercase SHA-256 artifact identity."""
        return _require_artifact_sha256(value, setting_name="INFERENCE_PRIMARY_ARTIFACT_SHA256")

    @field_validator("inference_primary_artifact_file")
    @classmethod
    def validate_artifact_file(cls, value: str) -> str:
        """Require one GGUF artifact file name without directories."""
        if _INFERENCE_GGUF_FILE_PATTERN.fullmatch(value) is None:
            raise ValueError("INFERENCE_PRIMARY_ARTIFACT_FILE must be a GGUF file name")
        return value

    @field_validator("inference_primary_artifact_path", mode="before")
    @classmethod
    def validate_artifact_path(cls, value: object) -> object:
        """Require one repository-relative artifact path without dot components."""
        return _require_relative_path(value, setting_name="INFERENCE_PRIMARY_ARTIFACT_PATH")

    @field_validator("inference_gpu_layers")
    @classmethod
    def validate_gpu_layers(cls, value: str) -> str:
        """Require full offload or one nonnegative layer count."""
        if _GPU_LAYERS_PATTERN.fullmatch(value) is None:
            raise ValueError("INFERENCE_GPU_LAYERS must be 'all' or a nonnegative integer")
        return value

    @field_validator("inference_chat_template_kwargs")
    @classmethod
    def validate_chat_template_kwargs(cls, value: dict[str, bool]) -> dict[str, bool]:
        """Require the non-thinking chat-template flag set."""
        if value != {"enable_thinking": False}:
            raise ValueError(
                'INFERENCE_CHAT_TEMPLATE_KWARGS must be exactly {"enable_thinking": false}'
            )
        return value

    @model_validator(mode="after")
    def validate_artifact_path_matches_file(self) -> Self:
        """Require the configured relative path to name exactly the configured artifact file."""
        if self.inference_primary_artifact_path.name != self.inference_primary_artifact_file:
            raise ValueError(
                "INFERENCE_PRIMARY_ARTIFACT_PATH basename must equal "
                "INFERENCE_PRIMARY_ARTIFACT_FILE"
            )
        return self

    @model_validator(mode="after")
    def validate_local_variants(self) -> Self:
        """Require exactly two ordered unique loopback keys with the MTP key first."""
        variants = self.inference_local_variants
        if len(variants) != 2:
            raise ValueError("INFERENCE_LOCAL_VARIANTS must configure exactly two ordered keys")
        if len({variant.alias for variant in variants}) != 2:
            raise ValueError("INFERENCE_LOCAL_VARIANTS aliases must be unique")
        if len({variant.port for variant in variants}) != 2:
            raise ValueError("INFERENCE_LOCAL_VARIANTS ports must be unique")
        if variants[0].context_size >= variants[1].context_size:
            raise ValueError("INFERENCE_LOCAL_VARIANTS must be ordered by increasing context")
        if variants[0].mtp_draft_n_max is None or variants[1].mtp_draft_n_max is not None:
            raise ValueError(
                "INFERENCE_LOCAL_VARIANTS must place the MTP key first and the no-MTP key second"
            )
        return self

    @model_validator(mode="after")
    def validate_output_budget_below_local_contexts(self) -> Self:
        """Require the output cap plus fit margin to fit strictly inside every local context."""
        budget = self.inference_max_tokens + self.inference_fit_headroom_tokens
        if any(budget >= variant.context_size for variant in self.inference_local_variants):
            raise ValueError(
                "INFERENCE_MAX_TOKENS plus INFERENCE_FIT_HEADROOM_TOKENS must be smaller than "
                "every INFERENCE_LOCAL_VARIANTS context"
            )
        return self

    @model_validator(mode="after")
    def validate_retry_backoff_bounds(self) -> Self:
        """Require the local base and poll interval to stay inside the configured retry cap.

        The capped backoff grows from the base toward the cap, and the cooperative poll chunk is
        bounded by the same cap, so a base or poll larger than the cap would silently change the
        retry timing. Both are validated once here rather than at each sleep site.
        """
        if self.inference_retry_backoff_seconds > self.inference_retry_max_backoff_seconds:
            raise ValueError(
                "INFERENCE_RETRY_BACKOFF_SECONDS must not exceed "
                "INFERENCE_RETRY_MAX_BACKOFF_SECONDS"
            )
        if self.inference_retry_poll_seconds > self.inference_retry_max_backoff_seconds:
            raise ValueError(
                "INFERENCE_RETRY_POLL_SECONDS must not exceed INFERENCE_RETRY_MAX_BACKOFF_SECONDS"
            )
        return self

    def local_generation_parameters(
        self, attempt_ordinal: int, *, first_attempt: bool
    ) -> tuple[float, int]:
        """Return the local sampling pair for one reserved generation-attempt ordinal.

        The cycle-target calculation's first attempt is greedy at the configured initial zero
        temperature. Every subsequent attempt samples at the configured retry temperature. The seed is the
        configured base advanced by the durable lifetime ordinal (one-based), so a consumed ordinal
        never re-draws a seed. The reservation owner guarantees the positive ordinal and the boolean.
        """
        temperature = (
            self.inference_temperature if first_attempt else self.inference_retry_temperature
        )
        return temperature, self.inference_seed + attempt_ordinal - 1

    def local_base_url(self, variant: InferenceLocalVariantSettings) -> AnyHttpUrl:
        """Derive one variant's loopback base URL from the shared host and configured port."""
        return _ANY_HTTP_URL_ADAPTER.validate_python(f"http://{self.inference_host}:{variant.port}")

    @property
    def primary_artifact_url(self) -> AnyHttpUrl:
        """Derive the immutable public resolve URL of the configured quantization artifact."""
        return _ANY_HTTP_URL_ADAPTER.validate_python(
            f"https://huggingface.co/{self.inference_primary_artifact_repository}"
            f"/resolve/{self.inference_primary_artifact_revision}"
            f"/{self.inference_primary_artifact_file}"
        )

    @property
    def primary_model_identity(self) -> str:
        """Return the immutable source-model plus artifact identity persisted with every run."""
        return (
            f"{self.inference_primary_model_repository}"
            f"@{self.inference_primary_model_revision}"
            f";artifact={self.inference_primary_artifact_repository}"
            f"@{self.inference_primary_artifact_revision}"
            f"/{self.inference_primary_artifact_file}"
            f";quant={self.inference_primary_artifact_quant}"
            f";sha256={self.inference_primary_artifact_sha256}"
        )

    def local_runtime_identity(self, variant: InferenceLocalVariantSettings) -> str:
        """Return one selected local variant's immutable runtime/generation identity.

        The identity binds the pinned llama.cpp revision, the selected key's alias/context/KV and
        MTP speculation, the shared physical batch/offload values, the generation thread geometry,
        and the common generation settings. Changing any of these records different execution
        provenance. It is not scheduling permission and never invalidates retained work.
        """
        chat_template_kwargs = json.dumps(
            self.inference_chat_template_kwargs, sort_keys=True, separators=(",", ":")
        )
        mtp_draft_n_max = (
            "none" if variant.mtp_draft_n_max is None else str(variant.mtp_draft_n_max)
        )
        return (
            f"llama.cpp@{self.inference_runtime_revision}"
            f";alias={variant.alias}"
            f";context={variant.context_size}"
            f";parallel={self.inference_parallel}"
            f";gpu_layers={self.inference_gpu_layers}"
            f";kv_cache={variant.kv_cache_type}"
            f";flash_attention={self.inference_flash_attention}"
            f";batch={variant.batch_size}"
            f";ubatch={variant.ubatch_size}"
            f";speculative={variant.speculative_type}"
            f";mtp_draft_n_max={mtp_draft_n_max}"
            f";threads={self.worker_runtime_threads}"
            f";threads_batch={self.worker_runtime_threads_batch}"
            f";max_tokens={self.inference_max_tokens}"
            f";generation_attempts=unbounded"
            f";initial_temperature={self.inference_temperature}"
            f";first_attempt_scope=cycle-target-calculation"
            f";retry_temperature={self.inference_retry_temperature}"
            f";seed_base={self.inference_seed}"
            f";seed_schedule={_GENERATION_ATTEMPT_SCHEDULE}"
            f";retry_backoff_seconds={self.inference_retry_backoff_seconds}"
            f";retry_max_backoff_seconds={self.inference_retry_max_backoff_seconds}"
            f";retry_poll_seconds={self.inference_retry_poll_seconds}"
            f";chat_template_kwargs={chat_template_kwargs}"
        )


def load_inference_settings() -> InferenceSettings:
    """Read inference settings through the automatic public/local configuration composition."""
    return InferenceSettings()


def _require_decimal_int(value: object, *, setting_name: str, minimum: int, maximum: int) -> int:
    """Coerce one non-boolean decimal integer input once and bound it inclusively.

    Runs before Pydantic coercion, so a boolean, a fractional string, or a float input is
    rejected instead of silently truncated. An environment value is a decimal string.
    """
    if isinstance(value, bool):
        raise ValueError(f"{setting_name} must be an integer")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value) is not None:
        number = int(value)
    else:
        raise ValueError(f"{setting_name} must be an integer")
    return _require_int_bounds(number, setting_name=setting_name, minimum=minimum, maximum=maximum)


def _require_int_bounds(value: int, *, setting_name: str, minimum: int, maximum: int) -> int:
    """Require one integer setting inside an inclusive configured range."""
    if not minimum <= value <= maximum:
        raise ValueError(f"{setting_name} must be between {minimum} and {maximum}")
    return value


# The canonical multiview field order, derived from the neutral ``TeachingTextField`` enum, which
# carries no ORM or database dependency. Settings serialize these wire values as plain strings.
_INFERENCE_MULTIVIEW_FIELD_ORDER: tuple[str, ...] = tuple(
    field.value for field in TeachingTextField
)


class InferenceContextSettings(ConfiguredSettings):
    """Validated label-blind multiview field-view and fusion settings for live selection.

    These two values own the accepted multiview field views and the reciprocal-rank
    fusion offset consumed by the installed operational CE-only selection. They are operational
    selection mechanics separate from development measurement policy and from the runtime contract
    in ``InferenceSettings``. Loading composes the tracked public TOML and the
    device-local ignored ``.env`` automatically. There is no code default.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    inference_multiview_evaluation_fields: tuple[Literal["name", "content", "outcomes"], ...] = (
        Field(validation_alias="INFERENCE_MULTIVIEW_EVALUATION_FIELDS")
    )
    inference_multiview_fusion_rank_offset: int = Field(
        validation_alias="INFERENCE_MULTIVIEW_FUSION_RANK_OFFSET"
    )

    @field_validator("inference_multiview_evaluation_fields")
    @classmethod
    def validate_multiview_fields(
        cls, value: tuple[Literal["name", "content", "outcomes"], ...]
    ) -> tuple[Literal["name", "content", "outcomes"], ...]:
        """Require a nonempty, unique field tuple in canonical name/content/outcomes order.

        The canonical order is the neutral ``TeachingTextField`` enum's declaration order, which
        carries no ORM dependency. The evaluation service converts these validated wire strings to
        ``TeachingTextField`` before a field-view query.
        """
        if not value:
            raise ValueError("INFERENCE_MULTIVIEW_EVALUATION_FIELDS must not be empty")
        for item in value:
            if item not in _INFERENCE_MULTIVIEW_FIELD_ORDER:
                raise ValueError(
                    "INFERENCE_MULTIVIEW_EVALUATION_FIELDS entries must be one of "
                    f"{list(_INFERENCE_MULTIVIEW_FIELD_ORDER)}"
                )
        if tuple(sorted(value, key=_INFERENCE_MULTIVIEW_FIELD_ORDER.index)) != value:
            raise ValueError(
                "INFERENCE_MULTIVIEW_EVALUATION_FIELDS must follow canonical name/content/"
                "outcomes order"
            )
        if len(set(value)) != len(value):
            raise ValueError("INFERENCE_MULTIVIEW_EVALUATION_FIELDS must not repeat a value")
        return value

    @field_validator("inference_multiview_fusion_rank_offset")
    @classmethod
    def validate_multiview_fusion_rank_offset(cls, value: int) -> int:
        """Bound the positive reciprocal-rank fusion offset used for live multiview selection."""
        return _require_int_bounds(
            value,
            setting_name="INFERENCE_MULTIVIEW_FUSION_RANK_OFFSET",
            minimum=1,
            maximum=1000,
        )


def load_inference_context_settings() -> InferenceContextSettings:
    """Read live multiview field-view/fusion settings through the automatic composition."""
    return InferenceContextSettings()


class InferenceSelectionSettings(ConfiguredSettings):
    """Validated pool and final-candidate policy for the label-free selection pipeline.

    The two values bound the label-free selection pipeline: the embedding
    pool depth that the live operational selection consumes, and the hard maximum of
    candidates the selected packet may carry. They are separate from
    ``InferenceContextSettings``: the multiview field views and fusion offset are selection
    mechanics, whereas ``INFERENCE_SELECTION_POOL_K`` records the pool size for the live
    operational selection and eventual bulk selection. ``INFERENCE_SELECTION_FINAL_K`` is the hard
    ceiling for the CE-only top-50 packet. No ranking-only model is enabled
    here. Loading composes the tracked public TOML and the
    device-local ignored ``.env`` automatically. There is no code default.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    inference_selection_pool_k: int = Field(validation_alias="INFERENCE_SELECTION_POOL_K")
    inference_selection_final_k: int = Field(validation_alias="INFERENCE_SELECTION_FINAL_K")

    @field_validator("inference_selection_pool_k")
    @classmethod
    def validate_selection_pool_k(cls, value: int) -> int:
        """Bound the positive embedding pool depth."""
        return _require_int_bounds(
            value,
            setting_name="INFERENCE_SELECTION_POOL_K",
            minimum=1,
            maximum=5000,
        )

    @field_validator("inference_selection_final_k")
    @classmethod
    def validate_selection_final_k(cls, value: int) -> int:
        """Bound the hard maximum of final candidates the whole-target packet may receive."""
        return _require_int_bounds(
            value,
            setting_name="INFERENCE_SELECTION_FINAL_K",
            minimum=1,
            maximum=50,
        )


def load_inference_selection_settings() -> InferenceSelectionSettings:
    """Read pool selection settings through the automatic public/local configuration composition."""
    return InferenceSelectionSettings()


class InferenceRerankSettings(ConfiguredSettings):
    """Validated loopback contract for the one pinned multilingual cross-encoder runtime.

    The ``rerank`` slot owns a distinct, separately pinned public GGUF and its own loopback
    llama.cpp serving contract (embedding/rank-pooling/reranking). It is separate from
    ``InferenceSettings``: the selected local generation settings carry primary-only
    quant, request, and generation values, and this cross-encoder has no chat template, sampling,
    or generation semantics. The llama.cpp runtime revision is shared with the primary runtime
    through the ``INFERENCE_RUNTIME_REVISION`` key so one worker build serves both, and
    the source-model and public-quantization artifact identities stay separate so a ranked output
    is always bound to one known configuration. The single batch-geometry value drives both physical
    llama.cpp flags and is part of the derived runtime identity, because the pinned ``--embedding``
    clamp otherwise reduces the physical batch below what a real 1536-character document needs.
    The single request timeout bounds one cross-encoder request and is likewise part of the derived
    runtime identity, so changing it invalidates rerank inputs and evidence.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    inference_rerank_host: str = Field(validation_alias="INFERENCE_RERANK_HOST")
    inference_rerank_port: int = Field(validation_alias="INFERENCE_RERANK_PORT")
    inference_rerank_model_alias: str = Field(validation_alias="INFERENCE_RERANK_MODEL_ALIAS")
    inference_rerank_model_repository: str = Field(
        validation_alias="INFERENCE_RERANK_MODEL_REPOSITORY"
    )
    inference_rerank_model_revision: str = Field(validation_alias="INFERENCE_RERANK_MODEL_REVISION")
    inference_rerank_artifact_repository: str = Field(
        validation_alias="INFERENCE_RERANK_ARTIFACT_REPOSITORY"
    )
    inference_rerank_artifact_revision: str = Field(
        validation_alias="INFERENCE_RERANK_ARTIFACT_REVISION"
    )
    inference_rerank_artifact_file: str = Field(validation_alias="INFERENCE_RERANK_ARTIFACT_FILE")
    inference_rerank_artifact_path: Path = Field(validation_alias="INFERENCE_RERANK_ARTIFACT_PATH")
    inference_rerank_artifact_sha256: str = Field(
        validation_alias="INFERENCE_RERANK_ARTIFACT_SHA256"
    )
    inference_rerank_artifact_quant: Literal["Q8_0"] = Field(
        validation_alias="INFERENCE_RERANK_ARTIFACT_QUANT"
    )
    inference_runtime_revision: str = Field(validation_alias="INFERENCE_RUNTIME_REVISION")
    inference_rerank_context_size: int = Field(
        validation_alias="INFERENCE_RERANK_CONTEXT_SIZE", ge=1, le=8192
    )
    inference_rerank_batch_size: int = Field(validation_alias="INFERENCE_RERANK_BATCH_SIZE")
    inference_rerank_request_timeout_seconds: float = Field(
        validation_alias="INFERENCE_RERANK_REQUEST_TIMEOUT_SECONDS"
    )

    @field_validator("inference_rerank_host")
    @classmethod
    def require_loopback_host(cls, value: str) -> str:
        """Permit only the loopback address the worker runtime may bind."""
        return _require_loopback_host(value, setting_name="INFERENCE_RERANK_HOST")

    @field_validator("inference_rerank_port")
    @classmethod
    def validate_rerank_port(cls, value: int) -> int:
        """Require a valid TCP port."""
        return _require_tcp_port(value, setting_name="INFERENCE_RERANK_PORT")

    @field_validator("inference_rerank_model_alias")
    @classmethod
    def validate_model_alias(cls, value: str) -> str:
        """Require a short request alias without whitespace or path characters."""
        if _INFERENCE_ALIAS_PATTERN.fullmatch(value) is None:
            raise ValueError("INFERENCE_RERANK_MODEL_ALIAS must be a short ASCII alias")
        return value

    @field_validator("inference_rerank_model_repository", "inference_rerank_artifact_repository")
    @classmethod
    def validate_repository(cls, value: str) -> str:
        """Require one ordered public ``namespace/name`` repository identity."""
        if _INFERENCE_REPOSITORY_PATTERN.fullmatch(value) is None:
            raise ValueError("rerank repositories must match namespace/name")
        return value

    @field_validator(
        "inference_rerank_model_revision",
        "inference_rerank_artifact_revision",
        "inference_runtime_revision",
    )
    @classmethod
    def validate_revision(cls, value: str) -> str:
        """Require a full lowercase pinned commit identity."""
        return _require_revision(
            value, message="rerank revisions must be 40 lowercase hexadecimal characters"
        )

    @field_validator("inference_rerank_artifact_sha256")
    @classmethod
    def validate_artifact_sha256(cls, value: str) -> str:
        """Require a full lowercase SHA-256 artifact identity."""
        return _require_artifact_sha256(value, setting_name="INFERENCE_RERANK_ARTIFACT_SHA256")

    @field_validator("inference_rerank_artifact_file")
    @classmethod
    def validate_artifact_file(cls, value: str) -> str:
        """Require one GGUF artifact file name without directories."""
        if _INFERENCE_GGUF_FILE_PATTERN.fullmatch(value) is None:
            raise ValueError("INFERENCE_RERANK_ARTIFACT_FILE must be a GGUF file name")
        return value

    @field_validator("inference_rerank_artifact_path", mode="before")
    @classmethod
    def validate_artifact_path(cls, value: object) -> object:
        """Require one repository-relative artifact path without dot components."""
        return _require_relative_path(value, setting_name="INFERENCE_RERANK_ARTIFACT_PATH")

    @field_validator("inference_rerank_batch_size", mode="before")
    @classmethod
    def validate_rerank_batch_size(cls, value: object) -> int:
        """Require one non-boolean decimal batch geometry inside the serving-context range.

        Runs before Pydantic coercion so a boolean, a fractional string, or a float input is
        rejected instead of silently truncated or coerced to a within-range batch. This single
        value drives both ``--batch-size`` and ``--ubatch-size``.
        """
        return _require_decimal_int(
            value,
            setting_name="INFERENCE_RERANK_BATCH_SIZE",
            minimum=1,
            maximum=8192,
        )

    @field_validator("inference_rerank_request_timeout_seconds", mode="before")
    @classmethod
    def validate_rerank_request_timeout(cls, value: object) -> float:
        """Require one positive finite decimal timeout no greater than the configured 60-second bound.

        Runs before Pydantic coercion so a boolean, a nonnumeric or formatted string, ``NaN``,
        ``Infinity``, or zero is rejected instead of being accepted as a finite in-range timeout.
        A bare integer or a decimal string is accepted because environment values always arrive as
        strings. A trailing unit or surrounding whitespace is not.
        """
        if isinstance(value, bool):
            raise ValueError("INFERENCE_RERANK_REQUEST_TIMEOUT_SECONDS must be a number")
        if isinstance(value, int):
            number = float(value)
        elif isinstance(value, float):
            number = value
        elif isinstance(value, str) and re.fullmatch(r"[0-9]+(\.[0-9]+)?", value) is not None:
            number = float(value)
        else:
            raise ValueError("INFERENCE_RERANK_REQUEST_TIMEOUT_SECONDS must be a number")
        if not math.isfinite(number) or number <= 0:
            raise ValueError("INFERENCE_RERANK_REQUEST_TIMEOUT_SECONDS must be finite and positive")
        if number > 60:
            raise ValueError("INFERENCE_RERANK_REQUEST_TIMEOUT_SECONDS must not exceed 60")
        return number

    @model_validator(mode="after")
    def validate_artifact_path_matches_file(self) -> Self:
        """Require the artifact path to name the artifact file and batch to fit the serving context."""
        if self.inference_rerank_artifact_path.name != self.inference_rerank_artifact_file:
            raise ValueError(
                "INFERENCE_RERANK_ARTIFACT_PATH basename must equal INFERENCE_RERANK_ARTIFACT_FILE"
            )
        if self.inference_rerank_batch_size > self.inference_rerank_context_size:
            raise ValueError(
                "INFERENCE_RERANK_BATCH_SIZE must not exceed INFERENCE_RERANK_CONTEXT_SIZE"
            )
        return self

    @property
    def base_url(self) -> AnyHttpUrl:
        """Derive the sole rerank endpoint base URL from the configured loopback host and port."""
        return _ANY_HTTP_URL_ADAPTER.validate_python(
            f"http://{self.inference_rerank_host}:{self.inference_rerank_port}"
        )

    @property
    def rerank_artifact_url(self) -> AnyHttpUrl:
        """Derive the immutable public resolve URL of the configured quantization artifact."""
        return _ANY_HTTP_URL_ADAPTER.validate_python(
            f"https://huggingface.co/{self.inference_rerank_artifact_repository}"
            f"/resolve/{self.inference_rerank_artifact_revision}"
            f"/{self.inference_rerank_artifact_file}"
        )

    @property
    def rerank_model_identity(self) -> str:
        """Return the immutable source-model plus artifact identity for this cross-encoder."""
        return (
            f"{self.inference_rerank_model_repository}"
            f"@{self.inference_rerank_model_revision}"
            f";artifact={self.inference_rerank_artifact_repository}"
            f"@{self.inference_rerank_artifact_revision}"
            f"/{self.inference_rerank_artifact_file}"
            f";quant={self.inference_rerank_artifact_quant}"
            f";sha256={self.inference_rerank_artifact_sha256}"
        )

    @property
    def rerank_runtime_identity(self) -> str:
        """Return the immutable runtime and serving identity for the rerank endpoint."""
        return (
            f"llama.cpp@{self.inference_runtime_revision}"
            f";alias={self.inference_rerank_model_alias}"
            f";context={self.inference_rerank_context_size}"
            f";host={self.inference_rerank_host}"
            f";port={self.inference_rerank_port}"
            f";embedding=true"
            f";pooling=rank"
            f";reranking=true"
            f";batch={self.inference_rerank_batch_size}"
            f";ubatch={self.inference_rerank_batch_size}"
            f";timeout={self.inference_rerank_request_timeout_seconds:g}"
        )


def load_inference_rerank_settings() -> InferenceRerankSettings:
    """Read cross-encoder rerank settings through the automatic public/local configuration composition."""
    return InferenceRerankSettings()


class InferenceRerankInputSettings(ConfiguredSettings):
    """Validated pair-text bounds and layout for one label-free cross-encoder input.

    These keys bound and order the query and document text a cross-encoder input may send to the
    operational reranker. They are separate from ``InferenceRerankSettings`` (the
    runtime/serving contract) and ``InferenceSelectionSettings`` (pool depth and final
    candidate ceiling): they are the shared label-free teaching-text construction, not a rerank
    depth or a top-50 policy. The layout is a closed teaching-text order and never reads prerequisite
    text. Loading composes the tracked public TOML and the
    device-local ignored ``.env`` automatically. There is no code default.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    inference_rerank_query_max_characters: int = Field(
        validation_alias="INFERENCE_RERANK_QUERY_MAX_CHARACTERS"
    )
    inference_rerank_document_max_characters: int = Field(
        validation_alias="INFERENCE_RERANK_DOCUMENT_MAX_CHARACTERS"
    )
    inference_rerank_text_layout: Literal["content-first"] = Field(
        validation_alias="INFERENCE_RERANK_TEXT_LAYOUT"
    )

    @field_validator(
        "inference_rerank_query_max_characters",
        "inference_rerank_document_max_characters",
        mode="before",
    )
    @classmethod
    def validate_rerank_input_limit(cls, value: object, info: ValidationInfo) -> int:
        """Require one non-boolean decimal integer inside the inclusive bound range.

        Runs before Pydantic coercion, so a boolean, a fractional string, or a float input is
        rejected instead of silently truncated or coerced to a within-range integer.
        """
        setting_name = (info.field_name or "").upper()
        return _require_decimal_int(value, setting_name=setting_name, minimum=64, maximum=8192)


def load_inference_rerank_input_settings() -> InferenceRerankInputSettings:
    """Read rerank-input bounds through the automatic public/local configuration composition."""
    return InferenceRerankInputSettings()


_CONTROLLER_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_CONTROLLER_DATABASE_PREFIX_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")
_CONTROLLER_SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _require_database_prefix(value: str, *, setting_name: str) -> str:
    """Require a lowercase SQL identifier prefix short enough for a 63-byte derived name."""
    if (
        _CONTROLLER_DATABASE_PREFIX_PATTERN.fullmatch(value) is None
        or len(value.encode("ascii")) > 30
    ):
        raise ValueError(
            f"{setting_name} must match [a-z_][a-z0-9_]* and be at most 30 ASCII bytes"
        )
    return value


class WorkerConnectionSettings(ConfiguredSettings):
    """Validated neutral worker transport and lifecycle-bounding policy.

    These values describe *where* the worker is reached and *how* a cooperative
    worker lifecycle is bounded. They are shared by the neutral SSH/WSL
    transport and any administrative worker stage that needs the connection boundary.

    Ownership splits by what must change per setup. ``TRANSLATION_CONTROLLER_SSH_TARGET``,
    ``TRANSLATION_CONTROLLER_WSL_DISTRIBUTION``, and
    ``TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT`` are machine-local values read from the ignored
    local ``.env``. The connect timeout comes from the tracked portable ``config/worker.toml``.
    The health interval and stop timeout are shared wait values that stay assigned once, in
    ``config/translation.toml``. All reach this class through the automatic public/local
    configuration composition.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    ssh_target: str = Field(validation_alias="TRANSLATION_CONTROLLER_SSH_TARGET")
    ssh_connect_timeout_seconds: int = Field(
        validation_alias="TRANSLATION_CONTROLLER_SSH_CONNECT_TIMEOUT_SECONDS", ge=1, le=120
    )
    wsl_distribution: str = Field(validation_alias="TRANSLATION_CONTROLLER_WSL_DISTRIBUTION")
    worker_project_root: Path = Field(validation_alias="TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT")
    poll_interval_seconds: float = Field(
        validation_alias="TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS",
        gt=0,
        le=30,
        allow_inf_nan=False,
    )
    stop_timeout_seconds: float = Field(
        validation_alias="TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS",
        gt=0,
        le=3600,
        allow_inf_nan=False,
    )

    @field_validator("ssh_target", "wsl_distribution")
    @classmethod
    def validate_controller_identifier(cls, value: str) -> str:
        """Require a short ASCII SSH alias or WSL distribution name."""
        if _CONTROLLER_IDENTIFIER_PATTERN.fullmatch(value) is None:
            raise ValueError(
                "controller SSH target and WSL distribution must be 1-64 ASCII "
                "letters, digits, underscore, dot, or hyphen"
            )
        return value

    @field_validator("worker_project_root")
    @classmethod
    def validate_worker_project_root(cls, value: Path) -> Path:
        """Require an absolute POSIX worker checkout path without dot or cmd-expand characters."""
        raw = str(value)
        if (
            not raw.strip()
            or not value.is_absolute()
            or any(part in {".", ".."} for part in value.parts)
            or "%" in raw
        ):
            raise ValueError(
                "TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT must be an absolute path "
                "without dot components or cmd-unsafe percent characters"
            )
        return value


class TranslationControllerSettings(WorkerConnectionSettings):
    """Validated remote-controller state-root and health-attempt policy.

    This adds the translation controller's own local state root and health attempt count on top
    of the neutral connection base. The derived worker database name comes from the shared
    administrative dataset settings, never a second translation prefix, so cleanup can only
    ever target the exact session database. All values reach this class through the
    the automatic public/local configuration composition.
    """

    translation_controller_state_root: Path = Field(
        validation_alias="TRANSLATION_CONTROLLER_STATE_ROOT"
    )
    translation_controller_health_attempts: int = Field(
        validation_alias="TRANSLATION_CONTROLLER_HEALTH_ATTEMPTS", ge=1, le=600
    )

    @field_validator("translation_controller_state_root", mode="before")
    @classmethod
    def validate_state_root(cls, value: object) -> object:
        """Require one nonblank repository-relative state root without dot or cmd-expand characters."""
        return _require_relative_path(
            value, setting_name="TRANSLATION_CONTROLLER_STATE_ROOT", reject_percent=True
        )


def load_worker_connection_settings() -> WorkerConnectionSettings:
    """Read the neutral worker connection settings through the automatic public/local configuration composition."""
    return WorkerConnectionSettings()


def load_translation_controller_settings() -> TranslationControllerSettings:
    """Read translation-controller settings through the automatic public/local configuration composition."""
    return TranslationControllerSettings()


class InferenceControllerSettings(WorkerConnectionSettings):
    """Validated inference-controller state-root and health-attempt policy.

    This adds only the inference controller's own repository-relative state root and bounded
    health attempt count on top of the neutral connection base. The derived worker database name
    comes from the shared administrative dataset settings, never from a second inference prefix,
    so cleanup can only ever target the exact canonical session database. All values reach this
    class through the automatic public/local configuration composition.
    """

    inference_controller_state_root: Path = Field(
        validation_alias="INFERENCE_CONTROLLER_STATE_ROOT"
    )
    inference_controller_health_attempts: int = Field(
        validation_alias="INFERENCE_CONTROLLER_HEALTH_ATTEMPTS", ge=1, le=600
    )

    @field_validator("inference_controller_state_root", mode="before")
    @classmethod
    def validate_state_root(cls, value: object) -> object:
        """Require one nonblank repository-relative state root without dot or cmd-expand characters."""
        return _require_relative_path(
            value, setting_name="INFERENCE_CONTROLLER_STATE_ROOT", reject_percent=True
        )


def load_inference_controller_settings() -> InferenceControllerSettings:
    """Read inference-controller settings through the automatic public/local configuration composition."""
    return InferenceControllerSettings()


class AdministrativeDatasetSettings(ConfiguredSettings):
    """Validated selected-dataset state root, derived database prefixes, and one operation bound.

    These values are portable policy: the repository-relative admin state root, the two
    distinct lowercase prefixes that derive one server or worker database name from a validated
    session id, and the single timeout every dataset dump/restore/rotation subprocess receives.
    The state root reuses the shared repository-relative predicate. Loading composes the tracked public TOML and the
    device-local ignored ``.env`` automatically. There is no code default.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    admin_state_root: Path = Field(validation_alias="ADMIN_STATE_ROOT")
    dataset_database_prefix: str = Field(validation_alias="ADMIN_DATASET_DATABASE_PREFIX")
    worker_database_prefix: str = Field(validation_alias="ADMIN_WORKER_DATABASE_PREFIX")
    database_operation_timeout_seconds: float = Field(
        validation_alias="ADMIN_DATABASE_OPERATION_TIMEOUT_SECONDS",
        gt=0,
        allow_inf_nan=False,
    )

    @field_validator("admin_state_root", mode="before")
    @classmethod
    def validate_admin_state_root(cls, value: object) -> object:
        """Require one nonblank repository-relative admin state root without dot components."""
        return _require_relative_path(value, setting_name="ADMIN_STATE_ROOT", reject_percent=True)

    @field_validator("dataset_database_prefix", "worker_database_prefix")
    @classmethod
    def validate_database_prefix(cls, value: str) -> str:
        """Require a lowercase SQL identifier prefix short enough for a 63-byte derived name."""
        return _require_database_prefix(value, setting_name="ADMIN_*_DATABASE_PREFIX")

    @model_validator(mode="after")
    def validate_distinct_prefixes(self) -> Self:
        """Require the server and worker prefixes to derive different database names."""
        if self.dataset_database_prefix == self.worker_database_prefix:
            raise ValueError("admin dataset and worker database prefixes must be distinct")
        return self

    def database_name(self, dataset_id: str, *, worker: bool = False) -> str:
        """Derive the one server or worker database name for a validated dataset id."""
        if _CONTROLLER_SESSION_ID_PATTERN.fullmatch(dataset_id) is None:
            raise ValueError("dataset id must be 32 lowercase hexadecimal characters")
        prefix = self.worker_database_prefix if worker else self.dataset_database_prefix
        derived = f"{prefix}_{dataset_id}"
        if len(derived.encode("ascii")) > 63:
            raise ValueError("derived dataset database name must be at most 63 ASCII bytes")
        return derived


def load_administrative_dataset_settings() -> AdministrativeDatasetSettings:
    """Read selected-dataset administrative settings through the automatic composition."""
    return AdministrativeDatasetSettings()


class WorkerSetupSettings(ConfiguredSettings):
    """Validated explicit worker setup/update identity and bound.

    Two portable values drive explicit worker setup/update: the GitHub origin URL the worker
    checkout must match, and one long setup timeout that a real install/download/build may use
    without borrowing the short model-request or control timeout. Loading composes the tracked public TOML and the
    device-local ignored ``.env`` automatically. There is no code default.
    """

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    worker_setup_project_url: str = Field(validation_alias="WORKER_SETUP_PROJECT_URL")
    worker_setup_timeout_seconds: float = Field(
        validation_alias="WORKER_SETUP_TIMEOUT_SECONDS", gt=0, allow_inf_nan=False
    )

    @field_validator("worker_setup_project_url")
    @classmethod
    def validate_project_url(cls, value: str) -> str:
        """Require one nonblank configured origin URL without normalizing it."""
        return _require_nonblank_text(value, message="WORKER_SETUP_PROJECT_URL must not be blank")


def load_worker_setup_settings() -> WorkerSetupSettings:
    """Read explicit worker setup/update settings through the automatic public/local configuration composition."""
    return WorkerSetupSettings()


SearchMethod = Literal["exact_code", "substring", "fuzzy_name", "semantic"]

_SEARCH_METHODS: tuple[SearchMethod, ...] = (
    "exact_code",
    "substring",
    "fuzzy_name",
    "semantic",
)


class SearchSettings(ConfiguredSettings):
    """Validated search, query-embedding request, comparison, recommendation, and route policy."""

    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    semantic_search_min_score: float = Field(
        validation_alias="SEMANTIC_SEARCH_MIN_SCORE",
        ge=-1,
        le=1,
        allow_inf_nan=False,
    )
    fuzzy_search_min_score: float = Field(
        validation_alias="FUZZY_SEARCH_MIN_SCORE",
        ge=0,
        le=100,
        allow_inf_nan=False,
    )
    fuzzy_token_match_weight: float = Field(
        validation_alias="FUZZY_TOKEN_MATCH_WEIGHT", gt=0, le=1, allow_inf_nan=False
    )
    search_embedding_request_timeout_seconds: float = Field(
        validation_alias="SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS",
        gt=0,
        allow_inf_nan=False,
    )
    search_embedding_max_attempts: int = Field(
        validation_alias="SEARCH_EMBEDDING_MAX_ATTEMPTS", ge=1
    )
    search_tier_priority: tuple[SearchMethod, ...] = Field(validation_alias="SEARCH_TIER_PRIORITY")
    comparison_name_weight: float = Field(
        validation_alias="COMPARISON_NAME_WEIGHT", gt=0, allow_inf_nan=False
    )
    comparison_content_weight: float = Field(
        validation_alias="COMPARISON_CONTENT_WEIGHT", gt=0, allow_inf_nan=False
    )
    comparison_outcomes_weight: float = Field(
        validation_alias="COMPARISON_OUTCOMES_WEIGHT", gt=0, allow_inf_nan=False
    )
    comparison_overlap_floor: float = Field(
        validation_alias="COMPARISON_OVERLAP_FLOOR", ge=0, le=1, allow_inf_nan=False
    )
    comparison_overlap_ceiling: float = Field(
        validation_alias="COMPARISON_OVERLAP_CEILING", ge=0, le=1, allow_inf_nan=False
    )
    comparison_heavy_overlap_percent: float = Field(
        validation_alias="COMPARISON_HEAVY_OVERLAP_PERCENT", ge=0, le=100, allow_inf_nan=False
    )
    comparison_partial_overlap_percent: float = Field(
        validation_alias="COMPARISON_PARTIAL_OVERLAP_PERCENT", ge=0, le=100, allow_inf_nan=False
    )
    comparison_same_area_percent: float = Field(
        validation_alias="COMPARISON_SAME_AREA_PERCENT", ge=0, le=100, allow_inf_nan=False
    )
    comparison_loose_related_percent: float = Field(
        validation_alias="COMPARISON_LOOSE_RELATED_PERCENT", ge=0, le=100, allow_inf_nan=False
    )
    prerequisite_path_max_compact_nodes: int = Field(
        validation_alias="PREREQUISITE_PATH_MAX_COMPACT_NODES", gt=0
    )
    recommendation_chunk_top_k: int = Field(validation_alias="RECOMMENDATION_CHUNK_TOP_K", gt=0)
    recommendation_min_relatedness: float = Field(
        validation_alias="RECOMMENDATION_MIN_RELATEDNESS",
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    recommendation_near_duplicate_percent: float = Field(
        validation_alias="RECOMMENDATION_NEAR_DUPLICATE_PERCENT",
        ge=0,
        le=100,
        allow_inf_nan=False,
    )
    recommendation_overlap_penalty_weight: float = Field(
        validation_alias="RECOMMENDATION_OVERLAP_PENALTY_WEIGHT",
        ge=0,
        le=1,
        allow_inf_nan=False,
    )

    @field_validator("search_tier_priority")
    @classmethod
    def validate_search_tier_priority(
        cls, value: tuple[SearchMethod, ...]
    ) -> tuple[SearchMethod, ...]:
        """Require one occurrence of every match method in the config-owned primary-tier order."""
        if len(value) != len(_SEARCH_METHODS) or set(value) != set(_SEARCH_METHODS):
            raise ValueError(
                "SEARCH_TIER_PRIORITY must contain each of exact_code, substring, fuzzy_name, "
                "and semantic exactly once"
            )
        return value

    @model_validator(mode="after")
    def validate_comparison_threshold_order(self) -> Self:
        """Require the partial and loose thresholds to stay below their upper neighbours."""
        if self.comparison_overlap_floor >= self.comparison_overlap_ceiling:
            raise ValueError("COMPARISON_OVERLAP_FLOOR must be below COMPARISON_OVERLAP_CEILING")
        if self.comparison_partial_overlap_percent >= self.comparison_heavy_overlap_percent:
            raise ValueError(
                "COMPARISON_PARTIAL_OVERLAP_PERCENT must be below COMPARISON_HEAVY_OVERLAP_PERCENT"
            )
        if self.comparison_loose_related_percent >= self.comparison_same_area_percent:
            raise ValueError(
                "COMPARISON_LOOSE_RELATED_PERCENT must be below COMPARISON_SAME_AREA_PERCENT"
            )
        return self


def load_search_settings() -> SearchSettings:
    """Read search settings through the automatic public/local configuration composition."""
    return SearchSettings()
