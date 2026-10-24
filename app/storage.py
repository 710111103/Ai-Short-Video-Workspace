from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = Path(os.environ.get("SHORT_VIDEO_STUDIO_APP_ROOT") or SOURCE_ROOT).resolve()
DATA_ROOT = Path(os.environ.get("SHORT_VIDEO_STUDIO_DATA_ROOT") or (APP_ROOT / "data")).resolve()
TEMPLATES_ROOT = DATA_ROOT / "templates"
PROJECTS_ROOT = DATA_ROOT / "projects"
TEMPLATE_PRODUCTS_ROOT = DATA_ROOT / "template-products"
CONFIG_ROOT = DATA_ROOT / "config"
COUNTERS_FILE = DATA_ROOT / "counters.json"
ENV_FILE = CONFIG_ROOT / ".env"
VALIDATION_FILE = CONFIG_ROOT / "validation.json"
UPDATE_MANIFEST_FILE = CONFIG_ROOT / "update_manifest.json"
VERSION_FILE = APP_ROOT.parent / "_analysis" / "awesome_app_install" / "VERSION"


DEFAULT_ENV = {
    "DEEPSEEK_API_KEY": "",
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_MODEL": "deepseek-v4-flash",
    "DEEPSEEK_THINKING_TYPE": "enabled",
    "DEEPSEEK_REASONING_EFFORT": "high",
    "VISION_API_KEY": "",
    "VISION_BASE_URL": "",
    "VISION_MODEL": "",
    "VISION_TIMEOUT_SECONDS": "90",
    "AI_TEXT_TIMEOUT_SECONDS": "300",
    "DEEPSEEK_REWRITE_TIMEOUT_SECONDS": "180",
    "TAVILY_API_KEY": "",
    "TAVILY_TOPIC": "general",
    "TAVILY_MAX_REFERENCES": "20",
    "GROK2API_BASE_URL": "http://127.0.0.1:8000",
    "GROK2API_API_KEY": "",
    "GROK2API_MODEL": "grok-chat-fast",
    "GROK2API_TIMEOUT_SECONDS": "120",
    "ARK_API_KEY": "",
    "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
    "ARK_IMAGE_MODEL": "doubao-seedream-5-0-260128",
    "ARK_VIDEO_MODEL": "doubao-seedance-2-0-260128",
    "ARK_IMAGE_WEB_SEARCH_COVER": "false",
    "ARK_IMAGE_WEB_SEARCH_SCENE": "false",
    "IMAGE_PROVIDER": "auto",
    "VIDEO_PROVIDER": "off",
    "VIDEO_MOTION_MODE": "key_scenes",
    "VIDEO_CLIP_COUNT": "2",
    "VIDEO_CLIP_DURATION_SECONDS": "5",
    "VIDEO_CLIP_RESOLUTION": "720p",
    "VIDEO_CLIP_TIMEOUT_SECONDS": "1200",
    "AGNES_API_KEY": "",
    "AGNES_BASE_URL": "https://apihub.agnes-ai.com",
    "AGNES_IMAGE_MODEL": "agnes-image-2.1-flash",
    "AGNES_VIDEO_MODEL": "agnes-video-v2.0",
    "APIYI_API_KEY": "",
    "APIYI_BASE_URL": "https://api.apiyi.com",
    "APIYI_IMAGE_REPLACE_ARK": "false",
    "APIYI_IMAGE_MODEL": "gpt-image-2-all",
    "THIRD_PARTY_IMAGE_API_KEY": "",
    "THIRD_PARTY_IMAGE_BASE_URL": "",
    "THIRD_PARTY_IMAGE_MODEL": "gpt-image-2-all",
    "THIRD_PARTY_IMAGE_TIMEOUT_SECONDS": "1200",
    "THIRD_PARTY_IMAGE_RETRIES": "3",
    "CPA_IMAGE_API_KEY": "",
    "CPA_IMAGE_BASE_URL": "http://127.0.0.1:8317/v1",
    "CPA_IMAGE_MODEL": "gpt-image-2.5",
    "CPA_IMAGE_TIMEOUT_SECONDS": "1200",
    "CPA_IMAGE_RETRIES": "2",
    "CHATGPT_IMAGE_OPEN_TARGET": "web",
    "CHATGPT_IMAGE_WEB_URL": "https://chatgpt.com/",
    "CHATGPT_IMAGE_DESKTOP_PATH": "",
    "CHATGPT_IMAGE_AUTO_OPEN": "true",
    "CHATGPT_IMAGE_DELETE_AFTER_SAVE": "true",
    "CHATGPT_IMAGE_CLOSE_BROWSER_AFTER_SAVE": "true",
    "CHATGPT_IMAGE_WAIT_SECONDS": "1200",
    "CHATGPT_IMAGE_STALL_SECONDS": "900",
    "CHATGPT_IMAGE_ACTIVE_LIMIT_SECONDS": "420",
    "CHATGPT_ACCOUNT_PROVIDER": "ant_browser",
    "ANT_BROWSER_API_URL": "http://127.0.0.1:19876",
    "ANT_BROWSER_API_KEY": "",
    "ANT_BROWSER_API_KEY_HEADER": "X-Ant-Api-Key",
    "ANT_BROWSER_LAUNCH_CODES": "",
    "CHATGPT_IMAGE_ACCOUNT_COUNT": "1",
    "CHATGPT_IMAGE_ACCOUNT_LABELS": "",
    "CHATGPT_IMAGE_CDP_BASE_PORT": "9222",
    "CHATGPT_IMAGE_ACCOUNT_COOLDOWN_SECONDS": "180",
    "CHATGPT_IMAGE_QUOTA_COOLDOWN_SECONDS": "18000",
    "CHATGPT_IMAGE_BROWSER_PATH": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "CHATGPT_IMAGE_USER_DATA_DIR": "",
    "CHATGPT_IMAGE_HEADLESS": "false",
    "CHATGPT_IMAGE_TRUE_HEADLESS": "false",
    "IMAGEAI_PLAYGROUND_URL": "https://imageai.centos.hk/",
    "IMAGEAI_PLAYGROUND_USE_SAVED_SETTINGS": "true",
    "IMAGEAI_PLAYGROUND_DELETE_AFTER_SAVE": "true",
    "IMAGEAI_PLAYGROUND_USER_DATA_DIR": "",
    "IMAGEAI_PLAYGROUND_HEADLESS": "false",
    "IMAGEAI_PLAYGROUND_WAIT_SECONDS": "1200",
    "SAU_REPO_PATH": "",
    "SAU_UV_BIN": "uv",
    "SAU_BROWSER_MODE": "headless",
    "SAU_PATCHRIGHT_DOWNLOAD_HOST": "",
    "SAU_XHS_CREATOR_BASE_URL": "https://creator.xiaohongshu.com",
    "VOLC_TTS_APP_KEY": "",
    "VOLC_TTS_ACCESS_KEY": "",
    "VOLC_TTS_RESOURCE_ID": "volc.service_type.10050",
    "VOLC_TTS_SINGLE_RESOURCE_ID": "seed-tts-2.0",
    "VOLC_PODCAST_APP_ID": "",
    "VOLC_PODCAST_ACCESS_TOKEN": "",
    "VOLC_PODCAST_RESOURCE_ID": "volc.service_type.10050",
    "VOLC_TTS_SPEAKER_1": "zh_male_dayixiansheng_v2_saturn_bigtts",
    "VOLC_TTS_SPEAKER_2": "zh_female_mizaitongxue_v2_saturn_bigtts",
    "VOLC_TTS_RANDOM_ORDER": "true",
    "VOLC_TTS_ACTION": "0",
    "VOLC_TTS_SPEECH_RATE": "1.0",
    "VOLC_ASR_APP_KEY": "",
    "VOLC_ASR_ACCESS_KEY": "",
    "VOLC_ASR_MODE": "submit",
    "VOLC_ASR_RESOURCE_ID": "volc.seedasr.auc",
    "VOLC_SPEECH_API_KEY": "",
    "VOLC_ASR_API_KEY_MODE": "submit",
    "VOLC_ASR_API_KEY_RESOURCE_ID": "volc.seedasr.auc",
    "TTS_TIMEOUT_SECONDS": "1200",
    "ASR_TIMEOUT_SECONDS": "900",
    "TIMELINE_TIMEOUT_SECONDS": "1200",
    "VIDEO_TIMEOUT_SECONDS": "3600",
    "DEFAULT_TEMPLATE": "单人讲故事",
    "BGM_VOLUME": "0.18",
    "BGM_AUTO_MODE": "auto",
    "BGM_ONLINE_PROVIDER": "loudly",
    "LOUDLY_API_KEY": "",
    "JAMENDO_CLIENT_ID": "",
    "FREESOUND_API_KEY": "",
    "BGM_DOWNLOAD_URL": "",
    "BGM_VOCAL_AUDIT": "auto",
    "BGM_VOCAL_AUDIT_MAX_CANDIDATES": "5",
    "BGM_VOCAL_AUDIT_TIMEOUT_SECONDS": "240",
}


SECRET_KEYS = {
    "DEEPSEEK_API_KEY",
    "VISION_API_KEY",
    "TAVILY_API_KEY",
    "GROK2API_API_KEY",
    "ARK_API_KEY",
    "AGNES_API_KEY",
    "APIYI_API_KEY",
    "THIRD_PARTY_IMAGE_API_KEY",
    "CPA_IMAGE_API_KEY",
    "VOLC_TTS_APP_KEY",
    "VOLC_TTS_ACCESS_KEY",
    "VOLC_PODCAST_APP_ID",
    "VOLC_PODCAST_ACCESS_TOKEN",
    "VOLC_ASR_APP_KEY",
    "VOLC_ASR_ACCESS_KEY",
    "VOLC_SPEECH_API_KEY",
    "LOUDLY_API_KEY",
    "JAMENDO_CLIENT_ID",
    "FREESOUND_API_KEY",
}


