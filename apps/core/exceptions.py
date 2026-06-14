"""Custom DRF exception handler."""

from rest_framework.views import exception_handler

from apps.core.responses import api_error


def custom_exception_handler(exc, context):
    """Wrap DRF exceptions in the FMS response envelope."""
    response = exception_handler(exc, context)
    if response is not None:
        errors = response.data
        if isinstance(errors, dict) and "detail" in errors:
            message = str(errors["detail"])
            errors = None
        else:
            message = "Validation error"
        return api_error(message=message, errors=errors, status=response.status_code)
    return response
