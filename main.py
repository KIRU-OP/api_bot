"""
AnonXStreamAPI - High Performance YouTube Streaming Microservice
Features:
- FastAPI Streaming & Extraction Engine
- Telegram Bot for instant API Key generation & management
- MongoDB Database integration for dynamic key validation and analytics
"""

import os
import re
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aiohttp
import yt_dlp
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import database as db
from bot import start_telegram_bot, stop_telegram_bot

load_dotenv()

logging.basicConfig(
    format="[%(asctime)s - %(levelname)s] - %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("AnonXStreamAPI")

MASTER_API_KEY = os.getenv("API_KEY", "").strip()
COOKIES_URL = os.getenv("COOKIES_URL", "https://batbin.me/raw/deejay").strip()
COOKIE_FILE = os.getenv("COOKIE_FILE", "cookies.txt").strip()

_cookie_path: Optional[str] = None


async def fetch_cookies():
    global _cookie_path
    if COOKIES_URL:
        logger.info("Fetching fresh cookies from: %s", COOKIES_URL)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(COOKIES_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        with open("cookies.txt", "w", encoding="utf-8") as f:
                            f.write(content)
                        _cookie_path = os.path.abspath("cookies.txt")
                        logger.info("Cookies successfully saved to %s", _cookie_path)
                    else:
                        logger.warning("Failed to fetch cookies. HTTP status: %s", resp.status)
        except Exception as err:
            logger.error("Error fetching cookies from COOKIES_URL: %s", err)

    if not _cookie_path and os.path.exists(COOKIE_FILE):
        _cookie_path = os.path.abspath(COOKIE_FILE)
        logger.info("Using existing local cookie file: %s", _cookie_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize services in background so Uvicorn can immediately bind to $PORT for Railway health check
    async def _init_services():
        try:
            await db.init_db()
        except Exception as exc:
            logger.error("Database initialization failed: %s", exc)

        try:
            await fetch_cookies()
        except Exception as exc:
            logger.error("Cookies fetch failed: %s", exc)

        try:
            await start_telegram_bot()
        except Exception as exc:
            logger.error("Telegram bot start failed: %s", exc)

    init_task = asyncio.create_task(_init_services())
    logger.info("AnonXStreamAPI port ready for incoming traffic.")
    yield

    # Shutdown
    init_task.cancel()
    await stop_telegram_bot()
    logger.info("Shutting down AnonXStreamAPI...")


app = FastAPI(
    title="AnonXStreamAPI",
    description="YouTube Streaming Microservice with Telegram Key Manager and MongoDB",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_auth(x_api_key: Optional[str] = Header(None), api_key: Optional[str] = Query(None)):
    client_key = (x_api_key or api_key or "").strip()

    # If neither master API_KEY nor MongoDB is configured, open access
    if not MASTER_API_KEY and not db.is_connected():
        return True

    if not client_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide via 'X-API-Key' header or 'api_key' query parameter.",
        )

    # 1. Check against Master API Key
    if MASTER_API_KEY and client_key == MASTER_API_KEY:
        return True

    # 2. Check against MongoDB Database dynamic keys
    if db.is_connected() and await db.verify_api_key(client_key):
        return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or deactivated API key. Please generate a new key using the Telegram Bot.",
    )


def get_ydl_opts(video: bool = False) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "skip_download": True,
        "extract_flat": False,
        "remote_components": ["ejs:github"],
    }
    if _cookie_path and os.path.exists(_cookie_path):
        opts["cookiefile"] = _cookie_path

    if video:
        opts["format"] = "best[ext=mp4]/best"
    else:
        opts["format"] = "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best"

    return opts


def format_duration(seconds: Optional[int]) -> str:
    if not seconds or seconds <= 0:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


@app.get("/")
async def root():
    db_stats = await db.get_stats()
    return {
        "status": "online",
        "service": "AnonXStreamAPI",
        "version": "2.0.0",
        "master_auth_enabled": bool(MASTER_API_KEY),
        "mongodb_connected": db_stats.get("connected", False),
        "total_active_keys": db_stats.get("active_keys", 0),
        "cookies_loaded": bool(_cookie_path and os.path.exists(_cookie_path)),
    }


@app.get("/search")
async def search(
    query: str = Query(..., description="Song name or YouTube URL to search"),
    video: bool = Query(False, description="Search video format instead of audio"),
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
):
    await verify_auth(x_api_key, api_key)

    if not query.strip():
        raise HTTPException(status_code=400, detail="Query parameter cannot be empty.")

    clean_query = query.strip()
    search_target = clean_query if clean_query.startswith("http") else f"ytsearch1:{clean_query}"

    def _extract():
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "extract_flat": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["ios", "web"],
                }
            },
        }
        if _cookie_path and os.path.exists(_cookie_path):
            opts["cookiefile"] = _cookie_path
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(search_target, download=False)
                if not info:
                    return None
                if "entries" in info:
                    entries = [e for e in info["entries"] if e]
                    if not entries:
                        return None
                    return entries[0]
                return info
            except Exception as e:
                logger.warning("yt-dlp search error: %s", e)
                return None

    entry = await asyncio.to_thread(_extract)
    if not entry:
        raise HTTPException(status_code=404, detail="No matching YouTube results found.")

    v_id = entry.get("id", "")
    duration_sec = int(entry.get("duration", 0) or 0)

    return {
        "status": True,
        "id": v_id,
        "title": entry.get("title", "YouTube Track"),
        "duration": format_duration(duration_sec),
        "duration_sec": duration_sec,
        "channel_name": entry.get("uploader", "") or entry.get("channel", ""),
        "thumbnail": entry.get("thumbnail") or f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg",
        "url": entry.get("webpage_url") or f"https://www.youtube.com/watch?v={v_id}",
        "view_count": entry.get("view_count", ""),
    }