CONFIG_SECTIONS = [
    {
        "key": "bgm",
        "title": "主题音乐与在线曲库",
        "description": "按每期主题自动匹配背景音乐。在线曲库不可用时会自动回退到本地主题音乐。",
        "validator": None,
        "fields": [
            {
                "key": "BGM_AUTO_MODE",
                "label": "BGM 自动模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "推荐选择“按主题自动切换”。项目内人工导入且未带自动元数据的 BGM 会被视为锁定。",
                "options": [
                    {"value": "auto", "label": "按主题自动切换"},
                    {"value": "online", "label": "优先在线"},
                    {"value": "generate", "label": "只生成"},
                    {"value": "download", "label": "只下载"},
                    {"value": "template", "label": "频道固定音乐"},
                    {"value": "off", "label": "关闭"},
                ],
            },
            {
                "key": "BGM_ONLINE_PROVIDER",
                "label": "BGM 在线来源",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "推荐 Loudly：从专业完整配乐中按主题、情绪和节奏自动选曲；Jamendo 为开放曲库备用，Freesound 仅保留兼容。",
                "options": [
                    {"value": "loudly", "label": "Loudly（推荐，优质完整配乐）"},
                    {"value": "jamendo", "label": "Jamendo（免费开放曲库）"},
                    {"value": "freesound", "label": "Freesound（旧声音素材库）"},
                    {"value": "none", "label": "不联网"},
                ],
            },
            {
                "key": "LOUDLY_API_KEY",
                "label": "Loudly API Key",
                "required": False,
                "secret": True,
                "kind": "password",
                "help": "在 Loudly Developers 获取 API Key。系统按主题、情绪、类型、BPM 和时长挑选无人声完整配乐。",
            },
            {
                "key": "JAMENDO_CLIENT_ID",
                "label": "Jamendo Client ID",
                "required": False,
                "secret": True,
                "kind": "password",
                "help": "在 Jamendo Developer 创建应用后填写 Client ID。系统只选择可下载、无人声且允许商业复用的完整配乐。",
            },
            {
                "key": "FREESOUND_API_KEY",
                "label": "Freesound API Key",
                "required": False,
                "secret": True,
                "kind": "password",
                "help": "粘贴 Freesound 应用详情页中的 API Key，不是 OAuth Client Secret。回调 URL 不需要填到本程序。",
            },
            {
                "key": "BGM_VOLUME",
                "label": "BGM 音量",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 0.18。口播优先，背景音乐会先做响度标准化再轻铺底。",
            },
            {
                "key": "BGM_DOWNLOAD_URL",
                "label": "自有音乐下载 URL",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "选填。仅填写你拥有版权或可商用授权的 mp3/wav 地址。",
            },
        ],
    },
    {
        "key": "deepseek",
        "title": "DeepSeek 文本生成",
        "description": "用于生成文案 content.md，也可作为结构化内容改写模型。",
        "validator": "deepseek",
        "fields": [
            {
                "key": "DEEPSEEK_API_KEY",
                "label": "DeepSeek API 密钥",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "把 DeepSeek 秘钥粘贴进来，留空则保持原值。",
            },
            {
                "key": "DEEPSEEK_MODEL",
                "label": "DeepSeek 模型",
                "required": False,
                "secret": False,
                "kind": "model_select",
                "help": "点击“同步模型”读取当前 Base URL 的 /models；同步后可下拉选择，也可直接输入模型 ID。",
                "options": [],
            },
            {
                "key": "DEEPSEEK_BASE_URL",
                "label": "DeepSeek Base URL",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "官方地址使用 https://api.deepseek.com；NewAPI 通常填写以 /v1 结尾的兼容地址。",
            },
            {
                "key": "DEEPSEEK_THINKING_TYPE",
                "label": "Thinking 模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "控制是否启用思考模式。",
                "options": [
                    {"value": "enabled", "label": "enabled"},
                    {"value": "disabled", "label": "disabled"},
                ],
            },
            {
                "key": "DEEPSEEK_REASONING_EFFORT",
                "label": "Reasoning 强度",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "官方常用等级为 high / max。",
                "options": [
                    {"value": "low", "label": "low"},
                    {"value": "medium", "label": "medium"},
                    {"value": "high", "label": "high"},
                    {"value": "max", "label": "max"},
                ],
            },
        ],
    },
    {
        "key": "tavily",
        "title": "Tavily 搜索增强",
        "description": "用于联网检索参考资料；不填时仍可走本地演示流程。",
        "validator": "tavily",
        "fields": [
            {
                "key": "TAVILY_API_KEY",
                "label": "Tavily API 密钥",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "联网搜索增强，可选；留空则使用无密钥模式或本地演示流程。",
            },
            {
                "key": "TAVILY_TOPIC",
                "label": "默认检索话题",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "一般用 general 就够了。",
                "options": [
                    {"value": "general", "label": "general"},
                    {"value": "news", "label": "news"},
                    {"value": "finance", "label": "finance"},
                ],
            },
            {
                "key": "TAVILY_MAX_REFERENCES",
                "label": "最大参考条数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "建议 10 到 20。",
            },
        ],
    },
    {
        "key": "grok_research",
        "title": "Grok 联网研究（Grok2API）",
        "description": "通过本机 Grok2API 调用 Grok 联网搜索，为挖题补充最新事件、论文、机构页面和公开报道。",
        "validator": "grok_research",
        "fields": [
            {
                "key": "GROK2API_BASE_URL",
                "label": "Grok2API 地址",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 http://127.0.0.1:8000。系统会调用 /v1/models 与 /v1/responses。",
            },
            {
                "key": "GROK2API_API_KEY",
                "label": "Grok2API 客户端 Key",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "填写 Grok2API“密钥”页面创建的客户端 Key（g2a_...），不是后台管理员密码。",
            },
            {
                "key": "GROK2API_MODEL",
                "label": "Grok 检索模型",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 grok-chat-fast；也可填写 Grok2API 模型路由页中支持 Responses 的模型名。",
            },
            {
                "key": "GROK2API_TIMEOUT_SECONDS",
                "label": "联网研究超时（秒）",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 120 秒。超时会回退到其他搜索渠道，不会卡死挖题任务。",
            },
        ],
    },
    {
        "key": "vision_judge",
        "title": "真实成图视觉复评",
        "description": "首镜和主封面完成两张候选后，用支持图片输入的 OpenAI 兼容模型直接看图复评；未配置时继续使用本地画质、OCR 与语义评分。",
        "validator": None,
        "fields": [
            {
                "key": "VISION_API_KEY",
                "label": "视觉模型 API Key",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "填写支持图片输入的 OpenAI 兼容服务密钥，只用于首镜与主封面的真实成图复评。",
            },
            {
                "key": "VISION_BASE_URL",
                "label": "视觉模型 Base URL",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "填写 OpenAI 兼容接口的 Base URL，例如服务商提供的 /v1 地址。",
            },
            {
                "key": "VISION_MODEL",
                "label": "视觉模型名称",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "填写该服务支持图片输入的模型名。Key、Base URL、模型名三项齐全后自动启用。",
            },
            {
                "key": "VISION_TIMEOUT_SECONDS",
                "label": "单张复评等待秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 90 秒；只复评首镜与主封面候选，不影响普通镜头。",
            },
        ],
    },
    {
        "key": "ark_image",
        "title": "火山方舟 文生图",
        "description": "用于豆包 Seedream 模型生成场景图与封面图。",
        "validator": "ark_image",
        "fields": [
            {
                "key": "ARK_API_KEY",
                "label": "火山方舟 API 密钥",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "用于豆包 Seedream 文生图，必填。",
            },
            {
                "key": "ARK_IMAGE_MODEL",
                "label": "文生图模型 ID",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "优先使用新版 Seedream 5.0。",
                "options": [
                    {"value": "doubao-seedream-5-0-260128", "label": "doubao-seedream-5-0-260128（官方示例）"},
                    {"value": "doubao-seedream-5.0-lite", "label": "doubao-seedream-5.0-lite（效果好推荐）"},
                    {"value": "doubao-seedream-4.5", "label": "doubao-seedream-4.5（免费额度多）"},
                    {"value": "seedream-5.0", "label": "seedream-5.0（兼容旧写法）"},
                    {"value": "seedream-4.5", "label": "seedream-4.5（兼容旧写法）"},
                ],
            },
            {
                "key": "ARK_IMAGE_WEB_SEARCH_COVER",
                "label": "封面出图联网",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "是否允许封面生成时额外联网检索。",
                "options": [
                    {"value": "false", "label": "关闭"},
                    {"value": "true", "label": "开启"},
                ],
            },
            {
                "key": "ARK_IMAGE_WEB_SEARCH_SCENE",
                "label": "场景出图联网",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "是否允许场景图生成时额外联网检索。",
                "options": [
                    {"value": "false", "label": "关闭"},
                    {"value": "true", "label": "开启"},
                ],
            },
        ],
    },
    {
        "key": "capsule_media",
        "title": "动态镜头与 Capsule API",
        "description": "把关键场景图交给 Seedance 生成短动态镜头；普通场景仍复用原图，控制成本并提升画面连续性。Agnes 可作为图片 API 入口。",
        "validator": "capsule_media",
        "fields": [
            {
                "key": "VIDEO_PROVIDER",
                "label": "动态镜头供应商",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "关闭时沿用静态图轻运动；Seedance 会把选中的关键场景图转为无声视频。",
                "options": [
                    {"value": "off", "label": "关闭（保持当前静态图链路）"},
                    {"value": "auto", "label": "自动选择可用视频 API"},
                    {"value": "seedance", "label": "火山方舟 Seedance 图生视频"},
                ],
            },
            {
                "key": "VIDEO_MOTION_MODE",
                "label": "动态镜头范围",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "推荐只生成首镜、核心证据和反转等关键镜头，不给每张图都生成视频。",
                "options": [
                    {"value": "key_scenes", "label": "关键镜头（推荐）"},
                    {"value": "opening_only", "label": "仅首镜"},
                    {"value": "all", "label": "全部场景"},
                    {"value": "off", "label": "关闭"},
                ],
            },
            {
                "key": "ARK_VIDEO_MODEL",
                "label": "Seedance 视频模型 ID",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 doubao-seedance-2-0-260128，使用上方火山方舟 API 密钥。",
            },
            {
                "key": "VIDEO_CLIP_COUNT",
                "label": "每期动态镜头数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "关键镜头模式默认生成 2 段；已生成且来源未变化的片段会直接复用。",
            },
            {
                "key": "VIDEO_CLIP_DURATION_SECONDS",
                "label": "单段时长（秒）",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "Seedance 支持 4 至 15 秒，推荐 5 秒。",
            },
            {
                "key": "VIDEO_CLIP_RESOLUTION",
                "label": "动态镜头分辨率",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "720p 适合短视频生产速度和成本。",
                "options": [
                    {"value": "480p", "label": "480p"},
                    {"value": "720p", "label": "720p（推荐）"},
                    {"value": "1080p", "label": "1080p"},
                ],
            },
            {
                "key": "AGNES_API_KEY",
                "label": "Agnes API Key",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "选择 Agnes 图片入口时填写。",
            },
            {
                "key": "AGNES_IMAGE_MODEL",
                "label": "Agnes 图片模型",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 agnes-image-2.1-flash。",
            },
        ],
    },
    {
        "key": "doubao_tts",
        "title": "豆包语音播客大模型",
        "description": "单人讲述和双人播客共用同一套播客模型认证。请填写同一个已开通播客服务的应用所显示的 APP ID 与 Access Token。",
        "validator": "volc_tts",
        "fields": [
            {
                "key": "VOLC_PODCAST_APP_ID",
                "label": "播客模型 APP ID",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "来自火山引擎豆包语音旧版控制台中、已开通语音播客大模型的同一个应用。单人和双人模式都使用它。",
            },
            {
                "key": "VOLC_PODCAST_ACCESS_TOKEN",
                "label": "播客模型 Access Token",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "填写该应用同一行的 Access Token。不要填写 Secret Key，也不要填写火山方舟 API Key。",
            },
            {
                "key": "VOLC_PODCAST_RESOURCE_ID",
                "label": "播客模型资源 ID",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "官方播客接口固定使用 volc.service_type.10050，通常无需修改。",
            },
            {
                "key": "VOLC_TTS_SPEAKER_1",
                "label": "TTS 音色 1",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "建议第一个说话人选择偏男性或旁白类音色。",
                "options": [
                    {"value": "zh_male_dayixiansheng_v2_saturn_bigtts", "label": "大仪先生 v2（男声）"},
                    {"value": "zh_female_mizaitongxue_v2_saturn_bigtts", "label": "蜜仔同学 v2（女声）"},
                    {"value": "zh_female_cancan_uranus_bigtts", "label": "灿灿"},
                    {"value": "zh_male_wennuanahuaxu_moon_bigtts", "label": "温暖阿华"},
                ],
            },
            {
                "key": "VOLC_TTS_SPEAKER_2",
                "label": "TTS 音色 2",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "建议第二个说话人和音色 1 拉开差异。",
                "options": [
                    {"value": "zh_female_mizaitongxue_v2_saturn_bigtts", "label": "蜜仔同学 v2（女声）"},
                    {"value": "zh_male_dayixiansheng_v2_saturn_bigtts", "label": "大仪先生 v2（男声）"},
                    {"value": "zh_female_cancan_uranus_bigtts", "label": "灿灿"},
                    {"value": "zh_male_wennuanahuaxu_moon_bigtts", "label": "温暖阿华"},
                ],
            },
            {
                "key": "VOLC_TTS_RANDOM_ORDER",
                "label": "发言人随机起始",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "随机表示每次按音色 1 / 音色 2 轮换起始，固定表示始终从音色 1 开始。",
                "options": [
                    {"value": "true", "label": "发言人随机"},
                    {"value": "false", "label": "发言人固定（每次都按音色 1 -> 音色 2）"},
                ],
            },
            {
                "key": "VOLC_TTS_ACTION",
                "label": "生成类型",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "默认使用总结生成播客。",
                "options": [
                    {"value": "0", "label": "总结生成播客（默认）"},
                    {"value": "3", "label": "一人一句对话"},
                ],
            },
            {
                "key": "VOLC_TTS_SPEECH_RATE",
                "label": "语速",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "1.0 表示默认语速。",
            },
        ],
    },
    {
        "key": "volc_asr",
        "title": "豆包录音文件识别",
        "description": "新版 API Key 为主通道，只用识别时间校准字幕；识别失败时自动使用本地真实停顿对齐，不会中断成片。",
        "validator": "volc_asr",
        "fields": [
            {
                "key": "VOLC_SPEECH_API_KEY",
                "label": "豆包语音 API Key",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "填写豆包语音控制台“API Key 管理”里创建的 Key。新版接口只需要这一项，不需要旧版 App ID。",
            },
            {
                "key": "VOLC_ASR_API_KEY_RESOURCE_ID",
                "label": "新版识别资源 ID",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "录音文件识别 2.0 使用 volc.seedasr.auc；只有开通极速版时才选择 turbo。",
                "options": [
                    {"value": "volc.seedasr.auc", "label": "录音文件识别 2.0（推荐）"},
                    {"value": "volc.bigasr.auc", "label": "录音文件识别 1.0"},
                    {"value": "volc.bigasr.auc_turbo", "label": "录音文件识别极速版"},
                ],
            },
            {
                "key": "VOLC_ASR_API_KEY_MODE",
                "label": "新版识别模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "2.0/1.0 使用异步提交；只有极速版资源使用同步极速识别。",
                "options": [
                    {"value": "submit", "label": "异步提交（推荐）"},
                    {"value": "flash", "label": "同步极速版"},
                ],
            },
            {
                "key": "VOLC_ASR_APP_KEY",
                "label": "旧版 ASR App ID（兼容）",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "仅兼容以前已经保存的旧版账号；找不到旧版入口时保持为空即可。",
            },
            {
                "key": "VOLC_ASR_ACCESS_KEY",
                "label": "旧版 ASR Access Token（兼容）",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "仅兼容旧版鉴权；新版 API Key 已配置时不会优先使用这里。",
            },
            {
                "key": "VOLC_ASR_MODE",
                "label": "识别模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "默认 submit。",
                "options": [
                    {"value": "submit", "label": "submit"},
                    {"value": "query", "label": "query"},
                ],
            },
            {
                "key": "VOLC_ASR_RESOURCE_ID",
                "label": "资源 ID",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 volc.seedasr.auc。",
            },
        ],
    },
    {
        "key": "image_provider",
        "title": "图片生成入口",
        "description": "选择场景图和封面图使用哪个出图入口；ChatGPT 网页与 Classic 桌面接力已完全分开。",
        "validator": None,
        "fields": [
            {
                "key": "IMAGE_PROVIDER",
                "label": "图片生成供应商",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "手动选择某个入口时会锁定该入口，失败直接报错；自动选择才会按队列兜底。",
                "options": [
                    {"value": "auto_no_apiyi", "label": "自动选择（不使用第三方接口）"},
                    {"value": "auto", "label": "自动选择（原逻辑）"},
                    {"value": "ark", "label": "火山方舟 Seedream"},
                    {"value": "agnes", "label": "Agnes Image 2.1 Flash（API）"},
                    {"value": "imageai_playground", "label": "GPT Image Playground 网页"},
                    {"value": "newapi", "label": "NewAPI / OpenAI Image"},
                    {"value": "third_party", "label": "第三方 OpenAI 兼容"},
                    {"value": "apiyi", "label": "API易 / OpenAI 兼容"},
                    {"value": "chatgpt_web_auto", "label": "ChatGPT 网页自动化"},
                    {"value": "chatgpt_web_handoff", "label": "ChatGPT 网页接力"},
                    {"value": "chatgpt_desktop_handoff", "label": "ChatGPT Classic 手动接力（粘贴/保存）"},
                ],
            },
            {
                "key": "CHATGPT_ACCOUNT_PROVIDER",
                "label": "ChatGPT 账号来源",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "推荐交给 Ant Browser 管理登录资料，本系统只按快捷打开码启动实例并轮询。",
                "options": [
                    {"value": "ant_browser", "label": "Ant Browser 实例池"},
                    {"value": "local", "label": "本工具旧版本地账号池"},
                ],
            },
            {
                "key": "ANT_BROWSER_API_URL",
                "label": "Ant Browser Launch API",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 http://127.0.0.1:19876；以 Ant Browser 设置页显示的启动 API 地址为准。",
            },
            {
                "key": "ANT_BROWSER_LAUNCH_CODES",
                "label": "Ant Browser 快捷打开码",
                "required": False,
                "secret": False,
                "kind": "textarea",
                "help": "逗号或换行分隔。留空时自动读取全部带快捷码的实例，并按列表顺序轮询。",
            },
            {
                "key": "ANT_BROWSER_API_KEY",
                "label": "Ant Browser API Key",
                "required": False,
                "secret": True,
                "kind": "password",
                "help": "Ant Browser 启用了 Launch API 认证时填写。",
            },
            {
                "key": "ANT_BROWSER_API_KEY_HEADER",
                "label": "Ant Browser 认证 Header",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 X-Ant-Api-Key。",
            },
            {
                "key": "CHATGPT_IMAGE_BROWSER_PATH",
                "label": "Chrome 路径",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "ChatGPT 网页自动化使用的 Chrome/Edge 路径；默认使用本机 Chrome。",
            },
            {
                "key": "CHATGPT_IMAGE_USER_DATA_DIR",
                "label": "ChatGPT 自动化登录资料夹",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "留空则使用 data/config/chatgpt-browser-profile。第一次运行会打开浏览器，请登录一次 ChatGPT。",
            },
            {
                "key": "CHATGPT_IMAGE_ACCOUNT_COUNT",
                "label": "ChatGPT 生图账号数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "1-12 个账号。每个账号使用独立浏览器资料夹和独立本地端口，生图失败会自动轮询下一个。",
            },
            {
                "key": "CHATGPT_IMAGE_ACCOUNT_LABELS",
                "label": "账号别名",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "可选，用英文逗号分隔，例如：主账号,备用账号,团队账号。仅用于页面显示。",
            },
            {
                "key": "CHATGPT_IMAGE_CDP_BASE_PORT",
                "label": "账号池起始端口",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 9222；后续账号依次使用 9223、9224。端口只监听本机 127.0.0.1。",
            },
            {
                "key": "CHATGPT_IMAGE_ACTIVE_LIMIT_SECONDS",
                "label": "单账号单图最长活跃等待",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 420 秒。超过后不再把动画误判为正常，会冷却当前账号并自动换号。",
            },
            {
                "key": "CHATGPT_IMAGE_ACCOUNT_COOLDOWN_SECONDS",
                "label": "失败账号冷却秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "普通停滞默认冷却 180 秒；额度或套餐限制默认冻结 5 小时，页面明确给出恢复时间时优先使用页面时间。",
            },
            {
                "key": "CHATGPT_IMAGE_HEADLESS",
                "label": "后台端口模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "默认显示普通 Chrome；若选择后台运行但触发安全验证，会自动切回可见窗口并等待处理。",
                "options": [
                    {"value": "false", "label": "显示普通 Chrome（推荐）"},
                    {"value": "true", "label": "后台运行（验证时自动显示）"},
                ],
            },
            {
                "key": "CHATGPT_IMAGE_CLOSE_BROWSER_AFTER_SAVE",
                "label": "生图后关闭浏览器",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "图片下载并保存成功后关闭当前账号的 Chrome；登录资料仍保留，下次生图会自动恢复。",
                "options": [
                    {"value": "true", "label": "自动关闭（推荐）"},
                    {"value": "false", "label": "保持浏览器常驻"},
                ],
            },
            {
                "key": "CHATGPT_IMAGE_OPEN_TARGET",
                "label": "旧版 ChatGPT 接力打开方式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "仅用于兼容旧配置；新配置请直接选择“网页接力”或“Classic 桌面接力”。",
                "options": [
                    {"value": "web", "label": "网页"},
                    {"value": "desktop", "label": "桌面软件"},
                    {"value": "both", "label": "网页 + 桌面软件"},
                ],
            },
            {
                "key": "CHATGPT_IMAGE_WEB_URL",
                "label": "ChatGPT 网页地址",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 https://chatgpt.com/；使用你当前浏览器登录态，不在本地保存账号密码。",
            },
            {
                "key": "CHATGPT_IMAGE_DESKTOP_PATH",
                "label": "ChatGPT 桌面程序路径",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "Classic 桌面接力默认使用 chatgpt://；也可填写桌面程序完整路径。",
            },
            {
                "key": "CHATGPT_IMAGE_AUTO_OPEN",
                "label": "自动打开 ChatGPT",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "开启后，每张图会自动复制提示词并打开 ChatGPT 接力页。",
                "options": [
                    {"value": "true", "label": "开启"},
                    {"value": "false", "label": "关闭，仅生成接力页"},
                ],
            },
            {
                "key": "CHATGPT_IMAGE_DELETE_AFTER_SAVE",
                "label": "生成后删除 ChatGPT 会话",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "开启后，ChatGPT 网页自动化保存图片成功后，会尝试删除本次生成图片的会话，避免左侧历史列表堆积。删除失败不影响图片保存。",
                "options": [
                    {"value": "true", "label": "开启（推荐）"},
                    {"value": "false", "label": "关闭"},
                ],
            },
            {
                "key": "CHATGPT_IMAGE_WAIT_SECONDS",
                "label": "等待保存图片秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "程序会等待目标图片文件出现；建议 600-1800 秒。",
            },
            {
                "key": "IMAGEAI_PLAYGROUND_URL",
                "label": "GPT Image Playground 地址",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认 https://imageai.centos.hk/。选择 GPT Image Playground 网页入口时，程序会打开该网站、输入提示词、点击生成并抓取图片。",
            },
            {
                "key": "IMAGEAI_PLAYGROUND_USE_SAVED_SETTINGS",
                "label": "使用网站已保存配置",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "开启后只打开网站并输入提示词，沿用你在 imageai.centos.hk 手动保存的密钥和模型配置；关闭后才会从短片工坊注入第三方 Base URL/API Key。",
                "options": [
                    {"value": "true", "label": "开启（推荐）"},
                    {"value": "false", "label": "关闭，注入短片工坊配置"},
                ],
            },
            {
                "key": "IMAGEAI_PLAYGROUND_DELETE_AFTER_SAVE",
                "label": "生成后清理 Playground 历史",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "开启后，每张图保存到项目目录后会清空 imageai.centos.hk 的本地任务/图片历史，避免网站列表堆积；不会清空网站密钥配置。",
                "options": [
                    {"value": "true", "label": "开启（推荐）"},
                    {"value": "false", "label": "关闭"},
                ],
            },
            {
                "key": "IMAGEAI_PLAYGROUND_USER_DATA_DIR",
                "label": "Playground 浏览器资料夹",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "留空则使用 data/config/imageai-playground-profile。用于保存该网站本地设置，不会保存账号密码。",
            },
            {
                "key": "IMAGEAI_PLAYGROUND_HEADLESS",
                "label": "Playground 无头模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "建议保持关闭，便于观察网站是否正常出图。",
                "options": [
                    {"value": "false", "label": "关闭（推荐）"},
                    {"value": "true", "label": "开启"},
                ],
            },
            {
                "key": "IMAGEAI_PLAYGROUND_WAIT_SECONDS",
                "label": "Playground 等待秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "单张图等待时间，默认 900 秒；网站排队慢时可调到 1800。",
            },
        ],
    },
    {
        "key": "apiyi_image",
        "title": "API易 / OpenAI 兼容文生图",
        "description": "兼容保留的 API易配置，也可填写其它 OpenAI 兼容网关。",
        "validator": "apiyi_image",
        "fields": [
            {
                "key": "APIYI_API_KEY",
                "label": "API易 / 兼容 API 密钥",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "旧配置兼容项。新接入第三方服务，建议填写下面的“第三方 OpenAI 兼容文生图”。",
            },
            {
                "key": "APIYI_BASE_URL",
                "label": "API易 / 兼容 Base URL",
                "required": True,
                "secret": False,
                "kind": "text",
                "help": "API易官方可直接填 https://api.apiyi.com；也支持填 /v1 或完整图片端点，程序会自动归一化。",
            },
            {
                "key": "APIYI_IMAGE_MODEL",
                "label": "图片模型 ID",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "按 API易官方文档，默认使用 gpt-image-2-all。",
            },
            {
                "key": "APIYI_IMAGE_REPLACE_ARK",
                "label": "优先使用 API易出图",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "开启后，场景图和封面图会优先走这里的兼容接口。",
                "options": [
                    {"value": "false", "label": "关闭"},
                    {"value": "true", "label": "开启"},
                ],
            },
        ],
    },
    {
        "key": "cpa_image",
        "title": "本地 CPA 生图",
        "description": "通过本机 CPA 直接调用图片模型，不启动指纹浏览器；账号与凭据轮换由 CPA 管理。",
        "validator": None,
        "fields": [
            {
                "key": "CPA_IMAGE_API_KEY",
                "label": "CPA API 密钥",
                "required": False,
                "secret": True,
                "kind": "secret",
                "help": "可留空；默认复用当前本地 DeepSeek/Gemini CPA 的访问密钥。",
            },
            {
                "key": "CPA_IMAGE_BASE_URL",
                "label": "CPA Base URL",
                "required": True,
                "secret": False,
                "kind": "text",
                "help": "本机默认 http://127.0.0.1:8317/v1。",
            },
            {
                "key": "CPA_IMAGE_MODEL",
                "label": "CPA 图片模型",
                "required": True,
                "secret": False,
                "kind": "select",
                "help": "选择 CPA 当前提供的图片模型。",
                "options": [
                    {"value": "gpt-image-2.5", "label": "GPT Image 2.5"},
                    {"value": "gpt-image-2.5-flare", "label": "GPT Image 2.5 Flare"},
                    {"value": "gpt-image-2.5-sunburst", "label": "GPT Image 2.5 Sunburst"},
                    {"value": "gpt-image-2", "label": "GPT Image 2"},
                    {"value": "gpt-image-1.5", "label": "GPT Image 1.5"},
                    {"value": "grok-imagine-image-2.0", "label": "Grok Imagine Image 2.0"},
                    {"value": "grok-imagine-image-quality", "label": "Grok Imagine Image Quality"},
                ],
            },
            {
                "key": "CPA_IMAGE_TIMEOUT_SECONDS",
                "label": "单张超时秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 1200 秒。",
            },
            {
                "key": "CPA_IMAGE_RETRIES",
                "label": "失败重试次数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 2 次；仅重试当前图片。",
            },
        ],
    },
    {
        "key": "third_party_image",
        "title": "第三方 OpenAI 兼容文生图",
        "description": "参考 CookSleep/gpt_image_playground 的 OpenAI 兼容接入方式，支持 NewAPI / One API / 各类中转站图片 API。",
        "validator": "third_party_image",
        "fields": [
            {
                "key": "THIRD_PARTY_IMAGE_API_KEY",
                "label": "第三方 API 密钥",
                "required": True,
                "secret": True,
                "kind": "secret",
                "help": "填写第三方中转站的 API Key。",
            },
            {
                "key": "THIRD_PARTY_IMAGE_BASE_URL",
                "label": "第三方 Base URL",
                "required": True,
                "secret": False,
                "kind": "text",
                "help": "NewAPI 填你的服务器地址即可，例如 https://你的newapi服务器地址；也可填 /v1 或完整 /v1/images/generations，程序会自动归一化。",
            },
            {
                "key": "THIRD_PARTY_IMAGE_MODEL",
                "label": "图片模型 ID",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "按 NewAPI 渠道支持填写，例如 gpt-image-1、dall-e-3、gpt-image-2-all 或其它中转站图片模型名；不要填 newapi_channel_conn 这类渠道连通性测试名。",
            },
            {
                "key": "THIRD_PARTY_IMAGE_TIMEOUT_SECONDS",
                "label": "单张超时秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 480 秒，慢速中转站可调到 900-1800。",
            },
            {
                "key": "THIRD_PARTY_IMAGE_RETRIES",
                "label": "失败重试次数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 3 次。手动选择第三方入口时只重试该入口，不会切换到 ChatGPT。",
            },
        ],
    },
    {
        "key": "task_waiting",
        "title": "任务等待时间",
        "description": "网络或模型较慢时继续等待，并持续显示运行状态；超过最终上限才停止。",
        "validator": None,
        "fields": [
            {
                "key": "AI_TEXT_TIMEOUT_SECONDS",
                "label": "AI 文案等待秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 300 秒，适用于脚本生成和内容分析。",
            },
            {
                "key": "DEEPSEEK_REWRITE_TIMEOUT_SECONDS",
                "label": "AI 总编等待秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 180 秒，慢速深度思考模型可继续调高。",
            },
            {
                "key": "TTS_TIMEOUT_SECONDS",
                "label": "配音等待秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 1200 秒。",
            },
            {
                "key": "ASR_TIMEOUT_SECONDS",
                "label": "字幕识别等待秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 900 秒。",
            },
            {
                "key": "VIDEO_TIMEOUT_SECONDS",
                "label": "成片合成等待秒数",
                "required": False,
                "secret": False,
                "kind": "number",
                "help": "默认 3600 秒，长视频可以继续调高。",
            },
        ],
    },
    {
        "key": "local",
        "title": "本地默认值",
        "description": "不涉及联网鉴权的常用默认值。",
        "validator": None,
        "fields": [
            {
                "key": "DEFAULT_TEMPLATE",
                "label": "默认模板",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "默认创建项目时使用的模板。",
                "options": [
                    {"value": "单人讲故事", "label": "单人讲故事"},
                    {"value": "双人讲故事", "label": "双人讲故事"},
                    {"value": "单人图文", "label": "单人图文"},
                ],
            },
        ],
    },
    {
        "key": "social_auto_upload",
        "title": "自动发布与浏览器配置",
        "description": "对接 dreammis/social-auto-upload，在投放页调用抖音、快手、小红书自动发布。",
        "validator": "social_auto_upload",
        "fields": [
            {
                "key": "SAU_REPO_PATH",
                "label": "social-auto-upload 仓库目录",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "选填。填写 dreammis/social-auto-upload 的本地仓库目录后，投放页会直接调用这套自动发布能力。",
            },
            {
                "key": "SAU_UV_BIN",
                "label": "uv 命令",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "填写 uv 可执行命令或完整路径。默认是 uv；如果系统 PATH 里找不到 uv，就在这里填实际安装位置。",
            },
            {
                "key": "SAU_BROWSER_MODE",
                "label": "浏览器模式",
                "required": False,
                "secret": False,
                "kind": "select",
                "help": "扫码登录、手动确认页面或排查问题时使用 headed；稳定运行时可用 headless。",
                "options": [
                    {"value": "headless", "label": "headless"},
                    {"value": "headed", "label": "headed"},
                ],
            },
            {
                "key": "SAU_PATCHRIGHT_DOWNLOAD_HOST",
                "label": "Patchright 下载镜像",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "可选。如果安装浏览器依赖要走国内镜像，可以填写 npmmirror 等下载源；留空使用默认地址。",
            },
            {
                "key": "SAU_XHS_CREATOR_BASE_URL",
                "label": "小红书创作者后台地址",
                "required": False,
                "secret": False,
                "kind": "text",
                "help": "默认使用 https://creator.xiaohongshu.com。只有在你的环境需要自定义域名或代理地址时才修改。",
            },
        ],
    },
]

