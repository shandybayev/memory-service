"""Application-specific exceptions."""

from fastapi import HTTPException, status


class PayloadTooLargeError(HTTPException):
    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Payload exceeds maximum size of {max_bytes} bytes",
        )


class ValidationError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
