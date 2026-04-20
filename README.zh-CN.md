# DigiPeople Core - 数字人核心系统

**Language / 语言**: [English](./README.md) | **简体中文**

基于 Fay 数字人框架和 MuseTalk 唇形同步技术的完整数字人解决方案。

用户输入文本 → Fay 调用 LLM 生成回复 → TTS 语音合成 → MuseTalk 唇形同步 → 输出说话视频

## 系统架构

```
┌─────────┐    ┌──────────────────┐    ┌──────────────┐    ┌───────────┐
│  前端    │───▶│  后端 (FastAPI)   │───▶│  Fay 服务     │───▶│ LLM 服务   │
│ :8002   │    │  :8002           │    │  HTTP :5000  │    │ (Ollama)  │
│         │◀───│                  │◀───│  WS :10002   │    │ :11434    │
└─────────┘    │  ┌─────────┐    │    └──────────────┘    └───────────┘
               │  │  TTS    │    │
               │  │Edge-TTS │    │
               │  └────┬────┘    │
               │       ▼         │
               │  ┌──────────┐   │
               │  │MuseTalk  │   │
               │  │ GPU推理   │   │
               │  └──────────┘   │
               └──────────────────┘
```

两种工作模式：
- **直连模式**：后端 API 收到请求后串行调用 Fay → TTS → MuseTalk
- **WS 皮肤客户端模式**：后端通过 WebSocket 连接 Fay 10002 端口，监听 Fay 发出的音频消息后自动触发 MuseTalk

## 环境要求

| 项目 | 最低要求 | 推荐配置 |
|------|---------|---------|
| 操作系统 | Windows 10 / Linux | Windows 10/11 |
| Python | 3.10 | 3.10（MuseTalk 兼容性最佳） |
| GPU | 无（CPU 极慢） | NVIDIA RTX 4060 及以上，8GB+ 显存 |
| CUDA | 11.7+ | 11.8 |
| 内存 | 8 GB | 16 GB |
| FFmpeg | 必须安装 | 系统 PATH 中可用 |
| 磁盘 | 10 GB | 20 GB（含模型权重） |

## 安装步骤

### 第一步：克隆项目并获取第三方依赖