CONFIG_SECTIONS = [section for section in CONFIG_SECTIONS if section.get("key") != "bgm"]


def _repair_social_auto_upload_section_text() -> None:
    field_overrides = {
        "SAU_REPO_PATH": {
            "label": "social-auto-upload 仓库目录",
            "help": "选填。填写 dreammis/social-auto-upload 的本地仓库目录后，投放页会直接调用这套自动发布能力。",
        },
        "SAU_UV_BIN": {
            "label": "uv 命令",
            "help": "填写 uv 可执行命令或完整路径。默认是 uv；如果系统 PATH 里找不到 uv，就在这里填实际安装位置。",
        },
        "SAU_BROWSER_MODE": {
            "label": "浏览器模式",
            "help": "默认用 headless。需要扫码登录、手动确认页面或排查问题时，切到 headed 会直接弹出可见浏览器；平时稳定运行可继续用 headless。",
        },
        "SAU_PATCHRIGHT_DOWNLOAD_HOST": {
            "label": "Patchright 下载镜像",
            "help": "可选。如果你希望安装浏览器依赖时走国内镜像，可以填写 npmmirror 等下载源；留空就使用默认地址。",
        },
        "SAU_XHS_CREATOR_BASE_URL": {
            "label": "小红书创作者后台地址",
            "help": "默认使用 https://creator.xiaohongshu.com。只有在你的环境需要自定义域名或代理地址时才修改。",
        },
    }
    for section in CONFIG_SECTIONS:
        if section.get("key") != "social_auto_upload":
            continue
        section["title"] = "自动发布与浏览器配置"
        section["description"] = "如果你要在投放页里直接登录、检测账号并自动发布到抖音或小红书，这里填写 dreammis/social-auto-upload 相关路径与运行参数。"
        for field in section.get("fields", []):
            override = field_overrides.get(str(field.get("key") or ""))
            if override:
                field.update(override)
        break


