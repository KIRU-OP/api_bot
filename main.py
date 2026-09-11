"""
AnonXStreamAPI - High Performance YouTube Streaming Microservice
Designed for deployment on Railway to bypass YouTube datacenter 403 blocks for Telegram Music Bots.
"""

import os
import re
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

import aiohttp
import yt_dlp
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

load_dotenv()

logging.basicConfig(
    format="[%(asctime)s - %(levelname)s] - %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("AnonXStreamAPI")

API_KEY = os.getenv("API_KEY", "").strip()
COOKIES_URL = os.getenv("COOKIES_URL", "").strip()
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
    await fetch_cookies()
    logger.info("AnonXStreamAPI started successfully.")
    yield
    logger.info("Shutting down AnonXStreamAPI...")


app = FastAPI(
    title="AnonXStreamAPI",
    description="YouTube Streaming & Extraction Microservice for Telegram Music Bots",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_auth(x_api_key: Optional[str] = Header(None), api_key: Optional[str] = Query(None)):
    if not API_KEY:
        return True  # No API_KEY configured on server; open mode
    client_key = x_api_key or api_key
    if not client_key or client_key.strip() != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Provide via 'X-API-Key' header or 'api_key' query parameter.",
        )
    return True


def get_ydl_opts(video: bool = False) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "skip_download": True,
        "extract_flat": False,
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
    return {
        "status": "online",
        "service": "AnonXStreamAPI",
        "version": "1.0.0",
        "auth_enabled": bool(API_KEY),
        "cookies_loaded": bool(_cookie_path and os.path.exists(_cookie_path)),
    }


@app.get("/search")
async def search(
    query: str = Query(..., description="Song name or YouTube URL to search"),
    video: bool = Query(False, description="Search video format instead of audio"),
    _: bool = Query(True, include_in_schema=False),
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
):
    verify_auth(x_api_key, api_key)

    if not query.strip():
        raise HTTPException(status_code=400, detail="Query parameter cannot be empty.")

    clean_query = query.strip()
    search_target = clean_query if clean_query.startswith("http") else f"ytsearch1:{clean_query}"

    def _extract():
        opts = get_ydl_opts(video=video)
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
    verify_auth(x_api_key, api_key)

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
                    return None
                if "entries" in info:
                    entries = [e for e in info["entries"] if e]
                    if not entries:
                        return None
                    return entries[0]
                return info
            except Exception as e:
                logger.warning("yt-dlp stream extraction error: %s", e)
                return None

    entry = await asyncio.to_thread(_extract_stream)
    if not entry:
        raise HTTPException(status_code=404, detail="Failed to extract stream for given media.")

    direct_url = entry.get("url")
    v_id = entry.get("id", "")
    duration_sec = int(entry.get("duration", 0) or 0)

    # Base URL of current API deployment
    base_url = str(request.base_url).rstrip("/")
    auth_query = f"?api_key={API_KEY}" if API_KEY else ""
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
    verify_auth(x_api_key, api_key)

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


@app.post("/reload_cookies")
async def reload_cookies(
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
):
    verify_auth(x_api_key, api_key)
    await fetch_cookies()
    return {
        "status": True,
        "message": "Cookies reloaded successfully",
        "cookies_loaded": bool(_cookie_path and os.path.exists(_cookie_path)),
    }
