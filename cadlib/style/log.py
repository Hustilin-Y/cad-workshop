"""Style log: cosmetics the style tools dropped or shrunk, collected while a model builds.

Tools call note(); the build report drains the notes after the model has been built.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Level = Literal["info", "warn"]


@dataclass(frozen=True)
class StyleNote:
    tool: str
    level: Level
    message: str


_notes: list[StyleNote] = []


def note(tool: str, message: str, level: Level = "warn") -> None:
    _notes.append(StyleNote(tool, level, message))


def drain() -> list[StyleNote]:
    """Returns the notes logged so far and clears the log."""
    notes = list(_notes)
    _notes.clear()
    return notes
