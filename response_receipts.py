"""Private, write-once SDK response evidence, separate from public results.

These are SDK-decoded responses, not original HTTP bytes. Transport headers
are excluded. Missing historical receipts are never reconstructed.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile


FORMAT = "gemini_sdk_response_v1"
IDENTITY = ("run", "turn", "agent_id", "agent_type", "model", "schema_version",
            "attempt", "snapshot_id", "observation_digest")


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _identity(audit):
    return {key: audit[key] for key in IDENTITY}


class ResponseReceipts:
    def __init__(self, directory):
        self.directory = Path(directory)

    @classmethod
    def for_output(cls, output):
        output = Path(output)
        return cls(output.parent / ".artifacts" / "response-receipts" / output.name)

    def prepare(self, *, resume=False):
        # A fresh execution must not reuse another execution's evidence.
        if self.directory.is_symlink():
            raise ValueError("RECEIPT_DIRECTORY_IS_SYMLINK")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=resume)

    def record(self, audit, response):
        identity = _identity(audit)
        key = hashlib.sha256(_bytes(identity)).hexdigest()
        sdk_json = response.model_dump_json(exclude={"sdk_http_response"}, exclude_none=True)
        payload = _bytes({"format": FORMAT, "identity": identity,
                          "sdk_response": json.loads(sdk_json)})
        destination = self.directory / (key + ".json")
        fd, temporary = tempfile.mkstemp(prefix=".receipt-", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            # No replace, even when an existing receipt has identical content.
            os.link(temporary, destination)
            directory_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            os.unlink(temporary)
        return {"id": key, "sha256": hashlib.sha256(payload).hexdigest(), "format": FORMAT}

    def verify(self, audits):
        """Check referenced local receipts before resuming; never modify them."""
        for audit in audits:
            reference = audit.get("response_receipt")
            if reference is None:
                if audit.get("receipt_required") is True and audit.get("response_status") == "validated":
                    raise ValueError("RESPONSE_RECEIPT_MISSING")
                continue  # Legacy absence is not proof of an original reply.
            identity = _identity(audit)
            key = hashlib.sha256(_bytes(identity)).hexdigest()
            if (type(reference) is not dict or reference.get("id") != key
                    or reference.get("format") != FORMAT):
                raise ValueError("RESPONSE_RECEIPT_IDENTITY_MISMATCH")
            path = self.directory / (key + ".json")
            if self.directory.is_symlink() or path.is_symlink() or not path.is_file():
                raise ValueError("RESPONSE_RECEIPT_MISSING")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != reference.get("sha256"):
                raise ValueError("RESPONSE_RECEIPT_HASH_MISMATCH")
            saved = json.loads(raw)
            if saved.get("identity") != identity or saved.get("format") != FORMAT:
                raise ValueError("RESPONSE_RECEIPT_IDENTITY_MISMATCH")
            if audit.get("response_status") == "validated":
                from google.genai.types import GenerateContentResponse
                from model_response_json import load_response_object
                from provider_response import complete_response_text
                text = complete_response_text(GenerateContentResponse.model_validate(saved["sdk_response"]))
                if (not isinstance(text, str)
                        or hashlib.sha256(text.encode("utf-8")).hexdigest() != audit.get("response_sha256")
                        or _bytes(load_response_object(text)) != _bytes(audit.get("structured_response"))):
                    raise ValueError("RESPONSE_RECEIPT_CONTENT_MISMATCH")
