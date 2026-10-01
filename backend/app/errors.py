"""API errors. Every error response is `{ "error": code, "message": human_text }`."""

import logging

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("dhaga.api")


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _json(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": code, "message": message})


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return _json(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path"))
        detail = first.get("msg", "Invalid request").removeprefix("Value error, ")
        return _json(422, "invalid_request", f"{where}: {detail}" if where else detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else "http_error"
        return _json(exc.status_code, code, str(exc.detail))

    # Registered as middleware (not an exception handler) so it sits inside the
    # CORS middleware: the browser can then read the error instead of a CORS failure.
    @app.middleware("http")
    async def _catch_all(request: Request, call_next):
        try:
            return await call_next(request)
        except psycopg.OperationalError:
            log.exception("Database unavailable")
            return _json(503, "database_unavailable", "Can't reach the database right now. Try again in a minute.")
        except Exception:
            log.exception("Unhandled error on %s %s", request.method, request.url.path)
            return _json(500, "internal_error", "Something went wrong on the server. The team can check the backend log.")
