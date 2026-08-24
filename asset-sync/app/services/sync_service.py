import hashlib
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from loguru import logger

from app.core.config import DATASHEET_SCOPE_SELECTOR, settings
from app.repository.audit import AuditRepository
from app.schemas.asset import AssetSyncRequest, AssetSyncResponse
from app.services.glpi_client import GLPIClient, GLPIClientError
from app.services.qrcode_lock import (
    QRCodeLockError,
    hold_global_mutation_lock,
    hold_qrcode_lock,
)
from app.services.sync_manifest import (
    ManifestAlreadyClaimedError,
    build_manifest,
    claim_manifest,
    compute_manifest_hash,
    persist_manifest,
)
from app.version import __version__


@dataclass
class SyncPlan:
    row_number: int
    request: AssetSyncRequest
    action: str
    expected_glpi_id: Optional[int]
    asset_payload: dict[str, Any]
    infocom_action: Optional[str]
    expected_infocom_id: Optional[int]
    infocom_payload: Optional[dict[str, Any]]
    write_cost: int
    asset_target_payload: Optional[dict[str, Any]] = None
    infocom_target_payload: Optional[dict[str, Any]] = None
    asset_state_sha256: Optional[str] = None
    infocom_state_sha256: Optional[str] = None
    expected_dat_infocom_id: Optional[int] = None
    selected: bool = False
    selection_reason: str = ""

    def to_manifest_item(self) -> dict[str, Any]:
        return {
            "row_number": self.row_number,
            "qrcode": self.request.qrcode,
            "asset_type": self.request.asset_type,
            "action": self.action,
            "expected_glpi_id": self.expected_glpi_id,
            "asset_payload": self.asset_payload,
            "asset_target_payload": self.asset_target_payload,
            "infocom_action": self.infocom_action,
            "expected_infocom_id": self.expected_infocom_id,
            "infocom_payload": self.infocom_payload,
            "infocom_target_payload": self.infocom_target_payload,
            "write_cost": self.write_cost,
            "asset_state_sha256": self.asset_state_sha256,
            "infocom_state_sha256": self.infocom_state_sha256,
            "expected_dat_infocom_id": self.expected_dat_infocom_id,
            "selected": self.selected,
            "selection_reason": self.selection_reason,
        }


class PartialMutationError(GLPIClientError):
    """Report a remote partial write without exposing upstream response text."""

    def __init__(self, *, glpi_id: int, stage: str, cause_type: str):
        self.glpi_id = glpi_id
        self.stage = stage
        self.cause_type = cause_type
        super().__init__(
            f"GLPI asset mutation succeeded but {stage} failed ({cause_type}); "
            "manual reconciliation is required"
        )


