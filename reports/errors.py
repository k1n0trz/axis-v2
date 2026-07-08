"""Manejo de errores centralizado para Axis."""
from http import HTTPStatus
from typing import Any, Optional

from django.http import JsonResponse


class ApiError(Exception):
    def __init__(
        self,
        message: str,
        code: str = "error",
        status_code: int = HTTPStatus.BAD_REQUEST,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "success": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


class ValidationError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, "validation_error", HTTPStatus.BAD_REQUEST, details)


class NotFoundError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, "not_found", HTTPStatus.NOT_FOUND, details)


class UnauthorizedError(ApiError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, "unauthorized", HTTPStatus.UNAUTHORIZED)


class ForbiddenError(ApiError):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, "forbidden", HTTPStatus.FORBIDDEN)


class ConflictError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, "conflict", HTTPStatus.CONFLICT, details)


def api_error_handler(exc: Exception) -> JsonResponse:
    if isinstance(exc, ApiError):
        return JsonResponse(exc.to_dict(), status=exc.status_code)
    return JsonResponse(
        {
            "success": False,
            "error": {
                "code": "internal_error",
                "message": "Error interno del servidor",
                "details": {},
            },
        },
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
    )


def field_errors_to_dict(errors: dict) -> dict:
    result = {}
    for field, messages in errors.items():
        if isinstance(messages, list):
            result[field] = messages[0] if messages else "Campo inválido"
        else:
            result[field] = messages
    return result