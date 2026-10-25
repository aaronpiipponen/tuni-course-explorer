"""Proofs of the front router's heavy placement, light placement and load score meter."""

from __future__ import annotations

import asyncio
import logging
import time
import types

import httpx
import pytest

from course_explorer.config import AdmissionSettings
from course_explorer_web.admission import host_cpu
from course_explorer_web.router import app as router_app
from course_explorer_web.router.app import create_router
from tests.support import settings_factory
from tests.web._router_support import WorkerHarness, recommendation_body, search_body, wait_for


def _cookie(value: str) -> dict[str, str]:
    return {"cookie": f"tce_anon={value}"}


def test_heavy_requests_place_on_workers_without_a_heavy_request() -> None:
    """Three concurrent heavy requests take three distinct workers and release their slots."""
    harness = WorkerHarness()
    settings = settings_factory(AdmissionSettings, ADMISSION_ENABLED="1", WEB_WORKERS="4")

    async def exercise() -> None:
        application = create_router(
            workers=harness.addresses,
            settings=settings,
            client=harness.client(),
        )
        await application.startup()
        assert application.state is not None
        try:
            harness.hold()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application), base_url="http://router"
            ) as client:
                pending = [
                    asyncio.create_task(
                        client.post(
                            "/api/recommendations",
                            json=recommendation_body(50, active_only=False),
                            headers=_cookie(letter * 32),
                        )
                    )
                    for letter in "abc"
                ]
                await wait_for(lambda: application.state.running_heavy == 3)
                assert len({call.worker for call in harness.calls}) == 3
                assert {call.worker for call in harness.calls} == {0, 1, 2}
                harness.release()
                responses = await asyncio.gather(*pending)
                assert [response.status_code for response in responses] == [200, 200, 200]
            assert application.state.running_heavy == 0
        finally:
            await application.shutdown()

    asyncio.run(exercise())


def test_light_requests_forward_to_the_least_busy_worker() -> None:
    """A held worker takes no second request, and a tie picks the lowest worker index."""
    harness = WorkerHarness()
    settings = settings_factory(AdmissionSettings, ADMISSION_ENABLED="1", WEB_WORKERS="4")

    async def exercise() -> None:
        application = create_router(
            workers=harness.addresses,
            settings=settings,
            client=harness.client(),
        )
        await application.startup()
        try:
            harness.hold()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application), base_url="http://router"
            ) as client:
                first = asyncio.create_task(client.post("/api/catalogue", json={}))
                await wait_for(lambda: len(harness.calls) == 1)
                second = asyncio.create_task(client.post("/api/catalogue", json={}))
                await wait_for(lambda: len(harness.calls) == 2)
                assert [call.worker for call in harness.calls] == [0, 1]
                harness.release()
                assert (await first).status_code == 200
                assert (await second).status_code == 200
        finally:
            await application.shutdown()

    asyncio.run(exercise())


def test_router_treats_an_unreadable_meter_as_unloaded(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unreadable counter logs one error and clears the CPU, the score and the latch, not activity."""
    harness = WorkerHarness()
    settings = settings_factory(
        AdmissionSettings,
        ADMISSION_ENABLED="1",
        ADMISSION_LOAD_WINDOW_SECONDS="2",
        ADMISSION_SCORE_LIGHT_WEIGHT="0.05",
    )
    wall_second = [100]
    busy = [100.0]
    monkeypatch.setattr(
        router_app,
        "time",
        types.SimpleNamespace(time=lambda: wall_second[0], monotonic=time.monotonic),
    )
    # The expected utilisation below is arithmetic over four cores, whatever the host has.
    monkeypatch.setattr(host_cpu, "core_count", lambda: 4)

    async def exercise() -> None:
        application = create_router(
            workers=harness.addresses,
            settings=settings,
            client=harness.client(),
        )
        await application.startup()
        assert application.state is not None
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application), base_url="http://router"
            ) as client:
                admitted = await client.post(
                    "/api/search", json=search_body(), headers=_cookie("a" * 32)
                )
                assert admitted.status_code == 200

            monkeypatch.setattr(host_cpu, "busy_cpu_seconds", lambda: busy[0])
            await application.sample_once()
            assert application.state.cpu_utilisation == pytest.approx(0.0)

            # Four host core-seconds in each of the window's two one-second buckets fill the window
            # of a four-core host, and the admitted light read adds its weight at the saturation
            # line.
            busy[0] = 104.0
            wall_second[0] = 101
            await application.sample_once()
            assert application.state.cpu_utilisation == pytest.approx(0.5)
            busy[0] = 108.0
            wall_second[0] = 102
            await application.sample_once()
            assert application.state.score == pytest.approx(1.05)
            assert application.state.saturated is True
            assert application.state.load_position == pytest.approx(1.0)

            def unreadable() -> float:
                raise OSError("synthetic unreadable counter")

            monkeypatch.setattr(host_cpu, "busy_cpu_seconds", unreadable)
            with caplog.at_level(logging.ERROR, logger="course_explorer_web.router.app"):
                await application.sample_once()
            assert application.state.cpu_utilisation == pytest.approx(0.0)
            assert application.state.score == pytest.approx(0.0)
            assert application.state.light_window == 0
            assert application.state.saturated is False
            assert application.state.load_position == pytest.approx(0.0)

            # The next good sample starts a fresh CPU baseline and still counts the admitted read.
            busy[0] = 200.0
            monkeypatch.setattr(host_cpu, "busy_cpu_seconds", lambda: busy[0])
            wall_second[0] = 103
            await application.sample_once()
            assert application.state.cpu_utilisation == pytest.approx(0.0)
            assert application.state.light_window == 1
            assert application.state.score == pytest.approx(0.05)
            assert application.state.load_position == pytest.approx(0.0)
        finally:
            await application.shutdown()

    asyncio.run(exercise())
    errors = [
        record
        for record in caplog.records
        if record.name == "course_explorer_web.router.app" and record.levelno == logging.ERROR
    ]
    assert len(errors) == 1
    assert errors[0].exc_info is None
