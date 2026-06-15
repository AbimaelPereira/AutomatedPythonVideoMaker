from pydantic_settings import BaseSettings
from pydantic import computed_field
from urllib.parse import quote_plus


class Settings(BaseSettings):
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASS: str
    MYSQL_DBNAME: str

    JWT_SECRET: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    FRONTEND_URL: str = "http://localhost:5173"
    ENVIRONMENT: str = "development"

    # Token de serviço para chamadas internas (ex: videomaker -> API de remote assets)
    SERVICE_TOKEN: str = "dev-service-token"

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{quote_plus(self.MYSQL_USER)}:{quote_plus(self.MYSQL_PASS)}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DBNAME}"

    class Config:
        env_file = ".env"


settings = Settings()
