"""Tool model for the FreshMesh agent.

Two kinds of tools exist:

* ``read`` tools only read or compute (forecast, plans, routes, SQL on whitelisted views, charts).
  The LLM may call them on its own.
* ``draft`` tools only *create drafts*. Their function computes a payload; the registry stores it via
  the injected :class:`DraftStore`, whose protocol has no approve/execute method. A draft is executed
  only when a human approves it through the API, never from the agent.

The registry refuses any other kind, validates every input against the tool's JSON schema (a strict,
dependency-free subset of JSON Schema) and converts every failure into a :class:`ToolError` carrying a
Vietnamese message.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

log = logging.getLogger(__name__)

ToolKind = Literal["read", "draft"]
TOOL_KINDS: frozenset[str] = frozenset({"read", "draft"})
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DRAFT_PREFIX_VI = "[BẢN NHÁP: chỉ tạo bản nháp, người dùng phải bấm Duyệt mới thực thi] "


@dataclass(frozen=True)
class ToolResult:
    data: dict[str, Any]
    citations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolContext:
    """What a tool may know about the caller. Tenant = ``chain_id`` (from the auth token)."""

    chain_id: str
    actor: str
    store_id: str | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)


class DraftStore(Protocol):
    """Only creation is exposed to the agent; approval lives in the API, outside the agent."""

    def create_draft(self, *, chain_id: str, kind: str, payload: dict[str, Any], created_by: str) -> str: ...


class ToolError(Exception):
    def __init__(self, message_vi: str):
        super().__init__(message_vi)
        self.message_vi = message_vi


ToolFn = Callable[[dict[str, Any], ToolContext], ToolResult]


@dataclass(frozen=True)
class Tool:
    name: str
    description_vi: str
    input_schema: dict[str, Any]
    kind: ToolKind
    fn: ToolFn
    # False when the output only echoes LLM-supplied numbers (charts, drafts): such output must not
    # count as a source for the number guardrail.
    verifiable: bool = True


# ---------------------------------------------------------------- JSON schema subset

_SUPPORTED_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "pattern",
        "description",
        "title",
        "default",
    }
)
_TYPES: dict[str, Callable[[Any], bool]] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def check_schema(schema: Mapping[str, Any], path: str = "$") -> None:
    """Raise ValueError if the schema uses keywords this validator does not implement."""
    unknown = set(schema) - _SUPPORTED_KEYWORDS
    if unknown:
        raise ValueError(f"unsupported JSON schema keyword(s) at {path}: {sorted(unknown)}")
    types = schema.get("type")
    for t in [types] if isinstance(types, str) else list(types or []):
        if t not in _TYPES:
            raise ValueError(f"unsupported JSON schema type at {path}: {t}")
    for key, sub in (schema.get("properties") or {}).items():
        check_schema(sub, f"{path}.{key}")
    if isinstance(schema.get("items"), Mapping):
        check_schema(schema["items"], f"{path}[]")
    if isinstance(schema.get("additionalProperties"), Mapping):
        check_schema(schema["additionalProperties"], f"{path}.*")


def validate_input(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    """Return every violation (empty list = valid)."""
    errors: list[str] = []
    types = schema.get("type")
    if types is not None:
        allowed = [types] if isinstance(types, str) else list(types)
        if not any(_TYPES[t](value) for t in allowed):
            return [f"{path}: cần kiểu {'/'.join(allowed)}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: giá trị không thuộc enum {schema['enum']}")
    if _TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: nhỏ hơn minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: lớn hơn maximum {schema['maximum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: ngắn hơn minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: dài hơn maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: không khớp pattern")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: ít hơn minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: nhiều hơn maxItems {schema['maxItems']}")
        if isinstance(schema.get("items"), Mapping):
            for i, item in enumerate(value):
                errors.extend(validate_input(item, schema["items"], f"{path}[{i}]"))
    if isinstance(value, dict):
        props: Mapping[str, Any] = schema.get("properties") or {}
        for req in schema.get("required") or []:
            if req not in value:
                errors.append(f"{path}.{req}: thiếu trường bắt buộc")
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                errors.extend(validate_input(item, props[key], f"{path}.{key}"))
            elif extra is False:
                errors.append(f"{path}.{key}: trường không được phép")
            elif isinstance(extra, Mapping):
                errors.extend(validate_input(item, extra, f"{path}.{key}"))
    return errors


# ---------------------------------------------------------------- registry


class ToolRegistry:
    def __init__(self, draft_store: DraftStore | None = None):
        self._tools: dict[str, Tool] = {}
        self._draft_store = draft_store

    def register(self, tool: Tool) -> Tool:
        if tool.kind not in TOOL_KINDS:
            raise ValueError(f"tool {tool.name!r}: kind must be 'read' or 'draft', got {tool.kind!r}")
        if not _NAME_RE.match(tool.name):
            raise ValueError(f"invalid tool name {tool.name!r}")
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} đã được đăng ký (already registered)")
        if tool.input_schema.get("type") != "object":
            raise ValueError(f"tool {tool.name!r}: input_schema must have type 'object'")
        check_schema(tool.input_schema)
        self._tools[tool.name] = tool
        return tool

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolError(f"Công cụ '{name}' không tồn tại.")
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools)

    def definitions(self) -> list[dict[str, Any]]:
        """Tool definitions in Anthropic Messages API shape (provider-neutral JSON schema)."""
        return [
            {
                "name": t.name,
                "description": (DRAFT_PREFIX_VI if t.kind == "draft" else "") + t.description_vi,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def call(self, name: str, args: Any, ctx: ToolContext) -> ToolResult:
        tool = self.get(name)
        errors = validate_input(args, tool.input_schema)
        if errors:
            raise ToolError(f"Tham số không hợp lệ cho '{name}': " + "; ".join(errors))
        if tool.kind == "draft" and self._draft_store is None:
            raise ToolError("Chưa cấu hình nơi lưu bản nháp; không thể tạo bản nháp.")
        try:
            result = tool.fn(dict(args), ctx)
        except ToolError:
            raise
        except Exception:
            log.exception("tool %s failed", name)
            raise ToolError(f"Công cụ '{name}' gặp lỗi khi chạy.") from None
        if not isinstance(result, ToolResult):
            raise ToolError(f"Công cụ '{name}' trả về kết quả sai định dạng.")
        if tool.kind == "read":
            return result
        assert self._draft_store is not None
        draft_id = self._draft_store.create_draft(
            chain_id=ctx.chain_id, kind=tool.name, payload=result.data, created_by=ctx.actor
        )
        return ToolResult(
            data={
                "draft_id": draft_id,
                "kind": tool.name,
                "status": "draft",
                "requires_approval": True,
                "payload": result.data,
            },
            citations=[*result.citations, f"draft:{draft_id}"],
        )
