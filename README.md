# DigiPeople Core - Digital Human Core System

**Language / 语言**: **English** | [简体中文](./README.zh-CN.md)

A complete digital human solution built on top of the Fay digital human framework and the MuseTalk lip-sync model.

User input (text) → Fay calls LLM to generate a reply → TTS speech synthesis → MuseTalk lip-sync → Talking-head video output.

## System Architecture

```
┌─────────┐    ┌──────────────────┐    ┌──────────────┐    ┌───────────┐
│Frontend │───▶│ Backend (FastAPI)│───▶│  Fay Service │───▶│ LLM (e.g. │
│ :8002   │    │  :8002           │    │  HTTP :5000  │    │  Ollama)  │
│         │◀───│                  │◀───│  WS   :10002 │    │  :11434   │
└─────────┘    │  ┌─────────┐    │    └──────────────┘    └───────────┘
               │  │  TTS    │    │
               │  │Edge-TTS │    │
               │  └────┬────┘    │
               │       ▼         │
               │  ┌──────────┐   │
               │  │ MuseTalk │   │
               │  │ GPU Inf. │   │
               │  └──────────┘   │
               └──────────────────┘
```

Two working modes:
- **Direct mode**: the backend API handles a request by serially calling Fay → TTS → MuseTalk.
- **WS skin-client mode**: the backend connects to Fay's port 10002 over WebSocket, listens for audio messages emitted by Fay, and automatically triggers MuseTalk.

## Requirements

| Item | Minimum | Recommended |
|------|---------|-------------|
| OS | Windows 10 / Linux | Windows 10/11 |
| Python | 3.10 | 3.10 (best compatibility with MuseTalk) |
| GPU | None (CPU is extremely slow) | NVIDIA RTX 4060 or above, 8 GB+ VRAM |
| CUDA | 11.7+ | 11.8 |
| RAM | 8 GB | 16 GB |
| FFmpeg | Required | Available in system PATH |
| Disk | 10 GB | 20 GB (including model weights) |

## Installation

### Step 1: Clone the project and third-party dependencies

