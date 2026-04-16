#!/usr/bin/env python3
"""
MuseTalk 依赖项安装脚本

用于安装 MuseTalk 所需的 Python 依赖项。
根据 MuseTalk 的 requirements.txt 和 mmpose 等额外需求进行安装。
"""

import os
import sys
import subprocess
import platform
import argparse

def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    print(f"Python 版本: {version.major}.{version.minor}.{version.micro}")

    # MuseTalk 可能需要 Python 3.8-3.11
    if version.major != 3:
        print("错误: 需要 Python 3")
        return False
    if version.minor < 8:
        print("警告: MuseTalk 可能需要 Python 3.8 或更高版本")
    return True

def run_command(cmd, description):
    """运行命令并返回是否成功"""
    print(f"\n{description}:")
    print(f"命令: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print("成功")
            return True
        else:
            print(f"失败，返回码: {result.returncode}")
            if result.stderr:
                print(f"错误输出: {result.stderr[:500]}")
            return False
    except Exception as e:
        print(f"执行命令时出错: {e}")
        return False

def install_pip_packages():
    """安装 pip 包"""
    # MuseTalk 核心依赖
    packages = [
        "torch>=2.0.0",
        "torchvision>=0.15.0",
        "opencv-python>=4.9.0.80",
        "numpy<2",  # MuseTalk 可能需要 NumPy 1.x
        "diffusers>=0.30.2",
        "accelerate>=0.28.0",
        "soundfile>=0.12.1",
        "transformers>=4.39.2",
        "huggingface-hub>=0.30.2",
        "librosa>=0.11.0",
        "einops>=0.8.1",
        "omegaconf>=2.3.0",
        "ffmpeg-python>=0.2.0",
        "moviepy>=2.2.1",
        "imageio[ffmpeg]>=2.31.0",
        "gradio>=5.24.0",
        "tensorflow>=2.12.0",  # 可选，某些组件可能需要
    ]

    success = True
    for package in packages:
        cmd = [sys.executable, "-m", "pip", "install", package]
        if not run_command(cmd, f"安装 {package}"):
            success = False
            print(f"警告: 安装 {package} 失败，继续...")

    return success

def install_mmengine_mmcv():
    """安装 mmengine 和 mmcv"""
    print("\n安装 mmengine 和 mmcv...")

    # 先安装 mmengine
    cmd = [sys.executable, "-m", "pip", "install", "mmengine"]
    if not run_command(cmd, "安装 mmengine"):
        print("警告: 安装 mmengine 失败")
        return False

    # 安装 mmcv，根据平台选择合适版本
    system = platform.system()
    if system == "Windows":
        # Windows 上可能需要从源码编译或使用特定 wheel
        print("在 Windows 上安装 mmcv 可能需要从源码编译")
        print("建议使用 mim 安装: mim install mmcv==2.0.1")
        cmd = [sys.executable, "-m", "pip", "install", "mmcv>=2.0.1"]
        if not run_command(cmd, "安装 mmcv"):
            print("警告: 安装 mmcv 失败，尝试安装 mmcv-lite")
            cmd = [sys.executable, "-m", "pip", "install", "mmcv-lite>=2.0.1"]
            run_command(cmd, "安装 mmcv-lite")
    else:
        # Linux/macOS
        cmd = [sys.executable, "-m", "pip", "install", "mmcv>=2.0.1"]
        run_command(cmd, "安装 mmcv")

    return True

def install_mmdet_mmpose():
    """安装 mmdet 和 mmpose"""
    print("\n安装 mmdet 和 mmpose...")

    # 安装 mmdet
    cmd = [sys.executable, "-m", "pip", "install", "mmdet>=3.1.0"]
    if not run_command(cmd, "安装 mmdet"):
        print("警告: 安装 mmdet 失败")
        return False

    # 安装 mmpose
    cmd = [sys.executable, "-m", "pip", "install", "mmpose>=1.1.0"]
    if not run_command(cmd, "安装 mmpose"):
        print("警告: 安装 mmpose 失败，尝试从源码安装")
        # 尝试从 GitHub 安装
        cmd = [sys.executable, "-m", "pip", "install", "git+https://github.com/open-mmlab/mmpose.git@v1.1.0"]
        run_command(cmd, "从 GitHub 安装 mmpose")

    return True

def install_openmim():
    """安装 openmim（用于管理 OpenMMLab 包）"""
    print("\n安装 openmim...")
    cmd = [sys.executable, "-m", "pip", "install", "openmim"]
    return run_command(cmd, "安装 openmim")

def check_ffmpeg():
    """检查 ffmpeg 是否可用"""
    print("\n检查 ffmpeg...")
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("ffmpeg 已安装")
            return True
        else:
            print("ffmpeg 未找到或不可用")
            return False
    except FileNotFoundError:
        print("ffmpeg 未安装")
        print("请从 https://ffmpeg.org/download.html 下载并安装 ffmpeg")
        print("或使用包管理器安装:")
        print("  - Windows: choco install ffmpeg")
        print("  - macOS: brew install ffmpeg")
        print("  - Ubuntu/Debian: sudo apt install ffmpeg")
        return False

def main():
    parser = argparse.ArgumentParser(description="安装 MuseTalk 依赖项")
    parser.add_argument("--skip-pip", action="store_true", help="跳过 pip 包安装")
    parser.add_argument("--skip-mm", action="store_true", help="跳过 OpenMMLab 包安装")
    parser.add_argument("--skip-ffmpeg", action="store_true", help="跳过 ffmpeg 检查")
    args = parser.parse_args()

    print("=" * 60)
    print("MuseTalk 依赖项安装脚本")
    print("=" * 60)

    # 检查 Python 版本
    if not check_python_version():
        sys.exit(1)

    # 升级 pip
    print("\n升级 pip...")
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
    run_command(cmd, "升级 pip")

    success = True

    # 安装 pip 包
    if not args.skip_pip:
        if not install_pip_packages():
            success = False
            print("警告: 部分 pip 包安装失败")

    # 安装 OpenMMLab 包
    if not args.skip_mm:
        if not install_openmim():
            print("警告: 安装 openmim 失败")

        if not install_mmengine_mmcv():
            success = False
            print("警告: 安装 mmengine/mmcv 失败")

        if not install_mmdet_mmpose():
            success = False
            print("警告: 安装 mmdet/mmpose 失败")

    # 检查 ffmpeg
    if not args.skip_ffmpeg:
        if not check_ffmpeg():
            success = False
            print("警告: ffmpeg 未安装")

    # 总结
    print("\n" + "=" * 60)
    print("安装完成摘要:")
    if success:
        print("✓ 所有依赖项已成功安装或尝试安装")
        print("\n下一步:")
        print("1. 如果仍有缺失依赖项，请手动安装")
        print("2. 运行测试: python test_musetalk_simple.py")
        print("3. 启动后端服务: python -m app.main")
    else:
        print("[WARNING] 部分依赖项安装失败")
        print("\n请手动安装失败的包，或检查错误信息")
        print("常见问题:")
        print("- Windows 用户可能需要安装 Visual C++ Build Tools")
        print("- mmcv 可能需要从源码编译")
        print("- 确保 Python 版本兼容 (3.8-3.11)")

    print("=" * 60)

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())