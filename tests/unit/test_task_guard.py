import asyncio
import logging

import pytest

from leviathan_common.infrastructure.task_guard import (
    BackgroundTaskGuard,
    DegradedRecoveryPolicy,
    TaskFailurePolicy,
)

_IMMEDIATE_DEGRADED = DegradedRecoveryPolicy(initial_backoff_seconds=0.0)


@pytest.mark.asyncio
async def test_task_guard_tolerant_logs_error_only(caplog):
    caplog.set_level(logging.ERROR)
    guard = BackgroundTaskGuard("TestComponent", logging.getLogger("test.tolerant"))

    async def _fail() -> None:
        raise RuntimeError("tolerant failure")

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("worker", TaskFailurePolicy.TOLERANT, task)

    assert any("policy=tolerant" in record.message for record in caplog.records)
    assert not any(record.levelno >= logging.CRITICAL for record in caplog.records)


@pytest.mark.asyncio
async def test_task_guard_fatal_invokes_on_fatal():
    fatal_calls: list[tuple[str, BaseException]] = []

    def _on_fatal(task_name: str, exc: BaseException) -> None:
        fatal_calls.append((task_name, exc))

    guard = BackgroundTaskGuard(
        "Engine",
        logging.getLogger("test.fatal"),
        on_fatal=_on_fatal,
    )

    async def _fail() -> None:
        raise RuntimeError("fatal failure")

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("streaming", TaskFailurePolicy.FATAL, task)

    assert fatal_calls
    assert fatal_calls[0][0] == "streaming"
    assert isinstance(fatal_calls[0][1], RuntimeError)


@pytest.mark.asyncio
async def test_task_guard_degraded_invokes_on_degraded():
    degraded_calls: list[tuple[str, BaseException]] = []

    def _on_degraded(task_name: str, exc: BaseException) -> None:
        degraded_calls.append((task_name, exc))

    guard = BackgroundTaskGuard(
        "Engine",
        logging.getLogger("test.degraded.recover"),
        on_degraded=_on_degraded,
        degraded_recovery_policy=_IMMEDIATE_DEGRADED,
    )

    async def _fail() -> None:
        raise RuntimeError("degraded failure")

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, task)
    await asyncio.sleep(0)

    assert degraded_calls
    assert degraded_calls[0][0] == "checkpoint_save"


@pytest.mark.asyncio
async def test_task_guard_degraded_does_not_invoke_on_fatal():
    fatal_calls: list[str] = []
    guard = BackgroundTaskGuard(
        "SetupExecutor",
        logging.getLogger("test.degraded"),
        on_fatal=lambda name, _exc: fatal_calls.append(name),
        degraded_recovery_policy=_IMMEDIATE_DEGRADED,
    )

    async def _fail() -> None:
        raise RuntimeError("degraded failure")

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("reconciliation", TaskFailurePolicy.DEGRADED, task)
    await asyncio.sleep(0)

    assert fatal_calls == []


def test_degraded_recovery_policy_backoff_caps_at_max():
    policy = DegradedRecoveryPolicy(
        initial_backoff_seconds=1.0,
        max_backoff_seconds=60.0,
    )
    assert policy.backoff_seconds(1) == 1.0
    assert policy.backoff_seconds(2) == 2.0
    assert policy.backoff_seconds(7) == 60.0


def test_degraded_recovery_policy_rejects_invalid_limits():
    with pytest.raises(ValueError, match="max_consecutive_failures"):
        DegradedRecoveryPolicy(max_consecutive_failures=0)
    with pytest.raises(ValueError, match="max_backoff_seconds"):
        DegradedRecoveryPolicy(initial_backoff_seconds=10.0, max_backoff_seconds=5.0)
    with pytest.raises(ValueError, match="initial_backoff_seconds must be non-negative"):
        DegradedRecoveryPolicy(initial_backoff_seconds=-1.0)
    with pytest.raises(ValueError, match="max_backoff_seconds must be strictly positive"):
        DegradedRecoveryPolicy(max_backoff_seconds=0.0)


def test_degraded_recovery_policy_backoff_returns_zero_for_non_positive_failures():
    policy = DegradedRecoveryPolicy()
    assert policy.backoff_seconds(0) == 0.0


def test_task_guard_handle_completed_rejects_non_task():
    guard = BackgroundTaskGuard("Engine", logging.getLogger("test.non.task"))
    with pytest.raises(TypeError, match="task must be an asyncio.Task instance"):
        guard.handle_completed("worker", TaskFailurePolicy.TOLERANT, "not-a-task")  # type: ignore[arg-type]


