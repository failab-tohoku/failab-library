# failab-library

PDF閲覧と全文検索のWebアプリです。

## 技術構成

1. `frontend`: React + PDF.js
2. `backend`: FastAPI + SQLite FTS5
3. `nginx`: HTTPS終端 / リバースプロキシ / PDF配信

## 前提

1. Docker / Docker Compose
2. `python3`
3. `openssl`
4. `envsubst`（`gettext`）
5. `bcrypt`（ローカルで`.env`生成時）

```bash
python3 -m pip install --user bcrypt
```

## セットアップ

1. `bcrypt` をインストール
```bash
python3 -m pip install bcrypt
```

2. 環境変数ファイルを生成
```bash
./scripts/init_env.sh
```

3. 起動
```bash
docker-compose up -d --build
```

4. アクセス
```text
https://localhost
```

注: 自己署名証明書のため、ブラウザ警告が表示されます。

## AWSセットアップ（EC2）

1. EC2を作成（Amazon Linux推奨）
2. セキュリティグループで `22`, `80`, `443` を許可
3. SSH接続後、このリポジトリを配置
4. PDFを配置（`backend/app/resources/pdfs`）
5. 初期セットアップ
```bash
./setup.sh
```
6. `bcrypt` をインストール
```bash
python3 -m pip install bcrypt
```
7. 環境変数ファイルを生成
```bash
./scripts/init_env.sh
```
8. 起動
```bash
docker-compose up -d --build
```
9. 動作確認
```bash
docker ps
curl -k https://localhost
```

アクセスURL:
```text
https://<EC2のPublic DNSまたはPublic IP>
```

## よく使うコマンド

再起動:
```bash
docker-compose down
docker-compose up -d --build
```

停止:
```bash
docker-compose down
```

ログ確認:
```bash
docker-compose logs -f nginx
docker-compose logs -f backend
```

## ディレクトリ

1. PDF: `backend/app/resources/pdfs`
2. サムネイル: `backend/app/resources/thumbnails`
3. 検索DB: `backend/app/resources/search.db`

## 容量管理

Dockerのビルドキャッシュが肥大化しやすいので、定期的に確認してください。

確認:
```bash
docker system df
df -h
du -sh backend/app/resources/*
```

キャッシュ削除:
```bash
docker builder prune -a -f
```

未使用イメージ削除:
```bash
docker image prune -a -f
```

注: `backend/.dockerignore` で `app/resources/` を除外しています。  
PDFやサムネイルはイメージに同梱せず、ホスト側をマウントして運用します。

## セキュリティ注意

1. `backend` の `8000` は外部公開しない
2. `.env` はGitにコミットしない
3. 本番では `COOKIE_SECURE=true` を維持する
