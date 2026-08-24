#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.services.datasheet_report import DatasheetReportGenerator  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a local, read-only preflight report from the authoritative Datasheet."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("./data/reports"),
        help="Parent directory for the timestamped report (default: ./data/reports)",
    )
    args = parser.parse_args()

    result = DatasheetReportGenerator().generate(
        settings.SPREADSHEET_ID,
        settings.SHEET_NAME,
        output_root=args.output_root,
        timezone_name=settings.SYNC_TIMEZONE,
    )
    counts = result["summary"]["counts"]
    print(f"Report directory: {result['report_directory']}")
    print(
        "Asset scope: {} ({})".format(
            ", ".join(result["summary"]["source"]["asset_types"]),
            result["summary"]["source"]["datasheet_scope_selector"],
        )
    )
    print(
        "Counts: fetched={fetched_rows}, eligible={eligible_rows}, "
        "duplicates={duplicate_groups}, unique={unique_candidates}, "
        "scope_excluded={scope_excluded_rows}, unsupported={unsupported_electronic_rows}".format(
            **counts
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
