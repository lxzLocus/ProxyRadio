"""radiko HLS Proxy - FastAPI メインアプリケーション"""

import logging
from contextlib import asynccontextmanager
from urllib.parse import unquote

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from . import config
from .auth import radiko_auth
from .programs import get_now_programs
from .proxy import get_playlist, proxy_segment
from .stations import clear_cache as clear_stations_cache
from .stations import get_stations

# ─── ログ設定 ─────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Lifespan ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリ起動時に認証、終了時にクリーンアップ"""
    logger.info("radiko HLS Proxy を起動中... (port=%d)", config.PORT)
    try:
        # 起動時に認証を実行
        token = await radiko_auth.get_token()
        status = await radiko_auth.get_auth_status()
        logger.info(
            "起動時認証完了: area=%s (%s)",
            status["area_id"],
            status["area_name"],
        )
    except Exception as e:
        logger.warning("起動時認証に失敗 (後でリトライします): %s", e)

    yield

    # クリーンアップ
    await radiko_auth.close()
    logger.info("radiko HLS Proxy を終了しました")


# ─── FastAPI App ──────────────────────────────────────
app = FastAPI(
    title="radiko HLS Proxy",
    description="関西エリアの radiko ライブ配信を HLS プロキシで中継するバックエンド",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 設定 (将来の Frontend 用)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番運用時はドメインを限定
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health Check ─────────────────────────────────────
@app.get("/health")
async def health_check():
    """ヘルスチェック"""
    return {"status": "ok", "service": "radiko-hls-proxy"}


# ─── Frontend Config ─────────────────────────────────
@app.get("/api/config")
async def frontend_config():
    """フロントエンド用の設定を返す（BACKEND_URL 等）"""
    return {
        "backend_url": config.BACKEND_URL,
    }


# ─── Auth Status ──────────────────────────────────────
@app.get("/api/auth/status")
async def auth_status():
    """認証状態を返す"""
    return await radiko_auth.get_auth_status()


@app.post("/api/auth/refresh")
async def auth_refresh():
    """認証トークンを強制的に再取得"""
    try:
        radiko_auth._cached = type(radiko_auth._cached)()  # キャッシュクリア
        token = await radiko_auth.get_token()
        return await radiko_auth.get_auth_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"認証失敗: {e}")


# ─── Stations ─────────────────────────────────────────
@app.get("/api/stations")
async def list_stations():
    """エリア内の放送局一覧を返す"""
    try:
        return await get_stations()
    except Exception as e:
        logger.error("放送局一覧取得失敗: %s", e)
        raise HTTPException(status_code=500, detail=f"放送局一覧の取得に失敗しました: {e}")


# ─── Now Playing Programs ─────────────────────────────
@app.get("/api/programs")
async def now_programs():
    """現在放送中の番組情報を返す（番組名・サムネイル・出演者）"""
    try:
        programs = await get_now_programs()
        return {"programs": programs}
    except Exception as e:
        logger.error("番組情報取得失敗: %s", e)
        raise HTTPException(status_code=500, detail=f"番組情報の取得に失敗しました: {e}")


# ─── HLS Stream ──────────────────────────────────────
@app.get("/api/stream/{station_id}")
async def stream_playlist(station_id: str, request: Request):
    """HLS playlist を取得（セグメントURLは書き換え済み）

    クライアントはこの playlist を HLS プレイヤーで読み込むだけで再生可能。
    """
    try:
        # ベースURLを構築（プロキシ経由を考慮）
        base_url = _get_base_url(request)

        playlist_text, content_type = await get_playlist(station_id, base_url)
        return PlainTextResponse(
            content=playlist_text,
            media_type=content_type,
        )
    except httpx.HTTPStatusError as e:
        logger.error("playlist 取得失敗 (station=%s): %s", station_id, e)
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"radiko からの playlist 取得に失敗しました: {e}",
        )
    except Exception as e:
        logger.error("playlist 取得失敗 (station=%s): %s", station_id, e)
        raise HTTPException(status_code=500, detail=f"playlist 取得エラー: {e}")


# ─── Segment Proxy ────────────────────────────────────
@app.get("/api/proxy/segment")
async def segment_proxy(url: str = Query(..., description="元のセグメントURL")):
    """AAC セグメントを radiko から取得してプロキシする

    playlist 内のセグメントURL はすべてこのエンドポイント経由に書き換えられる。
    クライアント側で radiko の認証トークンを持つ必要がない。
    """
    decoded_url = unquote(url)

    # セキュリティ: radiko 関連ドメインのみ許可
    allowed_domains = [
        "radiko.jp",
        "smartstream.ne.jp",
        "radiko.smartstream.ne.jp",
    ]
    if not any(domain in decoded_url for domain in allowed_domains):
        raise HTTPException(
            status_code=403,
            detail="許可されていないドメインです",
        )

    try:
        data, content_type = await proxy_segment(decoded_url)
        return Response(
            content=data,
            media_type=content_type,
            headers={
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": "*",
            },
        )
    except httpx.HTTPStatusError as e:
        logger.error("セグメント取得失敗: %s", e)
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"セグメント取得に失敗しました",
        )
    except Exception as e:
        logger.error("セグメント取得失敗: %s", e)
        raise HTTPException(status_code=500, detail=f"セグメント取得エラー: {e}")


# ─── Helpers ──────────────────────────────────────────
def _get_base_url(request: Request) -> str:
    """リクエストからベースURLを構築

    リバースプロキシ経由の場合は X-Forwarded-* ヘッダーを考慮
    """
    # X-Forwarded-Proto / X-Forwarded-Host があればそれを使用
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost"))
    return f"{proto}://{host}"



# ─── CLI エントリポイント ──────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=config.PORT,
        log_level=config.LOG_LEVEL,
        reload=True,
    )
