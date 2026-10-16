"""用户表。对应 docs/03-data-model.md §1。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    platform_user_id: Mapped[int | None] = mapped_column(Integer)
    platform_cookies: Mapped[str | None] = mapped_column(Text)
    cookies_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    ve_user_id: Mapped[int | None] = mapped_column(Integer)