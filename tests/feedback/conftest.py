"""Fixtures for the feedback application store's disposable database, temporary attachments and HTTP
surface.

A proof that stores rows receives a freshly migrated ``_test`` database of the feedback chain alone,
the committed example definition and an attachment store under the test's temporary directory, and
the database is dropped by the shared scratch helper when the test ends. An HTTP site starts the real
front router over real worker applications, binds the one repository-root owner to a temporary root
that carries the committed example configuration, and substitutes the feedback route's settings and
resource composition. A refusal or body-bound proof composes that site without a database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import AdmissionSettings, FeedbackIntakeSettings
from course_explorer.db.session import create_session_factory
from course_explorer.feedback.attachments import AttachmentStore
from course_explorer.feedback.definition import FeedbackDefinition, load_feedback_definition
from course_explorer.feedback.service import FeedbackService
from course_explorer_web.app import create_app
from course_explorer_web.router.app import RouterApplication, create_router
from course_explorer_web.routes import feedback as feedback_routes
from tests.support import REPO_ROOT, settings_factory, write_example_config_tree
from tests.support.database import scratch_database
from tests.support.repository import bind_repository_root
from tests.web._router_support import WorkerHarness

FEEDBACK_HEAD = "20261103_feedback_0004"
SYNTHETIC_SERVING_GENERATION = "f" * 32
FEEDBACK_TABLES = {"feedback_attachments", "feedback_submissions"}
FEEDBACK_HTTP_ORIGIN = "https://feedback.example.org"


@pytest.fixture(autouse=True)
def _synthetic_serving_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supply one synthetic generation value, so the router starts without a serving parent."""
    monkeypatch.setenv("COURSE_EXPLORER_WEB_GENERATION", SYNTHETIC_SERVING_GENERATION)


@dataclass(frozen=True)
class FeedbackDatabase:
    """The migrated feedback database, its definition and its temporary attachment store."""

    engine: Engine
    factory: sessionmaker[Session]
    root: Path
    store_root: Path
    definition: FeedbackDefinition
    store: AttachmentStore


@dataclass(frozen=True)
class FeedbackHttpSite:
    """One started front router over real worker applications and the feedback route's composition.

    ``clock`` is the mutable monotonic value the router's feedback allowance reads, and
    ``repository_root`` is the temporary repository root the site's product reads and writes resolve
    under.
    """

    client: TestClient
    router: RouterApplication
    harness: WorkerHarness
    clock: list[float]
    repository_root: Path


def feedback_alembic_config(connection: Connection) -> Config:
    """Bind the feedback migration configuration to one caller-owned connection."""
    config = Config(str(REPO_ROOT / "alembic_feedback.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture()
def feedback_database(tmp_path: Path) -> Iterator[FeedbackDatabase]:
    """Migrate one disposable feedback database and yield its store with a temporary root."""
    root = write_example_config_tree(tmp_path / "checkout")
    store_root = tmp_path / "attachments"
    with scratch_database("course_feedback") as engine:
        with engine.connect() as connection:
            command.upgrade(feedback_alembic_config(connection), "head")
        yield FeedbackDatabase(
            engine=engine,
            factory=create_session_factory(engine),
            root=root,
            store_root=store_root,
            definition=load_feedback_definition(root),
            store=AttachmentStore(store_root),
        )


@pytest.fixture()
def feedback_http(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Callable[..., AbstractContextManager[FeedbackHttpSite]]:
    """Return a factory that starts one real HTTP site over the example configuration.

    The factory accepts an optional migrated feedback database, the ordinary-admission switch and
    an optional small request cap. The site's product reads and writes resolve under one temporary
    repository root that carries the committed example configuration and links the tracked product
    entries from this checkout, so the definition read, the feedback schema check and the usage
    record share the root the site runs with. A supplied database binds the route's resource
    composition to that store, and without one a submission that reaches the service composition
    fails.
    """

    def compose(
        *,
        database: FeedbackDatabase | None = None,
        admission_enabled: bool = False,
        max_request_bytes: int | None = None,
    ) -> AbstractContextManager[FeedbackHttpSite]:
        overrides: dict[str, object] = {"WEB_APP_URL": f"{FEEDBACK_HTTP_ORIGIN}/"}
        if max_request_bytes is not None:
            overrides["FEEDBACK_MAX_REQUEST_BYTES"] = max_request_bytes
        intake_settings = settings_factory(FeedbackIntakeSettings, **overrides)
        admission_settings = settings_factory(
            AdmissionSettings,
            WEB_WORKERS="2",
            ADMISSION_ENABLED="1" if admission_enabled else "0",
        )
        monkeypatch.setattr(
            feedback_routes, "load_feedback_intake_settings", lambda: intake_settings
        )
        definition_root = (
            write_example_config_tree(tmp_path / "definition")
            if database is None
            else database.root
        )
        repository_root = bind_repository_root(monkeypatch, definition_root)
        if database is None:

            @contextmanager
            def unavailable_feedback_context() -> Iterator[FeedbackService]:
                raise RuntimeError("feedback submission composition needs a supplied database")
                yield

            feedback_context = unavailable_feedback_context
        else:

            @contextmanager
            def local_feedback_context() -> Iterator[FeedbackService]:
                yield FeedbackService(
                    database.factory,
                    load_feedback_definition(repository_root),
                    database.store,
                )

            feedback_context = local_feedback_context
        monkeypatch.setattr(feedback_routes, "feedback_context", feedback_context)

        @contextmanager
        def start() -> Iterator[FeedbackHttpSite]:
            application = create_app(frontend_directory=tmp_path / "dist")
            harness = WorkerHarness((application, application))
            clock = [0.0]
            router = create_router(
                workers=harness.addresses[:2],
                settings=admission_settings,
                client=harness.client(),
                feedback_settings=intake_settings,
                feedback_clock=lambda: clock[0],
            )
            with TestClient(
                router,
                base_url=FEEDBACK_HTTP_ORIGIN,
                headers={"Origin": FEEDBACK_HTTP_ORIGIN},
            ) as client:
                yield FeedbackHttpSite(
                    client=client,
                    router=router,
                    harness=harness,
                    clock=clock,
                    repository_root=repository_root,
                )

        return start()

    return compose