本项目依赖 [Fay](https://github.com/TheRamU/Fay) 和 [MuseTalk](https://github.com/TMElyralab/MuseTalk)，它们不包含在本仓库中，需要单独 clone。

```bash
# 1. 克隆本项目
git clone <your-repo-url>
cd <your-repo-name>

# 2. 克隆 Fay 数字人框架到 Fay/ 目录
git clone https://github.com/TheRamU/Fay.git Fay

# 3. 克隆 MuseTalk 唇形同步模型到 MuseTalk/ 目录
git clone https://github.com/TMElyralab/MuseTalk.git MuseTalk
```

> **注意**：Fay 和 MuseTalk 是独立的第三方开源项目，请遵循各自的许可证。本项目仅提供集成层代码。

### 第二步：安装 FFmpeg

MuseTalk 和 TTS 都依赖 FFmpeg 进行音视频处理。

**Windows**：
1. 从 https://github.com/BtbN/FFmpeg-Builds/releases 下载 `ffmpeg-master-latest-win64-gpl.zip`
2. 解压到任意目录（如 `C:\ffmpeg`）
3. 将 `C:\ffmpeg\bin` 添加到系统环境变量 `PATH`
4. 打开新终端验证：`ffmpeg -version`

**Linux**：
```bash
sudo apt update && sudo apt install ffmpeg -y
```

### 第三步：安装 Fay

Fay 是独立的数字人对话框架，提供 LLM 对话、记忆管理等功能。

```powershell
# 进入 Fay 目录
cd Fay

# 创建 Python 虚拟环境（Fay 使用 Python 3.12）
python -m venv .venv

# 激活虚拟环境
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/Mac:
# source .venv/bin/activate

# 安装 Fay 依赖
pip install -r requirements.txt

# 回到项目根目录
cd ..
```

#### 配置 Fay 的 LLM

Fay 通过 `system.conf` 配置 LLM。首次启动时会从配置中心拉取默认配置，你也可以手动创建 `Fay/system.conf`：

```ini
[key]
# 使用 Ollama 本地模型
gpt_base_url = http://localhost:11434/v1
gpt_model_engine = llama3.2
gpt_api_key = sk-ollama

# 或使用云端 API（如 SiliconFlow）
# gpt_base_url = https://api.siliconflow.cn/v1
# gpt_model_engine = zai-org/GLM-4.6
# gpt_api_key = sk-your-api-key
```

如果使用 Ollama，确保先安装并拉取模型：
```bash
# 安装 Ollama 后
ollama pull llama3.2
```

### 第四步：安装 MuseTalk

MuseTalk 是音频驱动的唇形同步模型，需要独立的 Python 环境（Python 3.10）。

```powershell
# 进入 MuseTalk 目录
cd MuseTalk

# 创建独立虚拟环境（必须使用 Python 3.10）
# 如果系统默认不是 3.10，请指定路径或使用 conda
python -m venv venv
# 或: conda create -n musetalk python=3.10 && conda activate musetalk

# 激活虚拟环境
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Linux/Mac:
# source venv/bin/activate
```

#### 4.1 安装 PyTorch（带 CUDA 支持）

根据你的 CUDA 版本选择对应的 PyTorch：

```bash
# CUDA 11.8（推荐）
pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1
# pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu121

# 仅 CPU（非常慢，不推荐）
# pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cpu
```

验证 CUDA：
```bash
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

#### 4.2 安装 MuseTalk 基础依赖

```bash
pip install -r requirements.txt
```

#### 4.3 安装 OpenMMLab 生态

MuseTalk 依赖 mmcv、mmdet、mmpose 进行人脸检测和姿态估计：

```bash
pip install --no-cache-dir -U openmim
mim install mmengine
mim install "mmcv==2.0.1"
mim install "mmdet==3.1.0"
mim install "mmpose==1.1.0"
```

> **Windows 常见问题**：如果 `mmcv` 编译失败，尝试 `pip install mmcv-lite>=2.0.1` 作为替代。

#### 4.4 下载模型权重

确保以下模型已下载到 `MuseTalk/models/` 目录：

```
MuseTalk/models/
├── musetalkV15/          # MuseTalk v1.5 模型（推荐）
│   ├── unet.pth
│   └── musetalk.json
├── whisper/              # Whisper 音频编码器
├── dwpose/               # 人体姿态检测
├── sd-vae/               # Stable Diffusion VAE
├── face-parse-bisent/    # 人脸解析
└── syncnet/              # 音视频同步网络
```

模型下载方式参考 [MuseTalk 官方仓库](https://github.com/TMElyralab/MuseTalk)。

```bash
# 回到项目根目录
cd ..
```

### 第五步：安装后端依赖

```powershell
# 激活 Fay 的虚拟环境（后端与 Fay 共用环境）
cd Fay
.\.venv\Scripts\Activate.ps1
cd ..

# 安装后端依赖
cd backend
pip install -r requirements.txt

# Edge-TTS（默认 TTS 引擎，需单独安装）
pip install edge-tts

cd ..
```

### 第六步：配置环境变量

```powershell
# 复制环境变量模板
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/Mac
```

编辑 `.env`，关键配置项：

```ini
# 后端端口
BACKEND_PORT=8002

# MuseTalk Python 解释器路径（指向 MuseTalk 的独立 venv）
MUSETALK_PYTHON_PATH=C:\你的路径\fay\MuseTalk\venv\Scripts\python.exe

# GPU 半精度加速（有 GPU 设为 true）
MUSETALK_USE_FLOAT16=true

# MuseTalk 模型版本
MUSETALK_MODEL_VERSION=v15
```

## 开始使用

### 启动顺序

必须按以下顺序启动三个服务，每个服务在**独立的终端窗口**中运行：

#### 终端 1：启动 LLM 服务（如使用 Ollama）

```bash
ollama serve
```

Ollama 默认监听 `http://localhost:11434`。如果已经作为系统服务运行则跳过此步。

#### 终端 2：启动 Fay

```powershell
cd Fay
.\.venv\Scripts\Activate.ps1
python main.py start
```

等待看到以下日志表示 Fay 启动成功：
```
[系统] 服务启动完成!
Uvicorn running on http://0.0.0.0:8765
```

Fay 提供的服务端口：
- **HTTP API**: `http://127.0.0.1:5000`（LLM 对话接口）
- **WebSocket**: `ws://127.0.0.1:10002`（数字人消息接口）
- **MCP SSE**: `http://127.0.0.1:8765`（MCP 服务）

#### 终端 3：启动后端

```powershell
cd Fay
.\.venv\Scripts\Activate.ps1
cd ..\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
```

等待看到以下日志：
```
服务初始化完成（含 MuseTalk 渲染器 WS 客户端）
Application startup complete.
Uvicorn running on http://0.0.0.0:8002
已连接 Fay WebSocket 10002          ← 确认 Fay 已连接
```

### 使用流程

1. **打开浏览器**访问 `http://localhost:8002`

2. **上传头像视频**：点击上传区域选择一段包含正脸的 MP4 视频（这将作为数字人的形象素材）

3. **等待预处理完成**：上传后系统会自动提取视频帧和元数据

4. **输入文本**：在文本框中输入想说的话（如"你好，请介绍你自己"）

5. **点击提交处理**：系统自动执行完整流程：
   - 将文本发送给 Fay → Fay 调用 LLM 生成回复
   - 回复文本通过 TTS 合成为 WAV 音频
   - MuseTalk 使用音频 + 头像视频生成口型同步视频
   - 前端自动加载并播放生成的视频

6. **查看结果**：页面右侧会显示回复文本和生成的视频

> **首次推理耗时较长**（5-7 分钟），因为需要加载模型到 GPU。后续调用会快很多（1-2 分钟）。

## API 接口

启动后访问 `http://localhost:8002/docs` 查看完整 Swagger 文档。

主要接口：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health/` | GET | 健康检查，返回各服务状态 |
| `/api/avatars/upload` | POST | 上传 MP4 头像视频 |
| `/api/avatars/{id}/info` | GET | 查询头像信息 |
| `/api/conversations/reply` | POST | 发送文本，获取回复+音频+视频 |
| `/api/conversations/reply-stream` | POST | 流式回复 |
| `/api/renderer/latest` | GET | 查询最近一次 WS 渲染结果 |
| `/api/renderer/set-default-avatar` | POST | 设置默认头像 |
| `/api/tasks/{id}/status` | GET | 查询任务状态 |

### 对话 API 示例

```bash
curl -X POST http://localhost:8002/api/conversations/reply \
  -H "Content-Type: application/json" \
  -d '{"text": "你好", "username": "User", "avatar_id": "your_avatar_id"}'
```

## 目录结构

```
fay/
├── .env                    # 环境变量配置
├── README.md               # 英文说明（默认）
├── README.zh-CN.md         # 中文说明
├── CLAUDE.md               # AI 助手配置说明
├── backend/                # 后端服务 (FastAPI)
│   ├── app/
│   │   ├── main.py         # 入口，服务初始化
│   │   ├── config.py       # 配置管理
│   │   ├── api/            # API 路由
│   │   │   ├── health.py
│   │   │   ├── avatars.py
│   │   │   ├── conversations.py
│   │   │   └── renderer.py
│   │   └── services/       # 业务服务
│   │       ├── fay_client.py           # Fay HTTP 客户端
│   │       ├── tts_service.py          # TTS 语音合成
│   │       ├── musetalk_service.py     # MuseTalk 推理
│   │       ├── musetalk_renderer_ws.py # WS 皮肤客户端
│   │       ├── avatar_service.py       # 头像管理
│   │       └── job_service.py          # 任务队列
│   └── requirements.txt
├── frontend/               # 前端 (HTML/CSS/JS)
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── Fay/                    # [需单独 clone] Fay 数字人框架
├── MuseTalk/               # [需单独 clone] MuseTalk 唇形同步
├── data/                   # 运行时数据
│   ├── uploads/            # 用户上传的原始文件
│   ├── avatars/            # 预处理后的头像数据
│   ├── audio/              # TTS 生成的音频
│   ├── videos/             # MuseTalk 生成的视频
│   └── temp/               # 临时文件
├── tests/                  # 测试脚本
└── scripts/                # 工具脚本
```

## 配置说明

### TTS 引擎选择

在 `.env` 中设置 `TTS_ENGINE`：

| 引擎 | 值 | 说明 |
|------|---|------|
| Edge-TTS | `edge_tts` | 微软在线语音合成，免费，质量好（默认） |
| CosyVoice | `cosy_voice` | 腾讯开源模型，需本地部署 |
| VITS | `vits` | 本地模型，需下载权重 |
| Mock | `mock` | 生成静音占位音频，仅用于测试 |

### MuseTalk 参数调优

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MUSETALK_MODEL_VERSION` | `v15` | 模型版本，v15 质量更好 |
| `MUSETALK_USE_FLOAT16` | `true` | GPU 半精度加速，减少显存占用 |
| `MUSETALK_BBOX_SHIFT` | `0` | 人脸边界框偏移，调整嘴部位置 |
| `MUSETALK_FPS` | `25` | 输出视频帧率 |

## 故障排除

### Fay 回复超时（返回模拟回复）

Fay 调用 LLM 可能耗时较长（尤其是云端 API），如果后端日志显示 `Fay API 调用异常`：
- 检查 `backend/app/config.py` 中 `FAY_TIMEOUT` 的值（默认 120 秒）
- 云端 LLM 首次调用可能需要更长时间，可适当增大超时

### MuseTalk 报错 "DLL load failed"

PyTorch 安装损坏或 CUDA 版本不匹配：
```bash
cd MuseTalk
.\venv\Scripts\Activate.ps1
pip install torch==2.0.1+cu118 --index-url https://download.pytorch.org/whl/cu118 --force-reinstall --no-deps
```

验证修复：
```bash
python -c "import torch; print(torch.cuda.is_available())"
```

### MuseTalk 推理非常慢

- 确认 `MUSETALK_USE_FLOAT16=true`
- 确认 PyTorch 检测到 GPU：`torch.cuda.is_available() == True`
- 首次推理需加载模型（5-7 分钟），后续会快很多
- CPU 推理可能需要 10 分钟以上，强烈建议使用 GPU

### 头像上传后 MuseTalk 被跳过

MuseTalk 只接受视频文件（`.mp4`、`.avi`、`.mov` 等），不接受图片。确保上传的是 MP4 视频文件。

### Fay WebSocket 10002 连接失败

后端日志显示 `Fay WebSocket 连接失败`：
- 确认 Fay 已启动且 10002 端口可用
- 后端会自动重连，启动 Fay 后即可恢复

### 清除 Fay 对话记忆

如果想让 Fay 忘掉之前的对话：
```powershell
# 先停止 Fay，然后删除记忆目录
Remove-Item "Fay/memory" -Recurse -Force
```

## 许可证

本项目基于 MIT 许可证开源，具体组件请参考各自项目的许可证。

## 致谢

- [Fay 数字人框架](https://github.com/TheRamU/Fay)
- [MuseTalk](https://github.com/TMElyralab/MuseTalk)
