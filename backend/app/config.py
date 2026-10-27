from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Read from environment variables (and backend/.env locally)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "JSAN Places"
    environment: str = "development"
    # Railway Postgres exposes DATABASE_URL; unset means the app runs without a database.
    database_url: str | None = None
    # Comma-separated origins, only needed when the frontend is hosted on another domain.
    cors_origins: str = ""
    # Built React app served at "/". The Docker image sets this to /app/frontend/dist.
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    # Set by Railway for each deploy.
    railway_git_commit_sha: str | None = None
    google_places_api_key: SecretStr | None = None
    google_translate_api_key: SecretStr | None = None  # optional; else the Places key, if Cloud Translation is enabled on it
    grab_api_key: SecretStr | None = None
    grab_place_index: str = ""
    grab_region: str = "ap-southeast-1"
    apple_maps_access_token: SecretStr | None = None
    # Shown in delivery file names and the manifest ([Supplier]_[Country]_[AOI]_[Action]_[YYYYMMDD]_v[x].xlsx).
    supplier_name: str = "JSAN"
    supplier_contact: str = ""

    @property
    def sqlalchemy_url(self) -> str | None:
        """Railway gives postgres://… or postgresql://…; SQLAlchemy needs the psycopg 3 driver named."""
        url = self.database_url
        if not url:
            return None
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def version(self) -> str:
        return (self.railway_git_commit_sha or "dev")[:7]


@lru_cache
def get_settings() -> Settings:
    return Settings()
