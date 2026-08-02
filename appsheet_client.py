"""
AppSheet API Client Module.

Handles direct calls to AppSheet Inbound REST API endpoints for adding, editing,
or upserting table records directly in AppSheet applications.
"""

import logging
import requests
from typing import List, Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class AppSheetClientError(Exception):
    """Base exception for AppSheet Client errors."""
    pass


class AppSheetAPIError(AppSheetClientError):
    """Raised when an AppSheet REST API call returns an error response."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class AppSheetClient:
    """
    Client for interacting directly with AppSheet REST API endpoints.

    Endpoint pattern:
    POST https://api.appsheet.com/api/v2/apps/{appId}/tables/{tableName}/Action
    """

    def __init__(
        self,
        app_id: str,
        access_key: str,
        table_name: str,
        api_base_url: str = "https://api.appsheet.com/api/v2",
        timeout: int = 15,
        max_retries: int = 3,
        backoff_factor: float = 0.5
    ):
        """
        Initialize the AppSheet Client.

        :param app_id: AppSheet Application ID (e.g. 5d5a71df-...)
        :param access_key: AppSheet Application Access Key
        :param table_name: Default table name in AppSheet application
        :param api_base_url: AppSheet REST API base URL
        :param timeout: Request timeout in seconds
        :param max_retries: Retry attempts on transient HTTP failures
        :param backoff_factor: Delay factor between retries
        """
        self.app_id = app_id
        self.access_key = access_key
        self.table_name = table_name
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout

        # Configure session with HTTP retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def post_action(
        self,
        action: str,
        rows: List[Dict[str, Any]],
        table_name: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute an Action on an AppSheet table via REST API.

        :param action: Action name ('Add', 'Edit', 'Upsert', 'Delete')
        :param rows: List of dictionaries representing table rows
        :param table_name: AppSheet table name (defaults to self.table_name)
        :param properties: Additional AppSheet action properties (Locale, Timezone, etc.)
        :return: Response dictionary from AppSheet API
        """
        target_table = table_name or self.table_name
        endpoint = f"{self.api_base_url}/apps/{self.app_id}/tables/{target_table}/Action"

        headers = {
            "ApplicationAccessKey": self.access_key,
            "Content-Type": "application/json"
        }

        default_properties = {
            "Locale": "en-US",
            "Timezone": "UTC"
        }
        if properties:
            default_properties.update(properties)

        payload = {
            "Action": action,
            "Properties": default_properties,
            "Rows": rows
        }

        logger.info(
            f"Posting '{action}' action with {len(rows)} record(s) to AppSheet table '{target_table}'..."
        )

        try:
            response = self.session.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            # Handle AppSheet response (can be JSON or text)
            if response.text:
                try:
                    result = response.json()
                    logger.info(f"AppSheet API request successfully processed for action '{action}'.")
                    return result
                except ValueError:
                    logger.info(f"AppSheet returned non-JSON text response: {response.text}")
                    return {"raw_response": response.text, "status_code": response.status_code}

            return {"status": "success", "status_code": response.status_code}

        except requests.exceptions.HTTPError as e:
            msg = f"AppSheet API error HTTP {response.status_code} for table '{target_table}': {response.text}"
            logger.error(msg)
            raise AppSheetAPIError(msg, status_code=response.status_code, response_text=response.text) from e
        except requests.exceptions.RequestException as e:
            msg = f"Network failure communicating with AppSheet API: {e}"
            logger.error(msg)
            raise AppSheetClientError(msg) from e

    def add_rows(
        self,
        rows: List[Dict[str, Any]],
        table_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add new rows to AppSheet table.

        :param rows: List of row dictionaries
        :param table_name: Target table name
        :return: AppSheet API response
        """
        return self.post_action("Add", rows=rows, table_name=table_name)

    def upsert_rows(
        self,
        rows: List[Dict[str, Any]],
        table_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upsert (Add or Update) rows in AppSheet table.

        :param rows: List of row dictionaries
        :param table_name: Target table name
        :return: AppSheet API response
        """
        return self.post_action("Upsert", rows=rows, table_name=table_name)

    def edit_rows(
        self,
        rows: List[Dict[str, Any]],
        table_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update existing rows in AppSheet table.

        :param rows: List of row dictionaries
        :param table_name: Target table name
        :return: AppSheet API response
        """
        return self.post_action("Edit", rows=rows, table_name=table_name)
