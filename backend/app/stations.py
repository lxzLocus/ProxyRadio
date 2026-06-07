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

    logger.info("放送局一覧を取得中... (area=%s)", current_area)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(config.RADIKO_STATION_REGION_URL)
        resp.raise_for_status()

    root = ElementTree.fromstring(resp.text)
    stations = []

    # XML 構造: <region> → <stations> → <station> → <area_id>JP13</area_id>
    # area_id は <station> の子要素として格納されている
    for station_elem in root.findall(".//station"):
        station_area_id = _get_text(station_elem, "area_id")

        # 現在のエリアに属する局のみ抽出
        if station_area_id != current_area:
            continue

        station_id = _get_text(station_elem, "id")
        name = _get_text(station_elem, "name")
        ascii_name = _get_text(station_elem, "ascii_name")

        # ロゴURL: 複数サイズがあるが、大きめのものを選ぶ
        logo_url = ""
        for logo_elem in station_elem.findall("logo"):
            width = logo_elem.get("width", "0")
            if int(width) >= 124:
                logo_url = logo_elem.text or ""
                break
        if not logo_url:
            logo_elem = station_elem.find("logo")
            if logo_elem is not None:
                logo_url = logo_elem.text or ""

        stations.append(
            {
                "id": station_id,
                "name": name,
                "ascii_name": ascii_name,
                "logo_url": logo_url,
                "area_id": station_area_id,
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
