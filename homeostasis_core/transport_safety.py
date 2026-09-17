"""Secret-free transport preflight and diagnostic evidence; no network access."""
import hashlib
import json
import locale
import os
import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version


class LocalTransportConfigurationError(ValueError):
    pass


def validate_credential(value):
    # Header values are ASCII. Do not transform, hash, log or echo credentials.
    if not isinstance(value, str) or not value or any(not 33 <= ord(c) <= 126 for c in value):
        raise LocalTransportConfigurationError('Credential must be nonempty printable ASCII without whitespace') from None


def client_settings(api_key):
    validate_credential(api_key)
    import ssl
    import certifi
    # SDK otherwise consults SSL_CERT_FILE/DIR even with HTTPX trust_env=False.
    context = ssl.create_default_context(cafile=certifi.where())
    return {'api_key': api_key, 'vertexai': False, 'http_options': {
        'base_url': 'https://generativelanguage.googleapis.com', 'api_version': 'v1beta',
        'retry_options': {'attempts': 1},
        'client_args': {'trust_env': False, 'verify': context},
        'async_client_args': {'trust_env': False, 'verify': context, 'ssl': context}}}


def request_fingerprint(request):
    """Validate the exact JSON/UTF-8 envelope without retaining its contents."""
    try:
        raw = json.dumps(request, ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf-8')
    except (ValueError, TypeError, UnicodeError):
        raise LocalTransportConfigurationError('Request is not finite UTF-8 JSON') from None
    return hashlib.sha256(raw).hexdigest()


def exception_evidence(exc, stage):
    """Never save exception text, UnicodeError.object, locals, paths or headers."""
    families = set()
    tb = exc.__traceback__
    while tb is not None:
        module = tb.tb_frame.f_globals.get('__name__', '')
        for prefix in ('httpx', 'httpcore', 'google.genai', 'homeostasis_core'):
            if module == prefix or module.startswith(prefix + '.'):
                families.add(prefix)
        tb = tb.tb_next
    encoding = getattr(exc, 'encoding', None)
    return {'stage': stage, 'error_type': type(exc).__name__,
            'encoding': encoding if encoding in ('ascii', 'utf-8', 'latin-1', 'charmap') else None,
            'source_families': sorted(families), 'provider_acceptance': 'unknown'}


def runtime_manifest(root, mode):
    from .observability import source_digest
    packages = {}
    for name in ('google-genai', 'httpx', 'httpcore', 'pydantic', 'certifi'):
        try: packages[name] = version(name)
        except PackageNotFoundError: packages[name] = None
    def encoding(value):
        return value.lower() if isinstance(value,str) and value.lower() in ('utf-8','utf8','ascii','us-ascii','ansi_x3.4-1968','latin-1') else 'other'
    return {'runtime_version': 1, 'mode': mode,
            'source_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'source_digest': source_digest(root), 'python_version': platform.python_version(),
            'packages': packages, 'encoding': {'default': encoding(sys.getdefaultencoding()),
                'locale': encoding(locale.getpreferredencoding(False)), 'stdout': encoding(sys.stdout.encoding),
                'stderr': encoding(sys.stderr.encoding)},
            'transport_policy': {'backend':'gemini-developer-api','endpoint':'https://generativelanguage.googleapis.com',
                'api_version':'v1beta','retry':0,'trust_env':False,'certificate_policy':'certifi'},
            'environment_presence': {name: bool(os.environ.get(name)) for name in (
                'GOOGLE_GENAI_USE_VERTEXAI','GOOGLE_GENAI_USE_ENTERPRISE','GOOGLE_GEMINI_BASE_URL',
                'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','SSL_CERT_FILE','SSL_CERT_DIR','PYTHONIOENCODING')},
            'credential_validation':'PASS'}