@app.get("/stream")
async def stream_info(
    request: Request,
    id: Optional[str] = Query(None, description="YouTube 11-char video ID"),
    query: Optional[str] = Query(None, description="YouTube URL or search term"),
    video: bool = Query(False, description="Stream video instead of audio"),
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
):
    await verify_auth(x_api_key, api_key)

    target_id = id or query
    if not target_id or not target_id.strip():
        raise HTTPException(status_code=400, detail="Must provide 'id' or 'query' parameter.")

    target = target_id.strip()
    if not target.startswith("http"):
        if re.match(r"^[A-Za-z0-9_-]{11}$", target):
            target = f"https://www.youtube.com/watch?v={target}"
        else:
            target = f"ytsearch1:{target}"

    def _extract_stream():
        opts = get_ydl_opts(video=video)
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(target, download=False)
                if not info:
                    return None, "No info returned by yt-dlp"
                if "entries" in info:
                    entries = [e for e in info["entries"] if e]
                    if not entries:
                        return None, "No entries found"
                    return entries[0], None
                return info, None
            except Exception as e:
                logger.warning("yt-dlp stream extraction error: %s", e)
                return None, str(e)

    entry, err_msg = await asyncio.to_thread(_extract_stream)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Failed to extract stream for given media: {err_msg}")

    direct_url = entry.get("url")
    v_id = entry.get("id", "")
    duration_sec = int(entry.get("duration", 0) or 0)

    base_url = str(request.base_url).rstrip("/")
    # Append the client key so downstream player can fetch audio stream cleanly
    used_key = (x_api_key or api_key or MASTER_API_KEY or "").strip()
    auth_query = f"?api_key={used_key}" if used_key else ""
    proxied_audio_url = f"{base_url}/audio/{v_id}{auth_query}"

    return {
        "status": True,
        "id": v_id,
        "title": entry.get("title", "YouTube Track"),
        "duration": format_duration(duration_sec),
        "duration_sec": duration_sec,
        "thumbnail": entry.get("thumbnail") or f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg",
        "url": entry.get("webpage_url") or f"https://www.youtube.com/watch?v={v_id}",
        "stream_url": direct_url,
        "audio_url": proxied_audio_url,
    }


@app.get("/audio/{video_id}")
async def proxy_audio_stream(
    video_id: str,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
):
    """
    Direct proxy audio stream from Railway to client (ffmpeg / PyTgCalls on VPS).
    Bypasses YouTube 403 Forbidden because connection to YouTube originates from Railway IP.
    """
    await verify_auth(x_api_key, api_key)

    if not re.match(r"^[A-Za-z0-9_-]{11}$", video_id):
        raise HTTPException(status_code=400, detail="Invalid YouTube video ID.")

    target_url = f"https://www.youtube.com/watch?v={video_id}"

    def _get_direct_audio():
        opts = get_ydl_opts(video=False)
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(target_url, download=False)
                return info.get("url") if info else None
            except Exception as ex:
                logger.error("Error extracting direct audio URL: %s", ex)
                return None

    raw_stream_url = await asyncio.to_thread(_get_direct_audio)
    if not raw_stream_url:
        raise HTTPException(status_code=404, detail="Could not resolve audio stream URL.")

    async def stream_generator():
        timeout = aiohttp.ClientTimeout(total=None, sock_read=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            async with session.get(raw_stream_url, headers=headers) as resp:
                if resp.status not in (200, 206):
                    logger.warning("Upstream audio stream returned status: %s", resp.status)
                    return
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    if chunk:
                        yield chunk

    return StreamingResponse(
        stream_generator(),
        media_type="audio/webm",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
        },
    )


DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_downloads(max_files: int = 40):
    """Keep downloaded media directory clean by removing oldest files."""
    try:
        files = sorted(DOWNLOAD_DIR.glob("*"), key=lambda p: p.stat().st_mtime)
        if len(files) > max_files:
            for f in files[: len(files) - max_files]:
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Cache cleanup error: %s", e)


def download_media(video_id: str, video: bool = False) -> tuple[Optional[str], Optional[str]]:
    """Download audio or video track locally using Railway IP and cookies."""
    cleanup_downloads()
    target_ext = "mp4" if video else "webm"
    target_path = DOWNLOAD_DIR / f"{video_id}.{target_ext}"

    # Check if exact file exists
    if target_path.exists() and target_path.stat().st_size > 1000:
        return str(target_path), None

    # Check for alternate audio formats if not video
    if not video:
        for ext in ["webm", "m4a", "opus", "mp3"]:
            cand = DOWNLOAD_DIR / f"{video_id}.{ext}"
            if cand.exists() and cand.stat().st_size > 1000:
                return str(cand), None

    target_url = f"https://www.youtube.com/watch?v={video_id}"
    base_opts = {
        "outtmpl": str(DOWNLOAD_DIR / f"%(id)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "geo_bypass": True,
        "no_warnings": True,
        "overwrites": True,
        "nocheckcertificate": True,
        "remote_components": ["ejs:github"],
    }
    if _cookie_path and os.path.exists(_cookie_path):
        base_opts["cookiefile"] = _cookie_path

    if video:
        ydl_opts = {
            **base_opts,
            "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)/best",
            "merge_output_format": "mp4",
        }
    else:
        ydl_opts = {
            **base_opts,
            "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([target_url])
    except Exception as e:
        logger.error("Download failed for %s: %s", video_id, e)
        return None, str(e)

    # 1. First priority: webm
    webm_cand = DOWNLOAD_DIR / f"{video_id}.webm"
    if webm_cand.exists() and webm_cand.stat().st_size > 1000:
        return str(webm_cand), None

    # 2. Second priority: m4a
    m4a_cand = DOWNLOAD_DIR / f"{video_id}.m4a"
    if m4a_cand.exists() and m4a_cand.stat().st_size > 1000:
        return str(m4a_cand), None

    # 3. Fallback: any downloaded file for this video_id
    for cand in DOWNLOAD_DIR.glob(f"{video_id}.*"):
        if cand.is_file() and cand.stat().st_size > 1000:
            return str(cand), None

    return None, "File not found after yt-dlp execution."


@app.get("/download/{video_id}")
async def download_track(
    video_id: str,
    video: bool = Query(False, description="Download video instead of audio"),
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
):
    """
    Download a track on Railway server and serve the binary file to VPS.
    Bypasses YouTube datacenter 403 blocks because Railway downloads the file with cookies.
    """
    await verify_auth(x_api_key, api_key)

    if not re.match(r"^[A-Za-z0-9_-]{11}$", video_id):
        raise HTTPException(status_code=400, detail="Invalid YouTube video ID.")

    file_path, err = await asyncio.to_thread(download_media, video_id, video)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail=f"Failed to download track on Railway: {err}")

    filename = os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=filename,
        headers={"X-Filename": filename},
    )


@app.post("/reload_cookies")
async def reload_cookies(
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
):
    await verify_auth(x_api_key, api_key)
    await fetch_cookies()
    return {
        "status": True,
        "message": "Cookies reloaded successfully",
        "cookies_loaded": bool(_cookie_path and os.path.exists(_cookie_path)),
    }


@app.get("/stats")
async def get_stats():
    return await db.get_stats()


if __name__ == "__main__":
    import uvicorn
    raw_port = os.getenv("PORT", "8000")
    try:
        port = int(raw_port)
    except ValueError:
        port = 8000
    logger.info("Starting uvicorn on 0.0.0.0:%d", port)
    uvicorn.run("main:app", host="0.0.0.0", port=port)

