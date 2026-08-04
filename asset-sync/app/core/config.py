from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    GLPI_URL: str = Field(default="http://localhost:8080/apirest.php", description="GLPI API base URL")
    GLPI_APP_TOKEN: str = Field(default="", description="GLPI App Token")
    GLPI_USER_TOKEN: str = Field(default="", description="GLPI User Token")
    GLPI_ENTITY: str = Field(default="0", description="GLPI Entity ID")
    API_KEY: str = Field(default="test_api_key", description="API Key for this service")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    TIMEOUT: int = Field(default=10, description="HTTP Request timeout")
    DATABASE_URL: str = Field(default="sqlite:///./data/audit.db", description="Database connection URL")
    
    # Sheets Polling Settings
    GOOGLE_CREDENTIALS_PATH: str = Field(default="./data/service_account.json", description="Path to Service Account JSON")
    SPREADSHEET_ID: str = Field(default="", description="Google Sheets ID")
    SHEET_NAME: str = Field(default="Assets", description="Tab name in Google Sheets")
    SYNC_INTERVAL_MINUTES: int = Field(default=5, description="Polling interval in minutes")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
