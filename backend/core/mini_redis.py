"""极简 Redis 客户端(RESP2 协议,纯标准库)

## 为什么需要它

当前开发机的出网被拦,pip 装不了官方 `redis` 包。为了不让缓存层变成死代码,
这里用标准库实现一个只覆盖**本项目实际用到的命令**的客户端:

    PING  GET  SET(含 NX/EX)  EXPIRE  INCRBY  MGET  DEL

配套一个轻量连接池。

## 定位

这是**回退实现**。一旦能装上官方包,`core/redis_client.py` 会自动优先用
`redis-py`(它更成熟、支持集群/哨兵/异步)。两者对外暴露的方法签名一致,
所以上层 `cache.py` 完全不用改。

不支持:集群、哨兵、pub/sub、Lua、异步。项目目前都用不到。
"""
from __future__ import annotations

import logging
import socket
import threading
from typing import Any, Iterable, Optional

log = logging.getLogger("redis.mini")

_CRLF = b"\r\n"


def _encode_command(args: Iterable[Any]) -> bytes:
    items = list(args)
    out = [b"*" + str(len(items)).encode()]
    for a in items:
        if isinstance(a, bytes):
            data = a
        elif isinstance(a, str):
            data = a.encode("utf-8")
        elif a is None:
            data = b""
        else:
            data = str(a).encode("utf-8")
        out.append(b"$" + str(len(data)).encode())
        out.append(data)
    return _CRLF.join(out) + _CRLF


def _read_line(f) -> bytes:
    line = f.readline()
    if not line:
        raise ConnectionError("Redis connection closed")
    return line.rstrip(b"\r\n")


def _read_reply(f) -> Any:
    line = _read_line(f)
    if not line:
        raise ConnectionError("empty reply")
    prefix, rest = line[:1], line[1:]
    if prefix == b"+":
        return rest.decode("utf-8", "replace")
    if prefix == b"-":
        raise RuntimeError("Redis error: " + rest.decode("utf-8", "replace"))
    if prefix == b":":
        return int(rest)
    if prefix == b"$":
        n = int(rest)
        if n == -1:
            return None
        data = f.read(n + 2)
        return data[:-2].decode("utf-8", "replace")
    if prefix == b"*":
        n = int(rest)
        if n == -1:
            return None
        return [_read_reply(f) for _ in range(n)]
    raise RuntimeError(f"unexpected reply prefix: {line[:40]!r}")


class _Connection:
    __slots__ = ("_sock", "_f", "_closed")

    def __init__(self, host: str, port: int, timeout: float):
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._f = self._sock.makefile("rb")
        self._closed = False

    def send(self, args: list) -> None:
        self._sock.sendall(_encode_command(args))

    def read(self) -> Any:
        return _read_reply(self._f)

    def execute(self, args: list) -> Any:
        self.send(args)
        return self.read()

    def alive(self) -> bool:
        try:
            return self.execute(["PING"]) == "PONG"
        except Exception:
            return False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for closer in (self._f.close, self._sock.close):
            try:
                closer()
            except Exception:
                pass


class _Pipeline:
    """只是把命令攒起来,execute() 时一次性写、一次性读"""

    def __init__(self, client: "MiniRedis"):
        self._client = client
        self._cmds: list[list] = []

    def set(self, key: str, value: Any, nx: bool = False, ex: Optional[int] = None):
        cmd = ["SET", key, value]
        if nx:
            cmd.append("NX")
        if ex:
            cmd.extend(["EX", int(ex)])
        self._cmds.append(cmd)
        return self

    def expire(self, key: str, ttl: int):
        self._cmds.append(["EXPIRE", key, int(ttl)])
        return self

    def incrby(self, key: str, amount: int = 1):
        self._cmds.append(["INCRBY", key, int(amount)])
        return self

    def delete(self, *keys: str):
        self._cmds.append(["DEL", *keys])
        return self

    def get(self, key: str):
        self._cmds.append(["GET", key])
        return self

    def execute(self) -> list:
        if not self._cmds:
            return []
        with self._client._borrow() as conn:
            for cmd in self._cmds:
                conn.send(cmd)
            return [conn.read() for _ in self._cmds]


