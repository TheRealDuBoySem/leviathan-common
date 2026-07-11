import asyncio
import logging

import pytest

from leviathan_common.infrastructure.asyncio_guards import install_unhandled_task_logger


@pytest.mark.asyncio
async def test_install_unhandled_task_logger_logs_task_failures(caplog):
    caplog.set_level(logging.ERROR, logger="leviathan_common.infrastructure.asyncio_guards")

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        log = logging.getLogger("leviathan_common.infrastructure.asyncio_guards")
        install_unhandled_task_logger(loop, log)

        async def _fail() -> None:
            raise RuntimeError("boom")

        asyncio.create_task(_fail())
        await asyncio.sleep(0.05)

    await _run()
    assert any("Unhandled asyncio exception" in record.message for record in caplog.records)
    assert any("policy=tolerant" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_install_unhandled_task_logger_logs_message_only_context(caplog):
    caplog.set_level(logging.ERROR)

    loop = asyncio.get_running_loop()
    log = logging.getLogger("test.asyncio.guards.message_only")
    install_unhandled_task_logger(loop, log)

    loop.call_exception_handler({"message": "callback failure"})

    assert any(
        "Unhandled asyncio exception (policy=tolerant): callback failure" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_install_unhandled_task_logger_uses_default_message_when_blank(caplog):
    caplog.set_level(logging.ERROR)
    loop = asyncio.get_running_loop()
    log = logging.getLogger("test.asyncio.guards.blank_message")
    install_unhandled_task_logger(loop, log)
    loop.call_exception_handler({"message": "   "})
    assert any(
        "Unhandled asyncio exception (policy=tolerant): Unhandled asyncio exception"
        in record.message
        for record in caplog.records
    )


def test_install_unhandled_task_logger_rejects_invalid_loop():
    with pytest.raises(TypeError, match="loop must be an asyncio.AbstractEventLoop"):
        install_unhandled_task_logger(object())  # type: ignore[arg-type]


def test_install_unhandled_task_logger_rejects_invalid_logger():
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(TypeError, match="logger must be a logging.Logger"):
            install_unhandled_task_logger(loop, "not-a-logger")  # type: ignore[arg-type]
    finally:
        loop.close()
