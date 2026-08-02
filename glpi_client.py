"""
GLPI REST API Client Module.

Handles authentication (initSession, killSession), token management, and fetching tickets/assets
from GLPI REST API with robust error handling and retry logic.
"""

import logging
import requests
from typing import Dict, Any, List, Optional, Union
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class GLPIClientError(Exception):
    """Base exception for GLPI client errors."""
    pass


class GLPIAuthenticationError(GLPIClientError):
    """Raised when GLPI authentication fails."""
    pass


class GLPIAPIError(GLPIClientError):
    """Raised when a GLPI API request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class GLPIClient:
    """
    Client for interacting with GLPI REST API.

    Supports context manager interface:
    >>> with GLPIClient(url, app_token, user_token) as client:
    >>>     tickets = client.get_tickets()
    """

    def __init__(
        self,
        base_url: str,
        app_token: str,
        user_token: str,
        timeout: int = 15,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        verify_ssl: bool = True
    ):
        """
        Initialize the GLPI REST API client.

        :param base_url: Base URL of GLPI REST API (e.g., https://glpi.domain.com/apirest.php)
        :param app_token: GLPI API App-Token
        :param user_token: GLPI API user_token
        :param timeout: Request timeout in seconds
        :param max_retries: Number of retries for transient HTTP errors
        :param backoff_factor: Backoff factor for retry delay calculation
        :param verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url.rstrip("/")
        self.app_token = app_token
        self.user_token = user_token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.session_token: Optional[str] = None

        # Setup requests Session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def init_session(self) -> str:
        """
        Authenticate with GLPI REST API (GET /initSession).

        Sets up the session_token for subsequent API requests.
        :return: GLPI session token
        """
        endpoint = f"{self.base_url}/initSession"
        headers = {
            "Content-Type": "application/json",
            "App-Token": self.app_token,
            "Authorization": f"user_token {self.user_token}"
        }

        logger.info("Initializing GLPI API session...")
        try:
            response = self.session.get(
                endpoint,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            response.raise_for_status()
            data = response.json()

            if "session_token" not in data:
                raise GLPIAuthenticationError(
                    f"Invalid response from GLPI initSession, missing session_token: {data}"
                )

            self.session_token = data["session_token"]
            logger.info("GLPI session initialized successfully.")
            return self.session_token

        except requests.exceptions.HTTPError as e:
            msg = f"GLPI authentication failed HTTP {response.status_code}: {response.text}"
            logger.error(msg)
            raise GLPIAuthenticationError(msg) from e
        except requests.exceptions.RequestException as e:
            msg = f"Network or connection error during GLPI initSession: {e}"
            logger.error(msg)
            raise GLPIClientError(msg) from e
        except Exception as e:
            msg = f"Unexpected error during GLPI initSession: {e}"
            logger.error(msg)
            raise GLPIClientError(msg) from e

    def kill_session(self) -> bool:
        """
        Close the GLPI REST API session (GET /killSession).

        :return: True if successfully closed, False otherwise
        """
        if not self.session_token:
            logger.debug("No active GLPI session token to destroy.")
            return True

        endpoint = f"{self.base_url}/killSession"
        headers = self._get_request_headers()

        logger.info("Closing GLPI API session...")
        try:
            response = self.session.get(
                endpoint,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            response.raise_for_status()
            logger.info("GLPI session closed successfully.")
            self.session_token = None
            return True
        except Exception as e:
            logger.warning(f"Error while destroying GLPI session: {e}")
            self.session_token = None
            return False

    def _get_request_headers(self) -> Dict[str, str]:
        """Generate headers for authenticated requests after initSession."""
        if not self.session_token:
            raise GLPIClientError("Session not initialized. Call init_session() first.")

        return {
            "Content-Type": "application/json",
            "App-Token": self.app_token,
            "Session-Token": self.session_token
        }

    def fetch_items(
        self,
        itemtype: str,
        params: Optional[Dict[str, Any]] = None,
        range_str: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generic method to retrieve items/assets from GLPI API.

        :param itemtype: Resource type name (e.g. 'Ticket', 'Computer', 'Monitor', 'Printer')
        :param params: Optional query parameters (e.g. expand_dropdowns=true)
        :param range_str: Optional pagination range (e.g. '0-100')
        :return: List of item dictionaries
        """
        if not self.session_token:
            self.init_session()

        endpoint = f"{self.base_url}/{itemtype}"
        headers = self._get_request_headers()

        query_params = {
            "expand_dropdowns": "true",
            "get_full_schema": "false"
        }
        if params:
            query_params.update(params)

        if range_str:
            query_params["range"] = range_str

        logger.info(f"Fetching {itemtype} items from GLPI (params={query_params})...")
        try:
            response = self.session.get(
                endpoint,
                headers=headers,
                params=query_params,
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            response.raise_for_status()

            data = response.json()
            if isinstance(data, list):
                logger.info(f"Successfully retrieved {len(data)} {itemtype} record(s).")
                return data
            elif isinstance(data, dict):
                # Some endpoints return dict if single object or schema response
                return [data]
            else:
                logger.warning(f"Unexpected data format received for {itemtype}: {type(data)}")
                return []

        except requests.exceptions.HTTPError as e:
            msg = f"Failed to fetch GLPI {itemtype}: HTTP {response.status_code} - {response.text}"
            logger.error(msg)
            raise GLPIAPIError(msg, status_code=response.status_code, response_text=response.text) from e
        except requests.exceptions.RequestException as e:
            msg = f"Network error while fetching GLPI {itemtype}: {e}"
            logger.error(msg)
            raise GLPIClientError(msg) from e

    def get_tickets(
        self,
        limit: int = 100,
        sort: str = "id",
        order: str = "DESC",
        additional_params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch tickets from GLPI REST API.

        :param limit: Maximum number of records to return
        :param sort: Field name to sort by
        :param order: 'ASC' or 'DESC'
        :param additional_params: Additional query parameters
        :param range: Custom range string (e.g., '0-50')
        :return: List of ticket dictionaries
        """
        params = {
            "sort": sort,
            "order": order
        }
        if additional_params:
            params.update(additional_params)

        range_str = f"0-{limit}" if limit > 0 else None
        return self.fetch_items("Ticket", params=params, range_str=range_str)

    def get_assets(
        self,
        itemtype: str = "Computer",
        limit: int = 100,
        additional_params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch assets (Computers, Monitors, Devices, etc.) from GLPI REST API.

        :param itemtype: GLPI Asset Item Type (default: 'Computer')
        :param limit: Maximum number of records to return
        :param additional_params: Additional query parameters
        :return: List of asset dictionaries
        """
        range_str = f"0-{limit}" if limit > 0 else None
        return self.fetch_items(itemtype, params=additional_params, range_str=range_str)

    def __enter__(self):
        """Context manager entry point."""
        self.init_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point - ensures session kill."""
        self.kill_session()
