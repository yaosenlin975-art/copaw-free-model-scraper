#!/usr/bin/env python3
"""
模型更新脚本 v2
功能：
1. 从 NVIDIA 和 OpenRouter 获取免费模型
2. 分析模型用途（文字、声音、视频、图片）
3. 对比上一次执行的模型列表，识别新增/变化/失效
4. 发送美观的邮件报告
5. 更新本地配置文件，删除失效模型
"""

import smtplib
import json
import os
import re
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path

# 配置
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # 指向项目根目录
SKILL_WORKSPACE = Path(__file__).parent.parent / "workspace"  # 技能工作空间
PREVIOUS_MODELS_FILE = SKILL_WORKSPACE / "previous_models.json"
CURRENT_MODELS_FILE = SKILL_WORKSPACE / "all_free_models.json"
NVIDIA_CONFIG = Path(r"C:\Users\Administrator\.copaw.secret\providers\custom\nvidia.json")
OPENROUTER_CONFIG = Path(r"C:\Users\Administrator\.copaw.secret\providers\custom\open-router.json")

# 数据文件路径
NVIDIA_DATA_FILE = PROJECT_ROOT / "planning" / "model-scraper" / "nvidia_models_processed.json"
OPENROUTER_DATA_FILE = PROJECT_ROOT / "planning" / "model-scraper" / "openrouter_models_processed.json"

# 读取环境变量
def load_env():
    env_file = Path(__file__).parent.parent.parent / ".env"
    env_vars = {}
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars

ENV = load_env()

# 模型用途关键词映射
MODALITY_KEYWORDS = {
    'audio': ['voice', 'speech', 'audio', 'asr', 'tts', 'sound', 'whisper', 'wav2vec', 'lyria', 'music'],
    'image': ['image', 'visual', 'vision', 'ocr', 'flux', 'stable-diffusion', 'dall', 'clip', 'picture', 'photo'],
    'video': ['video', 'movie', 'frame'],
    'text': ['chat', 'instruct', 'code', 'reasoning', 'agent', 'rerank', 'embed', 'search', 'translate', 'summarize']
}

def classify_model_modality(name, description):
    """根据模型名称和描述分类模型用途"""
    text = f"{name} {description}".lower()
    
    modalities = []
    
    # 检查音频
    if any(kw in text for kw in MODALITY_KEYWORDS['audio']):
        modalities.append('audio')
    
    # 检查图片
    if any(kw in text for kw in MODALITY_KEYWORDS['image']):
        modalities.append('image')
    
    # 检查视频
    if any(kw in text for kw in MODALITY_KEYWORDS['video']):
        modalities.append('video')
    
    # 检查文本（默认）
    if any(kw in text for kw in MODALITY_KEYWORDS['text']) or not modalities:
        modalities.append('text')
    
    return modalities

def fetch_nvidia_models():
    """获取 NVIDIA 免费模型"""
    print("正在获取 NVIDIA 免费模型...")
    
    # 这里应该调用之前的爬取逻辑
    # 为了简化，我们直接读取已有的数据文件
    if NVIDIA_DATA_FILE.exists():
        with open(NVIDIA_DATA_FILE, 'r', encoding='utf-8') as f:
            models = json.load(f)
        print(f"  从本地文件读取到 {len(models)} 个 NVIDIA 模型")
        return models
    
    print("  未找到本地 NVIDIA 数据文件")
    return []

