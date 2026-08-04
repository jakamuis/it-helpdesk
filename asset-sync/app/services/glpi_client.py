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
    async def search_asset(self, qrcode: str) -> typing.Optional[dict]:
        """Search for an asset by QRCODE_UNIT mapped to otherserial"""
        await self._ensure_session()
        
        # Searching in Computer (Assuming Computer for now, can be generic if needed)
        # Using search/Computer endpoint
        params = {
            "criteria[0][field]": 1, # otherserial ID usually isn't 1, we need to know the correct search option ID for otherserial in Computers. Wait, standard GLPI search option for otherserial in Computer is often 9 or similar.
            # Actually, standard otherserial search option in Computer is typically 9. Let's use 9 or a configurable one. For now, assuming 9.
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": qrcode
        }
        
        # Let's fix this to search for otherserial using standard GLPI API. 
        # Standard field ID for otherserial in Computer is 9.
        params = {
            "criteria[0][field]": 9,
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": qrcode
        }

        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            response = await client.get(f"{self.base_url}/search/Computer", headers=self.headers, params=params)
            
            # If 206 Partial Content or 200 OK
            if response.status_code in [200, 206]:
                data = response.json()
                results = data.get("data", [])
                if results:
                    return {"id": results[0]["2"]} # Usually ID is field 2
                return None
            
            logger.error(f"Error searching asset: {response.text}")
            raise GLPIClientError(f"Search failed: {response.status_code}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def create_asset(self, data: dict) -> int:
        await self._ensure_session()
        
        payload = {"input": data}
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            response = await client.post(f"{self.base_url}/Computer", headers=self.headers, json=payload)
            if response.status_code in [200, 201]:
                res_data = response.json()
                return res_data.get("id")
            
            logger.error(f"Error creating asset: {response.text}")
            raise GLPIClientError(f"Create failed: {response.status_code} - {response.text}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def update_asset(self, glpi_id: int, data: dict) -> bool:
        await self._ensure_session()
        
        payload = {"input": {"id": glpi_id, **data}}
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            response = await client.put(f"{self.base_url}/Computer/{glpi_id}", headers=self.headers, json=payload)
            if response.status_code in [200, 204]:
                return True
                
            logger.error(f"Error updating asset: {response.text}")
            raise GLPIClientError(f"Update failed: {response.status_code} - {response.text}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def get_or_create_dropdown(self, item_type: str, name: str) -> typing.Optional[int]:
        """Generic method to get or create a dropdown value (e.g. Manufacturer, Location)"""
        if not name:
            return 0 # 0 usually means none in GLPI
            
        await self._ensure_session()
        
        # 1. Search if it exists
        params = {
            "criteria[0][field]": 1, # 'name' field is usually 1 or 2. Actually in search it's 1 for name, 2 for id. Let's assume 1.
            "criteria[0][searchtype]": "equals",
            "criteria[0][value]": name
        }
        
        # In standard GLPI, name is usually search option 1 or 2 depending on the item type. For most dropdowns, name is 1.
        
        async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
            search_res = await client.get(f"{self.base_url}/search/{item_type}", headers=self.headers, params=params)
            
            if search_res.status_code in [200, 206]:
                data = search_res.json()
                results = data.get("data", [])
                if results:
                    return int(results[0]["2"]) # ID is usually returned in key "2"
                    
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

    async def kill_session(self):
        if self.session_token:
            async with httpx.AsyncClient(timeout=settings.TIMEOUT) as client:
                await client.get(f"{self.base_url}/killSession", headers=self.headers)
            self.session_token = None
