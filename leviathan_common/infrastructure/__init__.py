"""Shared infrastructure utilities for Leviathan subsystems."""

from leviathan_common.infrastructure.asyncio_guards import install_unhandled_task_logger
from leviathan_common.infrastructure.runtime_logging import (
    HourlyCalendarFileHandler,
    RuntimeContextFilter,
    configure_runtime_logging,
    ensure_session_id,
    purge_old_hourly_logs,
    resolve_log_level,
    resolve_restart_generation,
    resolve_role,
)
from leviathan_common.infrastructure.task_guard import (
    BackgroundTaskGuard,
    DegradedRecoveryPolicy,
    TaskFailurePolicy,
)

__all__ = [
    "BackgroundTaskGuard",
    "DegradedRecoveryPolicy",
    "HourlyCalendarFileHandler",
    "RuntimeContextFilter",
    "TaskFailurePolicy",
    "configure_runtime_logging",
    "ensure_session_id",
    "install_unhandled_task_logger",
    "purge_old_hourly_logs",
    "resolve_log_level",
    "resolve_restart_generation",
    "resolve_role",
]
