"""Proofs of the admission classes, the graph cost cache, the router's limits and its queue."""

from __future__ import annotations

import asyncio
import re
import time
import types

import httpx
import pytest

from course_explorer.config import AdmissionSettings
from course_explorer_web.admission import policy
from course_explorer_web.admission import state as state_module
from course_explorer_web.admission.classify import (
    AdmissionClass,
    Classification,
    active_only_from_body,
    basis_size,
    classify,
    next_courses_cost,
    recommendation_cost,
)
from course_explorer_web.admission.state import AdmissionRefused, AdmissionState
from course_explorer_web.router.app import create_router
from course_explorer_web.serving import Route, route_of
from tests.support import settings_factory
from tests.web._router_support import WorkerHarness, recommendation_body, search_body

_COOKIE = re.compile(r"tce_anon=([0-9a-f]{32})")


def test_routes_take_their_admission_class_and_cost() -> None:
    """Each route takes its class, and the cost curves and load position drive the limits."""
    settings = settings_factory(AdmissionSettings, WEB_WORKERS="4")
    two_workers = settings_factory(AdmissionSettings, WEB_WORKERS="2")

    assert classify(Route.FEATURES, {}, settings).admission_class is AdmissionClass.FREE
    assert classify(Route.COURSE_SUMMARIES, {}, settings).admission_class is AdmissionClass.FREE
    for route in (Route.COMPARISON, Route.STUDY_STRUCTURE, Route.CATALOGUE):
        assert classify(route, {}, settings).admission_class is AdmissionClass.LIGHT
    assert route_of("/api/search") is Route.SEARCH
    assert route_of("/api/unknown") is None

    # Search is heavy unless the request excludes inactive courses, whatever its query length.
    inactive_search = classify(
        Route.SEARCH, {"query": "analysis", "display_language": "en"}, settings
    )
    assert inactive_search.admission_class is AdmissionClass.HEAVY
    assert inactive_search.cost == pytest.approx(2.5)
    assert classify(Route.SEARCH, search_body(), settings).admission_class is AdmissionClass.LIGHT

    assert basis_size({"completed_courses": ["a", "b", " ", "a"]}) == 2
    assert basis_size({"basis": "selected", "selected_courses": ["s"]}) == 1
    assert (
        basis_size(
            {
                "basis": "selected",
                "selected_courses": [],
                "completed_courses": ["c0", "c1"],
            }
        )
        == 2
    )

    assert active_only_from_body({}) is True
    assert active_only_from_body({"active_only": True}) is True
    assert active_only_from_body({"active_only": False}) is False

    # A recommendation is heavy from five courses in either scope.
    assert (
        classify(Route.RECOMMENDATIONS, recommendation_body(4), settings).admission_class
        is AdmissionClass.LIGHT
    )
    assert (
        classify(Route.RECOMMENDATIONS, recommendation_body(5), settings).admission_class
        is AdmissionClass.HEAVY
    )
    assert (
        classify(
            Route.RECOMMENDATIONS, recommendation_body(4, active_only=False), settings
        ).admission_class
        is AdmissionClass.LIGHT
    )
    assert (
        classify(
            Route.RECOMMENDATIONS, recommendation_body(5, active_only=False), settings
        ).admission_class
        is AdmissionClass.HEAVY
    )

    # A next-courses request is heavy from 63 active courses and from 26 with inactive courses.
    assert (
        classify(Route.NEXT_COURSES, recommendation_body(62), settings).admission_class
        is AdmissionClass.LIGHT
    )
    assert (
        classify(Route.NEXT_COURSES, recommendation_body(63), settings).admission_class
        is AdmissionClass.HEAVY
    )
    assert (
        classify(
            Route.NEXT_COURSES, recommendation_body(25, active_only=False), settings
        ).admission_class
        is AdmissionClass.LIGHT
    )
    assert (
        classify(
            Route.NEXT_COURSES, recommendation_body(26, active_only=False), settings
        ).admission_class
        is AdmissionClass.HEAVY
    )

    assert classify(Route.PREREQUISITES, {}, settings).admission_class is AdmissionClass.LIGHT
    assert (
        classify(Route.PREREQUISITES, {}, settings, graph_cost=0.99).admission_class
        is AdmissionClass.LIGHT
    )
    heavy_graph = classify(Route.PREREQUISITES, {}, settings, graph_cost=1.0)
    assert heavy_graph.admission_class is AdmissionClass.HEAVY
    assert heavy_graph.cost == pytest.approx(1.0)

    assert recommendation_cost(200, settings, active_only=True) == pytest.approx(35.3195)
    assert recommendation_cost(50, settings, active_only=False) == pytest.approx(19.14176)
    assert next_courses_cost(63, settings, active_only=True) == pytest.approx(1.0080485)
    assert next_courses_cost(26, settings, active_only=False) == pytest.approx(1.026186)

    assert policy.light_load_factor(0.5, settings) == pytest.approx(0.625)
    assert policy.heavy_budget(0.5, settings) == pytest.approx(72)
    assert policy.heavy_queue_limit(0.5, settings) == 32
    assert policy.heavy_slots(0.5, settings) == 2
    assert policy.light_concurrency(1.0, settings) == 2
    assert policy.heavy_slots(0.0, two_workers) == 1


