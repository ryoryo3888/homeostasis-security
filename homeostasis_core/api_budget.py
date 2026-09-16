"""Transport-level attempt limit, including failures, with durable audit."""
import json
from types import SimpleNamespace


class BoundedClient:
    def __init__(self, client, maximum, audit_path):
        if type(maximum) is not int or maximum < 0:
            raise ValueError('maximum must be a nonnegative integer')
        self.client = client
        self.maximum = maximum
        self.audit_path = audit_path
        self.attempts = []
        self.models = SimpleNamespace(generate_content=self.generate_content)
        self._save()

    def _save(self):
        from final_experiment_runner import _checkpoint
        _checkpoint(self.audit_path, {'maximum_api_calls': self.maximum,
                                     'api_calls': len(self.attempts), 'attempts': self.attempts})

    def generate_content(self, **kwargs):
        if len(self.attempts) >= self.maximum:
            raise RuntimeError('Hard API call limit reached')
        record = {'attempt': len(self.attempts) + 1, 'status': 'started'}
        self.attempts.append(record)
        self._save()  # Reserve before dispatch; an interrupted request consumes budget.
        try:
            response = self.client.models.generate_content(**kwargs)
            record['status'] = 'returned'
            return response
        except BaseException as exc:
            record['status'] = 'failed'
            record['error_type'] = type(exc).__name__
            raise
        finally:
            self._save()
