import ast
import builtins
import runpy
from pathlib import Path

import pytest


ASSET_SYNC_ROOT = Path(__file__).resolve().parents[1]
QUARANTINED_SCRIPTS = {
    "push_new_assets.py": (
        "_historical_registration_asset_import_disabled",
        "comparison-only",
    ),
    "enrich_from_excel.py": (
        "_historical_registration_asset_enrichment_disabled",
        "comparison-only",
    ),
    "scripts/import_as_a_codes.py": (
        "_historical_registration_asset_mutation_disabled",
        "comparison-only",
    ),
    "scripts/import_deep_clean.py": (
        "_historical_registration_asset_mutation_disabled",
        "comparison-only",
    ),
    "scripts/import_hardware_info.py": (
        "_historical_registration_asset_mutation_disabled",
        "comparison-only",
    ),
    "scripts/import_hardware_info_by_name.py": (
        "_historical_registration_asset_mutation_disabled",
        "comparison-only",
    ),
    "scripts/import_hardware_info_slash.py": (
        "_historical_registration_asset_mutation_disabled",
        "comparison-only",
    ),
    "scripts/import_missing_am_codes.py": (
        "_historical_registration_asset_mutation_disabled",
        "comparison-only",
    ),
    "scripts/import_missing_am_no_hyphens.py": (
        "_historical_registration_asset_mutation_disabled",
        "comparison-only",
    ),
    "scripts/split_and_import_remaining.py": (
        "_historical_registration_asset_mutation_disabled",
        "comparison-only",
    ),
    "scripts/test_sync.py": (
        "_historical_manual_sync_bypass_disabled",
        "manual sync bypass",
    ),
}
FORBIDDEN_IMPORT_ROOTS = {"app", "httpx", "pandas", "pymysql"}


@pytest.mark.parametrize(
    ("script_name", "policy_fragment"),
    [
        (script_name, metadata[1])
        for script_name, metadata in QUARANTINED_SCRIPTS.items()
    ],
)
def test_direct_execution_refuses_before_loading_excel_or_glpi(
    script_name, policy_fragment, monkeypatch, capsys
):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.partition(".")[0] in FORBIDDEN_IMPORT_ROOTS:
            raise AssertionError(f"unsafe dependency imported during refusal: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(ASSET_SYNC_ROOT / script_name), run_name="__main__")

    assert exc_info.value.code == 78
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "BLOCKED" in captured.err
    assert policy_fragment in captured.err
    assert "Datasheet" in captured.err


@pytest.mark.parametrize(
    ("script_name", "historical_function"),
    [
        (script_name, metadata[0])
        for script_name, metadata in QUARANTINED_SCRIPTS.items()
    ],
)
def test_historical_mutator_starts_with_unconditional_refusal(
    script_name, historical_function
):
    tree = ast.parse((ASSET_SYNC_ROOT / script_name).read_text(encoding="utf-8"))
    matching_functions = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == historical_function
    ]

    assert len(matching_functions) == 1
    first_statement = matching_functions[0].body[0]
    assert isinstance(first_statement, ast.Raise)
    assert isinstance(first_statement.exc, ast.Call)
    assert isinstance(first_statement.exc.func, ast.Name)
    assert first_statement.exc.func.id == "RuntimeError"
