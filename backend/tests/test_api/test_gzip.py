"""API 响应压缩（docs/11 流量优化 F2）的回归测试。

用裸 ASGI 调用验证压缩语义，不经过 TestClient：这里只关心 middleware 与
response 头，不需要完整应用生命周期。
"""
from __future__ import annotations

import gzip
import json

from fastapi.middleware.gzip import GZipMiddleware

from app.main import app

BIG_BODY = json.dumps({"sentences": [f"第 {i} 句课程转写内容" for i in range(200)]}).encode("utf-8")


class _EchoApp:
    """最小 ASGI 应用：固定返回一个 >1KB 的响应。"""

    def __init__(self, content_type: str = "application/json"):
        self.content_type = content_type

    async def __call__(self, scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", self.content_type.encode())],
        })
        await send({"type": "http.response.body", "body": BIG_BODY})


async def _request(asgi_app, path: str, headers: list[tuple[str, str]] | None = None):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or [])],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await asgi_app(scope, receive, send)
    return messages


def _headers_of(messages: list[dict]) -> dict[bytes, bytes]:
    start = next(m for m in messages if m["type"] == "http.response.start")
    return dict(start["headers"])


def _body_of(messages: list[dict]) -> bytes:
    return b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")


def test_gzip_middleware_is_registered_with_1kb_threshold():
    gzip_layers = [m for m in app.user_middleware if m.cls is GZipMiddleware]
    assert gzip_layers, "main.py 应注册 GZipMiddleware，否则 docs/11 F2 的收益不存在"
    assert gzip_layers[0].kwargs["minimum_size"] == 1024


async def test_large_json_response_is_gzipped():
    asgi_app = GZipMiddleware(_EchoApp(), minimum_size=1024)
    messages = await _request(
        asgi_app, "/api/v1/courses/1/transcripts", [("accept-encoding", "gzip")]
    )

    assert _headers_of(messages).get(b"content-encoding") == b"gzip"
    assert gzip.decompress(_body_of(messages)) == BIG_BODY


async def test_small_response_is_not_gzipped():
    class _Small(_EchoApp):
        async def __call__(self, scope, receive, send):
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"ok":true}'})

    asgi_app = GZipMiddleware(_Small(), minimum_size=1024)
    messages = await _request(asgi_app, "/api/v1/health", [("accept-encoding", "gzip")])

    assert b"content-encoding" not in _headers_of(messages)
    assert _body_of(messages) == b'{"ok":true}'


async def test_event_stream_is_never_gzipped():
    """docs/11 优化 4 要上 SSE：事件流一旦被压缩缓冲，前端会收不到消息。"""
    asgi_app = GZipMiddleware(_EchoApp(content_type="text/event-stream"), minimum_size=1024)
    messages = await _request(asgi_app, "/api/v1/tasks/7/stream", [("accept-encoding", "gzip")])

    assert b"content-encoding" not in _headers_of(messages)
    assert _body_of(messages) == BIG_BODY


async def test_client_without_gzip_support_gets_plain_body():
    asgi_app = GZipMiddleware(_EchoApp(), minimum_size=1024)
    messages = await _request(asgi_app, "/api/v1/courses/1/transcripts")

    assert b"content-encoding" not in _headers_of(messages)
    assert _body_of(messages) == BIG_BODY