def test_score_scales_admission_and_holds_saturation_until_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The score combines host CPU and light admissions, interpolates and releases its latch later."""
    settings = settings_factory(
        AdmissionSettings,
        WEB_WORKERS="4",
        ADMISSION_LOAD_WINDOW_SECONDS="10",
        ADMISSION_SCORE_CPU_WEIGHT="0.75",
        ADMISSION_SCORE_LIGHT_WEIGHT="0.01",
        ADMISSION_SCORE_HEADROOM="0.60",
        ADMISSION_SCORE_SATURATION="1.05",
        ADMISSION_SCORE_RELEASE="0.90",
    )
    now = [1000.0]
    monkeypatch.setattr(
        state_module, "time", types.SimpleNamespace(monotonic=lambda: now[0], time=time.time)
    )
    state = AdmissionState(settings, cores=4)
    assert state.sample(0.0, 100) == pytest.approx(0.0)

    def admit_lights(offset: int, count: int) -> None:
        for index in range(offset, offset + count):
            state.admit_light(f"{index:032x}")

    # Twenty-eight host core-seconds over a ten-second window on four cores give a CPU utilisation
    # of 0.7, and thirty admissions in the window add 0.3. The weighted score is the midpoint
    # between the headroom and saturation lines.
    now[0] = 1000.0
    admit_lights(0, 30)
    assert state.sample(28.0, 101) == pytest.approx(0.5)
    assert state.cpu_utilisation == pytest.approx(0.7)
    assert state.light_window == 30
    assert state.score == pytest.approx(0.825)
    assert policy.regime(state.load_position, settings) is policy.Regime.MIDDLE
    assert policy.heavy_slots(state.load_position, settings) == 2
    assert policy.light_load_factor(state.load_position, settings) == pytest.approx(0.625)
    assert policy.heavy_budget(state.load_position, settings) == pytest.approx(72)
    assert policy.heavy_queue_limit(state.load_position, settings) == 32

    # Fifteen more admissions add 0.15, and four more host core-seconds raise the window's total to
    # 32 of its 40, so the score reaches the saturation line exactly.
    now[0] = 1005.0
    admit_lights(30, 15)
    now[0] = 1008.0
    assert state.sample(32.0, 102) == pytest.approx(1.0)
    assert state.saturated is True
    assert state.score == pytest.approx(1.05)
    assert state.light_window == 45
    assert policy.regime(state.load_position, settings) is policy.Regime.SATURATED
    assert policy.heavy_slots(state.load_position, settings) == 1
    assert policy.light_load_factor(state.load_position, settings) == pytest.approx(0.25)
    assert policy.heavy_budget(state.load_position, settings) == pytest.approx(24)
    assert policy.heavy_queue_limit(state.load_position, settings) == 16

    # Eight more host core-seconds fill the window, and the thirty older admissions leave it. The
    # score of exactly the release line holds the latch.
    now[0] = 1015.0
    assert state.sample(40.0, 103) == pytest.approx(1.0)
    assert state.saturated is True
    assert state.score == pytest.approx(0.90)
    assert state.light_window == 15

    # The remaining admissions leave the window, and a score below the release line drops the latch
    # to the score's own interpolated position.
    now[0] = 1030.0
    assert state.sample(40.0, 104) == pytest.approx((0.75 - 0.60) / (1.05 - 0.60))
    assert state.saturated is False
    assert state.light_window == 0
    assert policy.regime(state.load_position, settings) is policy.Regime.MIDDLE


def test_heavy_activity_counts_recent_starts_and_older_running_requests_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The heavy window counts a recent start once, keeps a completion until expiry and skips a waiter."""
    settings = settings_factory(
        AdmissionSettings, WEB_WORKERS="4", ADMISSION_LOAD_WINDOW_SECONDS="10"
    )
    now = [1000.0]
    monkeypatch.setattr(
        state_module, "time", types.SimpleNamespace(monotonic=lambda: now[0], time=time.time)
    )
    heavy = Classification(AdmissionClass.HEAVY, 1.0)

    async def exercise() -> None:
        state = AdmissionState(settings, cores=4)
        assert state.sample(100.0, 10) == pytest.approx(0.0)

        recent = await state.admit_heavy("a" * 32, heavy)
        assert state.sample(100.0, 11) == pytest.approx(0.0)
        assert state.heavy_window == 1

        await state.release_heavy(recent)
        assert state.sample(100.0, 12) == pytest.approx(0.0)
        assert state.heavy_window == 1

        now[0] = 1005.0
        held = await state.admit_heavy("b" * 32, heavy)
        now[0] = 1015.1
        assert state.sample(100.0, 13) == pytest.approx(0.0)
        assert state.heavy_window == 1

        await state.release_heavy(held)
        assert state.sample(100.0, 14) == pytest.approx(0.0)
        assert state.heavy_window == 0

        now[0] = 1030.0
        running = [await state.admit_heavy(f"{letter}" * 32, heavy) for letter in "def"]
        waiter = asyncio.create_task(state.admit_heavy("g" * 32, heavy))
        for _ in range(200):
            if state.waiting_heavy == 1:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("the heavy ticket did not join the queue")
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        assert state.waiting_heavy == 0

        # The three running tickets start exactly on the cutoff and count once each. The cancelled
        # ticket never started.
        now[0] = 1040.0
        assert state.sample(100.0, 15) == pytest.approx(0.0)
        assert state.heavy_window == 3

        for ticket in running:
            await state.release_heavy(ticket)
        now[0] = 1040.1
        assert state.sample(100.0, 16) == pytest.approx(0.0)
        assert state.heavy_window == 0
        assert state.running_heavy == 0

    asyncio.run(exercise())