class _Borrowed:
    def __init__(self, client: "MiniRedis"):
        self._client = client
        self._conn: Optional[_Connection] = None

    def __enter__(self) -> _Connection:
        self._conn = self._client._acquire()
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        if self._conn is not None:
            # 出错时连接状态不可信,直接丢弃;正常则归还
            if exc_type is None:
                self._client._release(self._conn)
            else:
                self._client._discard(self._conn)
            self._conn = None
        return False


class MiniRedis:
    """方法签名对齐 redis-py 的常用子集"""

    def __init__(self, host="127.0.0.1", port=6379, db=0, password=None,
                 socket_timeout=0.2, socket_connect_timeout=0.2, max_connections=32, **_ignored):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.timeout = socket_timeout
        self.connect_timeout = socket_connect_timeout
        self.max_connections = max_connections
        self._idle: list[_Connection] = []
        self._lock = threading.Lock()
        self._created = 0
        self._closed = False

    # ---- 连接池 ----
    def _new_conn(self) -> _Connection:
        conn = _Connection(self.host, self.port, self.connect_timeout)
        if self.password:
            conn.execute(["AUTH", self.password])
        if self.db:
            conn.execute(["SELECT", int(self.db)])
        conn._sock.settimeout(self.timeout)
        return conn

    def _acquire(self) -> _Connection:
        if self._closed:
            raise ConnectionError("MiniRedis closed")
        while True:
            with self._lock:
                if self._idle:
                    self._wait_since = None
                    return self._idle.pop()
                if self._created < self.max_connections:
                    self._created += 1
                    create = True
                else:
                    create = False
            if create:
                try:
                    return self._new_conn()
                except Exception:
                    with self._lock:
                        self._created -= 1
                    raise
            # 池满:短暂等待,超过总超时就放弃
            import time as _t
            waited = getattr(self, "_wait_since", None)
            now = _t.monotonic()
            if waited is None:
                self._wait_since = now
            elif now - waited > max(self.timeout * 4, 0.5):
                self._wait_since = None
                raise TimeoutError(f"MiniRedis pool exhausted (max={self.max_connections})")
            _t.sleep(0.002)

    def _release(self, conn: _Connection) -> None:
        if self._closed:
            conn.close()
            return
        with self._lock:
            if len(self._idle) < self.max_connections:
                self._idle.append(conn)
                return
        conn.close()
        with self._lock:
            self._created -= 1

    def _discard(self, conn: _Connection) -> None:
        conn.close()
        with self._lock:
            self._created -= 1

    def _borrow(self) -> _Borrowed:
        return _Borrowed(self)

    # ---- 命令 ----
    def execute(self, args: list) -> Any:
        with self._borrow() as conn:
            return conn.execute(args)

    def ping(self) -> bool:
        return self.execute(["PING"]) == "PONG"

    def get(self, key: str):
        return self.execute(["GET", key])

    def set(self, key: str, value: Any, nx: bool = False, ex: Optional[int] = None):
        cmd = ["SET", key, value]
        if nx:
            cmd.append("NX")
        if ex:
            cmd.extend(["EX", int(ex)])
        return self.execute(cmd)

    def setex(self, key: str, ttl: int, value: Any):
        return self.execute(["SETEX", key, int(ttl), value])

    def expire(self, key: str, ttl: int) -> int:
        return self.execute(["EXPIRE", key, int(ttl)])

    def incrby(self, key: str, amount: int = 1) -> int:
        return self.execute(["INCRBY", key, int(amount)])

    def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        return self.execute(["DEL", *keys])

    def mget(self, keys: list[str]) -> list:
        if not keys:
            return []
        return self.execute(["MGET", *keys])

    def pipeline(self, transaction: bool = False) -> _Pipeline:
        return _Pipeline(self)

    def close(self) -> None:
        self._closed = True
        with self._lock:
            idle, self._idle = self._idle, []
            self._created = 0
        for c in idle:
            c.close()

    def disconnect(self) -> None:
        self.close()