_repair_social_auto_upload_section_text()


BUILTIN_TEMPLATES = [
    {
        "key": "单人讲故事",
        "manifest": {
            "name": "单人讲故事",
            "brand_name": "单人讲故事",
            "mode": "video",
            "default_disclaimer": "内容基于公开资料整理，仅作知识科普，不构成医疗、投资或法律建议；本视频由 AI 辅助生成。",
            "release_tags": "#知识科普 #冷知识 #涨知识",
            "cover_footnote_line_1": "内容基于公开资料整理",
            "cover_footnote_line_2": "仅作知识科普",
            "cover_style": "doodle",
            "voice_mode": "single",
            "tts_speaker_1": "zh_female_cancan_uranus_bigtts",
            "tts_action": 3,
            "builtin_locked": True,
            "version": "2026.6.17.117",
        },
        "prompt": """# 单人讲故事

你要把输入的 brief 整理成一个时长随信息量自适应的横屏短视频 `content.md`。

要求：
- 用一个会讲故事的朋友口吻，写成单人独白
- 先交付本期最有用的结果或事实，再用证据、原因和例子把它讲清
- 最后给出普通人能采用的判断或行动；互动问题可有可无
- 产出时同时给出标题、封面副标题、推荐发布标题、场景清单
- 场景图只对应有效信息节点，不按固定数量凑图
""",
    },
    {
        "key": "双人讲故事",
        "manifest": {
            "name": "双人讲故事",
            "brand_name": "双人讲故事",
            "mode": "video",
            "default_disclaimer": "内容基于公开资料整理，仅作知识科普，不构成医疗、投资或法律建议；本视频由 AI 辅助生成。",
            "release_tags": "#知识科普 #双人播客 #故事感",
            "cover_footnote_line_1": "内容基于公开资料整理",
            "cover_footnote_line_2": "仅作知识科普",
            "cover_style": "notebook",
            "voice_mode": "dual",
            "tts_speaker_1": "zh_male_dayixiansheng_v2_saturn_bigtts",
            "tts_speaker_2": "zh_female_mizaitongxue_v2_saturn_bigtts",
            "tts_random_order": False,
            "tts_action": 3,
            "tts_speech_rate": 1.0,
            "builtin_locked": True,
            "version": "2026.6.17.117",
        },
        "prompt": """# 双人讲故事

把 brief 改写成自然的双人对话脚本。两个人都必须提供信息，不能让一人只负责机械追问。

要求：
- 两位角色轮流发言
- 开头尽快交付本期最有用的结果、事实或现实影响
- 每轮围绕同一件事自然承接，并增加事实、原因、例子、后果或判断
- 结尾给出明确判断或现实用途；只有自然产生讨论点时才加一个问题
- 同时给出标题、封面副标题、推荐发布标题、场景清单
""",
    },
    {
        "key": "单人图文",
        "manifest": {
            "name": "单人图文",
            "brand_name": "单人图文",
            "mode": "article",
            "default_disclaimer": "",
            "release_tags": "图文",
            "cover_style": "forbes",
            "cover_footnote_line_1": "",
            "cover_footnote_line_2": "",
            "builtin_locked": True,
            "version": "2026.6.17.117",
        },
        "prompt": """# 单人图文

把 brief 改写成适合图文平台发布的长图文内容。

要求：
- 保留强钩子标题
- 用 6-9 页卡片式结构讲清楚
- 每页都给出一句适合出图的核心文案
- 最终输出 `content.md` 和图文卡片清单
""",
    },
]


def now_ts() -> float:
    return time.time()


def now_ms() -> int:
    return int(time.time() * 1000)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


_PATH_WRITE_LOCKS_GUARD = threading.Lock()
_PATH_WRITE_LOCKS: dict[str, threading.RLock] = {}
_ATOMIC_REPLACE_RETRY_DELAYS = (0.02, 0.04, 0.08, 0.16, 0.32, 0.5, 0.75, 1.0)


def _path_write_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _PATH_WRITE_LOCKS_GUARD:
        lock = _PATH_WRITE_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_WRITE_LOCKS[key] = lock
        return lock


def _replace_with_retry(temp_path: Path, path: Path) -> None:
    for attempt in range(len(_ATOMIC_REPLACE_RETRY_DELAYS) + 1):
        try:
            os.replace(temp_path, path)
            return
        except OSError as exc:
            transient = isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {5, 32, 33}
            if not transient or attempt >= len(_ATOMIC_REPLACE_RETRY_DELAYS):
                raise
            time.sleep(_ATOMIC_REPLACE_RETRY_DELAYS[attempt])


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    raw = ""
    try:
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception:
        try:
            stripped = raw.lstrip("\ufeff\r\n\t ")
            recovered, _end = json.JSONDecoder().raw_decode(stripped)
            return recovered
        except Exception:
            return default


