from app.errors import (
    AppError,
    AvailabilityNotFoundError,
    BookingNotFoundError,
    ConflictError,
    DatabaseError,
    InvalidBookingStateError,
    LodgeNotFoundError,
    LodgeNotVerifiedError,
    NoRoomsAvailableError,
    NotFoundError,
    ValidationFailedError,
)


def test_app_error_defaults():
    err = AppError()
    assert err.status_code == 500
    assert err.code == "internal_error"
    assert err.message == "An unexpected error occurred"
    assert err.details == {}


def test_app_error_custom_message_and_details():
    err = AppError("custom message", details={"foo": "bar"})
    assert err.message == "custom message"
    assert err.details == {"foo": "bar"}
    assert str(err) == "custom message"


def test_subclass_status_codes_and_codes():
    cases = [
        (NotFoundError, 404, "not_found"),
        (LodgeNotFoundError, 404, "lodge_not_found"),
        (BookingNotFoundError, 404, "booking_not_found"),
        (AvailabilityNotFoundError, 404, "availability_not_found"),
        (ValidationFailedError, 400, "validation_failed"),
        (LodgeNotVerifiedError, 400, "lodge_not_verified"),
        (ConflictError, 409, "conflict"),
        (NoRoomsAvailableError, 409, "no_rooms_available"),
        (InvalidBookingStateError, 409, "invalid_booking_state"),
        (DatabaseError, 503, "database_error"),
    ]
    for cls, code, slug in cases:
        err = cls()
        assert err.status_code == code
        assert err.code == slug
