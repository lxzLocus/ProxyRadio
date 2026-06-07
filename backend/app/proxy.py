"""radiko HLS Proxy - HLS プロキシモジュール

radiko の HLS playlist / AAC セグメントを取得し、
playlist 内 URL をバックエンド経由に書き換えてクライアントへ返す。
"""

import logging
import re
import secrets
from urllib.parse import quote, urljoin
from xml.etree import ElementTree

import httpx

from . import config
from .auth import radiko_auth

logger = logging.getLogger(__name__)


def _generate_lsid() -> str:
    """radiko が要求する lsid (32桁の16進数文字列) を生成"""
    return secrets.token_hex(16)


async def get_stream_url(station_id: str) -> str:
    """放送局IDからストリーム(playlist)のURLを取得する

    radiko の /v2/station/stream_smh_multi/{station_id}.xml から
    HLS playlist URL を抽出する。
    """
    url = config.RADIKO_STREAM_URL.format(station_id=station_id)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    root = ElementTree.fromstring(resp.text)

    # XML 内の <url> → <playlist_create_url> を探す
    # areafree="0" のものを優先（通常配信）
    for item in root.findall(".//url"):
        areafree = item.get("areafree", "0")
        if areafree == "0":
            playlist_elem = item.find("playlist_create_url")
            if playlist_elem is not None and playlist_elem.text:
                return playlist_elem.text.strip()

    # areafree="0" が見つからなければ最初のものを使う
    for item in root.findall(".//url"):
        playlist_elem = item.find("playlist_create_url")
        if playlist_elem is not None and playlist_elem.text:
            return playlist_elem.text.strip()

    raise RuntimeError(f"ストリームURL が見つかりません: station={station_id}")


async def get_playlist(station_id: str, base_url: str) -> tuple[str, str]:
    """HLS playlist を取得し、セグメントURLをバックエンド経由に書き換える

    Args:
        station_id: 放送局ID (例: "ABC")
        base_url: バックエンドのベースURL (例: "http://localhost:8080")

    Returns:
        (書き換え済み playlist テキスト, content-type)
    """
    token = await radiko_auth.get_token()
    lsid = _generate_lsid()

    # Step 1: ストリームの master playlist URL を取得
    stream_url = await get_stream_url(station_id)
    logger.debug("ストリームURL: %s", stream_url)

    # lsid パラメータを追加（既存のパラメータと重複しないよう注意）
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    parsed = urlparse(stream_url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    # 必要なパラメータを設定（既存値を上書き）
    params["station_id"] = [station_id]
    params["l"] = ["15"]
    params["lsid"] = [lsid]
    params["type"] = ["b"]

    new_query = urlencode({k: v[0] for k, v in params.items()})
    master_url = urlunparse(parsed._replace(query=new_query))

    # Step 2: master playlist を取得
    headers = {
        "X-Radiko-AuthToken": token,
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(master_url, headers=headers)
        resp.raise_for_status()
        master_content = resp.text
        master_base_url = str(resp.url)  # リダイレクト後の実URLをベースに

    logger.debug("Master playlist 取得: %d bytes", len(master_content))

    # Step 3: master playlist 内のメディア playlist URL を取得
    # master playlist にはビットレート別の playlist URL が含まれる
    media_urls = _extract_urls(master_content, master_base_url)

    if not media_urls:
        # master playlist 自体がメディア playlist の場合
        rewritten = _rewrite_segment_urls(master_content, master_base_url, base_url)
        return rewritten, "application/x-mpegURL"

    # 最初の（最高品質の）media playlist を取得
    media_url = media_urls[0]
    logger.debug("Media playlist URL: %s", media_url)

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(media_url, headers=headers)
        resp.raise_for_status()
        media_content = resp.text
        media_base_url = str(resp.url)

    logger.debug("Media playlist 取得: %d bytes", len(media_content))

    # Step 4: セグメントURLを書き換え
    rewritten = _rewrite_segment_urls(media_content, media_base_url, base_url)
    return rewritten, "application/x-mpegURL"


async def proxy_segment(segment_url: str) -> tuple[bytes, str]:
    """AAC セグメントを radiko から取得し返す

    Args:
        segment_url: 元のセグメント URL

    Returns:
        (セグメントバイナリデータ, content-type)
    """
    token = await radiko_auth.get_token()
    headers = {
        "X-Radiko-AuthToken": token,
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(segment_url, headers=headers)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "audio/aac")
        return resp.content, content_type


def _extract_urls(playlist: str, base_url: str) -> list[str]:
    """playlist テキストからURLを抽出（コメント行以外の行）"""
    urls = []
    for line in playlist.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 相対URLを絶対URLに変換
        if not line.startswith("http"):
            line = urljoin(base_url, line)
        urls.append(line)
    return urls


def _rewrite_segment_urls(playlist: str, playlist_base_url: str, backend_base_url: str) -> str:
    """playlist 内のセグメントURLをバックエンドのプロキシURL経由に書き換える

    例:
        元: chunk_00001.aac
        → http://localhost:8080/api/proxy/segment?url=https%3A%2F%2Fradiko.jp%2F...%2Fchunk_00001.aac
    """
    lines = []
    for line in playlist.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            lines.append(line)
            continue

        # URLの行 → 書き換え
        if not stripped.startswith("http"):
            absolute_url = urljoin(playlist_base_url, stripped)
        else:
            absolute_url = stripped

        encoded = quote(absolute_url, safe="")
        proxy_url = f"{backend_base_url}/api/proxy/segment?url={encoded}"
        lines.append(proxy_url)

    return "\n".join(lines)
