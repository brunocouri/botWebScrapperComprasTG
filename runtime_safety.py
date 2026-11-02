"""Primitivas locais: lock do SO e substituição atômica, sem dependências."""
import errno
import json
import os
from pathlib import Path
import tempfile
import time


class LockBusy(OSError):
    pass


class FileLock:
    """O SO libera o lock inclusive após terminate/crash. Nunca remover o inode.

    O arquivo permanece como metadado; sua existência não indica processo ativo.
    Não truncar antes de adquirir o lock (Windows bloqueia o byte zero).
    """
    def __init__(self, path, timeout=0):
        self.path = Path(path)
        self.file = None
        self.timeout = timeout

    def acquire(self):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                return self._acquire()
            except LockBusy:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.025)

    def _acquire(self):
        handle = open(self.path, 'a+b')
        try:
            # Byte fora dos metadados: o comando de parada pode ler o PID
            # enquanto o monitor mantém o lock exclusivo no Windows.
            handle.seek(1024 * 1024)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise LockBusy('Sessão ou configuração em uso por outra operação.') from exc
            raise
        self.file = handle
        return self

    def set_owner(self):
        self.file.seek(0)
        self.file.truncate()
        self.file.write(json.dumps({'version': 2, 'pid': os.getpid()}).encode('ascii'))
        self.file.flush()

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        self.close()


def atomic_write(path, text):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
