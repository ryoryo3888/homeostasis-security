"""Recognize explicit transient provider rejections, never ambiguous outcomes."""


def retryable_provider_status(error):
    from google.genai.errors import APIError
    if not isinstance(error, APIError):
        return None
    code = error.code
    if type(code) is not int or code not in (429, 503):
        return None
    details = error.details
    rejection = details.get("error") if isinstance(details, dict) else None
    if not isinstance(rejection, dict):
        return None
    if type(rejection.get("code")) is not int or rejection["code"] != code:
        return None
    if rejection.get("status") != {429: "RESOURCE_EXHAUSTED", 503: "UNAVAILABLE"}[code]:
        return None
    return code
