"""radiko HLS Proxy - 認証モジュール

radiko の auth1 → PartialKey 生成 → auth2 フローを実装し、
認証トークンをキャッシュ・自動更新する。
"""

import base64
import logging
import time
from dataclasses import dataclass, field

import httpx

from . import config

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    """認証結果を保持する"""

    token: str = ""
    area_id: str = ""
    area_name: str = ""
    authenticated_at: float = 0.0

    @property
    def is_valid(self) -> bool:
        """トークンがキャッシュ有効期間内か"""
        if not self.token:
            return False
        elapsed = time.time() - self.authenticated_at
        return elapsed < config.TOKEN_CACHE_TTL


class RadikoAuth:
    """radiko 認証を管理するクラス

    Usage:
        auth = RadikoAuth()
        token = await auth.get_token()  # 自動で認証 & キャッシュ
    """

    def __init__(self) -> None:
        self._cached: AuthResult = AuthResult()
        self._http: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP クライアントを遅延初期化"""
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                follow_redirects=True,
            )
        return self._http

    async def close(self) -> None:
        """HTTP クライアントを閉じる"""
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ─── Public API ───────────────────────────────────

    async def get_token(self) -> str:
        """有効な認証トークンを返す（キャッシュ済みならそのまま、期限切れなら再取得）"""
        if self._cached.is_valid:
            return self._cached.token

        logger.info("radiko トークンを取得中...")
        result = await self._authorize()
        self._cached = result
        logger.info(
            "認証成功: area=%s (%s), token=%s...",
            result.area_id,
            result.area_name,
            result.token[:8],
        )
        return result.token

    async def get_auth_status(self) -> dict:
        """現在の認証状態を返す"""
        return {
            "authenticated": self._cached.is_valid,
            "area_id": self._cached.area_id,
            "area_name": self._cached.area_name,
            "token_prefix": self._cached.token[:8] + "..." if self._cached.token else "",
            "authenticated_at": self._cached.authenticated_at,
            "ttl_remaining": max(
                0,
                config.TOKEN_CACHE_TTL - (time.time() - self._cached.authenticated_at),
            )
            if self._cached.token
            else 0,
        }

    # ─── Internal ─────────────────────────────────────

    async def _authorize(self) -> AuthResult:
        """auth1 → PartialKey 生成 → auth2 の一連のフローを実行"""
        client = await self._get_client()

        # ── Step 1: auth1 ──
        auth1_headers = {
            "X-Radiko-App": config.RADIKO_APP,
            "X-Radiko-App-Version": config.RADIKO_APP_VERSION,
            "X-Radiko-User": config.RADIKO_USER,
            "X-Radiko-Device": config.RADIKO_DEVICE,
        }

        logger.debug("auth1 リクエスト: %s", config.RADIKO_AUTH1_URL)
        resp1 = await client.get(config.RADIKO_AUTH1_URL, headers=auth1_headers)
        resp1.raise_for_status()

        token = resp1.headers.get("x-radiko-authtoken", "")
        key_offset = int(resp1.headers.get("x-radiko-keyoffset", "0"))
        key_length = int(resp1.headers.get("x-radiko-keylength", "0"))

        if not token:
            raise RuntimeError("auth1: X-Radiko-AuthToken が取得できませんでした")

        logger.debug(
            "auth1 成功: token=%s..., offset=%d, length=%d",
            token[:8],
            key_offset,
            key_length,
        )

        # ── Step 2: PartialKey 生成 ──
        partial_key = self._generate_partial_key(key_offset, key_length)
        logger.debug("PartialKey 生成: %s...", partial_key[:8])

        # ── Step 3: auth2 ──
        auth2_headers = {
            "X-Radiko-App": config.RADIKO_APP,
            "X-Radiko-App-Version": config.RADIKO_APP_VERSION,
            "X-Radiko-User": config.RADIKO_USER,
            "X-Radiko-Device": config.RADIKO_DEVICE,
            "X-Radiko-AuthToken": token,
            "X-Radiko-PartialKey": partial_key,
        }

        logger.debug("auth2 リクエスト: %s", config.RADIKO_AUTH2_URL)
        resp2 = await client.get(config.RADIKO_AUTH2_URL, headers=auth2_headers)
        resp2.raise_for_status()

        # auth2 レスポンス: "JP27,大阪,osaka" のようなカンマ区切り
        body = resp2.text.strip()
        parts = body.split(",")
        area_id = parts[0].strip() if len(parts) > 0 else ""
        area_name = parts[1].strip() if len(parts) > 1 else ""

        if not area_id:
            raise RuntimeError(f"auth2: エリアID が取得できませんでした (response={body})")

        return AuthResult(
            token=token,
            area_id=area_id,
            area_name=area_name,
            authenticated_at=time.time(),
        )

    @staticmethod
    def _generate_partial_key(offset: int, length: int) -> str:
        """認証キーから指定オフセット・長さでバイナリを切り出し、Base64 エンコードする"""
        auth_key_bytes = config.RADIKO_AUTH_KEY.encode("ascii")
        partial = auth_key_bytes[offset : offset + length]
        return base64.b64encode(partial).decode("ascii")


# ─── シングルトンインスタンス ─────────────────────────
radiko_auth = RadikoAuth()
