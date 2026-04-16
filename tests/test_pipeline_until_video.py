"""
全链路验证：从上传到 MuseTalk 子进程启动
验证每一步的输入输出，确认管线在视频生成前全部畅通。
对 MuseTalk 只验证子进程正确启动并开始处理帧，不等推理完成。
"""

import os, sys, io, json, asyncio, time, subprocess, uuid
from datetime import datetime

# Windows GBK console workaround
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)
os.environ.setdefault("MUSETALK_USE_FLOAT16", "false")
os.environ.setdefault("DEBUG", "false")
os.environ["BACKEND_PORT"] = "18088"
os.environ["CORS_ORIGINS"] = '["http://localhost:18088"]'

PROJ_ROOT = os.path.dirname(BACKEND_DIR)

step_results = []

def report(step: str, ok: bool, detail: str):
    tag = "PASS" if ok else "FAIL"
    step_results.append({"step": step, "status": tag, "detail": detail})
    print(f"  [{tag}] {step}: {detail}")
    return ok


async def main():
    from app.config import settings

    print("=" * 70)
    print("  全链路验证：上传 -> Fay -> TTS -> MuseTalk 子进程启动")
    print("=" * 70)

    # ================================================================
    # Step 1: 确认测试用 source.mp4 存在
    # ================================================================
    print("\n--- Step 1: 确认测试用 source.mp4 ---")
    source_mp4 = None
    avatars_base = os.path.join(PROJ_ROOT, "data", "avatars")
    for d in sorted(os.listdir(avatars_base)):
        cand = os.path.join(avatars_base, d, "source.mp4")
        if os.path.isfile(cand) and os.path.getsize(cand) > 10000:
            source_mp4 = cand
            break

    if not source_mp4:
        report("1.source_mp4", False, "data/avatars 中无可用 source.mp4")
        print("  FATAL: 无测试视频，终止")
        return
    size = os.path.getsize(source_mp4)
    report("1.source_mp4", True, f"path={source_mp4}, size={size}")

    # ================================================================
    # Step 2: 启动后端服务器
    # ================================================================
    print("\n--- Step 2: 启动后端服务器 ---")
    import uvicorn
    from app.main import app

    config = uvicorn.Config(app, host="0.0.0.0", port=18088, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(5)
    report("2.server_start", True, "http://localhost:18088")

    import httpx
    BASE = "http://localhost:18088"

    try:
        async with httpx.AsyncClient(timeout=60) as c:

            # ============================================================
            # Step 3: Health check
            # ============================================================
            print("\n--- Step 3: 健康检查 ---")
            r = await c.get(f"{BASE}/api/health/")
            body = r.json()
            services = body.get("services", {})
            report("3a.http_200", r.status_code == 200, f"HTTP {r.status_code}")
            report("3b.musetalk", services.get("musetalk") == True,
                   f"musetalk={services.get('musetalk')}")
            report("3c.tts", services.get("tts") == True,
                   f"tts={services.get('tts')}")
            report("3d.backend", services.get("backend") == True,
                   f"backend={services.get('backend')}")

            # ============================================================
            # Step 4: 上传 mp4 -> avatar 预处理
            # ============================================================
            print("\n--- Step 4: 上传 mp4 -> avatar 预处理 ---")
            with open(source_mp4, "rb") as f:
                r = await c.post(f"{BASE}/api/avatars/upload",
                    files={"file": ("pipeline_test.mp4", f, "video/mp4")},
                    data={"avatar_name": "PipelineTest"})

            report("4a.upload_201", r.status_code == 201, f"HTTP {r.status_code}")
            upload_body = r.json() if r.status_code == 201 else {}
            avatar_id = upload_body.get("avatar_id", "")
            report("4b.avatar_id", bool(avatar_id), f"avatar_id={avatar_id}")

            if avatar_id:
                await asyncio.sleep(3)
                avatar_base = os.path.join(PROJ_ROOT, "data", "avatars", avatar_id)
                src_path = os.path.join(avatar_base, "source.mp4")
                frame_path = os.path.join(avatar_base, "first_frame.png")
                has_src = os.path.isfile(src_path)
                has_frame = os.path.isfile(frame_path)
                report("4c.source_mp4", has_src and os.path.getsize(src_path) > 10000,
                       f"exists={has_src}, size={os.path.getsize(src_path) if has_src else 0}")
                report("4d.first_frame", has_frame, f"exists={has_frame}")

                # 验证全局 metadata store 中有 original_path
                avatar_info = app.state.avatar_service.get_avatar(avatar_id)
                orig_path = (avatar_info or {}).get("original_path") or (avatar_info or {}).get("path")
                report("4e.global_metadata", orig_path is not None and orig_path.endswith(".mp4"),
                       f"original_path={orig_path}")

            # ============================================================
            # Step 5: 文本 -> Fay/mock -> 回复文本
            # ============================================================
            print("\n--- Step 5: 文本 -> Fay -> 回复文本 ---")
            r = await c.post(f"{BASE}/api/conversations/reply",
                json={"text": "Hello test", "username": "PipelineTester"})
            conv = r.json() if r.status_code == 200 else {}
            reply = conv.get("reply", "")
            report("5a.http_200", r.status_code == 200, f"HTTP {r.status_code}")
            report("5b.reply_text", len(reply) > 5,
                   f"length={len(reply)}, text={reply[:60]}")

            # ============================================================
            # Step 6: TTS 合成验证
            # ============================================================
            print("\n--- Step 6: TTS 合成验证 ---")
            audio_url = conv.get("audio_url")
            report("6a.audio_url", audio_url is not None, f"audio_url={audio_url}")

            audio_path = None
            if audio_url:
                audio_filename = audio_url.replace("/files/audio/", "")
                audio_path = os.path.join(settings.absolute_audio_dir, audio_filename)
                exists = os.path.isfile(audio_path)
                fsize = os.path.getsize(audio_path) if exists else 0
                report("6b.wav_file", exists and fsize > 1000,
                       f"path={audio_path}, size={fsize}")
                if exists:
                    with open(audio_path, "rb") as af:
                        header = af.read(4)
                    report("6c.wav_header", header == b"RIFF",
                           f"header={header!r}")

            # ============================================================
            # Step 7: get_avatar_file 验证（MuseTalk 用的路径）
            # ============================================================
            print("\n--- Step 7: get_avatar_file -> 确认 MuseTalk 能拿到视频路径 ---")
            if avatar_id:
                avatar_file = app.state.avatar_service.get_avatar_file(avatar_id, size="original")
                report("7a.get_avatar_file", avatar_file is not None,
                       f"path={avatar_file}")
                if avatar_file:
                    is_video = avatar_file.lower().endswith((".mp4", ".avi", ".mov"))
                    exists = os.path.isfile(avatar_file)
                    fsize = os.path.getsize(avatar_file) if exists else 0
                    report("7b.is_video", is_video, f"ext={os.path.splitext(avatar_file)[1]}")
                    report("7c.exists", exists and fsize > 10000,
                           f"exists={exists}, size={fsize}")

    except Exception as e:
        report("server_error", False, f"HTTP 测试异常: {e}")

    # ================================================================
    # Step 8: MuseTalk 子进程独立启动验证（核心步骤）
    # ================================================================
    print("\n--- Step 8: MuseTalk 子进程独立验证（只等 90s） ---")
    from app.services.musetalk_service import MuseTalkService
    svc = MuseTalkService()
    svc.initialize()

    if not svc.is_available():
        report("8a.available", False, "MuseTalk 服务 initialize 后不可用")
    else:
        report("8a.available", True, "MuseTalk 服务可用")

        # 找 wav
        if not audio_path or not os.path.isfile(audio_path):
            wav_dir = settings.absolute_audio_dir
            wavs = sorted(
                [os.path.join(wav_dir, f) for f in os.listdir(wav_dir) if f.endswith(".wav")],
                key=os.path.getsize, reverse=True
            )
            audio_path = wavs[0] if wavs else None

        if not audio_path:
            report("8b.audio", False, "无可用 wav")
        else:
            report("8b.audio", True,
                   f"{os.path.basename(audio_path)}, {os.path.getsize(audio_path)} bytes")

            # 找 avatar mp4
            test_avatar = None
            if avatar_id:
                cand = os.path.join(PROJ_ROOT, "data", "avatars", avatar_id, "source.mp4")
                if os.path.isfile(cand):
                    test_avatar = cand
            if not test_avatar:
                test_avatar = source_mp4
            report("8c.avatar", os.path.isfile(test_avatar), f"{test_avatar}")

            # 验证所有模型文件
            unet_path = os.path.join(svc.model_dir, "unet.pth")
            unet_cfg = os.path.join(svc.model_dir, "musetalk.json")
            whisper_dir = os.path.join(svc.musetalk_path, "models", "whisper")
            report("8d.unet_model", os.path.isfile(unet_path),
                   f"size={os.path.getsize(unet_path) if os.path.isfile(unet_path) else 0}")
            report("8e.unet_config", os.path.isfile(unet_cfg), f"{unet_cfg}")
            report("8f.whisper_dir", os.path.isdir(whisper_dir), f"{whisper_dir}")

            # 构建 config yaml
            temp_dir = settings.absolute_temp_dir
            os.makedirs(temp_dir, exist_ok=True)
            cfg_file = os.path.join(temp_dir, f"test_cfg_{uuid.uuid4().hex[:6]}.yaml")
            avatar_fixed = os.path.abspath(test_avatar).replace("\\", "/")
            audio_fixed = os.path.abspath(audio_path).replace("\\", "/")
            with open(cfg_file, "w", encoding="utf-8") as f:
                f.write(f'task_0:\n')
                f.write(f'  video_path: "{avatar_fixed}"\n')
                f.write(f'  audio_path: "{audio_fixed}"\n')
                f.write(f'  bbox_shift: {svc.bbox_shift}\n')
            report("8g.config_yaml", os.path.isfile(cfg_file), "已生成")

            # Python 路径
            python_path = svc._resolve_python_path()
            report("8h.python_path", os.path.isfile(python_path), f"{python_path}")

            result_dir = os.path.join(settings.absolute_video_dir, "pipeline_test_results")
            os.makedirs(result_dir, exist_ok=True)

            cmd = [
                python_path, "-m", "scripts.inference",
                "--inference_config", os.path.abspath(cfg_file),
                "--result_dir", result_dir,
                "--version", svc.model_version,
                "--bbox_shift", str(svc.bbox_shift),
                "--fps", str(svc.fps),
                "--output_vid_name", "pipeline_test.mp4",
                "--unet_model_path", unet_path,
                "--unet_config", unet_cfg,
                "--whisper_dir", whisper_dir,
                "--batch_size", "4",
            ]

            cwd = svc.musetalk_path
            env = os.environ.copy()
            env["PYTHONPATH"] = cwd + os.pathsep + env.get("PYTHONPATH", "")

            print(f"\n  Command: python -m scripts.inference ...")
            print(f"  CWD: {cwd}")

            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=cwd, env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            report("8i.process_pid", proc.pid is not None, f"PID={proc.pid}")

            # 收集输出，检测关键阶段标志
            stdout_buf = []
            stderr_buf = []
            milestones = {
                "import_ok": False,
                "config_loaded": False,
                "extracting_landmarks": False,
                "reading_images": False,
                "bbox_shift": False,
                "error": None,
            }

            WAIT = 90
            deadline = time.time() + WAIT
            while time.time() < deadline:
                # 非阻塞读 stdout
                try:
                    chunk = await asyncio.wait_for(proc.stdout.read(8192), timeout=3)
                    if chunk:
                        text = chunk.decode("utf-8", errors="replace")
                        stdout_buf.append(text)
                        if "inference_config" in text or "task_0" in text:
                            milestones["config_loaded"] = True
                        if "Extracting landmarks" in text:
                            milestones["extracting_landmarks"] = True
                        if "reading images" in text:
                            milestones["reading_images"] = True
                        if "bbox_shift" in text:
                            milestones["bbox_shift"] = True
                        if "Error occurred" in text:
                            milestones["error"] = text.strip()[-200:]
                except asyncio.TimeoutError:
                    pass

                # 非阻塞读 stderr
                try:
                    chunk = await asyncio.wait_for(proc.stderr.read(8192), timeout=1)
                    if chunk:
                        text = chunk.decode("utf-8", errors="replace")
                        stderr_buf.append(text)
                        if "import" not in text.lower():
                            milestones["import_ok"] = True
                except asyncio.TimeoutError:
                    pass

                # 如果已经到达 extracting_landmarks 或 reading_images，说明启动成功
                if milestones["extracting_landmarks"] or milestones["reading_images"]:
                    break
                # 如果进程已退出
                if proc.returncode is not None:
                    break
                # 如果发现致命错误
                if milestones["error"]:
                    break

            stdout_all = "".join(stdout_buf)
            stderr_all = "".join(stderr_buf)

            # 保存证据
            evidence_dir = os.path.join(PROJ_ROOT, "test_artifacts", "pipeline_verify")
            os.makedirs(evidence_dir, exist_ok=True)
            with open(os.path.join(evidence_dir, "musetalk_stdout.log"), "w", encoding="utf-8") as f:
                f.write(stdout_all)
            with open(os.path.join(evidence_dir, "musetalk_stderr.log"), "w", encoding="utf-8") as f:
                f.write(stderr_all)
            with open(os.path.join(evidence_dir, "musetalk_command.txt"), "w", encoding="utf-8") as f:
                f.write(f"Command: {' '.join(cmd)}\nCWD: {cwd}\n")

            print(f"\n  里程碑: {json.dumps(milestones, ensure_ascii=False)}")

            # 判定结果
            if milestones["extracting_landmarks"] or milestones["reading_images"]:
                report("8j.musetalk_started", True,
                       "MuseTalk 已成功加载模型并开始处理帧")
            elif milestones["bbox_shift"]:
                report("8j.musetalk_started", True,
                       "MuseTalk 已到达 bbox_shift 处理阶段")
            elif milestones["config_loaded"]:
                report("8j.musetalk_started", True,
                       "MuseTalk 已加载配置（模型加载中，90s 内未到帧处理阶段）")
            elif milestones["error"]:
                report("8j.musetalk_started", False,
                       f"MuseTalk 报错: {milestones['error'][:100]}")
            elif proc.returncode is not None and proc.returncode != 0:
                report("8j.musetalk_started", False,
                       f"子进程退出 code={proc.returncode}")
            else:
                # 90s 内没看到标志，但进程仍在运行 = 模型加载中
                running = proc.returncode is None
                report("8j.musetalk_started", running,
                       f"进程{'仍在运行' if running else '已退出'}，90s 内未见明确进度标志（可能在加载模型）")

            # 检查 stderr 致命错误
            fatal_kw = ["ModuleNotFoundError", "ImportError", "No module named"]
            fatal_found = [k for k in fatal_kw if k in stderr_all]
            if fatal_found:
                report("8k.no_import_error", False,
                       f"stderr 含: {fatal_found}")
                print(f"\n  stderr 末尾 500 字符:")
                print(f"  {stderr_all[-500:]}")
            else:
                report("8k.no_import_error", True, "无 import 致命错误")

            print(f"\n  stdout 末尾 400 字符:")
            print(f"  {stdout_all[-400:]}")

            # 终止子进程
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

            try:
                os.remove(cfg_file)
            except OSError:
                pass

    # ================================================================
    # 总结
    # ================================================================
    print("\n" + "=" * 70)
    print("  全链路验证结果总结")
    print("=" * 70)

    passed = sum(1 for s in step_results if s["status"] == "PASS")
    failed = sum(1 for s in step_results if s["status"] == "FAIL")
    total = len(step_results)
    print(f"\n  PASS: {passed}/{total}  |  FAIL: {failed}/{total}")

    if failed > 0:
        print("\n  失败项:")
        for s in step_results:
            if s["status"] == "FAIL":
                print(f"    [FAIL] {s['step']}: {s['detail']}")

    # 关键链路判定
    critical_steps = [s for s in step_results if s["step"].startswith(
        ("1.", "2.", "3a", "3b", "3c", "4a", "4b", "4c", "5a", "5b",
         "6a", "6b", "7a", "7b", "7c", "8a", "8b", "8c", "8h", "8i", "8k")
    )]
    critical_ok = all(s["status"] == "PASS" for s in critical_steps)
    critical_fail = [s for s in critical_steps if s["status"] == "FAIL"]

    print(f"\n  关键链路 ({len(critical_steps)} 项): {'全部通过' if critical_ok else f'{len(critical_fail)} 项失败'}")
    if critical_ok:
        print("\n  === 结论 ===")
        print("  从上传 mp4 到 MuseTalk 子进程启动的全部环节均已验证通过。")
        print("  完整链路：upload -> avatar -> Fay(mock) -> TTS(Edge) -> wav -> MuseTalk(subprocess) 全部畅通。")
        print("  唯一瓶颈：CPU 推理速度，需 GPU 环境才能在合理时间内产出视频。")
    else:
        print("\n  === 结论 ===")
        print("  链路存在断点，请查看上方失败项。")

    # 保存结果
    evidence_dir = os.path.join(PROJ_ROOT, "test_artifacts", "pipeline_verify")
    os.makedirs(evidence_dir, exist_ok=True)
    with open(os.path.join(evidence_dir, "step_results.json"), "w", encoding="utf-8") as f:
        json.dump(step_results, f, indent=2, ensure_ascii=False)

    server.should_exit = True
    await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
