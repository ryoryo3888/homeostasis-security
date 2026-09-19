"""Read one completed candidate without selecting among provider alternatives."""


def complete_response_text(response):
    candidates = getattr(response, "candidates", None)
    if not isinstance(candidates, (list, tuple)) or len(candidates) != 1:
        raise ValueError("MISSING_OR_AMBIGUOUS_PROVIDER_CANDIDATE")
    if getattr(candidates[0], "finish_reason", None) != "STOP":
        raise ValueError("INCOMPLETE_PROVIDER_RESPONSE")
    text = response.text
    if not isinstance(text, str):
        raise ValueError("MISSING_PROVIDER_RESPONSE_TEXT")
    return text
