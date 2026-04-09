---
name: copaw-free-model-scraper
description: >
  从 NVIDIA 和 OpenRouter 爬取免费 AI 模型信息，获取模型参数大小、上下文长度和用途分类，
  通过邮件发送汇总报告，并更新本地 CoPaw 配置文件。支持对比变更检测和失效模型清理。
  当用户提到"爬取免费模型"、"获取 NVIDIA/OpenRouter 模型"、"更新模型配置"、"免费 AI 模型汇总"、
  "模型对比"、"清理失效模型"或需要定期获取最新免费模型列表时使用此技能。
---

# Free Model Scraper

一个用于爬取、汇总和管理免费 AI 模型的技能。

## 功能概述

本技能提供以下功能：

1. **数据爬取** - 从 NVIDIA API Catalog 和 OpenRouter 获取免费模型列表
2. **信息提取** - 提取模型参数大小、上下文长度、用途分类（文字/声音/图像/视频）
3. **邮件报告** - 生成美化 HTML 邮件并发送汇总报告
4. **配置更新** - 自动更新 CoPaw 的 `nvidia.json` 和 `open-router.json` 配置文件
5. **变更检测** - 对比上次执行结果，报告新增/变化的模型
6. **失效清理** - 自动移除配置文件中已失效的模型条目

## 前置条件

### 环境要求

- Python 3.x
- `agent-browser` 技能（用于网页爬取）
- `.env` 文件配置以下变量：
  ```
  SMTP_SERVER=smtp.qq.com
  SMTP_PORT=465
  SMTP_USER=your_email@qq.com
  SMTP_AUTH_CODE=your_auth_code
  EMAIL_RECIPIENT=recipient@qq.com
  ```

### 配置文件路径

- NVIDIA 配置：`C:\Users\Administrator\.copaw.secret\providers\custom\nvidia.json`
- OpenRouter 配置：`C:\Users\Administrator\.copaw.secret\providers\custom\open-router.json`

## 使用方法

### 基本用法

运行主脚本执行完整的爬取和更新流程：

```bash
cd skills\free-model-scraper\scripts
python update_models.py
```

### 脚本执行流程

1. **加载现有配置** - 读取当前的 NVIDIA 和 OpenRouter 配置文件
2. **获取 NVIDIA 模型** - 使用 `agent-browser` 爬取 NVIDIA API Catalog 的免费模型
3. **获取 OpenRouter 模型** - 通过 API 获取 OpenRouter 的免费模型
4. **数据处理** - 提取模型参数、上下文长度、用途分类
5. **变更对比** - 与 `previous_models.json` 对比，检测新增/变化/失效模型
6. **配置更新** - 更新配置文件，移除失效模型
7. **邮件发送** - 生成 HTML 报告并发送邮件

### 输出文件

执行后会在 `skills/free-model-scraper/workspace/` 目录下生成：

- `previous_models.json` - 上次执行的模型列表（用于对比）
- `email_report.html` - 生成的邮件 HTML 报告
- `all_free_models.json` - 所有免费模型的完整数据
- `all_free_models.md` - Markdown 格式的模型汇总

## 模型用途分类

脚本会自动根据模型 ID 和描述判断用途：

| 用途 | 关键词示例 |
|------|-----------|
| 文字 (text) | chat, instruct, code, embed, rewrite, summarize |
| 声音 (audio) | tts, stt, voice, speech, whisper, audio |
| 图像 (image) | vision, image, flux, stable-diffusion, dall-e, sd |
| 视频 (video) | video, wanx, sora, kling |

## 邮件报告格式

邮件包含以下内容：

- **汇总统计** - 总模型数、各来源数量、各用途数量
- **变更报告** - 新增/变化/失效模型列表
- **模型列表** - 按来源和用途分类的完整列表，包含可点击链接

## 配置文件格式

更新后的 `extra_models` 数组格式：

```json
{
  "id": "model-id",
  "name": "Model Display Name",
  "supports_multimodal": false,
  "supports_image": false,
  "supports_video": false,
  "probe_source": "probed",
  "generate_kwargs": {}
}
```

## 定时执行

如需定期执行（如每天自动更新），可使用 `cron` 技能创建定时任务：

```
使用 cron 技能创建一个每天上午 9 点执行的定时任务，运行 free-model-scraper 技能
```

## 故障排除

### agent-browser 问题

如果 `agent-browser` 无法启动，确保已安装：

```bash
npx agent-browser --help
```

### SMTP 连接问题

检查 `.env` 文件中的邮件配置是否正确，QQ 邮箱需要使用授权码而非密码。

### 配置文件权限

确保有权限读写 `C:\Users\Administrator\.copaw.secret\providers\custom\` 目录下的文件。

## 注意事项

- 首次运行会创建 `previous_models.json` 基准文件，下次运行才会显示变更对比
- 脚本会自动备份原配置文件，更新前会移除已失效的模型
- OpenRouter 数据优先从本地缓存读取，如需刷新可删除 `openrouter_models_processed.json`
