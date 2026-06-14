"""Standard API response envelope for FMS."""

from rest_framework.response import Response
from rest_framework import status as http_status


def _flatten_validation_errors(errors, prefix=""):
    """Extract the first human-readable message from nested DRF errors."""
    if errors is None:
        return []
    if isinstance(errors, dict):
        messages = []
        for key, value in errors.items():
            segment = str(key) if not prefix else f"{prefix}.{key}"
            messages.extend(_flatten_validation_errors(value, segment))
        return messages
    if isinstance(errors, list):
        messages = []
        for index, value in enumerate(errors):
            if isinstance(value, (dict, list)):
                segment = f"{prefix}[{index}]" if prefix else f"[{index}]"
                messages.extend(_flatten_validation_errors(value, segment))
            else:
                text = str(value)
                messages.append(f"{prefix}: {text}" if prefix else text)
        return messages
    return [str(errors)]


def api_response(data=None, message="OK", success=True, errors=None, status=http_status.HTTP_200_OK):
    """Return a consistent { success, data, message, errors } response."""
    return Response(
        {
            "success": success,
            "data": data,
            "message": message,
            "errors": errors,
        },
        status=status,
    )


def api_error(message="An error occurred", errors=None, status=http_status.HTTP_400_BAD_REQUEST):
    """Return a standard error response."""
    if errors and message == "An error occurred":
        flat = _flatten_validation_errors(errors)
        if flat:
            message = flat[0]
    return api_response(
        data=None,
        message=message,
        success=False,
        errors=errors,
        status=status,
    )
