"""radiko HLS Proxy - 放送局一覧モジュール

radiko の局情報 XML を取得・パースし、エリア内の放送局一覧を返す。
"""

import logging
from xml.etree import ElementTree

import httpx

from . import config
from .auth import radiko_auth

logger = logging.getLogger(__name__)

# キャッシュ
_stations_cache: dict | None = None


async def get_stations(force_refresh: bool = False) -> dict:
    """エリア内の放送局一覧を取得する

    Returns:
        {
            "area_id": "JP27",
            "area_name": "大阪",
            "stations": [
                {
                    "id": "ABC",
                    "name": "ABCラジオ",
                    "ascii_name": "ABC RADIO",
                    "logo_url": "https://...",
                    "area_id": "JP27",
                },
                ...
            ]
        }
    """
    global _stations_cache
    if _stations_cache and not force_refresh:
        return _stations_cache

    token = await radiko_auth.get_token()
    auth_status = await radiko_auth.get_auth_status()
    current_area = auth_status["area_id"]

    async with httpx.AsyncClient(timeout=15.0) as client:
        url = config.RADIKO_STATION_LIST_URL.format(area_id=current_area)
        logger.info("放送局一覧を取得中... (url=%s)", url)
        resp = await client.get(url)
        resp.raise_for_status()

    root = ElementTree.fromstring(resp.text)
    stations = []

    # XML 構造: <stations> → <station>
    for station_elem in root.findall(".//station"):
        station_id = _get_text(station_elem, "id")
        name = _get_text(station_elem, "name")
        ascii_name = _get_text(station_elem, "ascii_name")

        # ロゴURL: 複数サイズがあるが、大きめのものを選ぶ
        logo_url = ""
        # 1. <logo> タグを検索 (複数サイズから124px以上のものを選ぶ)
        for logo_elem in station_elem.findall("logo"):
            width = logo_elem.get("width", "0")
            if int(width) >= 124:
                logo_url = logo_elem.text or ""
                break
        if not logo_url:
            # 2. 単一の <logo> タグがある場合
            logo_elem = station_elem.find("logo")
            if logo_elem is not None and logo_elem.text:
                logo_url = logo_elem.text.strip()
        if not logo_url:
            # 3. <logo_large> などのタグがある場合
            for tag in ["logo_large", "logo_medium", "logo_small", "logo_xsmall"]:
                logo_elem = station_elem.find(tag)
                if logo_elem is not None and logo_elem.text:
                    logo_url = logo_elem.text.strip()
                    break

        stations.append(
            {
                "id": station_id,
                "name": name,
                "ascii_name": ascii_name,
                "logo_url": logo_url,
                "area_id": current_area,
            }
        )

    result = {
        "area_id": current_area,
        "area_name": auth_status["area_name"],
        "stations": stations,
    }

    _stations_cache = result
    logger.info("放送局一覧取得完了: %d 局", len(stations))
    return result


def clear_cache() -> None:
    """キャッシュをクリアする"""
    global _stations_cache
    _stations_cache = None


def _get_text(elem: ElementTree.Element, tag: str) -> str:
    """子要素のテキストを安全に取得"""
    child = elem.find(tag)
    return child.text.strip() if child is not None and child.text else ""
