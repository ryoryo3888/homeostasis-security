"""Bounded REST transport for the paired pilot; no retries or secret persistence."""
import json
from pathlib import Path

from .agent_adapter import _object
from .choices import ensure, check, TechnicalFailure
from .comparison import protocol
from .contracts import canonical, digest
from .gemini_preflight import AttemptJournal
from .validation_runner import _write


class PilotExchange:
    def __init__(self, root, credential, *, transport=None):
        import httpx
        ensure(type(credential) is str and bool(credential.strip()), 'CREDENTIAL_REQUIRED')
        self.root = Path(root); self.config = protocol(root); self.seed = None
        self.path = self.root/'.artifacts/v3-paid-pilot-20260919-current'
        self.path.mkdir(parents=True, exist_ok=True)
        self.journal = AttemptJournal(self.path/'attempts.sqlite', configuration={
            'max_calls': 64, 'protocol_digest': digest(self.config)})
        self.http = httpx.Client(transport=transport or httpx.HTTPTransport(retries=0),
            trust_env=False, follow_redirects=False, timeout=30,
            headers={'x-goog-api-key': credential})

    def close(self): self.http.close()

    def __call__(self, raw):
        ensure(self.config == protocol(self.root), 'PILOT_PROTOCOL_CHANGED')
        ensure(self.seed in self.config['seeds'], 'INVALID_PILOT_SEED')
        ensure(type(raw) is str and len(raw.encode()) <= 500000, 'INPUT_LIMIT_EXCEEDED')
        r = json.loads(raw, object_pairs_hook=_object)
        ensure(r['phase'] in ('initiative', 'consent') and r['state_id'] in self.config['states'], 'INVALID_REQUEST')
        ensure(r['request_digest'] == digest({k:v for k,v in r.items() if k != 'request_digest'}), 'REQUEST_DIGEST_MISMATCH')
        ensure(r['observation_digest'] == digest(r['observation']), 'OBSERVATION_MISMATCH')
        schema = self.config['schemas'][0 if r['phase'] == 'initiative' else 1]
        body = {'contents': [{'role': 'user', 'parts': [{'text': raw}]}],
                'systemInstruction': {'parts': [{'text': self.config['system_instruction']}]},
                'generationConfig': {'temperature': self.config['temperature'], 'seed': self.seed,
                    'candidateCount': 1, 'maxOutputTokens': 1536,
                    'thinkingConfig': {'thinkingLevel': 'minimal'},
                    'responseMimeType': 'application/json', 'responseJsonSchema': schema}}
        base = 'https://generativelanguage.googleapis.com/v1beta/models/'+self.config['model']
        # Each reserved slot permits one count request and one generation at most.
        # 64 * ((37000+2048)*0.30 + 1536*2.50)/1e6 = USD 0.9954816.
        # This is a documented-rate estimate, not a provider-enforced billing limit.
        self.journal.reserve(r)
        usage = {'counted_input_tokens': None, 'provider_usage': None, 'generation_attempted': False}
        evidence = self.path/r['request_digest']; evidence.mkdir(exist_ok=False)
        try:
            _write(evidence/'request.json', {'seed': self.seed, 'body': body})
            count = self.http.post(base+':countTokens', json={
                'generateContentRequest': {'model': 'models/'+self.config['model'], **body}})
            count.raise_for_status()
            tokens = count.json().get('totalTokens')
            ensure(type(tokens) is int and 0 < tokens <= 37000, 'COUNTED_INPUT_LIMIT')
            usage['counted_input_tokens'] = tokens
            _write(evidence/'count.json', {'totalTokens': tokens})
            usage['generation_attempted'] = True
            _write(evidence/'dispatch.json', {'generation_attempted': True})
            response = self.http.post(base+':generateContent', json=body)
            response.raise_for_status()
            data = response.json()
            # Only model output and usage are retained, never HTTP headers or errors.
            _write(evidence/'response.json', data)
            usage['provider_usage'] = data.get('usageMetadata')
            candidates = data.get('candidates', [])
            ensure(len(candidates) == 1 and candidates[0].get('finishReason') == 'STOP', 'INCOMPLETE_RESPONSE')
            parts = candidates[0]['content']['parts']
            ensure(all('text' in p and set(p) <= {'text', 'thoughtSignature'} and type(p['text']) is str for p in parts), 'UNEXPECTED_RESPONSE_PART')
            answer = ''.join(p['text'] for p in parts)
            ensure(len(answer.encode()) <= 65536, 'RESPONSE_LIMIT')
            parsed = json.loads(answer, object_pairs_hook=_object); check(schema, parsed)
            ensure(parsed['request_digest'] == r['request_digest'] and parsed['state_id'] == r['state_id'], 'ANSWER_BINDING')
            meta = usage['provider_usage']
            ensure(isinstance(meta, dict), 'UNKNOWN_USAGE_STOP')
            inp, out, thoughts = (meta.get('promptTokenCount'), meta.get('candidatesTokenCount'), meta.get('thoughtsTokenCount', 0))
            ensure(all(type(x) is int and x >= 0 for x in (inp, out, thoughts)), 'INVALID_USAGE_STOP')
            ensure(inp <= tokens+2048 and out+thoughts <= 1536, 'BUDGET_ESTIMATE_EXCEEDED_STOP')
        except Exception as error:
            usage['failure_type'] = type(error).__name__
            usage['http_status'] = getattr(getattr(error, 'response', None), 'status_code', None)
            usage['failure_code'] = getattr(error, 'code', None)
            self.journal.finish(r['request_digest'], 'failed', usage)
            raise TechnicalFailure('PILOT_TRANSPORT_STOP_NO_RETRY') from None
        self.journal.finish(r['request_digest'], 'response_validated', usage)
        return answer
