# 🎵 AnonXStreamAPI v2.0

**High-Performance YouTube Streaming & Extraction Microservice with built-in Telegram Bot & MongoDB Key Management.**

Designed for seamless deployment on **Railway.app** to completely bypass YouTube datacenter IP blocks (`403 Forbidden` / `Sign in to confirm you're not a bot`) for Telegram Music Bots without burning cookies.

---

## ⚡ Features in v2.0

- 🛡️ **Bypass Datacenter Bans:** Runs on Railway where YouTube bot-detection is far more lenient and cookies stay healthy.
- 🤖 **Built-in Telegram Bot:** Users can get their own random API Key directly via Telegram (`/genkey` or inline button) without touching code.
- 🗄️ **MongoDB Dynamic Keys:** Automatically saves and validates generated API keys, tracks request count per key, and allows instant key revocation.
- 📡 **Audio Chunk Proxy (`/audio/{id}`):** Proxies live audio bytes directly from Railway to your VPS bot via chunked HTTP stream. Your VPS bot connects to Railway instead of YouTube, ensuring zero 403 blocks on VPS.
- 🔄 **Cookie Auto-Reload:** Automatically downloads fresh cookies from any raw URL (like `batbin.me/raw/<id>`) on startup, or via `/reload_cookies`.
- ⚡ **FastAPI Async Architecture:** Ultra-fast async execution with minimal memory usage.

---

## 🚀 Deployment on Railway

### 1. Deploy from GitHub
1. Fork or push this repository to your GitHub account (`https://github.com/SenpaiLabs/AnonXStreamAPI`).
2. Go to [Railway Dashboard](https://railway.com/dashboard) and click **New Project** -> **Deploy from GitHub repo**.
3. Select `AnonXStreamAPI`.

### 2. Set Environment Variables in Railway
In Railway's **Variables** tab, add:

| Variable | Required | Description |
|---|---|---|
| `MONGO_URL` | **Yes** | Your MongoDB connection string (e.g. from cloud.mongodb.com) |
| `BOT_TOKEN` | **Yes** | Telegram Bot Token from [@BotFather](https://t.me/BotFather) |
| `OWNER_ID` | Optional | Your numeric Telegram user ID (for admin commands) |
| `API_KEY` | Optional | Master override API Key for admin use |
| `COOKIES_URL` | Optional | URL to raw cookies (e.g. `https://batbin.me/raw/deejay`) |
| `PUBLIC_URL` | Optional | Your public Railway URL (e.g. `https://xxx.up.railway.app`) |

### 3. Generate Public Domain
In **Settings** -> **Networking**, click **Generate Domain** to get your public API URL.

---

## 🤖 Telegram Bot Usage

Start your bot on Telegram:
- `/start` — Interactive menu with buttons to generate keys, view keys, and check server stats.
- `/genkey` — Generate a random, unique API Key.
- `/mykeys` — View all your active API Keys and usage count.
- `/revoke <key>` — Deactivate an API Key.
- `/stats` — View total keys generated, active keys, and total requests served.

---

## 🔌 Connecting with AnonXMusic Bot

In your `AnonXMusic` `.env` file on your VPS, simply add the API URL and the generated key:

```env
STREAM_API_URL=https://your-app-name.up.railway.app
STREAM_API_KEY=anonx_live_xxxxxxxxxxxxxxxxxxxx
```

Restart your bot:
```bash
# In Telegram chat with bot:
/restart
```

Your bot will now route all music streams through Railway with zero YouTube 403 blocks!

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check & system status |
| `GET` | `/search?query=...` | Search YouTube for track info |
| `GET` | `/stream?id=...` | Extract direct stream URL and proxied audio URL |
| `GET` | `/audio/{video_id}` | Proxy audio stream chunks directly |
| `GET` | `/stats` | API & MongoDB usage statistics |
| `POST`| `/reload_cookies` | Fetch fresh cookies from `COOKIES_URL` |

### Authentication
Include your generated API Key either:
1. In the header: `X-API-Key: <your_key>`
2. Or as a query parameter: `?api_key=<your_key>`
