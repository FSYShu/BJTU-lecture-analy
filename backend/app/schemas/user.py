"""用户相关 schema。"""
from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    display_name: str | None = None

    class Config:
        from_attributes = True


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut