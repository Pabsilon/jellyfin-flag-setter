from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    hashed_password: str


class ServerConfig(SQLModel, table=True):
    __tablename__ = "server_config"
    id: int | None = Field(default=None, primary_key=True)
    jellyfin_url: str
    jellyfin_api_key: str
