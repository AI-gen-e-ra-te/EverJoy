# Claude 开发配置说明
# 项目目标

这是一个基于 Fay + 本地 LLM + MuseTalk 的网页应用。

## 业务流程
1. 程序启动后，自动启动一个 Web UI。
2. Web UI 支持上传 mp4 视频文件，作为数字人素材。
3. 上传完成后，不做完整模型训练；而是对该人物执行 MuseTalk avatar 预处理，并缓存结果。
4. Web UI 支持输入文本问题。
5. 后端把文本发送给 Fay 的 OpenAI 兼容接口。
6. Fay 使用本地 LLM（优先 Ollama，保留 vLLM 适配位）生成回复。
7. 将 Fay 的回复文本转换为 wav 音频。
8. 将 wav 音频和 avatar 素材交给 MuseTalk 生成说话视频。
9. 前端展示生成的视频，并保留任务状态与错误信息。

## 技术要求
- 后端使用 Python + FastAPI。
- 前端先用最简单的 HTML + JS，不要先引入重型前端框架。
- 必须把 Fay、MuseTalk、TTS、文件存储、任务队列解耦成独立 service。
- 必须优先做 MVP，可跑通单用户单任务流程。
- 所有关键配置从 .env 读取。
- 所有路径、端口、命令都集中在 config.py。
- 优先保证可读性和可维护性。
- 每完成一个阶段，都要更新 README，写清启动步骤和验证方法。
- 每新增功能都补最少可用测试。
- 不要一次性做复杂优化，不要过早引入分布式、消息队列和数据库迁移框架。

## 外部集成约束
- Fay 通过 http://127.0.0.1:5000/v1/chat/completions 交互。
- Fay 将使用本地 LLM。
- MuseTalk 走“上传 mp4 -> avatar 预处理 -> 音频驱动视频生成”的模式。
- 不要把 MuseTalk 设计成“每上传一次视频就完整训练一个模型”。

## 开发步骤
1. 先实现项目骨架和配置系统。
2. 再实现 Web UI 和文件上传。
3. 再实现 avatar 预处理任务。
4. 再实现 Fay client。
5. 再实现 TTS。
6. 再实现 MuseTalk 推理。
7. 再实现前端播放与任务状态轮询。
8. 最后补 README、测试和 docker-compose。

## 输出要求
- 每次动手改代码前，先给出计划。
- 每次改动后，说明改了哪些文件。
- 能运行命令时就主动运行测试或最小验证命令。
- 遇到不确定项时，优先给出两个可选方案并推荐一个。
## 开发环境配置

### Python 环境
建议使用 Python 3.10，创建虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows
```

### 依赖安装
1. 安装后端依赖：
```bash
cd backend
pip install -r requirements.txt
```

2. 安装 Fay 依赖：
```bash
cd ../Fay
pip install -r requirements.txt
```

3. 安装 MuseTalk 依赖：
```bash
cd ../MuseTalk
pip install -r requirements.txt
pip install --no-cache-dir -U openmim
mim install mmengine
mim install "mmcv==2.0.1"
mim install "mmdet==3.1.0"
mim install "mmpose==1.1.0"
```

### 模型文件下载
确保以下模型文件已下载并放置在正确位置：

1. **MuseTalk 模型**:
   - `./MuseTalk/models/musetalkV15/` (推荐版本)
   - `./MuseTalk/models/musetalk/` (1.0版本)

2. **辅助模型**:
   - `./MuseTalk/models/sd-vae/` (VAE模型)
   - `./MuseTalk/models/whisper/` (音频编码器)
   - `./MuseTalk/models/dwpose/` (姿态检测)
   - `./MuseTalk/models/syncnet/` (同步网络)
   - `./MuseTalk/models/face-parse-bisent/` (人脸解析)

## 配置文件说明

### 环境变量 (.env)
```env
# 后端服务配置
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# Fay 服务配置
FAY_HOST=127.0.0.1
FAY_PORT=10002
FAY_WS_URL=ws://127.0.0.1:10002

