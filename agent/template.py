"""The fixed Vietnamese answer template: Đề xuất / Vì sao / Độ tin cậy / Giả định / Việc cần bạn duyệt,
followed by a server-written ``**Nguồn dữ liệu:**`` line (never taken from the model)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence

SECTIONS: tuple[str, ...] = ("Đề xuất", "Vì sao", "Độ tin cậy", "Giả định", "Việc cần bạn duyệt")
SOURCES_HEADING = "Nguồn dữ liệu"
UNKNOWN_SOURCE_ID = "unknown"
UNKNOWN_SOURCE_VI = "không rõ nguồn"
NO_DATA_VI = "Không dùng dữ liệu (không có kết quả công cụ)"
_HEADING = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?\**[ \t]*("
    + "|".join((*SECTIONS, SOURCES_HEADING))
    + r")[ \t]*\**[ \t]*:?[ \t]*\**[ \t]*",
    re.MULTILINE,
)


def format_answer(sections: Mapping[str, str]) -> str:
    """Render the five sections in canonical order (missing ones raise KeyError)."""
    return "\n\n".join(f"**{name}:** {sections[name].strip()}" for name in SECTIONS)


def format_sources_line(labels: Sequence[str] | None) -> str:
    """The server-written provenance line. ``None`` = no tool ran; ``[]`` = data of unknown origin."""
    if labels is None:
        body = NO_DATA_VI
    else:
        body = "; ".join(dict.fromkeys(labels)) or UNKNOWN_SOURCE_VI
    return f"**{SOURCES_HEADING}:** {body}"


def parse_answer(text: str) -> dict[str, str] | None:
    """Split an answer into the five sections; ``None`` if any section is missing or duplicated.
    A model-written "Nguồn dữ liệu" section is dropped (the server writes that line itself)."""
    text = unicodedata.normalize("NFC", text)
    matches = list(_HEADING.finditer(text))
    found: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1)
        if name in found:
            return None
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        found[name] = text[m.end() : end].strip()
    found.pop(SOURCES_HEADING, None)
    if set(found) != set(SECTIONS) or any(not v for v in found.values()):
        return None
    return {name: found[name] for name in SECTIONS}
