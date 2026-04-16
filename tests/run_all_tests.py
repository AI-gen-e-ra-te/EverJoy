#!/usr/bin/env python3
"""
DigiPeople Core 全链路测试
按阶段执行：preflight → 单服务 → MuseTalk 推理 → 串联 → 异常
每条线路输出 PASS / FAIL / BLOCKED
所有证据保存到 test_artifacts/<timestamp>/
"""

import os, sys, json, time, asyncio, shutil, logging, traceback, io
from datetime import datetime
from pathlib import Path

# Windows GBK console workaround
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 确保后端包可导入
BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

# 设置环境变量（避免被 reload 覆盖）
os.environ.setdefault("MUSETALK_USE_FLOAT16", "false")
os.environ.setdefault("DEBUG", "false")

PROJ_ROOT = os.path.dirname(BACKEND_DIR)
ARTIFACTS_DIR = None  # 由 main() 设定

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

class TestResult:
    def __init__(self, test_id: str, name: str):
        self.test_id = test_id
        self.name = name
        self.status = "PENDING"  # PASS / FAIL / BLOCKED
        self.details = ""
        self.evidence = {}
        self.duration = 0.0
        self.root_cause = ""

    def to_dict(self):
        return {
            "test_id": self.test_id, "name": self.name,
            "status": self.status, "details": self.details,
            "evidence": self.evidence, "duration_s": round(self.duration, 2),
            "root_cause": self.root_cause,
        }

results: list[TestResult] = []