def fetch_openrouter_models():
    """获取 OpenRouter 免费模型"""
    print("正在获取 OpenRouter 免费模型...")
    
    # 先尝试从本地文件读取
    if OPENROUTER_DATA_FILE.exists():
        with open(OPENROUTER_DATA_FILE, 'r', encoding='utf-8') as f:
            models = json.load(f)
        print(f"  从本地文件读取到 {len(models)} 个 OpenRouter 模型")
        return models
    
    try:
        # 使用 curl 调用 OpenRouter API
        result = subprocess.run(
            ['curl', '-s', 'https://openrouter.ai/api/v1/models'],
            capture_output=True, timeout=30
        )
        
        if result.returncode != 0:
            print(f"  curl 调用失败")
            return []
        
        # 尝试不同编码解析
        try:
            content = result.stdout.decode('utf-8')
        except:
            content = result.stdout.decode('utf-8', errors='replace')
        
        data = json.loads(content)
        all_models = data.get('data', [])
        
        # 筛选免费模型
        free_models = []
        for model in all_models:
            pricing = model.get('pricing', {})
            prompt_price = float(pricing.get('prompt', '1'))
            completion_price = float(pricing.get('completion', '1'))
            
            if prompt_price == 0 and completion_price == 0:
                free_models.append({
                    'source': 'OpenRouter',
                    'name': model.get('name', model.get('id', 'Unknown')),
                    'id': model.get('id', ''),
                    'parameters': model.get('context_length', 'Unknown'),
                    'context_length': f"{model.get('context_length', 0)} tokens",
                    'description': model.get('description', ''),
                    'architecture': model.get('architecture', {})
                })
        
        print(f"  获取到 {len(free_models)} 个 OpenRouter 免费模型")
        return free_models
        
    except Exception as e:
        print(f"  获取 OpenRouter 模型失败: {e}")
        return []