def test_graph_cost_cache_is_dataset_scoped() -> None:
    """A cached graph cost is per dataset identity and per request field, and it is overwritten."""
    settings = settings_factory(AdmissionSettings)
    state = AdmissionState(settings, cores=4)

    assert state.graph_cost("dataset-a", "COURSE.A|1|1|0") is None
    state.record_graph_cost("dataset-a", "COURSE.A|1|1|0", 1.25)
    assert state.graph_cost("dataset-a", "COURSE.A|1|1|0") == pytest.approx(1.25)
    state.record_graph_cost("dataset-a", "COURSE.A|1|1|0", 0.75)
    assert state.graph_cost("dataset-a", "COURSE.A|1|1|0") == pytest.approx(0.75)
    state.record_graph_cost("dataset-a", "COURSE.A|1|0|0", 2.5)
    assert state.graph_cost("dataset-a", "COURSE.A|1|0|0") == pytest.approx(2.5)
    assert state.graph_cost("dataset-a", "COURSE.A|1|1|0") == pytest.approx(0.75)

    state.record_graph_cost("dataset-b", "COURSE.B|1|1|0", 3.0)
    assert state.graph_cost("dataset-a", "COURSE.A|1|1|0") is None
    assert state.graph_cost("dataset-a", "COURSE.A|1|0|0") is None
    assert state.graph_cost("dataset-b", "COURSE.B|1|1|0") == pytest.approx(3.0)


