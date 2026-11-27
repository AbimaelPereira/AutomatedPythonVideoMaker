from functools import cached_property
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Lê `api/.env`. Variáveis de ambiente têm prioridade sobre o arquivo."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASS: str
    MYSQL_DBNAME: str

    ENVIRONMENT: str = "development"

    @cached_property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{quote_plus(self.MYSQL_USER)}:{quote_plus(self.MYSQL_PASS)}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DBNAME}?charset=utf8mb4"
        )


settings = Settings()