def load_previous_models():
    """加载上一次的模型列表"""
    if PREVIOUS_MODELS_FILE.exists():
        with open(PREVIOUS_MODELS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_current_models(models):
    """保存当前模型列表作为下次对比的基准"""
    with open(PREVIOUS_MODELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(models, f, ensure_ascii=False, indent=2)
    print(f"已保存当前模型列表到 {PREVIOUS_MODELS_FILE}")

def compare_models(previous, current):
    """对比模型列表，识别新增/变化/失效"""
    prev_ids = {m.get('id', m.get('name')): m for m in previous}
    curr_ids = {m.get('id', m.get('name')): m for m in current}
    
    added = [m for m in current if m.get('id', m.get('name')) not in prev_ids]
    removed = [m for m in previous if m.get('id', m.get('name')) not in curr_ids]
    
    # 检查变化（参数大小、上下文长度等）
    changed = []
    for curr_id, curr_model in curr_ids.items():
        if curr_id in prev_ids:
            prev_model = prev_ids[curr_id]
            changes = []
            if prev_model.get('parameters') != curr_model.get('parameters'):
                changes.append(f"参数: {prev_model.get('parameters')} -> {curr_model.get('parameters')}")
            if prev_model.get('context_length') != curr_model.get('context_length'):
                changes.append(f"上下文: {prev_model.get('context_length')} -> {curr_model.get('context_length')}")
            if changes:
                changed.append({'model': curr_model, 'changes': changes})
    
    return {'added': added, 'removed': removed, 'changed': changed}

def verify_model_availability(model):
    """验证模型是否可用（简化版）"""
    # 这里可以添加实际的 API 调用来验证模型
    # 对于 NVIDIA，可以尝试调用 API
    # 对于 OpenRouter，可以检查模型状态
    
    # 简化：只检查模型是否有基本的必要字段
    if not model.get('name') or model.get('name') == 'Unknown':
        return False, "模型名称未知"
    
    # 检查是否是蓝图/教程（不是真正的模型）
    blueprint_keywords = ['blueprint', 'pipeline', 'tutorial', 'workflow', 'build a']
    name_lower = model.get('name', '').lower()
    desc_lower = model.get('description', '').lower()
    
    for kw in blueprint_keywords:
        if kw in name_lower or kw in desc_lower:
            return False, "蓝图/教程，非模型"
    
    return True, "可用"

def generate_html_email(models, comparison, stats):
    """生成美观的 HTML 邮件"""
    
    # 按来源分组
    nvidia_models = [m for m in models if m.get('source') == 'NVIDIA']
    openrouter_models = [m for m in models if m.get('source') == 'OpenRouter']
    
    # 按用途分组
    text_models = [m for m in models if 'text' in m.get('modalities', [])]
    audio_models = [m for m in models if 'audio' in m.get('modalities', [])]
    image_models = [m for m in models if 'image' in m.get('modalities', [])]
    video_models = [m for m in models if 'video' in m.get('modalities', [])]
    
    def format_model_row(m, show_source=True):
        """格式化模型行"""
        name = m.get('name', 'Unknown')
        link = m.get('link', '')
        params = m.get('parameters', 'Unknown')
        context = m.get('context_length', 'Unknown')
        modalities = ', '.join(m.get('modalities', ['text']))
        source = m.get('source', '')
        
        # 链接和模型名合并
        if link:
            name_html = f'<a href="{link}" target="_blank">{name}</a>'
        else:
            name_html = name
        
        source_class = f'source-{source.lower()}'
        
        return f"""
        <tr>
            <td>{name_html}</td>
            {f'<td class="{source_class}">{source}</td>' if show_source else ''}
            <td>{params}</td>
            <td>{context}</td>
            <td><span class="modality-badge modality-{modalities.split(",")[0].strip()}">{modalities}</span></td>
        </tr>
        """
    
    # 生成变更报告
    change_section = ""
    if comparison['added'] or comparison['removed'] or comparison['changed']:
        change_section = """
        <div class="changes-section">
            <h2>📊 模型变更报告</h2>
        """
        
        if comparison['added']:
            change_section += f"""
            <div class="change-box added">
                <h3>✅ 新增模型 ({len(comparison['added'])})</h3>
                <ul>
            """
            for m in comparison['added'][:10]:  # 只显示前10个
                change_section += f'<li>{m.get("name", "Unknown")} ({m.get("source", "")})</li>'
            if len(comparison['added']) > 10:
                change_section += f'<li>... 还有 {len(comparison["added"]) - 10} 个</li>'
            change_section += '</ul></div>'
        
        if comparison['removed']:
            change_section += f"""
            <div class="change-box removed">
                <h3>❌ 失效/移除模型 ({len(comparison['removed'])})</h3>
                <ul>
            """
            for m in comparison['removed'][:10]:
                change_section += f'<li>{m.get("name", "Unknown")} ({m.get("source", "")})</li>'
            if len(comparison['removed']) > 10:
                change_section += f'<li>... 还有 {len(comparison["removed"]) - 10} 个</li>'
            change_section += '</ul></div>'
        
        if comparison['changed']:
            change_section += f"""
            <div class="change-box changed">
                <h3>🔄 变更模型 ({len(comparison['changed'])})</h3>
                <ul>
            """
            for item in comparison['changed'][:10]:
                m = item['model']
                changes = '; '.join(item['changes'])
                change_section += f'<li>{m.get("name", "Unknown")}: {changes}</li>'
            if len(comparison['changed']) > 10:
                change_section += f'<li>... 还有 {len(comparison["changed"]) - 10} 个</li>'
            change_section += '</ul></div>'
        
        change_section += '</div>'
    else:
        change_section = """
        <div class="changes-section">
            <h2>📊 模型变更报告</h2>
            <p>✅ 与上次相比无变化</p>
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>免费模型汇总报告</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #2d3748;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            .container {{
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: white;
                padding: 40px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 2.5em;
                font-weight: 700;
            }}
            .header .subtitle {{
                margin-top: 10px;
                opacity: 0.8;
                font-size: 1.1em;
            }}
            .content {{
                padding: 40px;
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 40px;
            }}
            .stat-card {{
                background: linear-gradient(135deg, #f6f8fb 0%, #e9ecf2 100%);
                border-radius: 12px;
                padding: 24px;
                text-align: center;
                border: 1px solid #e2e8f0;
            }}
            .stat-card .number {{
                font-size: 2.5em;
                font-weight: 700;
                color: #4a5568;
            }}
            .stat-card .label {{
                color: #718096;
                font-size: 0.9em;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .stat-card.nvidia .number {{ color: #76b900; }}
            .stat-card.openrouter .number {{ color: #27ae60; }}
            .stat-card.text .number {{ color: #3182ce; }}
            .stat-card.audio .number {{ color: #805ad5; }}
            .stat-card.image .number {{ color: #ed8936; }}
            .stat-card.video .number {{ color: #e53e3e; }}
            
            .changes-section {{
                margin-bottom: 40px;
            }}
            .change-box {{
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
            }}
            .change-box h3 {{
                margin-top: 0;
                margin-bottom: 12px;
            }}
            .change-box ul {{
                margin: 0;
                padding-left: 20px;
            }}
            .change-box.added {{
                background: #f0fff4;
                border: 1px solid #9ae6b4;
            }}
            .change-box.added h3 {{ color: #276749; }}
            .change-box.removed {{
                background: #fff5f5;
                border: 1px solid #feb2b2;
            }}
            .change-box.removed h3 {{ color: #c53030; }}
            .change-box.changed {{
                background: #fffaf0;
                border: 1px solid #fbd38d;
            }}
            .change-box.changed h3 {{ color: #c05621; }}
            
            h2 {{
                color: #2d3748;
                font-size: 1.5em;
                margin-top: 0;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 2px solid #e2e8f0;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                font-size: 0.95em;
            }}
            th, td {{
                padding: 14px 12px;
                text-align: left;
                border-bottom: 1px solid #e2e8f0;
            }}
            th {{
                background: linear-gradient(135deg, #4a5568 0%, #2d3748 100%);
                color: white;
                font-weight: 600;
                text-transform: uppercase;
                font-size: 0.85em;
                letter-spacing: 0.5px;
            }}
            tr:nth-child(even) {{
                background-color: #f7fafc;
            }}
            tr:hover {{
                background-color: #edf2f7;
            }}
            .source-nvidia {{ color: #76b900; font-weight: 600; }}
            .source-openrouter {{ color: #27ae60; font-weight: 600; }}
            a {{
                color: #4299e1;
                text-decoration: none;
                font-weight: 500;
            }}
            a:hover {{
                color: #2b6cb0;
                text-decoration: underline;
            }}
            .modality-badge {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 20px;
                font-size: 0.85em;
                font-weight: 500;
            }}
            .modality-text {{ background: #ebf8ff; color: #2b6cb0; }}
            .modality-audio {{ background: #faf5ff; color: #6b46c1; }}
            .modality-image {{ background: #fffaf0; color: #c05621; }}
            .modality-video {{ background: #fff5f5; color: #c53030; }}
            
            .section {{
                margin-bottom: 40px;
            }}
            .footer {{
                text-align: center;
                padding: 30px;
                background: #f7fafc;
                color: #718096;
                font-size: 0.9em;
                border-top: 1px solid #e2e8f0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 免费 AI 模型汇总报告</h1>
                <div class="subtitle">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
            
            <div class="content">
                <!-- 统计卡片 -->
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="number">{stats['total']}</div>
                        <div class="label">总计模型</div>
                    </div>
                    <div class="stat-card nvidia">
                        <div class="number">{stats['nvidia']}</div>
                        <div class="label">NVIDIA</div>
                    </div>
                    <div class="stat-card openrouter">
                        <div class="number">{stats['openrouter']}</div>
                        <div class="label">OpenRouter</div>
                    </div>
                    <div class="stat-card text">
                        <div class="number">{stats['text']}</div>
                        <div class="label">文本模型</div>
                    </div>
                    <div class="stat-card audio">
                        <div class="number">{stats['audio']}</div>
                        <div class="label">音频模型</div>
                    </div>
                    <div class="stat-card image">
                        <div class="number">{stats['image']}</div>
                        <div class="label">图像模型</div>
                    </div>
                    <div class="stat-card video">
                        <div class="number">{stats['video']}</div>
                        <div class="label">视频模型</div>
                    </div>
                </div>
                
                {change_section}
                
                <!-- NVIDIA 模型 -->
                <div class="section">
                    <h2>🟢 NVIDIA 免费模型 ({len(nvidia_models)})</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>模型名称</th>
                                <th>参数大小</th>
                                <th>上下文长度</th>
                                <th>用途</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(format_model_row(m, show_source=False) for m in nvidia_models)}
                        </tbody>
                    </table>
                </div>
                
                <!-- OpenRouter 模型 -->
                <div class="section">
                    <h2>🟩 OpenRouter 免费模型 ({len(openrouter_models)})</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>模型名称</th>
                                <th>参数大小</th>
                                <th>上下文长度</th>
                                <th>用途</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(format_model_row(m, show_source=False) for m in openrouter_models)}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <div class="footer">
                <p>此邮件由 Forge 自动发送 | 数据来源: NVIDIA API Catalog & OpenRouter</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html

def send_email(html_content, stats, comparison):
    """发送邮件"""
    email_address = ENV.get('EMAIL_ADDRESS', '3163383667@qq.com')
    email_auth_code = ENV.get('EMAIL_AUTH_CODE', 'oqpigzrtbrnndeih')
    email_smtp_server = ENV.get('EMAIL_SMTP_SERVER', 'smtp.qq.com')
    email_smtp_port = int(ENV.get('EMAIL_SMTP_PORT', '465'))
    
    # 构建邮件主题
    subject = f"免费模型汇总 - {stats['total']} 个模型"
    
    # 添加变更信息到主题
    if comparison['added']:
        subject += f" (新增 {len(comparison['added'])})"
    if comparison['removed']:
        subject += f" (移除 {len(comparison['removed'])})"
    
    msg = MIMEMultipart('alternative')
    msg['From'] = email_address
    msg['To'] = email_address
    msg['Subject'] = subject
    
    # HTML 内容
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    
    # 发送邮件
    try:
        with smtplib.SMTP_SSL(email_smtp_server, email_smtp_port) as server:
            server.login(email_address, email_auth_code)
            server.send_message(msg)
        print(f"[OK] 邮件已发送到 {email_address}")
        return True
    except Exception as e:
        print(f"[ERROR] 邮件发送失败: {e}")
        return False

def update_config_file(config_path, models, source):
    """更新配置文件，删除失效模型"""
    if not config_path.exists():
        print(f"[ERROR] 配置文件不存在: {config_path}")
        return False
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 获取当前有效的模型 ID
    valid_ids = set()
    for m in models:
        model_id = m.get('id', m.get('name', '').lower().replace(' ', '-'))
        if source == 'NVIDIA':
            model_id = model_id.split('/')[-1]  # 只取最后一部分
        valid_ids.add(model_id)
    
    # 过滤 extra_models，只保留有效的
    old_models = config.get('extra_models', [])
    new_models = []
    removed_count = 0
    updated_count = 0
    added_count = 0
    
    # 先处理现有的模型
    for m in old_models:
        m_id = m.get('id', '')
        if m_id in valid_ids:
            # 更新模型信息
            for new_m in models:
                new_id = new_m.get('id', new_m.get('name', '').lower().replace(' ', '-'))
                if source == 'NVIDIA':
                    new_id = new_id.split('/')[-1]
                
                if new_id == m_id:
                    # 更新模态信息
                    modalities = new_m.get('modalities', ['text'])
                    m['supports_multimodal'] = 'image' in modalities or 'video' in modalities
                    m['supports_image'] = 'image' in modalities
                    m['supports_video'] = 'video' in modalities
                    updated_count += 1
                    break
            
            new_models.append(m)
        else:
            removed_count += 1
            print(f"  移除失效模型: {m_id}")
    
    # 添加新的模型
    existing_ids = {m.get('id', '') for m in new_models}
    for m in models:
        model_id = m.get('id', m.get('name', '').lower().replace(' ', '-'))
        if source == 'NVIDIA':
            model_id = model_id.split('/')[-1]
        
        if model_id not in existing_ids:
            # 添加新模型
            modalities = m.get('modalities', ['text'])
            new_model_entry = {
                'id': model_id,
                'name': m.get('name', model_id),
                'supports_multimodal': 'image' in modalities or 'video' in modalities,
                'supports_image': 'image' in modalities,
                'supports_video': 'video' in modalities,
                'probe_source': 'probed',
                'generate_kwargs': {}
            }
            new_models.append(new_model_entry)
            added_count += 1
            print(f"  添加新模型: {model_id}")
    
    config['extra_models'] = new_models
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] 已更新 {config_path.name}: {len(new_models)} 个模型 (更新 {updated_count}, 新增 {added_count}, 移除 {removed_count})")
    return True

def main():
    print("=" * 60)
    print("模型更新脚本 v2")
    print("=" * 60)
    
    # 1. 加载上一次的模型列表
    print("\n[1/6] 加载上一次的模型列表...")
    previous_models = load_previous_models()
    print(f"  上一次有 {len(previous_models)} 个模型")
    
    # 2. 获取当前模型
    print("\n[2/6] 获取当前模型...")
    nvidia_models = fetch_nvidia_models()
    openrouter_models = fetch_openrouter_models()
    
    all_models = []
    
    # 处理 NVIDIA 模型
    for m in nvidia_models:
        m['source'] = 'NVIDIA'
        m['modalities'] = classify_model_modality(m.get('name', ''), m.get('description', ''))
        all_models.append(m)
    
    # 处理 OpenRouter 模型
    for m in openrouter_models:
        m['source'] = 'OpenRouter'
        m['modalities'] = classify_model_modality(m.get('name', ''), m.get('description', ''))
        all_models.append(m)
    
    print(f"  总计 {len(all_models)} 个模型")
    
    # 3. 对比模型列表
    print("\n[3/6] 对比模型列表...")
    comparison = compare_models(previous_models, all_models)
    print(f"  新增: {len(comparison['added'])} 个")
    print(f"  移除: {len(comparison['removed'])} 个")
    print(f"  变更: {len(comparison['changed'])} 个")
    
    # 4. 统计信息
    print("\n[4/6] 计算统计信息...")
    stats = {
        'total': len(all_models),
        'nvidia': len(nvidia_models),
        'openrouter': len(openrouter_models),
        'text': sum(1 for m in all_models if 'text' in m.get('modalities', [])),
        'audio': sum(1 for m in all_models if 'audio' in m.get('modalities', [])),
        'image': sum(1 for m in all_models if 'image' in m.get('modalities', [])),
        'video': sum(1 for m in all_models if 'video' in m.get('modalities', []))
    }
    print(f"  统计: {stats}")
    
    # 5. 生成并发送邮件
    print("\n[5/6] 生成并发送邮件...")
    html_content = generate_html_email(all_models, comparison, stats)
    
    # 保存 HTML 以便预览
    html_file = SKILL_WORKSPACE / "email_report.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"  HTML 报告已保存到 {html_file}")
    
    send_email(html_content, stats, comparison)
    
    # 6. 更新配置文件
    print("\n[6/6] 更新配置文件...")
    update_config_file(NVIDIA_CONFIG, nvidia_models, 'NVIDIA')
    update_config_file(OPENROUTER_CONFIG, openrouter_models, 'OpenRouter')
    
    # 7. 保存当前模型列表作为下次对比的基准
    print("\n[额外] 保存当前模型列表...")
    save_current_models(all_models)
    
    print("\n" + "=" * 60)
    print("完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
