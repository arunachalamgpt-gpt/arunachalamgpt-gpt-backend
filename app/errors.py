"""Domain exception hierarchy.

Every business-rule violation raises a subclass of `AppError`. Each carries:

- `status_code` — HTTP status the global handler will use
- `code` — stable machine-readable identifier (e.g. `lodge_not_found`)
- `message` — human-readable default (overridable per raise)
- `details` — optional dict echoed back in the response body

The global handler in `app.exception_handlers` translates these into the
uniform error envelope. Routers and services only raise; they never craft
`HTTPException` directly.
"""

from typing import Any, Optional


class AppError(Exception):
    """Base class for all domain errors.

    Translated to JSON by the global handler in `app.exception_handlers`.
    Subclasses set class-level `status_code`, `code`, and `message`; instances
    may override `message` and attach a `details` dict echoed to the client.
    """

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        details: Optional[dict[str, Any]] = None,
    ):
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found"


class LodgeNotFoundError(NotFoundError):
    code = "lodge_not_found"
    message = "Lodge not found"


class BookingNotFoundError(NotFoundError):
    code = "booking_not_found"
    message = "Booking not found"


class AvailabilityNotFoundError(NotFoundError):
    code = "availability_not_found"
    message = "No availability record for that lodge/date"


class ValidationFailedError(AppError):
    status_code = 400
    code = "validation_failed"
    message = "Request failed validation"


class LodgeNotVerifiedError(AppError):
    status_code = 400
    code = "lodge_not_verified"
    message = "Lodge is not verified — booking blocked"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Conflicting request"


class NoRoomsAvailableError(ConflictError):
    code = "no_rooms_available"
    message = "No rooms available for the selected date"


class InvalidBookingStateError(ConflictError):
    code = "invalid_booking_state"
    message = "Booking is not in a valid state for this operation"


class DatabaseError(AppError):
    status_code = 503
    code = "database_error"
    message = "Database is unavailable"
