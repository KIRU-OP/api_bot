# 🎵 AnonXStreamAPI

**High-Performance YouTube Streaming & Extraction Microservice for Telegram Music Bots.**

Designed for seamless deployment on **Railway.app** to completely bypass YouTube datacenter IP blocks (`403 Forbidden` / `Sign in to confirm you're not a bot`) without burning cookies.

---

## ⚡ Key Highlights

- **Bypass Datacenter Bans:** Runs on Railway where YouTube bot-detection is far more lenient and cookies stay healthy.
- **Audio Proxy Streaming (`/audio/{id}`):** Proxies live audio bytes directly from Railway to your VPS bot via chunked HTTP stream. Your VPS bot connects to Railway instead of YouTube, ensuring zero 403 blocks on VPS.
- **API Key Security:** Protected by `X-API-Key` header or `api_key` query parameter to prevent unauthorized public usage.
- **Dynamic Cookie Auto-Reload:** Automatically loads cookies from any raw URL (like `batbin.me/raw/<id>`) on startup, or via `/reload_cookies`.
- **FastAPI Async Engine:** Ultra-low latency and minimal memory footprint.

---

## 🚀 Quick Deploy on Railway

### Method 1: Deploy with GitHub (Recommended)
1. Push this repository to your GitHub account (e.g. `https://github.com/<your-username>/AnonXStreamAPI`).
2. Go to [Railway Dashboard](https://railway.com/dashboard) and click **New Project** -> **Deploy from GitHub repo**.
3. Select your repo `AnonXStreamAPI`.
4. Add Environment Variables in Railway:
   - `API_KEY`: Set your custom secret key (e.g. `my_secret_token_12345`).
   - `COOKIES_URL` *(Optional)*: URL to raw cookies (e.g. `https://batbin.me/raw/deejay`).
5. Click **Generate Domain** in the **Settings** -> **Networking** section to get your public URL (e.g. `https://anonxstreamapi-production.up.railway.app`).

---

## 🔌 Connecting with AnonXMusic Bot

In your `AnonXMusic` `.env` file on your VPS, add:

```env
STREAM_API_URL=https://your-app-name.up.railway.app
STREAM_API_KEY=my_secret_token_12345
```

Restart your bot:
```bash
# In Telegram chat with bot:
/restart
```

That's it! Your bot will now route all search and audio streams through your private Railway API microservice. If the API is ever unreachable, the bot automatically falls back to local yt-dlp.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check & service status |
| `GET` | `/search?query=...` | Search YouTube for track info |
| `GET` | `/stream?id=...` | Extract direct stream URL and proxied audio URL |
| `GET` | `/audio/{video_id}` | Proxy audio stream chunks directly |
| `POST`| `/reload_cookies` | Fetch fresh cookies from `COOKIES_URL` |

### Authentication
Include your `API_KEY` either:
1. In the header: `X-API-Key: <your_key>`
2. Or as a query parameter: `?api_key=<your_key>`

---

## 🧪 Local Testing

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run local server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 3. Test health check
curl http://localhost:8000/
```
