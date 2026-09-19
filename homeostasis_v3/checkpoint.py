"""Local POSIX checkpoint publication: immutable record + atomic HEAD commit.

Checksums detect corruption, not malicious re-signing. Directory must be owned
by the trusted host. A failed pre-commit write is never a new official TURN.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile

from .choices import ensure, TechnicalFailure
from .contracts import canonical
from .turn import validate_checkpoint


class CommitUncertain(TechnicalFailure):
    """HEAD replaced but directory fsync failed; read HEAD before any retry."""


class CheckpointStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _lock(self):
        with (self.directory / '.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def _sync_dir(self):
        fd = os.open(self.directory, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def _atomic_write(self, path, data, *, replace=True):
        fd, temp = tempfile.mkstemp(prefix='.pending-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
            # Validate the exact written bytes before making them visible.
            ensure(json.loads(Path(temp).read_text(encoding='utf-8')) == json.loads(data), 'CHECKPOINT_WRITE_MISMATCH')
            if replace:
                os.replace(temp, path)
            else:
                try:
                    os.link(temp, path)
                except FileExistsError:
                    # A previous pre-HEAD failure may leave this exact record.
                    # Reuse its bytes without rewriting; conflicting evidence
                    # must remain available for inspection.
                    ensure(not path.is_symlink() and path.is_file()
                           and path.read_bytes() == data.encode('utf-8'), 'CHECKPOINT_RECORD_CONFLICT')
        finally:
            if os.path.exists(temp): os.unlink(temp)

    def load(self):
        head = self.directory / 'HEAD.json'
        if not os.path.lexists(head): return None
        ensure(not head.is_symlink(), 'CHECKPOINT_SYMLINK_FORBIDDEN')
        pointer = json.loads(head.read_text(encoding='utf-8'))
        ensure(set(pointer) == {'checkpoint_digest', 'file'}, 'INVALID_HEAD')
        checksum = pointer['checkpoint_digest']
        ensure(type(checksum) is str and len(checksum) == 64 and all(c in '0123456789abcdef' for c in checksum), 'INVALID_HEAD_DIGEST')
        ensure(pointer['file'] == checksum + '.json', 'INVALID_HEAD_PATH')
        record = self.directory / pointer['file']
        ensure(not record.is_symlink(), 'CHECKPOINT_SYMLINK_FORBIDDEN')
        cp = validate_checkpoint(json.loads(record.read_text(encoding='utf-8')))
        ensure(cp['checkpoint_digest'] == checksum, 'HEAD_DIGEST_MISMATCH')
        return cp

    def save(self, candidate, *, expected_digest):
        # Serialization severs aliases before validation / filesystem mutation.
        candidate = json.loads(canonical(candidate)); validate_checkpoint(candidate)
        with self._lock():
            current = self.load()
            ensure((None if current is None else current['checkpoint_digest']) == expected_digest, 'STALE_CHECKPOINT_HEAD')
            if current is None:
                ensure(candidate['turn'] == 0, 'GENESIS_REQUIRED')
            else:
                ensure(candidate['context_id'] == current['context_id'] and candidate['config_hash'] == current['config_hash'], 'CHECKPOINT_CONTEXT_MISMATCH')
                ensure(candidate['turn'] == current['turn'] + 1 and candidate['input']['opening'] == expected_digest, 'CHECKPOINT_CHAIN_MISMATCH')
            checksum = candidate['checkpoint_digest']; record = self.directory / (checksum + '.json')
            self._atomic_write(record, canonical(candidate), replace=False)
            self._sync_dir()  # Record must be durable before HEAD references it.
            self._atomic_write(self.directory / 'HEAD.json', canonical({'file': record.name, 'checkpoint_digest': checksum}))
            try: self._sync_dir()
            except OSError:
                raise CommitUncertain('COMMIT_DURABILITY_UNCERTAIN_READ_HEAD_BEFORE_RETRY') from None
        return checksum
