"""Shared error type and handlers producing {"error": {"code", "message"}} bodies."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

STORAGE_ERROR_MESSAGE = "The app couldn't save your work. Tell the team."


class AppError(Exception):
    """An error the caller can act on; rendered as a JSON error body."""

    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}  # extra top-level keys for the response body


def storage_error() -> AppError:
    return AppError(500, "storage_error", STORAGE_ERROR_MESSAGE)


def error_response(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}, **(details or {})})


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    if exc.status >= 500:
        logger.error("%s %s failed: %s (%s)", request.method, request.url.path, exc.code, exc.message)
    return error_response(exc.status, exc.code, exc.message, exc.details)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.info("Rejected %s %s: %s", request.method, request.url.path, exc.errors())
    return error_response(422, "bad_request", "That request wasn't quite right. Check what you sent and try again.")


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else "bad_request" if exc.status_code < 500 else "server_error"
    return error_response(exc.status_code, code, "That didn't work. Check the address and try again.")


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(500, "server_error", "Something went wrong. Tell the team.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
