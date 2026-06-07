"""radiko HLS Proxy - 番組情報モジュール

radiko の現在放送中番組 XML を取得・パースし、
各放送局の番組名・サムネイル・出演者情報を返す。
"""

import logging
import time
from xml.etree import ElementTree

import httpx

from . import config
from .auth import radiko_auth

logger = logging.getLogger(__name__)

# キャッシュ (60秒で無効化)
_programs_cache: dict | None = None
_programs_cache_at: float = 0.0
_PROGRAMS_CACHE_TTL = 60  # 秒


async def get_now_programs() -> dict[str, dict]:
    """現在放送中の番組情報を取得する

    Returns:
        station_id をキーとした辞書:
        {
            "ABC": {
                "title": "おはようパーソナリティ...",
                "img": "https://...",
                "performer": "道上洋三",
                "start_time": "20260607060000",
                "end_time": "20260607090000",
            },
            ...
        }
    """
    global _programs_cache, _programs_cache_at

    # キャッシュが有効ならそのまま返す
    if _programs_cache and (time.time() - _programs_cache_at) < _PROGRAMS_CACHE_TTL:
        return _programs_cache

    auth_status = await radiko_auth.get_auth_status()
    area_id = auth_status["area_id"]

    if not area_id:
        logger.warning("番組情報取得: エリアIDが未設定です")
        return {}

    url = config.RADIKO_NOW_PROGRAMS_URL.format(area_id=area_id)
    logger.info("番組情報を取得中... (url=%s)", url)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        logger.error("番組情報の取得に失敗: %s", e)
        return _programs_cache or {}

    root = ElementTree.fromstring(resp.text)
    programs: dict[str, dict] = {}

    # XML 構造: <radiko> → <stations> → <station id="ABC"> → <progs> → <prog>
    for station_elem in root.findall(".//station"):
        station_id = station_elem.get("id", "")
        if not station_id:
            continue

        # <progs> の中から現在放送中の <prog> を取得
        prog_elem = station_elem.find(".//prog")
        if prog_elem is None:
            continue

        title = _get_text_elem(prog_elem, "title")
        img = _get_text_elem(prog_elem, "img")
        performer = _get_text_elem(prog_elem, "pfm")
        start_time = prog_elem.get("ft", "")
        end_time = prog_elem.get("to", "")

        programs[station_id] = {
            "title": title,
            "img": img,
            "performer": performer,
            "start_time": start_time,
            "end_time": end_time,
        }

    _programs_cache = programs
    _programs_cache_at = time.time()
    logger.info("番組情報取得完了: %d 局", len(programs))
    return programs


def _get_text_elem(parent: ElementTree.Element, tag: str) -> str:
    """子要素のテキストを安全に取得"""
    child = parent.find(tag)
    return child.text.strip() if child is not None and child.text else ""