class SyncService:
    def __init__(
        self,
        glpi_client: GLPIClient,
        audit_repo: AuditRepository,
        dry_run: Optional[bool] = None,
    ):
        self.glpi = glpi_client
        self.audit = audit_repo
        self.dry_run = settings.SYNC_DRY_RUN if dry_run is None else dry_run
        self._dropdown_cache: dict[tuple[str, str], Optional[int]] = {}

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _write_transport_safe() -> bool:
        parsed_url = urlsplit(settings.GLPI_URL)
        return settings.GLPI_VERIFY_TLS is True and parsed_url.scheme.lower() == "https" and bool(
            parsed_url.hostname
        )

    @staticmethod
    def _canonical_glpi_url_identity(url: str) -> str:
        """Return a deterministic endpoint identity without credentials or URL extras."""
        parsed = urlsplit(url.strip())
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        if scheme not in {"http", "https"} or not hostname:
            raise GLPIClientError("GLPI URL must contain an HTTP(S) scheme and hostname")
        if parsed.query or parsed.fragment:
            raise GLPIClientError("GLPI URL must not contain a query string or fragment")
        try:
            port = parsed.port
        except ValueError as exc:
            raise GLPIClientError("GLPI URL contains an invalid port") from exc

        display_host = f"[{hostname}]" if ":" in hostname else hostname
        default_port = 443 if scheme == "https" else 80
        netloc = display_host if port in {None, default_port} else f"{display_host}:{port}"
        path = parsed.path.rstrip("/") or "/"
        return urlunsplit((scheme, netloc, path, "", ""))

    @staticmethod
    def _spreadsheet_id_sha256(spreadsheet_id: str) -> str:
        normalized_id = spreadsheet_id.strip()
        return hashlib.sha256(normalized_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _record_state_sha256(record: Any, fields: set[str]) -> str:
        if not isinstance(record, dict):
            raise GLPIClientError("GLPI detail record is unavailable for state verification")
        state = {
            field: {"present": field in record, "value": record.get(field)}
            for field in sorted(fields)
        }
        try:
            return compute_manifest_hash({"record_state": state})
        except Exception as exc:
            raise GLPIClientError("GLPI detail record cannot be fingerprinted safely") from exc

    @staticmethod
    def _field_values_equal(field: str, intended: Any, existing: Any) -> bool:
        integer_fields = {
            "id",
            "entities_id",
            "manufacturers_id",
            "locations_id",
            "states_id",
            "computermodels_id",
            "monitormodels_id",
            "computertypes_id",
            "monitortypes_id",
            "items_id",
            "sink_type",
            "sink_time",
        }
        if field in integer_fields:
            if isinstance(intended, bool) or isinstance(existing, bool):
                return intended is existing
            try:
                return int(intended) == int(existing)
            except (TypeError, ValueError):
                return False
        if field == "value":
            try:
                intended_decimal = Decimal(str(intended))
                existing_decimal = Decimal(str(existing))
            except (InvalidOperation, ValueError):
                return False
            return (
                intended_decimal.is_finite()
                and existing_decimal.is_finite()
                and intended_decimal == existing_decimal
            )
        return intended == existing

    @classmethod
    def _diff_payload(cls, target: dict[str, Any], record: Any) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise GLPIClientError("GLPI detail record is unavailable for diff planning")
        return {
            field: intended
            for field, intended in target.items()
            if field not in record
            or not cls._field_values_equal(field, intended, record.get(field))
        }

    @staticmethod
    def _parse_currency(value: Any) -> Optional[float]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, bool):
            raise GLPIClientError("NILAI RUPIAH must be a nonnegative finite number")

        if isinstance(value, (int, float, Decimal)):
            normalized = str(value)
        else:
            raw = str(value).replace("\u00a0", " ").strip()
            raw = re.sub(r"^(?:rp|idr)\.?\s*", "", raw, flags=re.IGNORECASE)
            normalized = re.sub(r"\s+", "", raw)
            if not normalized or not re.fullmatch(r"\d+(?:[.,]\d+)*", normalized):
                raise GLPIClientError("NILAI RUPIAH must be a nonnegative finite number")

            comma_count = normalized.count(",")
            dot_count = normalized.count(".")
            if comma_count and dot_count:
                decimal_separator = "," if normalized.rfind(",") > normalized.rfind(".") else "."
                thousands_separator = "." if decimal_separator == "," else ","
                if normalized.count(decimal_separator) != 1:
                    raise GLPIClientError("NILAI RUPIAH has an invalid separator format")
                whole, fraction = normalized.split(decimal_separator)
                groups = whole.split(thousands_separator)
                if (
                    not 1 <= len(fraction) <= 2
                    or not 1 <= len(groups[0]) <= 3
                    or any(len(group) != 3 for group in groups[1:])
                ):
                    raise GLPIClientError("NILAI RUPIAH has an invalid separator format")
                normalized = f"{''.join(groups)}.{fraction}"
            elif comma_count or dot_count:
                separator = "," if comma_count else "."
                groups = normalized.split(separator)
                if len(groups) > 2:
                    if not 1 <= len(groups[0]) <= 3 or any(len(group) != 3 for group in groups[1:]):
                        raise GLPIClientError("NILAI RUPIAH has an invalid separator format")
                    normalized = "".join(groups)
                else:
                    whole, fraction = groups
                    if len(fraction) == 3:
                        if not 1 <= len(whole) <= 3:
                            raise GLPIClientError("NILAI RUPIAH has an invalid separator format")
                        normalized = f"{whole}{fraction}"
                    elif 1 <= len(fraction) <= 2:
                        normalized = f"{whole}.{fraction}"
                    else:
                        raise GLPIClientError("NILAI RUPIAH has an invalid separator format")

        try:
            parsed = Decimal(normalized)
        except (InvalidOperation, ValueError) as exc:
            raise GLPIClientError("NILAI RUPIAH must be a nonnegative finite number") from exc
        if not parsed.is_finite() or parsed < 0:
            raise GLPIClientError("NILAI RUPIAH must be a nonnegative finite number")
        return float(parsed)

    @classmethod
    def _parse_buy_date(cls, value: Any) -> Optional[str]:
        raw = cls._text(value)
        if raw is None:
            return None
        try:
            if re.fullmatch(r"\d{4}", raw):
                parsed = date(int(raw), 1, 1)
            elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                parsed = date.fromisoformat(raw)
            elif match := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw):
                first, second, year = (int(part) for part in match.groups())
                # The sheet displays slash dates using a locale-dependent
                # day/month order. TAHUN PEROLEHAN only authorizes the year,
                # so validate that at least one ordering is a real date and
                # deliberately normalize it to 1 January without guessing.
                valid_orders = (
                    (year, first, second),
                    (year, second, first),
                )
                if not any(cls._is_real_date(*parts) for parts in valid_orders):
                    raise ValueError
                parsed = date(year, 1, 1)
            elif match := re.fullmatch(
                r"(\d{1,2})-([A-Za-z]{3})-(\d{4})",
                raw,
            ):
                day_text, month_text, year_text = match.groups()
                month = {
                    "jan": 1,
                    "feb": 2,
                    "mar": 3,
                    "apr": 4,
                    "may": 5,
                    "jun": 6,
                    "jul": 7,
                    "aug": 8,
                    "sep": 9,
                    "oct": 10,
                    "nov": 11,
                    "dec": 12,
                }.get(month_text.casefold())
                if month is None or not cls._is_real_date(
                    int(year_text),
                    month,
                    int(day_text),
                ):
                    raise ValueError
                parsed = date(int(year_text), 1, 1)
            else:
                raise ValueError
        except ValueError as exc:
            raise GLPIClientError(
                "TAHUN PEROLEHAN must contain a valid year or supported real date"
            ) from exc
        return parsed.isoformat()

    @staticmethod
    def _is_real_date(year: int, month: int, day: int) -> bool:
        try:
            date(year, month, day)
        except ValueError:
            return False
        return True

    @classmethod
    def _parse_amortization(cls, value: Any) -> Optional[int]:
        raw = cls._text(value)
        if raw is None:
            return None
        match = re.fullmatch(r"([1-9]\d*)\s*(?:tahun)?", raw, flags=re.IGNORECASE)
        if match is None:
            raise GLPIClientError("PENYUSUTAN must be a positive whole number of years")
        return int(match.group(1))

    async def _dropdown_id(self, itemtype: str, name: Optional[str]) -> Optional[int]:
        if not name:
            return None
        cache_key = (itemtype.casefold(), " ".join(name.split()).casefold())
        if cache_key not in self._dropdown_cache:
            self._dropdown_cache[cache_key] = await self.glpi.find_dropdown(itemtype, name)
        dropdown_id = self._dropdown_cache[cache_key]
        if isinstance(dropdown_id, bool) or not isinstance(dropdown_id, int) or dropdown_id <= 0:
            raise GLPIClientError(
                f"Exact {itemtype} dropdown value from the Datasheet was not found in GLPI"
            )
        return dropdown_id

    async def _map_payload(self, req: AssetSyncRequest, *, for_create: bool) -> dict:
        data = {"otherserial": req.qrcode}
        if for_create:
            data["entities_id"] = settings.GLPI_ENTITY

        if req.name:
            data["name"] = req.name
        else:
            composed = " ".join(part for part in (req.brand, req.model) if part)
            data["name"] = composed or req.qrcode

        if req.user:
            data["contact"] = req.user
        if req.comment:
            data["comment"] = req.comment

        manufacturer_id = await self._dropdown_id("Manufacturer", req.brand)
        if manufacturer_id:
            data["manufacturers_id"] = manufacturer_id

        if req.model:
            model_itemtype = "MonitorModel" if req.asset_type == "Monitor" else "ComputerModel"
            model_key = "monitormodels_id" if req.asset_type == "Monitor" else "computermodels_id"
            model_id = await self._dropdown_id(model_itemtype, req.model)
            if model_id:
                data[model_key] = model_id

        location_id = await self._dropdown_id("Location", req.location)
        if location_id:
            data["locations_id"] = location_id

        state_id = await self._dropdown_id("State", req.status)
        if state_id:
            data["states_id"] = state_id

        if req.category:
            type_itemtype = "MonitorType" if req.asset_type == "Monitor" else "ComputerType"
            type_key = "monitortypes_id" if req.asset_type == "Monitor" else "computertypes_id"
            type_id = await self._dropdown_id(type_itemtype, req.category)
            if type_id:
                data[type_key] = type_id

        return data

    def _build_infocom_payload(
        self,
        req: AssetSyncRequest,
        glpi_id: Optional[int],
    ) -> Optional[dict[str, Any]]:
        if not any((req.dat_number, req.buy_date, req.value not in (None, ""), req.amortization)):
            return None

        data: dict[str, Any] = {"itemtype": req.asset_type}
        if glpi_id is not None:
            data["items_id"] = glpi_id
        if req.dat_number:
            data["immo_number"] = req.dat_number
        parsed_buy_date = self._parse_buy_date(req.buy_date)
        if parsed_buy_date is not None:
            data["buy_date"] = parsed_buy_date

        parsed_value = self._parse_currency(req.value)
        if parsed_value is not None:
            data["value"] = parsed_value

        parsed_amortization = self._parse_amortization(req.amortization)
        if parsed_amortization is not None:
            data["sink_type"] = 2
            data["sink_time"] = parsed_amortization

        identifying_fields = {"itemtype", "items_id"}
        return data if set(data) - identifying_fields else None

    async def preflight_sync(self, req: AssetSyncRequest, *, row_number: int = 0) -> SyncPlan:
        """Build a complete mutation plan using read-only GLPI calls."""
        existing_asset = await self.glpi.resolve_asset_identity(
            req.qrcode,
            expected_itemtype=req.asset_type,
            expected_entities_id=settings.GLPI_ENTITY,
        )
        glpi_id = int(existing_asset["id"]) if existing_asset else None
        asset_target_payload = await self._map_payload(req, for_create=not existing_asset)
        if existing_asset:
            asset_payload = self._diff_payload(
                asset_target_payload,
                existing_asset.get("record"),
            )
            action = "UPDATE" if asset_payload else "NOOP"
        else:
            asset_payload = dict(asset_target_payload)
            action = "CREATE"
        asset_state_sha256 = None
        if existing_asset:
            asset_state_sha256 = self._record_state_sha256(
                existing_asset.get("record"),
                set(asset_target_payload) | {"id", "otherserial", "entities_id"},
            )

        infocom_target_payload = self._build_infocom_payload(req, glpi_id)
        infocom_payload = infocom_target_payload
        infocom_action: Optional[str] = None
        existing_infocom_id: Optional[int] = None
        infocom_state_sha256: Optional[str] = None
        expected_dat_infocom_id: Optional[int] = None
        if infocom_target_payload:
            if glpi_id is not None:
                existing_infocom = await self.glpi.resolve_infocom(req.asset_type, glpi_id)
                if existing_infocom is not None:
                    existing_infocom_id = int(existing_infocom["id"])
                    infocom_record = existing_infocom.get("record")
                    infocom_payload = self._diff_payload(
                        infocom_target_payload,
                        infocom_record,
                    )
                    infocom_state_sha256 = self._record_state_sha256(
                        infocom_record,
                        set(infocom_target_payload) | {"id", "itemtype", "items_id"},
                    )
            if existing_infocom_id is None:
                infocom_action = "CREATE"
            else:
                infocom_action = "UPDATE" if infocom_payload else "NOOP"

        if req.dat_number:
            dat_owner = await self.glpi.resolve_infocom_by_dat(req.dat_number)
            if dat_owner is not None:
                expected_dat_infocom_id = int(dat_owner["id"])
                if (
                    glpi_id is None
                    or dat_owner.get("itemtype") != req.asset_type
                    or int(dat_owner.get("items_id", -1)) != glpi_id
                    or existing_infocom_id != expected_dat_infocom_id
                ):
                    raise GLPIClientError(
                        "DAT number is already owned by a different GLPI asset or Infocom"
                    )

        return SyncPlan(
            row_number=row_number,
            request=req,
            action=action,
            expected_glpi_id=glpi_id,
            asset_payload=asset_payload,
            infocom_action=infocom_action,
            expected_infocom_id=existing_infocom_id,
            infocom_payload=infocom_payload,
            write_cost=(1 if action in {"CREATE", "UPDATE"} else 0)
            + (1 if infocom_action in {"CREATE", "UPDATE"} else 0),
            asset_target_payload=asset_target_payload,
            infocom_target_payload=infocom_target_payload,
            asset_state_sha256=asset_state_sha256,
            infocom_state_sha256=infocom_state_sha256,
            expected_dat_infocom_id=expected_dat_infocom_id,
        )

    async def _verify_plan_unchanged(self, plan: SyncPlan) -> None:
        """Fail closed if GLPI identity/action changed after preflight."""
        current_asset = await self.glpi.resolve_asset_identity(
            plan.request.qrcode,
            expected_itemtype=plan.request.asset_type,
            expected_entities_id=settings.GLPI_ENTITY,
        )
        current_id = int(current_asset["id"]) if current_asset else None
        if current_id != plan.expected_glpi_id:
            raise GLPIClientError("GLPI asset state changed after preflight; approval is stale")
        if current_asset is not None:
            asset_target_payload = plan.asset_target_payload or plan.asset_payload
            current_asset_state = self._record_state_sha256(
                current_asset.get("record"),
                set(asset_target_payload) | {"id", "otherserial", "entities_id"},
            )
            if current_asset_state != plan.asset_state_sha256:
                raise GLPIClientError(
                    "GLPI asset fields changed after preflight; approval is stale"
                )

        if plan.infocom_target_payload and plan.expected_glpi_id is not None:
            current_infocom = await self.glpi.resolve_infocom(
                plan.request.asset_type,
                plan.expected_glpi_id,
            )
            current_infocom_id = int(current_infocom["id"]) if current_infocom else None
            if current_infocom_id != plan.expected_infocom_id:
                raise GLPIClientError("GLPI Infocom state changed after preflight; approval is stale")
            if current_infocom_id is not None:
                current_infocom_state = self._record_state_sha256(
                    current_infocom.get("record"),
                    set(plan.infocom_target_payload) | {"id", "itemtype", "items_id"},
                )
                if current_infocom_state != plan.infocom_state_sha256:
                    raise GLPIClientError(
                        "GLPI Infocom fields changed after preflight; approval is stale"
                    )

        if plan.request.dat_number:
            current_dat_owner = await self.glpi.resolve_infocom_by_dat(
                plan.request.dat_number
            )
            current_dat_infocom_id = (
                int(current_dat_owner["id"]) if current_dat_owner is not None else None
            )
            if current_dat_infocom_id != plan.expected_dat_infocom_id:
                raise GLPIClientError(
                    "GLPI DAT ownership changed after preflight; approval is stale"
                )
            if current_dat_owner is not None and (
                plan.expected_glpi_id is None
                or current_dat_owner.get("itemtype") != plan.request.asset_type
                or int(current_dat_owner.get("items_id", -1)) != plan.expected_glpi_id
            ):
                raise GLPIClientError(
                    "GLPI DAT ownership no longer matches the approved asset"
                )

    async def _apply_plan(self, plan: SyncPlan) -> AssetSyncResponse:
        # Fixed acquisition order prevents deadlock and makes DAT ownership
        # recheck + all writes atomic across different QR codes/processes.
        async with hold_global_mutation_lock():
            async with hold_qrcode_lock(plan.request.qrcode):
                return await self._apply_plan_under_lock(plan)

    async def _apply_plan_under_lock(self, plan: SyncPlan) -> AssetSyncResponse:
        if not self._write_transport_safe():
            raise GLPIClientError(
                "GLPI writes require an HTTPS URL with TLS verification enabled"
            )
        if (
            plan.infocom_action in {"CREATE", "UPDATE"}
            and not settings.SYNC_FINANCE_ENABLED
        ):
            raise GLPIClientError("Finance synchronization is disabled by policy")
        if plan.action == "CREATE" and not settings.SYNC_ALLOW_CREATE:
            raise GLPIClientError("Asset creation is disabled by policy")
        if plan.infocom_action == "CREATE" and not settings.SYNC_ALLOW_INFOCOM_CREATE:
            raise GLPIClientError("Infocom creation is disabled by policy")
        if plan.infocom_action == "UPDATE" and not settings.SYNC_ALLOW_INFOCOM_UPDATE:
            raise GLPIClientError("Infocom update is disabled by policy")

        await self._verify_plan_unchanged(plan)

        if plan.action == "UPDATE":
            glpi_id = plan.expected_glpi_id
            if glpi_id is None:
                raise GLPIClientError("Update plan has no GLPI asset ID")
            await self.glpi.update_asset(
                glpi_id,
                plan.asset_payload,
                itemtype=plan.request.asset_type,
            )
            response_status = "updated"
        elif plan.action == "CREATE":
            glpi_id = await self.glpi.create_asset(
                plan.asset_payload,
                itemtype=plan.request.asset_type,
            )
            response_status = "created"
        elif plan.action == "NOOP":
            glpi_id = plan.expected_glpi_id
            if glpi_id is None:
                raise GLPIClientError("NOOP plan has no GLPI asset ID")
            response_status = "unchanged"
        else:
            raise GLPIClientError(f"Unsupported asset plan action: {plan.action}")

        try:
            infocom_changed = await self._apply_infocom_mutation(plan, glpi_id)
        except Exception as exc:
            if plan.action in {"CREATE", "UPDATE"}:
                raise PartialMutationError(
                    glpi_id=glpi_id,
                    stage="infocom_mutation",
                    cause_type=type(exc).__name__,
                ) from exc
            raise
        if infocom_changed and response_status == "unchanged":
            response_status = "updated"

        return AssetSyncResponse(status=response_status, glpi_id=glpi_id)

    async def _apply_infocom_mutation(self, plan: SyncPlan, glpi_id: int) -> bool:
        if plan.infocom_action == "UPDATE":
            if not plan.infocom_payload:
                raise GLPIClientError("Infocom update plan has no changed fields")
            if plan.expected_infocom_id is None:
                raise GLPIClientError("Infocom update plan has no record ID")
            await self.glpi.update_infocom(
                plan.expected_infocom_id,
                plan.infocom_payload,
            )
            return True
        elif plan.infocom_action == "CREATE":
            if not plan.infocom_payload:
                raise GLPIClientError("Infocom create plan has no payload")
            await self.glpi.create_infocom(
                {**plan.infocom_payload, "items_id": glpi_id}
            )
            return True
        elif plan.infocom_action not in {None, "NOOP"}:
            raise GLPIClientError(f"Unsupported Infocom plan action: {plan.infocom_action}")
        return False

    async def _audit_result(
        self,
        plan: SyncPlan,
        *,
        action: str,
        status: str,
        response: AssetSyncResponse,
        started_at: float,
        error: Optional[str] = None,
    ) -> None:
        await self.audit.log_sync(
            qrcode=plan.request.qrcode,
            action=action,
            status=status,
            duration=time.time() - started_at,
            glpi_id=response.glpi_id or plan.expected_glpi_id,
            request_payload=plan.request.model_dump(),
            response_payload=response.model_dump(),
            error=error,
        )

    async def process_sync(
        self,
        req: AssetSyncRequest,
        *,
        dry_run: Optional[bool] = None,
    ) -> AssetSyncResponse:
        start_time = time.time()
        effective_dry_run = self.dry_run if dry_run is None else dry_run
        audit_status = "ERROR"
        audit_action = "PREFLIGHT"
        error_msg = None
        response = AssetSyncResponse(status="error", message="Sync did not complete")
        plan: Optional[SyncPlan] = None

        try:
            if not effective_dry_run:
                audit_action = "BLOCKED_DIRECT_WRITE"
                audit_status = "BLOCKED"
                response = AssetSyncResponse(
                    status="blocked",
                    message=(
                        "Direct sync writes are permanently disabled; use the reviewed "
                        "Datasheet batch manifest path."
                    ),
                )
            else:
                plan = await self.preflight_sync(req)
                if plan.action == "CREATE":
                    response_status = "would_create"
                    audit_action = "DRY_RUN_CREATE"
                elif plan.write_cost:
                    response_status = "would_update"
                    audit_action = "DRY_RUN_UPDATE"
                else:
                    response_status = "unchanged"
                    audit_action = "DRY_RUN_NOOP"
                audit_status = "SUCCESS"
                response = AssetSyncResponse(
                    status=response_status,
                    glpi_id=plan.expected_glpi_id,
                    message="Dry-run only; GLPI was not changed.",
                    dry_run=True,
                )

        except (GLPIClientError, QRCodeLockError) as exc:
            error_msg = str(exc)
            logger.error("GLPI sync failed for {}: {}", req.qrcode, error_msg)
            response = AssetSyncResponse(status="error", message=error_msg, dry_run=effective_dry_run)
        except Exception as exc:
            error_msg = str(exc)
            logger.exception("Unexpected error syncing {}: {}", req.qrcode, error_msg)
            response = AssetSyncResponse(status="error", message="Internal sync error", dry_run=effective_dry_run)
        finally:
            try:
                if plan is None:
                    await self.audit.log_sync(
                        qrcode=req.qrcode,
                        action=audit_action,
                        status=audit_status,
                        duration=time.time() - start_time,
                        glpi_id=None,
                        request_payload=req.model_dump(),
                        response_payload=response.model_dump(),
                        error=error_msg,
                    )
                else:
                    await self._audit_result(
                        plan,
                        action=audit_action,
                        status=audit_status,
                        response=response,
                        started_at=start_time,
                        error=error_msg,
                    )
            finally:
                try:
                    await self.glpi.kill_session()
                except Exception as exc:
                    logger.warning("Failed to close the GLPI session cleanly: {}", exc)

        return response

    @classmethod
    def classify_sheet_asset_type(cls, row: dict[str, Any]) -> Optional[str]:
        """Classify supported Datasheet electronics without requiring a QR code."""
        kategori = (cls._text(row.get("KATEGORI ASSET")) or "").casefold()
        sub1 = (cls._text(row.get("SUB KATEGORI 1")) or "").casefold()
        sub2 = (cls._text(row.get("SUB KATEGORI 2")) or "").casefold()
        if kategori != "elektronik":
            return None
        if sub1 == "monitor" or sub2 == "monitor":
            return "Monitor"
        if (sub1 == "komputer" and sub2 in {"cpu", "laptop"}) or sub1 in {
            "cpu",
            "laptop",
        }:
            return "Computer"
        return None

    @classmethod
    def map_sheet_row(
        cls,
        row: dict[str, Any],
        *,
        include_finance: bool = True,
    ) -> Optional[AssetSyncRequest]:
        asset_type = cls.classify_sheet_asset_type(row)
        if asset_type is None:
            return None

        qrcode = cls._text(row.get("QRCODE UNIT"))
        if not qrcode:
            return None

        brand = cls._text(row.get("MERK"))
        model = cls._text(row.get("TYPE"))
        display_subcategory = cls._text(row.get("SUB KATEGORI 2")) or cls._text(row.get("SUB KATEGORI 1"))
        name = " ".join(part for part in (display_subcategory, brand, model) if part) or qrcode

        raw_location_parts = [
            cls._text(row.get("WILAYAH")),
            cls._text(row.get("CABANG")),
            cls._text(row.get("AREA")),
            cls._text(row.get("LOKASI")),
        ]
        location_parts: list[str] = []
        previous_location_part: Optional[str] = None
        for part in raw_location_parts:
            if part is None:
                continue
            normalized_part = " ".join(part.split()).casefold()
            if normalized_part == previous_location_part:
                continue
            previous_location_part = normalized_part
            location_parts.append(part)
        location = " > ".join(location_parts) or None

        if include_finance:
            dat_number = cls._text(row.get("NO. ASSET AKUNTANSI (DAT)"))
            buy_date = cls._parse_buy_date(row.get("TAHUN PEROLEHAN"))
            value = cls._parse_currency(row.get("NILAI RUPIAH"))
            amortization = cls._text(row.get("PENYUSUTAN"))
            cls._parse_amortization(amortization)
        else:
            dat_number = None
            buy_date = None
            value = None
            amortization = None

        return AssetSyncRequest(
            qrcode=qrcode,
            name=name,
            dat_number=dat_number,
            asset_type=asset_type,
            brand=brand,
            model=model,
            category=cls._text(row.get("JENIS ASSET")),
            location=location,
            status=cls._text(row.get("KONDISI")),
            user=cls._text(row.get("NAMA USER")),
            comment=cls._text(row.get("KETERANGAN")),
            buy_date=buy_date,
            value=value,
            amortization=amortization,
        )

    @staticmethod
    def _select_plans(plans: list[SyncPlan], *, fatal_reason: Optional[str]) -> int:
        """Select a deterministic subset without exceeding the mutation cap."""
        selected_cost = 0
        mutation_cap = settings.SYNC_MAX_GLPI_MUTATIONS_PER_RUN
        for plan in sorted(plans, key=lambda item: (item.row_number, item.request.qrcode.casefold())):
            if fatal_reason:
                plan.selection_reason = fatal_reason
            elif plan.write_cost == 0:
                plan.selection_reason = "no_changes"
            elif plan.action == "CREATE" and not settings.SYNC_ALLOW_CREATE:
                plan.selection_reason = "create_disabled"
            elif (
                plan.infocom_action in {"CREATE", "UPDATE"}
                and not settings.SYNC_FINANCE_ENABLED
            ):
                plan.selection_reason = "finance_disabled"
            elif plan.infocom_action == "CREATE" and not settings.SYNC_ALLOW_INFOCOM_CREATE:
                plan.selection_reason = "infocom_create_disabled"
            elif plan.infocom_action == "UPDATE" and not settings.SYNC_ALLOW_INFOCOM_UPDATE:
                plan.selection_reason = "infocom_update_disabled"
            elif mutation_cap == 0:
                plan.selection_reason = "mutation_cap_zero"
            elif selected_cost + plan.write_cost > mutation_cap:
                plan.selection_reason = "mutation_cap_exceeded"
            else:
                plan.selected = True
                plan.selection_reason = "selected"
                selected_cost += plan.write_cost
        return selected_cost

    @staticmethod
    def _manifest_material(
        *,
        headers: list[str],
        rows: list[dict[str, Any]],
        plans: list[SyncPlan],
        summary: dict[str, Any],
        preflight_errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        source_sha256 = compute_manifest_hash(
            {
                "sheet_name": settings.SHEET_NAME,
                "headers": headers,
                "rows": rows,
            }
        )
        count_keys = (
            "fetched",
            "eligible",
            "unique_candidates",
            "duplicate_groups",
            "duplicates_skipped",
            "duplicate_dat_groups",
            "duplicate_dat_rows",
            "ineligible_skipped",
            "scope_skipped",
            "planned_create",
            "planned_update",
            "planned_noop",
            "planned_mutations",
            "selected_plans",
            "selected_mutations",
            "blocked_create",
            "blocked_infocom_create",
            "blocked_infocom_update",
            "finance_enabled",
            "write_transport_safe",
            "deferred_by_limit",
            "preflight_errors",
            "readiness_status",
        )
        return {
            "app_version": __version__,
            "entity": settings.GLPI_ENTITY,
            "target_identity": {
                "glpi_url": SyncService._canonical_glpi_url_identity(settings.GLPI_URL),
                "spreadsheet_id_sha256": SyncService._spreadsheet_id_sha256(
                    settings.SPREADSHEET_ID
                ),
            },
            "sheet_name": settings.SHEET_NAME,
            "headers": headers,
            "source_sha256": source_sha256,
            "policy": {
                "asset_types": list(settings.SYNC_ASSET_TYPES),
                "datasheet_scope_selector": DATASHEET_SCOPE_SELECTOR,
                "finance_enabled": settings.SYNC_FINANCE_ENABLED,
                "allow_create": settings.SYNC_ALLOW_CREATE,
                "allow_infocom_create": settings.SYNC_ALLOW_INFOCOM_CREATE,
                "allow_infocom_update": settings.SYNC_ALLOW_INFOCOM_UPDATE,
                "blank_field_policy": "preserve_glpi",
                "require_https_for_writes": True,
                "glpi_verify_tls": settings.GLPI_VERIFY_TLS,
                "write_transport_safe": SyncService._write_transport_safe(),
                "max_glpi_mutations_per_run": settings.SYNC_MAX_GLPI_MUTATIONS_PER_RUN,
            },
            "summary": {key: summary[key] for key in count_keys},
            "preflight_errors": preflight_errors,
            "items": [plan.to_manifest_item() for plan in plans],
        }

    async def run_batch_sync(self) -> dict[str, Any]:
        try:
            return await self._run_batch_sync()
        finally:
            try:
                await self.glpi.kill_session()
            except Exception as exc:
                logger.warning("Failed to close the batch GLPI session cleanly: {}", exc)

    async def _run_batch_sync(self) -> dict[str, Any]:
        from app.services.datasheet_schema import require_valid_headers
        from app.services.sheets_client import SheetsClient

        summary: dict[str, Any] = {
            "fetched": 0,
            "eligible": 0,
            "unique_candidates": 0,
            "planned_create": 0,
            "planned_update": 0,
            "planned_noop": 0,
            "planned_mutations": 0,
            "selected_plans": 0,
            "selected_mutations": 0,
            "blocked_create": 0,
            "blocked_infocom_create": 0,
            "blocked_infocom_update": 0,
            "finance_enabled": settings.SYNC_FINANCE_ENABLED,
            "deferred_by_limit": 0,
            "dry_run_blocked_plans": 0,
            "preflight_errors": 0,
            "processed": 0,
            "would_create": 0,
            "would_update": 0,
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
            "partial_mutations": 0,
            "duplicates_skipped": 0,
            "duplicate_groups": 0,
            "duplicate_dat_groups": 0,
            "duplicate_dat_rows": 0,
            "ineligible_skipped": 0,
            "scope_skipped": 0,
            "asset_types": list(settings.SYNC_ASSET_TYPES),
            "write_transport_safe": self._write_transport_safe(),
            "manifest_sha256": None,
            "manifest_path": None,
            "approval_status": "not_evaluated",
            "readiness_status": "not_evaluated",
            "header_count": 0,
        }
        logger.info("Starting batch sync from authoritative Google Sheet '{}'.", settings.SHEET_NAME)

        try:
            sheets_client = SheetsClient()
            headers, rows = sheets_client.read_asset_snapshot(
                settings.SPREADSHEET_ID,
                settings.SHEET_NAME,
            )
            summary["header_count"] = len(headers)
            require_valid_headers(headers)
        except Exception as exc:
            logger.error("Batch sync could not read Google Sheets: {}", exc)
            summary["errors"] += 1
            summary["approval_status"] = "source_schema_error"
            return summary

        summary["fetched"] = len(rows)
        eligible_requests: list[tuple[int, AssetSyncRequest]] = []
        preflight_errors: list[dict[str, Any]] = []

        for row_number, row in enumerate(rows, start=2):
            try:
                asset_type = self.classify_sheet_asset_type(row)
                if asset_type is None:
                    summary["ineligible_skipped"] += 1
                    continue
                if asset_type not in settings.SYNC_ASSET_TYPES:
                    summary["scope_skipped"] += 1
                    continue
                request = self.map_sheet_row(row, include_finance=False)
                if request is None or request.asset_type != asset_type:
                    raise ValueError("Asset mapping changed the Datasheet classification")
                if settings.SYNC_FINANCE_ENABLED:
                    request = self.map_sheet_row(row, include_finance=True)
                    if request is None:  # Defensive: type classification must be stable.
                        raise ValueError("Finance mapping changed the asset classification")
                eligible_requests.append((row_number, request))
            except Exception as exc:
                summary["errors"] += 1
                summary["preflight_errors"] += 1
                preflight_errors.append(
                    {
                        "row_number": row_number,
                        "qrcode": self._text(row.get("QRCODE UNIT")),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                logger.exception("Datasheet mapping failed at row {}: {}", row_number, exc)

        summary["eligible"] = len(eligible_requests)
        qrcode_counts = Counter(request.qrcode.casefold() for _, request in eligible_requests)
        duplicate_qrcodes = {qrcode for qrcode, count in qrcode_counts.items() if count > 1}
        summary["duplicate_groups"] = len(duplicate_qrcodes)
        summary["duplicates_skipped"] = sum(qrcode_counts[qrcode] for qrcode in duplicate_qrcodes)

        unique_requests: list[tuple[int, AssetSyncRequest]] = []
        logged_duplicates: set[str] = set()
        for row_number, request in eligible_requests:
            normalized_qrcode = request.qrcode.casefold()
            if normalized_qrcode in duplicate_qrcodes:
                if normalized_qrcode not in logged_duplicates:
                    logger.error(
                        "Skipping every row for one duplicate QRCODE UNIT group (first seen at row {}).",
                        row_number,
                    )
                    logged_duplicates.add(normalized_qrcode)
                continue
            unique_requests.append((row_number, request))

        summary["unique_candidates"] = len(unique_requests)
        dat_counts = Counter(
            " ".join(request.dat_number.split()).casefold()
            for _, request in unique_requests
            if request.dat_number
        )
        duplicate_dat_numbers = {
            dat_number for dat_number, count in dat_counts.items() if count > 1
        }
        summary["duplicate_dat_groups"] = len(duplicate_dat_numbers)
        summary["duplicate_dat_rows"] = sum(
            dat_counts[dat_number] for dat_number in duplicate_dat_numbers
        )
        plans: list[SyncPlan] = []

        for row_number, request in unique_requests:
            try:
                plans.append(await self.preflight_sync(request, row_number=row_number))
            except Exception as exc:
                summary["errors"] += 1
                summary["preflight_errors"] += 1
                preflight_errors.append(
                    {
                        "row_number": row_number,
                        "qrcode": request.qrcode,
                        "asset_type": request.asset_type,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                logger.error("Preflight failed for Datasheet row {}: {}", row_number, exc)

        summary["planned_create"] = sum(plan.action == "CREATE" for plan in plans)
        summary["planned_update"] = sum(plan.action == "UPDATE" for plan in plans)
        summary["planned_noop"] = sum(plan.write_cost == 0 for plan in plans)
        summary["would_create"] = summary["planned_create"]
        summary["would_update"] = sum(
            plan.action != "CREATE" and plan.write_cost > 0 for plan in plans
        )
        summary["planned_mutations"] = sum(plan.write_cost for plan in plans)

        fatal_reason = None
        if not summary["write_transport_safe"]:
            fatal_reason = "unsafe_write_transport"
        if summary["duplicate_groups"]:
            fatal_reason = "source_duplicates"
        if summary["duplicate_dat_groups"]:
            fatal_reason = "source_dat_duplicates"
        if summary["preflight_errors"]:
            fatal_reason = "preflight_errors"
        selected_cost = self._select_plans(plans, fatal_reason=fatal_reason)
        summary["selected_plans"] = sum(plan.selected for plan in plans)
        summary["selected_mutations"] = selected_cost
        summary["blocked_create"] = sum(
            plan.selection_reason == "create_disabled" for plan in plans
        )
        summary["blocked_infocom_create"] = sum(
            plan.selection_reason == "infocom_create_disabled" for plan in plans
        )
        summary["blocked_infocom_update"] = sum(
            plan.selection_reason == "infocom_update_disabled" for plan in plans
        )
        summary["deferred_by_limit"] = sum(
            plan.selection_reason in {"mutation_cap_zero", "mutation_cap_exceeded"}
            for plan in plans
        )
        if fatal_reason:
            summary["readiness_status"] = fatal_reason
        elif any(plan.selected for plan in plans):
            summary["readiness_status"] = "ready_for_approval"
        elif plans and all(plan.write_cost == 0 for plan in plans):
            summary["readiness_status"] = "no_changes"
        else:
            summary["readiness_status"] = "policy_blocked"

        try:
            material = self._manifest_material(
                headers=headers,
                rows=rows,
                plans=plans,
                summary=summary,
                preflight_errors=preflight_errors,
            )
            manifest = build_manifest(material)
            manifest_path = persist_manifest(manifest, settings.SYNC_MANIFEST_DIR)
        except Exception as exc:
            summary["errors"] += 1
            summary["approval_status"] = "manifest_error"
            logger.error("Batch blocked because the approval manifest could not be persisted: {}", exc)
            return summary

        manifest_hash = manifest["manifest_sha256"]
        summary["manifest_sha256"] = manifest_hash
        summary["manifest_path"] = str(manifest_path)

        if self.dry_run:
            if summary["readiness_status"] == "ready_for_approval":
                summary["approval_status"] = "dry_run_ready"
            elif summary["readiness_status"] == "no_changes":
                summary["approval_status"] = "dry_run_no_changes"
            else:
                summary["approval_status"] = "dry_run_blocked"
            for plan in plans:
                started_at = time.time()
                if plan.action == "CREATE":
                    response_status = "would_create"
                    audit_action = "DRY_RUN_CREATE"
                elif plan.write_cost:
                    response_status = "would_update"
                    audit_action = "DRY_RUN_UPDATE"
                else:
                    response_status = "unchanged"
                    audit_action = "DRY_RUN_NOOP"
                response = AssetSyncResponse(
                    status=response_status,
                    glpi_id=plan.expected_glpi_id,
                    message="Dry-run preflight only; GLPI was not changed.",
                    dry_run=True,
                )
                plan_ready = plan.selection_reason in {"selected", "no_changes"}
                audit_status = "SUCCESS" if plan_ready else "BLOCKED"
                if not plan_ready:
                    summary["dry_run_blocked_plans"] += 1
                try:
                    await self._audit_result(
                        plan,
                        action=audit_action,
                        status=audit_status,
                        response=response,
                        started_at=started_at,
                    )
                    summary["processed"] += 1
                except Exception as exc:
                    summary["errors"] += 1
                    logger.error("Failed to audit dry-run plan for row {}: {}", plan.row_number, exc)
            logger.info("Batch dry-run completed without GLPI mutations: {}", summary)
            return summary

        if fatal_reason:
            summary["approval_status"] = fatal_reason
            logger.error("Batch write blocked by {} before any GLPI mutation.", fatal_reason)
            return summary

        selected_plans = [plan for plan in plans if plan.selected]
        if not selected_plans:
            summary["approval_status"] = "no_selected_mutations"
            logger.warning("Batch write blocked because policy selected no GLPI mutations.")
            return summary

        approved_hash = settings.SYNC_APPROVED_MANIFEST_SHA256.strip().lower()
        if not approved_hash:
            summary["approval_status"] = "approval_missing"
            logger.warning("Batch write blocked because no manifest hash was approved.")
            return summary
        if approved_hash != manifest_hash:
            summary["approval_status"] = "approval_mismatch"
            logger.error("Batch write blocked because the approved manifest is stale or different.")
            return summary

        try:
            claim_manifest(manifest_hash, settings.SYNC_MANIFEST_DIR)
        except ManifestAlreadyClaimedError:
            summary["approval_status"] = "approval_already_consumed"
            logger.error("Batch write blocked because this manifest approval was already consumed.")
            return summary
        except Exception as exc:
            summary["errors"] += 1
            summary["approval_status"] = "approval_claim_error"
            logger.error("Batch write blocked because approval could not be claimed atomically: {}", exc)
            return summary

        summary["approval_status"] = "approved"
        for plan in selected_plans:
            started_at = time.time()
            try:
                result = await self._apply_plan(plan)
            except Exception as exc:
                summary["errors"] += 1
                partial_glpi_id = getattr(exc, "glpi_id", plan.expected_glpi_id)
                if isinstance(exc, PartialMutationError):
                    summary["partial_mutations"] += 1
                    summary["approval_status"] = "partial_write_failed"
                else:
                    summary["approval_status"] = "write_failed"
                error_response = AssetSyncResponse(
                    status="error",
                    glpi_id=partial_glpi_id,
                    message="Approved write failed; remaining plans were aborted.",
                )
                try:
                    await self._audit_result(
                        plan,
                        action=plan.action,
                        status="ERROR",
                        response=error_response,
                        started_at=started_at,
                        error=str(exc),
                    )
                except Exception as audit_exc:
                    logger.error("Failed to audit write error for row {}: {}", plan.row_number, audit_exc)
                logger.error("Approved write failed at row {}; aborting remaining plans: {}", plan.row_number, exc)
                break

            summary["processed"] += 1
            summary[result.status] += 1
            try:
                await self._audit_result(
                    plan,
                    action=plan.action,
                    status="SUCCESS",
                    response=result,
                    started_at=started_at,
                )
            except Exception as exc:
                summary["errors"] += 1
                summary["approval_status"] = "audit_failed"
                logger.error("Audit failed after row {}; aborting remaining plans: {}", plan.row_number, exc)
                break
        else:
            summary["approval_status"] = "completed"

        logger.info("Batch sync completed: {}", summary)
        return summary
