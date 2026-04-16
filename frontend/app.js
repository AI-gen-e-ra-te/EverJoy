/* DigiPeople Core 前端应用逻辑 - 第四阶段：Fay WS 皮肤客户端模式 */

// 全局变量
let apiBaseUrl = 'http://localhost:8002';
let selectedFile = null;
let currentTaskId = null;
let currentAvatarId = null;
let pollingInterval = null;
let rendererPollingInterval = null;
let lastRendererTimestamp = null;

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('DigiPeople Core 第四阶段：Fay WS 皮肤客户端模式');

    // 设置API基础URL
    document.getElementById('api-url').textContent = apiBaseUrl;

    // 初始化事件监听器
    initEventListeners();

    // 初始健康检查
    checkHealthStatus();

    // 启动渲染器结果轮询
    startRendererPolling();
});

// 初始化事件监听器
function initEventListeners() {
    // 文件上传区域
    const mp4DropArea = document.getElementById('mp4-drop-area');
    const mp4FileInput = document.getElementById('mp4-file-input');
    const selectMp4Btn = document.getElementById('select-mp4-btn');

    if (selectMp4Btn) {
        selectMp4Btn.addEventListener('click', () => mp4FileInput.click());
    }

    if (mp4FileInput) {
        mp4FileInput.addEventListener('change', handleMp4FileSelect);
    }

    // 提交按钮
    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) {
        submitBtn.addEventListener('click', submitProcessing);
    }

    // 健康检查按钮
    const healthBtn = document.getElementById('check-health-btn');
    if (healthBtn) {
        healthBtn.addEventListener('click', checkHealthStatus);
    }

    // 刷新任务按钮
    const refreshBtn = document.getElementById('refresh-tasks-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshTaskStatus);
    }

    // 拖放文件支持
    if (mp4DropArea) {
        mp4DropArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            mp4DropArea.style.border = '2px dashed #4CAF50';
        });

        mp4DropArea.addEventListener('dragleave', () => {
            mp4DropArea.style.border = '2px dashed #ccc';
        });

        mp4DropArea.addEventListener('drop', (e) => {
            e.preventDefault();
            mp4DropArea.style.border = '2px dashed #ccc';

            if (e.dataTransfer.files.length) {
                const file = e.dataTransfer.files[0];
                if (file.type === 'video/mp4') {
                    selectedFile = file;
                    showNotification(`已选择文件: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`, 'success');
                    updateFileDisplay(file);
                } else {
                    showNotification('请选择有效的MP4文件', 'error');
                }
            }
        });
    }
}

// 处理MP4文件选择
function handleMp4FileSelect(e) {
    const file = e.target.files[0];
    if (file && file.type === 'video/mp4') {
        selectedFile = file;
        showNotification(`已选择文件: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`, 'success');
        updateFileDisplay(file);
    } else {
        showNotification('请选择有效的MP4文件', 'error');
    }
}

// 更新文件显示
function updateFileDisplay(file) {
    const dropArea = document.getElementById('mp4-drop-area');
    if (dropArea) {
        dropArea.innerHTML = `
            <i class="fas fa-check-circle" style="color: #4CAF50; font-size: 2rem; margin-bottom: 0.5rem;"></i>
            <p><strong>${file.name}</strong></p>
            <p class="upload-hint">${(file.size / 1024 / 1024).toFixed(2)} MB</p>
            <button id="change-file-btn" class="btn btn-secondary">更换文件</button>
        `;

        // 重新绑定更换文件按钮
        document.getElementById('change-file-btn').addEventListener('click', () => {
            document.getElementById('mp4-file-input').click();
        });
    }
}

