"""Vietnamese error JSON: ``{"error": {"code": "...", "message_vi": "..."}}`` with a proper HTTP status."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

_STATUS_VI = {
    400: ("bad_request", "Yêu cầu không hợp lệ."),
    401: ("unauthorized", "Bạn cần đăng nhập."),
    403: ("forbidden", "Bạn không có quyền thực hiện thao tác này."),
    404: ("not_found", "Không tìm thấy đường dẫn hoặc dữ liệu yêu cầu."),
    405: ("method_not_allowed", "Phương thức không được hỗ trợ cho đường dẫn này."),
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message_vi: str):
        super().__init__(f"{code}: {message_vi}")
        self.status = status
        self.code = code
        self.message_vi = message_vi

    def body(self) -> dict:
        return {"error": {"code": self.code, "message_vi": self.message_vi}}


def error_response(status: int, code: str, message_vi: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message_vi": message_vi}}, status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(exc.body(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in e.get("loc", ()) if p != "body") for e in exc.errors()})
        detail = f" Trường lỗi: {', '.join(f for f in fields if f)}." if any(fields) else ""
        return error_response(422, "validation_error", "Dữ liệu gửi lên không hợp lệ." + detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, msg = _STATUS_VI.get(exc.status_code, (f"http_{exc.status_code}", "Máy chủ trả lỗi."))
        return error_response(exc.status_code, code, msg)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return error_response(500, "internal_error", "Máy chủ gặp lỗi không mong muốn, vui lòng thử lại.")
