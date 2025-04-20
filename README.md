# Edge-TTS MCP Server

Model Context Protocol (MCP) サーバーで、Microsoft Edge のテキスト読み上げ機能を活用した AI エージェントの音声合成サービスを提供します。

## 概要

この MCP サーバーは、[edge-tts](https://github.com/rany2/edge-tts)ライブラリを使用して、テキストから音声への変換機能を提供します。AI エージェントが自然な音声で応答できるようにするためのツールとして設計されています。

## 機能

- テキストから音声への変換
- 複数の音声と言語のサポート
- 音声速度と音程の調整
- 音声データのストリーミング

## インストール

```bash
pip install "edge_tts_mcp_server"
```

または開発モードでインストールする場合：

```bash
git clone https://github.com/yuiseki/edge_tts_mcp_server.git
cd edge_tts_mcp_server
pip install -e .
```

## 使用方法

### MCP Inspector での使用

標準的な MCP サーバーとして実行：

```bash
mcp dev server.py
```

または、コマンドラインツールとして実行：

```bash
edge-tts-mcp --standard
```

### uvx（uvicorn）での実行

FastAPI ベースのサーバーとして uvx で実行する場合：

```bash
uvx edge_tts_mcp_server.server:get_app
```

または、コマンドラインツールを使用：

```bash
edge-tts-mcp
```

コマンドラインオプション：

```bash
edge-tts-mcp --host 0.0.0.0 --port 8080 --reload
```

### Claude Desktop との統合

```bash
mcp install server.py
```

## API エンドポイント

FastAPI モードで実行した場合、以下のエンドポイントが利用可能です：

- `/` - API 情報
- `/health` - ヘルスチェック
- `/voices` - 利用可能な音声一覧（オプションで `?locale=ja-JP` などでフィルタリング可能）
- `/mcp` - MCP API エンドポイント

## ライセンス

MIT
