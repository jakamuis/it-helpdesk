import fcntl
import hashlib
import os
import stat
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional, Union

from app.core.config import settings


class QRCodeLockError(RuntimeError):
    """Base error for the local QR mutation lock."""


class QRCodeLockBusyError(QRCodeLockError):
    """Raised when another local worker is already mutating the same QR."""


class GlobalMutationLockBusyError(QRCodeLockError):
    """Raised when another worker is inside the global GLPI mutation section."""


def _normalized_qrcode(qrcode: str) -> str:
    normalized = qrcode.strip().casefold()
    if not normalized:
        raise QRCodeLockError("QRCODE UNIT cannot be blank")
    return normalized


def _private_lock_directory(directory: Union[str, Path]) -> Path:
    lock_directory = Path(directory)
    lock_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(lock_directory, 0o700)
    return lock_directory


def _open_private_lock_file(lock_path: Path) -> int:
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    file_descriptor = os.open(lock_path, flags, 0o600)
    os.fchmod(file_descriptor, 0o600)
    if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
        os.close(file_descriptor)
        raise QRCodeLockError("Mutation lock path is not a regular file")
    return file_descriptor


@asynccontextmanager
async def hold_global_mutation_lock(
    *,
    directory: Optional[Union[str, Path]] = None,
) -> AsyncIterator[Path]:
    """Serialize all GLPI mutations so cross-QR DAT checks remain atomic."""
    lock_directory = _private_lock_directory(directory or settings.SYNC_LOCK_DIR)
    lock_path = lock_directory / "global-mutation.lock"
    file_descriptor = _open_private_lock_file(lock_path)
    acquired = False
    try:
        try:
            fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as exc:
            raise GlobalMutationLockBusyError(
                "Another local worker is applying a GLPI mutation"
            ) from exc
        yield lock_path
    finally:
        if acquired:
            fcntl.flock(file_descriptor, fcntl.LOCK_UN)
        os.close(file_descriptor)


@asynccontextmanager
async def hold_qrcode_lock(
    qrcode: str,
    *,
    directory: Optional[Union[str, Path]] = None,
) -> AsyncIterator[Path]:
    """Hold a non-blocking OS lock for one normalized QR mutation.

    The hashed lock filename avoids exposing the QR in the filesystem. Lock
    files intentionally remain in place after release: unlinking a flock file
    can create two live inodes and defeat mutual exclusion.
    """
    normalized = _normalized_qrcode(qrcode)
    lock_directory = _private_lock_directory(directory or settings.SYNC_LOCK_DIR)
    lock_name = f"{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}.lock"
    lock_path = lock_directory / lock_name

    file_descriptor = _open_private_lock_file(lock_path)
    acquired = False
    try:
        try:
            fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as exc:
            raise QRCodeLockBusyError(
                "Another local worker is already syncing this QRCODE UNIT"
            ) from exc

        yield lock_path
    finally:
        if acquired:
            fcntl.flock(file_descriptor, fcntl.LOCK_UN)
        os.close(file_descriptor)
