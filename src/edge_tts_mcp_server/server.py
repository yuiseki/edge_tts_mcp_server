"""
edge-tts MCPサーバー
Edge TTSを使用して、テキストから音声を生成するMCPサーバー
"""

import asyncio
import base64
import json
import os
import platform
import subprocess
import sys
import tempfile
from shutil import which
from typing import Dict, List, Optional, Sequence, Union, Callable

import edge_tts
from edge_tts import VoicesManager
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Windows用の再生ライブラリをインポート
if platform.system() == "Windows":
    # pylint: disable=import-error
    try:
        import asyncio
        import ctypes
        from ctypes import windll
    except ImportError:
        pass

class EdgeTTSTools:
    """Edge TTSのツール名を定義するクラス"""
    LIST_VOICES = "list_voices"
    TEXT_TO_SPEECH = "text_to_speech"

# Windows用の音声再生関数
def play_mp3_win32(mp3_path):
    """
    Windowsでバックグラウンドで音声を再生する関数
    """
    if platform.system() != "Windows":
        raise NotImplementedError("This function is only for Windows")

    try:
        # Short path nameを取得するための関数定義
        from ctypes import create_unicode_buffer, windll, wintypes

        _get_short_path_name_w = windll.kernel32.GetShortPathNameW
        _get_short_path_name_w.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        _get_short_path_name_w.restype = wintypes.DWORD

        def get_short_path_name(long_name):
            """
            長いパス名からDOS互換の短いパス名を取得します
            """
            output_buf_size = 0
            while True:
                output_buf = create_unicode_buffer(output_buf_size)
                needed = _get_short_path_name_w(long_name, output_buf, output_buf_size)
                if output_buf_size >= needed:
                    return output_buf.value
                output_buf_size = needed

        mci_send_string_w = windll.winmm.mciSendStringW

        def mci_send(msg):
            """MCIコマンド文字列を送信"""
            result = mci_send_string_w(msg, 0, 0, 0)
            if result != 0:
                print(f"Error {result} in mciSendString {msg}")
                return False
            return True

        # 短いパス名を取得
        mp3_shortname = get_short_path_name(mp3_path)

        # 以前のインスタンスをすべて閉じる
        mci_send("Close All")
        # MP3ファイルを開く
        mci_send(f'Open "{mp3_shortname}" Type MPEGVideo Alias theMP3')
        # 再生して完了を待つ
        mci_send("Play theMP3 Wait")
        # クローズ
        mci_send("Close theMP3")
        
        return True
    except Exception as e:
        print(f"Error occurred during playback on Windows: {e}")
        return False

# 遅延削除のためのヘルパー関数
async def _delayed_file_deletion(temp_path, delay_seconds):
    """指定した秒数待機してから一時ファイルを削除します"""
    await asyncio.sleep(delay_seconds)
    try:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
            print(f"Temporary file deleted: {temp_path}")
    except Exception as e:
        print(f"Error while deleting temporary file: {e}")

# mpvがインストールされているか確認する関数
def is_mpv_installed():
    """mpvがインストールされているかどうかを確認します"""
    return which("mpv") is not None