def test_task_guard_degraded_recovery_falls_back_without_running_loop():
    calls: list[str] = []
    guard = BackgroundTaskGuard(
        "Engine",
        logging.getLogger("test.no.loop"),
        on_degraded=lambda name, _exc: calls.append(name),
        degraded_recovery_policy=_IMMEDIATE_DEGRADED,
    )

    async def _create_failed_task() -> asyncio.Task:
        async def _fail() -> None:
            raise RuntimeError("degraded failure")

        task = asyncio.create_task(_fail())
        await asyncio.sleep(0)
        return task

    failed_task = asyncio.run(_create_failed_task())
    guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, failed_task)
    assert calls == ["checkpoint_save"]


@pytest.mark.asyncio
async def test_task_guard_degraded_backoff_delays_recovery(mocker):
    degraded_calls: list[str] = []
    guard = BackgroundTaskGuard(
        "Engine",
        logging.getLogger("test.degraded.backoff"),
        on_degraded=lambda name, _exc: degraded_calls.append(name),
        degraded_recovery_policy=DegradedRecoveryPolicy(
            initial_backoff_seconds=5.0,
            max_consecutive_failures=10,
        ),
    )
    call_later = mocker.patch("asyncio.get_running_loop")

    async def _fail() -> None:
        raise RuntimeError("degraded failure")

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, task)

    assert degraded_calls == []
    loop = call_later.return_value
    loop.call_later.assert_called_once()
    delay, callback = loop.call_later.call_args[0]
    assert delay == 5.0
    callback()
    assert degraded_calls == ["checkpoint_save"]


@pytest.mark.asyncio
async def test_task_guard_degraded_circuit_open_invokes_fatal():
    fatal_calls: list[tuple[str, BaseException]] = []
    degraded_calls: list[str] = []

    guard = BackgroundTaskGuard(
        "Engine",
        logging.getLogger("test.degraded.circuit"),
        on_fatal=lambda name, exc: fatal_calls.append((name, exc)),
        on_degraded=lambda name, _exc: degraded_calls.append(name),
        degraded_recovery_policy=DegradedRecoveryPolicy(
            max_consecutive_failures=3,
            initial_backoff_seconds=0.0,
        ),
    )

    async def _fail() -> None:
        raise RuntimeError("degraded failure")

    for _ in range(2):
        task = asyncio.create_task(_fail())
        await asyncio.sleep(0)
        guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, task)
        await asyncio.sleep(0)

    assert len(degraded_calls) == 2
    assert fatal_calls == []

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, task)
    await asyncio.sleep(0)

    assert len(degraded_calls) == 2
    assert fatal_calls
    assert fatal_calls[0][0] == "checkpoint_save"


@pytest.mark.asyncio
async def test_task_guard_degraded_circuit_open_without_fatal_stops_respawn():
    degraded_calls: list[str] = []
    guard = BackgroundTaskGuard(
        "SetupExecutor",
        logging.getLogger("test.degraded.circuit.no_fatal"),
        on_degraded=lambda name, _exc: degraded_calls.append(name),
        degraded_recovery_policy=DegradedRecoveryPolicy(
            max_consecutive_failures=2,
            initial_backoff_seconds=0.0,
            escalate_to_fatal_on_circuit_open=True,
        ),
    )

    async def _fail() -> None:
        raise RuntimeError("degraded failure")

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("reconciliation", TaskFailurePolicy.DEGRADED, task)
    await asyncio.sleep(0)
    assert degraded_calls == ["reconciliation"]

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("reconciliation", TaskFailurePolicy.DEGRADED, task)
    await asyncio.sleep(0)
    assert degraded_calls == ["reconciliation"]


@pytest.mark.asyncio
async def test_task_guard_degraded_success_resets_failure_counter():
    degraded_calls: list[str] = []
    guard = BackgroundTaskGuard(
        "Engine",
        logging.getLogger("test.degraded.reset"),
        on_degraded=lambda name, _exc: degraded_calls.append(name),
        degraded_recovery_policy=DegradedRecoveryPolicy(
            max_consecutive_failures=2,
            initial_backoff_seconds=0.0,
        ),
    )

    async def _fail() -> None:
        raise RuntimeError("degraded failure")

    async def _ok() -> None:
        return None

    fail_task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, fail_task)
    await asyncio.sleep(0)
    assert degraded_calls == ["checkpoint_save"]

    ok_task = asyncio.create_task(_ok())
    await asyncio.sleep(0)
    guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, ok_task)

    fail_task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, fail_task)
    await asyncio.sleep(0)

    assert len(degraded_calls) == 2


