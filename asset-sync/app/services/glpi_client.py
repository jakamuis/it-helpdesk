import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from app.core.config import settings
import typing

class GLPIClientError(Exception):
    pass

class GLPIClient:
    SUPPORTED_ASSET_TYPES = {"Computer", "Monitor"}

    def __init__(self):
        self.base_url = settings.GLPI_URL.rstrip('/')
        self.headers = {
            "App-Token": settings.GLPI_APP_TOKEN,
            "Authorization": f"user_token {settings.GLPI_USER_TOKEN}",
            "Content-Type": "application/json"
        }
        self.session_token = None

    @staticmethod
    def _validate_asset_type(itemtype: str) -> None:
        if itemtype not in GLPIClient.SUPPORTED_ASSET_TYPES:
            raise GLPIClientError(f"Unsupported GLPI asset type: {itemtype}")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=settings.TIMEOUT, verify=settings.GLPI_VERIFY_TLS)

    async def _init_session(self):
        if self.session_token:
            return
            
        async with self._client() as client:
            response = await client.get(f"{self.base_url}/initSession", headers=self.headers)
            if response.status_code != 200:
                logger.error("GLPI initSession failed with HTTP {}", response.status_code)
                raise GLPIClientError(f"GLPI initSession failed: HTTP {response.status_code}")
            data = response.json()
            self.session_token = data.get("session_token")
            if not self.session_token:
                raise GLPIClientError("GLPI initSession returned no session token")
            self.headers["Session-Token"] = self.session_token
            logger.info("GLPI session initialized.")

    async def _ensure_session(self):
        if not self.session_token:
            await self._init_session()


    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def search_asset_by_qrcode(
        self,
        qrcode: str,
        *,
        itemtype: str = "Computer",
        entities_id: typing.Optional[int] = None,
        recursive: bool = False,
    ) -> typing.Optional[dict]:
        """Return one exact QR match or fail closed if GLPI reports duplicates."""
        self._validate_asset_type(itemtype)
        normalized_qrcode = qrcode.strip().casefold()
        if not normalized_qrcode:
            raise GLPIClientError("QRCODE UNIT cannot be blank")
        await self._ensure_session()
        
        params = {
            "criteria[0][field]": 6,
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": qrcode,
            "forcedisplay[0]": 2,
            "forcedisplay[1]": 6,
            "forcedisplay[2]": 80,
            "range": "0-49",
        }
        if recursive:
            params["is_recursive"] = True
        if entities_id is not None:
            params.update(
                {
                    "criteria[1][link]": "AND",
                    "criteria[1][field]": 80,
                    "criteria[1][searchtype]": "equals",
                    "criteria[1][value]": entities_id,
                }
            )

        async with self._client() as client:
            response = await client.get(f"{self.base_url}/search/{itemtype}", headers=self.headers, params=params)
            
            if response.status_code == 206:
                raise GLPIClientError("GLPI QR search returned a partial result set")

            if response.status_code == 200:
                data = response.json()
                results = data.get("data", [])
                if not results:
                    return None
                exact_matches = [
                    result
                    for result in results
                    if str(result.get("6", "")).strip().casefold() == normalized_qrcode
                ]
                if len(exact_matches) > 1:
                    raise GLPIClientError(f"Duplicate QRCODE UNIT detected in GLPI for {itemtype}")
                if not exact_matches:
                    raise GLPIClientError("GLPI QR search returned unverifiable non-exact rows")
                asset_id = exact_matches[0].get("2")
                if asset_id is None:
                    raise GLPIClientError("GLPI QR search result did not include an asset ID")
                return {"id": int(asset_id), "qrcode": exact_matches[0].get("6")}
            
            logger.error("GLPI asset search failed with HTTP {}", response.status_code)
            raise GLPIClientError(f"Search failed: {response.status_code}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def get_asset(self, asset_id: int, *, itemtype: str) -> dict:
        """Fetch one complete Computer/Monitor record for identity verification."""
        self._validate_asset_type(itemtype)
        await self._ensure_session()

        async with self._client() as client:
            response = await client.get(
                f"{self.base_url}/{itemtype}/{asset_id}",
                headers=self.headers,
            )

        if response.status_code != 200:
            raise GLPIClientError(
                f"GLPI asset detail failed for {itemtype}: HTTP {response.status_code}"
            )
        record = response.json()
        if not isinstance(record, dict):
            raise GLPIClientError("GLPI asset detail returned an invalid record")
        try:
            record_id = int(record.get("id"))
        except (TypeError, ValueError) as exc:
            raise GLPIClientError("GLPI asset detail did not include a valid ID") from exc
        if record_id != asset_id:
            raise GLPIClientError("GLPI asset detail ID did not match the requested asset")
        return record

    async def resolve_asset_identity(
        self,
        qrcode: str,
        *,
        expected_itemtype: str,
        expected_entities_id: int,
    ) -> typing.Optional[dict]:
        """Resolve one QR across supported types and the recursive entity scope.

        A match is usable only when its item type and entity are exactly the
        expected values. Any duplicate or scope mismatch fails closed so a
        missing scoped lookup cannot be mistaken for permission to create.
        """
        self._validate_asset_type(expected_itemtype)
        normalized_qrcode = qrcode.strip().casefold()
        if not normalized_qrcode:
            raise GLPIClientError("QRCODE UNIT cannot be blank")

        identities = []
        for itemtype in sorted(self.SUPPORTED_ASSET_TYPES):
            match = await self.search_asset_by_qrcode(
                qrcode,
                itemtype=itemtype,
                recursive=True,
            )
            if match is None:
                continue

            record = await self.get_asset(int(match["id"]), itemtype=itemtype)
            record_qrcode = str(record.get("otherserial", "")).strip()
            if record_qrcode.casefold() != normalized_qrcode:
                raise GLPIClientError(
                    "GLPI asset detail did not confirm the exact QRCODE UNIT"
                )

            raw_entity_id = record.get("entities_id")
            if isinstance(raw_entity_id, bool):
                raise GLPIClientError("GLPI asset detail included an invalid entity ID")
            try:
                entity_id = int(raw_entity_id)
            except (TypeError, ValueError) as exc:
                raise GLPIClientError(
                    "GLPI asset detail did not include a valid entity ID"
                ) from exc

            identities.append(
                {
                    "id": int(match["id"]),
                    "qrcode": record_qrcode,
                    "itemtype": itemtype,
                    "entities_id": entity_id,
                    "record": record,
                }
            )

        if not identities:
            return None
        if len(identities) > 1:
            raise GLPIClientError(
                "QRCODE UNIT collision detected across GLPI asset types or entities"
            )

        identity = identities[0]
        if identity["itemtype"] != expected_itemtype:
            raise GLPIClientError(
                "QRCODE UNIT already belongs to a different GLPI asset type"
            )
        if identity["entities_id"] != expected_entities_id:
            raise GLPIClientError(
                "QRCODE UNIT already belongs to a different GLPI entity"
            )
        return identity

    async def create_asset(self, payload: dict, itemtype: str = "Computer") -> int:
        """Create an asset once; an ambiguous transport failure must be reconciled by QR."""
        self._validate_asset_type(itemtype)
        await self._ensure_session()
        async with self._client() as client:
            res = await client.post(f"{self.base_url}/{itemtype}", headers=self.headers, json={"input": payload})
            
            if res.status_code in [200, 201]:
                asset_id = res.json().get("id")
                if asset_id is None:
                    raise GLPIClientError("GLPI create response did not include an asset ID")
                return int(asset_id)
                
            logger.error("GLPI asset create failed with HTTP {}", res.status_code)
            raise GLPIClientError(f"Create failed: {res.status_code}")

    async def update_asset(self, asset_id: int, payload: dict, itemtype: str = "Computer") -> bool:
        """Update an existing asset in GLPI"""
        self._validate_asset_type(itemtype)
        await self._ensure_session()
        update_payload = {**payload, "id": asset_id}
        
        async with self._client() as client:
            res = await client.put(f"{self.base_url}/{itemtype}/{asset_id}", headers=self.headers, json={"input": update_payload})
            
            if res.status_code in [200, 204]:
                return True
                
            logger.error("GLPI asset update failed with HTTP {}", res.status_code)
            raise GLPIClientError(f"Update failed: {res.status_code}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def find_dropdown(self, item_type: str, name: str) -> typing.Optional[int]:
        """Return an existing dropdown ID without creating or changing taxonomy."""
        if not name:
            return None
            
        await self._ensure_session()
        
        # 1. Search if it exists
        params = {
            "criteria[0][field]": 1, # 'name' field is usually 1 or 2. Actually in search it's 1 for name, 2 for id. Let's assume 1.
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": name,
            "forcedisplay[0]": 2,
            "forcedisplay[1]": 1,
            "forcedisplay[2]": 14,
        }
        
        # In standard GLPI, name is usually search option 1 or 2 depending on the item type. For most dropdowns, name is 1.
        
        async with self._client() as client:
            search_res = await client.get(f"{self.base_url}/search/{item_type}", headers=self.headers, params=params)
            
            if search_res.status_code == 206:
                raise GLPIClientError(f"Dropdown search returned partial results for {item_type}")

            if search_res.status_code == 200:
                data = search_res.json()
                results = data.get("data", [])
                exact_ids = []
                for r in results:
                    val = str(r.get("1", "")).strip().lower()
                    val14 = str(r.get("14", "")).strip().lower() # fallback for Name
                    if val == name.strip().lower() or val14 == name.strip().lower() or val.endswith(f"> {name.strip().lower()}"):
                        if "2" in r:
                            exact_ids.append(int(r["2"]))

                unique_ids = sorted(set(exact_ids))
                if len(unique_ids) > 1:
                    raise GLPIClientError(f"Ambiguous dropdown name for {item_type}")
                return unique_ids[0] if unique_ids else None

            raise GLPIClientError(f"Dropdown search failed for {item_type}: HTTP {search_res.status_code}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def get_infocom(
        self,
        infocom_id: int,
        *,
        expected_itemtype: str,
        expected_items_id: int,
    ) -> dict:
        """Fetch and verify one Infocom record and its owning asset."""
        self._validate_asset_type(expected_itemtype)
        if (
            isinstance(infocom_id, bool)
            or not isinstance(infocom_id, int)
            or infocom_id <= 0
            or isinstance(expected_items_id, bool)
            or not isinstance(expected_items_id, int)
            or expected_items_id <= 0
        ):
            raise GLPIClientError("Infocom and owner IDs must be positive integers")
        await self._ensure_session()

        async with self._client() as client:
            response = await client.get(
                f"{self.base_url}/Infocom/{infocom_id}",
                headers=self.headers,
            )
        if response.status_code != 200:
            raise GLPIClientError(f"GLPI Infocom detail failed: HTTP {response.status_code}")
        record = response.json()
        if not isinstance(record, dict):
            raise GLPIClientError("GLPI Infocom detail returned an invalid record")
        try:
            record_id = int(record.get("id"))
            owner_id = int(record.get("items_id"))
        except (TypeError, ValueError) as exc:
            raise GLPIClientError(
                "GLPI Infocom detail did not expose verifiable ownership"
            ) from exc
        if (
            record_id != infocom_id
            or owner_id != expected_items_id
            or record.get("itemtype") != expected_itemtype
        ):
            raise GLPIClientError(
                "GLPI Infocom record ownership did not match the requested asset"
            )
        return record

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def resolve_infocom_by_dat(self, dat_number: str) -> typing.Optional[dict]:
        """Resolve one exact DAT number in the recursively visible Infocom scope."""
        normalized_dat = " ".join(str(dat_number).split()).casefold()
        if not normalized_dat:
            raise GLPIClientError("DAT number cannot be blank")
        await self._ensure_session()

        params = {
            "criteria[0][field]": 12,
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": dat_number.strip(),
            "forcedisplay[0]": 2,
            "forcedisplay[1]": 12,
            "forcedisplay[2]": 20,
            "forcedisplay[3]": 21,
            "is_recursive": True,
            "range": "0-49",
        }
        async with self._client() as client:
            response = await client.get(
                f"{self.base_url}/search/Infocom",
                headers=self.headers,
                params=params,
            )

        if response.status_code == 206:
            raise GLPIClientError("GLPI DAT search returned a partial result set")
        if response.status_code != 200:
            raise GLPIClientError(f"DAT search failed: HTTP {response.status_code}")
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("data", []), list):
            raise GLPIClientError("GLPI DAT search returned an invalid result set")
        results = body.get("data", [])
        if not results:
            return None

        infocom_ids: set[int] = set()
        for result in results:
            if not isinstance(result, dict) or "2" not in result or "12" not in result:
                raise GLPIClientError("GLPI DAT search returned an unverifiable row")
            result_dat = " ".join(str(result["12"]).split()).casefold()
            if result_dat != normalized_dat:
                raise GLPIClientError("GLPI DAT search returned a non-exact row")
            try:
                infocom_id = int(result["2"])
            except (TypeError, ValueError) as exc:
                raise GLPIClientError("GLPI DAT search returned an invalid Infocom ID") from exc
            if infocom_id <= 0:
                raise GLPIClientError("GLPI DAT search returned an invalid Infocom ID")
            infocom_ids.add(infocom_id)

        if len(infocom_ids) > 1:
            raise GLPIClientError("Duplicate DAT number detected across GLPI Infocom records")

        infocom_id = next(iter(infocom_ids))
        async with self._client() as client:
            detail_response = await client.get(
                f"{self.base_url}/Infocom/{infocom_id}",
                headers=self.headers,
            )
        if detail_response.status_code != 200:
            raise GLPIClientError(
                f"GLPI DAT owner detail failed: HTTP {detail_response.status_code}"
            )
        record = detail_response.json()
        if not isinstance(record, dict):
            raise GLPIClientError("GLPI DAT owner detail returned an invalid record")
        try:
            record_id = int(record.get("id"))
            owner_id = int(record.get("items_id"))
        except (TypeError, ValueError) as exc:
            raise GLPIClientError("GLPI DAT owner could not be verified") from exc
        owner_itemtype = record.get("itemtype")
        detail_dat = " ".join(str(record.get("immo_number", "")).split()).casefold()
        if (
            record_id != infocom_id
            or owner_id <= 0
            or not isinstance(owner_itemtype, str)
            or not owner_itemtype
            or detail_dat != normalized_dat
        ):
            raise GLPIClientError("GLPI DAT owner could not be verified")
        return {
            "id": infocom_id,
            "itemtype": owner_itemtype,
            "items_id": owner_id,
            "dat_number": record.get("immo_number"),
            "record": record,
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def resolve_infocom(self, itemtype: str, items_id: int) -> typing.Optional[dict]:
        """Return one verified Infocom identity and record for an exact owner."""
        self._validate_asset_type(itemtype)
        if isinstance(items_id, bool) or not isinstance(items_id, int) or items_id <= 0:
            raise GLPIClientError("Infocom owner asset ID must be a positive integer")
        await self._ensure_session()
        
        # Verified on GLPI 11.0.8: field 20=itemtype and 21=items_id.
        params = {
            "criteria[0][field]": 21, # items_id
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": items_id,
            "criteria[1][link]": "AND",
            "criteria[1][field]": 20, # itemtype
            "criteria[1][searchtype]": "equals",
            "criteria[1][value]": itemtype,
            "forcedisplay[0]": 2,
            "forcedisplay[1]": 20,
            "forcedisplay[2]": 21,
            "is_recursive": True,
            "range": "0-49",
        }
        
        async with self._client() as client:
            response = await client.get(
                f"{self.base_url}/search/Infocom",
                headers=self.headers,
                params=params,
            )

        if response.status_code == 206:
            raise GLPIClientError("GLPI Infocom search returned a partial result set")
        if response.status_code != 200:
            raise GLPIClientError(f"Infocom search failed: HTTP {response.status_code}")

        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("data", []), list):
            raise GLPIClientError("GLPI Infocom search returned an invalid result set")
        results = body.get("data", [])
        if not results:
            return None

        infocom_ids: set[int] = set()
        for result in results:
            if not isinstance(result, dict) or "2" not in result:
                raise GLPIClientError("GLPI Infocom search returned an unverifiable row")
            try:
                infocom_id = int(result["2"])
            except (TypeError, ValueError) as exc:
                raise GLPIClientError(
                    "GLPI Infocom search returned an invalid record ID"
                ) from exc
            if infocom_id <= 0:
                raise GLPIClientError("GLPI Infocom search returned an invalid record ID")
            infocom_ids.add(infocom_id)

        if len(infocom_ids) > 1:
            raise GLPIClientError("Duplicate Infocom records detected")

        infocom_id = next(iter(infocom_ids))
        record = await self.get_infocom(
            infocom_id,
            expected_itemtype=itemtype,
            expected_items_id=items_id,
        )
        return {"id": infocom_id, "record": record}

    async def search_infocom(self, itemtype: str, items_id: int) -> typing.Optional[int]:
        """Compatibility wrapper returning the verified Infocom ID only."""
        identity = await self.resolve_infocom(itemtype, items_id)
        return int(identity["id"]) if identity is not None else None

    async def create_infocom(self, data: dict) -> int:
        await self._ensure_session()
        
        payload = {"input": data}
        async with self._client() as client:
            response = await client.post(f"{self.base_url}/Infocom", headers=self.headers, json=payload)
            if response.status_code in [200, 201]:
                res_data = response.json()
                infocom_id = res_data.get("id")
                if infocom_id is None:
                    raise GLPIClientError("GLPI create Infocom response did not include an ID")
                return int(infocom_id)
            
            logger.error("GLPI Infocom create failed with HTTP {}", response.status_code)
            raise GLPIClientError(f"Create Infocom failed: {response.status_code}")

    async def update_infocom(self, infocom_id: int, data: dict) -> bool:
        await self._ensure_session()
        
        payload = {"input": {"id": infocom_id, **data}}
        async with self._client() as client:
            response = await client.put(f"{self.base_url}/Infocom/{infocom_id}", headers=self.headers, json=payload)
            if response.status_code in [200, 204]:
                return True
                
            logger.error("GLPI Infocom update failed with HTTP {}", response.status_code)
            raise GLPIClientError(f"Update Infocom failed: {response.status_code}")

    async def kill_session(self):
        try:
            if self.session_token:
                async with self._client() as client:
                    response = await client.get(f"{self.base_url}/killSession", headers=self.headers)
                    response.raise_for_status()
        finally:
            self.session_token = None
            self.headers.pop("Session-Token", None)