This project depends on [Fay](https://github.com/TheRamU/Fay) and [MuseTalk](https://github.com/TMElyralab/MuseTalk). They are **not** bundled in this repository and must be cloned separately.

```bash
# 1. Clone this project
git clone <your-repo-url>
cd <your-repo-name>

# 2. Clone the Fay framework into the Fay/ directory
git clone https://github.com/TheRamU/Fay.git Fay

# 3. Clone MuseTalk into the MuseTalk/ directory
git clone https://github.com/TMElyralab/MuseTalk.git MuseTalk
```

> **Note**: Fay and MuseTalk are independent third-party open-source projects. Please comply with their respective licenses. This repository only provides the integration layer.

### Step 2: Install FFmpeg

Both MuseTalk and the TTS engine rely on FFmpeg for audio/video processing.

**Windows**:
1. Download `ffmpeg-master-latest-win64-gpl.zip` from https://github.com/BtbN/FFmpeg-Builds/releases
2. Extract it to any directory (e.g. `C:\ffmpeg`)
3. Add `C:\ffmpeg\bin` to the system `PATH` environment variable
4. Open a new terminal and verify: `ffmpeg -version`

**Linux**:
```bash
sudo apt update && sudo apt install ffmpeg -y
```

### Step 3: Install Fay

Fay is a standalone digital human dialogue framework that provides LLM chat, memory management, etc.

```powershell
# Enter the Fay directory
cd Fay

# Create a Python virtual environment (Fay uses Python 3.12)
python -m venv .venv

# Activate the virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/Mac:
# source .venv/bin/activate

# Install Fay dependencies
pip install -r requirements.txt

# Return to the project root
cd ..
```

#### Configure Fay's LLM

Fay reads LLM settings from `system.conf`. On first launch it pulls a default config from the config center; alternatively, you can create `Fay/system.conf` manually:

```ini
[key]
# Use a local Ollama model
gpt_base_url = http://localhost:11434/v1
gpt_model_engine = llama3.2
gpt_api_key = sk-ollama

# Or use a cloud API (e.g. SiliconFlow)
# gpt_base_url = https://api.siliconflow.cn/v1
# gpt_model_engine = zai-org/GLM-4.6
# gpt_api_key = sk-your-api-key
```

If you use Ollama, make sure it is installed and the model is pulled:
```bash
# After installing Ollama
ollama pull llama3.2
```

### Step 4: Install MuseTalk

MuseTalk is an audio-driven lip-sync model and requires its own Python environment (Python 3.10).

```powershell
# Enter the MuseTalk directory
cd MuseTalk

# Create an isolated virtual environment (Python 3.10 is required)
# If your system default is not 3.10, specify the path or use conda
python -m venv venv
# or: conda create -n musetalk python=3.10 && conda activate musetalk

# Activate the virtual environment
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Linux/Mac:
# source venv/bin/activate
```

#### 4.1 Install PyTorch (with CUDA support)

Pick the PyTorch wheel that matches your CUDA version:

```bash
# CUDA 11.8 (recommended)
pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1
# pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu121

# CPU only (very slow, not recommended)
# pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu
```

Verify CUDA:
```bash
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

#### 4.2 Install MuseTalk base dependencies

```bash
pip install -r requirements.txt
```

#### 4.3 Install the OpenMMLab stack

MuseTalk relies on mmcv / mmdet / mmpose for face detection and pose estimation:

```bash
pip install --no-cache-dir -U openmim
mim install mmengine
mim install "mmcv==2.0.1"
mim install "mmdet==3.1.0"
mim install "mmpose==1.1.0"
```

> **Common issue on Windows**: if `mmcv` fails to compile, try `pip install mmcv-lite>=2.0.1` as a fallback.

#### 4.4 Download model weights

Make sure the following model files are placed under `MuseTalk/models/`:

```
MuseTalk/models/
├── musetalkV15/          # MuseTalk v1.5 (recommended)
│   ├── unet.pth
│   └── musetalk.json
├── whisper/              # Whisper audio encoder
├── dwpose/               # Pose detection
├── sd-vae/               # Stable Diffusion VAE
├── face-parse-bisent/    # Face parsing
└── syncnet/              # Audio-visual sync network
```

Refer to the [official MuseTalk repo](https://github.com/TMElyralab/MuseTalk) for download instructions.

```bash
# Return to the project root
cd ..
```

### Step 5: Install backend dependencies

```powershell
# Activate the Fay virtual environment (backend shares the same env as Fay)
cd Fay
.\.venv\Scripts\Activate.ps1
cd ..

# Install backend dependencies
cd backend
pip install -r requirements.txt

# Edge-TTS (default TTS engine, installed separately)
pip install edge-tts

cd ..
```

### Step 6: Configure environment variables

```powershell
# Copy the environment template
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/Mac
```

Edit `.env`. Key settings:

```ini
# Backend port
BACKEND_PORT=8002

# Path to the MuseTalk Python interpreter (point to MuseTalk's isolated venv)
MUSETALK_PYTHON_PATH=C:\your\path\fay\MuseTalk\venv\Scripts\python.exe

# GPU half-precision acceleration (set to true if you have a GPU)
MUSETALK_USE_FLOAT16=true

# MuseTalk model version
MUSETALK_MODEL_VERSION=v15
```

## Getting Started

### Startup order

The three services must be started in the following order, each in its **own terminal window**:

#### Terminal 1: Start the LLM service (e.g. Ollama)

```bash
ollama serve
```

Ollama listens on `http://localhost:11434` by default. Skip this step if it already runs as a system service.

#### Terminal 2: Start Fay

```powershell
cd Fay
.\.venv\Scripts\Activate.ps1
python main.py start
```

Fay has started successfully when you see log lines like:
```
[系统] 服务启动完成!
Uvicorn running on http://0.0.0.0:8765
```

Ports exposed by Fay:
- **HTTP API**: `http://127.0.0.1:5000` (LLM chat endpoint)
- **WebSocket**: `ws://127.0.0.1:10002` (digital human message channel)
- **MCP SSE**: `http://127.0.0.1:8765` (MCP service)

#### Terminal 3: Start the backend

```powershell
cd Fay
.\.venv\Scripts\Activate.ps1
cd ..\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
```

Wait until you see:
```
服务初始化完成（含 MuseTalk 渲染器 WS 客户端）
Application startup complete.
Uvicorn running on http://0.0.0.0:8002
已连接 Fay WebSocket 10002          ← confirms Fay is connected
```

### Usage flow

1. **Open your browser** and visit `http://localhost:8002`

2. **Upload an avatar video**: click the upload area and choose an MP4 clip with a clearly visible frontal face (it will be used as the digital human's appearance).

3. **Wait for preprocessing**: the system automatically extracts frames and metadata after upload.

4. **Type your text**: enter whatever you want the avatar to say (e.g. "Hello, please introduce yourself").

5. **Click submit**: the system runs the full pipeline:
   - Send text to Fay → Fay calls the LLM to generate a reply
   - The reply is synthesized to a WAV audio via TTS
   - MuseTalk combines the audio with the avatar video to produce a lip-synced video
   - The frontend loads and plays the generated video automatically

6. **View the result**: the reply text and generated video are shown on the right side of the page.

> **The first inference takes longer** (5–7 minutes) because the model has to be loaded onto the GPU. Subsequent calls are much faster (1–2 minutes).

## API Reference

After startup, visit `http://localhost:8002/docs` for the full Swagger documentation.

Main endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health/` | GET | Health check, returns status of each service |
| `/api/avatars/upload` | POST | Upload an MP4 avatar video |
| `/api/avatars/{id}/info` | GET | Query avatar info |
| `/api/conversations/reply` | POST | Send text, get reply + audio + video |
| `/api/conversations/reply-stream` | POST | Streaming reply |
| `/api/renderer/latest` | GET | Get the most recent WS render result |
| `/api/renderer/set-default-avatar` | POST | Set the default avatar |
| `/api/tasks/{id}/status` | GET | Query task status |

### Conversation API example

```bash
curl -X POST http://localhost:8002/api/conversations/reply \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello", "username": "User", "avatar_id": "your_avatar_id"}'
```

## Project Structure

```
fay/
├── .env                    # Environment variables
├── README.md               # English docs (default)
├── README.zh-CN.md         # Chinese docs
├── CLAUDE.md               # AI assistant configuration notes
├── backend/                # Backend service (FastAPI)
│   ├── app/
│   │   ├── main.py         # Entry point, service initialization
│   │   ├── config.py       # Configuration management
│   │   ├── api/            # API routes
│   │   │   ├── health.py
│   │   │   ├── avatars.py
│   │   │   ├── conversations.py
│   │   │   └── renderer.py
│   │   └── services/       # Business services
│   │       ├── fay_client.py           # Fay HTTP client
│   │       ├── tts_service.py          # TTS speech synthesis
│   │       ├── musetalk_service.py     # MuseTalk inference
│   │       ├── musetalk_renderer_ws.py # WS skin client
│   │       ├── avatar_service.py       # Avatar management
│   │       └── job_service.py          # Task queue
│   └── requirements.txt
├── frontend/               # Frontend (HTML/CSS/JS)
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── Fay/                    # [clone separately] Fay framework
├── MuseTalk/               # [clone separately] MuseTalk lip-sync
├── data/                   # Runtime data
│   ├── uploads/            # User-uploaded raw files
│   ├── avatars/            # Preprocessed avatar data
│   ├── audio/              # TTS-generated audio
│   ├── videos/             # MuseTalk-generated videos
│   └── temp/               # Temporary files
├── tests/                  # Test scripts
└── scripts/                # Utility scripts
```

## Configuration

### TTS engine selection

Set `TTS_ENGINE` in `.env`:

| Engine | Value | Description |
|--------|-------|-------------|
| Edge-TTS | `edge_tts` | Microsoft online TTS, free and high quality (default) |
| CosyVoice | `cosy_voice` | Tencent open-source model, requires local deployment |
| VITS | `vits` | Local model, weights must be downloaded |
| Mock | `mock` | Generates silent placeholder audio, for testing only |

### MuseTalk tuning

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MUSETALK_MODEL_VERSION` | `v15` | Model version; v15 has better quality |
| `MUSETALK_USE_FLOAT16` | `true` | GPU half precision, lower VRAM usage |
| `MUSETALK_BBOX_SHIFT` | `0` | Face bounding-box offset, adjusts mouth position |
| `MUSETALK_FPS` | `25` | Output video frame rate |

## Troubleshooting

### Fay reply times out (falls back to a mock reply)

Fay's LLM calls can be slow (especially for cloud APIs). If the backend log shows `Fay API 调用异常`:
- Check `FAY_TIMEOUT` in `backend/app/config.py` (default 120 seconds)
- Cloud LLMs may need longer on the first call; increase the timeout as needed

### MuseTalk error: "DLL load failed"

PyTorch is broken or the CUDA version does not match:
```bash
cd MuseTalk
.\venv\Scripts\Activate.ps1
pip install torch==2.0.1+cu118 --index-url https://download.pytorch.org/whl/cu118 --force-reinstall --no-deps
```

Verify the fix:
```bash
python -c "import torch; print(torch.cuda.is_available())"
```

### MuseTalk inference is very slow

- Make sure `MUSETALK_USE_FLOAT16=true`
- Make sure PyTorch actually detects a GPU: `torch.cuda.is_available() == True`
- The first inference loads the model (5–7 minutes); later runs are much faster
- CPU inference may take 10+ minutes; using a GPU is strongly recommended

### MuseTalk is skipped after uploading an avatar

MuseTalk only accepts video files (`.mp4`, `.avi`, `.mov`, etc.) — images are not supported. Make sure you upload an MP4 video.

### Fay WebSocket 10002 fails to connect

If the backend log shows `Fay WebSocket 连接失败`:
- Make sure Fay is running and port 10002 is available
- The backend auto-reconnects and will recover once Fay is up

### Clear Fay's conversation memory

If you want Fay to forget previous conversations:
```powershell
# Stop Fay first, then remove the memory directory
Remove-Item "Fay/memory" -Recurse -Force
```

## License

This project is released under the MIT license. Please refer to the upstream projects for their respective licenses.

## Acknowledgements

- [Fay digital human framework](https://github.com/TheRamU/Fay)
- [MuseTalk](https://github.com/TMElyralab/MuseTalk)
