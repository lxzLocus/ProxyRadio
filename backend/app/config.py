"""radiko HLS Proxy - 設定管理"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Server ───────────────────────────────────────────
PORT = int(os.getenv("PORT", "8080"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

# ─── radiko API Endpoints ─────────────────────────────
RADIKO_AUTH1_URL = "https://radiko.jp/v2/api/auth1"
RADIKO_AUTH2_URL = "https://radiko.jp/v2/api/auth2"
RADIKO_STATION_LIST_URL = "https://radiko.jp/v3/station/list/{area_id}.xml"
RADIKO_NOW_PROGRAMS_URL = "https://radiko.jp/v3/program/now/{area_id}.xml"
RADIKO_STREAM_URL = "https://radiko.jp/v2/station/stream_smh_multi/{station_id}.xml"

# radiko live playlist (通常パターン)
RADIKO_LIVE_PLAYLIST_BASE = "https://rpaa.smartstream.ne.jp/so/playlist.m3u8"

# ─── radiko Auth Constants ────────────────────────────
# 公開情報: radiko JS プレイヤーから抽出される認証キー
RADIKO_AUTH_KEY = "bcd151073c03b352e1ef2fd66c32209da9ca0afa"

# クライアント偽装ヘッダー (PC HTML5 プレイヤー)
RADIKO_APP = "pc_html5"
RADIKO_APP_VERSION = "0.0.1"
RADIKO_USER = "dummy_user"
RADIKO_DEVICE = "pc"

# ─── Area ─────────────────────────────────────────────
# 明示的にエリアIDを指定する場合 (例: JP27 = 大阪)
# 空の場合は auth2 の結果で自動検出
RADIKO_AREA_ID = os.getenv("RADIKO_AREA_ID", "")

# ─── Token Cache ──────────────────────────────────────
# トークンのキャッシュ有効期間 (秒)
# radiko のトークンは通常数時間有効だが、安全のため短めに設定
TOKEN_CACHE_TTL = int(os.getenv("TOKEN_CACHE_TTL", "3600"))

# ─── Frontend ─────────────────────────────────────────
# フロントエンドが使用するバックエンドの URL
# 例: http://192.168.10.10:8081
# 空の場合はフロントエンドと同一オリジン（same-origin）を使用
BACKEND_URL = os.getenv("BACKEND_URL", "")
