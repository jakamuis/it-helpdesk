from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


DATASHEET_SCOPE_SELECTOR = "electronics_cpu_laptop_v1"
COMPUTER_SYNC_ASSET_TYPES: tuple[Literal["Computer"], ...] = ("Computer",)


class Settings(BaseSettings):
    GLPI_URL: str = Field(default="http://localhost:8080/apirest.php", description="GLPI API base URL")
    GLPI_APP_TOKEN: str = Field(default="", description="GLPI App Token")
    GLPI_USER_TOKEN: str = Field(default="", description="GLPI User Token")
    GLPI_ENTITY: int = Field(default=0, ge=0, description="GLPI Entity ID")
    GLPI_VERIFY_TLS: bool = Field(default=True, description="Verify the GLPI TLS certificate")
    API_KEY: str = Field(default="", description="API Key for this service")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    TIMEOUT: int = Field(default=10, description="HTTP Request timeout")
    DATABASE_URL: str = Field(default="sqlite:///./data/audit.db", description="Database connection URL")
    ASSET_SYNC_IMAGE_TAG: str = Field(
        default="1.1.0-local",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="Compose image tag (deployment metadata only)",
    )
    ASSET_SYNC_PLATFORM: Literal["linux/amd64"] = Field(
        default="linux/amd64",
        description="Release container platform matching the Ubuntu server",
    )
    ASSET_SYNC_BUILD_COMMIT: str = Field(
        default="unknown",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="OCI revision label passed by Docker Compose",
    )
    
    # Weekly Google Sheets sync schedule
    GOOGLE_CREDENTIALS_PATH: str = Field(default="./data/service_account.json", description="Path to Service Account JSON")
    SPREADSHEET_ID: str = Field(default="", description="Google Sheets ID")
    SHEET_NAME: str = Field(default="DATABASE INVENTARIS", description="Authoritative tab name in Google Sheets")
    SYNC_ASSET_TYPES: tuple[Literal["Computer"], ...] = Field(
        default=COMPUTER_SYNC_ASSET_TYPES,
        min_length=1,
        max_length=1,
        description="Fixed authoritative batch scope; only GLPI Computer is allowed",
    )
    SYNC_ENABLED: bool = Field(default=False, description="Enable the weekly background job")
    SYNC_DRY_RUN: bool = Field(default=True, description="Allow reads and audit only; never mutate GLPI")
    SYNC_FINANCE_ENABLED: bool = Field(
        default=False,
        description="Include validated DAT and Infocom fields in authoritative batch plans",
    )
    SYNC_ALLOW_CREATE: bool = Field(
        default=False,
        description="Allow approved sync runs to create previously unknown assets",
    )
    SYNC_ALLOW_INFOCOM_CREATE: bool = Field(
        default=False,
        description="Allow approved sync runs to create missing Infocom records",
    )
    SYNC_ALLOW_INFOCOM_UPDATE: bool = Field(
        default=False,
        description="Allow approved sync runs to update existing Infocom records",
    )
    SYNC_MAX_GLPI_MUTATIONS_PER_RUN: int = Field(
        default=0,
        ge=0,
        description="Maximum approved GLPI mutations per run; zero blocks all writes",
    )
    SYNC_APPROVED_MANIFEST_SHA256: str = Field(
        default="",
        pattern=r"^(?:[0-9a-fA-F]{64})?$",
        description="One-shot SHA-256 approval for the exact current batch manifest",
    )
    SYNC_MANIFEST_DIR: str = Field(
        default="./data/manifests",
        description="Private directory for batch manifests and one-shot claim markers",
    )
    SYNC_LOCK_DIR: str = Field(
        default="./data/locks",
        description="Private shared directory for global and per-QR OS mutation locks",
    )
    SYNC_DAY_OF_WEEK: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] = Field(
        default="sun",
        description="Weekly sync day",
    )
    SYNC_HOUR: int = Field(default=17, ge=0, le=23, description="Weekly sync hour")
    SYNC_MINUTE: int = Field(default=0, ge=0, le=59, description="Weekly sync minute")
    SYNC_TIMEZONE: str = Field(default="Asia/Jakarta", description="Weekly sync timezone")

    @field_validator("SYNC_ASSET_TYPES")
    @classmethod
    def normalize_asset_types(
        cls,
        value: tuple[Literal["Computer"], ...],
    ) -> tuple[Literal["Computer"], ...]:
        if value != COMPUTER_SYNC_ASSET_TYPES:
            raise ValueError("SYNC_ASSET_TYPES is fixed to exactly ['Computer']")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

settings = Settings()