async def serve() -> None:
    """MCPサーバーの実行関数 - VSCode拡張向けの標準入出力を使ったMCPサーバー実装"""
    server = Server("edge-tts")
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """利用可能なツールのリストを返します"""
        return [
            Tool(
                name=EdgeTTSTools.LIST_VOICES,
                description="Get a list of available voices",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "locale": {
                            "type": "string",
                            "description": "Optional locale to filter voices (e.g., ja-JP, en-US)",
                        }
                    },
                    "required": [],
                },
            ),
            Tool(
                name=EdgeTTSTools.TEXT_TO_SPEECH,
                description="Convert text to speech",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to convert to speech",
                        },
                        "voice": {
                            "type": "string",
                            "description": "Voice to use (default: ja-JP-NanamiNeural)",
                            "default": "ja-JP-NanamiNeural",
                        },
                        "rate": {
                            "type": "string",
                            "description": "Speech rate (e.g., \"+10%\", \"-10%\")",
                            "default": "0%",
                        },
                        "volume": {
                            "type": "string",
                            "description": "Speech volume (e.g., \"+10%\", \"-10%\")",
                            "default": "0%",
                        },
                        "pitch": {
                            "type": "string",
                            "description": "Speech pitch (e.g., \"+10%\", \"-10%\")",
                            "default": "0%",
                        },
                        "play_audio": {
                            "type": "boolean",
                            "description": "Play the audio if true",
                            "default": True,
                        },
                        "use_default_player": {
                            "type": "boolean",
                            "description": "Use default media player if true (use mpv if false)",
                            "default": False,
                        }
                    },
                    "required": ["text"],
                },
            ),
        ]
    
    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict
    ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """ツール呼び出しを処理します"""
        try:
            match name:
                case EdgeTTSTools.LIST_VOICES:
                    locale = arguments.get("locale")
                    voices_manager = VoicesManager()
                    voices = await voices_manager.get_voices()
                    
                    if locale:
                        voices = [v for v in voices if v["Locale"].lower() == locale.lower()]
                    
                    result = [
                        {
                            "name": v["Name"],
                            "locale": v["Locale"],
                            "gender": v["Gender"],
                            "short_name": v["ShortName"],
                        }
                        for v in voices
                    ]
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                
                case EdgeTTSTools.TEXT_TO_SPEECH:
                    text = arguments.get("text")
                    if not text:
                        raise ValueError("Missing required argument: text")
                    
                    voice = arguments.get("voice", "ja-JP-NanamiNeural")
                    rate = arguments.get("rate", "0%")
                    volume = arguments.get("volume", "0%")
                    pitch = arguments.get("pitch", "0%")
                    play_audio = arguments.get("play_audio", True)
                    use_default_player = arguments.get("use_default_player", False)
                    
                    # デフォルトではmpvを使用、use_default_player=Trueの場合のみデフォルトプレーヤーを使用
                    use_mpv = not use_default_player
                    
                    # mpvが有効かつインストールされているか確認
                    mpv_available = use_mpv and is_mpv_installed()
                    if use_mpv and not mpv_available:
                        print("mpv not found. Using default player instead.")
                    
                    try:
                        print(f"Converting text \"{text}\" to speech...")
                        
                        # コミュニケーター作成
                        communicate = edge_tts.Communicate(text, voice)
                        
                        # 速度・音量・音程のパラメータは別途設定（必要に応じて）
                        if rate != "0%":
                            communicate.rate = rate
                        if volume != "0%":
                            communicate.volume = volume
                        if pitch != "0%":
                            communicate.pitch = pitch
                    
                        # 一時ファイルに音声を保存
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                            temp_path = temp_file.name
                        
                        # 字幕ファイルの作成（mpv使用時）
                        srt_path = None
                        if mpv_available:
                            with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as srt_file:
                                srt_path = srt_file.name
                        
                        # 音声生成と保存
                        await communicate.save(temp_path)
                        print(f"Created audio file: {temp_path}")
                        
                        # 音声を再生
                        if play_audio:
                            if mpv_available:
                                # mpvを使用して再生
                                print("Playing audio using mpv...")
                                mpv_cmd = ["mpv"]
                                if srt_path:
                                    mpv_cmd.append(f"--sub-file={srt_path}")
                                mpv_cmd.append(temp_path)
                                
                                with subprocess.Popen(mpv_cmd) as process:
                                    # 一定時間待機するのではなく、プロセスの終了を待つ
                                    process.communicate()
                            elif platform.system() == "Windows":
                                # Windows用のバックグラウンド再生
                                print("Playing audio in background on Windows...")
                                play_mp3_win32(temp_path)
                            else:
                                # デフォルトプレーヤーを使用
                                print("Playing audio with default player...")
                                if platform.system() == "Windows":
                                    os.system(f'start {temp_path}')
                                else:
                                    if which("xdg-open"):
                                        os.system(f'xdg-open {temp_path}')
                                    elif which("open"):  # macOS
                                        os.system(f'open {temp_path}')
                                    else:
                                        print("No suitable player found.")
                                
                                # 少し待機（デフォルトプレーヤーのみ）
                                await asyncio.sleep(0.5)
                        
                        result = {
                            "audio_path": temp_path,
                            "text": text,
                            "voice": voice
                        }
                        
                        # 非同期で一定時間後に一時ファイルを削除する
                        asyncio.create_task(_delayed_file_deletion(temp_path, 10))
                        if srt_path and os.path.exists(srt_path):
                            asyncio.create_task(_delayed_file_deletion(srt_path, 10))
                        
                        return [TextContent(type="text", text=json.dumps(result, indent=2))]
                    except Exception as e:
                        # エラーが発生した場合は、別の方法を試す
                        print(f"Error occurred in the first method: {e}")
                        # 代替方法: 基本的なパラメータのみで試す
                        print(f"Converting text \"{text}\" to speech (basic parameters only)...")
                        communicate = edge_tts.Communicate(text, voice)
                        
                        # 一時ファイルに音声を保存
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                            temp_path = temp_file.name
                        
                        # 音声生成と保存
                        await communicate.save(temp_path)
                        print(f"Created audio file: {temp_path}")
                        
                        # 音声を再生
                        if play_audio:
                            if mpv_available:
                                # mpvを使用して再生
                                print("Playing audio using mpv...")
                                with subprocess.Popen(["mpv", temp_path]) as process:
                                    process.communicate()
                            elif platform.system() == "Windows":
                                # Windows用のバックグラウンド再生
                                print("Playing audio in background on Windows...")
                                play_mp3_win32(temp_path)
                            else:
                                # デフォルトプレーヤーを使用
                                print("Playing audio with default player...")
                                if platform.system() == "Windows":
                                    os.system(f'start {temp_path}')
                                else:
                                    if which("xdg-open"):
                                        os.system(f'xdg-open {temp_path}')
                                    elif which("open"):  # macOS
                                        os.system(f'open {temp_path}')
                                    else:
                                        print("No suitable player found.")
                                
                                # 少し待機（デフォルトプレーヤーのみ）
                                await asyncio.sleep(0.5)
                        
                        result = {
                            "audio_path": temp_path,
                            "text": text,
                            "voice": voice
                        }
                        
                        # 非同期で一定時間後に一時ファイルを削除する
                        asyncio.create_task(_delayed_file_deletion(temp_path, 10))
                        
                        return [TextContent(type="text", text=json.dumps(result, indent=2))]
                
                case _:
                    raise ValueError(f"Unknown tool: {name}")
        
        except Exception as e:
            raise ValueError(f"Error processing edge-tts query: {str(e)}")
    
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)

if __name__ == "__main__":
    asyncio.run(serve())
