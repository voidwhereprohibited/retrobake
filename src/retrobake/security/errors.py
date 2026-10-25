"""Exceptions raised by the safety layer. ``message`` is always plain English for the UI."""

from __future__ import annotations


class InputRejected(ValueError):
    """User text that cannot be made safe. Show ``message`` to the user as-is."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


class OutputRejected(ValueError):
    """An AI result (name or image) that failed validation. Fall back to offline output."""


class SandboxError(RuntimeError):
    """A build step broke a sandbox rule (bad path, unknown program, time/size limit)."""
