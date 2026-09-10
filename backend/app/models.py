import os

from sqlmodel import Field, Session, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    role: str = Field(default="user")  # "admin" | "user"
    is_active: bool = Field(default=True)


class Runtime(SQLModel, table=True):
    __tablename__ = "runtimes"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    container_name: str = Field(unique=True)
    opencode_password: str  # per-user OPENCODE_SERVER_PASSWORD
    status: str = Field(default="provisioning")  # provisioning | running | idle | stopped | error
    created_at: str
    container_ip: str | None = Field(default=None)  # bridge IP for direct reachability (bind 0.0.0.0)


class UsageRecord(SQLModel, table=True):
    __tablename__ = "usage_records"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int | None
    created_at: str


class AppDB(SQLModel, table=True):
    __tablename__ = "app_db"

    id: int | None = Field(default=None, primary_key=True)
    db_path: str = Field(default=os.getenv("SRGE_DB", "srge.db"))