def test_router_limits_cookies_and_records_refusals() -> None:
    """Each cookie is limited, free and refused reads add no activity, and admission off sends no cookie."""
    harness = WorkerHarness()
    settings = settings_factory(
        AdmissionSettings,
        ADMISSION_ENABLED="1",
        WEB_WORKERS="4",
        ADMISSION_LIGHT_BURST="1",
        ADMISSION_LIGHT_OPERATIONS_PER_MINUTE="1",
        ADMISSION_HEAVY_BUDGET_CORE_SECONDS="15",
    )

    async def post(
        client: httpx.AsyncClient, path: str, body: dict[str, object], cookie: str | None
    ) -> httpx.Response:
        headers = {} if cookie is None else {"cookie": f"tce_anon={cookie}"}
        return await client.post(path, json=body, headers=headers)

    async def exercise() -> None:
        application = create_router(
            workers=harness.addresses,
            settings=settings,
            client=harness.client(),
        )
        await application.startup()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application), base_url="http://router"
            ) as client:
                features = await post(client, "/api/features", {}, None)
                assert features.status_code == 200
                header = features.headers["set-cookie"].lower()
                match = _COOKIE.search(header)
                assert match is not None
                cookie_a = match.group(1)
                assert "httponly" in header
                assert "secure" in header
                assert "samesite=lax" in header
                assert "max-age=2592000" in header
                assert "path=/" in header

                assert (
                    await post(client, "/api/search", search_body(), cookie_a)
                ).status_code != 429
                refused = await post(client, "/api/search", search_body(), cookie_a)
                assert refused.status_code == 429
                assert refused.headers["retry-after"] == "5"
                assert (await post(client, "/api/features", {}, None)).status_code == 200

                cookie_b = "b" * 32
                assert (
                    await post(client, "/api/search", search_body(), cookie_b)
                ).status_code != 429
                assert (
                    await post(client, "/api/search", search_body(), cookie_b)
                ).status_code == 429

                malformed = await post(client, "/api/features", {}, "not-a-cookie")
                assert malformed.status_code == 200
                minted = _COOKIE.search(malformed.headers["set-cookie"].lower())
                assert minted is not None
                cookie_c = minted.group(1)
                assert cookie_c != "not-a-cookie"
                assert (
                    await post(client, "/api/search", search_body(), cookie_c)
                ).status_code != 429
                assert (
                    await post(client, "/api/search", search_body(), cookie_c)
                ).status_code == 429

                cookie_d = "d" * 32
                assert (
                    await post(client, "/api/recommendations", recommendation_body(50), cookie_d)
                ).status_code != 429
                refused_heavy = await post(
                    client, "/api/recommendations", recommendation_body(50), cookie_d
                )
                assert refused_heavy.status_code == 429
                assert refused_heavy.headers["retry-after"] == "5"
                assert (
                    await post(client, "/api/recommendations", recommendation_body(50), "e" * 32)
                ).status_code != 429

                for _ in range(3):
                    free = await post(
                        client, "/api/course-summaries", {"identifiers": []}, cookie_a
                    )
                    assert free.status_code == 200

                assert application.state is not None
                await application.sample_once()
                assert application.state.light_window == 3
                assert application.state.heavy_window == 2
        finally:
            await application.shutdown()

        off_harness = WorkerHarness()
        off_settings = settings_factory(AdmissionSettings, ADMISSION_ENABLED="0", WEB_WORKERS="4")
        off_application = create_router(
            workers=off_harness.addresses,
            settings=off_settings,
            client=off_harness.client(),
        )
        await off_application.startup()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=off_application), base_url="http://router"
            ) as client:
                forwarded = await post(client, "/api/features", {}, None)
                assert forwarded.status_code == 200
                assert "set-cookie" not in forwarded.headers
        finally:
            await off_application.shutdown()

    asyncio.run(exercise())


def test_heavy_queue_waits_at_saturation_and_refuses_at_its_cap() -> None:
    """A heavy read waits for a freed slot at saturation, and only a full queue refuses it."""
    settings = settings_factory(AdmissionSettings, ADMISSION_ENABLED="1", WEB_WORKERS="4")
    heavy = Classification(AdmissionClass.HEAVY, 1.0)

    async def exercise() -> None:
        state = AdmissionState(settings, cores=4)
        state.load_position = 1.0
        held = await state.admit_heavy("a" * 32, heavy)
        assert state.running_heavy == 1
        first_waiter = asyncio.create_task(state.admit_heavy("b" * 32, heavy))
        second_waiter = asyncio.create_task(state.admit_heavy("c" * 32, heavy))
        for _ in range(200):
            if state.waiting_heavy == 2:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("the heavy tickets did not join the queue")
        await asyncio.sleep(0.05)
        assert not first_waiter.done()
        assert not second_waiter.done()

        await state.release_heavy(held)
        first_ticket = await asyncio.wait_for(first_waiter, 1.0)
        assert state.running_heavy == 1
        assert not second_waiter.done()

        extra = [asyncio.create_task(state.admit_heavy(f"d{index}", heavy)) for index in range(15)]
        for _ in range(200):
            if state.waiting_heavy == 16:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("the heavy queue did not reach its cap")
        with pytest.raises(AdmissionRefused):
            await state.admit_heavy("z" * 32, heavy)

        await state.release_heavy(first_ticket)
        second_ticket = await asyncio.wait_for(second_waiter, 1.0)
        assert state.running_heavy == 1
        for task in extra:
            task.cancel()
        await asyncio.gather(*extra, return_exceptions=True)
        await state.release_heavy(second_ticket)
        assert state.running_heavy == 0

        # A running light ticket keeps its identity past the idle lifetime.
        tight_settings = settings_factory(AdmissionSettings, ADMISSION_LIGHT_CONCURRENCY="1")
        tight = AdmissionState(tight_settings, cores=4)
        tight.load_position = 1.0
        light_ticket = tight.admit_light("l" * 32)
        tight.expire(int(time.time()) + tight_settings.admission_identity_ttl_seconds + 1)
        with pytest.raises(AdmissionRefused):
            tight.admit_light("l" * 32)
        tight.release_light("l" * 32, light_ticket)

    asyncio.run(exercise())
