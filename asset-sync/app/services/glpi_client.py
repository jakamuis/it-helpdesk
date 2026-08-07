import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from app.core.config import settings
import json
import typing

class GLPIClientError(Exception):
    pass

class GLPIClient:
    def __init__(self):
        self.base_url = settings.GLPI_URL.rstrip('/')
        self.headers = {
            "App-Token": settings.GLPI_APP_TOKEN,
            "Authorization": f"user_token {settings.GLPI_USER_TOKEN}",
            "Content-Type": "application/json"
        }
        self.session_token = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def _init_session(self):
        if self.session_token:
            return
            
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            response = await client.get(f"{self.base_url}/initSession", headers=self.headers)
            if response.status_code != 200:
                logger.error(f"initSession failed: {response.text}")
            response.raise_for_status()
            data = response.json()
            self.session_token = data.get("session_token")
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
    async def search_asset(self, value: str, field_id: int = 6, itemtype: str = "Computer") -> typing.Optional[dict]:
        """Search for an asset by value and search field ID. Default field 6 is otherserial (QR Code)"""
        await self._ensure_session()
        
        params = {
            "criteria[0][field]": field_id,
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": value,
            "forcedisplay[0]": 2
        }

        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            response = await client.get(f"{self.base_url}/search/{itemtype}", headers=self.headers, params=params)
            
            if response.status_code in [200, 206]:
                data = response.json()
                results = data.get("data", [])
                if results and "2" in results[0]:
                    return {"id": results[0]["2"]} # Usually ID is field 2
                return None
            
            logger.error(f"Error searching asset: {response.text}")
            raise GLPIClientError(f"Search failed: {response.status_code}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def create_asset(self, payload: dict, itemtype: str = "Computer") -> int:
        """Create a new asset (e.g. Computer, Monitor) in GLPI and return its ID"""
        await self._ensure_session()
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            res = await client.post(f"{self.base_url}/{itemtype}", headers=self.headers, json={"input": payload})
            
            if res.status_code in [200, 201]:
                return res.json().get("id")
                
            logger.error(f"Error creating asset: {res.text}")
            raise GLPIClientError(f"Create failed: {res.status_code}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def update_asset(self, asset_id: int, payload: dict, itemtype: str = "Computer") -> bool:
        """Update an existing asset in GLPI"""
        await self._ensure_session()
        payload["id"] = asset_id
        
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            res = await client.put(f"{self.base_url}/{itemtype}/{asset_id}", headers=self.headers, json={"input": payload})
            
            if res.status_code in [200, 204]:
                return True
                
            logger.error(f"Error updating asset: {res.text}")
            raise GLPIClientError(f"Update failed: {res.status_code}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def get_or_create_dropdown(self, item_type: str, name: str, allow_create: bool = False) -> typing.Optional[int]:
        """Generic method to get or create a dropdown value (e.g. Manufacturer, Location)"""
        if not name:
            return 0 # 0 usually means none in GLPI
            
        await self._ensure_session()
        
        # 1. Search if it exists
        params = {
            "criteria[0][field]": 1, # 'name' field is usually 1 or 2. Actually in search it's 1 for name, 2 for id. Let's assume 1.
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": name,
            "forcedisplay[0]": 2
        }
        
        # In standard GLPI, name is usually search option 1 or 2 depending on the item type. For most dropdowns, name is 1.
        
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            search_res = await client.get(f"{self.base_url}/search/{item_type}", headers=self.headers, params=params)
            
            if search_res.status_code in [200, 206]:
                data = search_res.json()
                results = data.get("data", [])
                for r in results:
                    val = str(r.get("1", "")).strip().lower()
                    val14 = str(r.get("14", "")).strip().lower() # fallback for Name
                    if val == name.strip().lower() or val14 == name.strip().lower() or val.endswith(f"> {name.strip().lower()}"):
                        if "2" in r:
                            return int(r["2"])
                    
            if not allow_create:
                return 0
                
            # 2. If not found or error in search, create it
            payload = {"input": {"name": name}}
            create_res = await client.post(f"{self.base_url}/{item_type}", headers=self.headers, json=payload)
            
            if create_res.status_code in [200, 201]:
                res_data = create_res.json()
                new_id = res_data.get("id")
                logger.info(f"Created new {item_type}: '{name}' with ID {new_id}")
                return new_id
                
            logger.warning(f"Failed to auto-provision {item_type} '{name}': {create_res.text}")
            return 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def link_monitor(self, comp_id: int, monitor_name: str) -> bool:
        """Create a Monitor asset if it doesn't exist, and link it to the Computer."""
        if not monitor_name:
            return False
            
        await self._ensure_session()
        
        # 1. Search if Monitor exists
        params = {
            "criteria[0][field]": 1,
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": monitor_name,
            "forcedisplay[0]": 2
        }
        
        monitor_id = None
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            search_res = await client.get(f"{self.base_url}/search/Monitor", headers=self.headers, params=params)
            if search_res.status_code in [200, 206]:
                data = search_res.json()
                results = data.get("data", [])
                if results and "2" in results[0]:
                    monitor_id = int(results[0]["2"])
                    
            if not monitor_id:
                # Always create Monitor if not found (since it's a physical asset specs)
                payload = {"input": {"name": monitor_name}}
                create_res = await client.post(f"{self.base_url}/Monitor", headers=self.headers, json=payload)
                if create_res.status_code in [200, 201]:
                    monitor_id = create_res.json().get("id")
                    logger.info(f"Created new Monitor: '{monitor_name}' with ID {monitor_id}")
                    
            if not monitor_id:
                return False
                
            # 2. Link Monitor to Computer
            link_payload = {"input": {"computers_id": comp_id, "itemtype": "Monitor", "items_id": monitor_id}}
            link_res = await client.post(f"{self.base_url}/Computer_Item", headers=self.headers, json=link_payload)
            return link_res.status_code in [200, 201]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def search_infocom(self, itemtype: str, items_id: int) -> typing.Optional[int]:
        """Search for an Infocom record by itemtype and items_id"""
        await self._ensure_session()
        
        # In Infocom, field 6 is usually items_id and field 7 is itemtype.
        # But we can also search using standard criteria
        params = {
            "criteria[0][field]": 21, # items_id
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": items_id,
            "criteria[1][link]": "AND",
            "criteria[1][field]": 20, # itemtype
            "criteria[1][searchtype]": "equals",
            "criteria[1][value]": itemtype
        }
        
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            response = await client.get(f"{self.base_url}/search/Infocom", headers=self.headers, params=params)
            
            if response.status_code in [200, 206]:
                data = response.json()
                results = data.get("data", [])
                if results:
                    return int(results[0]["2"]) # Return infocom ID
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def create_infocom(self, data: dict) -> int:
        await self._ensure_session()
        
        payload = {"input": data}
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            response = await client.post(f"{self.base_url}/Infocom", headers=self.headers, json=payload)
            if response.status_code in [200, 201]:
                res_data = response.json()
                return res_data.get("id")
            
            logger.error(f"Error creating infocom: {response.text}")
            raise GLPIClientError(f"Create Infocom failed: {response.status_code} - {response.text}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def update_infocom(self, infocom_id: int, data: dict) -> bool:
        await self._ensure_session()
        
        payload = {"input": {"id": infocom_id, **data}}
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            response = await client.put(f"{self.base_url}/Infocom/{infocom_id}", headers=self.headers, json=payload)
            if response.status_code in [200, 204]:
                return True
                
            logger.error(f"Error updating infocom: {response.text}")
            raise GLPIClientError(f"Update Infocom failed: {response.status_code} - {response.text}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def link_component(self, endpoint: str, foreign_key_field: str, computer_id: int, component_id: int) -> bool:
        """Generic method to link a component to a computer"""
        await self._ensure_session()
        
        # Check if link already exists
        params = {
            "criteria[0][field]": 6, # items_id is usually 6 or 4 depending on component, but actually it's safer to just let it fail or check. 
            # In Item_Device*, items_id is field 6. itemtype is 7.
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": computer_id,
            "criteria[1][link]": "AND",
            "criteria[1][field]": 7,
            "criteria[1][searchtype]": "equals",
            "criteria[1][value]": "Computer"
        }
        
        # We won't check for existence to save time, we just attempt to POST. 
        # If it's a duplicate, GLPI usually ignores it or returns an error we can catch.
        payload = {
            "input": {
                "itemtype": "Computer",
                "items_id": computer_id,
                foreign_key_field: component_id
            }
        }
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            response = await client.post(f"{self.base_url}/{endpoint}", headers=self.headers, json=payload)
            if response.status_code in [200, 201]:
                return True
                
            # If it already exists, GLPI might return 400 with a message. We just log warning.
            logger.warning(f"Failed to link {endpoint}: {response.text}")
            return False

    async def kill_session(self):
        if self.session_token:
            async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
                await client.get(f"{self.base_url}/killSession", headers=self.headers)
            self.session_token = None
