"""An assisted exercise's weight is the assistance, and the tool says so.

wger's weight field is non-negative and carries no meaning of its own. For an
exercise registered as assisted, the number is the help the machine gave, so a
caller that forgets to say so would file that help as load added to the lift. A
log cannot be corrected afterwards, so the tool refuses the call instead.
"""

from __future__ import annotations

from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from wger_api_client import models as api_models

from wger_mcp.api_client import build_api_client
from wger_mcp.config import Settings
from wger_mcp.tools import workout_logs

ASSISTED = 1929
LOG = api_models.WorkoutLog(exercise=ASSISTED)


class _StubProvider:
    async def authorization_header(self) -> str:
        return "Token dev"

    async def aclose(self) -> None:
        pass


class _Capture:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.result

    @property
    def body(self) -> Any:
        return self.calls[-1]["body"]


def _register(assisted_ids: list[int]) -> FastMCP:
    mcp = FastMCP("test")
    settings = Settings(  # type: ignore[call-arg]
        wger_base_url="https://wger.test",
        mcp_auth="none",
        wger_dev_token="dev",
        wger_assisted_exercise_ids=assisted_ids,
    )
    workout_logs.register(mcp, build_api_client(settings, _StubProvider()), settings)
    return mcp


def _result(raw: Any) -> Any:
    return raw[1] if isinstance(raw, tuple) else raw


def _creator(monkeypatch: pytest.MonkeyPatch) -> _Capture:
    create = _Capture(LOG)
    monkeypatch.setattr(workout_logs.workoutlog_create, "asyncio", create)
    return create


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{}, {"load_kind": "added"}])
async def test_an_assisted_exercise_logged_without_saying_so_is_refused(
    monkeypatch: pytest.MonkeyPatch, extra: dict[str, Any]
) -> None:
    mcp = _register([ASSISTED])
    create = _creator(monkeypatch)
    out = _result(
        await mcp.call_tool(
            "log_set", {"exercise_id": str(ASSISTED), "reps": 8, "weight": 40, **extra}
        )
    )
    assert out["error"] is True
    assert out["status"] == 400
    assert "assist" in out["detail"]
    assert create.calls == []


@pytest.mark.asyncio
async def test_declaring_assisted_on_an_unregistered_exercise_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = _register([ASSISTED])
    create = _creator(monkeypatch)
    out = _result(
        await mcp.call_tool(
            "log_set",
            {"exercise_id": "73", "reps": 8, "weight": 40, "load_kind": "assisted"},
        )
    )
    assert out["error"] is True
    assert out["status"] == 400
    assert "WGER_ASSISTED_EXERCISE_IDS" in out["detail"]
    assert create.calls == []


@pytest.mark.asyncio
async def test_an_assisted_exercise_declared_as_assisted_stores_the_assistance_as_weight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = _register([ASSISTED])
    create = _creator(monkeypatch)
    await mcp.call_tool(
        "log_set",
        {"exercise_id": str(ASSISTED), "reps": 8, "weight": 40, "load_kind": "assisted"},
    )
    assert float(create.body.weight) == 40
    assert create.body.exercise == ASSISTED


@pytest.mark.asyncio
async def test_a_plain_set_is_unchanged_when_assisted_exercises_are_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = _creator(monkeypatch)
    await _register([ASSISTED]).call_tool(
        "log_set", {"exercise_id": "73", "reps": 8, "weight": 80, "weight_unit": "kg"}
    )
    plain = _creator(monkeypatch)
    await _register([]).call_tool(
        "log_set", {"exercise_id": "73", "reps": 8, "weight": 80, "weight_unit": "kg"}
    )
    assert configured.body.to_dict() == plain.body.to_dict()
