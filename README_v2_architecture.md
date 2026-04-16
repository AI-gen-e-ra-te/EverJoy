# DigiPeople Core — 架构说明（v1 直连 vs v2 Fay WS 皮肤客户端）

## 两版架构对比

### v1 直连编排版（conversations.py）

```
前端 -> POST /api/conversations/reply
           |
           v
     后端 conversations.py 编排:
       1. 调 Fay HTTP API (5000) 获取 LLM 回复文本
       2. 后端自己调 Edge TTS 生成 WAV
       3. 后端调 MuseTalk subprocess 推理
       4. 返回 video_url + audio_url 给前端
```

**特点：**
- 后端负责整个链路编排（LLM → TTS → MuseTalk → 返回）
- 前端发一个请求，等整个流程跑完再拿结果
- TTS 在后端进程内完成，不走 Fay 的 TTS
- 同步阻塞式：请求到返回可能等几分钟（CPU 推理）

### v2 Fay WS 皮肤客户端版（musetalk_renderer_ws.py）

```
用户通过 Fay 自带界面/API 交互
           |
           v
     Fay 框架内部处理:
       1. LLM 对话（Fay 内置，支持 Ollama/vLLM 等）
       2. TTS 合成（Fay 内置，支持多种 TTS 引擎）
       3. 通过 WebSocket 10002 推送 audio 消息
           |
           v
     musetalk_renderer_ws.py（本服务）:
       - 作为 WebSocket 客户端连接 ws://127.0.0.1:10002
       - 注册为 "MuseTalkRenderer" 用户
       - 监听 Topic=human 的 audio/text/question 消息
       - 收到 audio 后自动调用 MuseTalk 生成视频
       - 结果写入 data/videos，前端轮询获取
           |
           v
     前端 (app.js):
       - 每 3s 轮询 GET /api/renderer/latest
       - 发现新结果后自动播放视频
```

**特点：**
- Fay 本身处理 LLM + TTS，我们只负责「皮肤渲染」
- 事件驱动：Fay 推音频，我们异步渲染，前端轮询
- 解耦更彻底：不依赖后端做 TTS，不需要同步等待
- 支持 Fay 的多种交互方式（语音唤醒、文字、MCP 等）

## 新增文件

| 文件 | 作用 |
|------|------|
| `backend/app/services/musetalk_renderer_ws.py` | WebSocket 客户端，连接 Fay 10002，监听 audio 消息触发 MuseTalk |
| `backend/app/api/renderer.py` | 渲染器 REST API：状态查询、avatar 绑定、最新结果 |

## 新增 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/renderer/status` | 渲染器运行状态（连接、是否正在渲染、avatar 绑定等） |
| GET | `/api/renderer/latest` | 最近一次渲染结果（视频 URL、文本、耗时等） |
| GET | `/api/renderer/history?limit=10` | 渲染历史记录 |
| POST | `/api/renderer/bind-avatar` | 将 Fay 用户名绑定到 avatar_id |
| POST | `/api/renderer/set-default-avatar` | 设置默认 avatar_id |

## Fay WebSocket 10002 协议

消息格式（JSON 文本帧）：

```json
{
    "Topic": "human",
    "Data": {
        "Key": "audio",
        "Value": "C:/path/to/audio.wav",
        "HttpValue": "http://127.0.0.1:5000/audio/xxx.wav",
        "Text": "回复文本",
        "Time": 3.5,
        "IsFirst": 1,
        "IsEnd": 1
    },
    "Username": "用户名"
}
```

Key 类型：
- `audio`: Fay TTS 生成的音频（触发 MuseTalk）
- `text`: 回复文本（流式，有 IsFirst/IsEnd）
- `question`: 用户问题
- `log`: 系统日志

## 使用方法

1. 启动 Fay（确保 10002 端口可访问）
2. 启动本后端：`python -m app.main`
3. 前端上传 MP4 → 自动设为默认 avatar
4. 在 Fay 界面或 API 中对话 → Fay 推 audio → 本服务渲染 → 前端自动播放

## 两种模式共存

v1 直连模式（`/api/conversations/reply`）仍然保留，可用于：
- Fay 未启动时的降级方案
- 快速测试 TTS + MuseTalk 链路
- 不需要 Fay 完整框架的场景