def test_background_task_guard_rejects_invalid_constructor_args():
    with pytest.raises(ValueError, match="component"):
        BackgroundTaskGuard("", logging.getLogger("test.invalid"))
    with pytest.raises(TypeError, match="logger"):
        BackgroundTaskGuard("Engine", "not-a-logger")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="on_fatal"):
        BackgroundTaskGuard(
            "Engine",
            logging.getLogger("test.invalid"),
            on_fatal="not-callable",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="on_degraded"):
        BackgroundTaskGuard(
            "Engine",
            logging.getLogger("test.invalid"),
            on_degraded=42,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_task_guard_attach_rejects_invalid_arguments():
    guard = BackgroundTaskGuard("Engine", logging.getLogger("test.attach"))
    task = asyncio.create_task(asyncio.sleep(0))
    await asyncio.sleep(0)

    with pytest.raises(TypeError, match="task must be"):
        guard.attach("not-a-task", "worker")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="task_name"):
        guard.attach(task, "   ")
    with pytest.raises(TypeError, match="policy"):
        guard.attach(task, "worker", policy="fatal")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_task_guard_attach_invokes_policy_on_completion():
    fatal_calls: list[str] = []
    guard = BackgroundTaskGuard(
        "Engine",
        logging.getLogger("test.attach.callback"),
        on_fatal=lambda name, _exc: fatal_calls.append(name),
    )

    async def _fail() -> None:
        raise RuntimeError("attach failure")

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.attach(task, "streaming", TaskFailurePolicy.FATAL)
    await asyncio.sleep(0)

    assert fatal_calls == ["streaming"]


@pytest.mark.asyncio
async def test_task_guard_make_done_callback_invokes_policy():
    degraded_calls: list[str] = []
    guard = BackgroundTaskGuard(
        "SetupExecutor",
        logging.getLogger("test.make_callback"),
        on_degraded=lambda name, _exc: degraded_calls.append(name),
        degraded_recovery_policy=_IMMEDIATE_DEGRADED,
    )
    callback = guard.make_done_callback("reconciliation", TaskFailurePolicy.DEGRADED)

    async def _fail() -> None:
        raise RuntimeError("callback failure")

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    task.add_done_callback(callback)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert degraded_calls == ["reconciliation"]


@pytest.mark.asyncio
async def test_task_guard_cancelled_task_is_silent(caplog):
    caplog.set_level(logging.ERROR)
    guard = BackgroundTaskGuard("Engine", logging.getLogger("test.cancelled"))

    async def _wait() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(_wait())
    task.cancel()
    await asyncio.sleep(0)
    guard.handle_completed("worker", TaskFailurePolicy.FATAL, task)

    assert caplog.records == []


@pytest.mark.asyncio
async def test_task_guard_fatal_without_callback_logs_warning(caplog):
    caplog.set_level(logging.WARNING)
    guard = BackgroundTaskGuard("Engine", logging.getLogger("test.fatal.no_cb"))

    async def _fail() -> None:
        raise RuntimeError("fatal failure")

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("streaming", TaskFailurePolicy.FATAL, task)

    assert any(
        "no on_fatal callback configured" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_task_guard_degraded_without_callback_logs_warning(caplog):
    caplog.set_level(logging.WARNING)
    guard = BackgroundTaskGuard(
        "Engine",
        logging.getLogger("test.degraded.no_cb"),
        degraded_recovery_policy=_IMMEDIATE_DEGRADED,
    )

    async def _fail() -> None:
        raise RuntimeError("degraded failure")

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, task)

    assert any(
        "no on_degraded callback configured" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_task_guard_normalizes_task_name_for_degraded_counter():
    degraded_calls: list[str] = []
    guard = BackgroundTaskGuard(
        "Engine",
        logging.getLogger("test.normalize"),
        on_degraded=lambda name, _exc: degraded_calls.append(name),
        degraded_recovery_policy=DegradedRecoveryPolicy(
            max_consecutive_failures=3,
            initial_backoff_seconds=0.0,
        ),
    )

    async def _fail() -> None:
        raise RuntimeError("degraded failure")

    async def _ok() -> None:
        return None

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("  checkpoint_save  ", TaskFailurePolicy.DEGRADED, task)
    await asyncio.sleep(0)
    assert degraded_calls == ["checkpoint_save"]

    ok_task = asyncio.create_task(_ok())
    await asyncio.sleep(0)
    guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, ok_task)

    task = asyncio.create_task(_fail())
    await asyncio.sleep(0)
    guard.handle_completed("checkpoint_save", TaskFailurePolicy.DEGRADED, task)
    await asyncio.sleep(0)

    assert degraded_calls == ["checkpoint_save", "checkpoint_save"]


def test_degraded_recovery_policy_rejects_negative_initial_backoff():
    with pytest.raises(ValueError, match="initial_backoff_seconds"):
        DegradedRecoveryPolicy(initial_backoff_seconds=-1.0)