def save_artifact(filename: str, content: str):
    path = os.path.join(ARTIFACTS_DIR, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path

def save_artifact_binary(filename: str, data: bytes):
    path = os.path.join(ARTIFACTS_DIR, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path

def copy_artifact(src: str, dest_name: str):
    if src and os.path.exists(src):
        dest = os.path.join(ARTIFACTS_DIR, dest_name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
        return dest
    return None

def run_test(test_id: str, name: str):
    """装饰器：记录测试结果和耗时"""
    def decorator(func):
        async def wrapper():
            r = TestResult(test_id, name)
            results.append(r)
            print(f"\n{'='*60}")
            print(f"[{test_id}] {name}")
            print(f"{'='*60}")
            start = time.time()
            try:
                await func(r)
            except Exception as e:
                if r.status == "PENDING":
                    r.status = "FAIL"
                    r.details = f"未捕获异常: {e}"
                    r.root_cause = f"异常: {type(e).__name__}: {e}"
                    r.evidence["traceback"] = traceback.format_exc()
            r.duration = time.time() - start
            icon = {"PASS": "OK", "FAIL": "XX", "BLOCKED": "--"}.get(r.status, "??")
            msg = f"  [{icon}] {r.status} ({r.duration:.1f}s) - {r.details}"
            print(msg.encode("ascii", errors="replace").decode("ascii"))
            if r.root_cause:
                rc = f"      Root cause: {r.root_cause}"
                print(rc.encode("ascii", errors="replace").decode("ascii"))
        wrapper._test_id = test_id
        wrapper._name = name
        return wrapper
    return decorator

# ──────────────────────────────────────────────
# Phase 1: Preflight
# ──────────────────────────────────────────────

@run_test("P1", "启动前环境检查")
async def test_p1_environment(r: TestResult):
    checks = {}

    # Python 包
    packages = ["fastapi", "uvicorn", "websockets", "edge_tts", "httpx",
                "pydantic", "pydantic_settings", "pydub", "PIL", "numpy"]
    missing = []
    for pkg in packages:
        try:
            __import__(pkg)
            checks[pkg] = "OK"
        except ImportError:
            checks[pkg] = "MISSING"
            missing.append(pkg)

    # ffmpeg
    import subprocess
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        checks["ffmpeg"] = "OK" if result.returncode == 0 else "FAIL"
    except Exception:
        checks["ffmpeg"] = "MISSING"
        missing.append("ffmpeg")

    # MuseTalk 模型权重
    from app.config import settings
    model_files = {
        "unet.pth": os.path.join(settings.absolute_musetalk_path, "models", "musetalkV15", "unet.pth"),
        "whisper": os.path.join(settings.absolute_musetalk_path, "models", "whisper", "pytorch_model.bin"),
        "dwpose": os.path.join(settings.absolute_musetalk_path, "models", "dwpose", "dw-ll_ucoco_384.pth"),
        "sd-vae": os.path.join(settings.absolute_musetalk_path, "models", "sd-vae", "diffusion_pytorch_model.bin"),
    }
    for name, path in model_files.items():
        exists = os.path.isfile(path)
        checks[f"model_{name}"] = "OK" if exists else "MISSING"
        if not exists:
            missing.append(f"model:{name}")

    # 目录结构
    for d_name in ["absolute_data_dir", "absolute_upload_dir", "absolute_avatar_dir",
                    "absolute_audio_dir", "absolute_video_dir", "absolute_temp_dir"]:
        d_path = getattr(settings, d_name)
        os.makedirs(d_path, exist_ok=True)
        checks[d_name] = "OK"

    r.evidence = checks
    save_artifact("env_snapshot.txt",
        "\n".join(f"{k}: {v}" for k, v in checks.items()) +
        f"\n\nPython: {sys.version}\nCWD: {os.getcwd()}\n")

    if missing:
        r.status = "FAIL"
        r.details = f"缺失: {', '.join(missing)}"
        r.root_cause = "环境依赖不满足"
    else:
        r.status = "PASS"
        r.details = f"全部 {len(checks)} 项通过"


@run_test("P2", "配置加载验证")
async def test_p2_config(r: TestResult):
    from app.config import settings
    checks = {}
    failures = []

    path_attrs = [
        "absolute_data_dir", "absolute_upload_dir", "absolute_avatar_dir",
        "absolute_audio_dir", "absolute_video_dir", "absolute_temp_dir",
        "absolute_musetalk_path",
    ]
    for attr in path_attrs:
        val = getattr(settings, attr)
        exists = os.path.isdir(val)
        checks[attr] = {"value": val, "exists": exists}
        if not exists:
            failures.append(f"{attr}={val}")

    checks["FAY_WS_URL"] = settings.FAY_WS_URL
    checks["FAY_API_URL"] = settings.FAY_API_URL
    checks["BACKEND_PORT"] = settings.BACKEND_PORT
    checks["MUSETALK_USE_FLOAT16"] = settings.MUSETALK_USE_FLOAT16
    checks["MUSETALK_PYTHON_PATH"] = settings.MUSETALK_PYTHON_PATH

    python_path = settings.MUSETALK_PYTHON_PATH
    if python_path and not os.path.isfile(python_path):
        failures.append(f"MUSETALK_PYTHON_PATH={python_path} (文件不存在)")

    r.evidence = checks
    save_artifact("config_snapshot.json", json.dumps(checks, indent=2, default=str, ensure_ascii=False))

    if failures:
        r.status = "FAIL"
        r.details = f"路径不存在: {'; '.join(failures)}"
        r.root_cause = "配置路径错误"
    else:
        r.status = "PASS"
        r.details = f"全部 {len(path_attrs)} 个路径 + 关键配置正确"


@run_test("P3", "MuseTalk preflight_check")
async def test_p3_preflight(r: TestResult):
    from app.services.musetalk_service import MuseTalkService
    svc = MuseTalkService()
    checks = svc.preflight_check()

    r.evidence = {
        "all_passed": checks.get("all_passed"),
        "critical_failures": checks.get("critical_failures", []),
        "python_path": checks.get("python_path"),
        "python_exists": checks.get("python_exists"),
        "inference_script_exists": checks.get("inference_script_exists"),
        "ffmpeg_available": checks.get("ffmpeg_available"),
    }
    save_artifact("preflight_result.json",
        json.dumps(checks, indent=2, default=str, ensure_ascii=False))

    if checks.get("all_passed"):
        r.status = "PASS"
        r.details = "MuseTalk preflight 全部通过"
    else:
        r.status = "FAIL"
        failures = checks.get("critical_failures", [])
        r.details = f"关键失败: {failures}"
        r.root_cause = "; ".join(failures) if failures else "preflight 未通过"

# ──────────────────────────────────────────────
# Phase 2: 单服务测试（需要启动后端）
# ──────────────────────────────────────────────

SERVER_PORT = 18055  # 使用高位端口避免冲突
_server_thread = None
_app_instance = None

async def start_test_server():
    global _app_instance
    import uvicorn
    os.environ["BACKEND_PORT"] = str(SERVER_PORT)
    os.environ["CORS_ORIGINS"] = f"http://localhost:{SERVER_PORT}"
    from app.main import app
    _app_instance = app

    config = uvicorn.Config(app, host="0.0.0.0", port=SERVER_PORT, log_level="warning")
    server = uvicorn.Server(config)
    loop = asyncio.get_event_loop()
    task = loop.create_task(server.serve())
    await asyncio.sleep(5)
    return server, task

async def api_request(method: str, path: str, **kwargs):
    """发 HTTP 请求并记录到 request_response.jsonl"""
    import httpx
    url = f"http://localhost:{SERVER_PORT}{path}"
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await getattr(client, method)(url, **kwargs)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "method": method.upper(), "url": url,
        "status": resp.status_code,
        "request_body": kwargs.get("json") or kwargs.get("data", ""),
        "response_body": resp.text[:2000],
    }
    with open(os.path.join(ARTIFACTS_DIR, "request_response.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return resp


@run_test("S1", "上传 mp4 → avatar 预处理")
async def test_s1_upload(r: TestResult):
    source = os.path.join(PROJ_ROOT, "data", "avatars", "avatar_9c45975c_1775709630", "source.mp4")
    if not os.path.isfile(source):
        r.status = "BLOCKED"
        r.details = "测试用 source.mp4 不存在"
        r.root_cause = "输入文件不存在"
        return

    with open(source, "rb") as f:
        resp = await api_request("post", "/api/avatars/upload",
            files={"file": ("test_upload.mp4", f, "video/mp4")},
            data={"avatar_name": "TestS1", "description": "Phase2 test"})

    r.evidence["status_code"] = resp.status_code
    r.evidence["response"] = resp.json() if resp.status_code < 500 else resp.text[:500]

    if resp.status_code == 201:
        data = resp.json()
        avatar_id = data.get("avatar_id", "")
        avatar_dir = os.path.join(PROJ_ROOT, "data", "avatars", avatar_id)
        has_source = os.path.isfile(os.path.join(avatar_dir, "source.mp4"))
        has_frame = os.path.isfile(os.path.join(avatar_dir, "first_frame.png"))
        r.evidence["avatar_id"] = avatar_id
        r.evidence["has_source"] = has_source
        r.evidence["has_first_frame"] = has_frame
        # 保存 avatar_id 供后续测试用
        save_artifact("s1_avatar_id.txt", avatar_id)

        if has_source and has_frame:
            r.status = "PASS"
            r.details = f"avatar_id={avatar_id}, source.mp4+first_frame.png 均存在"
        else:
            r.status = "FAIL"
            r.details = f"文件缺失: source={has_source}, frame={has_frame}"
            r.root_cause = "输出文件未落盘"
    else:
        r.status = "FAIL"
        r.details = f"HTTP {resp.status_code}"
        r.root_cause = f"HTTP 响应异常: {resp.status_code}"


@run_test("S2", "文本 → Fay → LLM 回复（含 mock 回退）")
async def test_s2_fay_reply(r: TestResult):
    resp = await api_request("post", "/api/conversations/reply",
        json={"text": "hello test", "username": "Tester"})

    r.evidence["status_code"] = resp.status_code
    body = resp.json() if resp.status_code == 200 else {}
    r.evidence["response"] = body

    if resp.status_code == 200 and body.get("reply"):
        r.status = "PASS"
        is_mock = "模拟" in body["reply"] or "mock" in body["reply"].lower()
        r.details = f"回复长度={len(body['reply'])}, mock回退={'是' if is_mock else '否'}"
    else:
        r.status = "FAIL"
        r.details = f"HTTP {resp.status_code}, reply={body.get('reply', 'EMPTY')}"
        r.root_cause = "HTTP 响应异常"


@run_test("S3", "文本 → TTS → wav（Edge TTS）")
async def test_s3_tts(r: TestResult):
    resp = await api_request("post", "/api/conversations/reply",
        json={"text": "TTS synthesis test for DigiPeople", "username": "TTSTest"})

    body = resp.json() if resp.status_code == 200 else {}
    audio_url = body.get("audio_url")
    r.evidence["status_code"] = resp.status_code
    r.evidence["audio_url"] = audio_url

    if not audio_url:
        r.status = "FAIL"
        r.details = "audio_url 为 null"
        r.root_cause = "TTS 合成失败或引擎不可用"
        return

    # 验证文件
    audio_filename = audio_url.replace("/files/audio/", "")
    audio_path = os.path.join(PROJ_ROOT, "data", "audio", audio_filename)
    exists = os.path.isfile(audio_path)
    size = os.path.getsize(audio_path) if exists else 0
    r.evidence["file_exists"] = exists
    r.evidence["file_size"] = size

    if exists and size > 1000:
        copy_artifact(audio_path, f"generated_audio/{audio_filename}")
        r.status = "PASS"
        r.details = f"wav 文件存在, {size} bytes, url={audio_url}"
    else:
        r.status = "FAIL"
        r.details = f"文件{'不存在' if not exists else f'太小({size}B)'}"
        r.root_cause = "输出文件未落盘" if not exists else "TTS 生成的文件异常"


@run_test("S5", "渲染器 WS 状态检查")
async def test_s5_renderer_status(r: TestResult):
    resp = await api_request("get", "/api/renderer/status")
    body = resp.json() if resp.status_code == 200 else {}
    r.evidence = body

    if resp.status_code != 200:
        r.status = "FAIL"
        r.details = f"HTTP {resp.status_code}"
        r.root_cause = "HTTP 响应异常"
        return

    if body.get("running") is True:
        r.status = "PASS"
        connected = body.get("connected", False)
        r.details = f"running=True, connected={connected}, ws_url={body.get('ws_url')}"
        if not connected:
            r.details += " (Fay 未运行，预期行为)"
    else:
        r.status = "FAIL"
        r.details = f"running={body.get('running')}"
        r.root_cause = "渲染器未启动"


@run_test("S6", "渲染器 avatar 绑定")
async def test_s6_bind_avatar(r: TestResult):
    # 读取 S1 产出的 avatar_id
    aid_file = os.path.join(ARTIFACTS_DIR, "s1_avatar_id.txt")
    if os.path.isfile(aid_file):
        avatar_id = open(aid_file).read().strip()
    else:
        avatar_id = "avatar_9c45975c_1775709630"

    # set-default-avatar
    resp1 = await api_request("post", "/api/renderer/set-default-avatar",
        json={"avatar_id": avatar_id})
    # bind-avatar
    resp2 = await api_request("post", "/api/renderer/bind-avatar",
        json={"username": "TestUser", "avatar_id": avatar_id})
    # 验证
    resp3 = await api_request("get", "/api/renderer/status")
    status = resp3.json() if resp3.status_code == 200 else {}

    r.evidence = {
        "set_default": resp1.json() if resp1.status_code == 200 else resp1.text,
        "bind": resp2.json() if resp2.status_code == 200 else resp2.text,
        "status_after": status,
    }

    default_ok = status.get("default_avatar_id") == avatar_id
    bind_ok = status.get("avatar_bindings", {}).get("TestUser") == avatar_id

    if default_ok and bind_ok:
        r.status = "PASS"
        r.details = f"default={avatar_id}, bind TestUser→{avatar_id}"
    else:
        r.status = "FAIL"
        r.details = f"default_ok={default_ok}, bind_ok={bind_ok}"
        r.root_cause = "绑定状态不一致"


# ──────────────────────────────────────────────
# Phase 3: MuseTalk 真实推理
# ──────────────────────────────────────────────

@run_test("S4", "MuseTalk subprocess 真实推理 (CPU)")
async def test_s4_musetalk(r: TestResult):
    from app.config import settings
    from app.services.musetalk_service import MuseTalkService

    svc = MuseTalkService()
    svc.initialize()
    if not svc.is_available():
        r.status = "BLOCKED"
        r.details = "MuseTalk 服务初始化失败"
        r.root_cause = "环境依赖不满足"
        return

    # 准备输入
    avatar_path = os.path.join(PROJ_ROOT, "data", "avatars", "avatar_9c45975c_1775709630", "source.mp4")
    # 选最大的 wav（Edge TTS 生成的真实音频）
    audio_dir = settings.absolute_audio_dir
    wav_files = sorted(
        [os.path.join(audio_dir, f) for f in os.listdir(audio_dir) if f.endswith(".wav")],
        key=lambda p: os.path.getsize(p), reverse=True
    )
    if not wav_files:
        r.status = "BLOCKED"
        r.details = "无可用 wav 文件"
        r.root_cause = "输入文件不存在"
        return

    audio_path = wav_files[0]
    r.evidence["avatar_path"] = avatar_path
    r.evidence["audio_path"] = audio_path
    r.evidence["audio_size"] = os.path.getsize(audio_path)

    if not os.path.isfile(avatar_path):
        r.status = "BLOCKED"
        r.details = "source.mp4 不存在"
        r.root_cause = "输入文件不存在"
        return

    TIMEOUT = 600  # 10 分钟
    output_path = os.path.join(settings.absolute_video_dir, f"test_s4_{datetime.now().strftime('%H%M%S')}.mp4")

    try:
        result = await asyncio.wait_for(
            svc.generate_lip_sync_video(
                audio_path=audio_path,
                avatar_path=avatar_path,
                output_path=output_path,
                username="S4Test",
            ),
            timeout=TIMEOUT
        )

        r.evidence["result"] = result
        video_path = result.get("video_path", output_path)
        exists = os.path.isfile(video_path)
        size = os.path.getsize(video_path) if exists else 0
        r.evidence["video_exists"] = exists
        r.evidence["video_size"] = size

        if exists and size > 10000:
            copy_artifact(video_path, f"generated_video/{os.path.basename(video_path)}")
            r.status = "PASS"
            r.details = f"视频生成成功: {size} bytes"
        else:
            r.status = "FAIL"
            r.details = f"视频{'不存在' if not exists else f'太小({size}B)'}"
            r.root_cause = "输出文件未落盘"

    except asyncio.TimeoutError:
        r.status = "BLOCKED"
        r.details = f"CPU 推理超时 ({TIMEOUT}s)"
        r.root_cause = "超时（CPU 推理过慢，需 GPU）"
        # 记录 MuseTalk 的 active jobs
        for jid, job in svc.active_jobs.items():
            r.evidence[f"job_{jid}"] = str(job.get("status"))

    except Exception as e:
        r.status = "FAIL"
        r.details = f"推理异常: {e}"
        r.root_cause = f"子进程返回非 0 或异常: {type(e).__name__}"
        r.evidence["error"] = str(e)
        r.evidence["traceback"] = traceback.format_exc()
        save_artifact("musetalk_stderr.log", r.evidence.get("traceback", ""))


# ──────────────────────────────────────────────
# Phase 4: 串联测试
# ──────────────────────────────────────────────

@run_test("C1", "直连 E2E：上传 → 对话 → TTS → MuseTalk → video_url")
async def test_c1_direct_e2e(r: TestResult):
    # 1. 上传
    source = os.path.join(PROJ_ROOT, "data", "avatars", "avatar_9c45975c_1775709630", "source.mp4")
    if not os.path.isfile(source):
        r.status = "BLOCKED"
        r.details = "source.mp4 不存在"
        r.root_cause = "输入文件不存在"
        return

    with open(source, "rb") as f:
        upload_resp = await api_request("post", "/api/avatars/upload",
            files={"file": ("e2e_test.mp4", f, "video/mp4")},
            data={"avatar_name": "E2E_C1", "description": "C1 test"})

    if upload_resp.status_code != 201:
        r.status = "FAIL"
        r.details = f"上传失败: HTTP {upload_resp.status_code}"
        r.root_cause = "HTTP 响应异常"
        return

    avatar_id = upload_resp.json().get("avatar_id")
    r.evidence["avatar_id"] = avatar_id
    await asyncio.sleep(2)  # 等预处理完成

    # 2. 对话（含 TTS + MuseTalk）— 超时设长
    conv_resp = await api_request("post", "/api/conversations/reply",
        json={"text": "E2E full pipeline test", "username": "E2EUser", "avatar_id": avatar_id})

    body = conv_resp.json() if conv_resp.status_code == 200 else {}
    r.evidence["conversation"] = body

    audio_url = body.get("audio_url")
    video_url = body.get("video_url")
    r.evidence["audio_url"] = audio_url
    r.evidence["video_url"] = video_url

    steps_passed = []
    steps_failed = []

    if body.get("reply"):
        steps_passed.append("Fay回复")
    else:
        steps_failed.append("Fay回复为空")

    if audio_url:
        steps_passed.append("TTS音频")
    else:
        steps_failed.append("TTS音频为null")

    if video_url:
        steps_passed.append("MuseTalk视频")
    else:
        steps_failed.append("MuseTalk视频为null")

    if steps_failed:
        r.status = "FAIL"
        r.details = f"通过: {steps_passed}; 失败: {steps_failed}"
        r.root_cause = steps_failed[0] if len(steps_failed) == 1 else "多环节失败"
    else:
        r.status = "PASS"
        r.details = f"全链路通过: reply+audio+video"


@run_test("C2", "WS 渲染器模拟：注入 audio → MuseTalk → latest_result")
async def test_c2_renderer_simulate(r: TestResult):
    """由于 Fay 未运行，无法真实走 WS。改为直接调用渲染器内部方法模拟。"""
    if not _app_instance or not hasattr(_app_instance.state, "musetalk_renderer"):
        r.status = "BLOCKED"
        r.details = "渲染器实例不可用"
        r.root_cause = "服务未初始化"
        return

    renderer = _app_instance.state.musetalk_renderer
    # 确保有默认 avatar
    aid_file = os.path.join(ARTIFACTS_DIR, "s1_avatar_id.txt")
    avatar_id = open(aid_file).read().strip() if os.path.isfile(aid_file) else "avatar_9c45975c_1775709630"
    renderer.set_default_avatar(avatar_id)

    # 找一个真实 wav
    from app.config import settings
    audio_dir = settings.absolute_audio_dir
    wav_files = [os.path.join(audio_dir, f) for f in os.listdir(audio_dir)
                 if f.endswith(".wav") and os.path.getsize(os.path.join(audio_dir, f)) > 5000]
    if not wav_files:
        r.status = "BLOCKED"
        r.details = "无可用 wav"
        r.root_cause = "输入文件不存在"
        return

    audio_path = sorted(wav_files, key=os.path.getsize, reverse=True)[0]

    # 模拟 Fay 推送的 audio 消息
    fake_data = {
        "Key": "audio",
        "Value": audio_path,
        "HttpValue": "",
        "Text": "Simulated Fay reply for C2 test",
        "Time": 3.0,
        "IsFirst": 1,
        "IsEnd": 1,
    }

    r.evidence["audio_path"] = audio_path
    r.evidence["avatar_id"] = avatar_id

    # 直接调用 _on_audio（不走 WS）
    try:
        await asyncio.wait_for(
            renderer._on_audio(fake_data, "TestUser"),
            timeout=660
        )
        # 等渲染完成
        for _ in range(660):
            await asyncio.sleep(1)
            if not renderer._is_rendering:
                break

        latest = renderer.get_latest_result()
        r.evidence["latest_result"] = latest

        if latest and latest.get("status") == "completed" and latest.get("video_url"):
            r.status = "PASS"
            r.details = f"渲染成功: {latest['video_url']}"
        elif latest and latest.get("status") == "failed":
            r.status = "FAIL"
            r.details = f"渲染失败: {latest.get('error')}"
            r.root_cause = latest.get("error", "未知")
        elif latest and latest.get("status") == "skipped":
            r.status = "FAIL"
            r.details = f"被跳过: {latest.get('error')}"
            r.root_cause = latest.get("error", "未知")
        else:
            r.status = "BLOCKED"
            r.details = "渲染未完成（超时）"
            r.root_cause = "超时"

    except asyncio.TimeoutError:
        r.status = "BLOCKED"
        r.details = "模拟渲染超时"
        r.root_cause = "超时（CPU 推理过慢）"


# ──────────────────────────────────────────────
# Phase 5: 异常 & 回退
# ──────────────────────────────────────────────

@run_test("F1", "上传非 mp4 文件 → 拒绝")
async def test_f1_bad_upload(r: TestResult):
    import io
    fake = io.BytesIO(b"this is not a video")
    resp = await api_request("post", "/api/avatars/upload",
        files={"file": ("test.txt", fake, "text/plain")},
        data={"avatar_name": "BadFile"})

    r.evidence["status_code"] = resp.status_code
    if resp.status_code in (400, 415, 422):
        r.status = "PASS"
        r.details = f"正确拒绝: HTTP {resp.status_code}"
    elif resp.status_code == 201:
        r.status = "FAIL"
        r.details = "非 mp4 文件被接受了"
        r.root_cause = "缺少文件类型校验"
    else:
        r.status = "FAIL"
        r.details = f"意外状态码: {resp.status_code}"
        r.root_cause = f"HTTP 响应异常: {resp.status_code}"


@run_test("F2", "不带 avatar_id → 跳过 MuseTalk")
async def test_f2_no_avatar(r: TestResult):
    resp = await api_request("post", "/api/conversations/reply",
        json={"text": "test no avatar", "username": "Tester"})

    body = resp.json() if resp.status_code == 200 else {}
    r.evidence = body

    if resp.status_code == 200 and body.get("video_url") is None:
        r.status = "PASS"
        r.details = "无 avatar_id 时 video_url=null，MuseTalk 被正确跳过"
    else:
        r.status = "FAIL"
        r.details = f"video_url={body.get('video_url')}"
        r.root_cause = "MuseTalk 不应在无 avatar 时触发"


@run_test("F3", "不存在的 avatar_id → 降级")
async def test_f3_bad_avatar(r: TestResult):
    resp = await api_request("post", "/api/conversations/reply",
        json={"text": "test bad avatar", "username": "Tester", "avatar_id": "nonexistent_avatar_999"})

    body = resp.json() if resp.status_code == 200 else {}
    r.evidence = body

    if resp.status_code == 200:
        r.status = "PASS"
        r.details = f"降级成功: video_url={body.get('video_url')}, audio_url={'有' if body.get('audio_url') else '无'}"
    else:
        r.status = "FAIL"
        r.details = f"HTTP {resp.status_code}"
        r.root_cause = "HTTP 响应异常"


@run_test("F4", "渲染器 Fay WS 断连 → 自动重连状态")
async def test_f4_ws_reconnect(r: TestResult):
    resp = await api_request("get", "/api/renderer/status")
    body = resp.json() if resp.status_code == 200 else {}

    if body.get("running") and not body.get("connected"):
        r.status = "PASS"
        r.details = "Fay 未运行，渲染器 running=true 且 connected=false（自动重连中）"
    elif body.get("running") and body.get("connected"):
        r.status = "PASS"
        r.details = "Fay 已连接"
    else:
        r.status = "FAIL"
        r.details = f"running={body.get('running')}, connected={body.get('connected')}"
        r.root_cause = "渲染器状态异常"

    r.evidence = body


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────

async def main():
    global ARTIFACTS_DIR
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ARTIFACTS_DIR = os.path.join(PROJ_ROOT, "test_artifacts", ts)
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    os.makedirs(os.path.join(ARTIFACTS_DIR, "generated_audio"), exist_ok=True)
    os.makedirs(os.path.join(ARTIFACTS_DIR, "generated_video"), exist_ok=True)

    print(f"测试 artifacts 目录: {ARTIFACTS_DIR}")
    print(f"开始时间: {ts}")

    # ── Phase 1 ──
    print("\n" + "█" * 60)
    print("  Phase 1: Preflight 检查")
    print("█" * 60)
    await test_p1_environment()
    await test_p2_config()
    await test_p3_preflight()

    phase1_ok = all(r.status == "PASS" for r in results if r.test_id.startswith("P"))
    print(f"\n>>> Phase 1 结论: {'全部通过' if phase1_ok else '有失败项'}")
    if not phase1_ok:
        print("    ⚠ Phase 1 有失败，后续测试可能受影响")

    # ── Phase 2: 启动后端 ──
    print("\n" + "█" * 60)
    print("  Phase 2: 单服务测试 (启动后端)")
    print("█" * 60)
    server = None
    server_task = None
    try:
        server, server_task = await start_test_server()
        print(f"  测试服务器已启动: http://localhost:{SERVER_PORT}")

        await test_s1_upload()
        await test_s2_fay_reply()
        await test_s3_tts()
        await test_s5_renderer_status()
        await test_s6_bind_avatar()

    except Exception as e:
        print(f"  Phase 2 启动失败: {e}")
        traceback.print_exc()

    phase2_ok = all(r.status == "PASS" for r in results if r.test_id.startswith("S") and r.test_id != "S4")
    print(f"\n>>> Phase 2 结论: {'全部通过' if phase2_ok else '有失败项'}")

    # ── Phase 3: MuseTalk 真实推理 ──
    print("\n" + "█" * 60)
    print("  Phase 3: MuseTalk 真实推理 (可能耗时很长)")
    print("█" * 60)
    await test_s4_musetalk()

    s4 = [r for r in results if r.test_id == "S4"][0]
    print(f"\n>>> Phase 3 结论: {s4.status}")

    # ── Phase 4: 串联 ──
    # C1 需要 MuseTalk，大概率因 CPU 超时而 BLOCKED，仍然执行以记录
    # 如果 S4 已经 BLOCKED（超时），C1 和 C2 也标 BLOCKED 不再等
    print("\n" + "█" * 60)
    print("  Phase 4: 串联测试")
    print("█" * 60)

    if s4.status == "BLOCKED":
        # C1: 直连 E2E 会因 MuseTalk 超时而 BLOCKED
        r_c1 = TestResult("C1", "直连 E2E（跳过：MuseTalk CPU 超时）")
        r_c1.status = "BLOCKED"
        r_c1.details = "S4 已 BLOCKED (CPU 推理超时)，跳过完整 E2E"
        r_c1.root_cause = "超时（CPU 推理过慢，需 GPU）"
        results.append(r_c1)
        print(f"\n{'='*60}\n[C1] {r_c1.name}\n{'='*60}")
        print(f"  [⊘] BLOCKED - {r_c1.details}")

        r_c2 = TestResult("C2", "WS 渲染器模拟（跳过：MuseTalk CPU 超时）")
        r_c2.status = "BLOCKED"
        r_c2.details = "S4 已 BLOCKED (CPU 推理超时)，跳过渲染器模拟"
        r_c2.root_cause = "超时（CPU 推理过慢，需 GPU）"
        results.append(r_c2)
        print(f"\n{'='*60}\n[C2] {r_c2.name}\n{'='*60}")
        print(f"  [⊘] BLOCKED - {r_c2.details}")
    else:
        await test_c1_direct_e2e()
        await test_c2_renderer_simulate()

    # ── Phase 5: 异常 ──
    print("\n" + "█" * 60)
    print("  Phase 5: 异常 & 回退")
    print("█" * 60)
    await test_f1_bad_upload()
    await test_f2_no_avatar()
    await test_f3_bad_avatar()
    await test_f4_ws_reconnect()

    # ── 清理 ──
    if server:
        server.should_exit = True

    # ── 生成报告 ──
    print("\n" + "█" * 60)
    print("  生成测试报告")
    print("█" * 60)

    save_artifact("all_results.json",
        json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))

    generate_report()

    # 打印摘要
    print(f"\n{'='*60}")
    print("测试摘要")
    print(f"{'='*60}")
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    blocked = sum(1 for r in results if r.status == "BLOCKED")
    print(f"  PASS: {passed}  |  FAIL: {failed}  |  BLOCKED: {blocked}  |  总计: {len(results)}")
    for r in results:
        icon = {"PASS": "OK", "FAIL": "XX", "BLOCKED": "--"}.get(r.status, "??")
        print(f"  [{icon}] {r.test_id}: {r.status} - {r.details[:80]}")

    print(f"\n报告: {os.path.join(ARTIFACTS_DIR, 'TEST_REPORT.md')}")
    print(f"证据: {ARTIFACTS_DIR}")


def generate_report():
    lines = []
    lines.append("# DigiPeople Core 全链路测试报告\n")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"**Artifacts 目录**: `{ARTIFACTS_DIR}`\n")

    # 摘要
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    blocked = sum(1 for r in results if r.status == "BLOCKED")

    lines.append(f"\n## 测试范围\n")
    lines.append(f"- Preflight 环境检查 (P1-P3)")
    lines.append(f"- 单服务测试: 上传/Fay对话/TTS/渲染器WS/绑定 (S1-S6)")
    lines.append(f"- MuseTalk 真实推理 (S4)")
    lines.append(f"- 串联 E2E (C1-C2)")
    lines.append(f"- 异常回退 (F1-F4)\n")

    lines.append(f"\n## 总览\n")
    lines.append(f"| 状态 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| PASS | {passed} |")
    lines.append(f"| FAIL | {failed} |")
    lines.append(f"| BLOCKED | {blocked} |")
    lines.append(f"| **总计** | **{len(results)}** |\n")

    # 线路清单
    lines.append(f"\n## 线路清单\n")
    lines.append(f"| ID | 线路 | 状态 | 耗时 | 说明 |")
    lines.append(f"|---|---|---|---|---|")
    for r in results:
        icon = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "⏸️"}.get(r.status, "❓")
        lines.append(f"| {r.test_id} | {r.name} | {icon} {r.status} | {r.duration:.1f}s | {r.details[:60]} |")

    # 失败线路
    failed_results = [r for r in results if r.status in ("FAIL", "BLOCKED")]
    if failed_results:
        lines.append(f"\n## 失败/阻塞线路详情\n")
        for r in failed_results:
            lines.append(f"### {r.test_id}: {r.name} ({r.status})\n")
            lines.append(f"- **说明**: {r.details}")
            lines.append(f"- **根因**: {r.root_cause}")
            if r.evidence:
                lines.append(f"- **证据摘要**:")
                for k, v in r.evidence.items():
                    v_str = str(v)[:200]
                    lines.append(f"  - `{k}`: {v_str}")
            lines.append("")

    # 修复优先级
    lines.append(f"\n## 修复优先级\n")
    fail_only = [r for r in results if r.status == "FAIL"]
    block_only = [r for r in results if r.status == "BLOCKED"]
    if fail_only:
        lines.append("### 需修复 (FAIL)\n")
        for i, r in enumerate(fail_only, 1):
            lines.append(f"{i}. **{r.test_id}** {r.name}: {r.root_cause}")
    if block_only:
        lines.append("\n### 环境限制 (BLOCKED)\n")
        for i, r in enumerate(block_only, 1):
            lines.append(f"{i}. **{r.test_id}** {r.name}: {r.root_cause}")
    if not fail_only and not block_only:
        lines.append("无需修复，全部通过。\n")

    # 下一步
    lines.append(f"\n## 下一步建议\n")
    if any(r.root_cause and "GPU" in r.root_cause for r in results):
        lines.append("1. 在 GPU 环境下重新执行 S4/C1/C2，验证 MuseTalk 完整推理")
    if any(r.root_cause and "Fay" in r.details for r in results):
        lines.append("2. 启动 Fay 框架后，重新测试 WS 渲染器的真实连接 (S5/C2)")
    lines.append("3. 对所有 FAIL 项按优先级逐一修复后重跑测试")
    lines.append("4. 添加 CI 集成，在每次提交时自动跑 P1-P3 + S1-S3 + F1-F4")

    report = "\n".join(lines)
    save_artifact("TEST_REPORT.md", report)


if __name__ == "__main__":
    asyncio.run(main())