// 提交处理
async function submitProcessing() {
    if (!selectedFile) {
        showNotification('请先选择MP4文件', 'warning');
        return;
    }

    const text = document.getElementById('text-input').value.trim();
    if (!text) {
        showNotification('请输入文本内容', 'warning');
        return;
    }

    // 禁用提交按钮，防止重复提交
    const submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 处理中...';

    try {
        // 创建FormData
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('avatar_name', `Avatar_${Date.now()}`);
        formData.append('description', `基于文本生成的数字人: ${text.substring(0, 50)}...`);

        // 显示上传进度
        showNotification('开始上传MP4文件...', 'info');

        // 发送上传请求
        const response = await fetch(`${apiBaseUrl}/api/avatars/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `上传失败: ${response.status}`);
        }

        const data = await response.json();

        // 保存任务ID和avatar ID
        currentTaskId = data.task_id;
        currentAvatarId = data.avatar_id;

        // 更新任务状态显示
        updateTaskStatus({
            id: currentTaskId,
            status: 'pending',
            progress: 0,
            message: 'MP4文件上传成功，等待avatar预处理...'
        });

        // 开始轮询任务状态
        startPollingTaskStatus();

        showNotification('MP4文件上传成功，已开始avatar预处理', 'success');

        // 自动设置为渲染器默认 avatar（Fay WS 模式用）
        await setRendererDefaultAvatar(currentAvatarId);

        // 调用Fay API生成对话回复（直连模式保留）
        await generateConversationReply(text);

    } catch (error) {
        console.error('提交处理失败:', error);
        showNotification(`处理失败: ${error.message}`, 'error');

        // 恢复提交按钮
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i> 提交处理';
    }
}

// 生成对话回复
async function generateConversationReply(userText) {
    try {
        showNotification('正在生成Fay对话回复...', 'info');

        const response = await fetch(`${apiBaseUrl}/api/conversations/reply`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: userText,
                username: 'User',
                avatar_id: currentAvatarId || null
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `生成回复失败: ${response.status}`);
        }

        const data = await response.json();

        // 显示回复
        updateConversationReplyDisplay(data);

        showNotification('Fay对话回复生成成功', 'success');

        return data.reply;
    } catch (error) {
        console.error('生成对话回复失败:', error);
        showNotification(`生成对话回复失败: ${error.message}`, 'error');

        // 显示错误信息
        updateConversationReplyDisplay({
            success: false,
            reply: `抱歉，生成回复时出现错误: ${error.message}`
        });

        return null;
    }
}

// 播放音频
function playAudio(audioUrl) {
    try {
        const audio = new Audio(audioUrl);
        audio.play();
        showNotification('正在播放音频...', 'info');
    } catch (error) {
        console.error('播放音频失败:', error);
        showNotification(`播放音频失败: ${error.message}`, 'error');
    }
}

// 加载并播放视频
function loadAndPlayVideo(videoUrl) {
    try {
        const videoPlayer = document.getElementById('video-player');
        const videoPlaceholder = document.getElementById('video-placeholder');
        const outputVideo = document.getElementById('output-video');

        if (!videoPlayer || !outputVideo) {
            console.error('视频播放器元素未找到');
            return;
        }

        // 设置视频源
        outputVideo.src = videoUrl;

        // 显示视频，隐藏占位符
        if (videoPlaceholder) {
            videoPlaceholder.style.display = 'none';
        }
        outputVideo.style.display = 'block';

        // 播放视频
        outputVideo.load();
        outputVideo.play().then(() => {
            showNotification('视频加载并开始播放', 'success');
        }).catch(error => {
            console.error('视频播放失败:', error);
            showNotification(`视频播放失败: ${error.message}`, 'error');
            // 可能需要用户交互才能播放，显示播放按钮
            outputVideo.controls = true;
        });

    } catch (error) {
        console.error('加载视频失败:', error);
        showNotification(`加载视频失败: ${error.message}`, 'error');
    }
}

// 更新对话回复显示
function updateConversationReplyDisplay(data) {
    const replyContainer = document.getElementById('conversation-reply');
    if (!replyContainer) return;

    const success = data.success || false;
    const reply = data.reply || '无回复内容';
    const username = data.username || 'User';
    const avatarId = data.avatar_id || currentAvatarId || 'N/A';
    const processingTime = data.processing_time ? `${data.processing_time.toFixed(2)}秒` : 'N/A';
    const audioUrl = data.audio_url || null;
    const videoUrl = data.video_url || null;
    const jobId = data.job_id || null;

    let mediaInfo = '';
    if (audioUrl) {
        mediaInfo += `<div style="margin-top: 0.5rem;">
            <strong><i class="fas fa-volume-up"></i> 音频:</strong>
            <a href="${apiBaseUrl}${audioUrl}" target="_blank">${audioUrl}</a>
            <button onclick="playAudio('${apiBaseUrl}${audioUrl}')" class="btn btn-small" style="margin-left: 0.5rem;">
                <i class="fas fa-play"></i> 播放音频
            </button>
        </div>`;
    }

    if (videoUrl) {
        mediaInfo += `<div style="margin-top: 0.5rem;">
            <strong><i class="fas fa-video"></i> 视频:</strong>
            <a href="${apiBaseUrl}${videoUrl}" target="_blank">${videoUrl}</a>
            <button onclick="loadAndPlayVideo('${apiBaseUrl}${videoUrl}')" class="btn btn-small" style="margin-left: 0.5rem;">
                <i class="fas fa-play"></i> 播放视频
            </button>
        </div>`;

        // 自动加载视频
        setTimeout(() => loadAndPlayVideo(`${apiBaseUrl}${videoUrl}`), 1000);
    }

    if (jobId) {
        mediaInfo += `<div style="margin-top: 0.5rem;">
            <strong><i class="fas fa-tasks"></i> 任务ID:</strong> ${jobId}
        </div>`;
    }

    replyContainer.innerHTML = `
        <div style="${success ? 'border-left: 4px solid #4CAF50;' : 'border-left: 4px solid #f44336;'} padding-left: 1rem;">
            ${success ?
                '<div style="color: #4CAF50; font-weight: bold; margin-bottom: 0.5rem;"><i class="fas fa-check-circle"></i> Fay回复成功</div>' :
                '<div style="color: #f44336; font-weight: bold; margin-bottom: 0.5rem;"><i class="fas fa-exclamation-circle"></i> 回复生成失败</div>'
            }
            <div style="margin-bottom: 0.5rem;">
                <strong>用户:</strong> ${username}<br>
                <strong>Avatar ID:</strong> ${avatarId}<br>
                <strong>处理时间:</strong> ${processingTime}
            </div>
            <div style="background: white; padding: 1rem; border-radius: var(--border-radius); margin-top: 1rem;">
                <strong>回复内容:</strong>
                <p style="margin-top: 0.5rem; white-space: pre-wrap; line-height: 1.5;">${reply}</p>
                ${mediaInfo ? `<div style="margin-top: 1rem; padding: 1rem; background: #f8f9fa; border-radius: var(--border-radius);">${mediaInfo}</div>` : ''}
            </div>
        </div>
    `;
}

// 开始轮询任务状态
function startPollingTaskStatus() {
    // 清除之前的轮询
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }

    // 每3秒轮询一次
    pollingInterval = setInterval(async () => {
        if (!currentTaskId) return;

        try {
            const response = await fetch(`${apiBaseUrl}/api/tasks/${currentTaskId}/status`);
            if (response.ok) {
                const taskStatus = await response.json();

                // 更新任务状态显示
                updateTaskStatus({
                    id: taskStatus.task_id || currentTaskId,
                    status: taskStatus.status,
                    progress: Math.round((taskStatus.progress || 0) * 100),
                    message: taskStatus.error_message || '处理中...'
                });

                // 如果任务完成或失败，停止轮询
                if (['completed', 'failed', 'timeout', 'cancelled'].includes(taskStatus.status)) {
                    clearInterval(pollingInterval);
                    pollingInterval = null;

                    // 启用提交按钮
                    const submitBtn = document.getElementById('submit-btn');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i> 提交处理';

                    // 如果任务完成，获取avatar信息
                    if (taskStatus.status === 'completed') {
                        fetchAvatarInfo(currentAvatarId);
                        showNotification('avatar预处理完成！', 'success');
                    } else {
                        showNotification(`avatar预处理失败: ${taskStatus.error_message || taskStatus.status}`, 'error');
                    }
                }
            }
        } catch (error) {
            console.error('轮询任务状态失败:', error);
        }
    }, 3000);
}

// 获取avatar信息
async function fetchAvatarInfo(avatarId) {
    try {
        const response = await fetch(`${apiBaseUrl}/api/avatars/${avatarId}/info`);
        if (response.ok) {
            const data = await response.json();
            console.log('Avatar信息:', data);

            // 更新界面显示avatar信息
            updateAvatarInfoDisplay(data.info);
        }
    } catch (error) {
        console.error('获取avatar信息失败:', error);
    }
}

// 更新avatar信息显示
function updateAvatarInfoDisplay(avatarInfo) {
    const taskStatusDiv = document.getElementById('task-status');
    if (taskStatusDiv && avatarInfo) {
        const metadata = avatarInfo.metadata || {};
        taskStatusDiv.innerHTML += `
            <div class="task-item" style="background: #e8f5e9; margin-top: 1rem;">
                <strong>Avatar信息:</strong><br>
                <strong>ID:</strong> ${avatarInfo.avatar_id || 'N/A'}<br>
                <strong>状态:</strong> ${avatarInfo.status || 'N/A'}<br>
                <strong>创建时间:</strong> ${avatarInfo.created_at || 'N/A'}<br>
                <strong>视频文件:</strong> ${metadata.original_filename || 'N/A'}<br>
                <strong>处理类型:</strong> ${avatarInfo.processing_type || metadata.processing_type || 'mock_preprocessing'}
            </div>
        `;
    }
}

// 更新任务状态显示
function updateTaskStatus(task) {
    const taskStatus = document.getElementById('task-status');
    if (!taskStatus) return;

    // 确定状态CSS类
    let statusClass = 'status-pending';
    if (task.status === 'running') statusClass = 'status-running';
    if (task.status === 'completed') statusClass = 'status-completed';
    if (['failed', 'timeout', 'cancelled'].includes(task.status)) statusClass = 'status-failed';

    taskStatus.innerHTML = `
        <div class="task-item">
            <strong>任务ID:</strong> <span>${task.id}</span><br>
            <strong>Avatar ID:</strong> <span>${currentAvatarId || '--'}</span><br>
            <strong>状态:</strong> <span class="${statusClass}">${task.status}</span><br>
            <strong>进度:</strong> <span>${task.progress}%</span><br>
            <strong>消息:</strong> <span>${task.message}</span>
        </div>
        <div class="task-item">
            <strong>系统状态:</strong> <span class="status-running">后端服务运行中</span><br>
            <strong>健康检查:</strong> <span id="health-status">未检查</span>
        </div>
    `;

    // 更新进度条（可选）
    // 这里可以添加进度条更新逻辑
}

// 检查健康状态
async function checkHealthStatus() {
    try {
        const response = await fetch(`${apiBaseUrl}/api/health/`);
        if (response.ok) {
            const data = await response.json();
            const services = data.services || {};
            const wsConnected = services.renderer_ws ? '已连接' : '未连接';
            document.getElementById('health-status').textContent =
                `健康 | Fay WS: ${wsConnected}`;
            document.getElementById('health-status').className = 'status-completed';
            showNotification(
                `后端健康 | MuseTalk: ${services.musetalk ? 'OK' : 'N/A'} | Fay WS: ${wsConnected}`,
                'success'
            );
        } else {
            throw new Error('健康检查失败');
        }
    } catch (error) {
        document.getElementById('health-status').textContent = '不健康';
        document.getElementById('health-status').className = 'status-failed';
        showNotification('后端服务不可用', 'error');
    }
}

// 刷新任务状态
function refreshTaskStatus() {
    if (currentTaskId) {
        // 手动触发一次轮询
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
        startPollingTaskStatus();
        showNotification('手动刷新任务状态', 'info');
    } else {
        showNotification('当前没有活跃的任务', 'info');
    }
}

// 显示通知 (简化版)
function showNotification(message, type = 'info') {
    console.log(`${type}: ${message}`);

    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'}"></i>
        <span>${message}</span>
    `;

    // 添加到通知容器
    const container = document.getElementById('notification-container');
    if (!container) {
        // 如果没有容器，创建一个
        const newContainer = document.createElement('div');
        newContainer.id = 'notification-container';
        newContainer.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 1000;';
        document.body.appendChild(newContainer);
        container = newContainer;
    }

    container.appendChild(notification);

    // 3秒后移除通知
    setTimeout(() => {
        if (notification.parentNode) {
            notification.style.opacity = '0';
            notification.style.transition = 'opacity 0.5s';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 500);
        }
    }, 3000);
}

// =====================================================================
// Fay WS 渲染器模式：轮询最新结果
// =====================================================================

async function setRendererDefaultAvatar(avatarId) {
    try {
        const response = await fetch(`${apiBaseUrl}/api/renderer/set-default-avatar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ avatar_id: avatarId }),
        });
        if (response.ok) {
            showNotification(`已设置渲染器默认 Avatar: ${avatarId}`, 'success');
        }
    } catch (e) {
        console.warn('设置渲染器默认 avatar 失败:', e);
    }
}

function startRendererPolling() {
    if (rendererPollingInterval) clearInterval(rendererPollingInterval);
    rendererPollingInterval = setInterval(pollRendererResult, 3000);
}

async function pollRendererResult() {
    try {
        const response = await fetch(`${apiBaseUrl}/api/renderer/latest`);
        if (!response.ok) return;
        const data = await response.json();
        if (!data.has_result) return;

        const result = data.result;
        if (result.timestamp === lastRendererTimestamp) return;
        lastRendererTimestamp = result.timestamp;

        updateRendererResultDisplay(result);
    } catch (e) {
        // 静默失败，不打扰用户
    }
}

function updateRendererResultDisplay(result) {
    const replyContainer = document.getElementById('conversation-reply');
    if (!replyContainer) return;

    const status = result.status || 'unknown';
    const isSuccess = status === 'completed';
    const text = result.text || '';
    const videoUrl = result.video_url || null;
    const error = result.error || null;
    const duration = result.duration ? `${result.duration.toFixed(1)}s` : 'N/A';
    const username = result.username || 'Fay';
    const ts = result.timestamp ? new Date(result.timestamp).toLocaleTimeString() : '';

    let mediaInfo = '';
    if (videoUrl) {
        const fullUrl = `${apiBaseUrl}${videoUrl}`;
        mediaInfo = `
            <div style="margin-top: 0.5rem;">
                <strong><i class="fas fa-video"></i> 唇形同步视频:</strong>
                <a href="${fullUrl}" target="_blank">${videoUrl}</a>
                <button onclick="loadAndPlayVideo('${fullUrl}')" class="btn btn-small" style="margin-left: 0.5rem;">
                    <i class="fas fa-play"></i> 播放视频
                </button>
            </div>`;
        setTimeout(() => loadAndPlayVideo(fullUrl), 500);
    }

    const borderColor = isSuccess ? '#4CAF50' : (status === 'failed' ? '#f44336' : '#ff9800');
    const statusIcon = isSuccess ? 'check-circle' : (status === 'failed' ? 'times-circle' : 'clock');
    const statusLabel = isSuccess ? '渲染完成' : (status === 'failed' ? '渲染失败' : '已跳过');

    replyContainer.innerHTML = `
        <div style="border-left: 4px solid ${borderColor}; padding-left: 1rem;">
            <div style="color: ${borderColor}; font-weight: bold; margin-bottom: 0.5rem;">
                <i class="fas fa-${statusIcon}"></i> [Fay WS] ${statusLabel}
                <span style="font-weight: normal; color: #888; margin-left: 0.5rem;">${ts}</span>
            </div>
            <div style="margin-bottom: 0.5rem;">
                <strong>用户:</strong> ${username} |
                <strong>渲染耗时:</strong> ${duration}
            </div>
            <div style="background: white; padding: 1rem; border-radius: var(--border-radius);">
                <strong>Fay 回复:</strong>
                <p style="margin-top: 0.5rem; white-space: pre-wrap;">${text}</p>
                ${error ? `<p style="color: #f44336; margin-top: 0.5rem;"><strong>错误:</strong> ${error}</p>` : ''}
                ${mediaInfo ? `<div style="margin-top: 1rem; padding: 1rem; background: #f8f9fa; border-radius: var(--border-radius);">${mediaInfo}</div>` : ''}
            </div>
        </div>`;
}

async function fetchRendererStatus() {
    try {
        const response = await fetch(`${apiBaseUrl}/api/renderer/status`);
        if (!response.ok) return null;
        return await response.json();
    } catch (e) {
        return null;
    }
}

// 添加CSS样式
const style = document.createElement('style');
style.textContent = `
    .notification {
        background: white;
        border-left: 4px solid #2196F3;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        padding: 12px 16px;
        margin-bottom: 10px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        min-width: 300px;
        max-width: 400px;
        animation: slideIn 0.3s ease;
    }

    .notification-success {
        border-left-color: #4CAF50;
    }

    .notification-error {
        border-left-color: #f44336;
    }

    .notification-warning {
        border-left-color: #ff9800;
    }

    .notification-info {
        border-left-color: #2196F3;
    }

    .notification i {
        margin-right: 10px;
        font-size: 1.2rem;
    }

    .notification-success i {
        color: #4CAF50;
    }

    .notification-error i {
        color: #f44336;
    }

    .notification-warning i {
        color: #ff9800;
    }

    .notification-info i {
        color: #2196F3;
    }

    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    .status-pending { color: #ff9800; font-weight: bold; }
    .status-running { color: #2196F3; font-weight: bold; }
    .status-completed { color: #4CAF50; font-weight: bold; }
    .status-failed { color: #f44336; font-weight: bold; }

    .btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }
`;
document.head.appendChild(style);