def write_json(path: Path, data: Any) -> None:
    _assert_valid_project_write_target(path)
    ensure_dir(path.parent)
    content = json.dumps(data, ensure_ascii=False, indent=2)
    with _path_write_lock(path):
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            temp_path.write_text(content, encoding="utf-8")
            _replace_with_retry(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return default


def write_text(path: Path, content: str) -> None:
    _assert_valid_project_write_target(path)
    ensure_dir(path.parent)
    with _path_write_lock(path):
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            temp_path.write_text(content, encoding="utf-8")
            _replace_with_retry(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    return cleaned[:80] or "未命名"


def is_builtin_template_key(key: str) -> bool:
    builtins = {safe_name(str(item.get("key", ""))) for item in BUILTIN_TEMPLATES}
    return safe_name(key) in builtins


def current_version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8", errors="ignore").strip() or "0.0.0"
    return "0.0.0"


def project_dir(project_id: int) -> Path:
    return PROJECTS_ROOT / str(project_id)


def project_file(project_id: int, relative: str) -> Path:
    return project_dir(project_id) / relative


def _project_root_from_path(path: Path) -> Path | None:
    try:
        absolute_path = path.resolve()
        projects_root = PROJECTS_ROOT.resolve()
        relative = absolute_path.relative_to(projects_root)
    except Exception:
        return None
    if not relative.parts:
        return None
    project_name = relative.parts[0]
    if not project_name.isdigit():
        return None
    return projects_root / project_name


def _assert_valid_project_write_target(path: Path) -> None:
    project_root = _project_root_from_path(path)
    if project_root is None:
        return
    if path.name == "project.json":
        return
    if (project_root / "project.json").exists():
        return
    raise FileNotFoundError(f"project {project_root.name} not found")


def _extract_topic_from_markdown(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip()
        for marker in ("主题：", "主题:", "标题：", "标题:"):
            if marker in line:
                _, _, tail = line.partition(marker)
                candidate = tail.strip()
                if candidate:
                    return candidate
        return line[:120]
    return ""


def _extract_topic_from_scene_timeline(path: Path) -> str:
    payload = read_json(path / "audio/scene_timeline.json", {})
    scenes = payload.get("scenes") if isinstance(payload, dict) else None
    if not isinstance(scenes, list):
        return ""
    for item in scenes:
        if not isinstance(item, dict):
            continue
        for field in ("prompt", "text"):
            value = str(item.get(field) or "").strip()
            if not value:
                continue
            for pattern in (r"[「“\"]([^」”\"\n]{4,80})[」”\"]", r"[《](.{4,80})[》]"):
                match = re.search(pattern, value)
                if match:
                    candidate = match.group(1).strip("：:,.，。 ")
                    if candidate:
                        return candidate
            return value.splitlines()[0].strip()[:120]
    return ""


def _infer_template_key_from_text(text: str) -> str:
    content = str(text or "")
    if not content:
        return ""
    for template in list_templates():
        for candidate in (template.get("key"), template.get("name"), template.get("brand_name")):
            label = str(candidate or "").strip()
            if label and label in content:
                return str(template.get("key") or label)
    return ""


def _fallback_template_key() -> str:
    configured = str(parse_env().get("DEFAULT_TEMPLATE") or "").strip()
    if configured and (TEMPLATES_ROOT / configured).exists():
        return configured
    for template in list_templates():
        if str(template.get("mode") or "video") == "video":
            return str(template.get("key") or "")
    templates = list_templates()
    return str(templates[0].get("key") or "") if templates else ""


def _project_dir_timestamps(path: Path) -> tuple[float, float]:
    created = path.stat().st_ctime
    updated = path.stat().st_mtime
    for child in path.rglob("*"):
        try:
            stat = child.stat()
        except OSError:
            continue
        created = min(created, stat.st_ctime)
        updated = max(updated, stat.st_mtime)
    return created, updated


def _repair_orphan_project_meta(path: Path) -> dict[str, Any] | None:
    if not path.is_dir():
        return None
    if not path.name.isdigit():
        return None
    meta_path = path / "project.json"
    existing_meta = read_json(meta_path, None) if meta_path.exists() else None
    if isinstance(existing_meta, dict) and existing_meta.get("id"):
        return None

    content_text = read_text(path / "content.md")
    brief_text = read_text(path / "brief.md")
    topic_name = (
        _extract_topic_from_markdown(content_text)
        or _extract_topic_from_markdown(brief_text)
        or _extract_topic_from_scene_timeline(path)
    )
    template_key = _infer_template_key_from_text(content_text) or _infer_template_key_from_text(brief_text)
    if not template_key:
        timeline_text = json.dumps(read_json(path / "audio/scene_timeline.json", {}), ensure_ascii=False)
        template_key = _infer_template_key_from_text(timeline_text) or _fallback_template_key()
    if not topic_name or not template_key:
        return None

    template = get_template(template_key)
    created_at, updated_at = _project_dir_timestamps(path)
    content_state = read_json(path / "content_generate.json", {})
    project_settings = read_json(path / "project_settings.json", {"tavily_topic": "general"})
    meta = {
        "id": int(path.name),
        "topic_name": topic_name,
        "template": template_key,
        "template_mode": template.get("mode", "video"),
        "created_at": created_at,
        "updated_at": updated_at,
        "last_job_status": content_state.get("status") or "idle",
        "content_generating": bool(content_state.get("status") == "running"),
        "tavily_topic": project_settings.get("tavily_topic", "general"),
    }
    if meta_path.exists():
        backup_path = path / f"project.corrupt-{now_ms()}.json"
        with contextlib.suppress(OSError):
            shutil.copy2(meta_path, backup_path)
    write_json(meta_path, meta)
    return meta


def _should_delete_orphan_project_dir(path: Path) -> bool:
    if not path.is_dir() or (path / "project.json").exists():
        return False
    meaningful_names = {
        "brief.md",
        "content.md",
        "summary.json",
        "references.json",
        "project_settings.json",
        "release_links.json",
        "auto_topic.json",
        "auto_video.json",
    }
    for child in path.rglob("*"):
        if child.is_dir():
            continue
        if child.name in meaningful_names and read_text(child).strip():
            return False
        if child.suffix.lower() in {".md", ".json"} and child.name not in {"content_generate.json", "image_prompt_controls.json"}:
            if read_text(child).strip():
                return False
    return True


def _cleanup_orphan_project_dir(path: Path) -> None:
    if _should_delete_orphan_project_dir(path):
        shutil.rmtree(path, ignore_errors=True)


def reconcile_interrupted_project_states() -> None:
    for path in PROJECTS_ROOT.iterdir():
        if not path.is_dir() or not path.name.isdigit():
            continue
        meta = read_json(path / "project.json", {})
        if not isinstance(meta, dict) or not meta.get("id"):
            meta = _repair_orphan_project_meta(path) or {}
        if not meta:
            continue

        interrupted = False
        latest_job_path = path / "jobs" / "latest.json"
        latest_job = read_json(latest_job_path, {})
        if isinstance(latest_job, dict) and latest_job.get("running"):
            auto_resume = bool(
                latest_job.get("auto_recover", False)
                and str(latest_job.get("origin") or "manual").strip() == "manual"
            )
            latest_job.update(
                {
                    "status": "interrupted",
                    "running": False,
                    "finished_at": latest_job.get("finished_at") or now_ts(),
                    "error": latest_job.get("error") or (
                        "服务重启时任务仍在运行，系统正在准备自动续跑。"
                        if auto_resume
                        else "服务重启时任务仍在运行，已有文件已保留。"
                    ),
                    "resume_pending": auto_resume,
                    "interruption_reason": "service_restart",
                }
            )
            log_text = str(latest_job.get("log") or "").rstrip()
            notice = (
                "[recovery] 服务重启时任务中断，已有文件保留；后台启动后将自动续跑。"
                if auto_resume
                else "[job] 服务重启时任务中断，已有文件保留。"
            )
            latest_job["log"] = f"{log_text}\n{notice}".strip() if log_text else notice
            write_json(latest_job_path, latest_job)
            meta["last_job_status"] = "interrupted"
            interrupted = True

        content_state_path = path / "content_generate.json"
        content_state = read_json(content_state_path, {})
        if isinstance(content_state, dict) and content_state.get("status") == "running":
            content_state.update(
                {
                    "status": "interrupted",
                    "finished_at": content_state.get("finished_at") or now_ts(),
                    "error": content_state.get("error") or "服务重启时内容生成中断，请重新生成。",
                }
            )
            write_json(content_state_path, content_state)
            meta["content_generating"] = False
            interrupted = True

        content_sync_path = path / "content_sync.json"
        content_sync = read_json(content_sync_path, {})
        if isinstance(content_sync, dict) and content_sync.get("running"):
            content_sync.update(
                {
                    "status": "interrupted",
                    "running": False,
                    "finished_at": content_sync.get("finished_at") or now_ts(),
                    "message": "服务重启时内容同步中断；再次保存会自动重建。",
                }
            )
            write_json(content_sync_path, content_sync)
            interrupted = True

        if interrupted:
            write_project_meta(int(path.name), meta)


def bootstrap() -> None:
    ensure_dir(DATA_ROOT)
    ensure_dir(TEMPLATES_ROOT)
    ensure_dir(PROJECTS_ROOT)
    ensure_dir(TEMPLATE_PRODUCTS_ROOT)
    ensure_dir(CONFIG_ROOT)

    if not COUNTERS_FILE.exists():
        write_json(COUNTERS_FILE, {"project_id": 0, "release_id": 0})

    if not ENV_FILE.exists():
        lines = [f"{key}={value}" for key, value in DEFAULT_ENV.items()]
        write_text(ENV_FILE, "\n".join(lines) + "\n")

    if not VALIDATION_FILE.exists():
        write_json(VALIDATION_FILE, {"sections": {}})

    if not UPDATE_MANIFEST_FILE.exists():
        write_json(
            UPDATE_MANIFEST_FILE,
            {
                "version": current_version(),
                "title": "当前已是本地最新版本",
                "highlights": [
                    "更新信息现在改为读取本地 update_manifest.json。",
                    "把更高版本号和下载地址写进去后，前端会真实提示更新。",
                ],
                "download_url": "",
                "recommend": "optional",
            },
        )

    for item in BUILTIN_TEMPLATES:
        template_root = TEMPLATES_ROOT / item["key"]
        ensure_dir(template_root)
        manifest_path = template_root / "manifest.json"
        prompt_path = template_root / "prompt.md"
        if not manifest_path.exists():
            write_json(manifest_path, item["manifest"])
        else:
            manifest = read_json(manifest_path, {})
            if not manifest.get("builtin_locked"):
                manifest["builtin_locked"] = True
                write_json(manifest_path, manifest)
        if not prompt_path.exists():
            write_text(prompt_path, item["prompt"].strip() + "\n")

    reconcile_interrupted_project_states()


def next_counter(name: str) -> int:
    payload = read_json(COUNTERS_FILE, {"project_id": 0, "release_id": 0})
    payload[name] = int(payload.get(name, 0)) + 1
    write_json(COUNTERS_FILE, payload)
    return payload[name]


def list_templates() -> list[dict[str, Any]]:
    def sort_key(path: Path) -> tuple[int, float, str]:
        manifest = read_json(path / "manifest.json", {})
        builtin = 1 if manifest.get("builtin_locked") or is_builtin_template_key(path.name) else 0
        try:
            created_at = path.stat().st_ctime
        except OSError:
            created_at = 0.0
        return (builtin, -created_at, path.name)

    templates: list[dict[str, Any]] = []
    for path in sorted(TEMPLATES_ROOT.iterdir(), key=sort_key):
        if not path.is_dir():
            continue
        templates.append(get_template(path.name))
    return templates


def get_template(key: str) -> dict[str, Any]:
    root = TEMPLATES_ROOT / key
    manifest = read_json(root / "manifest.json", {})
    prompt = read_text(root / "prompt.md")
    return {
        "key": key,
        "name": manifest.get("name", key),
        "brand_name": manifest.get("brand_name", key),
        "mode": manifest.get("mode", "video"),
        "target_audience": manifest.get("target_audience", ""),
        "channel_voice": manifest.get("channel_voice", ""),
        "visual_strategy": manifest.get("visual_strategy", ""),
        "forbidden_rules": manifest.get("forbidden_rules", ""),
        "image_style_prompt": manifest.get("image_style_prompt", ""),
        "image_negative_prompt": manifest.get("image_negative_prompt", ""),
        "visual_palette": manifest.get("visual_palette", {}),
        "interaction_goal": manifest.get("interaction_goal", ""),
        "topic_mining_hint": manifest.get("topic_mining_hint", ""),
        "default_disclaimer": manifest.get("default_disclaimer", ""),
        "release_tags": manifest.get("release_tags", ""),
        "cover_footnote_line_1": manifest.get("cover_footnote_line_1", ""),
        "cover_footnote_line_2": manifest.get("cover_footnote_line_2", ""),
        "cover_style": manifest.get("cover_style", "default"),
        "voice_mode": manifest.get("voice_mode", ""),
        "tts_speaker_1": manifest.get("tts_speaker_1", ""),
        "tts_speaker_2": manifest.get("tts_speaker_2", ""),
        "tts_random_order": manifest.get("tts_random_order", ""),
        "tts_action": manifest.get("tts_action", ""),
        "tts_speech_rate": manifest.get("tts_speech_rate", 1.0),
        "builtin_locked": bool(manifest.get("builtin_locked", False) or is_builtin_template_key(key)),
        "generate_cover_landscape": manifest.get("generate_cover_landscape", True),
        "generate_cover_portrait": manifest.get("generate_cover_portrait", True),
        "version": manifest.get("version", ""),
        "prompt": prompt,
    }


def validate_template_prompt(prompt: str) -> str:
    cleaned = str(prompt or "").strip()
    compact = re.sub(r"\s+", "", cleaned)
    if len(compact) < 120:
        raise ValueError("频道 prompt.md 太短。请至少写清楚频道人设、内容结构、画面风格和禁忌，避免生成退回通用模板。")
    required_hints = ("人设", "口吻", "结构", "封面", "场景", "图片", "禁忌", "互动")
    if sum(1 for hint in required_hints if hint in cleaned) < 2:
        raise ValueError("频道 prompt.md 缺少频道规则。建议写明人设/口吻、脚本结构、封面与场景图风格、禁忌和互动方式。")
    return cleaned


def save_template(key: str, payload: dict[str, Any]) -> dict[str, Any]:
    safe_key = safe_name(key)
    existing_manifest = read_json(TEMPLATES_ROOT / safe_key / "manifest.json", {})
    if existing_manifest.get("builtin_locked") or is_builtin_template_key(safe_key):
        raise PermissionError("内置频道模板不能通过工作台编辑。")

    prompt = validate_template_prompt(str(payload.get("prompt", "")))
    root = ensure_dir(TEMPLATES_ROOT / safe_key)
    manifest = {
        "name": payload.get("name", safe_key),
        "brand_name": payload.get("brand_name", safe_key),
        "mode": payload.get("mode", "video"),
        "target_audience": payload.get("target_audience", ""),
        "channel_voice": payload.get("channel_voice", ""),
        "visual_strategy": payload.get("visual_strategy", ""),
        "forbidden_rules": payload.get("forbidden_rules", ""),
        "image_style_prompt": payload.get("image_style_prompt", ""),
        "image_negative_prompt": payload.get("image_negative_prompt", ""),
        "visual_palette": payload.get("visual_palette", existing_manifest.get("visual_palette", {})),
        "interaction_goal": payload.get("interaction_goal", ""),
        "topic_mining_hint": payload.get("topic_mining_hint", ""),
        "default_disclaimer": payload.get("default_disclaimer", ""),
        "release_tags": payload.get("release_tags", ""),
        "cover_footnote_line_1": payload.get("cover_footnote_line_1", ""),
        "cover_footnote_line_2": payload.get("cover_footnote_line_2", ""),
        "cover_style": payload.get("cover_style", "default"),
        "voice_mode": payload.get("voice_mode", ""),
        "tts_speaker_1": payload.get("tts_speaker_1", ""),
        "tts_speaker_2": payload.get("tts_speaker_2", ""),
        "tts_random_order": payload.get("tts_random_order", ""),
        "tts_action": payload.get("tts_action", ""),
        "tts_speech_rate": payload.get("tts_speech_rate", 1.0),
        "generate_cover_landscape": payload.get("generate_cover_landscape", True),
        "generate_cover_portrait": payload.get("generate_cover_portrait", True),
        "builtin_locked": False,
        "version": payload.get("version", ""),
    }
    write_json(root / "manifest.json", manifest)
    write_text(root / "prompt.md", prompt + "\n")
    return get_template(safe_key)


def save_template_voice_settings(key: str, payload: dict[str, Any]) -> dict[str, Any]:
    safe_key = safe_name(key)
    root = TEMPLATES_ROOT / safe_key
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"频道模板「{safe_key}」不存在。")

    manifest = read_json(manifest_path, {})
    voice_mode = str(payload.get("voice_mode") or "").strip().lower()
    if voice_mode not in {"", "auto", "single", "dual"}:
        raise ValueError("配音模式只能是自动、单人或双人。")
    if voice_mode == "auto":
        voice_mode = ""

    speaker_1 = str(payload.get("tts_speaker_1") or "").strip()
    speaker_2 = str(payload.get("tts_speaker_2") or "").strip()
    if not speaker_1:
        raise ValueError("请至少选择一个豆包音色。")
    if voice_mode == "dual" and not speaker_2:
        raise ValueError("双人讲述需要选择两个豆包音色。")
    if voice_mode == "dual" and speaker_1 == speaker_2:
        raise ValueError("双人讲述的两个角色不能使用同一个音色。")

    try:
        speech_rate = float(payload.get("tts_speech_rate", 1.0) or 1.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("语速必须是数字。") from exc
    speech_rate = max(0.8, min(speech_rate, 1.2))

    manifest.update(
        {
            "voice_mode": voice_mode,
            "tts_speaker_1": speaker_1,
            "tts_speaker_2": speaker_2 if voice_mode in {"", "dual"} else "",
            "tts_random_order": bool(payload.get("tts_random_order", False)) if voice_mode in {"", "dual"} else False,
            # The studio supplies the final dialogue verbatim; action 3 prevents
            # the podcast service from adding an unexpected host or outro.
            "tts_action": 3,
            "tts_speech_rate": speech_rate,
        }
    )
    write_json(manifest_path, manifest)
    return get_template(safe_key)


def delete_template(template_key: str, delete_projects: bool = False) -> dict[str, Any]:
    safe_key = safe_name(template_key)
    template_root = TEMPLATES_ROOT / safe_key
    if not template_root.exists():
        raise FileNotFoundError(f"频道模板「{template_key}」不存在。")

    manifest = read_json(template_root / "manifest.json", {})
    if manifest.get("builtin_locked") or is_builtin_template_key(safe_key):
        raise PermissionError("内置频道模板不能通过工作台删除。")

    linked_projects = projects_for_template(safe_key)
    if linked_projects and not delete_projects:
        raise ValueError(f"频道模板「{safe_key}」还有 {len(linked_projects)} 个主题项目。")

    deleted_ids: list[int] = []
    if delete_projects:
        for meta in linked_projects:
            project_id = int(meta["id"])
            delete_project(project_id)
            deleted_ids.append(project_id)

    shutil.rmtree(template_root, ignore_errors=True)
    shutil.rmtree(template_products_dir(safe_key), ignore_errors=True)
    return {
        "ok": True,
        "template": safe_key,
        "deleted_projects": len(deleted_ids),
        "project_ids": deleted_ids,
    }


def list_projects() -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    for path in PROJECTS_ROOT.iterdir():
        if not path.is_dir():
            continue
        meta_path = path / "project.json"
        if not meta_path.exists():
            repaired = _repair_orphan_project_meta(path)
            if repaired:
                projects.append(repaired)
            else:
                _cleanup_orphan_project_dir(path)
            continue
        meta = read_json(meta_path, {})
        if isinstance(meta, dict) and meta.get("id"):
            projects.append(meta)
            continue
        repaired = _repair_orphan_project_meta(path)
        if repaired:
            projects.append(repaired)
    projects.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
    return projects


def get_project(project_id: int) -> dict[str, Any]:
    meta = read_json(project_file(project_id, "project.json"), {})
    if not meta:
        repaired = _repair_orphan_project_meta(project_dir(project_id))
        if repaired:
            return repaired
    if not meta:
        raise FileNotFoundError(f"project {project_id} not found")
    return meta


def write_project_meta(project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    payload["updated_at"] = now_ts()
    write_json(project_file(project_id, "project.json"), payload)
    return payload


def create_project(
    topic_name: str,
    template_key: str,
    content_type: str = "editorial",
    output_language: str = "zh-CN",
) -> dict[str, Any]:
    project_id = next_counter("project_id")
    template = get_template(template_key)
    normalized_content_type = "product" if str(content_type or "").strip().lower() == "product" else "editorial"
    normalized_output_language = "en-US" if str(output_language or "").strip().lower().startswith("en") else "zh-CN"
    meta = {
        "id": project_id,
        "topic_name": topic_name.strip(),
        "template": template_key,
        "template_mode": template.get("mode", "video"),
        "content_type": normalized_content_type,
        "output_language": normalized_output_language,
        "created_at": now_ts(),
        "updated_at": now_ts(),
        "last_job_status": "idle",
        "content_generating": False,
        "tavily_topic": "general",
    }
    root = ensure_dir(project_dir(project_id))
    ensure_dir(root / "reports")
    ensure_dir(root / "jobs")
    ensure_dir(root / "audio")
    ensure_dir(root / "scenes")
    ensure_dir(root / "covers")
    ensure_dir(root / "article")
    ensure_dir(root / "releases")
    ensure_dir(root / "uploads")
    write_project_meta(project_id, meta)
    write_text(root / "brief.md", "")
    write_text(root / "content.md", "")
    write_json(root / "references.json", [])
    write_json(root / "summary.json", {})
    project_settings = dict(DEFAULT_PROJECT_SETTINGS)
    project_settings["content_type"] = normalized_content_type
    project_settings["output_language"] = normalized_output_language
    write_json(root / "project_settings.json", project_settings)
    write_json(
        root / "motion_profile.json",
        {
            "version": "motion-samples-v3-balanced-information",
            "selected": "stable",
            "updated_at": now_ts(),
        },
    )
    write_json(root / "release_links.json", [])
    return meta


def delete_project(project_id: int) -> None:
    shutil.rmtree(project_dir(project_id), ignore_errors=True)


def projects_for_template(template_key: str) -> list[dict[str, Any]]:
    return [meta for meta in list_projects() if meta.get("template") == template_key]


def template_products_dir(template_key: str) -> Path:
    return TEMPLATE_PRODUCTS_ROOT / safe_name(template_key)


def build_template_products_dir(template_key: str) -> Path:
    root = ensure_dir(template_products_dir(template_key))
    for path in root.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)

    projects = projects_for_template(template_key)
    lines = [f"模板：{template_key}", f"项目数量：{len(projects)}", ""]
    for meta in projects:
        project_root = project_dir(meta["id"])
        releases_root = project_root / "releases"
        target = releases_root if releases_root.exists() else project_root
        base_name = f"{meta['id']:04d}-{safe_name(meta['topic_name'])}"
        launcher = root / f"{base_name}.cmd"
        write_text(
            launcher,
            "@echo off\n"
            f'start "" "{target}"\n',
        )
        lines.extend(
            [
                f"[{meta['id']}] {meta['topic_name']}",
                f"项目目录: {project_root}",
                f"成片目录: {releases_root}",
                f"快捷打开: {launcher.name}",
                "",
            ]
        )

    write_text(root / "README.txt", "\n".join(lines).rstrip() + "\n")
    return root


def delete_orphan_template(template_key: str) -> dict[str, Any]:
    template_root = TEMPLATES_ROOT / template_key
    if template_root.exists():
        raise ValueError(f"模板「{template_key}」仍然存在，不能按 orphan 清理。")

    deleted_ids: list[int] = []
    for meta in projects_for_template(template_key):
        delete_project(meta["id"])
        deleted_ids.append(meta["id"])

    shutil.rmtree(template_products_dir(template_key), ignore_errors=True)
    return {"ok": True, "deleted": len(deleted_ids), "project_ids": deleted_ids}


def get_brief(project_id: int) -> str:
    return read_text(project_file(project_id, "brief.md"))


def save_brief(project_id: int, brief: str) -> None:
    path = project_file(project_id, "brief.md")
    previous = read_text(path)
    if previous and previous != brief:
        history_name = f"brief-{int(now_ts() * 1000)}.md"
        write_text(project_file(project_id, f"history/{history_name}"), previous)
    write_text(path, brief)
    meta = get_project(project_id)
    meta["updated_at"] = now_ts()
    write_project_meta(project_id, meta)


def latest_complete_brief(project_id: int) -> str:
    candidates = [project_file(project_id, "brief.md")]
    history_root = project_file(project_id, "history")
    if history_root.exists():
        candidates.extend(sorted(history_root.glob("brief-*.md"), key=lambda item: item.stat().st_mtime, reverse=True))
    structured_markers = (
        "口播逐字稿",
        "核心材料",
        "核心检索对象",
        "必须保留",
        "成稿要求",
        "原始材料简述",
    )
    complete = []
    for path in candidates:
        value = read_text(path)
        if len(value) >= 800 and any(marker in value for marker in structured_markers):
            complete.append((len(value), path.stat().st_mtime, value))
    if not complete:
        return ""
    # Prefer the richest structured source, then the newest one. A short
    # stale textarea submission must never replace the source material.
    return max(complete, key=lambda item: (item[0], item[1]))[2]


def get_content(project_id: int) -> str:
    return read_text(project_file(project_id, "content.md"))


def save_content(project_id: int, content: str) -> None:
    write_text(project_file(project_id, "content.md"), content)
    meta = get_project(project_id)
    meta["updated_at"] = now_ts()
    write_project_meta(project_id, meta)


def get_summary(project_id: int) -> dict[str, Any]:
    summary = read_json(project_file(project_id, "summary.json"), {})
    if not isinstance(summary, dict):
        summary = {}
    settings = get_project_settings(project_id)
    if settings.get("scene_count_mode") == "fixed":
        fixed_count = int(settings.get("scene_count_fixed", 6) or 6)
        summary["scene_count"] = fixed_count
        summary["scene_count_aligned"] = fixed_count
        return summary
    timeline_path = project_file(project_id, "audio/scene_timeline.json")
    content_path = project_file(project_id, "content.md")
    timeline_fresh = timeline_path.exists() and (
        not content_path.exists() or timeline_path.stat().st_mtime >= content_path.stat().st_mtime
    )
    if timeline_fresh:
        timeline = read_json(timeline_path, {})
        scenes = timeline.get("scenes") if isinstance(timeline, dict) else None
        if isinstance(scenes, list) and scenes:
            summary["scene_count"] = len(scenes)
            summary["scene_count_aligned"] = len(scenes)
    return summary


def save_summary(project_id: int, summary: dict[str, Any]) -> None:
    write_json(project_file(project_id, "summary.json"), summary)


def get_references(project_id: int) -> list[dict[str, Any]]:
    return read_json(project_file(project_id, "references.json"), [])


def save_references(project_id: int, references: list[dict[str, Any]]) -> None:
    write_json(project_file(project_id, "references.json"), references)


DEFAULT_PROJECT_SETTINGS = {
    "tavily_topic": "general",
    "output_language": "zh-CN",
    "scene_count_mode": "auto",
    "scene_count_fixed": 6,
    "cover_enabled": True,
    "content_type": "editorial",
    "product_name": "",
    "product_category": "",
    "product_target_customer": "",
    "product_usage_scenarios": "",
    "product_selling_points": "",
    "product_evidence": "",
    "product_offer": "",
    "product_compliance_notes": "",
    "product_asset_files": [],
}


def normalize_project_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(DEFAULT_PROJECT_SETTINGS)
    if isinstance(settings, dict):
        normalized.update(settings)
    mode = str(normalized.get("scene_count_mode") or "auto").strip().lower()
    if mode not in {"auto", "fixed"}:
        mode = "auto"
    normalized["scene_count_mode"] = mode
    try:
        fixed = int(normalized.get("scene_count_fixed", 6) or 6)
    except Exception:
        fixed = 6
    normalized["scene_count_fixed"] = max(1, min(fixed, 24))
    cover_enabled = normalized.get("cover_enabled", True)
    if isinstance(cover_enabled, str):
        cover_enabled = cover_enabled.strip().lower() not in {"0", "false", "off", "no"}
    normalized["cover_enabled"] = bool(cover_enabled)
    normalized["tavily_topic"] = str(normalized.get("tavily_topic") or "general").strip() or "general"
    output_language = str(normalized.get("output_language") or "zh-CN").strip().lower()
    normalized["output_language"] = "en-US" if output_language.startswith("en") else "zh-CN"
    normalized["content_type"] = (
        "product" if str(normalized.get("content_type") or "").strip().lower() == "product" else "editorial"
    )
    for key in (
        "product_name",
        "product_category",
        "product_target_customer",
        "product_usage_scenarios",
        "product_selling_points",
        "product_evidence",
        "product_offer",
        "product_compliance_notes",
    ):
        normalized[key] = str(normalized.get(key) or "").strip()[:4000]
    asset_files = normalized.get("product_asset_files")
    if not isinstance(asset_files, list):
        asset_files = []
    normalized["product_asset_files"] = list(
        dict.fromkeys(
            safe_name(str(item))
            for item in asset_files
            if str(item or "").strip()
        )
    )[:10]
    return normalized


def get_project_settings(project_id: int) -> dict[str, Any]:
    return normalize_project_settings(read_json(project_file(project_id, "project_settings.json"), DEFAULT_PROJECT_SETTINGS))


def save_project_settings(project_id: int, settings: dict[str, Any]) -> None:
    current = get_project_settings(project_id)
    current.update(settings)
    current = normalize_project_settings(current)
    write_json(project_file(project_id, "project_settings.json"), current)
    meta = get_project(project_id)
    meta["tavily_topic"] = current.get("tavily_topic", "general")
    meta["content_type"] = current.get("content_type", "editorial")
    meta["output_language"] = current.get("output_language", "zh-CN")
    write_project_meta(project_id, meta)


def report_path(project_id: int, name: str) -> Path:
    return project_file(project_id, f"reports/{name}.json")


def get_report(project_id: int, name: str) -> dict[str, Any] | None:
    path = report_path(project_id, name)
    if not path.exists():
        return None
    return read_json(path, None)


def save_report(project_id: int, name: str, data: dict[str, Any]) -> Path:
    path = report_path(project_id, name)
    write_json(path, data)
    return path


def get_release_links(project_id: int) -> list[dict[str, Any]]:
    return read_json(project_file(project_id, "release_links.json"), [])


def save_release_links(project_id: int, links: list[dict[str, Any]]) -> None:
    write_json(project_file(project_id, "release_links.json"), links)


def next_release_id() -> int:
    return next_counter("release_id")


def parse_env() -> dict[str, str]:
    values = dict(DEFAULT_ENV)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "已配置，留空则不变"
    return f"已配置 ...{value[-4:]}，留空则不变"


def write_env(values: dict[str, str]) -> None:
    merged = dict(DEFAULT_ENV)
    merged.update(values)
    lines = [f"{key}={merged.get(key, '')}" for key in DEFAULT_ENV]
    write_text(ENV_FILE, "\n".join(lines) + "\n")


def save_env_patch(values: dict[str, str]) -> dict[str, str]:
    current = parse_env()
    merged = dict(current)
    for key in DEFAULT_ENV:
        if key not in values:
            continue
        incoming = values.get(key, "")
        if key in SECRET_KEYS and not incoming:
            continue
        merged[key] = incoming
    # The production pipeline uses the podcast model for both one-person and
    # two-person narration. Keep the extracted legacy runtime variables in
    # sync so there is only one credential source in the UI.
    podcast_app_id = str(merged.get("VOLC_PODCAST_APP_ID") or "").strip()
    podcast_token = str(merged.get("VOLC_PODCAST_ACCESS_TOKEN") or "").strip()
    podcast_resource = str(merged.get("VOLC_PODCAST_RESOURCE_ID") or "").strip()
    if podcast_app_id:
        merged["VOLC_TTS_APP_KEY"] = podcast_app_id
    if podcast_token:
        merged["VOLC_TTS_ACCESS_KEY"] = podcast_token
    if podcast_resource:
        merged["VOLC_TTS_RESOURCE_ID"] = podcast_resource
    write_env(merged)
    return merged


def load_validation_cache() -> dict[str, Any]:
    return read_json(VALIDATION_FILE, {"sections": {}})


def save_validation_cache(cache: dict[str, Any]) -> None:
    write_json(VALIDATION_FILE, cache)


def secrets_payload() -> dict[str, Any]:
    values = parse_env()
    public_values = {key: ("" if key in SECRET_KEYS else values.get(key, "")) for key in DEFAULT_ENV}
    validation = load_validation_cache().get("sections", {})
    metadata = []
    status = {}
    sections = []

    for section in CONFIG_SECTIONS:
        fields = []
        for field in section["fields"]:
            key = field["key"]
            value = values.get(key, DEFAULT_ENV.get(key, ""))
            configured = bool(value)
            options = field.get("options", [])
            if key in {"VOLC_TTS_SPEAKER_1", "VOLC_TTS_SPEAKER_2"}:
                options = doubao_tts_voice_options(value)
            payload = {
                "key": key,
                "label": field["label"],
                "required": field["required"],
                "secret": field["secret"],
                "kind": field["kind"],
                "help": field["help"],
                "configured": configured,
                "value": "" if field["secret"] else value,
                "placeholder": mask_secret(value) if field["secret"] and configured else "",
                "options": options,
            }
            fields.append(payload)
            metadata.append({"key": key, "default": DEFAULT_ENV.get(key, ""), "label": field["label"]})
            status[key] = {
                "configured": configured,
                "value": "" if field["secret"] else value,
                "masked": mask_secret(value) if field["secret"] else value,
            }
        sections.append(
            {
                "key": section["key"],
                "title": section["title"],
                "description": section["description"],
                "validator": section["validator"],
                "fields": fields,
                "validation": validation.get(section["key"], {"status": "idle", "message": "尚未校验"}),
            }
        )

    return {
        "values": public_values,
        "keys": list(DEFAULT_ENV.keys()),
        "metadata": metadata,
        "status": status,
        "groups": [{"key": section["key"], "label": section["title"]} for section in CONFIG_SECTIONS],
        "sections": sections,
    }


def doubao_tts_voice_options(current_value: str = "") -> list[dict[str, str]]:
    preview_roots = (
        APP_ROOT.parent / "_analysis" / "awesome_app_install" / "_internal" / "web" / "static" / "tts-previews",
        DATA_ROOT / "tts-previews",
    )
    voices: list[dict[str, str]] = []
    for root in preview_roots:
        manifest = read_json(root / "manifest.json", {})
        items = manifest.get("voices") if isinstance(manifest, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or item.get("supported") is False:
                continue
            value = str(item.get("voice_type") or "").strip()
            if not value:
                continue
            label = str(item.get("label") or value).strip()
            scene = str(item.get("scene") or "其他音色").strip()
            language = str(item.get("language") or "").strip()
            detail = " · ".join(part for part in (scene, language) if part)
            voices.append({"value": value, "label": f"{label}（{detail}）" if detail else label})
        if voices:
            break

    if not voices:
        voices = [
            {"value": "zh_male_dayixiansheng_v2_saturn_bigtts", "label": "黑猫侦探社大壹先生"},
            {"value": "zh_female_mizaitongxue_v2_saturn_bigtts", "label": "黑猫侦探社咪仔同学"},
            {"value": "zh_female_cancan_uranus_bigtts", "label": "知性灿灿 2.0"},
        ]
    known = {item["value"] for item in voices}
    current = str(current_value or "").strip()
    if current and current not in known:
        voices.insert(0, {"value": current, "label": f"当前自定义音色（{current}）"})
    return voices


def content_bundle(project_id: int) -> dict[str, Any]:
    meta = get_project(project_id)
    project_settings = get_project_settings(project_id)
    return {
        "content": get_content(project_id),
        "brief": get_brief(project_id),
        "summary": get_summary(project_id),
        "references": get_references(project_id),
        "fact_registry": read_json(project_file(project_id, "fact_registry.json"), {}),
        "content_strategy": read_json(project_file(project_id, "content_strategy.json"), {}),
        "content_audit": read_json(project_file(project_id, "content_audit.json"), {}),
        "video_spec": read_json(project_file(project_id, "video_spec.json"), {}),
        "scene_plan": read_json(project_file(project_id, "audio/scene_plan.json"), {}),
        "tavily_topic": project_settings.get("tavily_topic", "general"),
        "project_settings": project_settings,
        "project": meta,
    }


def list_project_files(project_id: int) -> list[dict[str, Any]]:
    root = project_dir(project_id)
    files: list[dict[str, Any]] = []
    try:
        paths = sorted(root.rglob("*"))
    except FileNotFoundError:
        return files
    for path in paths:
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except FileNotFoundError:
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith("cache/"):
            continue
        files.append(
            {
                "relative_path": rel,
                "name": path.name,
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
                "url": f"/data/projects/{project_id}/{rel}",
                "absolute_path": str(path.resolve()),
            }
        )
    return files


def prompt_preview_text(prompt: str, limit: int = 360) -> str:
    compact = re.sub(r"\s+", " ", str(prompt or "")).strip()
    if len(compact) <= limit:
        return compact
    prefix = compact[:limit]
    cut = max(prefix.rfind(mark) for mark in ("。", "！", "？", "；", ".", "!", "?", ";"))
    if cut >= max(24, int(limit * 0.55)):
        prefix = prefix[: cut + 1]
    return prefix.rstrip("，,、：: ") + "…"


def _scene_candidate_groups(project_id: int) -> dict[str, Any]:
    candidate_dir = project_file(project_id, "scenes/candidates")
    raw_review = read_json(project_file(project_id, "image_review.json"), {})
    review_required = bool(raw_review.get("required", True)) if isinstance(raw_review, dict) else True
    candidate_report = read_json(project_file(project_id, "reports/key_image_candidates.json"), {})
    competitions = candidate_report.get("competitions") if isinstance(candidate_report, dict) else []
    competition_by_index: dict[int, dict[str, Any]] = {}
    if isinstance(competitions, list):
        for item in competitions:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("scene_index", 0) or 0)
            except (TypeError, ValueError):
                continue
            if index > 0:
                competition_by_index[index] = item

    suffix_priority = {".png": 0, ".jpg": 1, ".jpeg": 2, ".webp": 3}
    candidate_paths: dict[tuple[int, str], Path] = {}
    if candidate_dir.exists():
        for path in sorted(candidate_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in suffix_priority:
                continue
            match = re.fullmatch(r"s_(\d+)_([a-z])", path.stem, flags=re.IGNORECASE)
            if not match:
                continue
            key = (int(match.group(1)), match.group(2).upper())
            current = candidate_paths.get(key)
            if current is None or suffix_priority[path.suffix.lower()] < suffix_priority[current.suffix.lower()]:
                candidate_paths[key] = path

    grouped_paths: dict[int, list[tuple[str, Path]]] = {}
    for (index, variant), path in candidate_paths.items():
        grouped_paths.setdefault(index, []).append((variant, path))

    groups: list[dict[str, Any]] = []
    total_candidates = 0
    for index in sorted(grouped_paths):
        competition = competition_by_index.get(index, {})
        report_candidates = competition.get("candidates") if isinstance(competition.get("candidates"), list) else []
        report_by_variant = {
            str(item.get("variant") or "").strip().upper(): item
            for item in report_candidates
            if isinstance(item, dict) and str(item.get("variant") or "").strip()
        }
        selected_variant = str(competition.get("selected_variant") or "").strip().upper()
        ai_recommended_variant = str(
            competition.get("ai_recommended_variant") or competition.get("selected_variant") or ""
        ).strip().upper()
        raw_selection_mode = str(competition.get("selection_mode") or "").strip()
        if review_required and raw_selection_mode == "ai_auto":
            selection_mode = "ai_recommended_pending_human"
        elif not review_required and raw_selection_mode == "ai_recommended_pending_human":
            selection_mode = "ai_auto"
        elif raw_selection_mode:
            selection_mode = raw_selection_mode
        elif review_required:
            selection_mode = "ai_recommended_pending_human" if selected_variant else "pending"
        else:
            selection_mode = "ai_auto" if selected_variant else "pending"

        candidates: list[dict[str, Any]] = []
        for variant, path in sorted(grouped_paths[index], key=lambda item: item[0]):
            stat = path.stat()
            prompt_path = path.with_suffix(".md")
            audit_path = path.with_suffix(".audit.json")
            prompt_text = read_text(prompt_path).strip() if prompt_path.exists() else ""
            audit = read_json(audit_path, {}) if audit_path.exists() else {}
            report_item = report_by_variant.get(variant, {})
            compact_prompt = re.sub(r"\s+", " ", prompt_text).strip()
            candidates.append(
                {
                    "filename": path.name,
                    "scene_index": index,
                    "variant": variant,
                    "url": f"/data/projects/{project_id}/scenes/candidates/{path.name}",
                    "relative_path": f"scenes/candidates/{path.name}",
                    "absolute_path": str(path.resolve()),
                    "size": stat.st_size,
                    "modified_at": stat.st_mtime,
                    "prompt": prompt_text,
                    "prompt_preview": prompt_preview_text(compact_prompt),
                    "prompt_url": (
                        f"/data/projects/{project_id}/scenes/candidates/{prompt_path.name}"
                        if prompt_path.exists()
                        else ""
                    ),
                    "audit": audit if isinstance(audit, dict) else {},
                    "audit_status": "ready" if audit_path.exists() else "pending",
                    "score": int(report_item.get("score", 0) or 0),
                    "local_score": int(report_item.get("local_score", report_item.get("score", 0)) or 0),
                    "judge_mode": str(report_item.get("judge_mode") or ""),
                    "vision_judge": report_item.get("vision_judge") if isinstance(report_item.get("vision_judge"), dict) else {},
                    "concept": report_item.get("concept") if isinstance(report_item.get("concept"), dict) else {},
                    "is_selected": bool(selected_variant and variant == selected_variant),
                    "is_ai_recommended": bool(ai_recommended_variant and variant == ai_recommended_variant),
                }
            )
        total_candidates += len(candidates)
        pending_modes = {"pending", "generating", "ai_recommended_pending_human", "recovered_pending_human"}
        selection_pending = bool(
            candidates
            and (
                selection_mode in pending_modes
                or not selected_variant
                or (review_required and selection_mode != "manual")
            )
        )
        groups.append(
            {
                "scene_index": index,
                "target": str(competition.get("target") or f"s_{index:02d}.png"),
                "role": str(competition.get("role") or "key_scene"),
                "review_required": bool(review_required or selection_pending),
                "selection_mode": selection_mode,
                "selected_variant": selected_variant,
                "ai_recommended_variant": ai_recommended_variant,
                "current_score": int(
                    (competition.get("current") or {}).get("score", 0)
                    if isinstance(competition.get("current"), dict)
                    else 0
                ),
                "current": competition.get("current") if isinstance(competition.get("current"), dict) else {},
                "concept_count": int(competition.get("concept_count", 0) or 0),
                "generated_count": int(competition.get("generated_count", 0) or 0),
                "concept_provider": str(competition.get("concept_provider") or ""),
                "concept_pool": competition.get("concept_pool") if isinstance(competition.get("concept_pool"), list) else [],
                "selected_concepts": competition.get("selected_concepts") if isinstance(competition.get("selected_concepts"), list) else [],
                "opening_contract": (
                    competition.get("opening_contract")
                    if isinstance(competition.get("opening_contract"), dict)
                    else {}
                ),
                "selection_pending": selection_pending,
                "complete": bool(candidates) and selection_mode != "generating",
                "candidates": candidates,
            }
        )

    return {
        "mode": "manual" if review_required else "auto",
        "candidate_count": total_candidates,
        "candidate_group_count": len(groups),
        "groups": groups,
    }


def scene_status(project_id: int) -> dict[str, Any]:
    raw_summary = read_json(project_file(project_id, "summary.json"), {})
    if not isinstance(raw_summary, dict):
        raw_summary = {}
    summary = get_summary(project_id)
    settings = get_project_settings(project_id)
    expected = int(summary.get("scene_count", 0) or 0)
    expected_source = "summary" if expected > 0 else "unknown"
    raw_summary_count = int(raw_summary.get("scene_count", 0) or 0)
    content_path = project_file(project_id, "content.md")
    timeline_path = project_file(project_id, "audio/scene_timeline.json")
    timeline_count = 0
    timeline_audio_ms = 0
    timeline_fresh = timeline_path.exists() and (not content_path.exists() or timeline_path.stat().st_mtime >= content_path.stat().st_mtime)
    if timeline_fresh:
        timeline_payload = read_json(timeline_path, {})
        timeline_scenes = timeline_payload.get("scenes") if isinstance(timeline_payload, dict) else None
        if isinstance(timeline_scenes, list) and timeline_scenes:
            timeline_count = len(timeline_scenes)
            timeline_audio_ms = int(timeline_payload.get("audio_duration_ms", 0) or 0) if isinstance(timeline_payload, dict) else 0
            if settings.get("scene_count_mode") == "fixed":
                expected = int(settings.get("scene_count_fixed", expected or 6) or 6)
                expected_source = "fixed_setting"
            else:
                expected = timeline_count
                expected_source = "audio_timeline"
    elif settings.get("scene_count_mode") == "fixed":
        expected = int(settings.get("scene_count_fixed", expected or 6) or 6)
        expected_source = "fixed_setting"
    scene_dir = project_file(project_id, "scenes")
    prompt_records = read_json(project_file(project_id, "scenes/scene_prompts.json"), [])
    records_by_filename: dict[str, dict[str, Any]] = {}
    if isinstance(prompt_records, list):
        for record in prompt_records:
            if not isinstance(record, dict):
                continue
            filename = str(record.get("filename") or "").strip()
            if filename:
                records_by_filename[filename] = record
    existing_by_index: dict[int, dict[str, Any]] = {}
    variant_count_by_index: dict[int, int] = {}
    suffix_priority = {".png": 0, ".jpg": 1, ".jpeg": 2, ".webp": 3, ".svg": 4}
    allowed_suffixes = set(suffix_priority)
    if scene_dir.exists():
        for path in sorted(scene_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in allowed_suffixes:
                continue
            if not re.fullmatch(r"s_\d+", path.stem):
                continue
            index = int(re.findall(r"(\d+)", path.stem)[0])
            variant_count_by_index[index] = variant_count_by_index.get(index, 0) + 1
            stat = path.stat()
            rel = f"scenes/{path.name}"
            prompt_path = path.with_suffix(".md")
            audit_path = path.with_suffix(".audit.json")
            record = records_by_filename.get(path.name, {})
            prompt_text = str(record.get("prompt") or "").strip()
            if not prompt_text and prompt_path.exists():
                prompt_text = read_text(prompt_path).strip()
            source_prompt = str(record.get("source_prompt") or "").strip()
            audit = read_json(audit_path, {}) if audit_path.exists() else {}
            if not audit:
                audit = record.get("audit") if isinstance(record.get("audit"), dict) else {}
            compact_prompt = re.sub(r"\s+", " ", prompt_text).strip()
            actual_prompt = str(audit.get("prompt") or "").strip() if isinstance(audit, dict) else ""
            compact_actual_prompt = re.sub(r"\s+", " ", actual_prompt).strip()
            prompt_policy_version = str(record.get("prompt_policy_version") or "").strip()
            actual_prompt_policy_version = str(audit.get("prompt_policy_version") or "").strip() if isinstance(audit, dict) else ""
            prompt_integrity = audit.get("prompt_integrity") if isinstance(audit, dict) and isinstance(audit.get("prompt_integrity"), dict) else {}
            prompt_integrity_failed = bool(prompt_integrity.get("required") and not prompt_integrity.get("ok"))
            manual_image_accepted = bool(record.get("manual_image_accepted"))
            prompt_pending_redraw = bool(
                not manual_image_accepted
                and prompt_policy_version
                and (
                    not actual_prompt_policy_version
                    or actual_prompt_policy_version != prompt_policy_version
                    or prompt_integrity_failed
                )
            )
            candidate = {
                "filename": path.name,
                "index": index,
                "url": f"/data/projects/{project_id}/scenes/{path.name}",
                "relative_path": rel,
                "absolute_path": str(path.resolve()),
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
                "prompt": prompt_text,
                "source_prompt": source_prompt,
                "prompt_preview": prompt_preview_text(compact_prompt),
                "actual_prompt_preview": prompt_preview_text(compact_actual_prompt),
                "prompt_policy_version": prompt_policy_version,
                "actual_prompt_policy_version": actual_prompt_policy_version,
                "prompt_pending_redraw": prompt_pending_redraw,
                "manual_image_accepted": manual_image_accepted,
                "audience_visual": record.get("audience_visual") if isinstance(record.get("audience_visual"), dict) else {},
                "audience_preflight": record.get("audience_preflight") if isinstance(record.get("audience_preflight"), dict) else {},
                "generation_decision": record.get("generation_decision") if isinstance(record.get("generation_decision"), dict) else {},
                "prompt_url": f"/data/projects/{project_id}/scenes/{prompt_path.name}" if prompt_path.exists() else "",
                "audit": audit if isinstance(audit, dict) else {},
            }
            current = existing_by_index.get(index)
            if current is None:
                existing_by_index[index] = candidate
                continue
            current_priority = suffix_priority.get(Path(current["filename"]).suffix.lower(), 999)
            candidate_priority = suffix_priority.get(path.suffix.lower(), 999)
            if candidate_priority < current_priority:
                existing_by_index[index] = candidate
    all_existing = [existing_by_index[index] for index in sorted(existing_by_index)]
    if expected <= 0:
        if isinstance(prompt_records, list) and prompt_records:
            expected = len(prompt_records)
            expected_source = "prompt_records"
        elif all_existing:
            expected = max(item["index"] for item in all_existing)
            expected_source = "existing_files"
    existing = [
        item
        for item in all_existing
        if expected <= 0 or int(item.get("index", 0) or 0) <= expected
    ]
    extra_items = [
        item
        for item in all_existing
        if expected > 0 and int(item.get("index", 0) or 0) > expected
    ]
    existing_indexes = {item["index"] for item in existing}
    missing = [f"s_{idx:02d}" for idx in range(1, expected + 1) if idx not in existing_indexes]
    missing_items = [
        {
            "filename": f"s_{idx:02d}.png",
            "stem": f"s_{idx:02d}",
            "index": idx,
            "expected_path": f"scenes/s_{idx:02d}.png",
        }
        for idx in range(1, expected + 1)
        if idx not in existing_indexes
    ]
    hidden_variants = sum(max(0, count - 1) for count in variant_count_by_index.values())
    candidate_status = _scene_candidate_groups(project_id)
    return {
        "expected_count": expected,
        "generated_count": len(existing),
        "actual_file_count": len(all_existing),
        "existing": existing,
        "extra_items": extra_items,
        "extra_count": len(extra_items),
        "missing": missing,
        "missing_items": missing_items,
        "hidden_variants": hidden_variants,
        "candidate_review_mode": candidate_status["mode"],
        "candidate_count": candidate_status["candidate_count"],
        "candidate_group_count": candidate_status["candidate_group_count"],
        "candidate_groups": candidate_status["groups"],
        "expected_source": expected_source,
        "raw_summary_count": raw_summary_count,
        "timeline_count": timeline_count,
        "timeline_audio_ms": timeline_audio_ms,
        "timeline_fresh": timeline_fresh,
        "scene_count_mode": settings.get("scene_count_mode", "auto"),
        "scene_count_fixed": settings.get("scene_count_fixed", 6),
        "complete": expected == 0 or not missing,
    }


def cleanup_scene_outputs(project_id: int) -> int:
    scene_dir = project_file(project_id, "scenes")
    if not scene_dir.exists():
        return 0
    removed = 0
    removable_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".md"}
    for path in scene_dir.iterdir():
        if not path.is_file():
            continue
        if re.fullmatch(r"s_\d+\.(?:audit|overlay)", path.stem) and path.suffix.lower() == ".json":
            path.unlink(missing_ok=True)
            removed += 1
            continue
        if re.fullmatch(r"s_\d+\.source", path.stem) and path.suffix.lower() in removable_suffixes:
            path.unlink(missing_ok=True)
            removed += 1
            continue
        if not re.fullmatch(r"s_\d+", path.stem):
            continue
        if path.suffix.lower() not in removable_suffixes:
            continue
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def cleanup_extra_scene_outputs(project_id: int, expected_count: int) -> int:
    scene_dir = project_file(project_id, "scenes")
    if not scene_dir.exists():
        return 0
    expected_count = max(0, int(expected_count or 0))
    if expected_count <= 0:
        return 0
    removed = 0
    removable_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".md"}
    for path in scene_dir.iterdir():
        if not path.is_file():
            continue
        sidecar_match = re.fullmatch(r"s_(\d+)\.(?:audit|overlay)", path.stem)
        if sidecar_match and path.suffix.lower() == ".json":
            index = int(sidecar_match.group(1))
            if index > expected_count:
                path.unlink(missing_ok=True)
                removed += 1
            continue
        source_match = re.fullmatch(r"s_(\d+)\.source", path.stem)
        if source_match and path.suffix.lower() in removable_suffixes:
            index = int(source_match.group(1))
            if index > expected_count:
                path.unlink(missing_ok=True)
                removed += 1
            continue
        match = re.fullmatch(r"s_(\d+)", path.stem)
        if not match:
            continue
        if path.suffix.lower() not in removable_suffixes:
            continue
        index = int(match.group(1))
        if index <= expected_count:
            continue
        path.unlink(missing_ok=True)
        removed += 1
    records_path = project_file(project_id, "scenes/scene_prompts.json")
    records = read_json(records_path, [])
    if isinstance(records, list):
        kept: list[Any] = []
        removed_records = 0
        for record in records:
            if not isinstance(record, dict):
                kept.append(record)
                continue
            filename = str(record.get("filename") or "").strip()
            match = re.search(r"s_(\d+)", filename)
            if match and int(match.group(1)) > expected_count:
                removed_records += 1
                continue
            kept.append(record)
        if removed_records:
            write_json(records_path, kept)
            removed += removed_records
    return removed


def latest_job_path(project_id: int) -> Path:
    return project_file(project_id, "jobs/latest.json")


def save_latest_job(project_id: int, payload: dict[str, Any]) -> None:
    write_json(latest_job_path(project_id), payload)
    job_id = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(payload.get("id") or "")).strip("-.")
    if job_id:
        write_json(project_file(project_id, f"jobs/{job_id}.json"), payload)
    meta = get_project(project_id)
    meta["last_job_status"] = payload.get("status", "idle")
    write_project_meta(project_id, meta)


def load_latest_job(project_id: int) -> dict[str, Any] | None:
    path = latest_job_path(project_id)
    if not path.exists():
        return None
    return read_json(path, None)


def list_job_history(project_id: int, limit: int = 20) -> list[dict[str, Any]]:
    jobs_dir = project_file(project_id, "jobs")
    if not jobs_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in jobs_dir.glob("job-*.json"):
        payload = read_json(path, {})
        if not isinstance(payload, dict) or not payload.get("id"):
            continue
        records.append(payload)
    records.sort(
        key=lambda item: float(item.get("started_at") or item.get("updated_at") or 0),
        reverse=True,
    )
    return records[: max(1, min(int(limit or 20), 100))]


def clear_latest_job_log(project_id: int) -> dict[str, Any]:
    payload = load_latest_job(project_id) or {}
    cleared = {
        **payload,
        "log": "",
        "cleared_at": now_ts(),
    }
    write_json(latest_job_path(project_id), cleared)
    return cleared
