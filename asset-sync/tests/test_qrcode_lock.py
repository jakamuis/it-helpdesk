import stat
import subprocess
import sys

import pytest

from app.services.qrcode_lock import (
    GlobalMutationLockBusyError,
    QRCodeLockBusyError,
    QRCodeLockError,
    hold_global_mutation_lock,
    hold_qrcode_lock,
)


@pytest.mark.asyncio
async def test_qrcode_lock_is_casefolded_nonblocking_and_private(tmp_path):
    lock_directory = tmp_path / "locks"

    async with hold_qrcode_lock(" QR-Secret ", directory=lock_directory) as lock_path:
        assert "qr-secret" not in lock_path.name
        assert stat.S_IMODE(lock_directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600

        with pytest.raises(QRCodeLockBusyError, match="already syncing"):
            async with hold_qrcode_lock("qr-secret", directory=lock_directory):
                pytest.fail("a contending normalized QR lock must not be acquired")

        contender = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import fcntl, os, sys; "
                    "fd=os.open(sys.argv[1], os.O_RDWR); "
                    "\ntry: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)"
                    "\nexcept BlockingIOError: sys.exit(23)"
                    "\nsys.exit(0)"
                ),
                str(lock_path),
            ],
            check=False,
        )
        assert contender.returncode == 23

        async with hold_qrcode_lock("QR-OTHER", directory=lock_directory):
            pass

    async with hold_qrcode_lock("qr-secret", directory=lock_directory):
        pass

    assert len(list(lock_directory.glob("*.lock"))) == 2


@pytest.mark.asyncio
async def test_qrcode_lock_rejects_blank_identity_without_creating_files(tmp_path):
    lock_directory = tmp_path / "locks"

    with pytest.raises(QRCodeLockError, match="cannot be blank"):
        async with hold_qrcode_lock("  ", directory=lock_directory):
            pytest.fail("blank QR must not acquire a lock")

    assert not lock_directory.exists()


@pytest.mark.asyncio
async def test_global_mutation_lock_serializes_different_qr_codes_and_is_private(tmp_path):
    lock_directory = tmp_path / "locks"

    async with hold_global_mutation_lock(directory=lock_directory) as lock_path:
        assert lock_path.name == "global-mutation.lock"
        assert stat.S_IMODE(lock_directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600

        with pytest.raises(GlobalMutationLockBusyError, match="Another local worker"):
            async with hold_global_mutation_lock(directory=lock_directory):
                pytest.fail("a second QR must not enter the global mutation section")

    async with hold_global_mutation_lock(directory=lock_directory):
        pass
