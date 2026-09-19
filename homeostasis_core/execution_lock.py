"""One local POSIX runner may own an output and its checkpoint at a time."""
from contextlib import contextmanager
import os
from pathlib import Path


@contextmanager
def exclusive_execution(output: Path):
    import fcntl
    # Resolve directory aliases so they cannot acquire different locks for
    # the same output. Keep the lock file: unlinking it can split contenders
    # between different inodes. The OS releases flock even on process death.
    canonical = output.resolve()
    directory = canonical.parent / '.artifacts' / 'execution-locks'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / (canonical.name + '.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise FileExistsError('execution already active for this output') from None
        yield
    finally:
        os.close(fd)
