"""In-memory draft store for the web API.

Each draft owns an open :class:`WorkoutParserSession` so we can pause on a
clarification question and resume later from another HTTP request.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .models import Workout
from .parser import WorkoutParserSession


@dataclass
class Draft:
    id: str
    session: WorkoutParserSession
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    workout: Optional[Workout] = None
    last_question: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class DraftStore:
    """Very small in-process registry of active drafts."""

    def __init__(self) -> None:
        self._drafts: dict[str, Draft] = {}
        self._global_lock = asyncio.Lock()

    async def create(self, model: Optional[str] = None) -> Draft:
        session = WorkoutParserSession(model=model)
        await session.__aenter__()
        draft = Draft(id=uuid.uuid4().hex, session=session)
        async with self._global_lock:
            self._drafts[draft.id] = draft
        return draft

    def get(self, draft_id: str) -> Draft | None:
        return self._drafts.get(draft_id)

    async def delete(self, draft_id: str) -> bool:
        async with self._global_lock:
            draft = self._drafts.pop(draft_id, None)
        if draft is None:
            return False
        try:
            await draft.session.__aexit__(None, None, None)
        except Exception:
            pass
        return True

    async def close_all(self) -> None:
        async with self._global_lock:
            drafts = list(self._drafts.values())
            self._drafts.clear()
        for draft in drafts:
            try:
                await draft.session.__aexit__(None, None, None)
            except Exception:
                pass
