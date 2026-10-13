"""The fixed Vietnamese answer template: Đề xuất / Vì sao / Độ tin cậy / Giả định / Việc cần bạn duyệt."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

SECTIONS: tuple[str, ...] = ("Đề xuất", "Vì sao", "Độ tin cậy", "Giả định", "Việc cần bạn duyệt")
_HEADING = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?\**[ \t]*(" + "|".join(SECTIONS) + r")[ \t]*\**[ \t]*:?[ \t]*\**[ \t]*",
    re.MULTILINE,
)


def format_answer(sections: Mapping[str, str]) -> str:
    """Render the five sections in canonical order (missing ones raise KeyError)."""
    return "\n\n".join(f"**{name}:** {sections[name].strip()}" for name in SECTIONS)


def parse_answer(text: str) -> dict[str, str] | None:
    """Split an answer into the five sections; ``None`` if any section is missing or duplicated."""
    text = unicodedata.normalize("NFC", text)
    matches = list(_HEADING.finditer(text))
    found: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1)
        if name in found:
            return None
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        found[name] = text[m.end() : end].strip()
    if set(found) != set(SECTIONS) or any(not v for v in found.values()):
        return None
    return {name: found[name] for name in SECTIONS}