# MuseTalk 配置
MUSETALK_PATH=./MuseTalk
MUSETALK_MODEL_VERSION=v15  # v15 或 v1
MUSETALK_USE_FLOAT16=true

# 路径配置
DATA_DIR=./data
AVATAR_DIR=./data/avatars
AUDIO_DIR=./data/audio
VIDEO_DIR=./data/videos
UPLOAD_DIR=./data/uploads

# 开发模式
DEBUG=true
LOG_LEVEL=INFO
```

### 后端配置 (backend/app/config.py)
主要配置项包括：
- 服务端口和主机
- Fay WebSocket 连接参数
- MuseTalk 执行路径和参数
- 文件存储路径
- 任务队列配置

## 启动顺序

1. **启动 Fay 服务**:
   ```bash
   cd ./Fay
   python main.py start -config_center d19f7b0a-2b8a-4503-8c0d-1a587b90eb69
   ```

2. **启动后端服务**:
   ```bash
   cd ./backend
   python -m app.main
   ```

3. **启动前端服务**:
   打开浏览器访问 `http://localhost:8000`

## 开发注意事项

### 1. 路径处理
- 所有路径使用绝对路径，避免相对路径问题
- Windows 系统注意路径分隔符 (`\` vs `/`)
- 使用 `os.path.join()` 构建跨平台路径

### 2. 异步处理
- Fay WebSocket 通信需要异步处理
- MuseTalk 推理可能耗时，使用后台任务或消息队列
- 视频生成使用单独进程，避免阻塞主线程

### 3. 错误处理
- WebSocket 连接需要重试机制
- MuseTalk 调用需要超时控制
- 文件操作需要异常捕获

### 4. 资源管理
- GPU 内存需要监控和管理
- 临时文件需要及时清理
- 长时间运行需要日志轮转

## 测试要点

### 单元测试
```bash
cd backend
python -m pytest tests/
```

### 集成测试
1. 测试 Fay WebSocket 连接
2. 测试 MuseTalk 推理流程
3. 测试完整对话流程

### 性能测试
1. 音频生成延迟
2. 视频生成帧率
3. 并发处理能力

## 调试技巧

### 日志查看
```bash
# 查看后端日志
tail -f backend/logs/app.log

# 查看 Fay 日志
tail -f ./Fay/logs/*.txt

# 查看 MuseTalk 输出
tail -f ./MuseTalk/results/*.log
```

### WebSocket 调试
使用工具如 `wscat` 测试 WebSocket 连接：
```bash
wscat -c ws://127.0.0.1:10002
```

### 视频质量检查
1. 唇形同步准确度
2. 面部表情自然度
3. 音频视频同步性

## 扩展开发

### 添加新功能
1. 在 `backend/app/services/` 添加新服务类
2. 在 `backend/app/api/` 添加新API端点
3. 更新前端界面 `frontend/`

### 集成其他模型
1. 新的 TTS 引擎
2. 新的视觉模型
3. 新的对话模型

## 故障排除

### 常见问题
1. **Fay 无法启动**: 检查 Python 版本和依赖
2. **MuseTalk 模型缺失**: 运行下载脚本或手动下载
3. **WebSocket 连接失败**: 检查端口占用和防火墙
4. **GPU 内存不足**: 降低批量大小或使用 CPU

### 性能优化
1. 启用 MuseTalk 的 float16 模式
2. 使用 Fay 的流式输出
3. 缓存常用资源

## 参考资料
- [Fay 文档](https://qqk9ntwbcit.feishu.cn/wiki/JzMJw7AghiO8eHktMwlcxznenIg)
- [MuseTalk GitHub](https://github.com/TMElyralab/MuseTalk)
- [WebSocket 协议](https://tools.ietf.org/html/rfc6455)