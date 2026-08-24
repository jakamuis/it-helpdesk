from pathlib import Path


ASSET_SYNC_ROOT = Path(__file__).resolve().parents[1]


def test_non_root_runtime_uses_staged_read_only_google_credentials():
    compose = (ASSET_SYNC_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "asset-sync-credentials-init:" in compose
    assert "platform: ${ASSET_SYNC_PLATFORM:-linux/amd64}" in compose
    assert 'user: "0:0"' in compose
    assert 'network_mode: "none"' in compose
    assert "cap_add:\n      - CHOWN" in compose
    assert "      - DAC_READ_SEARCH" in compose
    assert "condition: service_completed_successfully" in compose
    assert (
        "      - type: volume\n"
        "        source: asset-sync-credentials\n"
        "        target: /app/secrets\n"
        "        read_only: true"
    ) in compose
    assert "GOOGLE_CREDENTIALS_PATH: /app/secrets/google-service-account.json" in compose
    assert "chown 10001:10001" in compose
    assert "chmod 0400" in compose
    assert "mktemp /staged/.google-service-account.json.tmp.XXXXXX" in compose
    assert "trap 'rm -f" in compose
    assert "unsafe Google credential permissions" in compose
    assert "image: asset-sync:${ASSET_SYNC_IMAGE_TAG:-1.1.0-local}" in compose
    assert "BUILD_COMMIT: ${ASSET_SYNC_BUILD_COMMIT:-unknown}" in compose


def test_runtime_does_not_mount_host_backed_secret_directly():
    compose = (ASSET_SYNC_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    runtime_section = compose.split("\n  asset-sync:\n", maxsplit=1)[1]

    assert "source: google_service_account" not in runtime_section
    assert "/run/secrets/google-service-account.json" not in runtime_section
