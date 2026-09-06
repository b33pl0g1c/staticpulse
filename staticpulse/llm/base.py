"""Provider-agnostic LLM interface.

Agents never touch a raw model string or HTTP call — they call
`LLMClient.complete(...)` and get back a Pydantic-validated result. That
keeps every agent testable with a fake client and free of network code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Base class for LLM failures."""


class LLMValidationError(LLMError):
    """Model output failed schema validation after the corrective retry."""


class LLMRateLimited(LLMError):
    """Provider returned a rate-limit / quota error."""


class LLMResult(BaseModel, Generic[T]):
    """The outcome of one `complete` call."""

    parsed: T
    tokens_in: int = 0
    tokens_out: int = 0
    cache_hit: bool = False


class LLMClient(ABC):
    """What every provider implements."""

    name: str = "abstract"
    model: str = "unknown"

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        prompt_version: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResult[T]:
        """Send one completion; return a validated, cost-accounted result."""
        raise NotImplementedError
