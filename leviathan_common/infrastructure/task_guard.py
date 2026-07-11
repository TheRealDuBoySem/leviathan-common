"""Unified asyncio background-task failure policies for Leviathan.

Applies Strategy (``TaskFailurePolicy``) and circuit-breaker
(``DegradedRecoveryPolicy``) patterns via done-callbacks on ``asyncio.Task``
instances.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional


class TaskFailurePolicy(str, Enum):
    """
    Declares how a background task failure affects the hosting component.

    TOLERANT:
        Log ERROR and continue. The orchestrator keeps running; no recovery hook.
        Use for fire-and-forget side effects and loops that already catch transient errors.

    DEGRADED:
        Log CRITICAL, apply a circuit breaker (backoff + max consecutive failures),
        then invoke on_degraded to re-spawn the periodic loop when allowed.
        Does NOT trigger supervisor respawn — recovery is local unless the circuit
        opens and on_fatal is configured.

    FATAL:
        Log CRITICAL, invoke on_fatal (controlled shutdown / supervisor respawn).
        Use for tasks whose death means the process cannot trade safely.
    """

    TOLERANT = "tolerant"
    DEGRADED = "degraded"
    FATAL = "fatal"


@dataclass(frozen=True)
class DegradedRecoveryPolicy:
    """
    Limits tight respawn loops for DEGRADED background tasks.

    After each uncaught failure the guard increments a per-task counter, waits
    with exponential backoff, then calls on_degraded. When consecutive failures
    reach max_consecutive_failures the circuit opens: no further respawns; on_fatal
    is invoked when configured and escalate_to_fatal_on_circuit_open is True.
    """

    max_consecutive_failures: int = 10
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    escalate_to_fatal_on_circuit_open: bool = True

    def __post_init__(self) -> None:
        if self.max_consecutive_failures <= 0:
            raise ValueError("max_consecutive_failures must be strictly positive")
        if self.initial_backoff_seconds < 0:
            raise ValueError("initial_backoff_seconds must be non-negative")
        if self.max_backoff_seconds <= 0:
            raise ValueError("max_backoff_seconds must be strictly positive")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= initial_backoff_seconds")

    def backoff_seconds(self, consecutive_failures: int) -> float:
        if consecutive_failures <= 0:
            return 0.0
        delay = self.initial_backoff_seconds * (2 ** (consecutive_failures - 1))
        return min(delay, self.max_backoff_seconds)


FatalCallback = Callable[[str, BaseException], None]
DegradedCallback = Callable[[str, BaseException], None]


def _normalize_task_name(task_name: str) -> str:
    if not isinstance(task_name, str) or not task_name.strip():
        raise ValueError("task_name must be a non-empty string")
    return task_name.strip()


def _validate_failure_policy(policy: TaskFailurePolicy) -> None:
    if not isinstance(policy, TaskFailurePolicy):
        raise TypeError("policy must be a TaskFailurePolicy instance")


class BackgroundTaskGuard:
    """
    Attaches done-callbacks that apply a documented failure policy per task name.

    Use one guard per orchestrating component (Engine, SetupExecutor, etc.).
    """

    def __init__(
        self,
        component: str,
        logger: logging.Logger,
        on_fatal: Optional[FatalCallback] = None,
        on_degraded: Optional[DegradedCallback] = None,
        degraded_recovery_policy: Optional[DegradedRecoveryPolicy] = None,
    ) -> None:
        """
        Preconditions:
            component must be a non-empty string.
            logger must be a logging.Logger instance.
            on_fatal and on_degraded must be callable when provided.
        """
        if not isinstance(component, str) or not component.strip():
            raise ValueError("component must be a non-empty string")
        if not isinstance(logger, logging.Logger):
            raise TypeError("logger must be a logging.Logger instance")
        if on_fatal is not None and not callable(on_fatal):
            raise TypeError("on_fatal must be callable when provided")
        if on_degraded is not None and not callable(on_degraded):
            raise TypeError("on_degraded must be callable when provided")

        self.__component = component.strip()
        self.__logger = logger
        self.__on_fatal = on_fatal
        self.__on_degraded = on_degraded
        self.__degraded_recovery_policy = (
            degraded_recovery_policy or DegradedRecoveryPolicy()
        )
        self.__degraded_consecutive_failures: Dict[str, int] = {}

    def attach(
        self,
        task: asyncio.Task,
        task_name: str,
        policy: TaskFailurePolicy = TaskFailurePolicy.TOLERANT,
    ) -> None:
        """
        Register a done-callback on task that applies policy on completion.

        Preconditions:
            task must be an asyncio.Task instance.
            task_name must be a non-empty string.
            policy must be a TaskFailurePolicy instance.
        """
        if not isinstance(task, asyncio.Task):
            raise TypeError("task must be an asyncio.Task instance")
        normalized_name = _normalize_task_name(task_name)
        _validate_failure_policy(policy)
        task.add_done_callback(
            lambda completed: self.handle_completed(normalized_name, policy, completed)
        )

    def make_done_callback(
        self,
        task_name: str,
        policy: TaskFailurePolicy = TaskFailurePolicy.TOLERANT,
    ) -> Callable[[asyncio.Task], None]:
        """
        Build a done-callback for callers that manage task creation themselves.

        Preconditions:
            task_name must be a non-empty string.
            policy must be a TaskFailurePolicy instance.
        """
        normalized_name = _normalize_task_name(task_name)
        _validate_failure_policy(policy)

        def _callback(task: asyncio.Task) -> None:
            self.handle_completed(normalized_name, policy, task)

        return _callback

    def handle_completed(
        self,
        task_name: str,
        policy: TaskFailurePolicy,
        task: asyncio.Task,
    ) -> None:
        """
        Apply policy to a completed task (success, cancellation, or failure).

        Preconditions:
            task_name must be a non-empty string.
            policy must be a TaskFailurePolicy instance.
            task must be an asyncio.Task instance.
        Postconditions:
            Successful DEGRADED tasks reset the per-task failure counter.
            Cancelled tasks produce no logs and invoke no callbacks.
        """
        normalized_name = _normalize_task_name(task_name)
        _validate_failure_policy(policy)
        if not isinstance(task, asyncio.Task):
            raise TypeError("task must be an asyncio.Task instance")

        try:
            task.result()
            if policy == TaskFailurePolicy.DEGRADED:
                self.__degraded_consecutive_failures.pop(normalized_name, None)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            message = (
                f"{self.__component}: background task '{normalized_name}' failed "
                f"(policy={policy.value})"
            )
            if policy == TaskFailurePolicy.TOLERANT:
                self.__logger.error(message, exc_info=exc)
                return
            self.__logger.critical(message, exc_info=exc)
            if policy == TaskFailurePolicy.DEGRADED:
                self.__handle_degraded_failure(normalized_name, exc)
            elif policy == TaskFailurePolicy.FATAL:
                self.__invoke_fatal_callback(normalized_name, exc)

    def __invoke_fatal_callback(self, task_name: str, exc: BaseException) -> None:
        if self.__on_fatal is not None:
            self.__on_fatal(task_name, exc)
            return
        self.__logger.warning(
            "%s: FATAL policy for '%s' but no on_fatal callback configured",
            self.__component,
            task_name,
        )

    def __handle_degraded_failure(self, task_name: str, exc: BaseException) -> None:
        if self.__on_degraded is None:
            self.__logger.warning(
                "%s: DEGRADED policy for '%s' but no on_degraded callback configured",
                self.__component,
                task_name,
            )
            return

        consecutive = self.__degraded_consecutive_failures.get(task_name, 0) + 1
        self.__degraded_consecutive_failures[task_name] = consecutive
        policy = self.__degraded_recovery_policy

        if consecutive >= policy.max_consecutive_failures:
            self.__logger.critical(
                "%s: degraded circuit open for '%s' after %s consecutive failures "
                "(max=%s)",
                self.__component,
                task_name,
                consecutive,
                policy.max_consecutive_failures,
            )
            if (
                policy.escalate_to_fatal_on_circuit_open
                and self.__on_fatal is not None
            ):
                self.__on_fatal(task_name, exc)
            return

        backoff = policy.backoff_seconds(consecutive)
        self.__logger.warning(
            "%s: scheduling degraded recovery for '%s' in %.1fs "
            "(failure %s/%s)",
            self.__component,
            task_name,
            backoff,
            consecutive,
            policy.max_consecutive_failures,
        )

        def _deferred_recover() -> None:
            self.__on_degraded(task_name, exc)

        try:
            loop = asyncio.get_running_loop()
            if backoff <= 0:
                loop.call_soon(_deferred_recover)
            else:
                loop.call_later(backoff, _deferred_recover)
        except RuntimeError:
            _deferred_recover()
