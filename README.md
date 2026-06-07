# HLS Proxy

HLS Proxy Application

## 構成

- **`backend`**: FastAPI (Python 3.12)
  - 認証、番組リスト取得、プレイリスト (`.m3u8`) およびセグメント (`.ts` / `.aac`) のプロキシ
- **`frontend`**: Nginx + HLS.js
  - ブラウザで放送局を選択して再生可能なシンプルな Web プレイヤー

---

## クイックスタート

### 1. 環境変数の設定

プロジェクトルートにある `.env.example` をコピーして `.env` を作成します。

```bash
cp .env.example .env
```

`.env` 内の `BACKEND_URL` に、ブラウザからバックエンドにアクセスする際のベースURL（例: `http://localhost:8081`）を指定してください。

### 2. 起動

Docker Compose を利用して一括で起動します。

```bash
docker compose up -d --build
```

- **フロントエンド（プレイヤー）**: [http://localhost:3001](http://localhost:3001)
- **バックエンド（API）**: [http://localhost:8081](http://localhost:8081)

---

