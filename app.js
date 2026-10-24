const API_BASE = "http://127.0.0.1:8765";
const UI_MODE_KEY = "short-video-studio.ui-mode";

function storedAdvancedMode() {
  try {
    return window.localStorage.getItem(UI_MODE_KEY) === "advanced";
  } catch (_error) {
    return false;
  }
}

const STEP_DEFS = [
  { key: "audio", label: "配音生成", desc: "生成口播音频与文稿" },
  { key: "subtitles", label: "字幕对齐", desc: "输出字幕与时间轴" },
  { key: "images", label: "分镜出图", desc: "智能复用旧图，只重绘缺失或不匹配编号" },
  { key: "covers", label: "封面出图", desc: "生成横屏、竖屏与图文封面" },
  { key: "images_missing", label: "补缺失场景图", desc: "只生成缺失编号，保留已有图片", defaultChecked: false },
  { key: "covers_missing", label: "补缺失封面", desc: "只生成未生成的封面", defaultChecked: false },
  { key: "article", label: "图文版", desc: "输出图文发布版 markdown" },
  { key: "video", label: "成片合成", desc: "合成最终 mp4 成片并写出发布目录", defaultChecked: false },
];

const IMAGE_PROVIDER_OPTIONS = [
  { value: "cpa_image", label: "本地 CPA API 生图" },
  { value: "auto_no_apiyi", label: "自动选择（不使用第三方接口）" },
  { value: "ark", label: "火山方舟 Seedream" },
  { value: "agnes", label: "Agnes Image 2.1 Flash（API）" },
  { value: "imageai_playground", label: "GPT Image Playground 网页" },
  { value: "newapi", label: "NewAPI / OpenAI Image" },
  { value: "third_party", label: "第三方 OpenAI 兼容" },
  { value: "chatgpt_web_auto", label: "ChatGPT 网页自动化" },
  { value: "chatgpt_web_handoff", label: "ChatGPT 网页接力" },
  { value: "chatgpt_desktop_handoff", label: "ChatGPT Classic 手动接力（粘贴/保存）" },
  { value: "apiyi", label: "API易 / OpenAI 兼容" },
  { value: "auto", label: "自动选择（原逻辑）" },
];

const state = {
  backendOnline: false,
  templates: [],
  templatesLoaded: false,
  templatesLoading: false,
  templatesError: "",
  projects: [],
  selectedTemplateKey: "",
  currentProject: null,
  currentContent: null,
  sourceMaterials: [],
  sourceCandidates: null,
  currentJob: null,
  currentFiles: null,
  sceneStatus: null,
  imageReview: null,
  stageGates: null,
  projectStatus: null,
  productionManifest: null,
  voiceStatus: null,
  bgmStatus: null,
  chatgptAccounts: null,
  videoSelfCheck: null,
  releaseLinks: [],
  releasePlatformStats: null,
  releaseMetricsSync: {
    projectId: null,
    running: false,
    lastAttemptAt: 0,
    message: "",
  },
  releaseAutomation: null,
  releaseAccountCatalog: null,
  config: null,
  packaging: null,
  ttsPreviews: null,
  activeTab: "content",
  advancedMode: storedAdvancedMode(),
  pollTimer: null,
  pollTick: 0,
  pollBusy: false,
  jobPollTimer: null,
  jobPollBusy: false,
  jobPollFailures: 0,
  lastJobPollSuccessAt: 0,
  lastIdleJobPollAt: 0,
  autoVideo: null,
  autoVideoTimer: null,
  packagingTimer: null,
  autoVideoModalVisible: false,
  autoVideoOpenedProjectId: null,
  autoVideoDrafts: {},
  revealedSecrets: {},
  audioPreview: null,
  audioPreviewButton: null,
  productionAssetTab: "scenes",
  bgmMixPreviewVersion: "",
  editor: {
    projectId: null,
    briefDirty: false,
    contentDirty: false,
    lastBrief: "",
    lastContent: "",
  },
  releaseEditor: {
    projectId: null,
    lastDraft: "",
    saveTimer: null,
  },
};

const els = {
  studioShell: document.getElementById("app"),
  workspaceModeToggle: document.getElementById("workspace-mode-toggle"),
  backendBanner: document.getElementById("backend-banner"),
  backendStatus: document.getElementById("backend-status"),
  workspaceTitle: document.getElementById("workspace-title"),
  workspaceSubtitle: document.getElementById("workspace-subtitle"),
  taskCommandBar: document.getElementById("task-command-bar"),
  taskCommandStatus: document.getElementById("task-command-status"),
  taskCommandTitle: document.getElementById("task-command-title"),
  taskCommandDetail: document.getElementById("task-command-detail"),
  taskCommandMeter: document.getElementById("task-command-meter"),
  taskCommandMeta: document.getElementById("task-command-meta"),
  taskCommandPrimary: document.getElementById("task-command-primary"),
  taskCommandRefresh: document.getElementById("task-command-refresh"),
  taskCommandCancel: document.getElementById("task-command-cancel"),
  templateList: document.getElementById("template-list"),
  projectList: document.getElementById("project-list"),
  projectListScope: document.getElementById("project-list-scope"),
  briefInput: document.getElementById("brief-input"),
  contentTypeButtons: Array.from(document.querySelectorAll("[data-content-type]")),
  outputLanguageButtons: Array.from(document.querySelectorAll("[data-output-language]")),
  outputLanguageStatus: document.getElementById("output-language-status"),
  productSetupPanel: document.getElementById("product-setup-panel"),
  productName: document.getElementById("product-name"),
  productCategory: document.getElementById("product-category"),
  productTargetCustomer: document.getElementById("product-target-customer"),
  productUsageScenarios: document.getElementById("product-usage-scenarios"),
  productSellingPoints: document.getElementById("product-selling-points"),
  productEvidence: document.getElementById("product-evidence"),
  productOffer: document.getElementById("product-offer"),
  productComplianceNotes: document.getElementById("product-compliance-notes"),
  productAssetList: document.getElementById("product-asset-list"),
  productReferenceStatus: document.getElementById("product-reference-status"),
  productSettingsStatus: document.getElementById("product-settings-status"),
  productSettingsSaveBtn: document.getElementById("product-settings-save-btn"),
  productUploadBtn: document.getElementById("product-upload-btn"),
  productAssetsInput: document.getElementById("product-assets-input"),
  contentInput: document.getElementById("content-input"),
  nextToProduceBtn: document.getElementById("next-to-produce-btn"),
  summaryCards: document.getElementById("summary-cards"),
  referenceList: document.getElementById("reference-list"),
  sourceCountPill: document.getElementById("source-count-pill"),
  sourceUrlInput: document.getElementById("source-url-input"),
  sourceTitleInput: document.getElementById("source-title-input"),
  sourceNoteInput: document.getElementById("source-note-input"),
  sourceMustUseInput: document.getElementById("source-must-use-input"),
  sourceAddBtn: document.getElementById("source-add-btn"),
  sourceUploadBtn: document.getElementById("source-upload-btn"),
  sourceImageInput: document.getElementById("source-image-input"),
  sourceSearchInput: document.getElementById("source-search-input"),
  sourceNewsInput: document.getElementById("source-news-input"),
  sourceSearchBtn: document.getElementById("source-search-btn"),
  sourceSearchStatus: document.getElementById("source-search-status"),
  sourceMaterialList: document.getElementById("source-material-list"),
  sourceCandidateList: document.getElementById("source-candidate-list"),
  contentGenerateStatus: document.getElementById("content-generate-status"),
  contentLearningExplanation: document.getElementById("content-learning-explanation"),
  stepList: document.getElementById("step-list"),
  runJobBtn: document.getElementById("run-job-btn"),
  selectedStepSummary: document.getElementById("selected-step-summary"),
  sampleImageBtn: document.getElementById("sample-image-btn"),
  motionSampleBtn: document.getElementById("motion-sample-btn"),
  nextToFilesBtn: document.getElementById("next-to-files-btn"),
  jobStatusPill: document.getElementById("job-status-pill"),
  jobProgress: document.getElementById("job-progress"),
  jobLog: document.getElementById("job-log"),
  jobLogState: document.getElementById("job-log-state"),
  clearJobLogBtn: document.getElementById("clear-job-log-btn"),
  productionLiveLogPanel: document.getElementById("production-live-log-panel"),
  productionLogJumpBtn: document.getElementById("production-log-jump-btn"),
  sceneGrid: document.getElementById("scene-grid"),
  sceneStatusPill: document.getElementById("scene-status-pill"),
  coverGrid: document.getElementById("cover-grid"),
  coverStatusPill: document.getElementById("cover-status-pill"),
  imageReviewRequired: document.getElementById("image-review-required"),
  imageReviewModeButtons: Array.from(document.querySelectorAll("[data-image-review-mode]")),
  confirmImagesBtn: document.getElementById("confirm-images-btn"),
  imageReviewPill: document.getElementById("image-review-pill"),
  imageReviewHelper: document.getElementById("image-review-helper"),
  stageGatesPanel: document.getElementById("stage-gates-panel"),
  stageGatesRefreshBtn: document.getElementById("stage-gates-refresh-btn"),
  stageGatesSkipAllBtn: document.getElementById("stage-gates-skip-all-btn"),
  productionManifestPanel: document.getElementById("production-manifest-panel"),
  productionManifestPill: document.getElementById("production-manifest-pill"),
  productionManifestRefreshBtn: document.getElementById("production-manifest-refresh-btn"),
  voiceStatusTitle: document.getElementById("voice-status-title"),
  voiceStatusPill: document.getElementById("voice-status-pill"),
  voiceStatusReason: document.getElementById("voice-status-reason"),
  voiceStatusMeta: document.getElementById("voice-status-meta"),
  voiceSettingsBtn: document.getElementById("voice-settings-btn"),
  voiceRebuildBtn: document.getElementById("voice-rebuild-btn"),
  bgmStatusTitle: document.getElementById("bgm-status-title"),
  bgmStatusPill: document.getElementById("bgm-status-pill"),
  bgmStatusReason: document.getElementById("bgm-status-reason"),
  bgmStatusMeta: document.getElementById("bgm-status-meta"),
  bgmPreview: document.getElementById("bgm-preview"),
  bgmMixPreview: document.getElementById("bgm-mix-preview"),
  bgmMixPreviewBtn: document.getElementById("bgm-mix-preview-btn"),
  bgmVolume: document.getElementById("bgm-volume"),
  bgmVolumeValue: document.getElementById("bgm-volume-value"),
  bgmLockBtn: document.getElementById("bgm-lock-btn"),
  bgmRematchBtn: document.getElementById("bgm-rematch-btn"),
  productionStageStrip: document.getElementById("production-stage-strip"),
  productionCockpit: document.querySelector(".production-cockpit"),
  productionCockpitStatus: document.getElementById("production-cockpit-status"),
  productionCockpitKind: document.getElementById("production-cockpit-kind"),
  productionCockpitActionTitle: document.getElementById("production-cockpit-action-title"),
  productionCockpitActionDetail: document.getElementById("production-cockpit-action-detail"),
  productionCockpitElapsed: document.getElementById("production-cockpit-elapsed"),
  productionCockpitEta: document.getElementById("production-cockpit-eta"),
  productionCockpitProgress: document.getElementById("production-cockpit-progress"),
  productionCockpitHuman: document.getElementById("production-cockpit-human"),
  productionCockpitBudgetTitle: document.getElementById("production-cockpit-budget-title"),
  productionCockpitBudgetDetail: document.getElementById("production-cockpit-budget-detail"),
  productionCockpitScenes: document.getElementById("production-cockpit-scenes"),
  productionCockpitCandidates: document.getElementById("production-cockpit-candidates"),
  productionCockpitCovers: document.getElementById("production-cockpit-covers"),
  productionCockpitImageCalls: document.getElementById("production-cockpit-image-calls"),
  productionCockpitNext: document.getElementById("production-cockpit-next"),
  productionCockpitAction: document.getElementById("production-cockpit-action"),
  imageProviderSelect: document.getElementById("image-provider-select"),
  imageProviderSaveBtn: document.getElementById("image-provider-save-btn"),
  imageProviderCurrent: document.getElementById("image-provider-current"),
  chatgptAccountPool: document.getElementById("chatgpt-account-pool"),
  sceneCountMode: document.getElementById("scene-count-mode"),
  sceneCountFixed: document.getElementById("scene-count-fixed"),
  sceneCountSaveBtn: document.getElementById("scene-count-save-btn"),
  sceneCountCurrent: document.getElementById("scene-count-current"),
  coverGenerationStatus: document.getElementById("cover-generation-status"),
  coverEnabledButtons: Array.from(document.querySelectorAll("[data-cover-enabled]")),
  chatgptReloginBtn: document.getElementById("chatgpt-relogin-btn"),
  chatgptLogoutBtn: document.getElementById("chatgpt-logout-btn"),
  projectStatusStrip: document.getElementById("project-status-strip"),
  fileList: document.getElementById("file-list"),
  nextToReleasesBtn: document.getElementById("next-to-releases-btn"),
  nextToDataBtn: document.getElementById("next-to-data-btn"),
  videoSelfCheckBtn: document.getElementById("video-self-check-btn"),
  releaseList: document.getElementById("release-list"),
  syncReleaseMetricsBtn: document.getElementById("sync-release-metrics-btn"),
  importReleaseMetricsBtn: document.getElementById("import-release-metrics-btn"),
  releaseMetricsFileInput: document.getElementById("release-metrics-file-input"),
  releaseMetricsSyncStatus: document.getElementById("release-metrics-sync-status"),
  releasePlatformStats: document.getElementById("release-platform-stats"),
  releaseAutomationSummary: document.getElementById("release-automation-summary"),
  releaseQueueList: document.getElementById("release-queue-list"),
  releaseTaskMeta: document.getElementById("release-task-meta"),
  releaseTaskPill: document.getElementById("release-task-pill"),
  releaseAutomationLog: document.getElementById("release-automation-log"),
  configFields: document.getElementById("config-fields"),
  packagingSummary: document.getElementById("packaging-summary"),
  packagingStatusPill: document.getElementById("packaging-status-pill"),
  packagingLog: document.getElementById("packaging-log"),
  startPortableBuildBtn: document.getElementById("start-portable-build-btn"),
  startZipBuildBtn: document.getElementById("start-zip-build-btn"),
  cancelPackagingBtn: document.getElementById("cancel-packaging-btn"),
  refreshPackagingBtn: document.getElementById("refresh-packaging-btn"),
  openPackagingOutputBtn: document.getElementById("open-packaging-output-btn"),
  releasePlatform: document.getElementById("release-platform"),
  releaseUrl: document.getElementById("release-url"),
  releaseNote: document.getElementById("release-note"),
  releaseImpressions: document.getElementById("release-impressions"),
  releaseClickThroughRate: document.getElementById("release-click-through-rate"),
  releaseViews: document.getElementById("release-views"),
  releaseLikes: document.getElementById("release-likes"),
  releaseComments: document.getElementById("release-comments"),
  releaseShares: document.getElementById("release-shares"),
  releaseFavorites: document.getElementById("release-favorites"),
  releaseFollows: document.getElementById("release-follows"),
  releaseTwoSecondRetention: document.getElementById("release-two-second-retention"),
  releaseFiveSecondRetention: document.getElementById("release-five-second-retention"),
  releaseAverageWatchSeconds: document.getElementById("release-average-watch-seconds"),
  releaseCompletionRate: document.getElementById("release-completion-rate"),
  releaseAutoPlatform: document.getElementById("release-auto-platform"),
  releaseBatchTargets: document.getElementById("release-batch-targets"),
  releasePlatformCapability: document.getElementById("release-platform-capability"),
  releaseAutoAccount: document.getElementById("release-auto-account"),
  releaseAutoBrowserMode: document.getElementById("release-auto-browser-mode"),
  releaseAutoSchedule: document.getElementById("release-auto-schedule"),
  releaseAutoTitle: document.getElementById("release-auto-title"),
  releaseAutoTags: document.getElementById("release-auto-tags"),
  releaseAutoDescription: document.getElementById("release-auto-description"),
  validateConfigBtn: document.getElementById("validate-config-btn"),
  modal: document.getElementById("modal"),
  modalTitle: document.getElementById("modal-title"),
  modalBody: document.getElementById("modal-body"),
  audioInput: document.getElementById("audio-file-input"),
};

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value * 1000);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatValidationTime(value) {
  if (!value) return "";
  const date = new Date(value * 1000);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatMaybeTimestamp(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return formatDate(value);
  const text = String(value).trim();
  if (!text) return "—";
  if (/^\d+$/.test(text)) return formatDate(Number(text));
  return text;
}

function formatByteSize(value) {
  const size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let current = size;
  let index = 0;
  while (current >= 1024 && index < units.length - 1) {
    current /= 1024;
    index += 1;
  }
  return `${current.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function doubaoVoiceOptionsHtml(selectedValue = "") {
  const voices = (state.ttsPreviews?.voices || []).filter((item) => item?.supported !== false && item?.voice_type);
  const groups = new Map();
  for (const voice of voices) {
    const scene = voice.scene || "其他音色";
    if (!groups.has(scene)) groups.set(scene, []);
    groups.get(scene).push(voice);
  }
  if (selectedValue && !voices.some((item) => item.voice_type === selectedValue)) {
    groups.set("当前配置", [{ voice_type: selectedValue, label: selectedValue, language: "" }]);
  }
  if (!groups.size) {
    return `<option value="${escapeHtml(selectedValue)}">${escapeHtml(selectedValue || "请先同步豆包音色")}</option>`;
  }
  return Array.from(groups.entries())
    .map(([scene, items]) => `
      <optgroup label="${escapeHtml(scene)}">
        ${items.map((item) => {
          const selected = item.voice_type === selectedValue ? "selected" : "";
          const language = item.language ? ` · ${item.language}` : "";
          return `<option value="${escapeHtml(item.voice_type)}" ${selected}>${escapeHtml(`${item.label || item.voice_type}${language}`)}</option>`;
        }).join("")}
      </optgroup>
    `)
    .join("");
}

function resetDoubaoVoicePreview() {
  if (state.audioPreview) {
    state.audioPreview.pause();
    state.audioPreview.currentTime = 0;
  }
  if (state.audioPreviewButton) {
    state.audioPreviewButton.textContent = state.audioPreviewButton.dataset.idleLabel || "试听声音";
    state.audioPreviewButton.classList.remove("is-playing");
  }
  state.audioPreview = null;
  state.audioPreviewButton = null;
}

function playDoubaoVoicePreview(select, button = null, playbackRate = 1) {
  const voiceType = select?.value?.trim();
  if (!voiceType) {
    window.alert("请先选择一个豆包音色，再试听。");
    return;
  }
  const entry = (state.ttsPreviews?.voices || []).find((item) => item.voice_type === voiceType);
  if (!entry?.audio_url) {
    window.alert(`当前音色 ${voiceType} 没有本地试听样音。`);
    return;
  }
  const audioUrl = `${API_BASE}${entry.audio_url}`;
  if (state.audioPreview && state.audioPreview.src === audioUrl && !state.audioPreview.paused) {
    resetDoubaoVoicePreview();
    return;
  }
  resetDoubaoVoicePreview();
  if (button) {
    button.dataset.idleLabel = button.textContent?.trim() || "试听声音";
    button.textContent = "停止试听";
    button.classList.add("is-playing");
    state.audioPreviewButton = button;
  }
  state.audioPreview = new Audio(audioUrl);
  state.audioPreview.preservesPitch = true;
  state.audioPreview.playbackRate = Math.max(0.8, Math.min(Number(playbackRate) || 1, 1.2));
  state.audioPreview.addEventListener("ended", resetDoubaoVoicePreview, { once: true });
  state.audioPreview.play().catch(() => {
    resetDoubaoVoicePreview();
    window.alert("浏览器没有成功播放试听音频，请稍后重试。");
  });
}

function orphanTemplates() {
  if (!state.templatesLoaded) return [];
  const known = new Set((state.templates || []).map((template) => template.key));
  const groups = new Map();
  for (const project of state.projects || []) {
    if (known.has(project.template)) continue;
    const entry = groups.get(project.template) || {
      key: project.template,
      count: 0,
      latestTopic: project.topic_name,
    };
    entry.count += 1;
    entry.latestTopic = project.topic_name || entry.latestTopic;
    groups.set(project.template, entry);
  }
  return Array.from(groups.values()).sort((a, b) => a.key.localeCompare(b.key, "zh-CN"));
}

function isTemplateLocked(template) {
  return Boolean(template?.builtin_locked);
}

function templateProjectCount(templateKey) {
  return (state.projects || []).filter((project) => project.template === templateKey).length;
}

function hasTemplateOrProjects(templateKey) {
  if (!templateKey) return false;
  return (state.templates || []).some((template) => template.key === templateKey)
    || (state.projects || []).some((project) => project.template === templateKey);
}

function ensureSelectedTemplateKey() {
  if (hasTemplateOrProjects(state.selectedTemplateKey)) return;
  if (state.currentProject?.template) {
    state.selectedTemplateKey = state.currentProject.template;
    return;
  }
  const firstWithProjects = (state.templates || []).find((template) => templateProjectCount(template.key) > 0);
  state.selectedTemplateKey = firstWithProjects?.key || state.templates?.[0]?.key || "";
}

function selectedTemplateKey() {
  ensureSelectedTemplateKey();
  return state.selectedTemplateKey || "";
}

function selectedTemplate() {
  const key = selectedTemplateKey();
  return (state.templates || []).find((template) => template.key === key) || null;
}

function projectsForSelectedTemplate() {
  const key = selectedTemplateKey();
  if (!key) return state.projects || [];
  return (state.projects || []).filter((project) => project.template === key);
}

function adaptPromptChannelName(prompt, baseTemplate, newKey) {
  let result = prompt || "";
  const names = [baseTemplate?.key, baseTemplate?.name, baseTemplate?.brand_name]
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  for (const name of Array.from(new Set(names))) {
    if (name && name !== newKey) {
      result = result.split(name).join(newKey);
    }
  }
  return result;
}

function validateTemplatePromptText(prompt) {
  const cleaned = String(prompt || "").trim();
  const compact = cleaned.replace(/\s+/g, "");
  if (compact.length < 120) {
    return "频道 prompt.md 太短。请至少写清楚频道人设、内容结构、画面风格和禁忌，避免生成退回通用模板。";
  }
  const hints = ["人设", "口吻", "结构", "封面", "场景", "图片", "禁忌", "互动"];
  const matched = hints.filter((hint) => cleaned.includes(hint)).length;
  if (matched < 2) {
    return "频道 prompt.md 缺少频道规则。建议写明人设/口吻、脚本结构、封面与场景图风格、禁忌和互动方式。";
  }
  return "";
}

function resetEditorState(projectId = state.currentProject?.id ?? null, brief = "", content = "") {
  state.editor.projectId = projectId;
  state.editor.briefDirty = false;
  state.editor.contentDirty = false;
  state.editor.lastBrief = brief;
  state.editor.lastContent = content;
  els.briefInput.value = brief;
  els.contentInput.value = content;
}

function syncEditorFromBundle(bundle, { force = false } = {}) {
  const projectId = state.currentProject?.id ?? null;
  const nextBrief = bundle?.brief || "";
  const nextContent = bundle?.content || "";
  const projectChanged = state.editor.projectId !== projectId;

  if (!bundle) {
    if (force || projectChanged || !state.editor.briefDirty) {
      els.briefInput.value = "";
    }
    if (force || projectChanged || !state.editor.contentDirty) {
      els.contentInput.value = "";
    }
    state.editor.projectId = projectId;
    state.editor.lastBrief = "";
    state.editor.lastContent = "";
    if (force || projectChanged) {
      state.editor.briefDirty = false;
      state.editor.contentDirty = false;
    }
    return;
  }

  if (force || projectChanged) {
    resetEditorState(projectId, nextBrief, nextContent);
    return;
  }

  state.editor.lastBrief = nextBrief;
  state.editor.lastContent = nextContent;
  if (!state.editor.briefDirty && document.activeElement !== els.briefInput) {
    els.briefInput.value = nextBrief;
  }
  const editorHasNoContent = !String(els.contentInput.value || "").trim() && Boolean(nextContent.trim());
  if (editorHasNoContent || (!state.editor.contentDirty && document.activeElement !== els.contentInput)) {
    els.contentInput.value = nextContent;
    if (editorHasNoContent) state.editor.contentDirty = false;
  }
}

function clearCurrentWorkspace() {
  state.currentProject = null;
  state.currentContent = null;
  state.sourceMaterials = [];
  state.sourceCandidates = null;
  state.currentJob = null;
  state.currentFiles = null;
  state.sceneStatus = null;
  state.imageReview = null;
  state.projectStatus = null;
  state.productionManifest = null;
  state.voiceStatus = null;
  state.bgmStatus = null;
  state.videoSelfCheck = null;
  state.releaseLinks = [];
  state.releaseAutomation = null;
  state.releaseMetricsSync = { projectId: null, running: false, lastAttemptAt: 0, message: "" };
  renderContentBundle({ forceEditor: true });
  renderJob();
  renderFiles();
  renderScenes();
  renderImageReview();
  renderProductionManifest();
  renderVoiceStatus();
  renderBgmStatus();
  renderProjectStatus();
  renderReleases();
  renderReleaseAutomation();
}

function renderWorkspacePlaceholderForSelectedTemplate() {
  const key = selectedTemplateKey();
  els.workspaceTitle.textContent = "请选择一个主题";
  els.workspaceSubtitle.textContent = key
    ? `${key} · 当前频道还没有打开的主题项目`
    : "请选择左侧频道，再新建或打开一个主题项目";
}

async function selectTemplateProjects(templateKey, { openFirst = true } = {}) {
  state.selectedTemplateKey = templateKey || "";
  const projects = projectsForSelectedTemplate();
  renderTemplates();
  renderProjects();
  const currentVisible = state.currentProject && projects.some((project) => project.id === state.currentProject.id);
  if (openFirst && !currentVisible) {
    if (projects.length) {
      await openProject(projects[0].id);
      return;
    }
    clearCurrentWorkspace();
    renderWorkspacePlaceholderForSelectedTemplate();
    renderProjects();
    renderTemplates();
  }
}

async function deleteTemplateByKey(key) {
  const template = state.templates.find((item) => item.key === key);
  if (isTemplateLocked(template)) {
    window.alert("内置频道模板不能删除。");
    return false;
  }

  const count = templateProjectCount(key);
  const message = count
    ? `确认删除频道模板「${key}」吗？会同时删除该频道下 ${count} 个主题项目、模板目录和产物目录。`
    : `确认删除频道模板「${key}」吗？会删除模板目录和产物目录。`;
  if (!window.confirm(message)) return false;

  const deletingCurrentTemplate = state.currentProject?.template === key;
  await api(`/api/templates/${encodeURIComponent(key)}?delete_projects=${count > 0 ? "true" : "false"}`, {
    method: "DELETE",
  });
  if (deletingCurrentTemplate) {
    clearCurrentWorkspace();
  }
  if (state.selectedTemplateKey === key) {
    state.selectedTemplateKey = "";
  }
  if (!els.modal.classList.contains("hidden")) {
    closeModal();
  }
  await refreshTemplates();
  await refreshProjects();
  return true;
}

function formatBytes(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function versionedProjectUrl(item) {
  const rawUrl = item?.url || "";
  if (!rawUrl) return "";
  const modifiedAt = Number(item?.modified_at || 0);
  if (!Number.isFinite(modifiedAt) || modifiedAt <= 0) return rawUrl;
  const separator = rawUrl.includes("?") ? "&" : "?";
  return `${rawUrl}${separator}v=${Math.floor(modifiedAt * 1000)}`;
}

function findOutputByStem(files, stem) {
  const outputs = files?.outputs || [];
  const suffixes = [".png", ".jpg", ".jpeg", ".webp", ".svg"];
  for (const suffix of suffixes) {
    const match = outputs.find((item) => item.relative_path === `${stem}${suffix}`);
    if (match) return match;
  }
  return null;
}

function findOutputByPath(files, relativePath) {
  return (files?.outputs || []).find((item) => item.relative_path === relativePath) || null;
}

function coverRecords(files) {
  return [
    {
      key: "landscape",
      label: "横屏封面",
      ratio: "16:9",
      image: findOutputByStem(files, "covers/cover_landscape"),
      prompt: findOutputByPath(files, "covers/cover_landscape.md"),
    },
    {
      key: "story",
      label: "图文封面",
      ratio: "4:3",
      image: findOutputByStem(files, "covers/cover_story"),
      prompt: findOutputByPath(files, "covers/cover_story.md"),
    },
    {
      key: "portrait",
      label: "竖屏封面",
      ratio: "3:4",
      image: findOutputByStem(files, "covers/cover_portrait"),
      prompt: findOutputByPath(files, "covers/cover_portrait.md"),
    },
  ];
}

function imageAuditHtml(audit = {}) {
  const severity = audit?.severity || (audit?.ok === false ? "warn" : "ok");
  const reasons = Array.isArray(audit?.reasons) ? audit.reasons.filter(Boolean) : [];
  const warnings = Array.isArray(audit?.warnings) ? audit.warnings.filter(Boolean) : [];
  const provider = audit?.provider_label || audit?.provider || "";
  const ocr = audit?.ocr || {};
  const ocrLabel = ocr?.status === "ok" ? `OCR ${ocr.line_count || 0} 行` : ocr?.status === "unavailable" ? "OCR 未启用" : "";
  const label = severity === "hard" ? "需重看" : severity === "soft" ? "轻微提示" : "自检通过";
  return `
    <div class="media-card__audit">
      <span class="pill ${severity === "hard" ? "pill--warn" : ""}">${escapeHtml(label)}</span>
      ${provider ? `<span class="muted">${escapeHtml(provider)}</span>` : ""}
      ${ocrLabel ? `<span class="muted">${escapeHtml(ocrLabel)}</span>` : ""}
      ${reasons.length ? `<div class="muted">${escapeHtml(reasons.join("、"))}</div>` : ""}
      ${warnings.length ? `<div class="muted">${escapeHtml(warnings.join("、"))}</div>` : ""}
    </div>
  `;
}

function imagePromptPreviewHtml(prompt = "", fallback = "暂无提示词摘要", label = "") {
  const text = String(prompt || "").replace(/\r/g, "").trim();
  return `
    <div class="media-card__prompt-block">
      ${label ? `<div class="media-card__prompt-label">${escapeHtml(label)}</div>` : ""}
      <div class="media-card__prompt-preview">${escapeHtml(text || fallback)}</div>
    </div>
  `;
}

function imageTechnicalDetailsHtml(content, label = "提示词与自检") {
  return `
    <details class="media-card__technical">
      <summary>${escapeHtml(label)}</summary>
      <div class="media-card__technical-body">${content}</div>
    </details>
  `;
}

function audienceVisualContractHtml(item = {}) {
  const plan = item?.audience_visual || item?.audit?.audience_visual || {};
  const preflight = item?.audience_preflight || {};
  const decision = item?.generation_decision || {};
  const takeaway = plan?.audience_takeaway || "";
  if (!takeaway) return "";
  const roleLabels = {
    hook: "开场钩子",
    evidence: "核心证据",
    process: "操作步骤",
    verdict: "反转结论",
    context: "过渡画面",
  };
  const issues = Array.isArray(preflight?.issues) ? preflight.issues.filter(Boolean) : [];
  const repairs = Array.isArray(preflight?.repair_actions) ? preflight.repair_actions.filter(Boolean) : [];
  return `
    <div class="audience-contract">
      <div class="audience-contract__head">
        <strong>观众 1 秒验收</strong>
        <span class="pill">${escapeHtml(roleLabels[decision?.role] || plan?.visual_role || "当前镜头")}</span>
        <span class="muted">优先级 ${escapeHtml(decision?.priority ?? plan?.image_priority ?? "-")}</span>
      </div>
      <div class="audience-contract__takeaway">${escapeHtml(takeaway)}</div>
      ${plan?.proof_target ? `<div class="muted">画面证据：${escapeHtml(plan.proof_target)}</div>` : ""}
      ${issues.length ? `<div class="audience-contract__issue">待修：${escapeHtml(issues.join("、"))}</div>` : ""}
      ${repairs.length ? `<div class="muted">重构动作：${escapeHtml(repairs[0])}</div>` : ""}
    </div>
  `;
}

function sceneCardHtml(item) {
  const promptPreview = item.prompt || item.prompt_preview || "";
  const policy = item.prompt_policy_version ? ` · ${item.prompt_policy_version}` : "";
  const pending = Boolean(item.prompt_pending_redraw);
  const generateCandidate = state.imageReview?.required !== false;
  const imageActionLabel = generateCandidate ? "生成备选" : "调整 / 重绘";
  return `
    <article class="media-card media-card--workbench media-card--scene">
      <img src="${API_BASE}${versionedProjectUrl(item)}" alt="${escapeHtml(item.filename)}" />
      <div class="media-card__body">
        <div class="media-card__title-row">
          <strong>${escapeHtml(item.filename)}</strong>
          <span class="pill ${pending ? "pill--warn" : ""}">${pending ? "待按新策略重绘" : "使用中"}</span>
        </div>
        ${audienceVisualContractHtml(item)}
        ${imageTechnicalDetailsHtml(`
          ${imagePromptPreviewHtml(promptPreview, "暂无当前提示词", `当前待生图提示词${policy}`)}
          ${pending && item.actual_prompt_preview ? imagePromptPreviewHtml(item.actual_prompt_preview, "", "这张旧图实际使用的提示词") : ""}
          ${imageAuditHtml(item.audit || {})}
        `)}
        <div class="media-card__actions">
          <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(item))}">打开图片</button>
          ${item.prompt_url ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(item.prompt_url)}">当前提示词</button>` : ""}
          <button class="btn btn--primary" data-regenerate-image-kind="scene" data-regenerate-image-target="${escapeHtml(item.filename)}" data-regenerate-image-label="${escapeHtml(item.filename)}" data-regenerate-image-as-candidate="${generateCandidate ? "true" : "false"}">${escapeHtml(imageActionLabel)}</button>
          <button class="btn btn--danger" data-delete-file="${escapeHtml(item.relative_path || `scenes/${item.filename}`)}">弃用</button>
        </div>
      </div>
    </article>
  `;
}

function missingSceneCardHtml(item) {
  const filename = item.filename || `${item.stem || "s_01"}.png`;
  return `
    <article class="media-card media-card--placeholder media-card--workbench media-card--scene">
      <div class="media-card__preview">
        <div>
          <strong>${escapeHtml(filename)}</strong>
          <div class="muted">缺失 · 可单张补生成</div>
        </div>
      </div>
      <div class="media-card__body">
        <div class="media-card__title-row">
          <strong>${escapeHtml(filename)}</strong>
          <span class="pill pill--warn">缺失</span>
        </div>
        ${imagePromptPreviewHtml("", "点“生成这一张”会按频道、主题和对应口播重新取提示词。")}
        <div class="media-card__actions">
          <button class="btn btn--primary" data-regenerate-image-kind="scene" data-regenerate-image-target="${escapeHtml(filename)}" data-regenerate-image-label="${escapeHtml(filename)}">生成这一张</button>
        </div>
      </div>
    </article>
  `;
}

function visualConceptHtml(concept, fallback = "") {
  if (!concept || typeof concept !== "object") return fallback ? `<div class="muted">${escapeHtml(fallback)}</div>` : "";
  const name = String(concept.name || concept.id || "入选构思").trim();
  const thesis = String(concept.visual_thesis || concept.why_click || "").trim();
  if (!name && !thesis) return "";
  return `<div class="visual-concept-note"><strong>${escapeHtml(name)}</strong>${thesis ? `<span>${escapeHtml(thesis)}</span>` : ""}</div>`;
}

function actualImageJudgeLabel(item) {
  return item?.judge_mode === "multimodal_actual_image_review" ? "视觉模型已看图复评" : "本地真实画质/OCR 复评";
}

function sceneCandidateCardHtml(group, item) {
  const isSelected = Boolean(item.is_selected);
  const isRecommended = Boolean(item.is_ai_recommended);
  const manuallySelected = isSelected && group.selection_mode === "manual";
  const autoSelected = isSelected && group.selection_mode === "ai_auto";
  const jobRunning = Boolean(state.currentJob?.running);
  const statusLabel = manuallySelected
    ? "人工采用"
    : autoSelected
      ? "AI 已采用"
      : isRecommended
        ? "AI 推荐"
        : `方案 ${item.variant}`;
  const actionLabel = manuallySelected
    ? "当前采用"
    : isSelected && group.selection_pending
      ? `确认采用 ${item.variant}`
      : `采用 ${item.variant}`;
  const actionDisabled = jobRunning || manuallySelected || autoSelected;
  const scoreLabel = Number(item.score || 0) > 0 ? `${item.score} 分` : "待评分";
  return `
    <article class="media-card media-card--workbench media-card--scene media-card--candidate ${isSelected ? "media-card--candidate-selected" : ""}">
      <img src="${API_BASE}${versionedProjectUrl(item)}" alt="场景 ${group.scene_index} 候选 ${escapeHtml(item.variant)}" />
      <div class="media-card__body">
        <div class="media-card__title-row">
          <strong>方案 ${escapeHtml(item.variant)}</strong>
          <span class="pill ${isRecommended ? "pill--accent" : ""}">${escapeHtml(statusLabel)}</span>
        </div>
        <div class="media-card__meta">成图评分：${escapeHtml(scoreLabel)} · ${escapeHtml(actualImageJudgeLabel(item))}</div>
        ${visualConceptHtml(item.concept)}
        ${imageTechnicalDetailsHtml(`
          ${imagePromptPreviewHtml(item.prompt || item.prompt_preview || "", "提示词仍在生成或恢复中", "候选实际提示词")}
          ${imageAuditHtml(item.audit || {})}
        `)}
        <div class="media-card__actions">
          <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(item))}">打开图片</button>
          ${item.prompt_url ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(item.prompt_url)}">查看提示词</button>` : ""}
          <button
            class="btn ${manuallySelected || autoSelected ? "btn--ghost" : "btn--primary"}"
            data-select-scene-candidate="true"
            data-scene-candidate-index="${group.scene_index}"
            data-scene-candidate-variant="${escapeHtml(item.variant)}"
            ${actionDisabled ? "disabled" : ""}
          >${escapeHtml(jobRunning ? "生成完成后可选择" : actionLabel)}</button>
        </div>
      </div>
    </article>
  `;
}

function sceneReviewSpeechAnchor(group, official) {
  const openingContract = group?.opening_contract || {};
  const contractAnchor = String(openingContract.opening_line || openingContract.first_scene_speech || "").trim();
  if (contractAnchor) return contractAnchor.slice(0, 160);
  const candidate = (Array.isArray(group?.candidates) ? group.candidates : []).find((item) => item?.prompt);
  const source = String(candidate?.prompt || official?.prompt || "").replace(/\r/g, "");
  const patterns = [
    /(?:当前完整口播|当前口播重点|口播原文|对应口播)[：:]\s*([^\n]{4,180})/i,
    /(?:本镜口播|口播)[：:]\s*([^\n]{4,180})/i,
  ];
  for (const pattern of patterns) {
    const match = source.match(pattern);
    if (match?.[1]) return match[1].replace(/\s+/g, " ").trim().slice(0, 160);
  }
  return "本镜正式图与候选图应共同回应当前口播；只比较画面表达，不会额外生成图片。";
}

function sceneCurrentReviewCardHtml(group, official) {
  const jobRunning = Boolean(state.currentJob?.running);
  if (!official) {
    return `
      <article class="media-card media-card--placeholder media-card--workbench media-card--scene media-card--current-review">
        <div class="media-card__preview">
          <div>
            <strong>s_${String(group.scene_index).padStart(2, "0")}.png</strong>
            <div class="muted">当前没有正式图</div>
          </div>
        </div>
        <div class="media-card__body">
          <div class="media-card__title-row">
            <strong>当前正式图</strong>
            <span class="pill pill--warn">缺失</span>
          </div>
          <div class="media-card__prompt-preview">采用右侧候选后，它才会成为成片实际读取的正式图。</div>
        </div>
      </article>
    `;
  }
  const pending = Boolean(official.prompt_pending_redraw);
  const isOpeningCompetition = group.role === "opening_hook_competition";
  const currentRecommended = String(group.ai_recommended_variant || "").toUpperCase() === "CURRENT";
  const currentScore = Number(group.current_score || 0);
  const currentJudge = group.current || {};
  return `
    <article class="media-card media-card--workbench media-card--scene media-card--current-review">
      <img src="${API_BASE}${versionedProjectUrl(official)}" alt="场景 ${group.scene_index} 当前正式图" />
      <div class="media-card__body">
        <div class="media-card__title-row">
          <strong>${isOpeningCompetition ? "方案 A · 当前正式图" : "当前正式图"}</strong>
          <span class="pill ${currentRecommended ? "pill--accent" : pending ? "pill--warn" : "pill--success"}">${currentRecommended ? "AI 推荐" : pending ? "旧策略" : "成片使用中"}</span>
        </div>
        ${isOpeningCompetition && currentScore ? `<div class="media-card__meta">成图评分：${currentScore} 分 · ${escapeHtml(actualImageJudgeLabel(currentJudge))}</div>` : ""}
        ${isOpeningCompetition ? visualConceptHtml(currentJudge.concept) : ""}
        ${imageTechnicalDetailsHtml(`
          ${imagePromptPreviewHtml(official.prompt || official.prompt_preview || "", "暂无当前提示词", "当前正式图提示词")}
          ${imageAuditHtml(official.audit || {})}
        `)}
        <div class="media-card__actions">
          <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(official))}">打开图片</button>
          ${official.prompt_url ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(official.prompt_url)}">查看提示词</button>` : ""}
          ${group.selection_pending ? `<button class="btn btn--primary" data-keep-current-scene="${group.scene_index}" ${jobRunning ? "disabled" : ""}>${isOpeningCompetition ? "采用方案 A" : "保留当前旧图"}</button>` : ""}
        </div>
      </div>
    </article>
  `;
}

function sceneCandidateGroupHtml(group, official) {
  const candidates = Array.isArray(group.candidates) ? group.candidates : [];
  const isOpeningCompetition = group.role === "opening_hook_competition";
  const modeText = group.selection_mode === "manual"
    ? `已人工采用 ${group.selected_variant || "候选图"}，候选文件正在清理。`
    : group.selection_mode === "ai_auto"
      ? `全自动模式已由 AI 采用 ${group.selected_variant || group.ai_recommended_variant || "评分更高方案"}。`
      : isOpeningCompetition
        ? `首镜先完成 ${Number(group.concept_count || 3)} 个文字构思，只生成前 ${Number(group.generated_count || 2)} 名；真实成图复评推荐 ${group.ai_recommended_variant === "CURRENT" ? "方案 A" : `方案 ${group.ai_recommended_variant || "待评分"}`}，普通镜头仍保持单图。`
      : group.role === "repair_candidate"
        ? "正式图仍保留；这里只显示 1 张待审替换图，再次重绘会覆盖它，不会继续追加。"
        : `AI 推荐 ${group.ai_recommended_variant || "尚未产生"}，请比较候选后人工确认。`;
  return `
    <section class="scene-candidate-group">
      <div class="scene-candidate-group__head">
        <div>
          <strong>${isOpeningCompetition ? "首镜吸引力竞选 · 3 构思 → 2 成图 → 1 采用" : `场景 ${group.scene_index} · 正式图与候选图对比`}</strong>
          <div class="muted">${escapeHtml(modeText)}</div>
          <div class="scene-candidate-group__speech"><span>口播锚点</span>${escapeHtml(sceneReviewSpeechAnchor(group, official))}</div>
        </div>
        <span class="pill ${candidates.length ? "" : "pill--warn"}">${candidates.length ? `${Number(group.concept_count || candidates.length + 1)} 个构思 / ${candidates.length + (official ? 1 : 0)} 张成图` : "等待生成"}</span>
      </div>
      <div class="scene-review-compare">
        <div class="scene-review-compare__column">
          <div class="scene-review-compare__label">${isOpeningCompetition ? "方案 A · 当前成片使用" : "当前成片使用"}</div>
          ${sceneCurrentReviewCardHtml(group, official)}
        </div>
        <div class="scene-review-compare__column scene-review-compare__column--candidates">
          <div class="scene-review-compare__label">${isOpeningCompetition ? "方案 B · 不同视觉构思" : "待审替换方案"}</div>
          <div class="scene-candidate-grid">
            ${candidates.map((item) => sceneCandidateCardHtml(group, item)).join("") || `<div class="muted">候选图仍在生成，完成后会自动出现在这里。</div>`}
          </div>
        </div>
      </div>
    </section>
  `;
}

function coverGalleryCardsHtml(files, includeKeys = null) {
  return coverRecords(files)
    .filter((cover) => !includeKeys || includeKeys.includes(cover.key))
    .map((cover) => {
      if (!cover.image) {
        return `
          <article class="media-card media-card--cover media-card--cover-${escapeHtml(cover.key)} media-card--placeholder">
            <div class="media-card__preview">
              <div>
                <strong>${escapeHtml(cover.label)}</strong>
                <div class="muted">${escapeHtml(cover.ratio)} · 暂未生成</div>
              </div>
            </div>
            <div class="media-card__body">
              <strong>${escapeHtml(cover.label)}</strong>
              <div class="media-card__meta">预计落在 covers/cover_${escapeHtml(cover.key)}.*</div>
              ${imagePromptPreviewHtml("", "点“生成 / 重绘”会按本期标题、钩子和频道风格生成封面提示词。")}
              <div class="media-card__actions">
                <button class="btn btn--ghost" data-regenerate-image-kind="cover" data-regenerate-image-target="${escapeHtml(cover.key)}" data-regenerate-image-label="${escapeHtml(cover.label)}">生成 / 重绘</button>
              </div>
            </div>
          </article>
        `;
      }
      return `
        <article class="media-card media-card--cover media-card--cover-${escapeHtml(cover.key)}">
          <img src="${API_BASE}${versionedProjectUrl(cover.image)}" alt="${escapeHtml(cover.label)}" />
          <div class="media-card__body">
            <div class="media-card__title-row">
              <strong>${escapeHtml(cover.label)} · ${escapeHtml(cover.ratio)}</strong>
              <span class="pill">使用中</span>
            </div>
            <div class="media-card__meta">${escapeHtml(cover.image.absolute_path || cover.image.relative_path || "")}</div>
            ${imagePromptPreviewHtml("", "提示词可在“调整 / 重绘”窗口查看和追加修改。")}
            <div class="media-card__actions">
              <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(cover.image))}">打开图片</button>
              ${cover.prompt ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(cover.prompt))}">查看提示词</button>` : ""}
              <button class="btn btn--primary" data-regenerate-image-kind="cover" data-regenerate-image-target="${escapeHtml(cover.key)}" data-regenerate-image-label="${escapeHtml(cover.label)}">调整 / 重绘</button>
              <button class="btn btn--danger" data-delete-file="${escapeHtml(cover.image.relative_path || `covers/cover_${cover.key}.png`)}">弃用</button>
            </div>
          </div>
        </article>
      `;
    })
    .join("");
}

function coverCandidateComparisonHtml(files, competition) {
  const current = coverRecords(files).find((item) => item.key === "landscape");
  const candidate = competition?.candidate || null;
  if (!current?.image || !candidate) return "";
  const currentRecommended = String(competition.ai_recommended_variant || "").toUpperCase() === "CURRENT";
  const candidateRecommended = String(competition.ai_recommended_variant || "").toUpperCase() === "B";
  const jobRunning = Boolean(state.currentJob?.running);
  const openingContract = competition.opening_contract || {};
  const promise = String(openingContract.opening_line || openingContract.title || "").trim();
  return `
    <section class="scene-candidate-group scene-candidate-group--cover">
      <div class="scene-candidate-group__head">
        <div>
          <strong>封面吸引力竞选 · 3 构思 → 2 成图 → 1 采用</strong>
          <div class="muted">主横屏封面先完成 ${Number(competition.concept_count || 3)} 个文字构思，只生成前 ${Number(competition.generated_count || 2)} 名并按真实成图复评；图文封面和竖屏封面仍各生成 1 张。</div>
          ${promise ? `<div class="scene-candidate-group__speech"><span>标题/首句承诺</span>${escapeHtml(promise)}</div>` : ""}
        </div>
        <span class="pill">${Number(competition.concept_count || 3)} 个构思 / 2 张成图</span>
      </div>
      <div class="scene-review-compare">
        <div class="scene-review-compare__column">
          <div class="scene-review-compare__label">方案 A · 当前封面</div>
          <article class="media-card media-card--cover media-card--current-review">
            <img src="${API_BASE}${versionedProjectUrl(current.image)}" alt="当前横屏封面方案 A" />
            <div class="media-card__body">
              <div class="media-card__title-row">
                <strong>方案 A</strong>
                <span class="pill ${currentRecommended ? "pill--accent" : ""}">${currentRecommended ? "AI 推荐" : "当前使用"}</span>
              </div>
              <div class="media-card__meta">成图评分：${Number(competition.current_score || 0)} 分 · ${escapeHtml(actualImageJudgeLabel(competition.current || {}))}</div>
              ${visualConceptHtml(competition.current?.concept)}
              <div class="media-card__actions">
                <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(current.image))}">打开图片</button>
                <button class="btn btn--primary" data-keep-current-cover="true" ${jobRunning ? "disabled" : ""}>采用方案 A</button>
              </div>
            </div>
          </article>
        </div>
        <div class="scene-review-compare__column">
          <div class="scene-review-compare__label">方案 B · 不同视觉构思</div>
          <article class="media-card media-card--cover media-card--candidate ${candidateRecommended ? "media-card--candidate-selected" : ""}">
            <img src="${API_BASE}${versionedProjectUrl(candidate)}" alt="横屏封面候选方案 B" />
            <div class="media-card__body">
              <div class="media-card__title-row">
                <strong>方案 B</strong>
                <span class="pill ${candidateRecommended ? "pill--accent" : ""}">${candidateRecommended ? "AI 推荐" : "候选"}</span>
              </div>
              <div class="media-card__meta">成图评分：${Number(candidate.score || 0)} 分 · ${escapeHtml(actualImageJudgeLabel(candidate))}</div>
              ${visualConceptHtml(candidate.concept)}
              ${imageTechnicalDetailsHtml(`
                ${imagePromptPreviewHtml(candidate.prompt || candidate.prompt_preview || "", "候选提示词仍在生成", "候选实际提示词")}
                ${imageAuditHtml(candidate.audit || {})}
              `)}
              <div class="media-card__actions">
                <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(candidate))}">打开图片</button>
                ${candidate.prompt_url ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(candidate.prompt_url)}">查看提示词</button>` : ""}
                <button class="btn btn--primary" data-select-cover-candidate="B" ${jobRunning ? "disabled" : ""}>采用方案 B</button>
              </div>
            </div>
          </article>
        </div>
      </div>
    </section>
  `;
}

function coverPreviewHtml(files) {
  const covers = coverRecords(files);
  const generated = covers.filter((item) => item.image).length;
  const coversRoot = files?.project_root ? `${files.project_root}\\covers` : "项目目录\\covers";
  return `
    <article class="file-callout">
      <div>
        <strong>封面文件</strong>
        <div class="muted" style="margin-top:6px;">横屏、图文、竖屏封面都会落到本地 covers 目录，这里直接预览并保留绝对路径。</div>
        <div class="mono-path">${escapeHtml(coversRoot)}</div>
        <div class="muted" style="margin-top:6px;">已生成 ${generated}/${covers.length}</div>
      </div>
      <div class="file-item__actions">
        <button class="btn btn--ghost" data-open-project-subpath="covers">打开封面目录</button>
      </div>
    </article>
    <div class="media-grid media-grid--covers">
      ${coverGalleryCardsHtml(files)}
    </div>
  `;
}

function artifactSummaryHtml(files) {
  const artifacts = files?.artifacts || {};
  const finalVideo = artifacts.final_video || null;
  const finalPreview = artifacts.final_preview || null;
  const releaseNote = artifacts.release_note || null;
  const releasesRoot = files?.releases_root || "";
  if (!finalVideo && !finalPreview && !releaseNote) return "";

  const primary = finalVideo || finalPreview || releaseNote;
  const primaryLabel = finalVideo ? "最终成片（mp4）" : finalPreview ? "成片预演页面" : "成片说明文件";
  const helper = finalVideo
    ? "生产完成后，最终视频会落在这个绝对路径。"
    : "当前这个项目还没有生成 mp4，先给你显示现有的成片相关文件位置。";
  const openButton = finalVideo
    ? `<button class="btn btn--ghost" data-open-project-file="releases/final-video.mp4">打开 mp4</button>`
    : finalPreview
      ? `<button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(finalPreview))}">打开预演</button>`
      : `<button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(releaseNote))}">打开说明</button>`;

  return `
    <article class="file-callout">
      <div>
        <strong>${primaryLabel}</strong>
        <div class="muted" style="margin-top:6px;">${helper}</div>
        <div class="mono-path">${escapeHtml(primary.absolute_path || "—")}</div>
        ${releasesRoot ? `<div class="muted" style="margin-top:6px;">发布目录：<span class="mono-inline">${escapeHtml(releasesRoot)}</span></div>` : ""}
      </div>
      <div class="file-item__actions">
        ${openButton}
        <button class="btn btn--ghost" data-open-project-subpath="releases">打开成片目录</button>
      </div>
    </article>
  `;
}

const inflightGetRequests = new Map();

async function api(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const canReuseInflight = method === "GET" && !options.body;
  if (canReuseInflight && inflightGetRequests.has(path)) {
    return inflightGetRequests.get(path);
  }

  const request = (async () => {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...(method === "GET" ? { cache: "no-store" } : {}),
      ...options,
      headers,
    });
  } catch (error) {
    setBackendOnline(false);
    throw new Error(`后端未连接（${API_BASE}）。请重新打开短片工坊，等待顶部显示“后端已连接”后再操作。`);
  }
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" && data?.detail ? data.detail : response.statusText;
    throw new Error(detail || "请求失败");
  }
  return data;
  })();

  if (!canReuseInflight) return request;
  inflightGetRequests.set(path, request);
  try {
    return await request;
  } finally {
    if (inflightGetRequests.get(path) === request) inflightGetRequests.delete(path);
  }
}

function isChatgptLoginError(message = "") {
  const text = String(message || "");
  return [
    "ChatGPT 登录态已失效",
    "重新登录 ChatGPT",
    "没有找到输入框",
    "输入框当前不可编辑",
  ].some((token) => text.includes(token));
}

function renderChatgptReloginButton() {
  if (!els.chatgptReloginBtn) return;
  const loginRequired = isChatgptLoginError(state.currentJob?.log || "");
  els.chatgptReloginBtn.disabled = !state.backendOnline;
  if (els.chatgptLogoutBtn) els.chatgptLogoutBtn.disabled = !state.backendOnline;
  els.chatgptReloginBtn.className = loginRequired ? "btn btn--danger" : "btn btn--ghost";
  els.chatgptReloginBtn.textContent = loginRequired ? "ChatGPT 重新登录后重试" : "重新登录 ChatGPT";
  els.chatgptReloginBtn.title = loginRequired
    ? "检测到生图登录失效，点击会打开可见浏览器登录页。"
    : "如果 ChatGPT 生图提示登录失效，可以点这里重新登录。";
}

async function relaunchChatgptLogin(statusEl = null, sourceButton = null, accountId = "") {
  if (!state.backendOnline) {
    window.alert("请先启动后端。");
    return null;
  }
  const originalLabel = sourceButton ? sourceButton.textContent : "";
  if (sourceButton) {
    sourceButton.disabled = true;
    sourceButton.textContent = "正在打开...";
  }
  if (statusEl) statusEl.textContent = "正在打开 ChatGPT 登录窗口...";
  try {
    const payload = await api("/api/settings/chatgpt-login", {
      method: "POST",
      body: JSON.stringify({ account_id: accountId || null }),
    });
    const message = [
      `已打开${payload?.account_label ? ` ${payload.account_label}` : " ChatGPT"} 登录窗口。`,
      payload?.port ? `本地端口：${payload.port}。` : "",
      payload?.profile_dir ? `登录目录：${payload.profile_dir}` : "",
      "登录完成后可关闭该窗口；后续生图会复用此账号资料并在后台运行。",
    ].filter(Boolean).join(" ");
    if (statusEl) {
      statusEl.textContent = message;
    } else {
      window.alert(message);
    }
    return payload;
  } catch (error) {
    const message = error.message || "打开 ChatGPT 登录窗口失败。";
    if (statusEl) {
      statusEl.textContent = message;
    } else {
      window.alert(message);
    }
    return null;
  } finally {
    if (sourceButton) {
      sourceButton.disabled = false;
      sourceButton.textContent = originalLabel || "重新登录 ChatGPT";
    }
  }
}

function renderChatgptAccountPool() {
  if (!els.chatgptAccountPool) return;
  const payload = state.chatgptAccounts;
  if (payload?.provider === "ant_browser") {
    const accounts = payload.accounts || [];
    els.chatgptAccountPool.innerHTML = `
      <div class="chatgpt-account-pool__head">
        <div>
          <strong>Ant Browser · ChatGPT 实例轮询</strong>
          <span class="muted">账号、指纹、Cookie 与代理均由 Ant Browser 保管，本工具只按快捷码调用实例</span>
        </div>
        <button class="btn btn--ghost" type="button" data-refresh-chatgpt-accounts>刷新实例</button>
      </div>
      <div class="chatgpt-account-pool__setup">
        <label class="chatgpt-ant-api-field">
          <span>Launch API 地址</span>
          <input type="text" value="${escapeHtml(payload.api_url || "http://127.0.0.1:19876")}" data-ant-browser-api-url />
        </label>
        <label class="chatgpt-ant-codes-field">
          <span>参与轮询的快捷打开码</span>
          <textarea rows="3" placeholder="留空则自动使用全部实例" data-ant-browser-codes>${escapeHtml((payload.configured_codes || []).join(", "))}</textarea>
        </label>
        <button class="btn btn--ghost" type="button" data-save-ant-browser>保存连接</button>
        <button class="btn btn--primary" type="button" data-test-ant-browser>保存、检测并刷新</button>
        <span class="muted" data-chatgpt-pool-status>${escapeHtml(payload.connection_error || `已发现 ${accounts.length} 个可轮询实例；生图失败时会自动切换下一个快捷码。`)}</span>
      </div>
      <div class="chatgpt-account-pool__grid">
        ${accounts.map((account) => {
          const stateLabel = account.stopping
            ? "正在停止"
            : account.busy
              ? "生图中"
              : account.cooling_down
                ? `冷却 ${account.cooldown_remaining}s`
                : !account.found
                  ? "快捷码未找到"
                  : account.page_state === "challenge"
                    ? "需要验证"
                    : account.connected
                      ? "实例运行中"
                      : "可调用";
          const tone = !account.found || account.page_state === "challenge" || account.cooling_down ? "pill--warn" : "pill--saved";
          return `
            <div class="chatgpt-account-item">
              <div>
                <strong>${escapeHtml(account.label)}</strong>
                <div class="muted">快捷码 ${escapeHtml(account.code)}${account.profile_id ? ` · ID ${escapeHtml(account.profile_id.slice(0, 8))}` : ""}</div>
              </div>
              <span class="pill ${tone}">${escapeHtml(stateLabel)}</span>
              <div class="chatgpt-account-item__actions">
                <button class="btn btn--ghost" type="button" data-login-chatgpt-account="${escapeHtml(account.id)}"
                  ${account.busy || !account.found ? "disabled" : ""}>
                  ${account.connected ? "查看实例" : "打开实例 / 登录"}
                </button>
              </div>
            </div>
          `;
        }).join("") || `<div class="empty-state"><strong>暂未读取到实例</strong><span>${escapeHtml(payload.connection_error || "请确认 Ant Browser 已启动，并在设置中启用 Launch API。")}</span></div>`}
      </div>
    `;
    const statusEl = els.chatgptAccountPool.querySelector("[data-chatgpt-pool-status]");
    els.chatgptAccountPool.querySelector("[data-refresh-chatgpt-accounts]")?.addEventListener("click", refreshChatgptAccounts);
    els.chatgptAccountPool.querySelector("[data-save-ant-browser]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const apiUrl = els.chatgptAccountPool.querySelector("[data-ant-browser-api-url]")?.value?.trim() || "http://127.0.0.1:19876";
      const codes = els.chatgptAccountPool.querySelector("[data-ant-browser-codes]")?.value?.trim() || "";
      button.disabled = true;
      try {
        await api("/api/settings/secrets", {
          method: "POST",
          body: JSON.stringify({ values: {
            CHATGPT_ACCOUNT_PROVIDER: "ant_browser",
            ANT_BROWSER_API_URL: apiUrl,
            ANT_BROWSER_LAUNCH_CODES: codes,
          } }),
        });
        if (statusEl) statusEl.textContent = "连接配置已保存，正在重新读取快捷码实例。";
        await Promise.all([refreshConfig(), refreshChatgptAccounts()]);
      } catch (error) {
        if (statusEl) statusEl.textContent = error.message || "连接配置保存失败。";
      } finally {
        button.disabled = false;
      }
    });
    els.chatgptAccountPool.querySelector("[data-test-ant-browser]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const apiUrl = els.chatgptAccountPool.querySelector("[data-ant-browser-api-url]")?.value?.trim() || "http://127.0.0.1:19876";
      const codes = els.chatgptAccountPool.querySelector("[data-ant-browser-codes]")?.value?.trim() || "";
      button.disabled = true;
      button.textContent = "正在保存...";
      if (statusEl) statusEl.textContent = "正在保存当前连接配置…";
      try {
        await api("/api/settings/secrets", {
          method: "POST",
          body: JSON.stringify({ values: {
            CHATGPT_ACCOUNT_PROVIDER: "ant_browser",
            ANT_BROWSER_API_URL: apiUrl,
            ANT_BROWSER_LAUNCH_CODES: codes,
          } }),
        });
        button.textContent = "正在检测...";
        if (statusEl) statusEl.textContent = "正在连接 Ant Browser 并读取快捷码实例…";
        const result = await api("/api/settings/ant-browser/test", { method: "POST" });
        await Promise.all([refreshConfig(), refreshChatgptAccounts()]);
        const latestStatusEl = els.chatgptAccountPool.querySelector("[data-chatgpt-pool-status]");
        const accountCount = state.chatgptAccounts?.accounts?.length || 0;
        const refreshedAt = new Date().toLocaleTimeString("zh-CN", { hour12: false });
        if (latestStatusEl) {
          latestStatusEl.textContent = `${result.message || "Ant Browser 已连接。"} 当前参与轮询 ${accountCount} 个。刷新时间 ${refreshedAt}`;
        }
      } catch (error) {
        const latestStatusEl = els.chatgptAccountPool.querySelector("[data-chatgpt-pool-status]");
        if (latestStatusEl) latestStatusEl.textContent = error.message || "Ant Browser 连接检测失败。";
      } finally {
        const latestButton = els.chatgptAccountPool.querySelector("[data-test-ant-browser]");
        if (latestButton) {
          latestButton.disabled = false;
          latestButton.textContent = "保存、检测并刷新";
        }
      }
    });
    els.chatgptAccountPool.querySelectorAll("[data-login-chatgpt-account]").forEach((button) => {
      button.addEventListener("click", async () => {
        await relaunchChatgptLogin(statusEl, button, button.dataset.loginChatgptAccount || "");
        await refreshChatgptAccounts();
      });
    });
    return;
  }
  if (!payload?.accounts?.length) {
    els.chatgptAccountPool.innerHTML = "";
    return;
  }
  els.chatgptAccountPool.innerHTML = `
    <div class="chatgpt-account-pool__head">
      <div>
        <strong>ChatGPT 多账号轮询登录</strong>
        <span class="muted">每个账号独立登录 · 端口从 ${escapeHtml(payload.base_port)} 开始</span>
      </div>
      <button class="btn btn--ghost" type="button" data-refresh-chatgpt-accounts>刷新状态</button>
    </div>
    <div class="chatgpt-account-pool__setup">
      <label>
        <span>轮询账号数量</span>
        <input type="number" min="1" max="12" step="1" value="${escapeHtml(payload.count || 1)}" data-chatgpt-account-count />
      </label>
      <button class="btn btn--ghost" type="button" data-apply-chatgpt-account-count>保存账号数量</button>
      <button class="btn btn--primary" type="button" data-login-all-chatgpt-accounts>一键打开全部登录窗口</button>
      <span class="muted" data-chatgpt-pool-status>先保存账号数量，再分别登录弹出的独立窗口；登录状态会自动保存。</span>
    </div>
    <div class="chatgpt-account-pool__grid">
      ${payload.accounts.map((account) => {
        const stateLabel = account.stopping
          ? "正在停止"
          : account.busy
          ? "生图中"
          : account.cooling_down
            ? `冷却 ${account.cooldown_remaining}s`
            : account.page_state === "challenge"
              ? "需要验证"
            : account.connected
              ? "浏览器运行中"
              : account.saved_session
                ? "登录资料已保存"
                : "未登录";
        const tone = account.page_state === "challenge"
          ? "pill--warn"
          : account.connected && !account.cooling_down
          ? ""
          : account.saved_session && !account.cooling_down
            ? "pill--saved"
            : "pill--warn";
        return `
          <div class="chatgpt-account-item">
            <div>
              <strong>${escapeHtml(account.label)}</strong>
              <div class="muted">127.0.0.1:${escapeHtml(account.port)}</div>
            </div>
            <span class="pill ${tone}">${escapeHtml(stateLabel)}</span>
            <div class="chatgpt-account-item__actions">
              <button class="btn btn--ghost" type="button" data-login-chatgpt-account="${escapeHtml(account.id)}"
                ${account.busy ? "disabled" : ""}>
                ${account.stopping ? "正在回收账号" : account.busy ? "生图结束后可打开" : account.page_state === "challenge" ? "完成验证" : account.connected ? "查看账号" : account.saved_session ? "打开已保存账号" : "登录此账号"}
              </button>
              <button class="btn btn--danger" type="button" data-delete-chatgpt-account="${escapeHtml(account.id)}"
                data-chatgpt-account-label="${escapeHtml(account.label)}">
                删除账号
              </button>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
  els.chatgptAccountPool.querySelector("[data-refresh-chatgpt-accounts]")?.addEventListener("click", refreshChatgptAccounts);
  els.chatgptAccountPool.querySelector("[data-apply-chatgpt-account-count]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const input = els.chatgptAccountPool.querySelector("[data-chatgpt-account-count]");
    const statusEl = els.chatgptAccountPool.querySelector("[data-chatgpt-pool-status]");
    const count = Math.max(1, Math.min(12, Number.parseInt(input?.value || "1", 10) || 1));
    button.disabled = true;
    button.textContent = "正在应用...";
    try {
      await api("/api/settings/secrets", {
        method: "POST",
        body: JSON.stringify({ values: { CHATGPT_IMAGE_ACCOUNT_COUNT: String(count) } }),
      });
      if (statusEl) statusEl.textContent = `已建立 ${count} 个独立账号槽位，请继续登录每个账号。`;
      await Promise.all([refreshConfig(), refreshChatgptAccounts()]);
    } catch (error) {
      if (statusEl) statusEl.textContent = error.message || "账号数量保存失败。";
    } finally {
      button.disabled = false;
      button.textContent = "保存账号数量";
    }
  });
  els.chatgptAccountPool.querySelector("[data-login-all-chatgpt-accounts]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const statusEl = els.chatgptAccountPool.querySelector("[data-chatgpt-pool-status]");
    const accounts = state.chatgptAccounts?.accounts || [];
    const originalLabel = button.textContent;
    button.disabled = true;
    try {
      for (let index = 0; index < accounts.length; index += 1) {
        const account = accounts[index];
        button.textContent = `正在打开 ${index + 1}/${accounts.length}`;
        if (statusEl) statusEl.textContent = `正在打开 ${account.label}（127.0.0.1:${account.port}）...`;
        const opened = await relaunchChatgptLogin(statusEl, null, account.id);
        if (!opened) break;
      }
      if (statusEl) statusEl.textContent = "账号窗口已依次打开；请确认每个窗口登录的是不同 ChatGPT 账号。";
      await refreshChatgptAccounts();
    } finally {
      button.disabled = false;
      button.textContent = originalLabel;
    }
  });
  els.chatgptAccountPool.querySelectorAll("[data-login-chatgpt-account]").forEach((button) => {
    button.addEventListener("click", async () => {
      const statusEl = els.chatgptAccountPool.querySelector("[data-chatgpt-pool-status]");
      await relaunchChatgptLogin(statusEl, button, button.dataset.loginChatgptAccount || "");
      await refreshChatgptAccounts();
    });
  });
  els.chatgptAccountPool.querySelectorAll("[data-delete-chatgpt-account]").forEach((button) => {
    button.addEventListener("click", async () => {
      const accountId = button.dataset.deleteChatgptAccount || "";
      const accountLabel = button.dataset.chatgptAccountLabel || "这个账号";
      if (!window.confirm(`确认删除 ${accountLabel} 吗？后面的轮询账号会自动前移，已保存登录不会丢失。`)) return;
      const originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = "正在删除...";
      try {
        const payload = await api(`/api/settings/chatgpt-accounts/${encodeURIComponent(accountId)}`, {
          method: "DELETE",
        });
        window.alert(payload.message || `${accountLabel} 已删除。`);
        await Promise.all([refreshConfig(), refreshChatgptAccounts()]);
      } catch (error) {
        window.alert(error.message || "删除账号失败，请关闭该账号及后续账号的 ChatGPT/Chrome 窗口后重试。");
      } finally {
        button.disabled = false;
        button.textContent = originalLabel || "删除账号";
      }
    });
  });
}

async function logoutChatgptLogin(sourceButton = null) {
  if (!state.backendOnline) {
    window.alert("请先启动后端。");
    return null;
  }
  if (!window.confirm("确认退出 ChatGPT 自动化登录吗？这会清空本工具保存的 ChatGPT 浏览器登录状态，下次生图需要重新登录。")) {
    return null;
  }
  const originalLabel = sourceButton ? sourceButton.textContent : "";
  if (sourceButton) {
    sourceButton.disabled = true;
    sourceButton.textContent = "正在退出...";
  }
  try {
    const payload = await api("/api/settings/chatgpt-logout", { method: "POST" });
    window.alert(payload.message || "ChatGPT 登录状态已清空。");
    return payload;
  } catch (error) {
    window.alert(error.message || "退出 ChatGPT 登录失败，请先关闭弹出的 ChatGPT/Chrome 窗口后重试。");
    return null;
  } finally {
    if (sourceButton) {
      sourceButton.disabled = false;
      sourceButton.textContent = originalLabel || "退出 ChatGPT";
    }
  }
}

async function withBusyButton(button, busyText, task) {
  if (!button) {
    return await task();
  }
  if (button.getAttribute("aria-busy") === "true") return;
  const originalText = button.textContent;
  const originalDisabled = button.disabled;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = busyText;
  try {
    return await task();
  } finally {
    button.disabled = originalDisabled;
    button.removeAttribute("aria-busy");
    button.textContent = originalText || "";
  }
}

function markReleaseAutomationPending(action) {
  const actionLabels = {
    prepare: "准备环境",
    login: "登录账号",
    check: "检测账号",
    publish: "发布视频",
    cancel: "取消任务",
  };
  const label = actionLabels[action] || action;
  const platform = els.releaseAutoPlatform?.selectedOptions?.[0]?.textContent?.trim()
    || els.releaseAutoPlatform?.value?.trim()
    || "-";
  const accountName = els.releaseAutoAccount?.value?.trim() || "default";
  const stamp = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const existingLog = String(els.releaseAutomationLog?.textContent || "").trim();
  const nextLogLine = `[release] ${stamp} 正在发起${label}...`;

  if (els.releaseTaskPill) {
    els.releaseTaskPill.textContent = "starting";
    els.releaseTaskPill.className = "pill";
  }
  if (els.releaseTaskMeta) {
    els.releaseTaskMeta.innerHTML = `
      <div>动作: ${escapeHtml(action)} · 平台: ${escapeHtml(platform)} · 账号: ${escapeHtml(accountName)}</div>
      <div>状态: starting · 运行中: 是</div>
      <div class="muted">请求已经发送到后端，稍后会在这里刷新二维码、登录状态和运行日志。</div>
    `;
  }
  if (els.releaseAutomationLog) {
    els.releaseAutomationLog.textContent = existingLog ? `${existingLog}\n${nextLogLine}` : nextLogLine;
  }
}

function bindReleaseAutomationAction(buttonId, action, busyText, fallbackError) {
  const button = document.getElementById(buttonId);
  button?.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    await withBusyButton(button, busyText, async () => {
      try {
        await runReleaseAutomation(action);
      } catch (error) {
        window.alert(error.message || fallbackError);
      }
    });
  });
}

function ensureProject() {
  if (!state.currentProject) {
    window.alert("请先在左侧选择一个主题项目。");
    return null;
  }
  return state.currentProject;
}

async function resolveStageGateProject(target) {
  const current = ensureProject();
  if (!current) return null;
  const renderedProjectId = Number(target?.dataset?.stageGateProjectId || 0);
  if (!renderedProjectId || renderedProjectId !== Number(current.id)) {
    await refreshStageGates();
    window.alert("项目已切换，闸门状态已刷新，请重新点击。");
    return null;
  }
  const projects = await api("/api/projects");
  state.projects = Array.isArray(projects) ? projects : [];
  const latest = state.projects.find((item) => Number(item.id) === renderedProjectId);
  if (!latest) {
    clearCurrentWorkspace();
    await refreshProjects();
    window.alert("这个项目已被删除，项目列表已更新。");
    return null;
  }
  state.currentProject = { ...current, ...latest };
  return state.currentProject;
}

function hasContentDraft() {
  const bundleContent = state.currentContent?.content || "";
  const editorContent = els.contentInput?.value || "";
  return Boolean(bundleContent.trim() || editorContent.trim());
}

function hasFinalVideoArtifact() {
  return Boolean(state.currentFiles?.artifacts?.final_video);
}

function updateWorkflowButtons() {
  if (els.runJobBtn) {
    const running = Boolean(state.currentJob?.running);
    const selectedStepCount = stepValues().length;
    const hasProject = Boolean(state.currentProject);
    if (els.selectedStepSummary) {
      els.selectedStepSummary.textContent = `已选择 ${selectedStepCount} 个步骤`;
    }
    els.runJobBtn.disabled = !hasProject || running || selectedStepCount === 0;
    els.runJobBtn.textContent = running
      ? "正在执行…"
      : selectedStepCount > 0
        ? `开始执行 ${selectedStepCount} 个步骤`
        : "请先选择步骤";
    els.runJobBtn.title = running
      ? `当前任务正在执行 ${state.currentJob?.current_step || "生产步骤"}，完成或停止后才能再次启动。`
      : !hasProject
        ? "先选择一个主题项目"
        : selectedStepCount > 0
          ? `启动当前勾选的 ${selectedStepCount} 个生产步骤`
          : "请至少勾选一个生产步骤";
  }
  if (els.sampleImageBtn) {
    const running = Boolean(state.currentJob?.running);
    els.sampleImageBtn.disabled = !state.currentProject || !hasContentDraft() || running;
    els.sampleImageBtn.textContent = running ? "任务进行中" : "先生成质量样片";
  }
  if (els.nextToProduceBtn) {
    const ready = Boolean(state.currentProject && hasContentDraft());
    els.nextToProduceBtn.disabled = !ready;
    els.nextToProduceBtn.title = ready ? "跳到生产页继续下一步" : "先生成或保存 content.md";
  }
  if (els.nextToFilesBtn) {
    const ready = Boolean(state.currentProject && state.currentJob?.status === "succeeded" && hasFinalVideoArtifact());
    els.nextToFilesBtn.disabled = !ready;
    els.nextToFilesBtn.title = ready ? "跳到成片页查看输出文件" : "先跑完生产并生成 mp4";
  }
  if (els.nextToReleasesBtn) {
    const ready = Boolean(state.currentProject);
    els.nextToReleasesBtn.disabled = !ready;
    els.nextToReleasesBtn.title = ready ? "\u6253\u5f00\u53d1\u5e03\u4e2d\u5fc3\uff0c\u53ef\u63d0\u524d\u9884\u7ea6\u5e76\u7b49\u5f85\u6210\u7247" : "\u8bf7\u5148\u9009\u62e9\u9879\u76ee";
  }
  if (els.nextToDataBtn) {
    els.nextToDataBtn.disabled = !state.currentProject;
    els.nextToDataBtn.title = state.currentProject ? "打开运营数据看板" : "请先选择项目";
  }
  if (els.videoSelfCheckBtn) {
    const ready = Boolean(state.currentProject && hasFinalVideoArtifact());
    els.videoSelfCheckBtn.disabled = !ready;
    els.videoSelfCheckBtn.title = ready ? "抽帧检查黑屏、字幕覆盖和时长" : "先生成最终视频";
  }
}

function setBackendOnline(online) {
  state.backendOnline = online;
  els.backendBanner.classList.toggle("hidden", online);
  els.backendStatus.textContent = online ? "后端已连接" : "后端未连接";
  els.backendStatus.className = online ? "pill pill--success" : "pill pill--warn";
  renderChatgptReloginButton();
}

function showModal(title, html, afterRender) {
  els.modalTitle.textContent = title;
  els.modalBody.innerHTML = html;
  els.modal.classList.remove("hidden");
  if (afterRender) afterRender(els.modalBody);
}

function showMotionSamplesModal(manifest) {
  const variants = Array.isArray(manifest?.variants) ? manifest.variants : [];
  const selected = String(manifest?.selected || "stable");
  const recommended = String(manifest?.recommended || "stable");
  const version = encodeURIComponent(String(manifest?.generated_at || Date.now()));
  const cards = variants.map((variant) => {
    const key = String(variant.key || "");
    const available = variant.available !== false;
    const isSelected = key === selected;
    const isRecommended = key === recommended;
    const preview = available && variant.url
      ? `<video controls preload="metadata" style="width:100%;aspect-ratio:16/9;background:#101820;border-radius:12px;" src="${escapeHtml(`${variant.url}?v=${version}`)}"></video>`
      : `<div class="media-card__preview" style="aspect-ratio:16/9;display:grid;place-items:center;">当前项目尚无该类镜头</div>`;
    return `
      <article class="card" style="padding:14px;min-width:0;">
        ${preview}
        <div class="section-head" style="margin-top:10px;">
          <div>
            <strong>${escapeHtml(variant.label || key)}</strong>
            <div class="muted">${escapeHtml(variant.description || "")}</div>
          </div>
          <div class="stack stack--sm" style="align-items:flex-end;">
            ${isRecommended ? `<span class="pill pill--success">系统推荐</span>` : ""}
            <span class="pill">${escapeHtml(String(variant.score || 0))} 分</span>
          </div>
        </div>
        <button
          class="btn ${isSelected ? "btn--ghost" : "btn--primary"}"
          type="button"
          data-select-motion-profile="${escapeHtml(key)}"
          ${available && !isSelected ? "" : "disabled"}
        >${isSelected ? "当前采用" : (available ? "整期采用此方案" : "尚未配置")}</button>
      </article>
    `;
  }).join("");
  showModal(
    "动态样片对比",
    `
      <div class="stack">
        <div class="notice">
          样片截取第 ${escapeHtml(String(manifest?.sample_scene_index || 1))} 镜，
          时长 ${escapeHtml(String(Math.round(Number(manifest?.sample_duration || 0))))} 秒。
          这里只比较运动方式，不重新生成图片。
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;">
          ${cards || `<div class="muted">暂无样片，请重新生成。</div>`}
        </div>
      </div>
    `,
    (body) => {
      body.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-select-motion-profile]");
        if (!button) return;
        const project = ensureProject();
        if (!project) return;
        const profile = button.dataset.selectMotionProfile;
        await withBusyButton(button, "正在应用...", async () => {
          await api(`/api/projects/${project.id}/motion-profile`, {
            method: "POST",
            body: JSON.stringify({ selected: profile }),
          });
          const refreshed = await api(`/api/projects/${project.id}/motion-samples`);
          showMotionSamplesModal(refreshed);
        });
      });
    },
  );
}

function closeModal() {
  resetDoubaoVoicePreview();
  els.modal.classList.add("hidden");
  els.modalBody.innerHTML = "";
  state.autoVideoModalVisible = false;
}

function setActiveTab(tab) {
  if (tab === "config" && !state.advancedMode) {
    setAdvancedMode(true);
  }
  state.activeTab = tab;
  els.studioShell?.classList.toggle("is-produce-tab", tab === "produce");
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `tab-${tab}` || panel.id === "tab-content" && tab === "content");
  });
  els.projectStatusStrip?.classList.toggle("hidden", tab === "produce");
  if (tab === "releases" && state.currentProject) {
    refreshReleaseAutomation(true).catch((error) => console.warn(error));
  }
  if (tab === "analytics" && state.currentProject) {
    refreshReleases({ autoSync: true }).catch((error) => console.warn(error));
  }
  if (tab === "config") {
    refreshPackaging().catch((error) => console.warn(error));
  }
}

function setAdvancedMode(enabled, { persist = true } = {}) {
  state.advancedMode = Boolean(enabled);
  els.studioShell?.classList.toggle("is-advanced-mode", state.advancedMode);
  if (els.workspaceModeToggle) {
    els.workspaceModeToggle.textContent = state.advancedMode ? "返回精简模式" : "高级设置";
    els.workspaceModeToggle.setAttribute("aria-pressed", String(state.advancedMode));
  }
  if (persist) {
    try {
      window.localStorage.setItem(UI_MODE_KEY, state.advancedMode ? "advanced" : "focus");
    } catch (_error) {
      // The selected mode still applies for this session.
    }
  }
  if (!state.advancedMode && state.productionAssetTab === "diagnostics") {
    setProductionAssetTab("scenes");
  }
  if (!state.advancedMode && state.activeTab === "config") {
    setActiveTab("content");
  }
}

function doubaoVoiceLabel(voiceType) {
  if (!voiceType) return "未选择";
  const voice = (state.ttsPreviews?.voices || []).find((item) => item.voice_type === voiceType);
  return voice?.label || voiceType;
}

async function openTemplateVoiceSettings(key) {
  const template = await api(`/api/templates/${encodeURIComponent(key)}`);
  const projectCount = templateProjectCount(key);
  const appliesToCurrentProject = Boolean(state.currentProject && state.currentProject.template === key);
  const initialVoiceMode = template.voice_mode || (key.includes("双人") ? "dual" : "auto");
  const initialRandomOrder = template.tts_random_order === true || String(template.tts_random_order).toLowerCase() === "true";
  showModal(
    `试听 / 选择声音 · ${key}`,
    `
      <div class="voice-picker-intro">
        <div>
          <strong>豆包声音人物</strong>
          <div class="muted">${escapeHtml(String(state.ttsPreviews?.voices?.length || 0))} 个音色可选。先试听，满意后保存；下一次生成配音时生效。</div>
        </div>
        <button id="modal-voice-sync" class="btn btn--ghost" type="button">同步音色</button>
      </div>
      <div class="voice-picker-scope">
        <strong>频道专用设置</strong>
        <span>优先于配置页的全局默认。${projectCount ? `该频道已有 ${projectCount} 个主题；旧素材默认保留，需要时可立即把新声音应用到当前主题。` : "保存后用于这个频道新生成的配音。"}</span>
        <button id="voice-picker-open-config" class="btn btn--ghost" type="button">查看全局配置</button>
      </div>
      <section class="template-production-settings template-production-settings--voice-only">
        <label><span>讲述模式</span><select id="voice-picker-mode">
          <option value="auto" ${initialVoiceMode === "auto" ? "selected" : ""}>自动判断（按真实角色）</option>
          <option value="single" ${initialVoiceMode === "single" ? "selected" : ""}>固定单人讲述</option>
          <option value="dual" ${initialVoiceMode === "dual" ? "selected" : ""}>固定双人讲述</option>
        </select></label>
        <label><span id="voice-picker-speaker-1-label">${initialVoiceMode === "dual" ? "角色 A 音色" : "讲述人音色"}</span><div class="voice-picker-control">
          <select id="voice-picker-speaker-1">${doubaoVoiceOptionsHtml(template.tts_speaker_1 || "zh_female_cancan_uranus_bigtts")}</select>
          <button class="btn btn--ghost" type="button" data-preview-voice-select="voice-picker-speaker-1" data-preview-rate-input="voice-picker-rate">按当前语速试听</button>
        </div></label>
        <label id="voice-picker-speaker-2-row"><span>角色 B 音色</span><div class="voice-picker-control">
          <select id="voice-picker-speaker-2">${doubaoVoiceOptionsHtml(template.tts_speaker_2 || "zh_female_mizaitongxue_v2_saturn_bigtts")}</select>
          <button class="btn btn--ghost" type="button" data-preview-voice-select="voice-picker-speaker-2" data-preview-rate-input="voice-picker-rate">按当前语速试听</button>
        </div></label>
        <label id="voice-picker-random-row"><span>角色绑定</span><select id="voice-picker-random">
          <option value="false" ${initialRandomOrder ? "" : "selected"}>固定 A / B 音色（推荐）</option>
          <option value="true" ${initialRandomOrder ? "selected" : ""}>每期随机交换 A / B</option>
        </select></label>
        <label><span>语速 <strong id="voice-picker-rate-value">${escapeHtml(String(template.tts_speech_rate || 1))}x</strong></span><input id="voice-picker-rate" type="range" min="0.8" max="1.2" step="0.05" value="${escapeHtml(String(template.tts_speech_rate || 1))}" /></label>
        ${appliesToCurrentProject ? `
          <div class="voice-picker-impact">
            <div><span>预计成片时长</span><strong id="voice-picker-duration">正在估算…</strong></div>
            <div><span>应用当前主题时</span><strong>重做 配音 → 字幕 → 成片</strong></div>
            <small>保留场景图和封面；字幕会按新语速重新对齐。</small>
          </div>
        ` : ""}
        <div class="toolbar voice-picker-actions">
          <button id="voice-picker-save-default" class="btn btn--ghost">仅保存为频道默认</button>
          ${appliesToCurrentProject ? `<button id="voice-picker-apply-current" class="btn btn--primary">应用当前主题并重做</button>` : ""}
        </div>
      </section>
    `,
    (body) => {
      const modeInput = body.querySelector("#voice-picker-mode");
      const speaker1Input = body.querySelector("#voice-picker-speaker-1");
      const speaker2Input = body.querySelector("#voice-picker-speaker-2");
      const speaker2Row = body.querySelector("#voice-picker-speaker-2-row");
      const randomRow = body.querySelector("#voice-picker-random-row");
      const speaker1Label = body.querySelector("#voice-picker-speaker-1-label");
      const rateInput = body.querySelector("#voice-picker-rate");
      const rateValue = body.querySelector("#voice-picker-rate-value");
      const durationValue = body.querySelector("#voice-picker-duration");

      function estimatedDurationSeconds() {
        const selectedRate = Math.max(0.8, Math.min(Number(rateInput.value) || 1, 1.2));
        const status = state.voiceStatus || {};
        const currentDuration = Number(status.audio_duration_seconds || 0);
        const generatedRate = Number(status.generated_speech_rate || template.tts_speech_rate || 1);
        if (currentDuration > 0) return currentDuration * generatedRate / selectedRate;
        const characterCount = Number(status.spoken_character_count || 0);
        return characterCount > 0 ? characterCount / (4.2 * selectedRate) : 0;
      }

      function updateDuration() {
        if (!durationValue) return;
        const seconds = estimatedDurationSeconds();
        durationValue.textContent = seconds > 0 ? `约 ${formatTaskElapsed(Math.round(seconds))}` : "生成配音后确认";
      }

      function updateMode() {
        const dual = modeInput.value === "dual";
        const supportsSecondVoice = modeInput.value !== "single";
        speaker2Row.classList.toggle("hidden", !supportsSecondVoice);
        randomRow.classList.toggle("hidden", !supportsSecondVoice);
        speaker1Label.textContent = supportsSecondVoice ? "角色 A 音色" : "讲述人音色";
      }

      modeInput.addEventListener("change", updateMode);
      rateInput.addEventListener("input", () => {
        rateValue.textContent = `${Number(rateInput.value).toFixed(2)}x`;
        if (state.audioPreview) {
          state.audioPreview.preservesPitch = true;
          state.audioPreview.playbackRate = Number(rateInput.value);
        }
        updateDuration();
      });
      updateMode();
      updateDuration();

      body.querySelector("#voice-picker-open-config").addEventListener("click", () => {
        closeModal();
        setActiveTab("config");
      });

      body.querySelector("#modal-voice-sync").addEventListener("click", async (event) => {
        await withBusyButton(event.currentTarget, "同步中...", async () => {
          const selected1 = speaker1Input.value;
          const selected2 = speaker2Input.value;
          await refreshTtsPreviews();
          speaker1Input.innerHTML = doubaoVoiceOptionsHtml(selected1);
          speaker2Input.innerHTML = doubaoVoiceOptionsHtml(selected2);
          window.alert(`已同步 ${state.ttsPreviews?.voices?.length || 0} 个豆包音色。`);
        });
      });

      async function saveVoiceSettings(event, rebuildCurrent) {
        await withBusyButton(event.currentTarget, rebuildCurrent ? "正在启动重做..." : "保存中...", async () => {
          if (modeInput.value === "dual" && speaker1Input.value === speaker2Input.value) {
            window.alert("角色 A 和角色 B 不能使用同一个声音，请更换其中一个。");
            return;
          }
          const result = await api(`/api/templates/${encodeURIComponent(key)}/voice-settings`, {
            method: "PUT",
            body: JSON.stringify({
              voice_mode: modeInput.value,
              tts_speaker_1: speaker1Input.value,
              tts_speaker_2: speaker2Input.value,
              tts_random_order: body.querySelector("#voice-picker-random").value === "true",
              tts_speech_rate: Number(rateInput.value),
            }),
          });
          if (rebuildCurrent && state.currentProject?.template === key) {
            await api(`/api/projects/${state.currentProject.id}/jobs`, {
              method: "POST",
              body: JSON.stringify({ steps: ["audio", "subtitles", "video"], allow_incomplete_video: false }),
            });
          }
          await Promise.all([
            refreshTemplates(),
            refreshProjects(),
            state.currentProject ? refreshProductionManifest() : Promise.resolve(),
            state.currentProject ? refreshVoiceStatus() : Promise.resolve(),
          ]);
          closeModal();
          if (rebuildCurrent && state.currentProject?.template === key) {
            setActiveTab("produce");
            await refreshLatestJob();
            window.alert("声音设置已保存，当前主题已开始重新配音。场景图和封面不会重做。");
            return;
          }
          const update = result.voice_update || {};
          if (update.changed) {
            window.alert("声音设置已保存。已生成的旧素材保持不变，下一次重配音或新主题会使用新声音。");
          }
        });
      }

      body.querySelector("#voice-picker-save-default").addEventListener("click", (event) => {
        saveVoiceSettings(event, false).catch((error) => window.alert(error.message || "保存声音设置失败。"));
      });
      body.querySelector("#voice-picker-apply-current")?.addEventListener("click", (event) => {
        saveVoiceSettings(event, true).catch((error) => window.alert(error.message || "应用声音设置失败。"));
      });
    }
  );
}

function renderTemplates() {
  if (!state.templatesLoaded) {
    const message = state.templatesError
      ? `频道加载失败：${escapeHtml(state.templatesError)}`
      : "频道加载中...";
    els.templateList.innerHTML = `<div class="muted">${message}</div>`;
    return;
  }
  const orphans = orphanTemplates();
  if (!state.templates.length && !orphans.length) {
    els.templateList.innerHTML = `<div class="muted">暂无模板</div>`;
    return;
  }
  const templateCards = state.templates
    .map((template) => {
      const active = selectedTemplateKey() === template.key ? "is-active" : "";
      const locked = isTemplateLocked(template);
      const projectCount = templateProjectCount(template.key);
      const lockedBadge = locked ? ` <span class="pill">内置</span>` : "";
      const projectHint = projectCount ? ` · ${projectCount} 个主题` : "";
      const editLabel = locked ? "查看" : "查看 / 编辑";
      const voiceMode = template.voice_mode || (template.key.includes("双人") ? "dual" : "single");
      const voiceSummary = voiceMode === "dual"
        ? `${doubaoVoiceLabel(template.tts_speaker_1)} + ${doubaoVoiceLabel(template.tts_speaker_2)}`
        : doubaoVoiceLabel(template.tts_speaker_1);
      const voiceButton = template.mode === "article"
        ? ""
        : `<button class="btn btn--ghost" data-template-voice="${escapeHtml(template.key)}">试听 / 选声音</button>`;
      const autoVideoClass = voiceButton ? " template-action--wide" : "";
      const deleteButton = locked
        ? ""
        : `<button class="btn btn--danger" data-delete-template="${escapeHtml(template.key)}">删除频道</button>`;
      return `
        <article class="template-item ${active}">
          <div class="item-heading">
            <h4>${escapeHtml(template.key)}</h4>
            ${lockedBadge}
          </div>
          <p>${escapeHtml(template.mode === "article" ? "图文工作流" : `豆包配音 · ${voiceSummary}`)} · 封面风格 ${escapeHtml(template.cover_style || "default")}${escapeHtml(projectHint)}</p>
          <div class="template-item__actions">
            <button class="btn btn--ghost" data-select-template="${escapeHtml(template.key)}">查看主题</button>
            ${voiceButton}
            <button class="btn btn--primary${autoVideoClass}" data-auto-video-template="${escapeHtml(template.key)}">自动挖题成片</button>
          </div>
          <details class="item-more">
            <summary>更多操作</summary>
            <div class="item-more__actions">
              <button class="btn btn--ghost" data-edit-template="${escapeHtml(template.key)}">${editLabel}</button>
              <button class="btn btn--ghost" data-open-template="${escapeHtml(template.key)}">打开目录</button>
              <button class="btn btn--ghost" data-open-template-products="${escapeHtml(template.key)}">打开产物</button>
              ${deleteButton}
            </div>
          </details>
        </article>
      `;
    })
    .join("");
  const orphanCards = orphans
    .map(
      (template) => `
        <article class="template-item">
          <h4>${escapeHtml(template.key)} <span class="pill pill--warn">orphan</span></h4>
          <p>模板目录已经不存在，但还有 ${escapeHtml(String(template.count))} 个历史项目在引用。最近项目：${escapeHtml(template.latestTopic || "未命名")}</p>
          <div class="template-item__actions">
            <button class="btn btn--primary" data-select-template="${escapeHtml(template.key)}">主题</button>
            <button class="btn btn--ghost" data-open-template-products="${escapeHtml(template.key)}">打开产物</button>
            <button class="btn btn--ghost" data-delete-orphan-template="${escapeHtml(template.key)}">清理 orphan</button>
          </div>
        </article>
      `
    )
    .join("");
  els.templateList.innerHTML = templateCards + orphanCards;
}

function renderProjects() {
  const key = selectedTemplateKey();
  const projects = projectsForSelectedTemplate();
  if (els.projectListScope) {
    els.projectListScope.textContent = key
      ? `${key} · ${projects.length} 个主题`
      : `全部频道 · ${(state.projects || []).length} 个主题`;
  }
  if (!state.projects.length) {
    els.projectList.innerHTML = `<div class="muted">还没有主题项目，先点上面的“新建主题”。</div>`;
    return;
  }
  if (!projects.length) {
    els.projectList.innerHTML = `<div class="muted">这个频道还没有主题项目，点“新建主题”会默认创建到当前频道。</div>`;
    return;
  }
  els.projectList.innerHTML = projects
    .map((project) => {
      const active = state.currentProject?.id === project.id ? "is-active" : "";
      const rawStatus = String(project.last_job_status || "idle").toLowerCase();
      const statusClass = ["succeeded", "running", "failed", "cancelled", "interrupted"].includes(rawStatus) ? rawStatus : "idle";
      const statusLabel = {
        succeeded: "已完成",
        running: "生产中",
        failed: "需处理",
        cancelled: "已停止",
        interrupted: "可续跑",
        idle: "未开始",
      }[statusClass];
      return `
        <article class="project-item ${active}">
          <div class="item-heading">
            <h4>${escapeHtml(project.topic_name)}</h4>
            <span class="project-state project-state--${statusClass}">${statusLabel}</span>
          </div>
          <p>项目 #${escapeHtml(String(project.id))} · ${escapeHtml(project.template)} · ${escapeHtml(project.template_mode === "article" ? "图文" : "视频")}${project.content_type === "product" ? " · 商品" : ""}</p>
          <div class="project-item__actions">
            <button class="btn btn--ghost" data-open-project="${project.id}">打开项目</button>
            <button class="btn btn--danger" data-delete-project="${project.id}">删除</button>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderSummary(summary, factRegistry = null) {
  if (!summary || !summary.video_title) {
    els.summaryCards.innerHTML = `<div class="muted">先生成 content.md，这里会显示标题、时长、分镜数、评分等摘要。</div>`;
    return;
  }
  const factCounts = factRegistry?.counts || {};
  const verifiedFacts = Number(factCounts.verified || 0);
  const unsupportedFacts = Number(factCounts.unsupported || 0);
  const factStatus = unsupportedFacts > 0
    ? `${unsupportedFacts} 项待处理`
    : verifiedFacts > 0
      ? `${verifiedFacts} 项已核验`
      : "无精确数字";
  const cards = [
    ["主标题", summary.video_title, ""],
    ["发布标题", summary.publish_title, ""],
    ["预计时长", summary.duration, ""],
    ["场景图数量", summary.scene_count, ""],
    ["台词条数", summary.dialogue_count, ""],
    ["选题评分", summary.topic_score, ""],
    ["事实清单", factStatus, unsupportedFacts > 0 ? "summary-card--risk" : ""],
  ];
  els.summaryCards.innerHTML = cards
    .map(
      ([label, value, tone], index) => `
        <div class="summary-card ${index < 2 ? "summary-card--wide" : ""} ${tone}">
          <strong>${escapeHtml(label)}</strong>
          <span>${escapeHtml(String(value ?? "—"))}</span>
        </div>
      `
    )
    .join("");
}

function renderReferences(references = []) {
  if (!references.length) {
    els.referenceList.innerHTML = `<div class="muted">暂无参考资料</div>`;
    return;
  }
  els.referenceList.innerHTML = references
    .map(
      (ref) => `
        <article class="card card--inner">
          <h4>${escapeHtml(ref.title)}</h4>
          <p>${escapeHtml(ref.snippet || "")}</p>
          <div class="toolbar">
            <span class="pill">${escapeHtml(ref.source || "Web")}</span>
            <button class="btn btn--ghost" data-preview-reference="${Number(ref.index ?? 0)}">预览资料</button>
            <a class="link-btn" href="${escapeHtml(ref.url)}" target="_blank" rel="noreferrer">打开来源</a>
          </div>
        </article>
      `
    )
    .join("");
}

function renderSourceWorkbench() {
  const items = Array.isArray(state.sourceMaterials) ? state.sourceMaterials : [];
  const candidates = Array.isArray(state.sourceCandidates?.results) ? state.sourceCandidates.results : [];
  const mustUseCount = items.filter((item) => item.must_use).length;
  if (els.sourceCountPill) {
    els.sourceCountPill.textContent = `${items.length} 条采用 · ${mustUseCount} 条必用`;
  }
  if (els.motionSampleBtn) {
    const running = Boolean(state.currentJob?.running);
    els.motionSampleBtn.disabled = !state.currentProject || !hasContentDraft() || running;
    els.motionSampleBtn.textContent = running ? "任务进行中" : "对比动态样片";
  }
  if (els.sourceMaterialList) {
    els.sourceMaterialList.innerHTML = items.length
      ? items.map((item) => {
          const isImage = item.type === "image";
          const imageUrl = isImage && item.relative_path && state.currentProject
            ? `${API_BASE}/data/projects/${state.currentProject.id}/${String(item.relative_path).split("/").map(encodeURIComponent).join("/")}`
            : "";
          return `
            <article class="source-card ${item.must_use ? "source-card--must" : ""}">
              ${imageUrl ? `<img src="${imageUrl}" alt="${escapeHtml(item.title || "参考图片")}" />` : ""}
              <div class="source-card__body">
                <div class="source-card__head">
                  <strong>${escapeHtml(item.title || "未命名资料")}</strong>
                  <span class="pill">${escapeHtml(isImage ? "参考图片" : item.source || "用户资料")}</span>
                </div>
                ${item.snippet ? `<p>${escapeHtml(item.snippet)}</p>` : ""}
                ${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.url)}</a>` : ""}
                <div class="toolbar">
                  <button class="btn btn--ghost" data-toggle-source="${escapeHtml(item.id)}" data-next-must-use="${item.must_use ? "false" : "true"}">
                    ${item.must_use ? "取消必用" : "设为必用"}
                  </button>
                  <button class="btn btn--danger" data-delete-source="${escapeHtml(item.id)}">删除</button>
                </div>
              </div>
            </article>
          `;
        }).join("")
      : `<div class="source-empty">加入链接、摘要或参考图片，生成文案时会优先采用。</div>`;
  }
  if (els.sourceCandidateList) {
    els.sourceCandidateList.innerHTML = candidates.map((item) => `
      <article class="source-candidate-card">
        <div>
          <div class="source-card__head">
            <strong>${escapeHtml(item.title || "检索结果")}</strong>
            <span class="pill">${escapeHtml(item.source || "Web")}</span>
          </div>
          <p>${escapeHtml(item.snippet || "")}</p>
          <a href="${escapeHtml(item.url || "#")}" target="_blank" rel="noreferrer">查看原文</a>
        </div>
        <button class="btn ${item.adopted ? "btn--ghost" : "btn--primary"}" data-adopt-source="${escapeHtml(item.id)}" ${item.adopted ? "disabled" : ""}>
          ${item.adopted ? "已采用" : "采用为证据"}
        </button>
      </article>
    `).join("");
  }
}

function contentSaveSemanticNotice(changeImpact, numericConsistency) {
  const impact = changeImpact || {};
  const invalidate = impact.invalidate || {};
  const unsupported = Array.isArray(numericConsistency?.unsupported_facts) ? numericConsistency.unsupported_facts : [];
  const parts = [];
  if (impact.scope === "cta_only") {
    parts.push("仅结尾变化：重做配音、字幕和成片，图片与封面保持");
  } else if (impact.scope === "scene_local") {
    const targets = Array.isArray(invalidate.scene_images) ? invalidate.scene_images.join("、") : "对应镜头";
    parts.push(`局部事实变化：只标记 ${targets || "对应镜头"}`);
  } else if (impact.scope === "opening_only") {
    parts.push("仅开场变化：只标记首镜");
  } else if (impact.scope === "full_script") {
    parts.push("主题、核心观点或整稿变化：全量资产需更新");
  }
  if (unsupported.length) {
    parts.push(`发现 ${unsupported.length} 个未核验精确数字，文案闸门将阻止继续生产`);
  }
  return parts.join(" · ");
}

function renderContentLearningExplanation(bundle) {
  if (!els.contentLearningExplanation) return;
  // Release metrics belong to the analytics page. Showing them beside the
  // editor made post-release observations look like current writing rules.
  els.contentLearningExplanation.hidden = true;
  els.contentLearningExplanation.innerHTML = "";
}

function renderContentBundle({ forceEditor = false } = {}) {
  const bundle = state.currentContent;
  if (!bundle) {
    state.sourceMaterials = [];
    state.sourceCandidates = null;
    syncEditorFromBundle(null, { force: forceEditor });
    renderSummary(null);
    renderReferences([]);
    renderSourceWorkbench();
    renderSceneCountControls();
    renderProductModeControls();
    els.contentGenerateStatus.textContent = "状态：空闲";
    renderContentLearningExplanation(null);
    updateWorkflowButtons();
    return;
  }
  syncEditorFromBundle(bundle, { force: forceEditor });
  state.sourceMaterials = Array.isArray(bundle.source_materials) ? bundle.source_materials : [];
  state.sourceCandidates = bundle.source_candidates || null;
  renderSummary(bundle.summary || null, bundle.fact_registry || null);
  renderReferences(bundle.references || []);
  renderSourceWorkbench();

  const sync = bundle.content_sync || {};
  const saveNotice = bundle.save_notice ? ` · ${bundle.save_notice}` : "";
  if (sync.running || sync.status === "queued") {
    const elapsed = sync.started_at ? ` · ${formatTaskElapsed(Math.max(0, Date.now() / 1000 - Number(sync.started_at)))}` : "";
    els.contentGenerateStatus.textContent = `内容已保存 · ${sync.message || "后台更新中"}${elapsed}${saveNotice}`;
  } else if (sync.status === "failed" || sync.status === "interrupted") {
    els.contentGenerateStatus.textContent = `内容同步：${sync.message || sync.status}`;
  } else {
    const generation = bundle.content_generate || {};
    const statusLabels = {
      idle: "空闲",
      running: "生成中",
      succeeded: "已完成",
      succeeded_with_warnings: "已生成 · 建议优化",
      failed: "生成失败",
      interrupted: "生成中断",
      cancelled: "已取消",
    };
    const stageLabels = {
      think: "整理主题",
      search: "检索资料",
      evidence: "冻结本期资料",
      draft: "AI 撰写草稿",
      ai_review: "AI 六维初审",
      targeted_rewrite: "定点修改失败项",
      ai_recheck: "AI 同标准复审",
      finalize: "保存通过稿",
      visual: "整理分镜",
    };
    const status = statusLabels[generation.status || "idle"] || generation.status;
    const stage = generation.stage ? ` · ${stageLabels[generation.stage] || generation.stage}` : "";
    const elapsed = generation.status === "running" && generation.started_at
      ? ` · 已用时 ${formatTaskElapsed(Math.max(0, Date.now() / 1000 - Number(generation.started_at)))}`
      : "";
    const referenceCount = Number(generation.reference_count || 0) || (Array.isArray(bundle.references) ? bundle.references.length : 0);
    const references = referenceCount > 0 ? ` · ${referenceCount} 条资料` : "";
    const provider = generation.provider ? ` · ${generation.provider}` : "";
    const editorialScore = Number(generation.editorial_ai_score?.weighted_total || 0);
    const aiReview = editorialScore > 0 ? ` · AI审稿 ${editorialScore}分` : "";
    const message = generation.message ? ` · ${generation.message}` : "";
    const syncDone = sync.status === "succeeded" ? " · 分析已更新" : "";
    els.contentGenerateStatus.textContent = `状态：${status}${stage}${elapsed}${references}${provider}${aiReview}${message}${syncDone}`;
  }
  renderContentLearningExplanation(bundle);
  renderSceneCountControls();
  renderProductModeControls();
  updateWorkflowButtons();
}

function renderSteps() {
  const mode = state.currentProject?.template_mode || "video";
  const visibleSteps = mode === "article"
    ? STEP_DEFS.filter((step) => ["images", "covers", "images_missing", "covers_missing", "article"].includes(step.key))
    : STEP_DEFS;
  els.stepList.innerHTML = visibleSteps
    .map(
      (step) => `
        <label class="step-item">
          <input type="checkbox" data-step="${step.key}" ${step.defaultChecked === false ? "" : "checked"} />
          <div>
            <strong>${escapeHtml(step.label)}</strong>
            <div class="muted">${escapeHtml(step.desc)}</div>
          </div>
        </label>
      `
    )
    .join("");
  renderCoverGenerationControls();
  renderProductionCockpit();
  updateWorkflowButtons();
}

function syncVideoStepWithReviewMode({ force = false } = {}) {
  if (state.currentProject?.template_mode === "article") return;
  const videoStep = document.querySelector('[data-step="video"]');
  if (!videoStep || state.imageReview == null) return;
  if (!force && videoStep.dataset.reviewModeInitialized === "true") return;
  videoStep.checked = state.imageReview.required === false;
  videoStep.dataset.reviewModeInitialized = "true";
}

function renderImageReview() {
  if (!els.imageReviewRequired || !els.confirmImagesBtn || !els.imageReviewPill || !els.imageReviewHelper) return;
  const status = state.imageReview;
  if (!state.currentProject) {
    els.imageReviewRequired.checked = true;
    els.confirmImagesBtn.disabled = true;
    els.imageReviewModeButtons.forEach((button) => {
      const active = button.dataset.imageReviewMode === "manual";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
      button.disabled = true;
    });
    els.imageReviewPill.textContent = "待确认";
    els.imageReviewPill.className = "pill pill--warn";
    els.imageReviewHelper.textContent = "先选择一个主题项目。";
    renderTaskCommandBar();
    return;
  }
  const required = status?.required !== false;
  const confirmed = Boolean(status?.confirmed);
  const ready = Boolean(status?.ready_to_confirm);
  const coverEnabled = status?.cover_enabled !== false && coverGenerationEnabled();
  const pendingCandidates = Number(status?.scene_candidate_pending || 0) + Number(status?.cover_candidate_pending || 0);
  const jobRunning = Boolean(state.currentJob?.running);
  els.imageReviewRequired.checked = required;
  els.imageReviewModeButtons.forEach((button) => {
    const active = button.dataset.imageReviewMode === (required ? "manual" : "auto");
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
    button.disabled = jobRunning;
  });
  els.confirmImagesBtn.disabled = !required || !ready || jobRunning;
  if (!required) {
    els.imageReviewPill.textContent = "全自动";
    els.imageReviewPill.className = "pill pill--success";
    els.imageReviewHelper.textContent = pendingCandidates
      ? `AI 正在处理 ${pendingCandidates} 个关键位候选；推荐方案会成为正式图，不需要人工逐张确认。`
      : "吸引力预算集中在关键位置：首镜先做 3 个文字构思，只生成前 2 名，再看真实成图选 1 张；普通镜头每镜只生成 1 张。";
    renderTaskCommandBar();
    return;
  }
  if (confirmed) {
    els.imageReviewPill.textContent = "已确认";
    els.imageReviewPill.className = "pill pill--success";
    els.imageReviewHelper.textContent = coverEnabled
      ? "当前场景图和封面图已确认，可以进入成片合成。"
      : "当前场景图已确认；本期跳过封面，可以进入成片合成。";
    renderTaskCommandBar();
    return;
  }
  els.imageReviewPill.textContent = pendingCandidates ? `方案待选 ${pendingCandidates}` : (ready ? "待确认" : "图片未齐");
  els.imageReviewPill.className = "pill pill--warn";
  const sceneText = `${status?.scene_generated ?? 0}/${status?.scene_expected ?? 0}`;
  const coverText = coverEnabled ? `${status?.cover_generated ?? 0}/${status?.cover_expected ?? 3}` : "本期跳过";
  els.imageReviewHelper.textContent = pendingCandidates
    ? `还有 ${pendingCandidates} 个关键位方案等待选择；采用后未选方案会自动清理，再确认整组图片。`
    : ready
      ? (coverEnabled
        ? "请重点检查封面与首镜是否兑现标题和首句；普通镜头保持单图，不满意时再为指定镜头生成 1 张备选。"
        : "请重点检查首镜是否兑现标题和首句；本期封面已跳过。")
      : `确认前需要先生成完整图片：场景图 ${sceneText}，封面 ${coverText}。`;
  renderTaskCommandBar();
}

function stageGatePillClass(status, passed) {
  if (status === "skipped_reuse") return "";
  if (status === "accepted_with_warnings") return "pill--warn";
  if (status === "fixing" || status === "running") return "pill--warn";
  if (status === "blocked") return "pill--warn";
  if (passed || status === "passed") return "";
  if (status === "pending" || status === "stale") return "pill--warn";
  if (status === "needs_fix") return "pill--warn";
  return "pill--risk";
}

function stageGateStatusLabel(status, passed) {
  if (status === "skipped_reuse") return "复用跳过";
  if (status === "accepted_with_warnings") return "带提醒通过";
  if (status === "fixing" || status === "running") return "自动优化中";
  if (status === "blocked") return "等待前置闸门";
  if (status === "stale") return "内容已更新";
  if (status === "needs_fix") return "待优化";
  if (status === "failed") return "未通过";
  if (status === "pending") return "待检查";
  if (passed || status === "passed") return "已通过";
  return status || "待检查";
}

function stageGateRepairLabel(gate, issueText = "") {
  if (gate?.key === "content_gate") return "优化文案并复检";
  if (gate?.key === "visual_prompt_gate") return "重建提示词并复检";
  const text = String(issueText || "");
  if (/(podcast\.mp3|音频版本|配音过期|缺少音频)/i.test(text)) return "重新配音并复检";
  if (/(subtitles?\.srt|字幕版本|字幕过期|缺少字幕)/i.test(text)) return "重做字幕并复检";
  if (/(场景图|缺图|图片缺失)/i.test(text)) return "补齐场景图并复检";
  if (/(封面|cover)/i.test(text)) return "补齐封面并复检";
  return "修复阻断项并复检";
}

function formatTaskElapsed(seconds) {
  const safe = Math.max(0, Math.floor(Number(seconds) || 0));
  if (safe < 60) return `${safe} 秒`;
  const minutes = Math.floor(safe / 60);
  const remain = safe % 60;
  return remain ? `${minutes} 分 ${remain} 秒` : `${minutes} 分钟`;
}

function liveGateElapsed(progress) {
  const reported = Number(progress?.elapsed_seconds);
  const startedAt = Number(progress?.started_at);
  const localElapsed = Number.isFinite(startedAt) ? Math.max(0, Date.now() / 1000 - startedAt) : 0;
  return Math.max(Number.isFinite(reported) ? reported : 0, localElapsed);
}

function stageGatePhaseLabel(progress) {
  const phase = String(progress?.phase || "");
  const repairLabels = {
    repair_audio: "重新生成配音",
    repair_subtitles: "重新对齐字幕",
    repair_images_missing: "成片前补齐缺失场景图",
    repair_covers_missing: "成片前补齐缺失封面",
  };
  if (repairLabels[phase]) return repairLabels[phase];
  const labels = {
    queued: "准备启动",
    round_start: "开始新一轮",
    checking: "读取并检查",
    cache_hit: "复用未变化检查结果",
    checked: "初检完成",
    rule_repair: "规则与事实修复",
    rhythm_rewrite: "节奏增强",
    ai_rewrite: "AI 总编改稿",
    ai_rewrite_returned: "AI 已返回",
    ai_rewrite_validating: "改稿事实复检",
    ai_unavailable: "AI 服务不可用",
    second_rewrite: "第二轮校准",
    prompt_rebuild: "重建图片提示词",
    image_prepare: "准备图片重绘",
    image_redraw: "逐张重绘",
    rechecking: "重新检查",
    round_complete: "本轮复检完成",
    complete: "复检完成",
    needs_attention: "等待处理",
    finished: "任务结束",
    failed: "运行失败",
  };
  return labels[phase] || "正在处理";
}

function jobStepPhaseLabel(progress) {
  const labels = {
    queued: "准备启动",
    image_generation: "生成场景图",
    chatgpt_submitted: "提示词已发送",
    chatgpt_wait: "等待 ChatGPT 生图",
    auto_retry: "外部服务波动，正在自动重试",
    image_saved: "图片已保存",
    bgm_analyze: "分析主题",
    bgm_generate: "匹配音乐",
    bgm_complete: "音乐已就绪",
    visual_master: "构建画面母版",
    visual_master_cached: "复用画面母版",
    audio_mix: "整理成片音轨",
    quality_check: "成片质量总检",
    complete: "处理完成",
    failed: "运行失败",
  };
  return labels[String(progress?.phase || "")] || "正在处理";
}

function beginOptimisticGateJob(job, gateKey) {
  const report = state.stageGates?.result || state.stageGates || {};
  const gates = Array.isArray(report.ordered_gates) ? report.ordered_gates : Object.values(report.gates || {});
  const gate = gates.find((item) => item?.key === gateKey) || {};
  const startedAt = Number(job?.started_at) || Date.now() / 1000;
  state.currentJob = {
    ...(job || {}),
    status: "running",
    running: true,
    current_step: `gate:${gateKey}`,
    progress: [
      {
        key: `gate:${gateKey}`,
        label: gate.label || gateKey,
        status: "running",
        phase: "queued",
        message: "请求已收到，后台任务正在启动",
        started_at: startedAt,
      },
    ],
  };
  renderJob();
  renderStageGates();
  updateWorkflowButtons();
}

function renderStageGates() {
  if (!els.stageGatesPanel) return;
  const report = state.stageGates?.result || state.stageGates || {};
  const gates = Array.isArray(report.ordered_gates)
    ? report.ordered_gates
    : Object.values(report.gates || {});
  if (!gates.length) {
    els.stageGatesPanel.innerHTML = `<div class="muted">还没有生产闸门报告。点击“检查闸门”或开始生产后会显示。</div>`;
    return;
  }
  const renderedProjectId = Number(state.currentProject?.id || report.project_id || 0);
  els.stageGatesPanel.innerHTML = gates
    .map((gate) => {
      const issues = Array.isArray(gate.issues) ? gate.issues : [];
      const actions = Array.isArray(gate.actions) ? gate.actions : [];
      const issue = issues[0] || null;
      const activeGateProgress = (state.currentJob?.progress || []).find(
        (item) => item?.key === `gate:${gate.key}` && ["queued", "running"].includes(item?.status),
      );
      const isActivelyFixing = Boolean(activeGateProgress);
      const activeElapsed = isActivelyFixing ? liveGateElapsed(activeGateProgress) : 0;
      const activeElapsedLabel = formatTaskElapsed(activeElapsed);
      const activePhaseLabel = stageGatePhaseLabel(activeGateProgress);
      const activeMessage = String(activeGateProgress?.message || "任务已提交，正在读取最新内容");
      const status = isActivelyFixing ? "fixing" : (gate.status || (gate.passed ? "passed" : "pending"));
      const statusLabel = isActivelyFixing ? `运行中 · ${activeElapsedLabel}` : stageGateStatusLabel(status, gate.passed);
      const isSkippedReuse = status === "skipped_reuse";
      const isManualSkip = Boolean(gate.accepted_by_user) && status === "accepted_with_warnings";
      const isSkipped = isSkippedReuse || isManualSkip || status === "skipped_manual";
      const isBlocked = status === "blocked";
      const gateIssueText = issues.map((item) => `${item?.where || ""} ${item?.issue || ""} ${item?.fix || ""}`).join(" ");
      const canIgnoreImageWeak = gate.key === "pre_video_gate"
        && !gate.passed
        && !isBlocked
        && /(图片吸引力|自检提示|画面节奏|场景差异度|固定画风|固定风格|生产元信息|吸引力偏弱|平均吸引力偏弱|偏暗|对比度|细节偏少|太素|弱提示词)/i.test(gateIssueText);
      const canAcceptVisualPrompt = !gate.passed
        && status !== "skipped_reuse"
        && status !== "fixing"
        && !isBlocked;
      const researchChecklist = gate.key === "content_gate" &&
        /(缺少口播正文|待补资料清单|没有可分析的正文\/口播内容)/.test(gateIssueText);
      const canAutoFixGate = !researchChecklist && !gate.passed
        && status !== "skipped_reuse"
        && status !== "fixing"
        && !isBlocked
        && ["content_gate", "visual_prompt_gate", "pre_video_gate"].includes(gate.key);
      const defaultMessage = isSkippedReuse
        ? (gate.verdict || gate.details?.skipped_reason || "复用旧图，本轮不检查生图提示词")
        : isActivelyFixing
          ? activeMessage
          : (gate.desc || "等待检查");
      const beforeScore = Number(gate.before?.score);
      const afterScore = Number(gate.after?.score ?? gate.score);
      const hasScoreChange = Number.isFinite(beforeScore) && Number.isFinite(afterScore) && beforeScore !== afterScore;
      const scoreLabel = isActivelyFixing
        ? `已运行 ${activeElapsedLabel}`
        : isBlocked
          ? "等待前置"
        : status === "stale"
          ? "待复检"
          : hasScoreChange
            ? `${beforeScore} → ${afterScore} 分`
            : `${escapeHtml(String(gate.score ?? 0))} 分`;
      return `
        <article class="stage-gate-item">
          <div class="stage-gate-item__top">
            <strong>${escapeHtml(gate.label || gate.key || "")}</strong>
            <span class="pill ${stageGatePillClass(status, gate.passed)}">${escapeHtml(isManualSkip ? "已跳过（提醒保留）" : statusLabel)}</span>
          </div>
          <div class="summary-card">
            <strong>${isSkipped ? "已跳过" : scoreLabel}</strong>
            <span>${isSkippedReuse ? "复用旧图，不检查提示词" : isManualSkip ? "人工放行，可立即进入下一步；原评分和提醒已保留" : isActivelyFixing ? escapeHtml(activePhaseLabel) : isBlocked ? escapeHtml(gate.verdict || "先完成前置闸门") : status === "stale" ? "旧分数已失效" : (gate.passed ? "可进入下一步" : "仍需继续优化")}</span>
          </div>
          ${isActivelyFixing ? `<div class="stage-gate-live" role="status" aria-live="polite">
            <div class="stage-gate-live__track"><span></span></div>
            <div class="stage-gate-live__meta">
              <strong>${escapeHtml(activePhaseLabel)}</strong>
              <span>${escapeHtml(activeMessage)}</span>
            </div>
          </div>` : ""}
          ${!isActivelyFixing ? `<div class="muted stage-gate-item__issue">${escapeHtml(issue ? `${issue.where || ""} ${issue.issue || ""}`.trim() : defaultMessage)}</div>` : ""}
          ${!isActivelyFixing && issue?.fix ? `<div class="muted">建议：${escapeHtml(issue.fix)}</div>` : ""}
          ${!isActivelyFixing && actions.length ? `<div class="stage-gate-actions">${actions.map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
          ${(canAutoFixGate || canAcceptVisualPrompt || canIgnoreImageWeak) ? `<div class="toolbar toolbar--tight" style="margin-top:10px;">
            ${canAutoFixGate ? `<button class="btn btn--primary" data-stage-gate-run="${escapeHtml(gate.key)}" data-stage-gate-project-id="${renderedProjectId}">${escapeHtml(stageGateRepairLabel(gate, gateIssueText))}</button>` : ""}
            ${canAcceptVisualPrompt ? `<button class="btn btn--ghost" data-stage-gate-accept="${escapeHtml(gate.key)}" data-stage-gate-project-id="${renderedProjectId}">跳过此闸门</button>` : ""}
            ${canIgnoreImageWeak ? `<button class="btn btn--ghost" data-quality-ignore-images="video">忽略弱图并合成</button>` : ""}
          </div>` : ""}
        </article>
      `;
    })
    .join("");
}

function statusToneClass(status) {
  if (status === "risk") return "pill--risk";
  if (status === "warn") return "pill--warn";
  return "";
}

function setProductionAssetTab(tabKey) {
  const allowed = new Set(["scenes", "covers"]);
  const key = allowed.has(tabKey) ? tabKey : "scenes";
  state.productionAssetTab = key;
  document.querySelectorAll("[data-production-asset-tab]").forEach((button) => {
    const active = button.dataset.productionAssetTab === key;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  document.querySelectorAll("[data-production-asset-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.productionAssetPanel !== key;
  });
}

function renderProductionStageStrip() {
  if (!els.productionStageStrip) return;
  const definitions = [
    ["content", "文案"],
    ["audio", "配音"],
    ["subtitles", "字幕"],
    ["scene_images", "场景图"],
    ["covers", "封面"],
    ["motion_clips", "动态镜头"],
    ["video", "成片"],
  ];
  const assets = Array.isArray(state.productionManifest?.assets) ? state.productionManifest.assets : [];
  const assetMap = new Map(assets.map((item) => [item?.key, item]));
  const activeKey = String(state.currentJob?.current_step || "");
  const statusLabels = {
    current: "已完成",
    running: "运行中",
    stale: "已过期",
    partial: "未齐全",
    missing: "未生成",
    skipped: "本期跳过",
  };
  els.productionStageStrip.innerHTML = definitions.map(([key, label], index) => {
    const asset = assetMap.get(key) || {};
    const running = Boolean(state.currentJob?.running) && (
      activeKey === key
      || (key === "scene_images" && activeKey.startsWith("images"))
      || (key === "motion_clips" && activeKey === "motion_clips")
      || (key === "covers" && activeKey.startsWith("covers"))
    );
    const status = key === "covers" && !coverGenerationEnabled()
      ? "skipped"
      : (running ? "running" : String(asset.status || "missing"));
    return `
      <div class="production-stage production-stage--${escapeHtml(status)}" title="${escapeHtml(asset.detail || statusLabels[status] || "")}">
        <span>${index + 1}</span>
        <div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(statusLabels[status] || status)}</small></div>
      </div>
    `;
  }).join("");
}

function renderProductionManifest() {
  if (!els.productionManifestPanel || !els.productionManifestPill) return;
  const manifest = state.productionManifest;
  if (!state.currentProject) {
    els.productionManifestPanel.innerHTML = "";
    els.productionManifestPill.textContent = "未选择项目";
    els.productionManifestPill.className = "pill";
    renderProductionStageStrip();
    return;
  }
  if (!manifest) {
    els.productionManifestPanel.innerHTML = `<div class="muted">正在读取资产来源版本...</div>`;
    els.productionManifestPill.textContent = "读取中";
    els.productionManifestPill.className = "pill";
    renderProductionStageStrip();
    return;
  }
  const statusLabels = {
    current: "当前版",
    running: "处理中",
    stale: "旧版",
    partial: "未齐",
    missing: "缺失",
    skipped: "本期跳过",
  };
  const overallLabels = {
    current: "全部一致",
    running: "正在更新",
    stale: "存在旧资产",
    incomplete: "生产未完成",
  };
  const pillClass = manifest.overall_status === "current"
    ? ""
    : manifest.overall_status === "running" || manifest.overall_status === "incomplete"
      ? "pill--warn"
      : "pill--risk";
  els.productionManifestPill.textContent = overallLabels[manifest.overall_status] || manifest.overall_status || "未知";
  els.productionManifestPill.className = `pill ${pillClass}`;
  const assets = Array.isArray(manifest.assets) ? manifest.assets : [];
  els.productionManifestPanel.innerHTML = assets
    .map((item) => `
      <div class="asset-version-item asset-version-item--${escapeHtml(item.status || "missing")}" title="${escapeHtml(item.relative_path || "")}">
        <span class="asset-version-dot" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(item.label || item.key || "")}</strong>
          <span>${escapeHtml(item.detail || "")}</span>
        </div>
        <em>${escapeHtml(statusLabels[item.status] || item.status || "")}</em>
      </div>
    `)
    .join("");
  renderProductionStageStrip();
  renderTaskCommandBar();
}

function renderVoiceStatus() {
  if (!els.voiceStatusTitle || !els.voiceStatusPill || !els.voiceStatusReason || !els.voiceStatusMeta) return;
  const project = state.currentProject;
  const status = state.voiceStatus;
  const running = Boolean(state.currentJob?.running && ["audio", "subtitles"].includes(state.currentJob?.current_step));
  if (!project) {
    els.voiceStatusTitle.textContent = "尚未选择项目";
    els.voiceStatusPill.textContent = "未选择";
    els.voiceStatusPill.className = "pill";
    els.voiceStatusReason.textContent = "选择项目后会核对实际配音版本。";
    els.voiceStatusMeta.innerHTML = "";
    if (els.voiceSettingsBtn) els.voiceSettingsBtn.disabled = true;
    if (els.voiceRebuildBtn) els.voiceRebuildBtn.disabled = true;
    return;
  }
  if (!status) {
    els.voiceStatusTitle.textContent = "正在读取实际音色";
    els.voiceStatusPill.textContent = "读取中";
    els.voiceStatusPill.className = "pill";
    els.voiceStatusReason.textContent = "正在核对音频、稿件和频道声音设置。";
    els.voiceStatusMeta.innerHTML = "";
    if (els.voiceSettingsBtn) els.voiceSettingsBtn.disabled = Boolean(state.currentJob?.running);
    if (els.voiceRebuildBtn) els.voiceRebuildBtn.disabled = true;
    return;
  }
  const generatedLabels = Array.isArray(status.generated_labels) ? status.generated_labels.filter(Boolean) : [];
  const expectedLabels = Array.isArray(status.expected_labels) ? status.expected_labels.filter(Boolean) : [];
  const displayLabels = generatedLabels.length ? generatedLabels : expectedLabels;
  els.voiceStatusTitle.textContent = displayLabels.join(" + ") || "尚未选择音色";
  const labels = {
    current: "已锁定",
    stale: "旧声音",
    missing: "未生成",
    unverified: "未核验",
    risk: "有风险",
  };
  els.voiceStatusPill.textContent = running ? "生成中" : (labels[status.status] || status.status || "未知");
  els.voiceStatusPill.className = `pill ${running || ["missing", "unverified"].includes(status.status) ? "pill--warn" : ["stale", "risk"].includes(status.status) ? "pill--risk" : ""}`;
  els.voiceStatusReason.textContent = running
    ? "正在重新配音并对齐字幕，完成后会重新核验实际声音版本。"
    : (status.reason || "等待配音验收结果。");
  const meta = [
    status.voice_mode === "dual" ? "双人讲述" : "单人讲述",
    status.generated_speech_rate ? `当前音频 ${Number(status.generated_speech_rate).toFixed(2)}x` : "",
    status.audio_duration_seconds ? `时长 ${formatTaskElapsed(Math.round(status.audio_duration_seconds))}` : "",
    status.natural_pacing_enforced ? "自然停顿已校准" : "",
    status.inserted_pause_seconds ? `句间补足 ${Number(status.inserted_pause_seconds).toFixed(1)} 秒` : "",
    status.current && status.utterance_count ? `${status.utterance_count}/${status.utterance_count} 句音色绑定一致` : "",
    status.single_voice_enforced ? "第二音色已禁用" : "",
    status.verification_label || "",
    status.status === "stale" && expectedLabels.length ? `当前设置 ${expectedLabels.join(" + ")}` : "",
  ].filter(Boolean);
  els.voiceStatusMeta.innerHTML = meta.map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join("");
  if (els.voiceSettingsBtn) els.voiceSettingsBtn.disabled = Boolean(state.currentJob?.running);
  if (els.voiceRebuildBtn) {
    els.voiceRebuildBtn.textContent = status.audio_exists ? "重新配音并对齐字幕" : "生成配音并对齐字幕";
    els.voiceRebuildBtn.disabled = Boolean(state.currentJob?.running);
  }
}

function renderBgmStatus() {
  if (!els.bgmStatusTitle || !els.bgmStatusPill || !els.bgmStatusReason || !els.bgmStatusMeta || !els.bgmRematchBtn) return;
  if (!state.currentProject) {
    els.bgmStatusTitle.textContent = "尚未选择项目";
    els.bgmStatusPill.textContent = "未选择";
    els.bgmStatusPill.className = "pill";
    els.bgmStatusReason.textContent = "选择项目后会分析本期主题。";
    els.bgmStatusMeta.innerHTML = "";
    if (els.bgmPreview) {
      els.bgmPreview.classList.add("hidden");
      els.bgmPreview.removeAttribute("src");
    }
    if (els.bgmMixPreview) {
      els.bgmMixPreview.classList.add("hidden");
      els.bgmMixPreview.removeAttribute("src");
    }
    if (els.bgmMixPreviewBtn) els.bgmMixPreviewBtn.disabled = true;
    if (els.bgmLockBtn) els.bgmLockBtn.disabled = true;
    els.bgmRematchBtn.disabled = true;
    return;
  }
  const status = state.bgmStatus;
  const running = Boolean(state.currentJob?.running && state.currentJob?.current_step === "bgm");
  if (!status) {
    els.bgmStatusTitle.textContent = "正在分析本期主题";
    els.bgmStatusPill.textContent = "读取中";
    els.bgmStatusPill.className = "pill";
    els.bgmStatusReason.textContent = "正在读取音乐画像与版本信息。";
    els.bgmStatusMeta.innerHTML = "";
    if (els.bgmPreview) els.bgmPreview.classList.add("hidden");
    if (els.bgmMixPreview) els.bgmMixPreview.classList.add("hidden");
    if (els.bgmMixPreviewBtn) els.bgmMixPreviewBtn.disabled = true;
    if (els.bgmLockBtn) els.bgmLockBtn.disabled = true;
    els.bgmRematchBtn.disabled = true;
    return;
  }
  const stateLabel = running
    ? "匹配中"
    : ({ current: "当前版", stale: "需更新", pending: "待生成", disabled: "已关闭", missing: "缺失" }[status.status] || status.status || "未知");
  const tone = running || ["pending", "missing"].includes(status.status)
    ? "pill--warn"
    : status.status === "stale"
      ? "pill--risk"
      : "";
  els.bgmStatusTitle.textContent = status.status === "stale" && status.desired_label
    ? `${status.label || "旧音乐"} → ${status.desired_label}`
    : (status.label || status.desired_label || "自动匹配");
  els.bgmStatusPill.textContent = stateLabel;
  els.bgmStatusPill.className = `pill ${tone}`;
  const bgmReason = status.reason || status.desired_reason || "按本期主题与口播情绪自动选择。";
  els.bgmStatusReason.textContent = running
    ? "任务已启动，正在根据本期主题和口播重新选择音乐。"
    : [bgmReason, status.rotation_reason, status.fallback_reason].filter(Boolean).join("；");
  const bpm = Array.isArray(status.bpm) && status.bpm.length ? status.bpm : (Array.isArray(status.desired_bpm) ? status.desired_bpm : []);
  const track = status.track && typeof status.track === "object" ? status.track : {};
  const trackLicense = String(track.license || "");
  const trackDuration = Number(track.duration || 0);
  const sourceLabels = {
    loudly: "Loudly 优质完整配乐",
    jamendo: "Jamendo 完整纯音乐",
    procedural_local: status.online_catalog_ready ? "本地无版权生成" : "本地主题备用",
    freesound: "Freesound 热门 CC0",
    project_manual: "人工音乐",
    template_fixed: "频道固定曲",
    theme_auto: "按主题自动",
    off: "关闭",
  };
  const meta = [
    track.name ? `曲目 ${track.name}` : "",
    track.artist_name ? `音乐人 ${track.artist_name}` : "",
    bpm.length ? `BPM ${bpm[0]}-${bpm[bpm.length - 1]}` : "",
    status.mood || status.desired_mood ? `画像 ${status.mood || status.desired_mood}` : "",
    status.arrangement_label ? `配器 ${status.arrangement_label}` : "",
    status.source ? (sourceLabels[status.source] || status.source) : "",
    trackLicense.includes("publicdomain/zero") || /\bcc0\b/i.test(trackLicense) ? "授权 CC0" : "",
    trackDuration > 0 ? `时长 ${Math.round(trackDuration)} 秒` : "",
    Number(status.volume) > 0 ? `混音 ${Number(status.volume).toFixed(2)}` : "",
    status.manual_locked ? "人工锁定" : "自动跟随主题",
    status.rotation_reason?.includes("避开") ? "频道轮换已生效" : "",
    status.source === "procedural_local" && !status.online_catalog_ready ? "在线曲库未配置" : "",
    status.audio_vocal_audit?.status === "passed" ? "实际人声检测通过" : "",
    status.audio_vocal_audit?.status === "inconclusive" ? "实际人声检测未完成" : "",
    status.audio_vocal_audit?.status === "unavailable" ? "仅完成标签过滤" : "",
    Number(track.rejected_candidate_count || 0) > 0 ? `已淘汰 ${Number(track.rejected_candidate_count)} 首不合格候选` : "",
  ].filter(Boolean);
  els.bgmStatusMeta.innerHTML = meta.map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join("");
  const statusVolume = Number(status.volume);
  const volume = Math.max(0, Math.min(Number.isFinite(statusVolume) ? statusVolume : 0.18, 0.35));
  if (els.bgmVolume) {
    els.bgmVolume.value = volume.toFixed(2);
    els.bgmVolume.disabled = running || Boolean(state.currentJob?.running) || !status.path;
  }
  if (els.bgmVolumeValue) els.bgmVolumeValue.textContent = volume.toFixed(2);
  if (els.bgmLockBtn) {
    els.bgmLockBtn.textContent = status.track_locked ? "解除锁定" : "锁定本曲";
    els.bgmLockBtn.disabled = running || Boolean(state.currentJob?.running) || !status.path;
  }
  if (els.bgmMixPreviewBtn) {
    els.bgmMixPreviewBtn.disabled = running || Boolean(state.currentJob?.running) || !status.path;
  }
  const mixVersion = `${status.updated_at || status.context_hash || "current"}:${volume.toFixed(2)}`;
  if (state.bgmMixPreviewVersion && state.bgmMixPreviewVersion !== mixVersion && els.bgmMixPreview) {
    els.bgmMixPreview.pause();
    els.bgmMixPreview.removeAttribute("src");
    els.bgmMixPreview.classList.add("hidden");
  }
  state.bgmMixPreviewVersion = mixVersion;
  if (els.bgmPreview) {
    const canPreview = Boolean(status.path) && status.status !== "disabled";
    if (canPreview) {
      const version = encodeURIComponent(String(status.updated_at || status.context_hash || "current"));
      const previewUrl = `${API_BASE}/api/projects/${state.currentProject.id}/bgm/audio?v=${version}`;
      if (els.bgmPreview.getAttribute("src") !== previewUrl) {
        els.bgmPreview.setAttribute("src", previewUrl);
        els.bgmPreview.load();
      }
      els.bgmPreview.classList.remove("hidden");
    } else {
      els.bgmPreview.classList.add("hidden");
      els.bgmPreview.removeAttribute("src");
    }
  }
  const fixedMode = ["off", "disabled", "template", "channel", "fixed"].includes(String(status.mode || "").toLowerCase());
  els.bgmRematchBtn.textContent = status.manual_locked && !fixedMode ? "解除锁定并换一首" : "换一首";
  els.bgmRematchBtn.disabled = running || Boolean(state.currentJob?.running) || fixedMode;
}

function renderProjectStatus() {
  if (!els.projectStatusStrip) return;
  if (!state.currentProject) {
    els.projectStatusStrip.innerHTML = "";
    return;
  }
  const payload = state.projectStatus;
  if (!payload) {
    els.projectStatusStrip.innerHTML = `<div class="muted">项目状态加载中...</div>`;
    return;
  }
  const steps = Array.isArray(payload.steps) ? payload.steps : [];
  els.projectStatusStrip.innerHTML = steps
    .map((item) => {
      const title = [item.detail, item.action].filter(Boolean).join(" · ");
      const rawStatus = String(item.status || "ok").toLowerCase();
      const tone = rawStatus === "risk" || rawStatus === "failed" ? "risk" : rawStatus === "warn" || rawStatus === "pending" ? "warn" : "ok";
      const statusLabel = tone === "ok" ? "完成" : tone === "warn" ? "注意" : "处理";
      return `
        <div class="project-status-item project-status-item--${tone}" title="${escapeHtml(title)}">
          <span class="project-status-dot" aria-hidden="true"></span>
          <strong>${escapeHtml(item.label || item.key || "")}</strong>
          <span class="project-status-state">${statusLabel}</span>
          <span>${escapeHtml(item.detail || "")}</span>
        </div>
      `;
    })
    .join("");
  renderTaskCommandBar();
}

function jobHeartbeatLabel(job) {
  const heartbeatAt = Number(job?.heartbeat_at || job?.updated_at || job?.started_at || 0);
  if (!Number.isFinite(heartbeatAt) || heartbeatAt <= 0) return "等待首次心跳";
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - heartbeatAt));
  if (seconds < 3) return "刚刚收到后台心跳";
  if (seconds < 60) return `${seconds} 秒前收到后台心跳`;
  return `${Math.floor(seconds / 60)} 分钟前收到后台心跳`;
}

function jobRuntimeHealth(job) {
  const backend = job?.runtime_health && typeof job.runtime_health === "object" ? job.runtime_health : null;
  if (backend) return backend;
  const heartbeatAt = Number(job?.heartbeat_at || job?.updated_at || job?.started_at || 0);
  const progressAt = Number(job?.last_progress_at || job?.updated_at || job?.started_at || 0);
  const now = Date.now() / 1000;
  const heartbeatAge = heartbeatAt > 0 ? Math.max(0, Math.floor(now - heartbeatAt)) : 0;
  const progressAge = progressAt > 0 ? Math.max(0, Math.floor(now - progressAt)) : 0;
  const running = Boolean(job?.running);
  const state = !running ? "terminal" : heartbeatAge > 15 ? "stalled" : progressAge > 45 ? "waiting_external" : "active";
  return {
    state,
    label: state === "stalled" ? "后台心跳中断，任务可能已卡住" : state === "waiting_external" ? "后台在线，正在等待外部服务返回" : "后台运行正常",
    heartbeat_age_seconds: heartbeatAge,
    progress_age_seconds: progressAge,
  };
}

function productionProtectionLabel(job) {
  const retryLimit = Number(job?.auto_retry_limit ?? 2);
  const stability = state.projectStatus?.metrics?.production_stability;
  const historyLabel = Number(stability?.sample_count || 0) > 0 ? stability.label : "稳定性数据积累中";
  if (job?.auto_recover === false || retryLimit <= 0) return `手动诊断模式 · 已完成素材仍会保留 · ${historyLabel}`;
  return `全自动保障 · 瞬时错误自动重试 ${retryLimit} 次 · 已完成素材不重做 · ${historyLabel}`;
}

function productionBudgetSnapshot(job) {
  const firstPositive = (...values) => {
    const found = values.map((value) => Number(value)).find((value) => Number.isFinite(value) && value > 0);
    return found ? Math.round(found) : 0;
  };
  const projectSettings = state.currentContent?.project_settings || {};
  const fixedMode = els.sceneCountMode?.value === "fixed" || projectSettings.scene_count_mode === "fixed";
  const fixedCount = fixedMode
    ? Number(els.sceneCountFixed?.value || projectSettings.scene_count_fixed || 0)
    : 0;
  const sceneExpected = firstPositive(
    state.imageReview?.scene_expected,
    state.sceneStatus?.expected_count,
    state.currentContent?.summary?.scene_count,
    fixedCount,
    6,
  );
  const sceneGenerated = Math.max(0, Number(
    state.imageReview?.scene_generated
      ?? state.sceneStatus?.generated_count
      ?? state.sceneStatus?.existing?.length
      ?? 0,
  ) || 0);
  const covers = state.currentFiles ? coverRecords(state.currentFiles) : [];
  const coverEnabled = coverGenerationEnabled();
  const coverExpected = coverEnabled ? firstPositive(state.imageReview?.cover_expected, covers.length, 3) : 0;
  const coverGenerated = Math.max(0, Number(
    state.imageReview?.cover_generated
      ?? covers.filter((item) => item?.image).length
      ?? 0,
  ) || 0);
  const jobStatus = String(job?.status || "");
  const preserveJobPlan = Boolean(job?.running) || ["failed", "interrupted", "cancelled"].includes(jobStatus);
  const jobSteps = Array.isArray(job?.steps) ? job.steps.map((item) => String(item || "")).filter(Boolean) : [];
  const steps = preserveJobPlan && jobSteps.length ? jobSteps : stepValues();
  const stepSet = new Set(steps);
  const sceneCalls = stepSet.has("images")
    ? sceneExpected
    : stepSet.has("images_missing")
      ? Math.max(0, sceneExpected - sceneGenerated)
      : 0;
  const coverCalls = !coverEnabled
    ? 0
    : stepSet.has("covers")
    ? (coverExpected > 0 ? 1 : 0)
    : stepSet.has("covers_missing")
      ? (coverExpected > 0 && coverGenerated === 0 ? 1 : 0)
      : 0;
  const keyCandidateExtra = stepSet.has("images") && sceneCalls > 0 ? 1 : 0;
  const imageCalls = sceneCalls + coverCalls + keyCandidateExtra;
  const formula = [];
  if (sceneCalls) formula.push(`场景 ${sceneCalls}`);
  if (stepSet.has("images") && sceneCalls) formula.push("首镜备选 1");
  if (coverCalls) formula.push("主封面 1（其它比例本地适配）");
  return {
    sceneExpected,
    sceneGenerated,
    coverExpected,
    coverGenerated,
    coverEnabled,
    keyCandidateExtra,
    imageCalls,
    title: imageCalls
      ? `${sceneCalls + coverCalls} 张正式图 + ${keyCandidateExtra} 张关键位备选`
      : "本轮不新增图片",
    detail: formula.length
      ? `${formula.join(" + ")} = 预计 ${imageCalls} 次生图调用；普通镜头保持单图。`
      : "当前勾选步骤只处理已有素材；需要出图时再勾选场景图或封面步骤。",
  };
}

function productionDeliverableComplete() {
  const manifestCurrent = String(state.productionManifest?.overall_status || "") === "current";
  const finalVideo = state.currentFiles?.artifacts?.final_video || null;
  const videoAsset = (Array.isArray(state.productionManifest?.assets) ? state.productionManifest.assets : [])
    .find((item) => String(item?.key || "") === "video");
  const videoStep = (Array.isArray(state.projectStatus?.steps) ? state.projectStatus.steps : [])
    .find((item) => String(item?.key || "") === "video");
  return Boolean(
    manifestCurrent
    && finalVideo
    && String(videoAsset?.status || "") === "current"
    && state.projectStatus?.final_video_stale === false
    && String(videoStep?.status || "") === "ok"
  );
}

function productionOverallProgress(job) {
  if (productionDeliverableComplete() || job?.status === "succeeded") return 100;
  const jobSteps = Array.isArray(job?.steps) ? job.steps.map((item) => String(item || "")).filter(Boolean) : [];
  const progressItems = Array.isArray(job?.progress) ? job.progress : [];
  if (jobSteps.length && progressItems.length) {
    const latestByKey = new Map();
    progressItems.forEach((item) => latestByKey.set(String(item?.key || ""), item));
    const doneStatuses = new Set(["success", "passed", "accepted_with_warnings"]);
    let completed = 0;
    jobSteps.forEach((key) => {
      const item = latestByKey.get(key);
      if (doneStatuses.has(String(item?.status || ""))) {
        completed += 1;
        return;
      }
      if (["queued", "running"].includes(String(item?.status || ""))) {
        const percent = Number(item?.percent);
        if (Number.isFinite(percent)) completed += Math.max(0, Math.min(100, percent)) / 100;
      }
    });
    const percent = Math.round(completed * 100 / jobSteps.length);
    return job?.running ? Math.min(99, percent) : Math.max(0, Math.min(100, percent));
  }
  const assets = Array.isArray(state.productionManifest?.assets) ? state.productionManifest.assets : [];
  if (!assets.length) return 0;
  const completed = assets.filter((item) => item?.status === "current").length;
  return Math.round(completed * 100 / assets.length);
}

function productionRuntimeSnapshot(job) {
  const progressItems = Array.isArray(job?.progress) ? job.progress : [];
  const activeProgress = [...progressItems]
    .reverse()
    .find((item) => ["queued", "running"].includes(String(item?.status || "")));
  const action = String(els.taskCommandPrimary?.dataset.taskCommandAction || "produce");
  const status = String(els.taskCommandStatus?.textContent || "空闲");
  const title = String(els.taskCommandTitle?.textContent || "可以开始下一步");
  const detail = String(els.taskCommandDetail?.textContent || "选择生产步骤后即可启动。");
  const actionLabel = String(els.taskCommandPrimary?.textContent || "进入生产");
  const deliverableComplete = productionDeliverableComplete();
  const running = Boolean(job?.running) && !deliverableComplete;
  const health = jobRuntimeHealth(job);
  const phase = String(activeProgress?.phase || "");
  const stepKey = String(activeProgress?.key || job?.current_step || "");
  const startedAt = Number(job?.started_at || activeProgress?.started_at || 0);
  const finishedAt = Number(job?.finished_at || 0);
  const elapsedSeconds = startedAt > 0
    ? Math.max(0, (finishedAt > 0 ? finishedAt : Date.now() / 1000) - startedAt)
    : 0;
  const etaSeconds = Number(activeProgress?.eta_seconds);
  const failed = !deliverableComplete && ["failed", "cancelled", "interrupted"].includes(String(job?.status || ""));
  let kind = "idle";
  let kindLabel = "等待启动";
  if (deliverableComplete) {
    kind = "done";
    kindLabel = "成片交付完成";
  } else if (state.jobPollFailures >= 2) {
    kind = "failed";
    kindLabel = "等待重新连接";
  } else if (running) {
    if (phase === "auto_retry" || Number(activeProgress?.auto_retry_count || 0) > 0) {
      kind = "retrying";
      kindLabel = "正在自动重试";
    } else if (health.state === "stalled") {
      kind = "stalled";
      kindLabel = "后台心跳异常";
    } else if (health.state === "waiting_external") {
      kind = "external";
      kindLabel = "等待外部服务";
    } else if (stepKey === "video") {
      kind = "active";
      kindLabel = "本机正在合成";
    } else if (["audio", "subtitles", "bgm", "motion_clips"].includes(stepKey)) {
      kind = "active";
      kindLabel = "媒体处理中";
    } else {
      kind = "ai";
      kindLabel = "AI 正在处理";
    }
  } else if (["candidates", "confirm-images"].includes(action)) {
    kind = "human";
    kindLabel = "等待人工确认";
  } else if (action === "gate") {
    kind = "human";
    kindLabel = "等待启动修复";
  } else if (["retry", "reconnect"].includes(action) || failed) {
    kind = "failed";
    kindLabel = action === "reconnect" ? "等待重新连接" : "等待恢复生产";
  } else if (job?.status === "succeeded") {
    kind = "done";
    kindLabel = "本轮生产完成";
  }

  const humanActions = new Set(["candidates", "confirm-images", "gate", "retry", "reconnect"]);
  const humanLabel = running ? "当前无需" : humanActions.has(action) ? "需要处理" : action === "produce" ? "可启动" : "当前无需";
  let etaLabel = "待启动";
  if (running && Number.isFinite(etaSeconds) && etaSeconds > 0) {
    etaLabel = formatTaskElapsed(etaSeconds);
  } else if (running && health.state === "waiting_external") {
    etaLabel = "等待服务返回";
  } else if (running) {
    etaLabel = "动态估算中";
  } else if (deliverableComplete || job?.status === "succeeded") {
    etaLabel = "已完成";
  }

  let next = actionLabel;
  if (running) {
    const jobSteps = Array.isArray(job?.steps) ? job.steps.map((item) => String(item || "")).filter(Boolean) : [];
    const currentIndex = jobSteps.indexOf(stepKey);
    const nextKey = currentIndex >= 0 ? jobSteps[currentIndex + 1] : jobSteps[0];
    const nextDef = STEP_DEFS.find((item) => item.key === nextKey);
    next = nextDef ? `自动进入：${nextDef.label}` : "完成本轮并更新资产状态";
  }
  return {
    kind,
    kindLabel,
    status,
    title,
    detail,
    action,
    actionLabel,
    elapsedLabel: formatTaskElapsed(elapsedSeconds),
    etaLabel,
    progress: productionOverallProgress(job),
    humanLabel,
    next,
  };
}

function renderProductionCockpit() {
  if (!els.productionCockpit) return;
  const project = state.currentProject;
  const job = state.currentJob;
  const budget = project
    ? productionBudgetSnapshot(job)
    : {
        sceneExpected: 0,
        sceneGenerated: 0,
        coverExpected: 0,
        coverGenerated: 0,
        keyCandidateExtra: 0,
        imageCalls: 0,
        title: "选择项目后读取素材预算",
        detail: "预算会随勾选步骤和现有素材实时更新。",
      };
  const snapshot = project
    ? productionRuntimeSnapshot(job)
    : {
        kind: "idle",
        kindLabel: "等待项目",
        status: "空闲",
        title: "选择项目后开始生产",
        detail: "系统会在这里持续更新当前动作。",
        action: "produce",
        actionLabel: "进入生产",
        elapsedLabel: "0 秒",
        etaLabel: "待启动",
        progress: 0,
        humanLabel: "当前无需",
        next: "等待选择项目",
      };
  ["idle", "ai", "active", "external", "retrying", "human", "stalled", "failed", "done"].forEach((kind) => {
    els.productionCockpit.classList.remove(`production-cockpit--${kind}`);
  });
  els.productionCockpit.classList.add(`production-cockpit--${snapshot.kind}`);
  els.productionCockpitStatus.textContent = snapshot.status;
  els.productionCockpitStatus.className = project ? (els.taskCommandStatus?.className || "pill") : "pill";
  els.productionCockpitKind.textContent = snapshot.kindLabel;
  els.productionCockpitActionTitle.textContent = snapshot.title;
  els.productionCockpitActionDetail.textContent = snapshot.detail;
  els.productionCockpitElapsed.textContent = snapshot.elapsedLabel;
  els.productionCockpitEta.textContent = snapshot.etaLabel;
  els.productionCockpitProgress.textContent = `${snapshot.progress}%`;
  els.productionCockpitHuman.textContent = snapshot.humanLabel;
  els.productionCockpitBudgetTitle.textContent = budget.title;
  els.productionCockpitBudgetDetail.textContent = budget.detail;
  els.productionCockpitScenes.textContent = `${budget.sceneGenerated}/${budget.sceneExpected}`;
  els.productionCockpitCandidates.textContent = `${budget.keyCandidateExtra} 张`;
  els.productionCockpitCovers.textContent = budget.coverEnabled
    ? `${budget.coverGenerated}/${budget.coverExpected}`
    : "本期跳过";
  els.productionCockpitImageCalls.textContent = `${budget.imageCalls} 次`;
  els.productionCockpitNext.textContent = snapshot.next;
  els.productionCockpitAction.textContent = snapshot.actionLabel;
  els.productionCockpitAction.dataset.taskCommandProxy = snapshot.action;
  els.productionCockpitAction.disabled = !project;
}

function renderTaskCommandBar() {
  if (!els.taskCommandBar) return;
  if (!state.currentProject) {
    els.taskCommandBar.classList.add("hidden");
    renderProductionCockpit();
    return;
  }

  els.taskCommandBar.classList.remove("hidden");
  if (state.jobPollFailures >= 2) {
    els.taskCommandStatus.textContent = "连接中断";
    els.taskCommandStatus.className = "pill pill--risk";
    els.taskCommandTitle.textContent = "暂时没有收到后台最新状态";
    els.taskCommandDetail.textContent = "页面已停止使用旧进度冒充运行状态；重新连接后会继续读取后台真实任务。";
    els.taskCommandMeta.textContent = state.lastJobPollSuccessAt
      ? `最后成功刷新：${new Date(state.lastJobPollSuccessAt).toLocaleTimeString("zh-CN", { hour12: false })}`
      : "尚未收到任务状态";
    els.taskCommandPrimary.textContent = "重新连接";
    els.taskCommandPrimary.dataset.taskCommandAction = "reconnect";
    els.taskCommandPrimary.disabled = false;
    els.taskCommandCancel?.classList.add("hidden");
    els.taskCommandBar.classList.add("task-command-bar--attention");
    const meterTrack = els.taskCommandMeter?.parentElement;
    meterTrack?.classList.remove("is-indeterminate");
    if (els.taskCommandMeter) els.taskCommandMeter.style.width = "0%";
    renderProductionCockpit();
    return;
  }
  const job = state.currentJob;
  const progressItems = Array.isArray(job?.progress) ? job.progress : [];
  const activeProgress = [...progressItems]
    .reverse()
    .find((item) => ["queued", "running"].includes(String(item?.status || "")));
  const stepDef = STEP_DEFS.find((item) => item.key === (activeProgress?.key || job?.current_step));
  const candidateGroups = Array.isArray(state.sceneStatus?.candidate_groups) ? state.sceneStatus.candidate_groups : [];
  const candidatePending = Math.max(
    Number(state.imageReview?.scene_candidate_pending || 0),
    candidateGroups.filter((item) => item?.selection_pending).length
  ) + Number(state.imageReview?.cover_candidate_pending || 0);
  const reviewRequired = state.imageReview?.required !== false;
  const reviewConfirmed = Boolean(state.imageReview?.confirmed);
  const reviewReady = Boolean(state.imageReview?.ready_to_confirm);
  const hasReviewData = Boolean(state.imageReview);
  const finalVideo = state.currentFiles?.artifacts?.final_video || null;
  const manifestAssets = Array.isArray(state.productionManifest?.assets) ? state.productionManifest.assets : [];
  const videoManifest = manifestAssets.find((item) => item?.key === "video") || null;
  const videoNeedsUpdate = Boolean(finalVideo && videoManifest && videoManifest.status !== "current");
  const deliverableComplete = productionDeliverableComplete();
  const running = Boolean(job?.running) && !deliverableComplete;
  const failed = !deliverableComplete && ["failed", "cancelled", "interrupted"].includes(String(job?.status || ""));
  const retrySteps = deliverableComplete ? [] : retryableJobSteps(job);
  const gateReport = state.stageGates?.result || state.stageGates || {};
  const gates = Array.isArray(gateReport?.ordered_gates)
    ? gateReport.ordered_gates
    : Object.values(gateReport?.gates || {});
  const blockingGate = gates.find((gate) => {
    const gateStatus = String(gate?.status || "").toLowerCase();
    return gate && !gate.passed && ["failed", "needs_fix", "stale"].includes(gateStatus);
  }) || null;

  let status = "空闲";
  let tone = "";
  let title = "可以开始下一步";
  let detail = "选择生产步骤后即可启动；执行状态会持续显示在这里。";
  let meta = "尚未启动任务";
  let action = "produce";
  let actionLabel = "进入生产";
  let meter = 0;
  let indeterminate = false;

  if (deliverableComplete) {
    status = "已完成";
    tone = "pill--success";
    title = "成片与全部生产资产已完成";
    detail = "已有成片有效，历史任务的停止记录不会覆盖当前交付状态。";
    meta = "最终视频已写入成片目录 · 无需重复生成";
    action = "files";
    actionLabel = "查看成片";
    meter = 100;
  } else if (running) {
    const health = jobRuntimeHealth(job);
    const numericPercent = Number(activeProgress?.percent);
    const hasPercent = Number.isFinite(numericPercent);
    const elapsedFromStep = activeProgress ? liveGateElapsed(activeProgress) : 0;
    const elapsedFromJob = Number.isFinite(Number(job?.started_at))
      ? Math.max(0, Date.now() / 1000 - Number(job.started_at))
      : 0;
    status = health.state === "stalled" ? "疑似卡住" : health.state === "waiting_external" ? "等待返回" : "运行中";
    tone = health.state === "stalled" ? "pill--risk" : health.state === "waiting_external" ? "pill--warn" : "pill--accent";
    title = stepDef?.label || activeProgress?.label || job?.current_step || "正在执行生产任务";
    detail = health.state === "stalled"
      ? "后台心跳已经中断。请先查看日志；确认无变化后可停止任务，再从当前步骤继续。"
      : String(activeProgress?.message || job?.phase_message || "后台正在处理当前步骤。").trim();
    const progressAge = Number(health.progress_age_seconds || 0);
    const healthMeta = health.state === "waiting_external"
      ? `后台在线 · ${formatTaskElapsed(progressAge)} 没有新结果`
      : health.label || jobHeartbeatLabel(job);
    meta = `已用 ${formatTaskElapsed(Math.max(elapsedFromStep, elapsedFromJob))} · ${healthMeta}`;
    action = "view-job";
    actionLabel = "查看任务";
    meter = hasPercent ? Math.max(0, Math.min(100, numericPercent)) : 36;
    indeterminate = !hasPercent;
  } else if (!failed && blockingGate) {
    const issues = Array.isArray(blockingGate.issues) ? blockingGate.issues : [];
    const firstIssue = issues[0] || {};
    const issueText = `${firstIssue?.where || ""} ${firstIssue?.issue || ""} ${firstIssue?.fix || ""}`.trim();
    status = "待修复";
    tone = "pill--warn";
    title = `当前唯一阻断：${blockingGate.label || blockingGate.key || "生产闸门"}`;
    detail = issueText || blockingGate.desc || "系统将先处理这一项，通过后继续原生产流程。";
    const canAcceptCurrentPrompt = Boolean(blockingGate);
    meta = canAcceptCurrentPrompt
      ? `当前 ${blockingGate.score ?? 0} 分 · 可直接跳过并继续原生产流程`
      : `当前 ${blockingGate.score ?? 0} 分 · 修复后自动复检`;
    action = canAcceptCurrentPrompt ? "gate-accept" : "gate";
    actionLabel = canAcceptCurrentPrompt ? "忽略本次并继续" : stageGateRepairLabel(blockingGate, issueText);
    meter = Math.max(8, Math.min(92, Number(blockingGate.score || 0)));
    els.taskCommandPrimary.dataset.taskCommandGateKey = String(blockingGate.key || "");
  } else if (!failed && reviewRequired && candidatePending > 0) {
    status = "待选择";
    tone = "pill--warn";
    title = `${candidatePending} 个关键位方案待选择`;
    detail = "重点比较封面/首镜对标题与首句的兑现程度；采用 A 或 B 都不会再次生图。";
    meta = reviewRequired ? "人工确认模式" : "切换全自动后由 AI 推荐直接采用";
    action = "candidates";
    actionLabel = "选择关键方案";
    meter = 72;
  } else if (!failed && reviewRequired && reviewReady && !reviewConfirmed) {
    status = "待确认";
    tone = "pill--warn";
    title = "图片已齐，等待整组确认";
    detail = "确认后才允许进入成片；此操作不会重新生成任何图片。";
    meta = `场景图 ${state.imageReview?.scene_generated || 0}/${state.imageReview?.scene_expected || 0} · 封面 ${state.imageReview?.cover_generated || 0}/${state.imageReview?.cover_expected || 0}`;
    action = "confirm-images";
    actionLabel = "确认当前图片";
    meter = 88;
  } else if (!failed && hasReviewData && reviewRequired && !reviewConfirmed && !reviewReady && job?.status === "succeeded") {
    status = "待补齐";
    tone = "pill--warn";
    title = "图片资产还没有齐全";
    detail = "先补缺失场景图或封面，完成后再确认；不会重做已经存在的图片。";
    meta = `场景图 ${state.imageReview?.scene_generated || 0}/${state.imageReview?.scene_expected || 0} · 封面 ${state.imageReview?.cover_generated || 0}/${state.imageReview?.cover_expected || 0}`;
    action = "produce";
    actionLabel = "查看缺失项";
    meter = 58;
  } else if (failed) {
    const recovery = job?.recovery && typeof job.recovery === "object" ? job.recovery : null;
    status = job.status === "cancelled" ? "已停止" : job.status === "interrupted" ? "已中断" : "失败";
    tone = "pill--risk";
    title = recovery?.automatic_retries_exhausted
      ? "自动重试已完成，等待按最新资产续跑"
      : (retrySteps.length ? "任务已停止，可从失败步骤继续" : "任务没有继续运行");
    detail = String(recovery?.action || job.error || job.phase_message || "查看任务日志可定位最后一个执行步骤。").trim();
    meta = jobHeartbeatLabel(job);
    action = retrySteps.length ? "retry" : "view-job";
    actionLabel = retrySteps.length ? "按资产状态继续" : "查看日志";
    const lastPercent = Number([...progressItems].reverse().find((item) => Number.isFinite(Number(item?.percent)))?.percent);
    meter = Number.isFinite(lastPercent) ? Math.max(0, Math.min(100, lastPercent)) : 0;
  } else if (job?.status === "succeeded") {
    status = "已完成";
    tone = videoNeedsUpdate ? "pill--warn" : "pill--success";
    title = videoNeedsUpdate
      ? "上游素材已更新，需要重新合成成片"
      : (finalVideo ? "本轮生产已完成，成片可查看" : "本轮生产步骤已完成");
    detail = videoNeedsUpdate
      ? "系统会复用现有配音、字幕和图片，只执行资产版本要求的续跑步骤。"
      : String(job.phase_message || "所选生产步骤已经执行完成。").trim();
    meta = videoNeedsUpdate
      ? "点击后立即读取续跑计划并启动"
      : (finalVideo ? "最终视频已写入成片目录" : "可继续选择下一组生产步骤");
    action = finalVideo && !videoNeedsUpdate ? "files" : "produce";
    actionLabel = videoNeedsUpdate ? "更新成片" : (finalVideo ? "查看成片" : "继续生产");
    meter = 100;
  }

  meta = [meta, productionProtectionLabel(job)].filter(Boolean).join(" · ");

  els.taskCommandStatus.textContent = status;
  els.taskCommandStatus.className = `pill ${tone}`.trim();
  els.taskCommandTitle.textContent = title;
  els.taskCommandDetail.textContent = detail;
  els.taskCommandMeta.textContent = meta;
  els.taskCommandPrimary.textContent = actionLabel;
  els.taskCommandPrimary.dataset.taskCommandAction = action;
  if (action !== "gate") delete els.taskCommandPrimary.dataset.taskCommandGateKey;
  els.taskCommandPrimary.disabled = false;
  els.taskCommandBar.classList.toggle("task-command-bar--attention", Boolean(!deliverableComplete && (failed || blockingGate)));
  const meterTrack = els.taskCommandMeter?.parentElement;
  meterTrack?.classList.toggle("is-indeterminate", indeterminate);
  if (els.taskCommandMeter) els.taskCommandMeter.style.width = `${meter}%`;
  els.taskCommandCancel?.classList.toggle("hidden", !running);
  renderProductionStageStrip();
  renderProductionCockpit();
}

function renderJob() {
  const job = state.currentJob;
  if (!job) {
    els.jobStatusPill.textContent = "暂无任务";
    els.jobLog.textContent = "暂无日志";
    els.jobLog.classList.remove("log-view--history");
    if (els.jobLogState) {
      els.jobLogState.className = "job-log-state hidden";
      els.jobLogState.innerHTML = "";
    }
    els.jobProgress.innerHTML = `<div class="muted">启动任务后，这里会显示每一个步骤的状态。</div>`;
    renderChatgptReloginButton();
    updateWorkflowButtons();
    renderTaskCommandBar();
    return;
  }
  const deliverableComplete = productionDeliverableComplete();
  const jobStatusLabels = {
    running: "运行中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已取消",
    interrupted: "已中断",
  };
  els.jobStatusPill.textContent = deliverableComplete ? "已完成" : (jobStatusLabels[job.status] || job.status || "运行中");
  els.jobStatusPill.className = `pill ${deliverableComplete ? "pill--success" : (["failed", "cancelled", "interrupted"].includes(job.status) ? "pill--warn" : "")}`;
  els.jobLog.textContent = job.log || "暂无日志";
  els.jobLog.classList.toggle("log-view--history", !job.running);
  els.productionLiveLogPanel?.classList.toggle("production-live-log-panel--running", Boolean(job.running) && !deliverableComplete);
  if (job.running && !deliverableComplete) {
    const distanceFromBottom = els.jobLog.scrollHeight - els.jobLog.scrollTop - els.jobLog.clientHeight;
    if (distanceFromBottom < 96) els.jobLog.scrollTop = els.jobLog.scrollHeight;
  }
  const retrySteps = retryableJobSteps(job);
  const activeProgress = [...(Array.isArray(job.progress) ? job.progress : [])]
    .reverse()
    .find((item) => ["queued", "running"].includes(String(item?.status || "")));
  const phaseMessage = String(activeProgress?.message || job.phase_message || "后台正在处理当前步骤。").trim();
  if (els.jobLogState) {
    const runtimeHealth = jobRuntimeHealth(job);
    let tone = "";
    let title = "任务正在运行";
    let detail = `${phaseMessage} · ${jobHeartbeatLabel(job)}`;
    let action = "";
    if (deliverableComplete) {
      tone = "job-log-state--done";
      title = "成片与全部生产资产已完成";
      detail = "下方日志属于历史任务记录；取消记录没有影响当前有效成片。";
    } else if (job.running && runtimeHealth.state === "stalled") {
      tone = "job-log-state--failed";
      title = "后台心跳中断，任务可能已卡住";
      detail = `${phaseMessage} · ${runtimeHealth.label || jobHeartbeatLabel(job)}。请查看最后日志；确认没有变化后停止并续跑。`;
    } else if (job.running && runtimeHealth.state === "waiting_external") {
      tone = "job-log-state--waiting";
      title = "后台在线，正在等待外部服务";
      detail = `${phaseMessage} · 已等待 ${formatTaskElapsed(Number(runtimeHealth.progress_age_seconds || 0))}，任务仍在运行。`;
    } else if (job.status === "interrupted") {
      tone = "job-log-state--stopped";
      title = "任务已停止，没有继续运行";
      detail = String(job.error || "服务重启打断了当前步骤，下面的倒计时只是历史日志。");
    } else if (job.status === "failed") {
      tone = "job-log-state--failed";
      title = "任务已失败，没有继续运行";
      detail = String(job.error || "当前步骤执行失败，请查看最后几行日志。");
    } else if (job.status === "cancelled") {
      tone = "job-log-state--stopped";
      title = "任务已取消";
      detail = "后台任务已经停止，下面显示的是历史日志。";
    } else if (job.status === "succeeded") {
      tone = "job-log-state--done";
      title = "任务已完成";
      detail = String(job.phase_message || "全部生产步骤已完成。");
    }
    els.jobLogState.className = `job-log-state ${tone}`.trim();
    els.jobLogState.innerHTML = `
      <div class="job-log-state__content">
        <strong>${escapeHtml(title)}</strong>
        <div class="job-log-state__meta">${escapeHtml(detail)}</div>
      </div>
      ${action}
    `;
  }
  const loginRequired = isChatgptLoginError(job.log || "");
  const progress = job.progress || [];
  const progressHtml = deliverableComplete
    ? `<div class="step-item"><div class="step-item__body"><strong>当前交付已完成</strong><div class="muted">成片与生产资产均为当前版本，历史任务进度仅保留在日志中。</div><div class="job-step-progress"><div class="job-step-progress__track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="100"><span style="width:100%"></span></div><strong>100%</strong></div></div></div>`
    : progress.length
    ? progress
        .map(
          (item) => {
            const stepDef = STEP_DEFS.find((definition) => definition.key === item.key);
            const label = item.label || stepDef?.label || item.key;
            const orphanedRunningStep = !job.running && ["queued", "running"].includes(item.status);
            const effectiveStatus = orphanedRunningStep
              ? (job.status === "cancelled" ? "cancelled" : job.status === "failed" ? "failed" : "interrupted")
              : item.status;
            const itemRunning = Boolean(job.running) && ["queued", "running"].includes(effectiveStatus);
            const elapsed = itemRunning ? formatTaskElapsed(liveGateElapsed(item)) : "";
            const phase = itemRunning
              ? (String(item.key || "").startsWith("gate:") ? stageGatePhaseLabel(item) : jobStepPhaseLabel(item))
              : "";
            const statusLabels = {
              queued: "排队中",
              running: "运行中",
              success: "已完成",
              failed: "失败",
              cancelled: "已取消",
              interrupted: "已中断",
              accepted_with_warnings: "带提醒通过",
            };
            const numericPercent = Number(item.percent);
            const hasPercent = itemRunning && Number.isFinite(numericPercent);
            const percent = hasPercent ? Math.max(0, Math.min(100, numericPercent)) : 0;
            const etaSeconds = Number(item.eta_seconds);
            const eta = hasPercent && Number.isFinite(etaSeconds) && etaSeconds > 0 ? `预计剩余 ${formatTaskElapsed(etaSeconds)}` : "";
            const meta = [statusLabels[effectiveStatus] || effectiveStatus, phase, elapsed ? `已用 ${elapsed}` : "", eta, item.score !== undefined ? `${item.score} 分` : "", item.effective_step ? `实际执行 ${item.effective_step}` : ""].filter(Boolean).join(" · ");
            const meterHtml = hasPercent
              ? `
                <div class="job-step-progress">
                  <div class="job-step-progress__track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(percent)}">
                    <span style="width:${percent.toFixed(1)}%"></span>
                  </div>
                  <strong>${Math.round(percent)}%</strong>
                </div>
              `
              : "";
            return `
            <div class="step-item">
              <div class="step-item__body">
                <strong>${escapeHtml(label)}</strong>
                <div class="muted">${escapeHtml(meta)}</div>
                ${(orphanedRunningStep ? "任务已停止，可重新运行当前步骤。" : item.message) ? `<div class="muted step-item__message">${escapeHtml(orphanedRunningStep ? "任务已停止，可重新运行当前步骤。" : item.message)}</div>` : ""}
                ${meterHtml}
              </div>
            </div>
          `;
          }
        )
        .join("")
    : `<div class="muted">任务已创建，但还没有进度。</div>`;
  const loginAssistHtml = loginRequired
    ? `
      <article class="file-callout file-callout--compact">
        <div>
          <strong>ChatGPT 生图需要重新登录</strong>
          <div class="muted" style="margin-top:6px;">检测到当前任务卡在 ChatGPT 登录态。点右侧按钮会打开可见浏览器，登录完成后回来重试当前图片即可。</div>
        </div>
        <div class="file-item__actions">
          <button class="btn btn--primary" data-chatgpt-relogin="true">重新登录 ChatGPT</button>
        </div>
      </article>
    `
    : "";
  const finalVideo = state.currentFiles?.artifacts?.final_video || null;
  const outputHtml = (deliverableComplete || job.status === "succeeded") && finalVideo
    ? `
      <article class="file-callout file-callout--compact job-output-callout">
        <div class="file-callout__content">
          <strong>最终成片已生成</strong>
          <div class="mono-path">${escapeHtml(finalVideo.absolute_path || "-")}</div>
        </div>
        <div class="file-item__actions">
          <button class="btn btn--ghost" data-open-project-file="releases/final-video.mp4">打开 mp4</button>
          <button class="btn btn--ghost" data-open-project-subpath="releases">打开成片目录</button>
        </div>
      </article>
    `
    : "";
  const retryButtonHtml = !deliverableComplete && retrySteps.length
    ? `<button class="btn btn--primary" data-retry-failed-job="${escapeHtml(retrySteps.join(","))}">按最新资产状态继续</button>`
    : "";
  const terminalNoticeHtml = !deliverableComplete && ["failed", "interrupted"].includes(job.status)
    ? `<div class="step-item"><div class="step-item__body"><strong>${job.status === "interrupted" ? "任务已中断" : "任务执行失败"}</strong><div class="muted">${escapeHtml(job.status === "failed" && job.error ? `失败原因：${job.error}` : "后台步骤已经停止。")}</div><div class="muted step-item__message">重新运行会保留已完成资产并继续补齐，不会继续假计时。</div>${retryButtonHtml}</div></div>`
    : "";
  els.jobProgress.innerHTML = terminalNoticeHtml + loginAssistHtml + progressHtml + outputHtml;
  renderChatgptReloginButton();
  renderVoiceStatus();
  renderBgmStatus();
  updateWorkflowButtons();
  renderTaskCommandBar();
}

function renderScenes() {
  const sceneStatus = state.sceneStatus;
  if (!sceneStatus) {
    els.sceneGrid.innerHTML = `<div class="muted">暂无场景图</div>`;
    els.sceneStatusPill.textContent = "未生成";
    renderTaskCommandBar();
    return;
  }
  const items = sceneStatus.existing || [];
  const missingItems = sceneStatus.missing_items || [];
  const generatedCount = sceneStatus.generated_count ?? items.length;
  const expectedCount = sceneStatus.expected_count ?? generatedCount;
  const hiddenVariants = sceneStatus.hidden_variants ?? 0;
  const extraCount = sceneStatus.extra_count ?? 0;
  const candidateGroups = Array.isArray(sceneStatus.candidate_groups) ? sceneStatus.candidate_groups : [];
  const candidateCount = Number(sceneStatus.candidate_count || 0);
  els.sceneStatusPill.textContent = sceneStatus.complete
    ? `已完成 ${generatedCount}/${expectedCount}${candidateCount ? ` · 候选 ${candidateCount}` : ""}`
    : `已生成 ${generatedCount}/${expectedCount}${candidateCount ? ` · 候选 ${candidateCount}` : ""}`;
  const hiddenTotal = Number(hiddenVariants || 0) + Number(extraCount || 0);
  const hintHtml = hiddenTotal
    ? `<div class="muted" style="grid-column:1 / -1;">已自动隐藏 ${hiddenTotal} 个旧占位/重复/超出计划的场景文件，仅展示可用于成片的场景图。</div>`
    : "";
  const candidateIndexes = new Set(candidateGroups.map((group) => Number(group.scene_index || 0)));
  const officialByIndex = new Map(items.map((item) => [Number(item.index || 0), item]));
  const standaloneItems = items.filter((item) => !candidateIndexes.has(Number(item.index || 0)));
  const standaloneMissingItems = missingItems.filter((item) => !candidateIndexes.has(Number(item.index || 0)));
  const existingHtml = standaloneItems.length ? standaloneItems.map(sceneCardHtml).join("") : "";
  const missingHtml = standaloneMissingItems.length ? standaloneMissingItems.map(missingSceneCardHtml).join("") : "";
  const candidateHtml = candidateGroups.length
    ? `
        <div class="scene-grid-heading">
          <strong>待审图片工作台</strong>
          <span class="muted">左侧始终是成片正在使用的正式图，右侧才是候选；采用或保留后候选会自动清理。</span>
        </div>
        ${candidateGroups.map((group) => sceneCandidateGroupHtml(group, officialByIndex.get(Number(group.scene_index || 0)))).join("")}
        ${standaloneItems.length || standaloneMissingItems.length ? `<div class="scene-grid-heading scene-grid-heading--official"><strong>其他正式场景图</strong><span class="muted">这些镜头当前没有待审候选。</span></div>` : ""}
      `
    : "";
  els.sceneGrid.innerHTML = `${hintHtml}${candidateHtml}${existingHtml}${missingHtml}` || `<div class="muted">还没有输出场景图。</div>`;
  renderTaskCommandBar();
}

function renderCovers(files) {
  if (!els.coverGrid || !els.coverStatusPill) return;
  const coverEnabled = coverGenerationEnabled();
  if (!files) {
    els.coverStatusPill.textContent = coverEnabled ? "未生成" : "本期已跳过";
    els.coverGrid.innerHTML = `<div class="muted">${coverEnabled ? "暂无封面" : "封面是可选项，本期生产链路已跳过；需要时仍可在这里手动生成。"}</div>`;
    return;
  }
  const covers = coverRecords(files);
  const generated = covers.filter((item) => item.image).length;
  const competition = state.imageReview?.cover_candidate;
  const competitionPending = Boolean(competition?.pending && competition?.candidate);
  els.coverStatusPill.textContent = !coverEnabled
    ? "本期已跳过"
    : competitionPending
    ? `已生成 ${generated}/${covers.length} · 封面 2 选 1`
    : generated
      ? `已生成 ${generated}/${covers.length}`
      : "未生成";
  const optionalNotice = !coverEnabled
    ? `<div class="notice notice--soft">本期自动生产已跳过封面；已有封面会保留，也可随时手动生成。</div>`
    : "";
  els.coverGrid.innerHTML = optionalNotice + (competitionPending
    ? `${coverCandidateComparisonHtml(files, competition)}${coverGalleryCardsHtml(files, ["story", "portrait"])}`
    : coverGalleryCardsHtml(files));
}

function renderFiles() {
  const files = state.currentFiles;
  if (!files) {
    renderCovers(null);
    els.fileList.innerHTML = `<div class="muted">暂无文件</div>`;
    updateWorkflowButtons();
    renderTaskCommandBar();
    return;
  }
  renderCovers(files);
  const items = [...(files.topics || []), ...(files.outputs || [])];
  const callout = artifactSummaryHtml(files);
  const coversHtml = coverPreviewHtml(files);
  if (!items.length) {
    els.fileList.innerHTML = [callout, coversHtml].filter(Boolean).join("") || `<div class="muted">项目里还没有产物。</div>`;
    updateWorkflowButtons();
    renderTaskCommandBar();
    return;
  }
  const fileItems = items
    .map(
      (item) => `
        <article class="file-item">
          <div>
            <strong>${escapeHtml(item.relative_path)}</strong>
            <div class="muted">${formatBytes(item.size)} · ${formatDate(item.modified_at)}</div>
            ${item.absolute_path ? `<div class="mono-path mono-path--sm">${escapeHtml(item.absolute_path)}</div>` : ""}
          </div>
          <div class="file-item__actions">
            <button class="btn btn--ghost" data-open-file="${escapeHtml(versionedProjectUrl(item))}">打开</button>
            <button class="btn btn--ghost" data-delete-file="${escapeHtml(item.relative_path)}">删除</button>
          </div>
        </article>
      `
    )
    .join("");
  els.fileList.innerHTML = [callout, coversHtml, fileItems].filter(Boolean).join("");
  updateWorkflowButtons();
  renderTaskCommandBar();
}

function numericInputValue(input) {
  if (!input) return null;
  const value = String(input.value || "").trim();
  if (!value) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function releaseMetricsPayloadFromFields() {
  return {
    impressions: numericInputValue(els.releaseImpressions),
    click_through_rate: numericInputValue(els.releaseClickThroughRate),
    views: numericInputValue(els.releaseViews),
    likes: numericInputValue(els.releaseLikes),
    comments: numericInputValue(els.releaseComments),
    shares: numericInputValue(els.releaseShares),
    favorites: numericInputValue(els.releaseFavorites),
    follows: numericInputValue(els.releaseFollows),
    two_second_retention_rate: numericInputValue(els.releaseTwoSecondRetention),
    five_second_retention_rate: numericInputValue(els.releaseFiveSecondRetention),
    average_watch_seconds: numericInputValue(els.releaseAverageWatchSeconds),
    completion_rate: numericInputValue(els.releaseCompletionRate),
    metrics_notes: "",
  };
}

function clearReleaseMetricFields() {
  [
    els.releaseImpressions,
    els.releaseClickThroughRate,
    els.releaseViews,
    els.releaseLikes,
    els.releaseComments,
    els.releaseShares,
    els.releaseFavorites,
    els.releaseFollows,
    els.releaseTwoSecondRetention,
    els.releaseFiveSecondRetention,
    els.releaseAverageWatchSeconds,
    els.releaseCompletionRate,
  ].forEach((field) => {
    if (field) field.value = "";
  });
}

function releaseMetricsSummary(item) {
  const metrics = item?.metrics || {};
  const impressions = Number(metrics.impressions || 0);
  const clickThroughRate = Number(metrics.click_through_rate || (impressions && Number(metrics.views || 0) ? (Number(metrics.views || 0) / impressions) * 100 : 0));
  const views = Number(metrics.views || 0);
  const likes = Number(metrics.likes || 0);
  const comments = Number(metrics.comments || 0);
  const shares = Number(metrics.shares || 0);
  const favorites = Number(metrics.favorites || 0);
  const follows = Number(metrics.follows || 0);
  const twoSecondRetention = Number(metrics.two_second_retention_rate || 0);
  const fiveSecondRetention = Number(metrics.five_second_retention_rate || 0);
  const averageWatchSeconds = Number(metrics.average_watch_seconds || 0);
  const completion = Number(metrics.completion_rate || 0);
  const engagement = likes + comments + shares + favorites;
  const engagementRate = views > 0 ? ((engagement / views) * 100).toFixed(2) : "0.00";
  return {
    impressions,
    clickThroughRate,
    views,
    likes,
    comments,
    shares,
    favorites,
    follows,
    twoSecondRetention,
    fiveSecondRetention,
    averageWatchSeconds,
    completion,
    engagement,
    engagementRate,
    notes: metrics.notes || "",
  };
}

function releaseGrowthStage(metrics) {
  if (metrics.twoSecondRetention && metrics.twoSecondRetention < 55) return "开场流失";
  if (metrics.fiveSecondRetention && metrics.fiveSecondRetention < 38) return "前段承接弱";
  if (metrics.completion && metrics.completion < 22) return "中后段流失";
  if (metrics.views && Number(metrics.engagementRate || 0) < 2) return "互动偏弱";
  if (metrics.views || metrics.twoSecondRetention || metrics.completion) return "表现健康";
  return "待回填";
}

function releaseMetricsInlineHtml(item) {
  const metrics = releaseMetricsSummary(item);
  const metricHistory = Array.isArray(item?.metrics_history) ? item.metrics_history : [];
  const latestHistory = metricHistory.length ? metricHistory[metricHistory.length - 1] : null;
  const previousHistory = metricHistory.length > 1 ? metricHistory[metricHistory.length - 2] : null;
  const viewsDelta = latestHistory && previousHistory
    ? Number(latestHistory.views || 0) - Number(previousHistory.views || 0)
    : 0;
  const engagementDelta = latestHistory && previousHistory
    ? ["likes", "comments", "shares", "favorites"].reduce(
        (sum, key) => sum + Number(latestHistory[key] || 0) - Number(previousHistory[key] || 0),
        0
      )
    : 0;
  const hasMetrics = metrics.views || metrics.likes || metrics.comments || metrics.shares || metrics.favorites
    || metrics.impressions || metrics.clickThroughRate || metrics.follows || metrics.twoSecondRetention || metrics.fiveSecondRetention
    || metrics.averageWatchSeconds || metrics.completion;
  if (!hasMetrics) {
    const syncMessage = item?.metrics_sync?.message || "暂无表现数据，发布后会尝试自动同步，也可手动回填。";
    return `<div class="muted">${escapeHtml(syncMessage)}</div>`;
  }
  const syncedAt = Number(item?.metrics?.synced_at || item?.metrics_sync?.synced_at || 0);
  const syncedLabel = syncedAt ? new Date(syncedAt * 1000).toLocaleString("zh-CN", { hour12: false }) : "";
  const performance = item?.performance || {};
  const dimensions = performance.dimension_scores || {};
  const playPotential = Number(dimensions.play_potential ?? performance.play_potential_score ?? 0);
  const completionPotential = Number(dimensions.completion_potential ?? performance.completion_potential_score ?? 0);
  const commentPotential = Number(dimensions.comment_potential ?? performance.comment_potential_score ?? 0);
  const growthStage = performance.growth_stage || releaseGrowthStage(metrics);
  let diagnosis = performance.diagnosis || "数据仍在积累";
  if (!performance.diagnosis) {
    if (playPotential >= 60 && completionPotential < 22) diagnosis = "选题有效，正文未兑现";
    else if (commentPotential >= 35 && completionPotential < 22) diagnosis = "有争议，留存不足";
    else if (completionPotential >= 30) diagnosis = "正文留存较健康";
  }
  return `
    <div class="toolbar toolbar--tight">
      <span class="pill ${growthStage === "表现健康" ? "pill--success" : "pill--warn"}">${escapeHtml(growthStage)}</span>
      <span class="pill">${escapeHtml(diagnosis)}</span>
    </div>
    <div class="summary-grid summary-grid--compact">
      <div class="summary-card"><strong>播放潜力</strong><span>${escapeHtml(playPotential.toFixed(1))}</span></div>
      <div class="summary-card"><strong>完播潜力</strong><span>${escapeHtml(completionPotential.toFixed(1))}</span></div>
      <div class="summary-card"><strong>评论潜力</strong><span>${escapeHtml(commentPotential.toFixed(1))}</span></div>
      <div class="summary-card"><strong>展现</strong><span>${escapeHtml(String(metrics.impressions || 0))}</span></div>
      <div class="summary-card"><strong>点击率</strong><span>${escapeHtml(Number(metrics.clickThroughRate || 0).toFixed(2))}%</span></div>
      <div class="summary-card"><strong>播放</strong><span>${escapeHtml(String(metrics.views))}</span></div>
      <div class="summary-card"><strong>互动</strong><span>${escapeHtml(String(metrics.engagement))}</span></div>
      <div class="summary-card"><strong>互动率</strong><span>${escapeHtml(metrics.engagementRate)}%</span></div>
      <div class="summary-card"><strong>2 秒留存</strong><span>${escapeHtml(String(metrics.twoSecondRetention || 0))}%</span></div>
      <div class="summary-card"><strong>5 秒留存</strong><span>${escapeHtml(String(metrics.fiveSecondRetention || 0))}%</span></div>
      <div class="summary-card"><strong>平均观看</strong><span>${escapeHtml(String(metrics.averageWatchSeconds || 0))}秒</span></div>
      <div class="summary-card"><strong>完播</strong><span>${escapeHtml(String(metrics.completion || 0))}%</span></div>
      <div class="summary-card"><strong>新增关注</strong><span>${escapeHtml(String(metrics.follows || 0))}</span></div>
    </div>
    ${viewsDelta > 0 || engagementDelta > 0 ? `<div class="muted">本轮增长：播放 +${escapeHtml(String(Math.max(0, viewsDelta)))} · 互动 +${escapeHtml(String(Math.max(0, engagementDelta)))}</div>` : ""}
    ${syncedLabel ? `<div class="muted">平台数据同步于 ${escapeHtml(syncedLabel)}</div>` : ""}
    ${metrics.notes ? `<div class="muted">反馈：${escapeHtml(metrics.notes)}</div>` : ""}
  `;
}

function renderReleases() {
  const items = [...(state.releaseLinks || [])].sort(
    (a, b) => Number(b.published_at || b.created_at || 0) - Number(a.published_at || a.created_at || 0)
  );
  if (!items.length) {
    els.releaseList.innerHTML = `<div class="muted">暂无投放链接</div>`;
    return;
  }
  els.releaseList.innerHTML = items
    .map(
      (item) => `
        <article class="release-item">
          <h4>${escapeHtml(item.platform)}</h4>
          <p><a class="link-btn" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.url)}</a></p>
          <p>${escapeHtml(item.note || "无备注")}</p>
          ${releaseMetricsInlineHtml(item)}
          <div class="release-item__actions">
            <button class="btn btn--ghost" data-edit-release-metrics="${item.id}">回填数据</button>
            <button class="btn btn--ghost" data-delete-release="${item.id}">删除</button>
          </div>
        </article>
      `
    )
    .join("");
}

function compactMetric(value) {
  const number = Number(value || 0);
  if (number >= 100000000) return `${(number / 100000000).toFixed(number >= 1000000000 ? 0 : 1)}亿`;
  if (number >= 10000) return `${(number / 10000).toFixed(number >= 100000 ? 0 : 1)}万`;
  return String(Math.max(0, Math.round(number)));
}

function channelStrategyHtml(strategy = {}) {
  const observationMetrics = Array.isArray(strategy.observation_metrics) ? strategy.observation_metrics : [];
  return strategy.current_problem ? `
    <section class="channel-strategy-card" aria-label="频道级运营结论">
      <div class="channel-strategy-card__head">
        <div><span>真实数据反哺下一期</span><strong>频道当前结论</strong></div>
        <span class="pill">${escapeHtml(String(strategy.sample_count || 0))} 个样本</span>
      </div>
      <div class="channel-strategy-card__grid">
        <div><small>当前最大问题</small><strong>${escapeHtml(strategy.current_problem)}</strong></div>
        <div><small>已验证能力</small><strong>${escapeHtml(strategy.proven_strength || "仍在积累")}</strong></div>
        <div><small>下一期实验</small><strong>${escapeHtml(strategy.next_experiment || "建立频道基线")}</strong></div>
        <div><small>观察指标</small><strong>${observationMetrics.map((item) => escapeHtml(item)).join(" · ") || "2 秒留存 · 5 秒留存 · 完播率"}</strong></div>
      </div>
    </section>` : "";
}

function renderReleasePlatformStats() {
  if (!els.releasePlatformStats) return;
  const stats = state.releasePlatformStats || {};
  const accounts = Array.isArray(stats.accounts) ? stats.accounts : [];
  const strategyHtml = channelStrategyHtml(stats.channel_strategy || {});
  if (!accounts.length) {
    els.releasePlatformStats.innerHTML = strategyHtml + `
      <article class="platform-stat-card platform-stat-card--empty">
        <strong>还没有平台数据</strong>
        <span class="muted">点击“同步平台数据”，这里会按账号展示作品、播放、互动和完播表现。</span>
      </article>`;
    return;
  }

  const accountSnapshots = accounts.map((account) => {
    const works = Array.isArray(account.items) ? account.items : [];
    const totals = works.reduce((sum, item) => ({
      views: sum.views + Number(item.play_count || 0),
      likes: sum.likes + Number(item.like_count || 0),
      comments: sum.comments + Number(item.comment_count || 0),
      shares: sum.shares + Number(item.share_count || 0),
      favorites: sum.favorites + Number(item.collect_count || 0),
    }), { views: 0, likes: 0, comments: 0, shares: 0, favorites: 0 });
    return { account, works, totals };
  });
  const overview = accountSnapshots.reduce((sum, snapshot) => ({
    works: sum.works + snapshot.works.length,
    views: sum.views + snapshot.totals.views,
    likes: sum.likes + snapshot.totals.likes,
    comments: sum.comments + snapshot.totals.comments,
    interactions: sum.interactions + snapshot.totals.likes + snapshot.totals.comments + snapshot.totals.shares + snapshot.totals.favorites,
  }), { works: 0, views: 0, likes: 0, comments: 0, interactions: 0 });

  const overviewHtml = `
    <section class="platform-data-overview" aria-label="全平台数据概览">
      <div><span>账号</span><strong>${compactMetric(accounts.length)}</strong></div>
      <div><span>作品</span><strong>${compactMetric(overview.works)}</strong></div>
      <div><span>总播放</span><strong>${compactMetric(overview.views)}</strong></div>
      <div><span>总互动</span><strong>${compactMetric(overview.interactions)}</strong></div>
      <div><span>总评论</span><strong>${compactMetric(overview.comments)}</strong></div>
    </section>`;

  const accountHtml = accountSnapshots.map(({ account, works, totals }) => {
    const workRows = works.slice(0, 8).map((item) => {
      const performance = item.performance || {};
      const dimensions = performance.dimension_scores || {};
      const playPotential = Number(dimensions.play_potential ?? performance.play_potential_score ?? 0);
      const completionPotential = Number(dimensions.completion_potential ?? performance.completion_potential_score ?? 0);
      const commentPotential = Number(dimensions.comment_potential ?? performance.comment_potential_score ?? 0);
      const diagnosis = performance.diagnosis || "数据仍在积累";
      return `
      <div class="platform-work-row">
        <div class="platform-work-copy">
          <strong title="${escapeHtml(item.title || item.item_id || "未命名作品")}">${escapeHtml(item.title || item.item_id || "未命名作品")}</strong>
          <span class="muted">${escapeHtml(item.published_at || item.status || "")}</span>
          <div class="platform-work-diagnosis">
            <span class="pill ${diagnosis === "正文留存较健康" ? "pill--success" : diagnosis === "数据仍在积累" ? "" : "pill--warn"}">${escapeHtml(diagnosis)}</span>
          </div>
        </div>
        <div class="platform-work-scoreboard" aria-label="三维作品诊断">
          <span><b>${escapeHtml(playPotential.toFixed(1))}</b><small>播放潜力</small></span>
          <span><b>${escapeHtml(completionPotential.toFixed(1))}</b><small>完播潜力</small></span>
          <span><b>${escapeHtml(commentPotential.toFixed(1))}</b><small>评论潜力</small></span>
        </div>
        <div class="platform-work-metrics">
          <span><b>${compactMetric(item.play_count)}</b><small>播放</small></span>
          <span><b>${compactMetric(item.like_count)}</b><small>点赞</small></span>
          <span><b>${compactMetric(item.comment_count)}</b><small>评论</small></span>
          <span><b>${Number(item.completion_rate || 0) ? `${escapeHtml(String(Number(item.completion_rate).toFixed(1)))}%` : "—"}</b><small>完播</small></span>
        </div>
      </div>`;
    }).join("");
    return `
      <article class="platform-stat-card ${account.status === "failed" ? "platform-stat-card--error" : ""}">
        <div class="platform-stat-head">
          <div>
            <strong>${escapeHtml(account.platform_label || account.platform || "平台")}</strong>
            <div class="muted">${escapeHtml(account.account_display_name || account.account_name || "default")}</div>
          </div>
          <span class="pill ${account.status === "succeeded" ? "pill--success" : "pill--danger"}">${account.status === "succeeded" ? `${works.length} 条作品` : "同步失败"}</span>
        </div>
        ${account.status === "failed" ? `<div class="file-callout file-callout--compact">${escapeHtml(account.message || "账号数据同步失败")}</div>` : `
          <div class="platform-stat-totals">
            <span><b>${compactMetric(totals.views)}</b>播放</span>
            <span><b>${compactMetric(totals.likes)}</b>点赞</span>
            <span><b>${compactMetric(totals.comments)}</b>评论</span>
            <span><b>${compactMetric(totals.shares + totals.favorites)}</b>转藏</span>
          </div>
          <div class="platform-work-list">${workRows || '<div class="platform-work-empty"><strong>这个账号暂时没有作品数据</strong><span class="muted">账号同步正常，平台本次返回 0 条作品。</span></div>'}</div>`}
      </article>`;
  }).join("");

  els.releasePlatformStats.innerHTML = strategyHtml + overviewHtml + accountHtml;
}

function releaseMetricsPlatformName(platform) {
  const key = String(platform || "").toLowerCase();
  return { douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书", bilibili: "B站" }[key] || platform || "平台";
}

function renderReleaseMetricsSyncStatus() {
  if (!els.releaseMetricsSyncStatus) return;
  const sync = state.releaseMetricsSync || {};
  const accounts = Array.isArray(sync.accounts) ? sync.accounts : [];
  const completed = Number(sync.completed_accounts || 0);
  const total = Number(sync.total_accounts || 0);
  const percent = sync.running
    ? Math.max(0, Math.min(100, total ? Math.round(completed * 100 / total) : Number(sync.percent || 0)))
    : Number(sync.percent || 0);
  const autoCount = (state.releaseLinks || []).filter((item) => item?.item_id || item?.aweme_id || item?.metrics_sync?.status === "succeeded").length;
  const latestSync = (state.releaseLinks || [])
    .map((item) => Number(item?.metrics?.synced_at || item?.metrics_sync?.synced_at || 0))
    .filter(Boolean)
    .sort((a, b) => b - a)[0] || 0;
  const syncFinishedAt = Number(sync.finished_at || sync.updated_at || 0);
  const lastSyncAt = Math.max(latestSync, syncFinishedAt);
  const lastLabel = lastSyncAt ? new Date(lastSyncAt * 1000).toLocaleString("zh-CN", { hour12: false }) : "尚未同步";
  const failed = sync.status === "failed" || sync.status === "interrupted";
  const title = sync.running
    ? (sync.current_account_display_name
      ? `正在同步${releaseMetricsPlatformName(sync.current_platform)} · ${sync.current_account_display_name}`
      : "正在读取平台表现")
    : failed
      ? "平台数据同步未完成"
      : sync.status === "succeeded"
        ? "平台数据同步完成"
        : autoCount
          ? `已识别 ${autoCount} 条自动发布记录`
          : "等待可归因的发布记录";
  const succeededCount = accounts.filter((account) => String(account?.status || "") === "succeeded").length;
  const message = sync.status === "succeeded"
    ? `${succeededCount || completed || total} 个账号同步成功 · ${lastLabel}`
    : (sync.message || `最近同步：${lastLabel}。系统按作品 ID 归因，原有留存率和人工备注会继续保留。`);
  const accountRows = accounts.length ? `
    <details class="release-sync-details" ${sync.running || failed ? "open" : ""}>
      <summary>查看同步详情</summary>
      <div class="release-sync-accounts">
        ${accounts.map((account) => {
          const status = String(account?.status || "waiting");
          const statusLabel = { waiting: "等待中", running: "正在读取", succeeded: "已完成", failed: "失败" }[status] || status;
          const tone = status === "succeeded" ? "pill--success" : status === "failed" ? "pill--danger" : status === "running" ? "pill--accent" : "";
          return `<div class="release-sync-account">
            <span>${escapeHtml(account.platform_label || releaseMetricsPlatformName(account.platform))} · ${escapeHtml(account.account_display_name || account.account_name || "default")}</span>
            <span class="pill ${tone}">${escapeHtml(statusLabel)}</span>
            <small class="muted">${escapeHtml(account.message || "")}</small>
          </div>`;
        }).join("")}
      </div>
    </details>` : "";
  const progressHtml = sync.running || failed ? `
    <div class="release-sync-progress">
      <div class="release-sync-progress__meta"><span>账号进度</span><strong>${completed}/${total}</strong></div>
      <div class="release-sync-progress__track"><span style="width:${percent}%"></span></div>
    </div>` : "";
  els.releaseMetricsSyncStatus.innerHTML = `
    <div class="release-sync-status__body">
      <strong>${escapeHtml(title)}</strong>
      <div class="muted">${escapeHtml(message)}</div>
      ${progressHtml}
      ${accountRows}
    </div>
    <span class="pill ${sync.running ? "pill--accent" : failed ? "pill--danger" : sync.status === "succeeded" || autoCount ? "pill--success" : ""}">${sync.running ? "同步中" : failed ? "需处理" : "自动归因"}</span>
  `;
}

function setReleaseMetricsSyncButton(running) {
  if (!els.syncReleaseMetricsBtn) return;
  els.syncReleaseMetricsBtn.disabled = Boolean(running);
  els.syncReleaseMetricsBtn.textContent = running ? "同步中…" : "同步平台数据";
}

async function refreshReleaseMetricsSyncStatus({ poll = false, silent = true } = {}) {
  const project = ensureProject();
  if (!project) return null;
  const projectId = project.id;
  let lastStatus = null;
  do {
    const payload = await api(`/api/projects/${projectId}/releases/sync-metrics/status`);
    if (state.currentProject?.id !== projectId) return payload;
    lastStatus = payload;
    state.releaseMetricsSync = {
      ...payload,
      projectId,
      lastAttemptAt: Number(state.releaseMetricsSync?.lastAttemptAt || Date.now()),
    };
    renderReleaseMetricsSyncStatus();
    setReleaseMetricsSyncButton(payload.running);
    if (!poll || !payload.running) break;
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  } while (state.currentProject?.id === projectId);

  if (lastStatus && !lastStatus.running && ["succeeded", "failed", "interrupted"].includes(lastStatus.status)) {
    [state.releaseLinks, state.releasePlatformStats] = await Promise.all([
      api(`/api/projects/${projectId}/releases`),
      api(`/api/projects/${projectId}/releases/platform-stats`),
    ]);
    if (state.currentProject?.id === projectId) {
      renderReleases();
      renderReleasePlatformStats();
      renderReleaseMetricsSyncStatus();
    }
    if (!silent && lastStatus.status === "failed") window.alert(lastStatus.message || "平台数据同步未完成。");
  }
  return lastStatus;
}

async function syncReleaseMetrics({ silent = false, platform = "" } = {}) {
  const project = ensureProject();
  if (!project) return null;
  if (state.releaseMetricsSync?.running) return refreshReleaseMetricsSyncStatus({ poll: true, silent });
  state.releaseMetricsSync = {
    projectId: project.id,
    status: "queued",
    stage: "queued",
    running: true,
    lastAttemptAt: Date.now(),
    message: "同步任务已提交，正在准备账号列表…",
    accounts: [],
    completed_accounts: 0,
    total_accounts: 0,
  };
  renderReleaseMetricsSyncStatus();
  setReleaseMetricsSyncButton(true);
  try {
    const payload = await api(`/api/projects/${project.id}/releases/sync-metrics`, {
      method: "POST",
      body: JSON.stringify({ account_name: "", platform, limit: 10 }),
    });
    state.releaseMetricsSync = { ...payload, projectId: project.id, lastAttemptAt: Date.now() };
    renderReleaseMetricsSyncStatus();
    setReleaseMetricsSyncButton(payload.running);
    return await refreshReleaseMetricsSyncStatus({ poll: Boolean(payload.running), silent });
  } catch (error) {
    state.releaseMetricsSync = {
      projectId: project.id,
      status: "failed",
      running: false,
      lastAttemptAt: Date.now(),
      message: error.message || "本次平台数据同步未完成。",
    };
    renderReleaseMetricsSyncStatus();
    setReleaseMetricsSyncButton(false);
    if (!silent) window.alert(state.releaseMetricsSync.message);
    return null;
  }
}

function openReleaseMetricsModal(releaseId) {
  const item = (state.releaseLinks || []).find((entry) => Number(entry.id) === Number(releaseId));
  if (!item) return window.alert("没有找到这条投放链接。");
  const metrics = item.metrics || {};
  showModal(
    `回填投放数据 · ${item.platform || ""}`,
    `
      <div class="stack">
        <div class="card card--inner">
          <div class="muted">${escapeHtml(item.url || "")}</div>
          <div>${escapeHtml(item.note || "")}</div>
        </div>
        <div class="form-grid">
          <label>
            <span>展现量</span>
            <input id="modal-release-impressions" type="number" min="0" value="${escapeHtml(String(metrics.impressions || ""))}" />
          </label>
          <label>
            <span>点击率 %</span>
            <input id="modal-release-click-through-rate" type="number" min="0" max="100" step="0.1" value="${escapeHtml(String(metrics.click_through_rate || ""))}" placeholder="没有可留空" />
          </label>
          <label>
            <span>播放</span>
            <input id="modal-release-views" type="number" min="0" value="${escapeHtml(String(metrics.views || ""))}" />
          </label>
          <label>
            <span>点赞</span>
            <input id="modal-release-likes" type="number" min="0" value="${escapeHtml(String(metrics.likes || ""))}" />
          </label>
          <label>
            <span>评论</span>
            <input id="modal-release-comments" type="number" min="0" value="${escapeHtml(String(metrics.comments || ""))}" />
          </label>
          <label>
            <span>转发</span>
            <input id="modal-release-shares" type="number" min="0" value="${escapeHtml(String(metrics.shares || ""))}" />
          </label>
          <label>
            <span>收藏</span>
            <input id="modal-release-favorites" type="number" min="0" value="${escapeHtml(String(metrics.favorites || ""))}" />
          </label>
          <label>
            <span>新增关注</span>
            <input id="modal-release-follows" type="number" min="0" value="${escapeHtml(String(metrics.follows || ""))}" />
          </label>
          <label>
            <span>2 秒留存 %</span>
            <input id="modal-release-two-second" type="number" min="0" max="100" step="0.1" value="${escapeHtml(String(metrics.two_second_retention_rate || ""))}" />
          </label>
          <label>
            <span>5 秒留存 %</span>
            <input id="modal-release-five-second" type="number" min="0" max="100" step="0.1" value="${escapeHtml(String(metrics.five_second_retention_rate || ""))}" />
          </label>
          <label>
            <span>平均观看 秒</span>
            <input id="modal-release-average-watch" type="number" min="0" step="0.1" value="${escapeHtml(String(metrics.average_watch_seconds || ""))}" />
          </label>
          <label>
            <span>完播率 %</span>
            <input id="modal-release-completion" type="number" min="0" max="100" step="0.1" value="${escapeHtml(String(metrics.completion_rate || ""))}" />
          </label>
          <label class="form-grid__wide">
            <span>复盘备注</span>
            <input id="modal-release-notes" type="text" value="${escapeHtml(metrics.notes || "")}" placeholder="例如：开头留存好，评论集中问价格" />
          </label>
        </div>
        <div class="toolbar">
          <button id="modal-release-metrics-save" class="btn btn--primary">保存回填</button>
          <button class="btn btn--ghost" data-close-modal="true">取消</button>
        </div>
      </div>
    `,
    (body) => {
      body.querySelector("#modal-release-metrics-save")?.addEventListener("click", async () => {
        const project = ensureProject();
        if (!project) return;
        const payload = {
          impressions: Number(body.querySelector("#modal-release-impressions")?.value || 0),
          click_through_rate: Number(body.querySelector("#modal-release-click-through-rate")?.value || 0),
          views: Number(body.querySelector("#modal-release-views")?.value || 0),
          likes: Number(body.querySelector("#modal-release-likes")?.value || 0),
          comments: Number(body.querySelector("#modal-release-comments")?.value || 0),
          shares: Number(body.querySelector("#modal-release-shares")?.value || 0),
          favorites: Number(body.querySelector("#modal-release-favorites")?.value || 0),
          follows: Number(body.querySelector("#modal-release-follows")?.value || 0),
          two_second_retention_rate: Number(body.querySelector("#modal-release-two-second")?.value || 0),
          five_second_retention_rate: Number(body.querySelector("#modal-release-five-second")?.value || 0),
          average_watch_seconds: Number(body.querySelector("#modal-release-average-watch")?.value || 0),
          completion_rate: Number(body.querySelector("#modal-release-completion")?.value || 0),
          notes: body.querySelector("#modal-release-notes")?.value?.trim() || "",
        };
        await api(`/api/projects/${project.id}/releases/${releaseId}/metrics`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        await refreshReleases();
        closeModal();
      });
    }
  );
}

function selectedReleaseBatchTargets() {
  if (!els.releaseBatchTargets) return [];
  return Array.from(els.releaseBatchTargets.querySelectorAll('input[data-release-target]:checked'))
    .map((input) => ({
      platform: input.dataset.platform || "",
      account_name: input.dataset.account || "default",
    }))
    .filter((item) => item.platform);
}

function renderReleaseBatchTargets() {
  if (!els.releaseBatchTargets) return;
  const catalog = state.releaseAccountCatalog || {};
  const platforms = Array.isArray(catalog.platforms) ? catalog.platforms : [];
  const accountsByPlatform = catalog.accounts || {};
  const previous = new Set(
    Array.from(els.releaseBatchTargets.querySelectorAll('input[data-release-target]:checked'))
      .map((input) => `${input.dataset.platform}:${input.dataset.account}`)
  );
  const draft = state.releaseAutomation?.draft || {};
  const rows = [];
  platforms
    .filter((platform) => platform.status === "ready" && platform.available !== false && (platform.capabilities || []).includes("video"))
    .forEach((platform) => {
      const accounts = Array.isArray(accountsByPlatform[platform.key]) ? accountsByPlatform[platform.key] : [];
      accounts.forEach((account) => {
        const alias = account.alias || "default";
        const identity = `${platform.key}:${alias}`;
        const checked = previous.has(identity) || (!previous.size && platform.key === draft.platform && alias === (draft.account_name || "default"));
        const nickname = account.display_name || alias;
        const sessionLabel = account.cookie_exists ? "已保存会话，发布前实时检测" : "尚未登录";
        rows.push(`
          <label class="release-target-option ${account.cookie_exists ? "" : "release-target-option--missing"}">
            <input type="checkbox" data-release-target data-platform="${escapeHtml(platform.key)}" data-account="${escapeHtml(alias)}" ${checked ? "checked" : ""} ${account.cookie_exists ? "" : "disabled"} />
            <span class="release-target-option__copy">
              <strong>${escapeHtml(platform.label || platform.key)} · ${escapeHtml(nickname)}</strong>
              <small>${escapeHtml(alias)} · ${escapeHtml(sessionLabel)}</small>
            </span>
          </label>
        `);
      });
    });
  els.releaseBatchTargets.innerHTML = rows.length ? rows.join("") : '<div class="muted">还没有可用的发布账号，请先在“当前操作平台”中登录账号。</div>';
}

function releaseAutomationFormPayload() {
  return {
    platform: els.releaseAutoPlatform?.value?.trim() || "douyin",
    account_name: els.releaseAutoAccount?.value?.trim() || "default",
    title: els.releaseAutoTitle?.value?.trim() || "",
    description: els.releaseAutoDescription?.value?.trim() || "",
    tags: els.releaseAutoTags?.value?.trim() || "",
    schedule: els.releaseAutoSchedule?.value?.trim() || "",
    headed: (els.releaseAutoBrowserMode?.value || "headless") === "headed",
    debug: false,
  };
}

async function persistReleaseAutomationDraft({ refresh = false } = {}) {
  const project = ensureProject();
  if (!project) return;
  await api(`/api/projects/${project.id}/release-automation/draft`, {
    method: "POST",
    body: JSON.stringify(releaseAutomationFormPayload()),
  });
  if (refresh) {
    await Promise.all([refreshReleaseAutomation(true), refreshReleases()]);
  }
}

function scheduleReleaseAutomationDraftSave({ refresh = false, delay = 500 } = {}) {
  const scheduledProjectId = state.currentProject?.id || null;
  if (state.releaseEditor.saveTimer) {
    window.clearTimeout(state.releaseEditor.saveTimer);
  }
  state.releaseEditor.saveTimer = window.setTimeout(async () => {
    state.releaseEditor.saveTimer = null;
    if ((state.currentProject?.id || null) !== scheduledProjectId) return;
    try {
      await persistReleaseAutomationDraft({ refresh });
    } catch (error) {
      console.warn(error);
    }
  }, delay);
}

function renderReleasePlatformCapability() {
  if (!els.releasePlatformCapability || !els.releaseAutoPlatform) return;
  const platforms = Array.isArray(state.releaseAutomation?.supported_platforms)
    ? state.releaseAutomation.supported_platforms
    : [];
  const platform = platforms.find((item) => item.key === els.releaseAutoPlatform.value) || null;
  const labels = {
    video: "视频",
    note: "图文",
    article: "文章",
    schedule: "定时发布",
    login: "账号登录",
    check: "登录检查",
    content_stats: "运营数据",
    metrics_backfill: "数据回填",
  };
  const statusLabels = {
    ready: "可执行",
    needs_update: "需更新 OmniPost",
    planned: "待适配",
  };
  const available = Boolean(platform && platform.available !== false && platform.status === "ready");
  const capabilities = (platform?.capabilities || []).map((item) => labels[item] || item).join("、");
  els.releasePlatformCapability.innerHTML = platform
    ? `<span class="pill ${available ? "" : "pill--warn"}">${escapeHtml(statusLabels[platform.status] || platform.status || "未知")}</span> ${
        capabilities ? `支持：${escapeHtml(capabilities)}。` : ""
      }${platform.note ? escapeHtml(platform.note) : ""}`
    : "请选择发布平台。";
  ["release-auto-login-btn", "release-auto-check-btn", "release-auto-publish-btn", "release-auto-enqueue-btn"].forEach((id) => {
    const button = document.getElementById(id);
    if (button) button.disabled = !available;
  });
}

function syncReleaseAutomationForm(force = false) {
  const payload = state.releaseAutomation;
  if (!payload || !els.releaseAutoPlatform) return;
  const draft = payload.draft || {};
  const draftSignature = JSON.stringify({ projectId: state.currentProject?.id || 0, draft });
  const projectChanged = state.releaseEditor.projectId !== (state.currentProject?.id || null);
  if (!force && !projectChanged && state.releaseEditor.lastDraft === draftSignature) return;
  const platforms = Array.isArray(payload.supported_platforms) ? payload.supported_platforms : [];
  if (platforms.length) {
    els.releaseAutoPlatform.innerHTML = platforms
      .map((item) => {
        const status = item.status || (item.available === false ? "planned" : "ready");
        const suffix = status === "ready" ? "" : ` · ${status === "needs_update" ? "需更新" : "待适配"}`;
        const disabled = item.available === false ? " disabled" : "";
        return `<option value="${escapeHtml(item.key)}"${disabled}>${escapeHtml((item.label || item.key) + suffix)}</option>`;
      })
      .join("");
  }
  const accountOptions = Array.isArray(payload.account_options) ? [...payload.account_options] : [];
  const accountProfiles = new Map(
    (Array.isArray(payload.account_profiles) ? payload.account_profiles : []).map((item) => [item.alias, item])
  );
  if (draft.account_name && !accountOptions.includes(draft.account_name)) accountOptions.unshift(draft.account_name);
  els.releaseAutoAccount.innerHTML = accountOptions
    .map((item) => {
      const profile = accountProfiles.get(item) || {};
      const label = profile.display_name ? `${profile.display_name}（${item}）` : `${item}（昵称待同步）`;
      return `<option value="${escapeHtml(item)}">${escapeHtml(label)}</option>`;
    })
    .join("");
  els.releaseAutoPlatform.value = draft.platform || els.releaseAutoPlatform.value || platforms[0]?.key || "douyin";
  els.releaseAutoAccount.value = draft.account_name || "default";
  els.releaseAutoBrowserMode.value = draft.headed ? "headed" : "headless";
  els.releaseAutoSchedule.value = draft.schedule || "";
  els.releaseAutoTitle.value = draft.title || "";
  els.releaseAutoTags.value = draft.tags || "";
  els.releaseAutoDescription.value = draft.description || "";
  renderReleasePlatformCapability();
  state.releaseEditor.projectId = state.currentProject?.id || null;
  state.releaseEditor.lastDraft = draftSignature;
}

function renderReleaseAutomation() {
  const payload = state.releaseAutomation;
  if (!payload) {
    if (els.releaseAutomationSummary) els.releaseAutomationSummary.innerHTML = `<div class="muted">自动发布状态尚未加载</div>`;
    if (els.releaseTaskMeta) els.releaseTaskMeta.innerHTML = `<div class="muted">暂无任务</div>`;
    if (els.releaseAutomationLog) els.releaseAutomationLog.textContent = "暂无自动发布任务";
    if (els.releaseQueueList) els.releaseQueueList.innerHTML = `<div class="muted">暂无发布队列任务</div>`;
    if (els.releaseTaskPill) {
      els.releaseTaskPill.textContent = "未启动";
      els.releaseTaskPill.className = "pill";
    }
    return;
  }
  const probe = payload.probe || {};
  const files = payload.files || {};
  const task = payload.task || null;
  const releaseDraft = payload.draft || {};
  const selectedPlatform = (Array.isArray(payload.supported_platforms) ? payload.supported_platforms : [])
    .find((item) => item.key === releaseDraft.platform) || null;
  const publishedRelease = payload.last_published_release || task?.result?.published_release || null;
  const account = payload.account || {};
  const loginQr = payload.login_qrcode || null;
  const loginPending = task?.action === "login" && task?.running;
  const loginFailed = task?.action === "login"
    && !task?.running
    && ["failed", "timeout", "cancelled", "interrupted"].includes(task?.status);
  const loginError = task?.error || task?.result?.message || task?.message || "登录二维码生成失败";
  const scannerLabels = {
    douyin: "抖音 APP",
    kuaishou: "快手 APP",
    xiaohongshu: "小红书 APP",
    tencent: "微信",
    baijiahao: "百度 APP",
    toutiao: "今日头条 APP",
    sohu: "搜狐新闻 APP",
    zhihu: "知乎 APP",
    tiktok: "TikTok APP",
  };
  const scannerLabel = scannerLabels[releaseDraft.platform] || "对应平台 APP";
  const releaseQueue = payload.queue || {};
  const accountName = account.display_name || account.account_id || "";
  const accountStatusMap = {
    connected: "已登录",
    not_logged_in: "未登录",
    missing: "未找到 cookie",
    unsupported: "暂未接入识别",
    error: "识别失败",
  };
  const accountStatusLabel = accountStatusMap[account.status] || (account.status || "未知");
  const accountSummary = accountName
    ? `${accountStatusLabel} · ${accountName}`
    : `${accountStatusLabel}${account.message ? ` · ${account.message}` : ""}`;
  const taskAccountLabel = accountName && task?.account_name === account.alias
    ? `${accountName}（${task.account_name}）`
    : (task?.account_name || "-");
  const sanitizedLog = (() => {
    const raw = String(task?.log || "暂无自动发布任务");
    const lines = raw.split(/\r?\n/);
    const qrLine = /^[\s\u2580-\u259f\u25a0-\u25ff]+$/;
    let folded = false;
    const kept = [];
    for (const line of lines) {
      const text = line.trim();
      if (text.length > 20 && qrLine.test(text)) {
        folded = true;
        continue;
      }
      kept.push(line);
    }
    if (folded) {
      kept.unshift("[release] 终端字符二维码已折叠，请直接扫上方 PNG 二维码。");
    }
    return kept.join("\n").trim() || "暂无自动发布任务";
  })();
  const fileRow = (label, item) =>
    `<div>${escapeHtml(label)}：${
      item
        ? `<a class="link-btn" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.relative_path || item.name || label)}</a>`
        : `<span class="muted">未找到</span>`
    }</div>`;
  if (els.releaseAutomationSummary) {
    els.releaseAutomationSummary.innerHTML = `
      <div>环境状态：<span class="pill ${probe.status === "success" ? "" : "pill--warn"}">${escapeHtml(probe.status || "idle")}</span></div>
      <div>${escapeHtml(probe.message || "")}</div>
      <div>仓库路径：<span class="mono-inline">${escapeHtml(probe.repo_path || "-")}</span></div>
      <div>uv：<span class="mono-inline">${escapeHtml(probe.uv_bin || "uv")}</span> ${probe.uv_available ? "已找到" : "未找到"}</div>
      ${probe.local_chrome_path ? `<div>本机 Chrome：<span class="mono-inline">${escapeHtml(probe.local_chrome_path)}</span></div>` : ""}
      ${
        selectedPlatform
          ? `<div>发布平台：${escapeHtml(selectedPlatform.label || selectedPlatform.key)} · ${escapeHtml(selectedPlatform.status === "ready" ? "可执行" : "待适配")} ${selectedPlatform.note ? `· ${escapeHtml(selectedPlatform.note)}` : ""}</div>`
          : ""
      }
      <div>账号别名：<span class="mono-inline">${escapeHtml(account.alias || (payload.draft || {}).account_name || "default")}</span></div>
      <div>平台账号：${escapeHtml(accountSummary)}</div>
      ${
        loginQr || loginPending || loginFailed
          ? `
            <div class="release-qr-card">
              <div class="release-qr-card__head">
                <strong>登录二维码</strong>
                ${loginQr ? `<a class="link-btn" href="${escapeHtml(loginQr.url)}" target="_blank" rel="noreferrer">打开大图</a>` : ""}
              </div>
              ${
                loginQr
                  ? `<img class="release-qr-card__image" src="${escapeHtml(loginQr.url)}" alt="${escapeHtml(releaseDraft.platform || "平台")}登录二维码" />`
                  : loginFailed
                    ? `<div class="release-qr-card__loading release-qr-card__error"><strong>二维码生成失败</strong><span>${escapeHtml(loginError)}</span></div>`
                    : `<div class="release-qr-card__loading"><span class="spinner"></span><span>正在自动点击“创作者登录”并准备二维码...</span></div>`
              }
              <div class="muted">请使用${escapeHtml(scannerLabel)}扫码并在手机端确认，页面会自动更新登录状态。</div>
            </div>
          `
          : ""
      }
      ${fileRow("成片视频", files.final_video)}
      ${fileRow("抖音横封面(4:3)", files.thumbnail_story || files.thumbnail_landscape)}
      ${fileRow("竖屏封面(3:4)", files.thumbnail_portrait)}
      ${
        publishedRelease
          ? `<div>最近回填：<a class="link-btn" href="${escapeHtml(publishedRelease.url || "")}" target="_blank" rel="noreferrer">${escapeHtml(publishedRelease.url || "")}</a></div>`
          : ""
      }
    `;
  }
  if (els.releaseTaskPill) {
    els.releaseTaskPill.textContent = task?.status || "未启动";
    els.releaseTaskPill.className = `pill ${task?.status === "failed" || task?.status === "cancelled" ? "pill--warn" : ""}`.trim();
  }
  if (els.releaseTaskMeta) {
    els.releaseTaskMeta.innerHTML = task
      ? `
          <div>动作：${escapeHtml(task.action || "-")} · 平台：${escapeHtml(task.platform || "-")} · 账号：${escapeHtml(taskAccountLabel)}</div>
          <div>平台账号：${escapeHtml(accountSummary)}</div>
          <div>状态：${escapeHtml(task.status || "-")} · 运行中：${task.running ? "是" : "否"}</div>
          ${
            publishedRelease
              ? `<div>回填链接：<a class="link-btn" href="${escapeHtml(publishedRelease.url || "")}" target="_blank" rel="noreferrer">${escapeHtml(publishedRelease.url || "")}</a></div>`
              : ""
          }
          ${task.command ? `<div>命令：<span class="mono-inline">${escapeHtml(task.command)}</span></div>` : ""}
          ${task.cwd ? `<div>工作目录：<span class="mono-inline">${escapeHtml(task.cwd)}</span></div>` : ""}
          ${task.error ? `<div class="pill pill--warn">${escapeHtml(task.error)}</div>` : ""}
        `
      : `<div class="muted">这里会显示仓库、账号、源文件和最近一次任务状态。</div>`;
  }
  if (els.releaseAutomationLog) {
    els.releaseAutomationLog.textContent = sanitizedLog;
  }
  renderReleaseQueue(releaseQueue);
  syncReleaseAutomationForm();
  const preflight = payload.release_preflight || null;
  const publishReady = preflight ? Boolean(preflight.ready) : Boolean(files.final_video);
  const enqueueButton = document.getElementById("release-auto-enqueue-btn");
  const publishButton = document.getElementById("release-auto-publish-btn");
  if (enqueueButton) {
    enqueueButton.disabled = false;
    enqueueButton.textContent = publishReady ? "\u52a0\u5165\u53d1\u5e03\u961f\u5217" : "\u9884\u7ea6\u5e76\u7b49\u5f85\u6210\u7247";
    enqueueButton.title = publishReady
      ? "\u6309\u9884\u7ea6\u65f6\u95f4\u8fdb\u5165\u53d1\u5e03\u6d41\u7a0b"
      : "\u53ef\u4ee5\u63d0\u524d\u9884\u7ea6\uff1b\u7cfb\u7edf\u4f1a\u7b49\u5f85\u6210\u7247\u751f\u6210\u540e\u81ea\u52a8\u53d1\u5e03";
  }
  if (publishButton) {
    publishButton.disabled = false;
    publishButton.textContent = publishReady ? "\u7acb\u5373\u53d1\u5e03" : "\u6210\u7247\u540e\u7acb\u5373\u53d1\u5e03";
    publishButton.title = publishReady
      ? "\u7acb\u5373\u52a0\u5165\u53d1\u5e03\u961f\u5217"
      : "\u5148\u52a0\u5165\u961f\u5217\uff0c\u6210\u7247\u751f\u6210\u540e\u7acb\u5373\u81ea\u52a8\u53d1\u5e03";
  }
}

function renderReleaseQueue(queue) {
  if (!els.releaseQueueList) return;
  const allJobs = Array.isArray(queue?.jobs) ? queue.jobs : [];
  if (!allJobs.length) {
    els.releaseQueueList.innerHTML = `<div class="muted">当前主题还没有发布任务。</div>`;
    return;
  }
  const statusLabels = {
    waiting_assets: "\u7b49\u5f85\u6210\u7247",
    waiting_schedule: "\u7b49\u5f85\u9884\u7ea6\u65f6\u95f4",
    queued: "等待发布",
    checking_account: "检查账号",
    waiting_login: "等待登录",
    publishing: "上传发布",
    verifying: "平台核验",
    retrying: "自动重试",
    needs_attention: "等待确认",
    succeeded: "发布成功",
    failed: "发布失败",
    cancelled: "已取消",
  };
  const activeStatuses = new Set(["waiting_assets", "waiting_schedule", "queued", "checking_account", "waiting_login", "publishing", "verifying", "retrying"]);
  const dateLabel = (value) => {
    const number = Number(value || 0);
    if (!number) return "-";
    return new Date(number * 1000).toLocaleString("zh-CN", { hour12: false });
  };
  const sortedJobs = [...allJobs].sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0));
  const latestKeys = new Set();
  const jobs = [];
  const historyJobs = [];
  sortedJobs.forEach((job) => {
    const key = `${job.platform || "unknown"}:${job.account_name || "default"}`;
    if (!latestKeys.has(key)) {
      latestKeys.add(key);
      jobs.push(job);
    } else {
      historyJobs.push(job);
    }
  });
  const platformLabels = {
    douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书", bilibili: "Bilibili",
    tencent: "视频号", toutiao: "今日头条", baijiahao: "百家号", sohu: "搜狐号",
    zhihu: "知乎", tiktok: "TikTok",
  };
  const renderJob = (job, historical = false) => {
    const status = job.status || "queued";
    const retryable = !historical && (status === "failed" || status === "cancelled" || status === "needs_attention");
    const cancellable = !historical && activeStatuses.has(status);
    const resultLink = job.result?.published_release?.url || "";
    const diagnostics = job.log || "";
    const heartbeatAt = Number(job.last_heartbeat_at || job.updated_at || 0);
    const heartbeatAge = heartbeatAt ? Math.max(0, Math.round(Date.now() / 1000 - heartbeatAt)) : null;
    const heartbeatLabel = activeStatuses.has(status) && heartbeatAge !== null
      ? ` · 后台心跳 ${heartbeatAge < 5 ? "刚刚" : `${heartbeatAge} 秒前`}`
      : "";
    const progressDetail = job.last_action_detail || "";
    return `
      <div class="release-queue-row ${historical ? "release-queue-row--historical" : ""}">
        <div class="release-queue-row__main">
          <div class="release-queue-row__title">
            <strong>${escapeHtml(job.project_title || state.currentProject?.topic_name || "未命名主题")}</strong>
            <span class="pill ${status === "failed" || status === "cancelled" ? "pill--warn" : ""}">${escapeHtml(statusLabels[status] || status)}</span>
          </div>
          <div class="muted">频道：${escapeHtml(job.channel || "-")} · ${escapeHtml(platformLabels[job.platform] || job.platform || "-")} · 固定账号：${escapeHtml(job.account_display_name ? `${job.account_display_name}（${job.account_name || "default"}）` : (job.account_name || "default"))}</div>
          <div class="muted">${escapeHtml(job.stage || statusLabels[status] || "-")} · 尝试 ${escapeHtml(job.attempts || 0)}/${escapeHtml(job.max_attempts || 2)}${escapeHtml(heartbeatLabel)} · ${escapeHtml(dateLabel(job.updated_at))}</div>
          ${progressDetail && activeStatuses.has(status) ? `<div class="release-queue-row__progress"><span class="spinner"></span><span>${escapeHtml(progressDetail)}</span></div>` : ""}
          ${job.error ? `<div class="release-queue-row__error">${escapeHtml(job.error)}</div>` : ""}
          ${diagnostics ? `
            <details class="release-queue-row__details">
              <summary>查看本次执行详情</summary>
              <div class="muted">动作：${escapeHtml(job.last_action || "-")} · 工作目录：${escapeHtml(job.cwd || "-")}</div>
              ${job.command ? `<div class="release-queue-row__command">${escapeHtml(job.command)}</div>` : ""}
              <pre>${escapeHtml(diagnostics)}</pre>
            </details>
          ` : (status === "failed" ? `<div class="muted">这是升级日志持久化前的历史任务；请查看该平台上方最新任务的真实错误。</div>` : "")}
          ${resultLink ? `<a class="link-btn" href="${escapeHtml(resultLink)}" target="_blank" rel="noreferrer">查看平台作品</a>` : ""}
        </div>
        <div class="release-queue-row__actions">
          ${retryable ? `<button class="btn btn--ghost" type="button" data-release-queue-retry="${escapeHtml(job.id)}">重试</button>` : ""}
          ${cancellable ? `<button class="btn btn--danger" type="button" data-release-queue-cancel="${escapeHtml(job.id)}">取消</button>` : ""}
        </div>
      </div>
    `;
  };
  const currentHtml = jobs.map((job) => renderJob(job)).join("");
  const historyHtml = historyJobs.length
    ? `<details class="release-queue-history"><summary>查看历史发布记录（${historyJobs.length}）</summary>${historyJobs.map((job) => renderJob(job, true)).join("")}</details>`
    : "";
  els.releaseQueueList.innerHTML = currentHtml + historyHtml;
  els.releaseQueueList.querySelectorAll("[data-release-queue-retry]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await withBusyButton(button, "正在重试...", async () => {
          await api(`/api/release-queue/${encodeURIComponent(button.dataset.releaseQueueRetry || "")}/retry`, { method: "POST" });
          await refreshReleaseAutomation();
        });
      } catch (error) {
        window.alert(error.message || "发布任务重试失败。");
      }
    });
  });
  els.releaseQueueList.querySelectorAll("[data-release-queue-cancel]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("确认取消这个发布任务吗？")) return;
      try {
        await withBusyButton(button, "正在取消...", async () => {
          await api(`/api/release-queue/${encodeURIComponent(button.dataset.releaseQueueCancel || "")}/cancel`, { method: "POST" });
          await refreshReleaseAutomation();
        });
      } catch (error) {
        window.alert(error.message || "取消发布任务失败。");
      }
    });
  });
}

function renderConfig() {
  if (!state.config) {
    els.configFields.innerHTML = `<div class="muted">配置尚未加载</div>`;
    return;
  }
  const renderBadge = (label, kind) => `<span class="config-badge config-badge--${kind}">${escapeHtml(label)}</span>`;
  const renderSectionCheck = (section) => {
    const validation = section.validation || {};
    const status = validation.status || "idle";
    const labelMap = {
      idle: "未校验",
      unconfigured: "未配置",
      success: "校验通过",
      warning: "待联调",
      error: "校验失败",
    };
    const toneMap = {
      idle: "optional",
      unconfigured: "optional",
      success: "success",
      warning: "warning",
      error: "error",
    };
    return `
      <div class="config-item__check">
        ${renderBadge(labelMap[status] || status, toneMap[status] || "optional")}
        ${validation.message ? `<div style="margin-top:8px;">${escapeHtml(validation.message)}</div>` : ""}
        ${validation.checked_at ? `<div style="margin-top:6px;">最近校验：${escapeHtml(formatValidationTime(validation.checked_at))}</div>` : ""}
      </div>
    `;
  };
  const renderFieldControl = (field) => {
    const key = escapeHtml(field.key);
    const currentValue = field.value || "";
    const isTtsSpeaker = field.key === "VOLC_TTS_SPEAKER_1" || field.key === "VOLC_TTS_SPEAKER_2";
    if (field.kind === "model_select") {
      const options = (field.options || [])
        .map((item) => {
          const value = typeof item === "string" ? item : item.value;
          const label = typeof item === "string" ? item : (item.label || item.value);
          return `<button type="button" class="model-dropdown-option${value === currentValue ? " is-selected" : ""}" data-select-model="${escapeHtml(value || "")}">${escapeHtml(label || value || "")}</button>`;
        })
        .join("");
      return `
        <div class="model-select-control">
          <div class="model-combobox">
            <input data-config-key="${key}" type="text" value="${escapeHtml(currentValue)}" placeholder="选择或输入模型 ID" autocomplete="off" aria-label="DeepSeek 模型" />
            <button class="model-dropdown-toggle" type="button" data-toggle-model-dropdown="deepseek" aria-label="展开模型列表" aria-expanded="false">▾</button>
            <div class="model-dropdown hidden" data-model-options="deepseek">${options || '<div class="model-dropdown-empty">请先点击右侧“同步模型”</div>'}</div>
          </div>
          <button class="btn btn--primary model-sync-button" type="button" data-save-selected-model="deepseek">应用模型</button>
          <button class="btn btn--ghost model-sync-button" type="button" data-sync-models="deepseek">同步模型</button>
        </div>
        <div class="model-sync-status" data-model-sync-status="deepseek" aria-live="polite"></div>
      `;
    }
    if (field.kind === "select") {
      const options = (field.options || [])
        .map((item) => {
          const selected = item.value === currentValue ? "selected" : "";
          return `<option value="${escapeHtml(item.value)}" ${selected}>${escapeHtml(item.label || item.value)}</option>`;
        })
        .join("");
      const selectHtml = `<select data-config-key="${key}">${options}</select>`;
      if (isTtsSpeaker) {
        return `
          <div class="secret-input">
            ${selectHtml}
            <button class="icon-btn" type="button" data-preview-voice-key="${key}" title="试听">听</button>
          </div>
        `;
      }
      return selectHtml;
    }
    if (field.kind === "number") {
      return `<input data-config-key="${key}" type="number" step="any" value="${escapeHtml(currentValue)}" />`;
    }
    if (field.secret) {
      const revealed = !!state.revealedSecrets[field.key];
      return `
        <div class="secret-input">
          <input
            data-config-key="${key}"
            data-secret="true"
            type="${revealed ? "text" : "password"}"
            value=""
            placeholder="${escapeHtml(field.placeholder || "粘贴后写入，留空则不变")}"
          />
          <button class="icon-btn" type="button" data-toggle-secret="${key}" title="${revealed ? "隐藏" : "显示"}">${revealed ? "隐" : "显"}</button>
        </div>
      `;
    }
    return `<input data-config-key="${key}" type="text" value="${escapeHtml(currentValue)}" />`;
  };

  els.configFields.className = "config-layout";
  els.configFields.innerHTML = (state.config.sections || [])
    .map(
      (section) => `
        <section class="config-group">
          <div class="section-head">
            <div>
              <h4>${escapeHtml(section.title)}</h4>
              <p class="config-group__desc">${escapeHtml(section.description || "")}</p>
            </div>
            <div class="toolbar">
              ${section.validator ? `<button class="btn btn--ghost" data-validate-config="${escapeHtml(section.key)}">校验密钥</button>` : ""}
            </div>
          </div>
          ${renderSectionCheck(section)}
          <div class="config-group__fields">
            ${(section.fields || [])
              .map(
                (field) => `
                  <article class="config-item">
                    <div class="config-item__head">
                      <div>
                        <div class="config-item__title">
                          <strong>${escapeHtml(field.label)}</strong>
                          ${renderBadge(field.required ? "必填" : "可选", field.required ? "required" : "optional")}
                          ${field.configured ? renderBadge("已配置", "configured") : ""}
                        </div>
                        <div class="config-item__key">${escapeHtml(field.key)}</div>
                      </div>
                    </div>
                    <div class="config-control">${renderFieldControl(field)}</div>
                    <div class="config-item__help">${escapeHtml(field.help || "")}</div>
                  </article>
                `
              )
              .join("")}
          </div>
        </section>
      `
    )
    .join("");
}

function renderPackaging() {
  if (!els.packagingSummary || !els.packagingLog || !els.packagingStatusPill) return;
  const payload = state.packaging;
  if (!payload) {
    els.packagingSummary.innerHTML = `<div class="muted">导出状态尚未加载</div>`;
    els.packagingLog.textContent = "暂无导出任务";
    els.packagingStatusPill.textContent = "未启动";
    els.packagingStatusPill.className = "pill";
    if (els.startPortableBuildBtn) els.startPortableBuildBtn.disabled = true;
    if (els.startZipBuildBtn) els.startZipBuildBtn.disabled = true;
    if (els.cancelPackagingBtn) els.cancelPackagingBtn.disabled = true;
    if (els.openPackagingOutputBtn) els.openPackagingOutputBtn.disabled = true;
    return;
  }
  const task = payload.task || null;
  const artifacts = payload.artifacts || {};
  const available = !!payload.available;
  const running = !!task?.running;
  const status = task?.status || "idle";
  const statusMap = {
    idle: "未启动",
    running: "导出中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已取消",
  };
  const pathLine = (label, value, target, exists) => `
    <div>
      ${label}：<span class="mono-inline">${escapeHtml(value || "—")}</span>
      ${exists ? `<button class="btn btn--ghost" data-open-packaging-target="${escapeHtml(target)}">打开</button>` : ""}
    </div>
  `;
  els.packagingSummary.innerHTML = `
    <div>${available ? "打包环境已就绪，可直接导出当前桌面版。" : "当前运行环境里没有可用打包脚本，暂时无法导出 EXE。"}</div>
    <div>Python：<span class="mono-inline">${escapeHtml(payload.python_path || "—")}</span></div>
    ${pathLine("输出目录", artifacts.output_root, "output", artifacts.output_exists)}
    ${pathLine("便携目录", artifacts.portable_dir, "portable", artifacts.portable_exists)}
    ${pathLine("EXE 文件", artifacts.exe_path, "exe", false)}
    ${pathLine("ZIP 文件", artifacts.zip_path, "zip", artifacts.zip_exists)}
    ${artifacts.zip_exists ? `<div>ZIP 大小：${escapeHtml(formatByteSize(artifacts.zip_size))}</div>` : ""}
    ${task ? `<div>最近任务：${escapeHtml(task.mode || "portable")} · 开始 ${escapeHtml(formatMaybeTimestamp(task.started_at))}${task.finished_at ? ` · 结束 ${escapeHtml(formatMaybeTimestamp(task.finished_at))}` : ""}</div>` : ""}
    ${task?.error ? `<div class="pill pill--warn">${escapeHtml(task.error)}</div>` : ""}
  `;
  els.packagingLog.textContent = task?.log || "暂无导出任务";
  els.packagingStatusPill.textContent = statusMap[status] || status;
  els.packagingStatusPill.className = `pill ${status === "failed" || status === "cancelled" ? "pill--warn" : ""}`.trim();
  if (els.startPortableBuildBtn) els.startPortableBuildBtn.disabled = !available || running;
  if (els.startZipBuildBtn) els.startZipBuildBtn.disabled = !available || running;
  if (els.cancelPackagingBtn) els.cancelPackagingBtn.disabled = !running;
  if (els.openPackagingOutputBtn) els.openPackagingOutputBtn.disabled = !artifacts.output_exists;
}

async function refreshTemplates() {
  state.templatesLoading = true;
  state.templatesError = "";
  if (!state.templatesLoaded) renderTemplates();
  try {
    state.templates = await api("/api/templates");
    state.templatesLoaded = true;
    ensureSelectedTemplateKey();
  } catch (error) {
    state.templatesError = error.message || "请检查服务后重试";
    throw error;
  } finally {
    state.templatesLoading = false;
    renderTemplates();
    renderProjects();
  }
}

async function refreshProjects() {
  state.projects = await api("/api/projects");
  ensureSelectedTemplateKey();
  renderProjects();
  renderTemplates();
  if (!state.currentProject) {
    const firstProject = projectsForSelectedTemplate()[0] || state.projects[0];
    if (firstProject) await openProject(firstProject.id);
  }
}

async function refreshConfig() {
  state.config = await api("/api/settings/secrets");
  renderConfig();
  renderImageProviderSwitch();
}

async function refreshPackaging() {
  state.packaging = await api("/api/settings/packaging");
  renderPackaging();
  if (state.packaging?.task?.running) {
    startPackagingPolling();
  } else {
    stopPackagingPolling();
  }
}

async function refreshTtsPreviews() {
  try {
    state.ttsPreviews = await api("/api/settings/tts-previews");
  } catch (error) {
    console.warn(error);
    state.ttsPreviews = null;
  }
}

async function validateConfigSections(targets = null) {
  await api("/api/settings/secrets/validate", {
    method: "POST",
    body: JSON.stringify({ targets }),
  });
  await refreshConfig();
}

async function refreshAutoVideoStatus({ openCreatedProject = false } = {}) {
  try {
    const payload = await api("/api/auto-video/latest");
    state.autoVideo = payload.task || null;
    if (state.autoVideoModalVisible) {
      renderAutoVideoModal();
    }
    const projectId = Number(state.autoVideo?.project_id || state.autoVideo?.result?.project_id || 0);
    if (openCreatedProject && projectId && state.autoVideoOpenedProjectId !== projectId) {
      state.autoVideoOpenedProjectId = projectId;
      await refreshProjects();
      await openProject(projectId);
    }
    if (!payload.running && state.autoVideoTimer) {
      clearInterval(state.autoVideoTimer);
      state.autoVideoTimer = null;
      await refreshProjects();
      if (projectId) {
        await openProject(projectId);
      }
    }
  } catch (error) {
    console.warn(error);
  }
}

async function refreshFiles() {
  const project = ensureProject();
  if (!project) return;
  state.currentFiles = await api(`/api/projects/${project.id}/files`);
  renderFiles();
}

async function refreshSceneStatus() {
  const project = ensureProject();
  if (!project) return;
  state.sceneStatus = await api(`/api/projects/${project.id}/scene-images/status`);
  renderScenes();
  renderSceneCountControls();
}

async function refreshImageReview() {
  const project = ensureProject();
  if (!project) return;
  state.imageReview = await api(`/api/projects/${project.id}/image-review`);
  renderImageReview();
  if (state.currentFiles) renderCovers(state.currentFiles);
  syncVideoStepWithReviewMode();
}

async function refreshStageGates() {
  const project = ensureProject();
  if (!project) return;
  state.stageGates = await api(`/api/projects/${project.id}/stage-gates`);
  renderStageGates();
}

async function refreshProjectStatus() {
  const project = ensureProject();
  if (!project) return;
  state.projectStatus = await api(`/api/projects/${project.id}/status`);
  renderProjectStatus();
}

async function refreshProductionManifest() {
  const project = ensureProject();
  if (!project) return;
  state.productionManifest = await api(`/api/projects/${project.id}/production-manifest`);
  renderProductionManifest();
}

async function refreshVoiceStatus() {
  const project = ensureProject();
  if (!project) return;
  state.voiceStatus = await api(`/api/projects/${project.id}/voice/status`);
  renderVoiceStatus();
}

async function refreshBgmStatus() {
  state.bgmStatus = {
    mode: "off",
    status: "disabled",
    current: true,
    path: "",
    label: "已移除",
    reason: "成片只保留口播音轨。",
  };
}

async function refreshChatgptAccounts() {
  if (!state.backendOnline) return;
  state.chatgptAccounts = await api("/api/settings/chatgpt-accounts");
  renderChatgptAccountPool();
}

async function refreshContentSyncStatus() {
  const project = ensureProject();
  if (!project || !state.currentContent) return;
  const previous = state.currentContent.content_sync || {};
  const sync = await api(`/api/projects/${project.id}/content/sync/status`);
  state.currentContent.content_sync = sync;
  renderContentBundle();
  if (previous.running && !sync.running) {
    await Promise.all([refreshContentBundle(), refreshProductionManifest(), refreshProjectStatus(), refreshStageGates(), refreshVoiceStatus(), refreshBgmStatus()]);
  }
}

async function refreshLatestJob({ refreshGates = true } = {}) {
  const project = ensureProject();
  if (!project) return;
  const previousId = state.currentJob?.id;
  const previousStatus = state.currentJob?.status;
  const payload = await api(`/api/projects/${project.id}/jobs/latest`);
  state.jobPollFailures = 0;
  state.lastJobPollSuccessAt = Date.now();
  state.currentJob = payload.job;
  renderJob();
  const currentStep = String(state.currentJob?.current_step || "");
  const jobLog = String(state.currentJob?.log || "");
  const imageWorkActive = Boolean(
    state.currentJob?.running
    && (
      ["images", "images_missing", "images_sample", "covers", "covers_missing"].includes(currentStep)
      || /\[images\].*(?:开始|进度|已保存|normalized|生成图片)/.test(jobLog)
    )
  );
  if (imageWorkActive) {
    await Promise.all([refreshSceneStatus(), refreshFiles()]);
  }
  if (refreshGates) await refreshStageGates();
  const terminal = ["succeeded", "failed", "cancelled", "interrupted"].includes(state.currentJob?.status);
  const transitioned = terminal && (previousId !== state.currentJob?.id || previousStatus !== state.currentJob?.status);
  if (transitioned) {
    await Promise.all([refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshProjectStatus(), refreshStageGates(), refreshProductionManifest(), refreshVoiceStatus(), refreshBgmStatus()]);
  }
}

async function refreshReleases({ autoSync = false } = {}) {
  const project = ensureProject();
  if (!project) return;
  [state.releaseLinks, state.releasePlatformStats] = await Promise.all([
    api(`/api/projects/${project.id}/releases`),
    api(`/api/projects/${project.id}/releases/platform-stats`),
  ]);
  renderReleases();
  renderReleasePlatformStats();
  renderReleaseMetricsSyncStatus();
  refreshReleaseMetricsSyncStatus({ poll: true, silent: true }).catch((error) => console.warn(error));
  const lastAttemptAge = Date.now() - Number(state.releaseMetricsSync?.lastAttemptAt || 0);
  const recentlyAttempted = state.releaseMetricsSync?.projectId === project.id && lastAttemptAge < 15 * 60 * 1000;
  const hasAutoRelease = state.releaseLinks.some((item) => ["douyin", "抖音"].includes(String(item?.platform || "").toLowerCase()));
  if (autoSync && hasAutoRelease && !recentlyAttempted) {
    syncReleaseMetrics({ silent: true, platform: "douyin" }).catch((error) => console.warn(error));
  }
}

async function refreshReleaseAutomation(forceForm = false) {
  const project = ensureProject();
  if (!project) return;
  const [automation, catalog] = await Promise.all([
    api(`/api/projects/${project.id}/release-automation`),
    api("/api/release-automation/accounts"),
  ]);
  state.releaseAutomation = automation;
  state.releaseAccountCatalog = catalog;
  renderReleaseAutomation();
  syncReleaseAutomationForm(forceForm);
  renderReleaseBatchTargets();
}

async function refreshContentBundle(forceEditor = false) {
  const project = ensureProject();
  if (!project) return;
  const previousGenerationStatus = String(state.currentContent?.content_generate?.status || "");
  const bundle = await api(`/api/projects/${project.id}/content`);
  const nextGenerationStatus = String(bundle?.content_generate?.status || "");
  const generationJustFinished = previousGenerationStatus === "running"
    && ["succeeded", "succeeded_with_warnings"].includes(nextGenerationStatus);
  state.currentContent = bundle;
  renderContentBundle({ forceEditor: forceEditor || generationJustFinished });
}

async function openProject(projectId) {
  state.currentProject = state.projects.find((item) => item.id === projectId) || await api(`/api/projects/${projectId}`);
  if (state.releaseMetricsSync?.projectId !== projectId) {
    state.releaseMetricsSync = { projectId: null, running: false, lastAttemptAt: 0, message: "" };
  }
  state.voiceStatus = null;
  state.bgmStatus = null;
  state.imageReview = null;
  state.selectedTemplateKey = state.currentProject.template || state.selectedTemplateKey;
  renderProjects();
  renderTemplates();
  renderSteps();
  els.workspaceTitle.textContent = state.currentProject.topic_name;
  const latestStatus = {
    succeeded: "已完成",
    running: "生产中",
    failed: "需处理",
    cancelled: "已停止",
    interrupted: "已中断，可续跑",
    idle: "未开始",
  }[String(state.currentProject.last_job_status || "idle").toLowerCase()] || "未开始";
  const contentTypeLabel = state.currentProject.content_type === "product" ? "商品推广" : "知识 / 观点";
  els.workspaceSubtitle.textContent = `${state.currentProject.template} · ${contentTypeLabel} · ${state.currentProject.template_mode === "article" ? "图文工作流" : "视频工作流"} · ${latestStatus}`;
  renderVoiceStatus();
  renderBgmStatus();
  await Promise.all([refreshContentBundle(true), refreshFiles(), refreshSceneStatus(), refreshImageReview(), refreshStageGates(), refreshProjectStatus(), refreshProductionManifest(), refreshVoiceStatus(), refreshBgmStatus(), refreshChatgptAccounts(), refreshLatestJob({ refreshGates: false }), refreshReleases()]);
}

async function checkBackend() {
  try {
    await api("/api/projects");
    setBackendOnline(true);
    return true;
  } catch (error) {
    setBackendOnline(false);
    return false;
  }
}

async function boot() {
  renderSteps();
  updateWorkflowButtons();
  const online = await checkBackend();
  if (!online) return;
  await Promise.all([refreshTemplates(), refreshProjects(), refreshConfig(), refreshPackaging(), refreshTtsPreviews(), refreshChatgptAccounts()]);
  await refreshAutoVideoStatus();
  if (state.autoVideo?.running) startAutoVideoPolling();
  if (state.currentProject) {
    await openProject(state.currentProject.id);
  }
  startJobPolling();
  startPolling();
}

function startJobPolling() {
  if (state.jobPollTimer) clearInterval(state.jobPollTimer);
  state.jobPollTimer = window.setInterval(async () => {
    if (!state.currentProject || state.jobPollBusy) return;
    if (!state.backendOnline) {
      state.jobPollBusy = true;
      try {
        const reconnected = await checkBackend();
        if (!reconnected) {
          state.jobPollFailures = Math.max(2, Number(state.jobPollFailures || 0) + 1);
          renderTaskCommandBar();
          return;
        }
        state.jobPollFailures = 0;
        await refreshLatestJob({ refreshGates: false });
        await Promise.all([refreshSceneStatus(), refreshFiles(), refreshProjectStatus(), refreshProductionManifest()]);
      } catch (error) {
        state.jobPollFailures = Math.max(2, Number(state.jobPollFailures || 0) + 1);
        renderTaskCommandBar();
        console.warn(error);
      } finally {
        state.jobPollBusy = false;
      }
      return;
    }
    const now = Date.now();
    const jobRunning = Boolean(state.currentJob?.running);
    const idleInterval = document.hidden ? 30000 : 10000;
    if (!jobRunning && now - state.lastIdleJobPollAt < idleInterval) return;
    if (!jobRunning) state.lastIdleJobPollAt = now;
    state.jobPollBusy = true;
    try {
      await refreshLatestJob({ refreshGates: false });
    } catch (error) {
      state.jobPollFailures = state.backendOnline
        ? Number(state.jobPollFailures || 0) + 1
        : Math.max(2, Number(state.jobPollFailures || 0) + 1);
      renderTaskCommandBar();
      console.warn(error);
    } finally {
      state.jobPollBusy = false;
    }
  }, 1800);
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = window.setInterval(async () => {
    if (!state.backendOnline || !state.currentProject || state.pollBusy) return;
    const jobRunning = Boolean(state.currentJob?.running);
    const contentRunning = state.currentContent?.content_generate?.status === "running";
    const releaseRunning = Boolean(
      state.releaseAutomation?.task?.running
      || state.releaseAutomation?.queue?.running
      || state.releaseAutomation?.queue?.pending_count
    );
    if (document.hidden && !jobRunning && !contentRunning && !releaseRunning) return;
    state.pollBusy = true;
    state.pollTick += 1;
    try {
      const runningImages = state.currentJob?.running && ["images", "images_missing", "images_sample", "covers", "covers_missing"].includes(state.currentJob?.current_step);
      const lightTasks = [];
      if (contentRunning || state.pollTick % 4 === 0) lightTasks.push(refreshContentSyncStatus());
      if (jobRunning ? state.pollTick % 4 === 0 : state.pollTick % 8 === 0) lightTasks.push(refreshStageGates());
      if (jobRunning ? state.pollTick % 2 === 0 : state.pollTick % 8 === 0) lightTasks.push(refreshProductionManifest());
      if (contentRunning) lightTasks.push(refreshContentBundle());
      if (runningImages && state.pollTick % 2 === 0) lightTasks.push(refreshSceneStatus(), refreshFiles());
      if (jobRunning ? state.pollTick % 8 === 0 : state.pollTick % 24 === 0) {
        lightTasks.push(refreshContentBundle());
        if (!runningImages) lightTasks.push(refreshSceneStatus(), refreshFiles());
        if (state.activeTab === "releases") lightTasks.push(refreshReleases({ autoSync: true }));
      }
      const releaseBusy = releaseRunning;
      // Login QR state is time-sensitive. Poll every cycle while it is visible
      // rather than waiting for the generic release queue cadence.
      const releaseLoginLive = Boolean(
        state.releaseAutomation?.login_qrcode
        || (state.releaseAutomation?.task?.action === "login" && state.releaseAutomation?.task?.running)
      );
      if (releaseLoginLive || (releaseBusy && state.pollTick % 2 === 0)) lightTasks.push(refreshReleaseAutomation());
      await Promise.all(lightTasks);
    } catch (error) {
      console.warn(error);
    } finally {
      state.pollBusy = false;
    }
  }, 2500);
}

function startAutoVideoPolling() {
  if (state.autoVideoTimer) clearInterval(state.autoVideoTimer);
  state.autoVideoTimer = window.setInterval(async () => {
    if (!state.backendOnline) return;
    await refreshAutoVideoStatus({ openCreatedProject: true });
  }, 3000);
}

function stopPackagingPolling() {
  if (state.packagingTimer) {
    clearInterval(state.packagingTimer);
    state.packagingTimer = null;
  }
}

function startPackagingPolling() {
  if (state.packagingTimer) clearInterval(state.packagingTimer);
  state.packagingTimer = window.setInterval(async () => {
    if (!state.backendOnline) return;
    try {
      await refreshPackaging();
    } catch (error) {
      console.warn(error);
    }
  }, 2500);
}

function collectConfigValues() {
  const values = {};
  document.querySelectorAll("[data-config-key]").forEach((input) => {
    values[input.dataset.configKey] = input.value;
  });
  return values;
}

function configFieldValue(key, fallback = "") {
  for (const section of state.config?.sections || []) {
    for (const field of section.fields || []) {
      if (field.key === key) return field.value || fallback;
    }
  }
  return fallback;
}

function imageProviderLabel(value) {
  return IMAGE_PROVIDER_OPTIONS.find((item) => item.value === value)?.label || value || "未设置";
}

function renderImageProviderSwitch() {
  if (!els.imageProviderSelect) return;
  const currentValue = configFieldValue("IMAGE_PROVIDER", "auto_no_apiyi");
  els.imageProviderSelect.innerHTML = IMAGE_PROVIDER_OPTIONS.map((item) => {
    const selected = item.value === currentValue ? "selected" : "";
    return `<option value="${escapeHtml(item.value)}" ${selected}>${escapeHtml(item.label)}</option>`;
  }).join("");
  if (els.imageProviderCurrent) {
    const modeHint = currentValue === "chatgpt_desktop_handoff"
      ? "提示词自动存档并复制；需手动粘贴、生成和保存图片"
      : currentValue === "chatgpt_web_handoff"
        ? "提示词自动存档并复制；需在网页手动生成和保存"
        : currentValue === "chatgpt_web_auto"
          ? "自动输入提示词、等待生成并保存图片"
          : "";
    els.imageProviderCurrent.textContent = `当前：${imageProviderLabel(currentValue)}${modeHint ? ` · ${modeHint}` : ""}`;
  }
}

function renderSceneCountControls() {
  if (!els.sceneCountMode || !els.sceneCountFixed || !els.sceneCountCurrent) return;
  const settings = state.currentContent?.project_settings || {};
  const mode = settings.scene_count_mode === "fixed" ? "fixed" : "auto";
  const fixed = Math.max(1, Math.min(Number(settings.scene_count_fixed || 6), 24));
  if (document.activeElement !== els.sceneCountMode) {
    els.sceneCountMode.value = mode;
  }
  if (document.activeElement !== els.sceneCountFixed) {
    els.sceneCountFixed.value = String(fixed);
  }
  els.sceneCountFixed.disabled = mode !== "fixed";
  const statusCount = Number(state.sceneStatus?.expected_count || 0);
  const summaryCount = statusCount || state.currentContent?.summary?.scene_count || "—";
  const rawSummaryCount = Number(state.sceneStatus?.raw_summary_count || 0);
  const expectedSource = state.sceneStatus?.expected_source || "";
  const timelineAudioMs = Number(state.sceneStatus?.timeline_audio_ms || 0);
  const timelineMinutes = timelineAudioMs ? Math.round(timelineAudioMs / 6000) / 10 : 0;
  const autoText = expectedSource === "audio_timeline" && rawSummaryCount && Number(summaryCount) !== rawSummaryCount
    ? `当前：自动估算，文案 ${rawSummaryCount} 张 / 按音频实际 ${summaryCount} 张${timelineMinutes ? `（约 ${timelineMinutes} 分钟）` : ""}`
    : `当前：自动估算，现计划 ${summaryCount} 张`;
  els.sceneCountCurrent.textContent = mode === "fixed"
    ? `当前：固定 ${fixed} 张`
    : autoText;
  renderCoverGenerationControls();
}

function coverGenerationEnabled() {
  const settings = state.currentContent?.project_settings || {};
  return settings.cover_enabled !== false;
}

function renderCoverGenerationControls() {
  const enabled = coverGenerationEnabled();
  els.coverEnabledButtons.forEach((button) => {
    const active = (button.dataset.coverEnabled === "true") === enabled;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
    button.disabled = !state.currentProject || Boolean(state.currentJob?.running);
  });
  if (els.coverGenerationStatus) {
    els.coverGenerationStatus.textContent = enabled
      ? "本期会自动生成封面，并纳入图片检查"
      : "本期跳过封面，场景图完成后即可继续成片";
  }
  document.querySelectorAll('[data-step="covers"], [data-step="covers_missing"]').forEach((input) => {
    input.disabled = !enabled;
    if (!enabled) input.checked = false;
  });
}

function productModeEnabled() {
  const settings = state.currentContent?.project_settings || {};
  return (settings.content_type || state.currentProject?.content_type || "editorial") === "product";
}

function currentOutputLanguage() {
  const settings = state.currentContent?.project_settings || {};
  const value = settings.output_language || state.currentProject?.output_language || "zh-CN";
  return String(value).toLowerCase().startsWith("en") ? "en-US" : "zh-CN";
}

function renderOutputLanguageControls() {
  const language = currentOutputLanguage();
  els.outputLanguageButtons.forEach((button) => {
    const active = button.dataset.outputLanguage === language;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
    button.disabled = !state.currentProject;
  });
  if (els.outputLanguageStatus) {
    els.outputLanguageStatus.textContent = language === "en-US"
      ? "English production: script, voice, subtitles, image text and release copy. Preview the selected voice before rendering."
      : "文案、配音、字幕、图片文字和发布文案保持中文。";
  }
}

function productSettingsPayload() {
  return {
    content_type: "product",
    product_name: els.productName?.value.trim() || "",
    product_category: els.productCategory?.value.trim() || "",
    product_target_customer: els.productTargetCustomer?.value.trim() || "",
    product_usage_scenarios: els.productUsageScenarios?.value.trim() || "",
    product_selling_points: els.productSellingPoints?.value.trim() || "",
    product_evidence: els.productEvidence?.value.trim() || "",
    product_offer: els.productOffer?.value.trim() || "",
    product_compliance_notes: els.productComplianceNotes?.value.trim() || "",
  };
}

function applyProjectSettingsResponse(payload) {
  if (!payload) return;
  if (state.currentContent && payload.project_settings) {
    state.currentContent.project_settings = payload.project_settings;
    state.currentContent.tavily_topic = payload.project_settings.tavily_topic || state.currentContent.tavily_topic;
  }
  if (payload.project) {
    state.currentProject = { ...state.currentProject, ...payload.project };
    const index = state.projects.findIndex((item) => item.id === payload.project.id);
    if (index >= 0) state.projects[index] = { ...state.projects[index], ...payload.project };
  }
}

function renderProductModeControls() {
  renderOutputLanguageControls();
  const settings = state.currentContent?.project_settings || {};
  const enabled = productModeEnabled();
  els.contentTypeButtons.forEach((button) => {
    const active = button.dataset.contentType === (enabled ? "product" : "editorial");
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
    button.disabled = !state.currentProject;
  });
  els.productSetupPanel?.classList.toggle("hidden", !enabled);
  const generateButton = document.getElementById("generate-content-btn");
  if (generateButton) generateButton.textContent = enabled ? "生成商品脚本" : "生成 content.md";
  if (els.briefInput) {
    els.briefInput.placeholder = enabled
      ? "补充商品故事、用户反馈、竞品差异、测试过程或本期想讲的角度。商品事实请填写在上方。"
      : "在这里整理主题、素材、想法，或者直接贴一份 brief。";
  }
  if (!enabled) return;

  const fields = [
    [els.productName, settings.product_name],
    [els.productCategory, settings.product_category],
    [els.productTargetCustomer, settings.product_target_customer],
    [els.productUsageScenarios, settings.product_usage_scenarios],
    [els.productSellingPoints, settings.product_selling_points],
    [els.productEvidence, settings.product_evidence],
    [els.productOffer, settings.product_offer],
    [els.productComplianceNotes, settings.product_compliance_notes],
  ];
  fields.forEach(([field, value]) => {
    if (field && document.activeElement !== field) field.value = value || "";
  });

  const assets = Array.isArray(settings.product_asset_files) ? settings.product_asset_files : [];
  if (els.productReferenceStatus) {
    els.productReferenceStatus.textContent = assets.length ? `图生图参考 ${assets.length} 张` : "尚未上传参考图";
    els.productReferenceStatus.className = assets.length ? "pill" : "pill pill--warn";
  }
  if (els.productAssetList) {
    els.productAssetList.innerHTML = assets.length
      ? assets.map((filename) => {
          const src = `${API_BASE}/data/projects/${state.currentProject.id}/uploads/products/${encodeURIComponent(filename)}?v=${Date.now()}`;
          return `
            <div class="product-asset-item">
              <img src="${escapeHtml(src)}" alt="${escapeHtml(filename)}" />
              <div class="product-asset-item__meta">
                <span title="${escapeHtml(filename)}">${escapeHtml(filename)}</span>
                <button class="product-asset-delete" type="button" data-delete-product-asset="${escapeHtml(filename)}" title="删除参考图" aria-label="删除参考图">×</button>
              </div>
            </div>
          `;
        }).join("")
      : `<span class="muted">上传商品正面、背面、细节或使用状态图。没有参考图时只生成品类场景，不虚构具体包装。</span>`;
  }
  if (els.productSettingsStatus) {
    const provider = configFieldValue("IMAGE_PROVIDER", "auto_no_apiyi");
    const autoReferenceProviders = new Set(["auto", "auto_no_apiyi", "ark", "cpa_image", "chatgpt_web_auto", "imageai_playground", "newapi", "third_party", "apiyi"]);
    els.productSettingsStatus.textContent = assets.length
      ? autoReferenceProviders.has(provider)
        ? "参考图将在生图时自动上传"
        : "当前是手动接力入口，请切换到网页自动化或火山方舟"
      : "先上传真实商品图，商品身份会更稳定";
  }
}

function stepValues() {
  return Array.from(document.querySelectorAll("[data-step]:checked")).map((el) => el.dataset.step);
}

function retryableJobSteps(job) {
  const steps = Array.isArray(job?.steps) ? job.steps.map((step) => String(step || "").trim()).filter(Boolean) : [];
  if (!steps.length || !["failed", "interrupted"].includes(String(job?.status || ""))) return [];
  const currentIndex = steps.indexOf(String(job?.current_step || ""));
  if (currentIndex >= 0) return steps.slice(currentIndex);
  const completed = new Set(
    (Array.isArray(job?.progress) ? job.progress : [])
      .filter((item) => ["success", "passed", "accepted_with_warnings"].includes(String(item?.status || "")))
      .map((item) => String(item?.key || "")),
  );
  const remaining = steps.filter((step) => !completed.has(step));
  return remaining.length ? remaining : steps;
}

function reportHtml(title, payload) {
  return `
    <div class="stack">
      <div class="card card--inner">
        <strong>${escapeHtml(title)}</strong>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "内存对象")}</div>
      </div>
      <pre class="json-box">${escapeHtml(JSON.stringify(payload.result, null, 2))}</pre>
    </div>
  `;
}

function sectionScore(section) {
  if (!section) return "—";
  return section.score ?? section.overall_score ?? "—";
}

function aiSupervisorsHtml(payload) {
  const result = payload.result || {};
  const dimensions = Array.isArray(result.dimensions) ? result.dimensions : [];
  const teachers = dimensions.length
    ? dimensions.map((item) => ({
        ...item,
        blocking: !item.passed,
        grade: item.passed ? "通过" : `未达到 ${item.minimum_score || 0} 分`,
        findings: [...(Array.isArray(item.evidence_quotes) ? item.evidence_quotes : []), item.reason].filter(Boolean),
        suggestions: item.repair_instruction ? [item.repair_instruction] : [],
      }))
    : (Array.isArray(result.teachers) ? result.teachers : []);
  const actions = dimensions.length
    ? dimensions.filter((item) => !item.passed).map((item) => item.repair_instruction).filter(Boolean)
    : (Array.isArray(result.next_actions) ? result.next_actions : []);
  const overallScore = result.weighted_total ?? result.overall_score ?? result.score ?? 0;
  const teacherHtml = teachers
    .map((item) => {
      const findings = Array.isArray(item.findings) ? item.findings : [];
      const suggestions = Array.isArray(item.suggestions) ? item.suggestions : [];
      return `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(item.name || item.key || "AI 老师")}</strong>
            <span class="pill ${item.blocking || Number(item.score || 0) < 60 ? "pill--warn" : ""}">${escapeHtml(String(item.score ?? 0))} 分</span>
          </div>
          <div class="muted">${escapeHtml(item.grade || "")}</div>
          ${findings.length ? `<div class="stack stack--sm">${findings.map((text) => `<div>${escapeHtml(text)}</div>`).join("")}</div>` : ""}
          ${suggestions.length ? `<div class="muted">建议：${suggestions.map(escapeHtml).join("；")}</div>` : ""}
        </article>
      `;
    })
    .join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>AI 六维总编审稿</strong>
          <span class="pill ${!result.passed || Number(overallScore) < 80 ? "pill--warn" : ""}">${escapeHtml(String(overallScore))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.summary || result.verdict || "")}</div>
        <div class="muted">结论：${result.passed ? "通过" : "未通过"} · 标准：${escapeHtml(result.rubric_version || "-")}</div>
        <div class="muted">来源：${escapeHtml(result.provider || "unknown")}${result.model || result.ai_model ? ` · ${escapeHtml(result.model || result.ai_model)}` : ""}</div>
        ${result.ai_error ? `<div class="notice notice--warn">${escapeHtml(result.ai_error)}</div>` : ""}
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/editorial_ai_score.json")}</div>
      </div>
      <div class="summary-grid">
        ${teachers
          .map(
            (item) => `
              <div class="summary-card">
                <strong>${escapeHtml(item.name || item.key || "")}</strong>
                <span>${escapeHtml(String(item.score ?? 0))} 分</span>
              </div>
            `
          )
          .join("")}
      </div>
      ${teacherHtml || `<div class="muted">暂无老师团评审。</div>`}
      ${
        actions.length
          ? `<div class="card card--inner"><strong>优先修改</strong><div class="stack stack--sm">${actions
              .map((item) => `<div class="muted">- ${escapeHtml(item)}</div>`)
              .join("")}</div></div>`
          : ""
      }
      <details>
        <summary>查看完整 JSON</summary>
        <pre class="json-box">${escapeHtml(JSON.stringify(result, null, 2))}</pre>
      </details>
    </div>
  `;
}

function qualityGateHtml(payload) {
  const result = payload.result || {};
  const sections = result.sections || {};
  const imageMetrics = sections.images?.metrics || {};
  const visualMetrics = sections.images?.visual?.metrics || {};
  const supervisorTeachers = Array.isArray(sections.supervisors?.teachers) ? sections.supervisors.teachers : [];
  const qualityActionDefs = {
    "image-prompts": { label: "重建图片提示词" },
    "rhythm-enhance": { label: "节奏增强" },
    "viral-rewrite": { label: "总编优化" },
    subtitles: { label: "重跑字幕" },
    "audio-subtitles": { label: "重跑配音+字幕" },
    "images-missing": { label: "补缺失图" },
    "covers-missing": { label: "补缺失封面" },
    images: { label: "重生成图片" },
    video: { label: "重新合成" },
  };
  const qualityActionForText = (text) => {
    const raw = String(text || "");
    if (!raw.trim()) return null;
    if (/(字幕|ASR|srt|字幕覆盖|字幕同步|字幕对齐|时间轴|时轴)/i.test(raw)) return "subtitles";
    if (/(音频|语音|配音|口播音频|TTS|豆包播客)/i.test(raw)) return "audio-subtitles";
    if (/(缺失.*封面|封面.*缺失|补缺失封面)/i.test(raw)) return "covers-missing";
    if (/(缺失.*图|图.*缺失|场景图.*不足|补缺失图|补图)/i.test(raw)) return "images-missing";
    if (/(图片提示词|提示词分层|弱提示词|固定画风|固定风格|画面提示词|图内文字|16:9|视觉|画面|图片吸引力|口播绑定|场景图语义|封面)/i.test(raw)) return "image-prompts";
    if (/(文案|脚本|开头|钩子|中段|结尾|互动|节奏|留存|转折|情绪曲线|口播)/i.test(raw)) return "rhythm-enhance";
    if (/(事实|来源|参考资料|资料不足|引用|合规|可信)/i.test(raw)) return "viral-rewrite";
    if (/(黑屏|成片|合成|视频)/i.test(raw)) return "video";
    return null;
  };
  const qualityActionButton = (key, primary = false) => {
    const action = qualityActionDefs[key];
    if (!action) return "";
    return `<button class="btn ${primary ? "btn--primary" : "btn--ghost"}" data-quality-action="${escapeHtml(key)}">${escapeHtml(action.label)}</button>`;
  };
  const imageSoftIssueRegex = /(图片吸引力|自检提示|画面节奏|场景差异度|固定画风|固定风格|生产元信息|个人 IP|吸引力偏弱|平均吸引力偏弱|偏暗|对比度|细节偏少|太素|弱提示词)/i;
  const qualityIssueActionButton = (item) => {
    const raw = `${item.label || ""} ${item.where || ""} ${item.issue || ""} ${item.fix || ""}`;
    const key = qualityActionForText(raw);
    const buttons = [];
    if (key) buttons.push(qualityActionButton(key));
    if (item.label === "图片" && item.level !== "risk" && imageSoftIssueRegex.test(raw)) {
      buttons.push(`<button class="btn btn--ghost" data-quality-ignore-images="video">忽略弱图并合成</button>`);
    }
    return buttons.length ? `<div class="toolbar toolbar--tight" style="margin-top:10px;">${buttons.join("")}</div>` : "";
  };
  const qualityNextActionHtml = (item) => {
    const key = qualityActionForText(item);
    return `
      <div class="section-head">
        <div class="muted">- ${escapeHtml(item)}</div>
        ${key ? `<div class="toolbar toolbar--tight">${qualityActionButton(key)}</div>` : ""}
      </div>
    `;
  };
  const sectionRows = [
    ["文案", sections.content],
    ["导演", sections.director],
    ["图片", sections.images],
    ["成片", sections.video],
    ["老师团", sections.supervisors],
  ];
  const imageIssues = Array.isArray(sections.images?.issues) ? sections.images.issues : [];
  const hasIgnorableImageIssue = imageIssues.some((item) => item?.level !== "risk" && imageSoftIssueRegex.test(`${item?.where || ""} ${item?.issue || ""} ${item?.fix || ""}`));
  const ignoredImageCount = Number(sections.images?.metrics?.ignored_image_soft_issue_count || 0);
  const imageOverrideActive = Boolean(sections.images?.metrics?.image_quality_override_active || sections.images?.image_quality_override?.active);
  const issueHtml = sectionRows
    .flatMap(([label, section]) => (section?.issues || []).map((item) => ({ label, ...item })))
    .slice(0, 16)
    .map(
      (item) => `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(item.label)} · ${escapeHtml(item.where || "")}</strong>
            <span class="pill ${item.level === "risk" ? "pill--warn" : ""}">${escapeHtml(item.level || "info")}</span>
          </div>
          <div>${escapeHtml(item.issue || "")}</div>
          ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
          ${qualityIssueActionButton(item)}
        </article>
      `
    )
    .join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>质量总检</strong>
          <span class="pill">${escapeHtml(String(result.overall_score ?? 0))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "内存对象")}</div>
        <div class="toolbar" style="margin-top:12px;">
          <button class="btn btn--primary" data-quality-repair="image-prompts">重建图片提示词</button>
          ${hasIgnorableImageIssue ? `<button class="btn btn--ghost" data-quality-ignore-images="video">忽略弱图并合成</button>` : ""}
          <button class="btn btn--ghost" data-quality-action="rhythm-enhance">节奏增强</button>
          <button class="btn btn--ghost" data-quality-action="subtitles">重跑字幕</button>
          <button class="btn btn--ghost" data-quality-refresh="true">重新质检</button>
        </div>
      </div>
      <div class="summary-grid">
        ${sectionRows
          .map(
            ([label, section]) => `
              <div class="summary-card">
                <strong>${escapeHtml(label)}</strong>
                <span>${escapeHtml(String(sectionScore(section)))} 分</span>
              </div>
            `
          )
          .join("")}
        <div class="summary-card"><strong>图片吸引力</strong><span>${escapeHtml(String(imageMetrics.avg_image_appeal_score ?? visualMetrics.avg_appeal_score ?? "—"))} 分</span></div>
        <div class="summary-card"><strong>低吸引力图</strong><span>${escapeHtml(String(imageMetrics.low_image_appeal_count ?? visualMetrics.low_appeal_count ?? 0))} 张</span></div>
        <div class="summary-card"><strong>提示词分层</strong><span>${escapeHtml(String(imageMetrics.image_prompt_layer_score ?? "—"))} 分</span></div>
        <div class="summary-card"><strong>弱提示词</strong><span>${escapeHtml(String(imageMetrics.weak_image_prompt_count ?? 0))} 条</span></div>
        <div class="summary-card"><strong>弱图忽略</strong><span>${imageOverrideActive ? `已放行 ${ignoredImageCount} 条` : "未开启"}</span></div>
      </div>
      ${imageOverrideActive ? `<div class="notice">已人工忽略亮度、对比度和风格等软弱项；语义错图、跨题材词、缺图和硬失败仍会继续检查。</div>` : ""}
      ${
        supervisorTeachers.length
          ? `<div class="card card--inner">
              <strong>AI 老师团</strong>
              <div class="summary-grid" style="margin-top:12px;">
                ${supervisorTeachers
                  .map(
                    (item) => `
                      <div class="summary-card">
                        <strong>${escapeHtml(item.name || item.key || "")}</strong>
                        <span>${escapeHtml(String(item.score ?? 0))} 分</span>
                      </div>
                    `
                  )
                  .join("")}
              </div>
              ${sections.supervisors?.ai_error ? `<div class="notice notice--warn">${escapeHtml(sections.supervisors.ai_error)}</div>` : ""}
            </div>`
          : ""
      }
      ${issueHtml || `<div class="muted">没有发现明显风险。</div>`}
      ${
        Array.isArray(result.next_actions) && result.next_actions.length
          ? `<div class="card card--inner"><strong>下一步建议</strong><div class="stack stack--sm">${result.next_actions
              .map((item) => qualityNextActionHtml(item))
              .join("")}</div></div>`
          : ""
      }
      <details>
        <summary>查看完整 JSON</summary>
        <pre class="json-box">${escapeHtml(JSON.stringify(result, null, 2))}</pre>
      </details>
    </div>
  `;
}

function viralRewriteHtml(result) {
  const before = result.before || {};
  const after = result.after || {};
  const provider = result.provider || "unknown";
  const deepseekError = result.deepseek_error || "";
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>一键总编优化</strong>
          <span class="pill ${provider.includes("failed") ? "pill--warn" : ""}">${escapeHtml(provider)}</span>
        </div>
        <div class="muted">${result.changed ? "content.md 已更新，图片确认状态会重新变为待确认。" : "没有检测到内容变化。"}</div>
        ${deepseekError ? `<div class="pill pill--warn">${escapeHtml(deepseekError)}</div>` : ""}
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>优化前</strong><span>${escapeHtml(String(before.overall_score ?? "—"))} 分</span></div>
        <div class="summary-card"><strong>优化后</strong><span>${escapeHtml(String(after.overall_score ?? "—"))} 分</span></div>
        <div class="summary-card"><strong>开头</strong><span>${escapeHtml(String(after.opening_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>中段</strong><span>${escapeHtml(String(after.retention_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>互动</strong><span>${escapeHtml(String(after.interaction_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>图片提示词</strong><span>${result.changed ? "已重建" : "未变化"}</span></div>
      </div>
      <div class="muted">${escapeHtml(after.verdict || "")}</div>
    </div>
  `;
}

function channelSignatureDisplay(value) {
  const labels = {
    binary_code_comment: "数字二选一评论",
    single_experience_comment: "只写一个经历",
    choice_comment: "选择题评论",
    stance_comment: "观点站队评论",
    engagement_command: "点赞收藏指令",
    open_question_comment: "开放式提问",
    personal_case: "亲历案例",
    data_evidence: "数字证据",
    comparison: "前后对比",
    step_solution: "分步解决",
    mechanism_explain: "机制拆解",
    consequence_reveal: "后果揭示",
    scene_explain: "场景解释",
    shrug_or_spread_hands: "摊手/耸肩",
    pointing_at_screen: "指向屏幕",
    looking_down_at_phone: "低头看手机",
    desk_computer_gaze: "坐在电脑前",
    holding_evidence: "举物展示",
    face_reaction: "人物表情反应",
    object_led: "物件主导",
    split_comparison: "左右对比",
    subject_one_side_title_space: "主体偏侧留标题",
    large_number_center: "大数字居中",
    person_phone_closeup: "人物手机近景",
    object_evidence_closeup: "证据物件特写",
    interface_scene: "屏幕界面构图",
    topic_scene: "主题场景",
  };
  return String(value || "")
    .split("+")
    .map((item) => labels[item] || item)
    .join(" + ") || "暂无";
}

function channelHistoryHtml(payload) {
  const result = payload.result || {};
  const repetition = result.repetition_monitor || {};
  const repetitionDimensions = repetition.dimensions || {};
  const repetitionWarnings = Array.isArray(repetition.warnings) ? repetition.warnings : [];
  const recommendations = Array.isArray(result.recommendations) ? result.recommendations : [];
  const hooks = Array.isArray(result.best_hooks) ? result.best_hooks : [];
  const keywords = Array.isArray(result.top_keywords) ? result.top_keywords : [];
  const weaknesses = Array.isArray(result.common_weaknesses) ? result.common_weaknesses : [];
  const topProjects = Array.isArray(result.top_projects) ? result.top_projects : [];
  const performance = result.performance_insights || {};
  const growthExperiment = performance.growth_experiment || {};
  const performanceMemory = result.performance_memory || {};
  const learnedRules = Array.isArray(performanceMemory.active_rules) ? performanceMemory.active_rules : [];
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>${escapeHtml(result.channel_name || result.template_key || "频道")} · 历史复盘</strong>
          <span class="pill">${escapeHtml(String(result.history_count || 0))} 个项目</span>
        </div>
        <div class="muted">已回填表现数据：${escapeHtml(String(result.with_release_metrics_count || 0))} 个项目</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/channel_history.json")}</div>
      </div>
      <div class="card card--inner">
        <div class="section-head">
          <strong>频道迭代大脑</strong>
          <span class="pill pill--accent">${escapeHtml(String(performanceMemory.sample_count || 0))} 个真实样本</span>
        </div>
        <div class="muted">按样本置信度和时间衰减持续更新。单期结果只形成带权证据，不会永久写死频道。</div>
        <div class="stack stack--sm">
          ${learnedRules.length
            ? learnedRules.slice(0, 8).map((item) => `<div class="muted">- ${item.kind === "strengths" ? "保留" : "修正"}：${escapeHtml(item.rule || "")}</div>`).join("")
            : `<div class="muted">发布后回填展现、播放、平均观看、完播和互动，系统会自动形成下一期约束。</div>`}
        </div>
      </div>
      <div class="card card--inner">
        <strong>下一条建议</strong>
        <div class="stack stack--sm">
          ${recommendations.length ? recommendations.map((item) => `<div class="muted">- ${escapeHtml(item)}</div>`).join("") : `<div class="muted">历史数据还不够，先继续生产并回填表现。</div>`}
        </div>
      </div>
      <div class="card card--inner">
        <div class="section-head">
          <strong>真实留存漏斗</strong>
          <span class="pill ${performance.primary_bottleneck && performance.primary_bottleneck !== "表现健康" ? "pill--warn" : ""}">${escapeHtml(performance.primary_bottleneck || "待回填")}</span>
        </div>
        <div class="summary-grid">
          <div class="summary-card"><strong>2 秒留存</strong><span>${escapeHtml(String(performance.average_two_second_retention_rate || 0))}%</span></div>
          <div class="summary-card"><strong>5 秒留存</strong><span>${escapeHtml(String(performance.average_five_second_retention_rate || 0))}%</span></div>
          <div class="summary-card"><strong>平均展现</strong><span>${escapeHtml(String(performance.average_impressions || 0))}</span></div>
          <div class="summary-card"><strong>平均点击率</strong><span>${escapeHtml(String(performance.average_click_through_rate || 0))}%</span></div>
          <div class="summary-card"><strong>平均观看</strong><span>${escapeHtml(String(performance.average_watch_seconds || 0))}秒</span></div>
          <div class="summary-card"><strong>完播率</strong><span>${escapeHtml(String(performance.average_completion_rate || 0))}%</span></div>
          <div class="summary-card"><strong>推算片长</strong><span>${escapeHtml(String(performance.median_estimated_duration_seconds || 0))}秒</span></div>
          <div class="summary-card"><strong>互动率</strong><span>${escapeHtml(String(performance.average_engagement_rate || 0))}%</span></div>
          <div class="summary-card"><strong>有效样本</strong><span>${escapeHtml(String(performance.sample_count || 0))}期</span></div>
        </div>
        <div class="muted">系统按真实投放数据判断问题发生在开场、前段承接、中后段还是互动，不再只看内部文案分。</div>
      </div>
      ${growthExperiment.kind && growthExperiment.kind !== "observe" ? `
        <div class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(growthExperiment.label || "下一期实验")}</strong>
            <span class="pill pill--accent">${escapeHtml(growthExperiment.duration_target || "数据驱动")}</span>
          </div>
          <div class="muted">${escapeHtml(growthExperiment.recommendation || "系统会按真实数据调整下一期策略。")}</div>
        </div>
      ` : ""}
      <div class="summary-grid">
        ${keywords.slice(0, 6).map((item) => `<div class="summary-card"><strong>${escapeHtml(item.keyword || "")}</strong><span>${escapeHtml(String(item.count || 0))} 次</span></div>`).join("")}
      </div>
      <div class="card card--inner">
        <div class="section-head">
          <strong>最近 20 期防重复</strong>
          <span class="pill ${repetitionWarnings.length ? "pill--warn" : ""}">${repetitionWarnings.length ? `${repetitionWarnings.length} 项撞车` : "本期有差异"}</span>
        </div>
        <div class="summary-grid">
          ${["opening_surface", "case_structure", "cta", "character_pose", "cover_composition"].map((key) => {
            const item = repetitionDimensions[key] || {};
            const current = channelSignatureDisplay(item.current);
            const repeats = Number(item.recent_repeat_count || 0);
            return `<div class="summary-card">
              <strong>${escapeHtml(item.label || key)}</strong>
              <span>${escapeHtml(current)} · 近 20 期 ${escapeHtml(String(repeats))} 次</span>
            </div>`;
          }).join("")}
        </div>
        ${repetitionWarnings.length ? `<div class="stack stack--sm">${repetitionWarnings.map((item) => `<div class="muted">- ${escapeHtml(item.instruction || "更换重复结构")}</div>`).join("")}</div>` : `<div class="muted">开场、案例、CTA、人物动作和封面构图暂未触发过密阈值。</div>`}
      </div>
      <div class="card card--inner">
        <strong>历史优质开头</strong>
        <div class="stack stack--sm">
          ${hooks.length ? hooks.slice(0, 6).map((item) => `
            <article class="card card--inner">
              <div class="section-head">
                <span>#${escapeHtml(String(item.project_id || ""))} ${escapeHtml(item.topic || "")}</span>
                <span class="pill">开头 ${escapeHtml(String(item.opening_score || 0))}</span>
              </div>
              <div>${escapeHtml(item.hook || "")}</div>
            </article>
          `).join("") : `<div class="muted">还没有可复用的开头样本。</div>`}
        </div>
      </div>
      <div class="card card--inner">
        <strong>常见问题</strong>
        <div class="stack stack--sm">
          ${weaknesses.length ? weaknesses.map((item) => `<div class="muted">- ${escapeHtml(item.issue || "")} · ${escapeHtml(String(item.count || 0))} 次</div>`).join("") : `<div class="muted">暂未统计到重复问题。</div>`}
        </div>
      </div>
      <details>
        <summary>表现较好的历史项目</summary>
        <div class="stack stack--sm">
          ${topProjects.map((item) => `
            <article class="card card--inner">
              <div class="section-head">
                <strong>#${escapeHtml(String(item.project_id || ""))} ${escapeHtml(item.title || item.topic || "")}</strong>
                <span class="pill">${escapeHtml(String(item.performance_score || 0))}</span>
              </div>
              <div class="muted">${escapeHtml(item.hook || "")}</div>
            </article>
          `).join("")}
        </div>
      </details>
    </div>
  `;
}

function optimizationPlanHtml(payload) {
  const result = payload.result || {};
  const summary = result.summary || {};
  const actions = Array.isArray(result.actions) ? result.actions : [];
  const reports = result.reports || {};
  const history = reports.channel_history || {};
  const actionButton = (action) => {
    const type = action.action_type || "";
    const label = escapeHtml(action.label || action.key || "执行");
    if (type === "viral_rewrite") return `<button class="btn btn--primary" data-auto-opt-action="viral-rewrite">${label}</button>`;
    if (type === "repair_image_prompts") return `<button class="btn btn--primary" data-quality-repair="image-prompts">${label}</button>`;
    if (type === "apply_resume_steps") {
      const steps = Array.isArray(action.payload?.steps) ? action.payload.steps.join(",") : "";
      return `<button class="btn btn--primary" data-apply-resume-steps="${escapeHtml(steps)}">${label}</button>`;
    }
    if (type === "release_checklist") return `<button class="btn btn--primary" data-auto-opt-action="release-checklist">${label}</button>`;
    if (type === "open_content") return `<button class="btn btn--ghost" data-auto-opt-action="open-content">${label}</button>`;
    return `<button class="btn btn--ghost" data-auto-opt-action="open-produce">${label}</button>`;
  };
  const actionHtml = actions
    .map((action) => `
      <article class="card card--inner">
        <div class="section-head">
          <strong>${escapeHtml(action.label || action.key || "")}</strong>
          <span class="pill">${escapeHtml(String(action.priority || 0))}</span>
        </div>
        <div class="muted">${escapeHtml(action.reason || "")}</div>
        <div class="toolbar">${actionButton(action)}</div>
      </article>
    `)
    .join("");
  const recs = Array.isArray(history.recommendations) ? history.recommendations : [];
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>智能优化路线</strong>
          <span class="pill ${Number(result.score || 0) < 72 ? "pill--warn" : ""}">${escapeHtml(String(result.score ?? 0))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/creative_optimization_plan.json")}</div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>质量</strong><span>${escapeHtml(String(summary.quality_score || 0))}</span></div>
        <div class="summary-card"><strong>节奏</strong><span>${escapeHtml(String(summary.rhythm_score || 0))}</span></div>
        <div class="summary-card"><strong>图片分层</strong><span>${escapeHtml(String(summary.image_layer_score || 0))}</span></div>
        <div class="summary-card"><strong>历史项目</strong><span>${escapeHtml(String(summary.history_count || 0))}</span></div>
        <div class="summary-card"><strong>投放反馈</strong><span>${escapeHtml(String(summary.release_metrics_count || 0))}</span></div>
        <div class="summary-card"><strong>生产状态</strong><span>${summary.ready_for_release ? "可发布" : summary.ready_for_video ? "可成片" : "待补齐"}</span></div>
      </div>
      <div class="card card--inner">
        <strong>推荐动作</strong>
        <div class="stack stack--sm">${actionHtml || `<div class="muted">当前没有明确动作，按目标继续生产或发布。</div>`}</div>
      </div>
      ${
        recs.length
          ? `<div class="card card--inner"><strong>频道记忆提醒</strong><div class="stack stack--sm">${recs
              .slice(0, 4)
              .map((item) => `<div class="muted">- ${escapeHtml(item)}</div>`)
              .join("")}</div></div>`
          : ""
      }
    </div>
  `;
}

function imagePromptLayersHtml(payload) {
  const result = payload.result || {};
  const metrics = result.metrics || {};
  const issues = Array.isArray(result.issues) ? result.issues : [];
  const entries = Array.isArray(result.entries) ? result.entries : [];
  const issueHtml = issues
    .slice(0, 10)
    .map((item) => `
      <article class="card card--inner">
        <div class="section-head">
          <strong>${escapeHtml(item.where || "图片提示词")}</strong>
          <span class="pill ${statusToneClass(item.level)}">${escapeHtml(item.level || "info")}</span>
        </div>
        <div>${escapeHtml(item.issue || "")}</div>
        ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
      </article>
    `)
    .join("");
  const entryHtml = entries
    .slice(0, 14)
    .map((item) => {
      const layers = item.layers || {};
      const layerLabels = [
        ["channel", "频道"],
        ["topic", "主题"],
        ["script_anchor", "口播"],
        ["subject_action", "主体动作"],
        ["emotion_conflict", "冲突"],
        ["text_rules", "文字"],
        ["safety", "禁忌"],
      ];
      return `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(item.label || item.target || "")}</strong>
            <span class="pill ${Number(item.score || 0) < 72 ? "pill--warn" : ""}">${escapeHtml(String(item.score || 0))} 分</span>
          </div>
          <div class="toolbar toolbar--tight">
            ${layerLabels.map(([key, label]) => `<span class="pill ${layers[key] ? "" : "pill--warn"}">${escapeHtml(label)} ${layers[key] ? "✓" : "缺"}</span>`).join("")}
          </div>
          ${Array.isArray(item.suggestions) && item.suggestions.length ? `<div class="muted">${item.suggestions.map(escapeHtml).join("；")}</div>` : ""}
        </article>
      `;
    })
    .join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>图片提示词分层</strong>
          <span class="pill">${escapeHtml(String(result.score ?? 0))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/image_prompt_layers.json")}</div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>提示词</strong><span>${escapeHtml(String(metrics.prompt_count || 0))}</span></div>
        <div class="summary-card"><strong>场景图</strong><span>${escapeHtml(String(metrics.scene_prompt_count || 0))}</span></div>
        <div class="summary-card"><strong>平均分层</strong><span>${escapeHtml(String(metrics.avg_layer_score || 0))}</span></div>
        <div class="summary-card"><strong>弱提示词</strong><span>${escapeHtml(String(metrics.weak_prompt_count || 0))}</span></div>
      </div>
      ${issueHtml || `<div class="muted">图片提示词分层没有明显风险。</div>`}
      <div class="card card--inner">
        <strong>逐张分层</strong>
        <div class="stack stack--sm">${entryHtml || `<div class="muted">暂无图片提示词。</div>`}</div>
      </div>
      <div class="toolbar">
        <button class="btn btn--primary" data-quality-repair="image-prompts">重建图片提示词</button>
      </div>
    </div>
  `;
}

function rhythmReportHtml(payload) {
  const result = payload.result || {};
  const metrics = result.metrics || {};
  const engagement = result.engagement || {};
  const issues = Array.isArray(result.issues) ? result.issues : [];
  const visualNotes = Array.isArray(result.visual_notes) ? result.visual_notes : [];
  const beats = Array.isArray(result.beats) ? result.beats : [];
  const issueHtml = issues
    .map((item) => `
      <article class="card card--inner">
        <div class="section-head">
          <strong>${escapeHtml(item.where || "节奏")}</strong>
          <span class="pill ${statusToneClass(item.level)}">${escapeHtml(item.level || "info")}</span>
        </div>
        <div>${escapeHtml(item.issue || "")}</div>
        ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
      </article>
    `)
    .join("");
  const visualNoteHtml = visualNotes
    .map((item) => `
      <div class="file-callout file-callout--compact">
        <div>
          <strong>${escapeHtml(item.where || "画面建议")}（不计文案节奏分）</strong>
          <div class="muted">${escapeHtml(item.issue || "")}</div>
          ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
        </div>
      </div>
    `)
    .join("");
  const beatHtml = beats
    .slice(0, 36)
    .map((item) => `
      <div class="step-item">
        <div>
          <strong>${escapeHtml(String(item.index || ""))}. ${escapeHtml(item.signal || "")}</strong>
          <div class="muted">${escapeHtml(item.text || "")}</div>
        </div>
        <span class="pill">${escapeHtml(String(item.chars || 0))}字</span>
      </div>
    `)
    .join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>脚本/成片节奏体检</strong>
          <span class="pill">${escapeHtml(String(result.score ?? 0))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/script_rhythm.json")}</div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>开头</strong><span>${escapeHtml(String(engagement.opening_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>中段</strong><span>${escapeHtml(String(engagement.retention_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>互动</strong><span>${escapeHtml(String(engagement.interaction_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>推进信号</strong><span>${escapeHtml(String(metrics.push_signal_count || 0))}</span></div>
        <div class="summary-card"><strong>最长平铺</strong><span>${escapeHtml(String(metrics.max_plain_gap || 0))}句</span></div>
        <div class="summary-card"><strong>单图停留</strong><span>${escapeHtml(String(metrics.avg_scene_hold_sec || 0))}秒</span></div>
      </div>
      ${issueHtml || `<div class="muted">节奏没有明显风险。</div>`}
      ${visualNoteHtml}
      <details>
        <summary>查看节奏拆解</summary>
        <div class="stack stack--sm">${beatHtml || `<div class="muted">暂无可拆解内容。</div>`}</div>
      </details>
    </div>
  `;
}

function rhythmEnhanceHtml(payload) {
  const result = payload.result || {};
  const edits = result.edits || {};
  const before = result.before || {};
  const after = result.after || {};
  const beforeMetrics = before.metrics || {};
  const afterMetrics = after.metrics || {};
  const afterIssues = Array.isArray(after.issues) ? after.issues : [];
  const issueHtml = afterIssues
    .slice(0, 4)
    .map((item) => `
      <article class="card card--inner">
        <div class="section-head">
          <strong>${escapeHtml(item.where || "节奏")}</strong>
          <span class="pill ${statusToneClass(item.level)}">${escapeHtml(item.level || "info")}</span>
        </div>
        <div>${escapeHtml(item.issue || "")}</div>
        ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
      </article>
    `)
    .join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>节奏增强完成</strong>
          <span class="pill">${escapeHtml(String(before.score ?? "—"))} → ${escapeHtml(String(after.score ?? "—"))} 分</span>
        </div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/script_rhythm_enhance.json")}</div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>拆长句</strong><span>${escapeHtml(String(edits.split_count || 0))}</span></div>
        <div class="summary-card"><strong>补转折</strong><span>${escapeHtml(String(edits.bridge_count || 0))}</span></div>
        <div class="summary-card"><strong>互动句</strong><span>${edits.interaction_added ? "已补" : "无需补"}</span></div>
        <div class="summary-card"><strong>最长平铺</strong><span>${escapeHtml(String(beforeMetrics.max_plain_gap || 0))} → ${escapeHtml(String(afterMetrics.max_plain_gap || 0))}</span></div>
        <div class="summary-card"><strong>长句数</strong><span>${escapeHtml(String(beforeMetrics.long_line_count || 0))} → ${escapeHtml(String(afterMetrics.long_line_count || 0))}</span></div>
      </div>
      ${issueHtml || `<div class="muted">增强后没有明显节奏风险。</div>`}
    </div>
  `;
}

function videoPreflightHtml(payload) {
  const result = payload.result || {};
  const blockers = Array.isArray(result.blockers) ? result.blockers : [];
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  const metrics = result.metrics || {};
  const timelineCount = Number(metrics.timeline_scene_count || 0);
  const sceneGenerated = Number(metrics.scene_generated || 0);
  const needsTimelineRepair = blockers.some((item) => item?.where === "场景时轴")
    || !metrics.timeline_exists
    || (sceneGenerated > 0 && timelineCount !== sceneGenerated);
  const issueText = (item) => `${item?.where || ""} ${item?.issue || ""} ${item?.fix || ""}`;
  const allPreflightIssues = blockers.concat(warnings);
  const hasOldVersionIssue = (text) => /早于最新|版本|旧|重生|重新生成/.test(text);
  const needsSubtitleRepair = blockers.some((item) => /字幕|ASR|语音识别|对齐/.test(issueText(item)));
  const needsAudioRepair = blockers.some((item) => /音频|配音|podcast|mp3|TTS/.test(issueText(item)));
  const isImageConfirmationIssue = (item) => /图片确认|尚未确认|没有确认|确认当前图片/.test(issueText(item));
  const hasImageConfirmationBlocker = blockers.some(isImageConfirmationIssue);
  const pendingCandidateCount = Number(state.sceneStatus?.candidate_group_count || state.imageReview?.scene_candidate_pending || 0)
    + Number(state.imageReview?.cover_candidate_pending || 0);
  const needsSceneRepair = allPreflightIssues.some((item) => !isImageConfirmationIssue(item) && /场景图|图片|出图/.test(issueText(item)));
  const needsSceneRegenerate = allPreflightIssues.some((item) => !isImageConfirmationIssue(item) && /场景图|图片|出图/.test(issueText(item)) && hasOldVersionIssue(issueText(item)));
  const needsCoverRepair = allPreflightIssues.some((item) => /封面/.test(issueText(item)));
  const needsReusableOldImages = allPreflightIssues.some((item) => /(场景图|图片|出图|封面)/.test(issueText(item)) && hasOldVersionIssue(issueText(item)));
  const actionButtonsFor = (item) => {
    const text = issueText(item);
    const actions = [];
    if (isImageConfirmationIssue(item)) {
      actions.push(`<button class="btn btn--primary" data-preflight-open-images="true">${pendingCandidateCount ? "查看并选择候选" : "查看当前图片"}</button>`);
      if (!pendingCandidateCount) {
        actions.push(`<button class="btn btn--ghost" data-preflight-confirm-images="true">确认当前图片</button>`);
      }
      return `<div class="toolbar toolbar--compact">${actions.join("")}</div>`;
    }
    if (/音频|配音|podcast|mp3|TTS/.test(text)) {
      actions.push(`<button class="btn btn--primary" data-preflight-run="audio,subtitles">生成配音+字幕</button>`);
      actions.push(`<button class="btn btn--ghost" data-preflight-run="audio,subtitles,video">配音后继续成片</button>`);
    }
    if (/字幕|ASR|语音识别|对齐/.test(text)) {
      actions.push(`<button class="btn btn--primary" data-preflight-run="subtitles">重做字幕</button>`);
      actions.push(`<button class="btn btn--ghost" data-preflight-run="subtitles,video">重做字幕后继续成片</button>`);
    }
    if (/场景图|图片|出图/.test(text)) {
      if (hasOldVersionIssue(text)) {
        actions.push(`<button class="btn btn--primary" data-preflight-run="images">重生成场景图</button>`);
        actions.push(`<button class="btn btn--ghost" data-preflight-run="images,video">重图后继续成片</button>`);
        actions.push(`<button class="btn btn--ghost" data-preflight-reuse-images="true">复用旧图</button>`);
      } else {
        actions.push(`<button class="btn btn--primary" data-preflight-run="images_missing">补缺失场景图</button>`);
        actions.push(`<button class="btn btn--ghost" data-preflight-run="images_missing,video">补图后继续成片</button>`);
      }
    }
    if (/封面/.test(text)) {
      if (hasOldVersionIssue(text)) {
        actions.push(`<button class="btn btn--primary" data-preflight-run="covers">重生封面</button>`);
        actions.push(`<button class="btn btn--ghost" data-preflight-reuse-images="true">复用旧封面</button>`);
      } else {
        actions.push(`<button class="btn btn--primary" data-preflight-run="covers_missing">补缺失封面</button>`);
      }
    }
    return actions.length ? `<div class="toolbar toolbar--compact">${actions.join("")}</div>` : "";
  };
  const issueCards = (items, label) => items
    .map(
      (item) => `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(label)} · ${escapeHtml(item.where || "")}</strong>
            <span class="pill ${label === "阻止项" ? "pill--warn" : ""}">${escapeHtml(item.level || "")}</span>
          </div>
          <div>${escapeHtml(item.issue || "")}</div>
          ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
          ${actionButtonsFor(item)}
        </article>
      `
    )
    .join("");
  const topActions = [
    needsAudioRepair ? `<button class="btn btn--primary" data-preflight-run="audio,subtitles,video">生成配音后继续成片</button>` : "",
    needsAudioRepair ? `<button class="btn btn--ghost" data-preflight-run="audio,subtitles">只生成配音+字幕</button>` : "",
    needsSubtitleRepair ? `<button class="btn btn--primary" data-preflight-run="subtitles,video">重做字幕后继续成片</button>` : "",
    needsSubtitleRepair ? `<button class="btn btn--ghost" data-preflight-run="subtitles">只重做字幕</button>` : "",
    needsSceneRegenerate ? `<button class="btn btn--primary" data-preflight-run="images">重生成场景图</button>` : "",
    needsSceneRepair && !needsSceneRegenerate ? `<button class="btn btn--ghost" data-preflight-run="images_missing,video">补图后继续成片</button>` : "",
    hasImageConfirmationBlocker ? `<button class="btn btn--primary" data-preflight-open-images="true">${pendingCandidateCount ? "查看并选择候选" : "查看当前图片"}</button>` : "",
    hasImageConfirmationBlocker && !pendingCandidateCount ? `<button class="btn btn--ghost" data-preflight-confirm-images="true">确认当前图片</button>` : "",
    needsCoverRepair ? `<button class="btn btn--ghost" data-preflight-run="covers">重生封面</button>` : "",
    needsReusableOldImages ? `<button class="btn btn--ghost" data-preflight-reuse-images="video">复用旧图继续成片</button>` : "",
    needsTimelineRepair ? `<button class="btn btn--primary" data-preflight-repair="timeline">重建场景时轴</button>` : "",
    `<button class="btn btn--ghost" data-preflight-refresh="true">重新总检</button>`,
    `<button class="btn btn--ghost" data-apply-resume-steps="${needsAudioRepair ? "audio,subtitles,video" : needsSubtitleRepair ? "subtitles,video" : needsSceneRegenerate ? "images,video" : "video"}">按建议修复并继续</button>`,
  ].filter(Boolean).join("");
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>成片前总检</strong>
          <span class="pill ${result.passed ? "" : "pill--warn"}">${result.passed ? "通过" : "未通过"}</span>
        </div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "内存对象")}</div>
        <div class="toolbar">
          ${topActions}
        </div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>音频</strong><span>${escapeHtml(String(metrics.audio_duration_sec ?? 0))} 秒</span></div>
        <div class="summary-card"><strong>字幕覆盖</strong><span>${escapeHtml(String(Math.round((metrics.subtitle_coverage || 0) * 100)))}%</span></div>
        <div class="summary-card"><strong>场景图</strong><span>${escapeHtml(String(metrics.scene_generated ?? 0))}/${escapeHtml(String(metrics.scene_expected ?? 0))}</span></div>
        <div class="summary-card"><strong>时轴段数</strong><span>${escapeHtml(String(metrics.timeline_scene_count ?? 0))}</span></div>
        <div class="summary-card"><strong>时轴语音</strong><span>${escapeHtml(String(metrics.timeline_body_sec ?? metrics.timeline_audio_sec ?? 0))} 秒</span></div>
        <div class="summary-card"><strong>节奏分</strong><span>${escapeHtml(String(metrics.rhythm_score ?? "—"))}</span></div>
        <div class="summary-card"><strong>字幕同步</strong><span>${metrics.root_subtitle_exists ? "已同步" : "未同步"}</span></div>
      </div>
      ${issueCards(blockers, "阻止项")}
      ${issueCards(warnings, "提醒")}
      ${!blockers.length && !warnings.length ? `<div class="muted">没有发现成片前风险。</div>` : ""}
    </div>
  `;
}

function resumePlanHtml(plan) {
  const steps = Array.isArray(plan.recommended_steps) ? plan.recommended_steps : [];
  const reasons = Array.isArray(plan.reasons) ? plan.reasons : [];
  const stepLabels = new Map(STEP_DEFS.map((item) => [item.key, item.label]));
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>续跑建议</strong>
          <span class="pill ${plan.can_resume ? "" : "pill--warn"}">${plan.can_resume ? "可续跑" : "无需续跑"}</span>
        </div>
        <div class="muted">场景图 ${escapeHtml(String(plan.scene_generated ?? 0))}/${escapeHtml(String(plan.scene_expected ?? 0))}，封面 ${escapeHtml(String(plan.cover_generated ?? 0))}/${escapeHtml(String(plan.cover_expected ?? 0))}</div>
      </div>
      <div class="card card--inner">
        <strong>后台建议执行</strong>
        <div class="muted">${steps.length ? steps.map((step) => stepLabels.get(step) || step).join("、") : "当前不需要自动续跑。"}</div>
        ${steps.length ? `<button class="btn btn--primary" data-apply-resume-steps="${escapeHtml(steps.join(","))}">立即续跑并保留已有素材</button>` : ""}
      </div>
      ${reasons.map((item) => `<div class="muted">- ${escapeHtml(item)}</div>`).join("")}
    </div>
  `;
}

function videoSelfCheckHtml(payload) {
  const result = payload.result || {};
  const metrics = result.metrics || {};
  const issues = Array.isArray(result.issues) ? result.issues : [];
  const issueHtml = issues
    .map(
      (item) => `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(item.where || "检查项")}</strong>
            <span class="pill ${statusToneClass(item.level)}">${escapeHtml(item.level || "info")}</span>
          </div>
          <div>${escapeHtml(item.issue || "")}</div>
          ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
        </article>
      `
    )
    .join("");
  const contactSheet = result.contact_sheet_url
    ? `
      <a class="self-check-sheet" href="${API_BASE}${escapeHtml(result.contact_sheet_url)}" target="_blank" rel="noreferrer">
        <img src="${API_BASE}${escapeHtml(result.contact_sheet_url)}" alt="成片抽帧联系图" />
      </a>
    `
    : `<div class="muted">暂无抽帧图。</div>`;
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>成片自检</strong>
          <span class="pill ${Number(result.score || 0) >= 72 ? "" : "pill--warn"}">${escapeHtml(String(result.score ?? 0))} 分</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/video_self_check.json")}</div>
      </div>
      <div class="summary-grid">
        <div class="summary-card"><strong>视频时长</strong><span>${escapeHtml(String(metrics.video_duration_sec ?? 0))} 秒</span></div>
        <div class="summary-card"><strong>音频时长</strong><span>${escapeHtml(String(metrics.audio_duration_sec ?? 0))} 秒</span></div>
        <div class="summary-card"><strong>字幕覆盖</strong><span>${escapeHtml(String(Math.round((metrics.subtitle_coverage || 0) * 100)))}%</span></div>
        <div class="summary-card"><strong>场景时轴</strong><span>${escapeHtml(String(metrics.timeline_scene_count ?? 0))}/${escapeHtml(String(metrics.scene_count ?? 0))}</span></div>
        <div class="summary-card"><strong>抽帧</strong><span>${escapeHtml(String(metrics.sampled_frame_count ?? 0))} 张</span></div>
        <div class="summary-card"><strong>黑屏段</strong><span>${escapeHtml(String(metrics.black_segment_count ?? 0))}</span></div>
      </div>
      <div class="card card--inner">
        <strong>抽帧联系图</strong>
        ${contactSheet}
      </div>
      ${issueHtml || `<div class="muted">没有发现明显黑屏、时长或字幕风险。</div>`}
      <details>
        <summary>查看完整 JSON</summary>
        <pre class="json-box">${escapeHtml(JSON.stringify(result, null, 2))}</pre>
      </details>
    </div>
  `;
}

function releaseChecklistHtml(payload) {
  const result = payload.result || {};
  const checks = Array.isArray(result.checks) ? result.checks : [];
  const checkHtml = checks
    .map(
      (item) => `
        <article class="card card--inner">
          <div class="section-head">
            <strong>${escapeHtml(item.label || item.key || "")}</strong>
            <span class="pill ${statusToneClass(item.status)}">${escapeHtml(item.status || "ok")}</span>
          </div>
          <div>${escapeHtml(item.detail || "")}</div>
          ${item.fix ? `<div class="muted">建议：${escapeHtml(item.fix)}</div>` : ""}
        </article>
      `
    )
    .join("");
  const assets = result.publish_assets || {};
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>发布前检查</strong>
          <span class="pill ${result.passed ? "" : "pill--warn"}">${result.passed ? "可发布" : "需处理"}</span>
        </div>
        <div class="muted">${escapeHtml(result.verdict || "")}</div>
        <div class="muted">报告路径：${escapeHtml(payload.report_path || "reports/release_checklist.json")}</div>
      </div>
      <div class="card card--inner">
        <strong>发布素材</strong>
        <div class="muted">标题：${escapeHtml(assets.title || "")}</div>
        <div class="muted">标签：${escapeHtml(assets.tags || "")}</div>
      </div>
      ${checkHtml || `<div class="muted">暂无检查项。</div>`}
    </div>
  `;
}

function autoTopicCandidatesFromTask(task) {
  if (!task || typeof task !== "object") return [];
  const candidates = Array.isArray(task.topic_candidates) ? task.topic_candidates.filter(Boolean) : [];
  if (candidates.length) return candidates;
  const queued = Array.isArray(task.queued_topics) ? task.queued_topics.filter(Boolean) : [];
  if (queued.length) return queued;
  const topic = String(task.topic || task.result?.topic || "").trim();
  return topic ? [{ title: topic, source: "latest" }] : [];
}

function autoTopicPayloadFromTask(task, key) {
  if (!task || task.template_key !== key) return null;
  const candidates = autoTopicCandidatesFromTask(task);
  if (!candidates.length) return null;
  const picked = candidates.find((item) => String(item?.title || "").trim() === String(task.topic || "").trim()) || candidates[0];
  return {
    template_key: key,
    provider: task.status ? `latest:${task.status}` : "latest",
    picked,
    candidates,
    queued_topics: Array.isArray(task.queued_topics) ? task.queued_topics : candidates,
    count: candidates.length,
    from_latest_task: true,
  };
}

function autoVideoStatusHtml() {
  const task = state.autoVideo || {};
  if (!task.id) {
    return `<div class="muted">暂无自动挖题成片任务。</div>`;
  }
  const projectId = Number(task.project_id || task.result?.project_id || 0);
  const finalVideo = task.result?.final_video || null;
  const miningPrompt = String(task.mining_prompt || "").trim();
  const topicCandidates = autoTopicCandidatesFromTask(task);
  const queueTotal = Number(task.queue_total || task.count || 0);
  const queueIndex = Number(task.queue_index || 0);
  const queueText = queueTotal > 1 ? ` · 队列：${queueIndex || 1}/${queueTotal}` : "";
  const statusClass = task.status === "succeeded" ? "" : ["failed", "cancelled", "interrupted"].includes(task.status) ? "pill--warn" : "";
  const runningActions = task.running
    ? `<button class="btn btn--ghost" data-cancel-auto-video="true">取消任务</button>`
    : "";
  const projectAction = projectId
    ? `<button class="btn btn--primary" data-open-auto-video-project="${projectId}">打开项目 #${projectId}</button>`
    : "";
  const continueAction = projectId && ["failed", "interrupted"].includes(task.status)
    ? `<button class="btn btn--primary" data-auto-video-continue-project="${projectId}">自动修复并继续生产</button>`
    : "";
  const finalAction = finalVideo?.url
    ? `<button class="btn btn--ghost" data-open-project-file="releases/final-video.mp4" data-open-project-file-project="${projectId}">打开 final-video.mp4</button>`
    : "";
  return `
    <div class="stack">
      <div class="card card--inner">
        <div class="section-head">
          <strong>自动挖题成片</strong>
          <span class="pill ${statusClass}">${escapeHtml(task.status || "idle")}</span>
        </div>
        <div class="muted">频道：${escapeHtml(task.template_key || "-")} · 阶段：${escapeHtml(task.stage || "-")}${escapeHtml(queueText)} · 主题：${escapeHtml(task.topic || "-")}</div>
        ${miningPrompt ? `<div class="muted">本次提示词：${escapeHtml(miningPrompt)}</div>` : ""}
        ${
          topicCandidates.length
            ? `<div class="stack stack--sm">${topicCandidates
                .slice(0, 6)
                .map((item, index) => `<div class="muted">${index + 1}. ${escapeHtml(item?.title || "")}${item?.score ? ` · ${escapeHtml(String(item.score))}分` : ""}</div>`)
                .join("")}</div>`
            : ""
        }
        ${task.error ? `<div class="pill pill--warn">${escapeHtml(task.error)}</div>` : ""}
        ${finalVideo?.absolute_path ? `<div class="mono-path">${escapeHtml(finalVideo.absolute_path)}</div>` : ""}
        <div class="toolbar">
          <button class="btn btn--ghost" data-refresh-auto-video="true">刷新状态</button>
          ${continueAction}
          ${projectAction}
          ${finalAction}
          ${runningActions}
        </div>
      </div>
      <pre class="json-box" style="white-space:pre-wrap;max-height:360px;overflow:auto;">${escapeHtml(task.log || "等待任务日志...")}</pre>
    </div>
  `;
}

function renderAutoVideoModal() {
  if (!state.autoVideoModalVisible) return;
  els.modalTitle.textContent = "自动挖题成片";
  els.modalBody.innerHTML = autoVideoStatusHtml();
  els.modal.classList.remove("hidden");
}

function autoVideoDraftForTemplate(key) {
  const latestPrompt = state.autoVideo?.template_key === key ? String(state.autoVideo?.mining_prompt || "") : "";
  const draft = state.autoVideoDrafts[key] || {};
  return {
    miningPrompt: draft.miningPrompt || latestPrompt,
    topicPayload: draft.topicPayload || null,
  };
}

async function resumeContentGenerationWhenMissing(project, plan) {
  if (!project) return false;
  const blockedStage = String(plan?.blocked_stage || "").trim().toLowerCase();
  const reasons = Array.isArray(plan?.reasons) ? plan.reasons.join(" ") : "";
  const contentStatus = String(plan?.content_generation?.status || "").trim().toLowerCase();
  const editorIsEmpty = !String(els.contentInput?.value || "").trim();
  const contentIsMissing = blockedStage === "content_missing"
    || (editorIsEmpty && ["failed", "idle", "", "cancelled"].includes(contentStatus))
    || /文案为空|content\.md.*(?:为空|生成)/i.test(reasons);
  if (!contentIsMissing) return false;
  const task = await api(`/api/auto-video/continue/${project.id}`, { method: "POST" });
  state.autoVideo = task;
  await Promise.all([
    refreshAutoVideoStatus(),
    refreshContentBundle(),
    refreshProductionManifest(),
    refreshProjectStatus(),
  ]);
  return true;
}

function openAutoVideoStartModal(key) {
  if (!state.backendOnline) return window.alert("请先启动后端。");
  const template = state.templates.find((item) => item.key === key);
  if (!template) return window.alert("没有找到这个频道模板。");
  if (state.autoVideo?.running) {
    state.autoVideoModalVisible = true;
    renderAutoVideoModal();
    return window.alert("当前已有自动挖题任务正在运行，先处理这一个。");
  }
  const draft = autoVideoDraftForTemplate(key);
  showModal(
    `自动挖题成片 · ${template.key}`,
    `
      <div class="stack">
        <div class="muted">系统先检索近 7 天真实事件，再按频道定位提炼选题。留空时会从频道方向中自动寻找。</div>
        <div class="form-grid">
          <label class="form-grid__wide">
            <span>这次想关注什么（可选）</span>
            <textarea id="modal-auto-video-prompt" class="text-editor text-editor--short" placeholder="例：智能驾驶最近一周的新变化，对普通车主有什么实际影响">${escapeHtml(draft.miningPrompt)}</textarea>
          </label>
          <input id="modal-auto-video-count" type="hidden" value="6" />
          <input id="modal-auto-video-topic" type="hidden" value="news" />
        </div>
        <div id="modal-auto-video-mine-status" class="muted">先检索真实事件，再生成候选，通常需要 20—35 秒。</div>
        <div id="modal-auto-video-candidates" class="stack stack--sm"></div>
        <div class="toolbar">
          <button id="modal-auto-video-mine-btn" class="btn btn--primary">挖出候选</button>
          <button id="modal-auto-video-start-selected-btn" class="btn btn--ghost" disabled>用勾选主题成片</button>
          <button id="modal-auto-video-start-btn" class="btn btn--ghost">AI 选最佳并成片</button>
          <button class="btn btn--ghost" data-close-modal="true">取消</button>
        </div>
      </div>
    `,
    (body) => {
      const promptInput = body.querySelector("#modal-auto-video-prompt");
      const countInput = body.querySelector("#modal-auto-video-count");
      const topicInput = body.querySelector("#modal-auto-video-topic");
      const candidateBox = body.querySelector("#modal-auto-video-candidates");
      const mineStatus = body.querySelector("#modal-auto-video-mine-status");
      const mineButton = body.querySelector("#modal-auto-video-mine-btn");
      const selectedButton = body.querySelector("#modal-auto-video-start-selected-btn");
      const startButton = body.querySelector("#modal-auto-video-start-btn");
      const renderCandidates = (payload) => {
        const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
        if (!candidateBox) return;
        if (!candidates.length) {
          if (selectedButton) selectedButton.disabled = true;
          const qualityMessage = payload?.quality_summary?.message || "点击“挖出候选”开始检索近期事件。";
          candidateBox.innerHTML = `<div class="file-callout"><strong>本轮结果</strong><div class="muted">${escapeHtml(qualityMessage)}</div></div>`;
          return;
        }
        const qualitySummary = payload?.quality_summary || {};
        const grokUsed = payload?.primary_search_provider === "grok";
        candidateBox.innerHTML = `
          <div class="section-head">
            <div>
              <strong>候选选题</strong>
              <div class="muted">${escapeHtml(qualitySummary.message || "按近期依据和频道贴合度排序。")}</div>
            </div>
            <span class="pill">${Number(qualitySummary.strong_count || 0)} 个可直接生产</span>
            <span class="pill ${grokUsed ? "pill--success" : "pill--warn"}">${grokUsed ? `Grok 主检索 · ${Number(qualitySummary.grok_reference_count || 0)} 条` : payload.grok2api_configured ? "Grok 本轮未返回" : "Grok 未配置"}</span>
          </div>
          <div id="modal-auto-video-selected-hint" class="muted">请勾选要生成的候选；可多选，会按列表顺序逐个成片。</div>
          ${candidates
            .map((item, index) => {
              const evidence = Array.isArray(item.news_evidence) ? item.news_evidence : [];
              const sourceCount = Number(item.independent_source_count || 0);
              const latestAge = Number.isFinite(Number(item.latest_age_days)) ? Number(item.latest_age_days) : null;
              const readiness = item.readiness || (sourceCount >= 2 ? "strong" : "review");
              const readinessLabel = item.readiness_label || (readiness === "strong" ? "可直接生产" : "建议复核");
              const issues = Array.isArray(item.quality_issues) ? item.quality_issues.filter(Boolean) : [];
              return `
              <label class="card card--inner">
                <div class="section-head">
                  <span><input class="auto-topic-check" type="checkbox" data-topic-index="${index}" /> ${escapeHtml(item.title || "")}</span>
                  <span class="toolbar">
                    <span class="pill ${readiness === "strong" ? "pill--success" : readiness === "weak" ? "pill--danger" : "pill--warn"}">${escapeHtml(readinessLabel)}</span>
                    <span class="pill">${escapeHtml(String(item.rank_score || item.score || "-"))}分</span>
                  </span>
                </div>
                ${item.brief ? `<div class="muted">${escapeHtml(item.brief)}</div>` : ""}
                <div class="topic-candidate-signals">
                  <span>Grok 证据 ${Number(item.grok_evidence_count || 0)} 条</span>
                  <span>${sourceCount} 个独立来源</span>
                  <span>${latestAge === null ? "日期待核验" : latestAge === 0 ? "今天" : `${latestAge} 天前`}</span>
                  <span>历史重复 ${Math.round(Number(item.duplicate_penalty || 0) * 100)}%</span>
                </div>
                ${issues.length ? `<div class="muted topic-candidate-warning">待处理：${escapeHtml(issues.join("、"))}</div>` : ""}
                ${evidence.length ? `<details><summary>查看依据</summary>${evidence.slice(0, 2).map((ref) => `<div class="muted">${escapeHtml(ref.published_date || "日期待核验")} · ${escapeHtml(ref.title || "")}</div>`).join("")}</details>` : ""}
              </label>
            `;
            })
            .join("")}
        `;
        const updateSelectedState = () => {
          const selectedCount = candidateBox.querySelectorAll(".auto-topic-check:checked").length;
          const hint = candidateBox.querySelector("#modal-auto-video-selected-hint");
          if (selectedButton) selectedButton.disabled = selectedCount <= 0;
          if (hint) {
            hint.textContent = selectedCount
              ? `已选择 ${selectedCount} 个候选，会按列表顺序逐个成片。`
              : "请勾选要生成的候选；可多选，会按列表顺序逐个成片。";
          }
        };
        candidateBox.querySelectorAll(".auto-topic-check").forEach((input) => {
          input.addEventListener("change", updateSelectedState);
        });
        updateSelectedState();
      };
      renderCandidates(draft.topicPayload);
      const fetchCandidates = async () => {
        const online = await checkBackend();
        if (!online) {
          const message = `后端未连接（${API_BASE}），本次检索没有启动。请重新打开短片工坊。`;
          if (mineStatus) mineStatus.textContent = message;
          if (candidateBox) candidateBox.innerHTML = `<div class="card card--inner"><strong>没有开始检索</strong><div class="muted topic-candidate-warning">${escapeHtml(message)}</div></div>`;
          throw new Error(message);
        }
        const miningPrompt = promptInput?.value?.trim() || "";
        const count = Math.max(1, Math.min(Number(countInput?.value || 6), 12));
        const tavilyTopic = topicInput?.value?.trim() || "news";
        state.autoVideoDrafts[key] = { miningPrompt, topicPayload: null };
        const startedAt = Date.now();
        if (mineStatus) mineStatus.textContent = "正在检索近 7 天事件和来源... 0 秒";
        const statusTimer = window.setInterval(() => {
          if (!mineStatus) return;
          const elapsed = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
          const phase = elapsed < 12 ? "正在检索近 7 天事件和来源" : elapsed < 24 ? "正在交叉核对日期与来源" : "正在去重并按频道价值排序";
          mineStatus.textContent = `${phase}... ${elapsed} 秒`;
        }, 1000);
        let payload;
        try {
          payload = await api(`/api/templates/${encodeURIComponent(key)}/auto-topics/mine`, {
            method: "POST",
            body: JSON.stringify({
              count,
              tavily_topic: tavilyTopic,
              mining_prompt: miningPrompt,
            }),
          });
        } finally {
          window.clearInterval(statusTimer);
        }
        state.autoVideoDrafts[key] = { miningPrompt, topicPayload: payload };
        renderCandidates(payload);
        if (mineStatus) {
          const returnedCount = Number(payload?.quality_summary?.returned_count ?? payload?.candidates?.length ?? 0);
          mineStatus.textContent = `检索完成，保留 ${returnedCount} 个有依据的候选。`;
        }
        return payload;
      };
      mineButton?.addEventListener("click", async () => {
        try {
          await withBusyButton(mineButton, "正在挖候选...", async () => {
            await fetchCandidates();
          });
        } catch (error) {
          const message = error?.message || "候选检索失败。";
          if (mineStatus) mineStatus.textContent = message;
          if (candidateBox && !candidateBox.textContent.trim()) {
            candidateBox.innerHTML = `<div class="card card--inner"><strong>检索失败</strong><div class="muted topic-candidate-warning">${escapeHtml(message)}</div></div>`;
          }
        }
      });
      selectedButton?.addEventListener("click", async () => {
        const miningPrompt = promptInput?.value?.trim() || "";
        const tavilyTopic = topicInput?.value?.trim() || "general";
        const payload = state.autoVideoDrafts[key]?.topicPayload || null;
        const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
        const selectedTopics = Array.from(body.querySelectorAll(".auto-topic-check:checked"))
          .map((input) => candidates[Number(input.dataset.topicIndex)])
          .filter(Boolean);
        if (!selectedTopics.length) {
          window.alert("请先勾选至少一个候选选题。");
          return;
        }
        state.autoVideoDrafts[key] = { miningPrompt, topicPayload: payload };
        await withBusyButton(selectedButton, "正在启动队列...", async () => {
          await startAutoVideoForTemplate(key, { miningPrompt, tavilyTopic, selectedTopics });
        });
      });
      startButton?.addEventListener("click", async () => {
        const miningPrompt = promptInput?.value?.trim() || "";
        const tavilyTopic = topicInput?.value?.trim() || "news";
        await withBusyButton(startButton, "正在选最佳主题...", async () => {
          let payload = state.autoVideoDrafts[key]?.topicPayload || null;
          if (!Array.isArray(payload?.candidates) || !payload.candidates.length) {
            payload = await fetchCandidates();
          }
          const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];
          const best = candidates.find((item) => item.readiness === "strong")
            || candidates.find((item) => item.readiness !== "weak")
            || candidates[0];
          if (!best) throw new Error("本轮没有形成可用候选，请换一个更具体的关注方向。");
          await startAutoVideoForTemplate(key, { miningPrompt, tavilyTopic, selectedTopics: [best] });
        });
      });
    }
  );
}

async function startAutoVideoForTemplate(key, { miningPrompt = "", tavilyTopic = "general", autoConfirmImages = true, selectedTopics = [] } = {}) {
  if (!state.backendOnline) return window.alert("请先启动后端。");
  const template = state.templates.find((item) => item.key === key);
  if (!template) return window.alert("没有找到这个频道模板。");
  const selectedQueue = Array.isArray(selectedTopics) ? selectedTopics.filter(Boolean) : [];
  state.autoVideoOpenedProjectId = null;
  state.autoVideo = await api(`/api/templates/${encodeURIComponent(key)}/auto-video`, {
    method: "POST",
    body: JSON.stringify({
      count: selectedQueue.length || 1,
      tavily_topic: tavilyTopic,
      mining_prompt: miningPrompt,
      auto_confirm_images: autoConfirmImages,
      selected_topics: selectedQueue,
    }),
  });
  state.autoVideoModalVisible = true;
  renderAutoVideoModal();
  startAutoVideoPolling();
}

async function openImageRegenerateModal(kind, target, label, asCandidate = false) {
  const project = ensureProject();
  if (!project) return;
  let promptPayload = { prompt: "" };
  try {
    promptPayload = await api(`/api/projects/${project.id}/image-prompt?kind=${encodeURIComponent(kind)}&target=${encodeURIComponent(target)}`);
  } catch (error) {
    window.alert(error.message || "读取当前提示词失败。");
    return;
  }
  const anchorOptions = Array.isArray(promptPayload.anchor_options) ? promptPayload.anchor_options : [];
  const abstractionOptions = Array.isArray(promptPayload.abstraction_options) && promptPayload.abstraction_options.length
    ? promptPayload.abstraction_options
    : [
        { value: "literal", label: "贴着口播" },
        { value: "balanced", label: "平衡" },
        { value: "conceptual", label: "更抽象" },
      ];
  const recommendedAnchorKey = promptPayload.recommended_anchor_key || "";
  const currentAnchorKey = promptPayload.anchor_key || recommendedAnchorKey || "";
  const currentAbstractionLevel = promptPayload.abstraction_level || "balanced";
  const configuredImageProvider = configFieldValue("IMAGE_PROVIDER", "auto_no_apiyi");
  const isDesktopHandoff = configuredImageProvider === "chatgpt_desktop_handoff";
  const regenerateButtonLabel = isDesktopHandoff
    ? "复制提示词并打开 Classic"
    : asCandidate
      ? "生成 1 张备选"
      : "生成 / 重绘这一张";
  const providerHelp = isDesktopHandoff
    ? "Classic 是手动接力：工坊会自动存档并复制中文提示词、打开桌面程序；你需要手动粘贴发送并保存生成图片。"
    : asCandidate
      ? "只额外生成 1 张待审备选，当前正式图不会被覆盖。满意后再点“采用”，再次生成会替换这张备选，不会继续累加。"
      : "频道定气质，主题定方向，锚点决定这一张画哪句口播。你可以改写完整提示词，也可以只写追加要求；重绘成功后会自动把图片确认状态改为待确认。";
  const anchorSelectOptions = [
    `<option value="">自动推荐${recommendedAnchorKey ? "（当前建议）" : ""}</option>`,
    ...anchorOptions.map((item) => {
      const key = item.key || "";
      const selected = key === currentAnchorKey ? "selected" : "";
      return `<option value="${escapeHtml(key)}" ${selected}>${escapeHtml(item.label || key)}</option>`;
    }),
  ].join("");
  const abstractionSelectOptions = abstractionOptions
    .map((item) => {
      const value = item.value || "balanced";
      const selected = value === currentAbstractionLevel ? "selected" : "";
      return `<option value="${escapeHtml(value)}" ${selected}>${escapeHtml(item.label || value)}</option>`;
    })
    .join("");
  showModal(
    `${asCandidate ? "生成备选图" : "重绘图片"} · ${label || target}`,
    `
      <div class="stack">
        <div class="form-grid">
          <label>
            <span>对应口播锚点</span>
            <select id="modal-image-anchor">${anchorSelectOptions}</select>
          </label>
          <div id="modal-image-anchor-preview" class="form-grid__wide muted"></div>
        </div>
        <label class="form-grid__wide">
          <span>我想怎么改</span>
          <textarea id="modal-image-extra" class="text-editor text-editor--small" placeholder="例如：车型必须是 MPV；不要头盔；刹车结构要清楚可辨认"></textarea>
        </label>
        <label>
          <span>改写范围</span>
          <select id="modal-image-rewrite-scope">
            <option value="partial" selected>局部改写（保留其它内容）</option>
            <option value="full">整体改写（重新设计画面）</option>
          </select>
        </label>
        <div class="toolbar">
          <button id="modal-image-rewrite-prompt" class="btn btn--ghost">按我的要求重做提示词</button>
        </div>
        <label class="form-grid__wide">
          <span>最终发送给当前生图渠道的完整提示词</span>
          <textarea id="modal-image-prompt" class="text-editor media-card__prompt" readonly placeholder="填写修改要求并点击“按我的要求重做提示词”后，这里才显示实际发送内容。"></textarea>
        </label>
        <details class="form-grid__wide">
          <summary>高级控制</summary>
          <label>
            <span>抽象强度</span>
            <select id="modal-image-abstraction">${abstractionSelectOptions}</select>
          </label>
          <label>
            <span>系统基础画面要求（只读）</span>
            <textarea id="modal-image-base-prompt" class="text-editor text-editor--small" readonly></textarea>
          </label>
        </details>
        <div class="muted">${escapeHtml(providerHelp)}</div>
        <div class="toolbar">
          <button id="modal-image-regenerate" class="btn btn--primary">${escapeHtml(regenerateButtonLabel)}</button>
          <button id="modal-chatgpt-login" class="btn btn--ghost">重新登录 ChatGPT</button>
          <button class="btn btn--ghost" data-close-modal="true">取消</button>
        </div>
        <div id="modal-image-regenerate-status" class="regen-status"></div>
        <pre id="modal-image-regenerate-log" class="log-view log-view--compact">等待提交单张重绘</pre>
      </div>
    `,
    (body) => {
      const anchorSelect = body.querySelector("#modal-image-anchor");
      const abstractionSelect = body.querySelector("#modal-image-abstraction");
      const promptInput = body.querySelector("#modal-image-prompt");
      const extraInput = body.querySelector("#modal-image-extra");
      const anchorPreview = body.querySelector("#modal-image-anchor-preview");
      const basePromptInput = body.querySelector("#modal-image-base-prompt");
      const rewriteButton = body.querySelector("#modal-image-rewrite-prompt");
      const rewriteScope = body.querySelector("#modal-image-rewrite-scope");
      const button = body.querySelector("#modal-image-regenerate");
      const reloginButton = body.querySelector("#modal-chatgpt-login");
      const status = body.querySelector("#modal-image-regenerate-status");
      const redrawLog = body.querySelector("#modal-image-regenerate-log");
      const appendRedrawLog = (message) => {
        const stamp = new Date().toLocaleTimeString("zh-CN", { hour12: false });
        redrawLog.textContent = `${redrawLog.textContent}\n[${stamp}] ${message}`.trim();
        redrawLog.scrollTop = redrawLog.scrollHeight;
      };
      const findAnchorText = (selectedKey) => {
        const effectiveKey = selectedKey || recommendedAnchorKey || "";
        const match = anchorOptions.find((item) => item.key === effectiveKey);
        return match?.text || "";
      };
      const renderAnchorPreview = () => {
        const selectedText = findAnchorText(anchorSelect.value);
        anchorPreview.textContent = selectedText
          ? `当前锚点：${selectedText}`
          : "当前会自动使用系统为这张图推荐的口播锚点。";
      };
      let previewTimer = null;
      let previewVersion = 0;
      let latestBasePrompt = "";
      let previewRequirement = "";
      button.disabled = true;
      const refreshSuggestedPrompt = async (rewritePrompt = false) => {
        const requestVersion = ++previewVersion;
        const requirement = extraInput?.value?.trim() || "";
        status.textContent = rewritePrompt ? "AI 视觉导演正在按补充词重做整份提示词..." : "正在编译最终发送提示词...";
        button.disabled = true;
        rewriteButton.disabled = true;
        try {
          const nextPayload = await api(`/api/projects/${project.id}/image-prompt/preview`, {
            method: "POST",
            body: JSON.stringify({
              kind,
              target,
              prompt: "",
              anchor_key: anchorSelect.value,
              abstraction_level: abstractionSelect.value,
              additional_requirement: requirement,
              rewrite_prompt: rewritePrompt,
              rewrite_scope: rewriteScope.value,
              as_candidate: asCandidate,
            }),
          });
          if (requestVersion !== previewVersion) return;
          promptInput.value = nextPayload.final_outbound_prompt || "";
          basePromptInput.value = nextPayload.base_prompt || "";
          latestBasePrompt = nextPayload.base_prompt || "";
          previewRequirement = requirement;
          status.textContent = rewritePrompt
            ? `已用 ${nextPayload.rewrite_provider || "当前模型"} 完成${rewriteScope.value === "full" ? "整体" : "局部"}改写；检查后可开始重绘。`
            : "原始提示词已就绪；填写修改要求后先点击“按我的要求重做提示词”。";
          if (rewritePrompt) {
            appendRedrawLog(`提示词改写完成，模型：${nextPayload.rewrite_provider || "当前模型"}，长度：${latestBasePrompt.length} 字。`);
            appendRedrawLog("下一步：点击蓝色“生成 / 重绘这一张”提交 CPA 生图。");
            button.textContent = "提示词已就绪 · 点击开始 CPA 生图";
          }
          renderAnchorPreview();
        } catch (error) {
          if (requestVersion !== previewVersion) return;
          promptInput.value = "";
          latestBasePrompt = "";
          previewRequirement = "";
          status.textContent = error.message || "最终提示词预览失败。";
          appendRedrawLog(`提示词改写失败：${error.message || "未知错误"}`);
        } finally {
          if (requestVersion === previewVersion) {
            button.disabled = !(latestBasePrompt && previewRequirement);
            rewriteButton.disabled = false;
          }
        }
      };
      const invalidatePreview = () => {
        window.clearTimeout(previewTimer);
        previewVersion += 1;
        latestBasePrompt = "";
        previewRequirement = "";
        promptInput.value = "";
        button.disabled = true;
        button.textContent = "CPA 生图处理中…";
        status.textContent = "修改要求已变化，请点击“按我的要求重做提示词”。";
      };
      renderAnchorPreview();
      basePromptInput.value = promptPayload.prompt || "";
      status.textContent = "这份旧系统稿不会发送。请填写修改要求，再选择局部或整体改写。";
      anchorSelect.addEventListener("change", invalidatePreview);
      abstractionSelect.addEventListener("change", invalidatePreview);
      rewriteScope.addEventListener("change", invalidatePreview);
      extraInput.addEventListener("input", invalidatePreview);
      rewriteButton.addEventListener("click", () => {
        if (!extraInput.value.trim()) {
          appendRedrawLog("尚未提交：请先填写修改要求。");
          return window.alert("请先写明这次想增加、删除或改变什么。");
        }
        appendRedrawLog(`开始调用 AI 重写提示词，范围：${rewriteScope.value === "full" ? "整体" : "局部"}。`);
        refreshSuggestedPrompt(true);
      });
      reloginButton?.addEventListener("click", async () => {
        await relaunchChatgptLogin(status, reloginButton);
      });
      button.addEventListener("click", async () => {
        const extra = extraInput?.value?.trim() || "";
        const prompt = promptInput.value.trim();
        if (!extra) { appendRedrawLog("尚未提交：修改要求为空。"); return window.alert("请先写明这次想增加、删除或改变什么，再重做提示词。"); }
        if (!prompt) { appendRedrawLog("尚未提交：AI 提示词还未生成。"); return window.alert("最终发送提示词还没有生成完成。"); }
        if (extra && previewRequirement !== extra) { appendRedrawLog("尚未提交：修改要求变化后尚未重新改写提示词。"); return window.alert("修改要求有变化，请先重新点击“按我的要求重做提示词”。"); }
        if (!latestBasePrompt) { appendRedrawLog("尚未提交：缺少最终提示词。"); return window.alert("请先完成提示词重做。"); }
        button.disabled = true;
        const providerName = imageProviderLabel(configFieldValue("IMAGE_PROVIDER", "auto"));
        const startedAt = Date.now();
        appendRedrawLog(`已提交 ${target}，渠道：${providerName}。`);
        status.textContent = extra
          ? `正在生成；已提交追加要求：${extra}`
          : "正在生成，这一步可能需要几十秒到几分钟...";
        const progressTimer = window.setInterval(() => {
          const seconds = Math.max(1, Math.floor((Date.now() - startedAt) / 1000));
          status.textContent = `正在通过 ${providerName} 生成 ${target}，已等待 ${seconds} 秒…`;
          if (seconds % 10 === 0) appendRedrawLog(`CPA/图片模型仍在处理，已等待 ${seconds} 秒。`);
        }, 1000);
        try {
          const result = await api(`/api/projects/${project.id}/images/regenerate`, {
            method: "POST",
            body: JSON.stringify({
              kind,
              target,
              prompt: latestBasePrompt,
              anchor_key: anchorSelect.value,
              abstraction_level: abstractionSelect.value,
              additional_requirement: extra,
              as_candidate: asCandidate,
            }),
          });
          state.imageReview = result.review || state.imageReview;
          state.productionManifest = result.manifest || state.productionManifest;
          renderProductionManifest();
          if (result.needs_handoff) {
            const handoff = result.handoff || {};
            const desktopInstructions = handoff.open_target === "desktop"
              ? `${handoff.clipboard_copied ? "中文提示词已复制。" : "剪贴板写入失败，请打开提示词存档。"}请在 Classic 输入框按 Ctrl+V、发送并等待生成，然后手动保存图片。`
              : "请在打开的 ChatGPT 页面粘贴发送并保存图片。";
            status.innerHTML = `
              ${escapeHtml(desktopInstructions)}<br>
              提示词存档：<span class="mono-inline">${escapeHtml(handoff.prompt_path || "")}</span><br>
              图片必须保存到：<br>
              <span class="mono-inline">${escapeHtml(handoff.output_path || result.path || "")}</span><br>
              保存完成后点“刷新状态”或重新打开生产页查看。
            `;
            return;
          }
          status.textContent = result.candidate
            ? "备选图已生成，正式图保持不变；请在对比区决定是否采用。"
            : "已重绘完成，请检查图片效果。";
          appendRedrawLog(`生成成功并已保存：${result.path || target}`);
          const refreshTimeout = new Promise((resolve) => setTimeout(resolve, 8000));
          await Promise.race([
            Promise.allSettled([refreshSceneStatus(), refreshFiles(), refreshImageReview()]),
            refreshTimeout,
          ]);
          setTimeout(closeModal, 300);
        } catch (error) {
          const message = error.message || "图片重绘失败。";
          appendRedrawLog(`生成失败：${message}`);
          if (isChatgptLoginError(message)) {
            status.textContent = `${message} 请先点击“重新登录 ChatGPT”，登录完成后再重试这一张。`;
          } else {
            status.textContent = `生成失败：${message}`;
          }
        } finally {
          window.clearInterval(progressTimer);
          button.disabled = false;
          button.textContent = "生成 / 重绘这一张";
        }
      });
    }
  );
}

async function runReleaseAutomation(action) {
  const project = ensureProject();
  if (!project) return;
  const pathMap = {
    prepare: `/api/projects/${project.id}/release-automation/prepare`,
    login: `/api/projects/${project.id}/release-automation/login`,
    check: `/api/projects/${project.id}/release-automation/check`,
    publish: `/api/projects/${project.id}/release-automation/publish`,
    cancel: `/api/projects/${project.id}/release-automation/cancel`,
  };
  const path = pathMap[action];
  if (!path) {
    throw new Error(`Unknown release automation action: ${action}`);
  }
  if (action === "publish") {
    const title = els.releaseAutoTitle?.value?.trim() || "";
    if (!title) {
      window.alert("请先填写发布标题。");
      return;
    }
  }
  const options = action === "cancel"
    ? { method: "POST" }
    : action === "prepare"
      ? { method: "POST" }
      : { method: "POST", body: JSON.stringify(releaseAutomationFormPayload()) };
  markReleaseAutomationPending(action);
  try {
    await api(path, options);
  } finally {
    await refreshReleaseAutomation();
  }
}

async function enqueueReleaseAutomation() {
  const project = ensureProject();
  if (!project) return;
  const title = els.releaseAutoTitle?.value?.trim() || "";
  if (!title) {
    window.alert("请先填写发布标题。");
    return;
  }
  markReleaseAutomationPending("publish");
  await persistReleaseAutomationDraft();
  const formPayload = releaseAutomationFormPayload();
  const targets = selectedReleaseBatchTargets();
  if (!targets.length) {
    window.alert("请先在“发布目标”里勾选至少一个已登录账号。");
    return;
  }
  await api(`/api/projects/${project.id}/release-queue/batch`, {
    method: "POST",
    body: JSON.stringify({ ...formPayload, targets }),
  });
  await refreshReleaseAutomation();
}

function bindEvents() {
  setAdvancedMode(state.advancedMode, { persist: false });

  els.workspaceModeToggle?.addEventListener("click", () => {
    setAdvancedMode(!state.advancedMode);
  });

  document.querySelectorAll("[data-enable-advanced-mode]").forEach((button) => {
    button.addEventListener("click", () => setAdvancedMode(true));
  });

  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => setActiveTab(button.dataset.tab));
  });

  document.querySelectorAll("[data-production-asset-tab]").forEach((button) => {
    button.addEventListener("click", () => setProductionAssetTab(button.dataset.productionAssetTab));
  });
  els.productionLogJumpBtn?.addEventListener("click", () => {
    els.productionLiveLogPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  setProductionAssetTab(state.productionAssetTab);

  els.stepList?.addEventListener("change", (event) => {
    if (event.target instanceof HTMLInputElement && event.target.matches("[data-step]")) {
      renderProductionCockpit();
      updateWorkflowButtons();
    }
  });

  els.productionCockpitAction?.addEventListener("click", () => {
    if (!state.currentProject || !els.taskCommandPrimary) return;
    els.productionCockpitAction.disabled = true;
    els.productionCockpitAction.textContent = "请求已发送";
    els.taskCommandPrimary.click();
    window.setTimeout(() => {
      renderTaskCommandBar();
    }, 3000);
  });

  els.nextToProduceBtn?.addEventListener("click", () => {
    if (els.nextToProduceBtn.disabled) return;
    setActiveTab("produce");
  });

  els.nextToFilesBtn?.addEventListener("click", () => {
    if (els.nextToFilesBtn.disabled) return;
    setActiveTab("files");
  });

  els.nextToReleasesBtn?.addEventListener("click", () => {
    if (els.nextToReleasesBtn.disabled) return;
    setActiveTab("releases");
  });

  els.nextToDataBtn?.addEventListener("click", () => {
    if (els.nextToDataBtn.disabled) return;
    setActiveTab("analytics");
  });

  els.modal.addEventListener("click", (event) => {
    if (event.target.dataset.closeModal === "true") closeModal();
  });
  document.getElementById("modal-close-btn").addEventListener("click", closeModal);

  els.briefInput.addEventListener("input", () => {
    state.editor.projectId = state.currentProject?.id ?? null;
    state.editor.briefDirty = els.briefInput.value !== state.editor.lastBrief;
    updateWorkflowButtons();
  });

  els.contentInput.addEventListener("input", () => {
    state.editor.projectId = state.currentProject?.id ?? null;
    state.editor.contentDirty = els.contentInput.value !== state.editor.lastContent;
    updateWorkflowButtons();
  });

  document.getElementById("new-project-btn").addEventListener("click", () => {
    if (!state.backendOnline) return window.alert("请先启动后端。");
    const currentTemplateKey = selectedTemplateKey();
    const templateOptions = state.templates.map((item) => {
      const selected = item.key === currentTemplateKey ? "selected" : "";
      return `<option value="${escapeHtml(item.key)}" ${selected}>${escapeHtml(item.key)}</option>`;
    }).join("");
    showModal(
      "新建主题项目",
      `
        <label><span>主题名</span><input id="modal-project-topic" placeholder="例如：秦始皇陵为什么不敢挖" /></label>
        <label><span>频道模板</span><select id="modal-project-template">${templateOptions}</select></label>
        <label><span>创作类型</span><select id="modal-project-content-type"><option value="editorial">知识 / 观点</option><option value="product">商品推广</option></select></label>
        <label><span>成片语言</span><select id="modal-project-output-language"><option value="zh-CN">中文</option><option value="en-US">English</option></select></label>
        <div class="toolbar"><button id="modal-project-save" class="btn btn--primary">创建</button></div>
      `,
      (body) => {
        body.querySelector("#modal-project-save").addEventListener("click", async () => {
          const topic = body.querySelector("#modal-project-topic").value.trim();
          const template = body.querySelector("#modal-project-template").value;
          const contentType = body.querySelector("#modal-project-content-type").value === "product" ? "product" : "editorial";
          const outputLanguage = body.querySelector("#modal-project-output-language").value === "en-US" ? "en-US" : "zh-CN";
          if (!topic) return window.alert("请先填写主题名。");
          const created = await api("/api/projects", {
            method: "POST",
            body: JSON.stringify({ topic_name: topic, template, content_type: contentType, output_language: outputLanguage }),
          });
          state.selectedTemplateKey = template;
          closeModal();
          await refreshProjects();
          if (created?.id) await openProject(created.id);
        });
      }
    );
  });

  function openTemplateCreateModal() {
    if (!state.backendOnline) return window.alert("请先启动后端。");
    const baseTemplates = state.templates || [];
    const baseOptions = baseTemplates
      .map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.key)}</option>`)
      .join("");
    const fallbackPrompt = `# 新频道提示词

请把 brief 组织成一份能直接进入生产流程的 content.md。

频道人设：写清楚这个频道是谁在讲、给谁看、口吻是冷静解释、情绪共鸣、商业分析还是生活提醒。
内容结构：开头必须有钩子，中段持续推进信息差，结尾给可执行动作或互动问题。
封面规则：封面要和本期主题、频道名称、作者/个人 IP 强关联，标题短而清楚。
场景图片：必须根据本期主题和对应文案段落生成，不要套固定画风；每张图有主体、动作、情绪和字幕空间。
禁忌：不要空泛说教，不要生成长段不可读文字，不要把不同主题套成同一套画面。`;
    showModal(
      "新建频道模板",
      `
        <label><span>频道名</span><input id="modal-template-key" placeholder="例如：商道人物志" /></label>
        <label><span>基于频道</span><select id="modal-template-base">${baseOptions}</select></label>
        <label><span>模式</span><select id="modal-template-mode"><option value="video">视频</option><option value="article">图文</option></select></label>
        <label><span>发布标签</span><input id="modal-template-tags" placeholder="#知识科普 #涨知识" /></label>
        <label><span>封面风格</span><input id="modal-template-cover-style" placeholder="default / doodle / notebook / forbes" /></label>
        <label><span>目标受众</span><input id="modal-template-audience" placeholder="例如：给爸妈看的生活提醒 / 科技产品用户" /></label>
        <label><span>频道口吻</span><input id="modal-template-voice" placeholder="例如：温和提醒、犀利拆解、朋友式吐槽" /></label>
        <label class="form-grid__wide"><span>内容与选题视觉策略</span><textarea id="modal-template-visual" class="text-editor text-editor--small" placeholder="这个频道通常拍什么、面向谁、重点呈现哪些真实证据；不要在这里写死每期场景"></textarea></label>
        <label class="form-grid__wide"><span>频道色彩与材质系统</span><textarea id="modal-template-palette" class="text-editor text-editor--small" placeholder="例如：暖米白纸张；炭黑线稿；砖红、靛蓝、芥末黄只用于重点；全频道保持同一纸张颗粒与线条粗细"></textarea></label>
        <label class="form-grid__wide"><span>内容与合规禁忌</span><textarea id="modal-template-forbidden" class="text-editor text-editor--small" placeholder="不要出现的语气、题材、误导结论或平台风险"></textarea></label>
        <label class="form-grid__wide"><span>频道固定画面风格</span><textarea id="modal-template-image-style" class="text-editor text-editor--small" placeholder="例如：真实纪实摄影，生活化自然光，冷灰与暖黄点色，35mm 近景；关键镜头用大字与 1–3 个核心物体铺满画面。只写画风、光线、镜头、材质和排版气质，不写固定人物或固定剧情"></textarea></label>
        <label class="form-grid__wide"><span>生图禁止词 / 禁止元素</span><textarea id="modal-template-image-negative" class="text-editor text-editor--small" placeholder="例如：赛博蓝光、机器人、全息屏、廉价红叉、PPT 卡片、同一男模、摆拍摊手、乱码、长段文字、水印"></textarea></label>
        <label><span>互动目标</span><input id="modal-template-interaction" placeholder="例如：引导观众讲经历 / 站队 / 补充建议" /></label>
        <label><span>挖题方向</span><input id="modal-template-mining" placeholder="例如：家庭沟通、免费套路、智能设备避坑" /></label>
        <label class="form-grid__wide"><span>prompt.md</span><textarea id="modal-template-prompt" class="text-editor text-editor--short"></textarea></label>
        <div class="toolbar"><button id="modal-template-save" class="btn btn--primary">保存</button></div>
      `,
      (body) => {
        const baseSelect = body.querySelector("#modal-template-base");
        const modeInput = body.querySelector("#modal-template-mode");
        const tagsInput = body.querySelector("#modal-template-tags");
        const styleInput = body.querySelector("#modal-template-cover-style");
        const audienceInput = body.querySelector("#modal-template-audience");
        const voiceInput = body.querySelector("#modal-template-voice");
        const visualInput = body.querySelector("#modal-template-visual");
        const paletteInput = body.querySelector("#modal-template-palette");
        const forbiddenInput = body.querySelector("#modal-template-forbidden");
        const imageStyleInput = body.querySelector("#modal-template-image-style");
        const imageNegativeInput = body.querySelector("#modal-template-image-negative");
        const interactionInput = body.querySelector("#modal-template-interaction");
        const miningInput = body.querySelector("#modal-template-mining");
        const promptInput = body.querySelector("#modal-template-prompt");
        let promptTouched = false;

        function formatVisualPalette(value) {
          if (typeof value === "string") return value;
          if (!value || typeof value !== "object") return "";
          const accents = Array.isArray(value.accents) ? value.accents.filter(Boolean).join("、") : "";
          return [
            value.background ? `背景：${value.background}` : "",
            value.ink ? `线条：${value.ink}` : "",
            accents ? `强调色：${accents}` : "",
            value.rule ? `规则：${value.rule}` : "",
          ].filter(Boolean).join("\n");
        }

        function selectedBase() {
          return baseTemplates.find((item) => item.key === baseSelect.value) || baseTemplates[0] || null;
        }

        function applyBaseTemplate() {
          const base = selectedBase();
          modeInput.value = base?.mode || "video";
          tagsInput.value = base?.release_tags || "";
          styleInput.value = base?.cover_style || "default";
          audienceInput.value = base?.target_audience || "";
          voiceInput.value = base?.channel_voice || "";
          visualInput.value = base?.visual_strategy || "";
          paletteInput.value = formatVisualPalette(base?.visual_palette);
          forbiddenInput.value = base?.forbidden_rules || "";
          imageStyleInput.value = base?.image_style_prompt || "";
          imageNegativeInput.value = base?.image_negative_prompt || "";
          interactionInput.value = base?.interaction_goal || "";
          miningInput.value = base?.topic_mining_hint || "";
          promptInput.value = base?.prompt?.trim() || fallbackPrompt;
          promptTouched = false;
        }

        baseSelect.addEventListener("change", applyBaseTemplate);
        promptInput.addEventListener("input", () => {
          promptTouched = true;
        });
        applyBaseTemplate();

        body.querySelector("#modal-template-save").addEventListener("click", async () => {
          const key = body.querySelector("#modal-template-key").value.trim();
          if (!key) return window.alert("请先填写频道名。");
          const base = selectedBase();
          const prompt = promptTouched ? promptInput.value : adaptPromptChannelName(promptInput.value, base, key);
          const promptError = validateTemplatePromptText(prompt);
          if (promptError) return window.alert(promptError);
          await api("/api/templates", {
            method: "POST",
            body: JSON.stringify({
              key,
              name: key,
              brand_name: key,
              mode: modeInput.value,
              target_audience: audienceInput.value,
              channel_voice: voiceInput.value,
              visual_strategy: visualInput.value,
              visual_palette: paletteInput.value,
              forbidden_rules: forbiddenInput.value,
              image_style_prompt: imageStyleInput.value,
              image_negative_prompt: imageNegativeInput.value,
              interaction_goal: interactionInput.value,
              topic_mining_hint: miningInput.value,
              release_tags: tagsInput.value,
              cover_style: styleInput.value,
              prompt,
            }),
          });
          closeModal();
          await refreshTemplates();
        });
      }
    );
  }

  document.getElementById("new-template-btn").addEventListener("click", openTemplateCreateModal);
  document.getElementById("new-template-inline-btn")?.addEventListener("click", openTemplateCreateModal);

  document.getElementById("open-templates-btn").addEventListener("click", async () => {
    await api("/api/templates/open-root", { method: "POST" });
  });

  document.getElementById("refresh-projects-btn").addEventListener("click", refreshProjects);
  els.sourceAddBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const url = els.sourceUrlInput?.value?.trim() || "";
    const note = els.sourceNoteInput?.value?.trim() || "";
    if (!url && !note) return window.alert("请先填写链接或资料摘要。");
    const original = els.sourceAddBtn.textContent;
    els.sourceAddBtn.disabled = true;
    els.sourceAddBtn.textContent = "正在加入...";
    try {
      const result = await api(`/api/projects/${project.id}/sources`, {
        method: "POST",
        body: JSON.stringify({
          type: url ? "url" : "note",
          title: els.sourceTitleInput?.value?.trim() || "",
          url,
          note,
          must_use: !!els.sourceMustUseInput?.checked,
        }),
      });
      state.sourceMaterials = result.items || [];
      if (els.sourceUrlInput) els.sourceUrlInput.value = "";
      if (els.sourceTitleInput) els.sourceTitleInput.value = "";
      if (els.sourceNoteInput) els.sourceNoteInput.value = "";
      renderSourceWorkbench();
    } finally {
      els.sourceAddBtn.disabled = false;
      els.sourceAddBtn.textContent = original || "加入资料";
    }
  });
  els.sourceUploadBtn?.addEventListener("click", () => els.sourceImageInput?.click());
  els.sourceImageInput?.addEventListener("change", async () => {
    const project = ensureProject();
    const file = els.sourceImageInput.files?.[0];
    if (!project || !file) return;
    const form = new FormData();
    form.append("file", file);
    const query = new URLSearchParams({
      title: els.sourceTitleInput?.value?.trim() || file.name,
      note: els.sourceNoteInput?.value?.trim() || "",
      must_use: String(!!els.sourceMustUseInput?.checked),
    });
    els.sourceSearchStatus.textContent = "正在保存参考图片...";
    try {
      const result = await api(`/api/projects/${project.id}/sources/upload?${query.toString()}`, {
        method: "POST",
        body: form,
      });
      state.sourceMaterials = result.items || [];
      renderSourceWorkbench();
      els.sourceSearchStatus.textContent = "参考图片已加入，后续生图会把它作为图生图依据。";
    } finally {
      els.sourceImageInput.value = "";
    }
  });
  els.sourceSearchBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const query = els.sourceSearchInput?.value?.trim() || state.currentProject?.topic_name || "";
    if (!query) return window.alert("请输入检索关键词。");
    const original = els.sourceSearchBtn.textContent;
    els.sourceSearchBtn.disabled = true;
    els.sourceSearchBtn.textContent = "检索中...";
    els.sourceSearchStatus.textContent = "正在使用 Grok 主检索，并通过公开来源辅助核验，请稍候...";
    try {
      const result = await api(`/api/projects/${project.id}/sources/search`, {
        method: "POST",
        body: JSON.stringify({
          query,
          current_news: !!els.sourceNewsInput?.checked,
          limit: 8,
        }),
      });
      state.sourceCandidates = result;
      const providerText = Object.entries(result.providers || {}).map(([name, count]) => `${name} ${count}`).join(" · ");
      els.sourceSearchStatus.textContent = `已找到 ${result.results?.length || 0} 条 · ${providerText || "公开网页"}`;
      renderSourceWorkbench();
    } finally {
      els.sourceSearchBtn.disabled = false;
      els.sourceSearchBtn.textContent = original || "多来源搜索";
    }
  });
  els.sourceMaterialList?.addEventListener("click", async (event) => {
    const project = ensureProject();
    if (!project) return;
    const toggle = event.target.closest("[data-toggle-source]");
    const remove = event.target.closest("[data-delete-source]");
    if (toggle) {
      const result = await api(`/api/projects/${project.id}/sources/${encodeURIComponent(toggle.dataset.toggleSource)}`, {
        method: "PATCH",
        body: JSON.stringify({ must_use: toggle.dataset.nextMustUse === "true" }),
      });
      state.sourceMaterials = result.items || [];
      renderSourceWorkbench();
    }
    if (remove) {
      const result = await api(`/api/projects/${project.id}/sources/${encodeURIComponent(remove.dataset.deleteSource)}`, {
        method: "DELETE",
      });
      state.sourceMaterials = result.items || [];
      renderSourceWorkbench();
    }
  });
  els.sourceCandidateList?.addEventListener("click", async (event) => {
    const project = ensureProject();
    const button = event.target.closest("[data-adopt-source]");
    if (!project || !button) return;
    button.disabled = true;
    button.textContent = "正在采用...";
    const result = await api(
      `/api/projects/${project.id}/sources/candidates/${encodeURIComponent(button.dataset.adoptSource)}/adopt`,
      { method: "POST" }
    );
    state.sourceMaterials = [...state.sourceMaterials, result.item].filter(Boolean);
    state.sourceCandidates = result.candidates || state.sourceCandidates;
    renderSourceWorkbench();
  });
  document.getElementById("save-brief-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const brief = els.briefInput.value;
    const result = await api(`/api/projects/${project.id}/brief`, {
      method: "POST",
      body: JSON.stringify({ brief }),
    });
    state.editor.lastBrief = brief;
    state.editor.briefDirty = false;
    if (state.currentContent) {
      state.currentContent.brief = brief;
      state.currentContent.fact_registry = result.fact_registry || state.currentContent.fact_registry;
    }
    renderContentBundle();
    await refreshProjects();
  });

  document.getElementById("save-content-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const content = els.contentInput.value;
    const button = document.getElementById("save-content-btn");
    await withBusyButton(button, "保存中...", async () => {
      const result = await api(`/api/projects/${project.id}/content`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      const savedContent = result.content || content;
      state.editor.lastContent = savedContent;
      state.editor.contentDirty = false;
      if (savedContent !== content) {
        els.contentInput.value = savedContent;
      }
      if (state.currentContent) {
        state.currentContent.content = savedContent;
        state.currentContent.summary = result.summary || state.currentContent.summary;
        state.currentContent.fact_registry = result.fact_registry || state.currentContent.fact_registry;
        state.currentContent.content_sync = result.sync || state.currentContent.content_sync;
        state.currentContent.save_notice = contentSaveSemanticNotice(
          result.change_impact,
          result.canonicalization?.numeric_consistency,
        );
      }
      state.productionManifest = result.manifest || state.productionManifest;
      renderContentBundle({ forceEditor: true });
      renderProductionManifest();
      await refreshImageReview();
    });
  });

  document.getElementById("generate-content-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (productModeEnabled()) {
      const product = productSettingsPayload();
      if (!product.product_name || !product.product_selling_points) {
        return window.alert("商品推广模式需要先填写商品名称和至少一个确认卖点，并保存商品资料。");
      }
    }
    const tavily = state.currentContent?.tavily_topic || project.tavily_topic || "general";
    const brief = els.briefInput.value;
    const requestProjectId = project.id;
    const requestToken = crypto.randomUUID();
    state.contentGenerateRequest = { projectId: requestProjectId, token: requestToken };
    const button = document.getElementById("generate-content-btn");
    button.disabled = true;
    state.currentContent = state.currentContent || {};
    state.currentContent.content_generate = {
      status: "running",
      stage: "think",
      started_at: Date.now() / 1000,
      reference_count: 0,
      message: "已收到生成请求，正在整理主题和频道要求。",
    };
    renderContentBundle();
    try {
      await api(`/api/projects/${requestProjectId}/content/generate`, {
        method: "POST",
        body: JSON.stringify({ brief, tavily_topic: tavily, client_run_id: requestToken }),
      });
      if (state.currentProject?.id !== requestProjectId || state.contentGenerateRequest?.token !== requestToken) return;
      state.editor.lastBrief = brief;
      state.editor.briefDirty = false;
      state.editor.contentDirty = false;
      await Promise.all([refreshContentBundle(), refreshImageReview()]);
    } catch (error) {
      if (state.currentProject?.id !== requestProjectId || state.contentGenerateRequest?.token !== requestToken) return;
      state.currentContent.content_generate = {
        status: "failed",
        message: error?.message || "生成请求未成功提交。",
      };
      renderContentBundle();
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("cancel-generate-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    await api(`/api/projects/${project.id}/content/generate/cancel`, { method: "POST" });
    await refreshContentBundle();
  });

  document.getElementById("topic-score-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const payload = await api(`/api/projects/${project.id}/content/tools/topic-score`, {
      method: "POST",
      body: JSON.stringify({ brief: els.briefInput.value }),
    });
    showModal("选题评分", reportHtml("选题评分", payload));
  });

  document.getElementById("viral-doctor-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const payload = await api(`/api/projects/${project.id}/content/tools/viral-doctor`, {
      method: "POST",
      body: JSON.stringify({ content: els.contentInput.value }),
    });
    showModal("脚本体检", reportHtml("脚本体检", payload));
  });

  async function queueViralRewriteJob(button) {
    const project = ensureProject();
    if (!project) return;
    const content = els.contentInput.value;
    const saved = await api(`/api/projects/${project.id}/content`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    const savedContent = saved.content || content;
    els.contentInput.value = savedContent;
    state.editor.lastContent = savedContent;
    state.editor.contentDirty = false;
    if (state.currentContent) {
      state.currentContent.content = savedContent;
      state.currentContent.summary = saved.summary || state.currentContent.summary;
      state.currentContent.content_sync = saved.sync || state.currentContent.content_sync;
    }
    const payload = await api(`/api/projects/${project.id}/stage-gates/content_gate/run`, { method: "POST" });
    state.stageGates = { report_path: payload.report_path, result: payload.dashboard || state.stageGates?.result || {} };
    beginOptimisticGateJob(payload.job, "content_gate");
    renderContentBundle({ forceEditor: true });
  }

  document.getElementById("viral-rewrite-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (!els.contentInput.value.trim()) return window.alert("请先生成或粘贴 content.md。");
    const button = document.getElementById("viral-rewrite-btn");
    await withBusyButton(button, "正在创建优化任务...", () => queueViralRewriteJob(button));
  });

  document.getElementById("optimization-plan-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const button = document.getElementById("optimization-plan-btn");
    await withBusyButton(button, "正在规划...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/optimization-plan`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      showModal("优化路线", optimizationPlanHtml(payload));
    });
  });

  document.getElementById("episode-review-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    await withBusyButton(document.getElementById("episode-review-btn"), "正在读取...", async () => {
      const data = await api(`/api/projects/${project.id}/episode-review`);
      const fields = [
        ["audience_question", "观众为什么要看？", "写下本期回答的一个具体问题，不是新闻标题。"],
        ["viewer_takeaway", "看完能带走什么？", "一个清楚的认识、判断依据或实用方法。"],
        ["evidence_notes", "事实与待核实项", "关键数字、来源链接、哪些是事实，哪些只是推测。"],
        ["visual_purpose", "关键画面帮助理解什么？", "说明对应口播、证据或对比关系，不只写画面风格。"],
        ["audience_feedback", "观众实际反馈", "哪些评论有共鸣？哪里没讲懂？未发布时留空。"],
        ["next_experiment", "下一期只测试一个变化", "写下要改变什么，以及用哪个指标或反馈验证。"],
      ];
      const metrics = (data.releases || []).map(item => {
        const m = item.metrics || {};
        const value = key => m[key] === undefined || m[key] === null || m[key] === "" ? "未记录" : escapeHtml(String(m[key]));
        return `<div class="card card--inner"><strong>${escapeHtml(item.platform || "平台")}</strong>
          <div class="muted">${escapeHtml(item.url || "")}</div>
          <p>播放：${value("views")} · 平均观看秒数：${value("average_watch_seconds")} · 完播率 %：${value("completion_rate")} · 转发：${value("shares")} · 收藏：${value("favorites")}</p>
          <div>${escapeHtml(m.notes || "")}</div></div>`;
      }).join("");
      showModal(`项目 ${project.id} · 单期复盘卡`, `<div class="stack">
        <p class="muted">内部评分不是事实核验，也不是流量保证。先把内容价值讲清，再用同平台、相近时长的数据验证。保存此卡不会重做任何素材；前四项会在下次生成脚本、改稿和规划画面时生效。观众反馈与下一期实验仅作复盘，不自动套用到本期。</p>
        ${fields.map(([key, label, hint]) => `<label><span>${label}</span><textarea data-review-field="${key}" rows="3" maxlength="${key === "evidence_notes" || key === "audience_feedback" ? 8000 : 4000}" placeholder="${hint}">${escapeHtml(data.card?.[key] || "")}</textarea></label>`).join("")}
        <h3>已有发布数据</h3>${metrics || '<p class="muted">尚无发布记录。发布后可在投放数据中回填；这里同步读取，不重复录入。</p>'}
        <p class="muted">少量播放先作观察，不急着判断成败；不同平台的数据不要直接相加比较。</p>
        <div class="toolbar"><button id="save-episode-review" class="btn btn--primary">保存复盘卡</button><span id="episode-review-save-status" role="status"></span></div>
      </div>`, body => {
        body.querySelector("#save-episode-review").addEventListener("click", async event => {
          const status = body.querySelector("#episode-review-save-status");
          status.textContent = "正在保存...";
          try {
            await withBusyButton(event.currentTarget, "保存中...", async () => {
              const payload = Object.fromEntries(fields.map(([key]) => [key, body.querySelector(`[data-review-field="${key}"]`).value]));
              await api(`/api/projects/${project.id}/episode-review`, {method: "PUT", body: JSON.stringify(payload)});
              status.textContent = "已保存，现有素材保持不变。";
            });
          } catch (error) { status.textContent = `保存失败：${error.message}`; }
        });
      });
    });
  });

  document.getElementById("channel-history-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const button = document.getElementById("channel-history-btn");
    await withBusyButton(button, "正在复盘...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/channel-history`, { method: "POST" });
      showModal("频道复盘", channelHistoryHtml(payload));
    });
  });

  document.getElementById("rhythm-check-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const button = document.getElementById("rhythm-check-btn");
    await withBusyButton(button, "正在体检...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/rhythm`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      showModal("节奏体检", rhythmReportHtml(payload));
    });
  });

  document.getElementById("rhythm-enhance-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (!window.confirm("将自动拆长句、补中段转折，并重建图片提示词。继续吗？")) return;
    const button = document.getElementById("rhythm-enhance-btn");
    await withBusyButton(button, "正在增强...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/rhythm-enhance`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      if (payload.content) {
        els.contentInput.value = payload.content;
        state.editor.lastContent = payload.content;
        state.editor.contentDirty = false;
        if (state.currentContent) {
          state.currentContent.content = payload.content;
          state.currentContent.summary = payload.summary || state.currentContent.summary;
        }
      }
      await Promise.all([refreshContentBundle(true), refreshImageReview(), refreshFiles(), refreshProjectStatus()]);
      showModal("节奏增强", rhythmEnhanceHtml(payload));
    });
  });

  document.getElementById("image-layer-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const button = document.getElementById("image-layer-btn");
    await withBusyButton(button, "正在分析...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/image-prompt-layers`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      showModal("图片提示词分层", imagePromptLayersHtml(payload));
    });
  });

  document.getElementById("ai-supervisors-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (!els.contentInput.value.trim()) return window.alert("请先生成或粘贴 content.md。");
    const button = document.getElementById("ai-supervisors-btn");
    await withBusyButton(button, "正在评审...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/ai-supervisors`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      showModal("AI 老师团", aiSupervisorsHtml(payload));
      await Promise.all([refreshFiles(), refreshProjectStatus()]);
    });
  });

  document.getElementById("video-spec-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (!els.contentInput.value.trim()) return window.alert("请先生成或粘贴 content.md。");
    const button = document.getElementById("video-spec-btn");
    await withBusyButton(button, "正在生成...", async () => {
      const payload = await api(`/api/projects/${project.id}/content/tools/video-spec`, {
        method: "POST",
        body: JSON.stringify({ content: els.contentInput.value }),
      });
      showModal("编导规格", reportHtml("video_spec.json", payload));
      await Promise.all([refreshContentBundle(), refreshFiles(), refreshProjectStatus()]);
    });
  });

  document.getElementById("title-ab-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const payload = await api(`/api/projects/${project.id}/content/tools/title-cover-ab`, {
      method: "POST",
      body: JSON.stringify({ content: els.contentInput.value, count: 6, platform: "douyin" }),
    });
    showModal("标题封面 A/B", reportHtml("标题封面 A/B", payload));
  });

  document.getElementById("quality-gate-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const payload = await api(`/api/projects/${project.id}/quality-gate`, {
      method: "POST",
      body: JSON.stringify({ brief: els.briefInput.value, content: els.contentInput.value }),
    });
    showModal("质量总检", qualityGateHtml(payload));
    await Promise.all([refreshFiles(), refreshProjectStatus()]);
  });

  els.productionManifestRefreshBtn?.addEventListener("click", async () => {
    await withBusyButton(els.productionManifestRefreshBtn, "刷新中...", refreshProductionManifest);
  });

  els.voiceSettingsBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project || state.currentJob?.running) return;
    await openTemplateVoiceSettings(project.template);
  });

  els.voiceRebuildBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (state.currentJob?.running) {
      return window.alert(`当前任务正在执行 ${state.currentJob.current_step || "生产步骤"}，请先完成或停止当前任务。`);
    }
    await withBusyButton(els.voiceRebuildBtn, "正在启动...", async () => {
      const job = await api(`/api/projects/${project.id}/jobs`, {
        method: "POST",
        body: JSON.stringify({ steps: ["audio", "subtitles"], allow_incomplete_video: false }),
      });
      state.currentJob = job;
      setActiveTab("produce");
      renderJob();
      await Promise.all([refreshLatestJob(), refreshVoiceStatus(), refreshProductionManifest()]);
    });
  });

  els.bgmVolume?.addEventListener("input", () => {
    const value = Math.max(0, Math.min(Number(els.bgmVolume?.value || 0), 0.35));
    if (els.bgmVolumeValue) els.bgmVolumeValue.textContent = value.toFixed(2);
  });

  els.bgmVolume?.addEventListener("change", async () => {
    const project = ensureProject();
    if (!project) return;
    const volume = Math.max(0, Math.min(Number(els.bgmVolume?.value || 0), 0.35));
    try {
      state.bgmStatus = await api(`/api/projects/${project.id}/bgm/settings`, {
        method: "POST",
        body: JSON.stringify({ volume }),
      });
      renderBgmStatus();
      await refreshProductionManifest();
    } catch (error) {
      window.alert(error.message || "保存 BGM 音量失败。");
      await refreshBgmStatus();
    }
  });

  els.bgmLockBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const trackLocked = !Boolean(state.bgmStatus?.track_locked);
    await withBusyButton(els.bgmLockBtn, trackLocked ? "锁定中..." : "解除中...", async () => {
      state.bgmStatus = await api(`/api/projects/${project.id}/bgm/settings`, {
        method: "POST",
        body: JSON.stringify({ track_locked: trackLocked }),
      });
      renderBgmStatus();
      await refreshProductionManifest();
    });
  });

  els.bgmMixPreviewBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project || !els.bgmMixPreview) return;
    await withBusyButton(els.bgmMixPreviewBtn, "正在混音...", async () => {
      const version = encodeURIComponent(`${state.bgmMixPreviewVersion}:${Date.now()}`);
      els.bgmMixPreview.setAttribute("src", `${API_BASE}/api/projects/${project.id}/bgm/mix-preview?v=${version}`);
      els.bgmMixPreview.classList.remove("hidden");
      els.bgmMixPreview.load();
      try {
        await els.bgmMixPreview.play();
      } catch (error) {
        throw new Error("混音试听未能播放，请确认当前项目已有配音和 BGM。", { cause: error });
      }
    });
  });

  els.bgmRematchBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (state.currentJob?.running) {
      return window.alert(`当前任务正在执行 ${state.currentJob.current_step || "生产步骤"}，请先完成或停止当前任务。`);
    }
    if (state.bgmStatus?.manual_locked) {
      const confirmed = window.confirm("当前项目使用人工锁定的 BGM。继续后会先备份旧音乐，再按本期主题重新匹配。是否继续？");
      if (!confirmed) return;
    }
    try {
      await withBusyButton(els.bgmRematchBtn, "正在启动...", async () => {
        if (state.bgmStatus?.track_locked) {
          state.bgmStatus = await api(`/api/projects/${project.id}/bgm/settings`, {
            method: "POST",
            body: JSON.stringify({ track_locked: false }),
          });
        }
        const job = await api(`/api/projects/${project.id}/jobs`, {
          method: "POST",
          body: JSON.stringify({ steps: ["bgm"], allow_incomplete_video: false }),
        });
        state.currentJob = job;
        setActiveTab("produce");
        renderJob();
        await Promise.all([refreshLatestJob(), refreshBgmStatus(), refreshProductionManifest()]);
      });
    } finally {
      renderBgmStatus();
    }
  });

  els.stageGatesRefreshBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    try {
      await withBusyButton(els.stageGatesRefreshBtn, "正在创建检查任务...", async () => {
        const payload = await api(`/api/projects/${project.id}/stage-gates/evaluate`, { method: "POST" });
        state.stageGates = { report_path: payload.report_path, result: payload.dashboard || state.stageGates?.result || {} };
        beginOptimisticGateJob(payload.job, "content_gate");
      });
    } catch (error) {
      window.alert(error.message || "创建闸门检查任务失败。");
    }
  });

  els.stageGatesSkipAllBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    try {
      await withBusyButton(els.stageGatesSkipAllBtn, "正在跳过全部闸门...", async () => {
        const report = state.stageGates?.result || state.stageGates || {};
        const gates = Array.isArray(report.ordered_gates)
          ? report.ordered_gates
          : Object.values(report.gates || {});
        const targets = gates.filter((g) => g && g.key && !g.passed && !["skipped_reuse", "accepted_with_warnings", "skipped_manual"].includes(String(g.status || "")));
        const failures = [];
        for (const gate of targets) {
          try {
            const payload = await api(`/api/projects/${project.id}/stage-gates/${encodeURIComponent(gate.key)}/accept`, {
              method: "POST",
            });
            state.stageGates = { report_path: payload.report_path, result: payload.dashboard || state.stageGates?.result || {} };
          } catch (e) {
            console.warn("Skip gate failed:", gate.key, e);
            failures.push(`${gate.label || gate.key}：${e?.message || "跳过失败"}`);
          }
        }
        if (failures.length) {
          throw new Error(`以下闸门未能跳过：${failures.join("；")}`);
        }
        renderStageGates();
        renderTaskCommandBar();
        await Promise.all([refreshStageGates(), refreshProjectStatus(), refreshProductionManifest()]);
      });
    } catch (error) {
      window.alert(error.message || "跳过全部闸门失败。");
    }
  });

  els.sampleImageBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (state.currentJob?.running) {
      return window.alert(`当前任务正在执行 ${state.currentJob.current_step || "生产步骤"}，请先完成或停止当前任务。`);
    }
    await withBusyButton(els.sampleImageBtn, "正在启动...", async () => {
      const job = await api(`/api/projects/${project.id}/jobs`, {
        method: "POST",
        body: JSON.stringify({
          steps: ["images_sample"],
          allow_incomplete_video: false,
          auto_recover: true,
        }),
      });
      state.currentJob = job;
      setActiveTab("produce");
      renderJob();
      await Promise.all([refreshProductionManifest(), refreshImageReview()]);
    });
  });

  els.motionSampleBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (state.currentJob?.running) {
      return window.alert(`当前任务正在执行 ${state.currentJob.current_step || "生产步骤"}，请等待当前任务结束后再生成动态样片。`);
    }
    await withBusyButton(els.motionSampleBtn, "正在生成样片...", async () => {
      try {
        const manifest = await api(`/api/projects/${project.id}/motion-samples`, {
          method: "POST",
        });
        showMotionSamplesModal(manifest);
      } catch (error) {
        window.alert(error.message || "动态样片生成失败。");
      }
    });
  });

  document.getElementById("run-job-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    if (state.currentJob?.running) {
      return window.alert(`当前任务正在执行 ${state.currentJob.current_step || "生产步骤"}，请先完成或停止当前任务。`);
    }
    const steps = stepValues();
    const initialPlan = await api(`/api/projects/${project.id}/resume-plan`);
    if (await resumeContentGenerationWhenMissing(project, initialPlan)) return;
    if (!steps.length) return window.alert("请至少勾选一个生产步骤。");
    if (!state.imageReview) await refreshImageReview();
    const reviewRequired = state.imageReview?.required !== false;
    const imageChangingSteps = ["images", "images_sample", "covers", "images_missing", "covers_missing"];
    if (reviewRequired && steps.includes("video")) {
      if (steps.some((step) => imageChangingSteps.includes(step))) {
        return window.alert("当前开启了图片确认关卡：请先只生成场景图/封面图，确认满意后再勾选成片合成。");
      }
      if (!state.imageReview?.confirmed) {
        return window.alert("请先确认当前场景图和封面图，再开始成片合成。");
      }
    }
    if (steps.includes("video") && !steps.some((step) => imageChangingSteps.includes(step))) {
      const preflight = await api(`/api/projects/${project.id}/video-preflight`);
      if (!preflight.result?.passed) {
        showModal("成片前总检未通过", videoPreflightHtml(preflight));
        return;
      }
      const warnings = Array.isArray(preflight.result?.warnings) ? preflight.result.warnings : [];
      if (reviewRequired && warnings.length && !window.confirm(`成片前总检有 ${warnings.length} 个提醒，仍然继续合成吗？`)) {
        showModal("成片前总检提醒", videoPreflightHtml(preflight));
        return;
      }
    }
    await withBusyButton(els.runJobBtn, "正在启动...", async () => {
      const job = await api(`/api/projects/${project.id}/jobs`, {
        method: "POST",
        body: JSON.stringify({ steps, allow_incomplete_video: false, auto_recover: true }),
      });
      state.currentJob = job;
      renderJob();
      await Promise.all([refreshLatestJob(), refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshStageGates(), refreshProjectStatus()]);
    });
    updateWorkflowButtons();
  });

  document.getElementById("resume-plan-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const plan = await api(`/api/projects/${project.id}/resume-plan`);
    showModal("续跑建议", resumePlanHtml(plan));
  });

  els.imageProviderSaveBtn?.addEventListener("click", async () => {
    const value = els.imageProviderSelect?.value || "auto_no_apiyi";
    await withBusyButton(els.imageProviderSaveBtn, "正在切换...", async () => {
      const values = { IMAGE_PROVIDER: value };
      if (value === "auto_no_apiyi") {
        values.APIYI_IMAGE_REPLACE_ARK = "false";
      }
      await api("/api/settings/secrets", {
        method: "POST",
        body: JSON.stringify({ values }),
      });
      await refreshConfig();
    });
  });

  els.sceneCountMode?.addEventListener("change", () => {
    const fixedMode = els.sceneCountMode?.value === "fixed";
    if (els.sceneCountFixed) els.sceneCountFixed.disabled = !fixedMode;
    if (els.sceneCountCurrent) {
      els.sceneCountCurrent.textContent = fixedMode ? "待保存：固定张数" : "待保存：自动估算";
    }
    renderProductionCockpit();
  });

  els.sceneCountFixed?.addEventListener("input", renderProductionCockpit);

  els.coverEnabledButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const project = ensureProject();
      if (!project) return;
      const enabled = button.dataset.coverEnabled === "true";
      if (coverGenerationEnabled() === enabled) return;
      await withBusyButton(button, "保存中...", async () => {
        const payload = await api(`/api/projects/${project.id}/project-settings`, {
          method: "POST",
          body: JSON.stringify({ cover_enabled: enabled }),
        });
        applyProjectSettingsResponse(payload);
        renderCoverGenerationControls();
        renderSteps();
        renderImageReview();
        renderFiles();
        await Promise.all([
          refreshImageReview(),
          refreshProductionManifest(),
          refreshProjectStatus(),
        ]);
        renderProductionCockpit();
      });
    });
  });

  els.contentTypeButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const project = ensureProject();
      if (!project) return;
      const contentType = button.dataset.contentType === "product" ? "product" : "editorial";
      if ((productModeEnabled() ? "product" : "editorial") === contentType) return;
      await withBusyButton(button, "切换中...", async () => {
        const payload = await api(`/api/projects/${project.id}/project-settings`, {
          method: "POST",
          body: JSON.stringify({ content_type: contentType }),
        });
        applyProjectSettingsResponse(payload);
        renderProductModeControls();
        renderProjects();
        if (els.productSettingsStatus && contentType === "product") {
          els.productSettingsStatus.textContent = "商品模式已启用，请填写事实并上传参考图";
        }
        await Promise.all([refreshProjects(), refreshImageReview(), refreshProductionManifest()]);
      });
    });
  });

  els.outputLanguageButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const project = ensureProject();
      if (!project) return;
      const outputLanguage = button.dataset.outputLanguage === "en-US" ? "en-US" : "zh-CN";
      if (currentOutputLanguage() === outputLanguage) return;
      await withBusyButton(button, "切换中...", async () => {
        const payload = await api(`/api/projects/${project.id}/project-settings`, {
          method: "POST",
          body: JSON.stringify({ output_language: outputLanguage }),
        });
        applyProjectSettingsResponse(payload);
        renderOutputLanguageControls();
        renderProjects();
        if (els.contentGenerateStatus) {
          els.contentGenerateStatus.textContent = outputLanguage === "en-US"
            ? "已切换 English；重新生成 content.md 后，后续配音、字幕、图片文字和发布文案会同步为英文。"
            : "已切换中文；重新生成 content.md 后，后续资产会同步为中文。";
        }
        await Promise.all([refreshProjects(), refreshProductionManifest(), refreshProjectStatus()]);
      });
    });
  });

  els.productSettingsSaveBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const product = productSettingsPayload();
    if (!product.product_name) return window.alert("请先填写商品名称。");
    if (!product.product_selling_points) return window.alert("请至少填写一个确认过的商品卖点。");
    await withBusyButton(els.productSettingsSaveBtn, "保存中...", async () => {
      const payload = await api(`/api/projects/${project.id}/project-settings`, {
        method: "POST",
        body: JSON.stringify(product),
      });
      applyProjectSettingsResponse(payload);
      renderProductModeControls();
      if (els.productSettingsStatus) els.productSettingsStatus.textContent = "商品事实已保存，文案和图片将使用同一份资料";
      await Promise.all([refreshImageReview(), refreshProductionManifest()]);
    });
  });

  els.productUploadBtn?.addEventListener("click", () => els.productAssetsInput?.click());
  els.productAssetsInput?.addEventListener("change", async () => {
    const project = ensureProject();
    const files = Array.from(els.productAssetsInput?.files || []);
    if (!project || !files.length) return;
    const form = new FormData();
    files.forEach((file) => form.append("files", file, file.name));
    await withBusyButton(els.productUploadBtn, "上传中...", async () => {
      const payload = await api(`/api/projects/${project.id}/product-assets`, { method: "POST", body: form });
      if (state.currentContent) state.currentContent.project_settings = payload.project_settings || state.currentContent.project_settings;
      state.currentProject = { ...state.currentProject, content_type: "product" };
      renderProductModeControls();
      if (els.productSettingsStatus) els.productSettingsStatus.textContent = "参考图已保存，生图时会自动走图生图";
      await Promise.all([refreshProjects(), refreshImageReview()]);
    });
    els.productAssetsInput.value = "";
  });

  els.productAssetList?.addEventListener("click", async (event) => {
    const target = event.target instanceof HTMLElement ? event.target.closest("[data-delete-product-asset]") : null;
    if (!(target instanceof HTMLElement)) return;
    const project = ensureProject();
    const filename = target.dataset.deleteProductAsset || "";
    if (!project || !filename) return;
    if (!window.confirm(`删除商品参考图“${filename}”？`)) return;
    await withBusyButton(target, "...", async () => {
      const payload = await api(`/api/projects/${project.id}/product-assets/${encodeURIComponent(filename)}`, { method: "DELETE" });
      if (state.currentContent) state.currentContent.project_settings = payload.project_settings || state.currentContent.project_settings;
      renderProductModeControls();
      await refreshImageReview();
    });
  });

  els.sceneCountSaveBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const mode = els.sceneCountMode?.value === "fixed" ? "fixed" : "auto";
    const fixed = Math.max(1, Math.min(Number(els.sceneCountFixed?.value || 6), 24));
    const tavilyTopic = state.currentContent?.project_settings?.tavily_topic || state.currentContent?.tavily_topic || project.tavily_topic || "general";
    await withBusyButton(els.sceneCountSaveBtn, "正在保存...", async () => {
      await api(`/api/projects/${project.id}/project-settings`, {
        method: "POST",
        body: JSON.stringify({
          tavily_topic: tavilyTopic,
          scene_count_mode: mode,
          scene_count_fixed: fixed,
        }),
      });
      await Promise.all([refreshContentBundle(true), refreshSceneStatus(), refreshImageReview(), refreshProjectStatus()]);
    });
  });

  els.imageReviewModeButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const project = ensureProject();
      if (!project) return;
      const mode = button.dataset.imageReviewMode === "auto" ? "auto" : "manual";
      const required = mode === "manual";
      if ((state.imageReview?.required !== false) === required) return;
      const pendingCandidates = Number(state.imageReview?.scene_candidate_pending || 0) + Number(state.imageReview?.cover_candidate_pending || 0);
      try {
        els.imageReviewHelper.textContent = required
          ? "正在切换到人工确认，现有正式图不会变化..."
          : "正在采用 AI 推荐候选并整理正式图，不会重新生成图片...";
        await withBusyButton(button, "切换中...", async () => {
          state.imageReview = await api(`/api/projects/${project.id}/image-review`, {
            method: "POST",
            body: JSON.stringify({ required }),
          });
          await Promise.all([
            refreshSceneStatus(),
            refreshFiles(),
            refreshStageGates(),
            refreshProjectStatus(),
            refreshProductionManifest(),
          ]);
          renderImageReview();
          syncVideoStepWithReviewMode({ force: true });
        });
      } catch (error) {
        await Promise.all([
          refreshSceneStatus().catch(() => null),
          refreshImageReview().catch(() => null),
          refreshProjectStatus().catch(() => null),
        ]);
        renderImageReview();
        window.alert(error.message || "切换审图方式失败。");
      }
    });
  });

  els.confirmImagesBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    try {
      await withBusyButton(els.confirmImagesBtn, "确认并启动成片...", async () => {
        els.imageReviewHelper.textContent = "正在记录当前正式图版本，不会重新生成图片...";
        state.imageReview = await api(`/api/projects/${project.id}/image-review`, {
          method: "POST",
          body: JSON.stringify({ required: true, confirmed: true }),
        });
        document.querySelectorAll("[data-step]").forEach((checkbox) => {
          if (!(checkbox instanceof HTMLInputElement)) return;
          checkbox.checked = checkbox.dataset.step === "video";
        });
        renderImageReview();
        await Promise.all([refreshProjectStatus(), refreshStageGates(), refreshProductionManifest()]);
        const plan = await api(`/api/projects/${project.id}/resume-plan`);
        const steps = Array.isArray(plan?.recommended_steps)
          ? plan.recommended_steps.map((item) => String(item || "").trim()).filter(Boolean)
          : [];
        if (steps.length) {
          const job = await api(`/api/projects/${project.id}/jobs`, {
            method: "POST",
            body: JSON.stringify({ steps, allow_incomplete_video: true, auto_recover: true }),
          });
          state.currentJob = job;
          renderJob();
          els.imageReviewHelper.textContent = "图片已确认，系统正在自动补齐剩余步骤并生成成片。";
        } else {
          els.imageReviewHelper.textContent = "当前图片已确认，现有成片已经是最新版本。";
        }
      });
    } catch (error) {
      renderImageReview();
      window.alert(error.message || "确认图片失败。");
    }
  });

  document.getElementById("cancel-job-btn").addEventListener("click", async () => {
    if (!state.currentJob?.id) return window.alert("当前没有可停止的任务。");
    await api(`/api/jobs/${state.currentJob.id}/cancel`, { method: "POST" });
    await refreshLatestJob();
  });

  document.getElementById("refresh-job-btn").addEventListener("click", async () => {
    await Promise.all([refreshLatestJob(), refreshSceneStatus(), refreshFiles()]);
  });

  els.taskCommandPrimary?.addEventListener("click", async () => {
    const action = els.taskCommandPrimary.dataset.taskCommandAction || "produce";
    if (action === "reconnect") {
      await withBusyButton(els.taskCommandPrimary, "正在重连...", async () => {
        state.jobPollFailures = 0;
        await Promise.all([refreshLatestJob({ refreshGates: false }), refreshProjectStatus(), refreshProductionManifest()]);
      });
      return;
    }
    if (action === "files") {
      setActiveTab("files");
      return;
    }
    setActiveTab("produce");
    if (action === "candidates") {
      setProductionAssetTab(Number(state.imageReview?.cover_candidate_pending || 0) > 0 ? "covers" : "scenes");
    }
    if (action === "view-job") {
      els.productionLiveLogPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (action === "confirm-images") {
      els.confirmImagesBtn?.click();
      return;
    }
    if (action === "gate" || action === "gate-accept") {
      const gateKey = els.taskCommandPrimary.dataset.taskCommandGateKey || "";
      const selector = action === "gate-accept" ? "data-stage-gate-accept" : "data-stage-gate-run";
      const button = document.querySelector(`[${selector}="${CSS.escape(gateKey)}"]`);
      if (button instanceof HTMLButtonElement) {
        button.click();
      } else {
        els.stageGatesRefreshBtn?.click();
      }
      return;
    }
    if (action === "retry") {
      const project = ensureProject();
      if (!project) return;
      const plan = await api(`/api/projects/${project.id}/resume-plan`);
      if (await resumeContentGenerationWhenMissing(project, plan)) return;
      const plannedSteps = Array.isArray(plan?.recommended_steps)
        ? plan.recommended_steps.map((item) => String(item || "").trim()).filter(Boolean)
        : [];
      const recoverySteps = Array.isArray(state.currentJob?.recovery?.recommended_steps)
        ? state.currentJob.recovery.recommended_steps.map((item) => String(item || "").trim()).filter(Boolean)
        : [];
      const steps = plannedSteps.length ? plannedSteps : (recoverySteps.length ? recoverySteps : retryableJobSteps(state.currentJob));
      if (!steps.length) {
        document.getElementById("job-progress")?.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      await withBusyButton(els.taskCommandPrimary, "正在续跑...", async () => {
        const job = await api(`/api/projects/${project.id}/jobs`, {
          method: "POST",
          body: JSON.stringify({ steps, allow_incomplete_video: true, auto_recover: true }),
        });
        state.currentJob = job;
        renderJob();
      });
      return;
    }
    if (action === "produce") {
      const project = ensureProject();
      if (!project) return;
      if (state.currentJob?.running) {
        document.getElementById("job-progress")?.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      try {
        await withBusyButton(els.taskCommandPrimary, "正在读取续跑计划...", async () => {
          const plan = await api(`/api/projects/${project.id}/resume-plan`);
          if (await resumeContentGenerationWhenMissing(project, plan)) return;
          const steps = Array.isArray(plan?.recommended_steps)
            ? plan.recommended_steps.map((item) => String(item || "").trim()).filter(Boolean)
            : [];
          if (!steps.length) {
            const reason = Array.isArray(plan?.reasons) && plan.reasons.length
              ? String(plan.reasons[0])
              : "当前没有需要自动补齐的生产步骤。";
            window.alert(`${reason}\n可在下方手动勾选需要重新执行的步骤。`);
            window.setTimeout(() => document.getElementById("step-list")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
            return;
          }
          els.taskCommandPrimary.textContent = "正在启动生产...";
          const job = await api(`/api/projects/${project.id}/jobs`, {
            method: "POST",
            body: JSON.stringify({ steps, allow_incomplete_video: true, auto_recover: true }),
          });
          state.currentJob = job;
          renderJob();
          document.getElementById("job-progress")?.scrollIntoView({ behavior: "smooth", block: "start" });
          await Promise.all([
            refreshLatestJob({ refreshGates: false }),
            refreshProductionManifest(),
            refreshProjectStatus(),
            refreshBgmStatus(),
          ]);
        });
      } catch (error) {
        window.alert(error.message || "启动续跑任务失败。请查看运行日志后重试。");
      }
      return;
    }
    const targetId = action === "candidates"
      ? (Number(state.imageReview?.cover_candidate_pending || 0) > 0 ? "cover-grid" : "scene-grid")
      : action === "view-job"
        ? "job-progress"
        : "step-list";
    window.setTimeout(() => document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  });

  els.taskCommandRefresh?.addEventListener("click", async () => {
    if (!state.currentProject) return;
    await withBusyButton(els.taskCommandRefresh, "刷新中...", async () => {
      await Promise.all([
        refreshLatestJob({ refreshGates: false }),
        refreshSceneStatus(),
        refreshFiles(),
        refreshImageReview(),
        refreshStageGates(),
        refreshProjectStatus(),
        refreshProductionManifest(),
      ]);
    });
  });

  els.taskCommandCancel?.addEventListener("click", () => {
    document.getElementById("cancel-job-btn")?.click();
  });

  els.clearJobLogBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const running = Boolean(state.currentJob?.running);
    if (running && !window.confirm("当前任务仍在运行，确定要清空当前显示的日志吗？")) return;
    await withBusyButton(els.clearJobLogBtn, "清空中...", async () => {
      const payload = await api(`/api/projects/${project.id}/jobs/latest/log`, { method: "DELETE" });
      state.currentJob = payload.job || null;
      renderJob();
      await Promise.all([refreshProjectStatus(), refreshStageGates()]);
    });
  });

  els.chatgptReloginBtn?.addEventListener("click", async () => {
    await relaunchChatgptLogin(null, els.chatgptReloginBtn);
  });
  els.chatgptLogoutBtn?.addEventListener("click", async () => {
    await logoutChatgptLogin(els.chatgptLogoutBtn);
  });

  document.getElementById("refresh-files-btn").addEventListener("click", async () => {
    await Promise.all([refreshFiles(), refreshProjectStatus()]);
  });
  els.videoSelfCheckBtn?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    await withBusyButton(els.videoSelfCheckBtn, "正在自检...", async () => {
      const payload = await api(`/api/projects/${project.id}/video-self-check`, { method: "POST" });
      state.videoSelfCheck = payload.result;
      showModal("成片自检", videoSelfCheckHtml(payload));
      await Promise.all([refreshFiles(), refreshProjectStatus()]);
    });
  });
  document.getElementById("refresh-releases-btn").addEventListener("click", () => refreshReleases());
  els.syncReleaseMetricsBtn?.addEventListener("click", () => syncReleaseMetrics({ silent: false }));
  els.importReleaseMetricsBtn?.addEventListener("click", () => els.releaseMetricsFileInput?.click());
  els.releaseMetricsFileInput?.addEventListener("change", async () => {
    const project = ensureProject();
    const file = els.releaseMetricsFileInput?.files?.[0];
    if (!project || !file) return;
    await withBusyButton(els.importReleaseMetricsBtn, "导入中…", async () => {
      const form = new FormData();
      form.append("file", file);
      const payload = await api(`/api/projects/${project.id}/releases/import-metrics`, {
        method: "POST",
        body: form,
      });
      state.releaseMetricsSync = {
        projectId: project.id,
        running: false,
        lastAttemptAt: Date.now(),
        message: payload.message || "平台数据已导入。",
      };
      await refreshReleases();
      renderReleaseMetricsSyncStatus();
      if (payload.unmatched?.length) {
        window.alert(`${payload.message} 另有 ${payload.unmatched.length} 行等待匹配，请检查作品 ID、链接或标题。`);
      }
    });
    els.releaseMetricsFileInput.value = "";
  });
  document.getElementById("refresh-release-automation-btn")?.addEventListener("click", async () => {
    try {
      await refreshReleaseAutomation(true);
    } catch (error) {
      window.alert(error.message || "刷新自动发布状态失败。");
    }
  });
  document.getElementById("release-checklist-btn")?.addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const button = document.getElementById("release-checklist-btn");
    await withBusyButton(button, "正在检查...", async () => {
      const payload = await api(`/api/projects/${project.id}/release-checklist`, { method: "POST" });
      showModal("发布前检查", releaseChecklistHtml(payload));
      await refreshFiles();
    });
  });
  bindReleaseAutomationAction("prepare-release-automation-btn", "prepare", "正在准备...", "准备自动发布环境失败。");
  bindReleaseAutomationAction("release-auto-login-btn", "login", "正在登录...", "登录账号失败。");
  bindReleaseAutomationAction("release-auto-check-btn", "check", "正在检测...", "检测账号失败。");
  document.getElementById("release-auto-publish-btn")?.addEventListener("click", async (event) => {
    await withBusyButton(event.currentTarget, "正在发布...", async () => {
      try {
        await enqueueReleaseAutomation();
      } catch (error) {
        window.alert(error.message || "发布视频失败。");
      }
    });
  });
  bindReleaseAutomationAction("release-auto-cancel-btn", "cancel", "正在取消...", "取消发布任务失败。");
  document.getElementById("release-auto-new-account-btn")?.addEventListener("click", () => {
    const alias = window.prompt("请输入这个平台账号的本地别名，例如 tech-2");
    const normalized = String(alias || "").trim().replace(/[^A-Za-z0-9_-]+/g, "-");
    if (!normalized) return;
    if (![...els.releaseAutoAccount.options].some((option) => option.value === normalized)) {
      els.releaseAutoAccount.add(new Option(`${normalized}（登录后同步昵称）`, normalized));
    }
    els.releaseAutoAccount.value = normalized;
    scheduleReleaseAutomationDraftSave({ refresh: true, delay: 0 });
  });
  document.getElementById("release-auto-enqueue-btn")?.addEventListener("click", async (event) => {
    await withBusyButton(event.currentTarget, "正在入队...", async () => {
      try {
        await enqueueReleaseAutomation();
      } catch (error) {
        window.alert(error.message || "加入发布队列失败。");
      }
    });
  });
  [
    els.releaseAutoTitle,
    els.releaseAutoTags,
    els.releaseAutoDescription,
    els.releaseAutoSchedule,
  ].forEach((field) => {
    field?.addEventListener("input", () => scheduleReleaseAutomationDraftSave());
    field?.addEventListener("change", () => scheduleReleaseAutomationDraftSave());
  });
  [
    els.releaseAutoPlatform,
    els.releaseAutoAccount,
    els.releaseAutoBrowserMode,
  ].forEach((field) => {
    field?.addEventListener("change", () => {
      if (field === els.releaseAutoPlatform) renderReleasePlatformCapability();
      scheduleReleaseAutomationDraftSave({ refresh: true, delay: 120 });
    });
  });
  document.getElementById("open-data-folder-btn").addEventListener("click", () => api("/api/settings/open-data-folder"));
  document.getElementById("open-project-folder-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    await api(`/api/projects/${project.id}/open-folder`, { method: "POST" });
  });

  document.getElementById("save-release-btn").addEventListener("click", async () => {
    const project = ensureProject();
    if (!project) return;
    const platform = els.releasePlatform.value.trim();
    const url = els.releaseUrl.value.trim();
    const note = els.releaseNote.value.trim();
    if (!platform || !url) return window.alert("请至少填写平台和链接。");
    await api(`/api/projects/${project.id}/releases`, {
      method: "POST",
      body: JSON.stringify({ platform, url, note, ...releaseMetricsPayloadFromFields() }),
    });
    els.releasePlatform.value = "";
    els.releaseUrl.value = "";
    els.releaseNote.value = "";
    clearReleaseMetricFields();
    await refreshReleases();
  });

  document.getElementById("save-config-btn").addEventListener("click", async () => {
    await api("/api/settings/secrets", {
      method: "POST",
      body: JSON.stringify({ values: collectConfigValues() }),
    });
    await refreshConfig();
    await validateConfigSections();
  });

  els.validateConfigBtn.addEventListener("click", async () => {
    await api("/api/settings/secrets", {
      method: "POST",
      body: JSON.stringify({ values: collectConfigValues() }),
    });
    await validateConfigSections();
  });

  document.getElementById("refresh-config-btn").addEventListener("click", async () => {
    await Promise.all([refreshConfig(), refreshTtsPreviews(), refreshChatgptAccounts()]);
  });

  els.refreshPackagingBtn?.addEventListener("click", refreshPackaging);
  els.openPackagingOutputBtn?.addEventListener("click", () => api("/api/settings/packaging/open?target=output", { method: "POST" }));
  els.startPortableBuildBtn?.addEventListener("click", async () => {
    await api("/api/settings/packaging/build", {
      method: "POST",
      body: JSON.stringify({ include_zip: false }),
    });
    await refreshPackaging();
  });
  els.startZipBuildBtn?.addEventListener("click", async () => {
    if (!window.confirm("生成 ZIP 会比便携 EXE 更慢一些，继续吗？")) return;
    await api("/api/settings/packaging/build", {
      method: "POST",
      body: JSON.stringify({ include_zip: true }),
    });
    await refreshPackaging();
  });
  els.cancelPackagingBtn?.addEventListener("click", async () => {
    await api("/api/settings/packaging/cancel", { method: "POST" });
    await refreshPackaging();
  });

  document.getElementById("import-audio-btn").addEventListener("click", () => els.audioInput.click());
  els.audioInput.addEventListener("change", async () => {
    const project = ensureProject();
    if (!project) return;
    const file = els.audioInput.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file, file.name);
    const response = await fetch(`${API_BASE}/api/transcribe-audio`, { method: "POST", body: form });
    const data = await response.json();
    els.briefInput.value = data.text || "";
    state.editor.projectId = state.currentProject?.id ?? null;
    state.editor.briefDirty = els.briefInput.value !== state.editor.lastBrief;
    updateWorkflowButtons();
  });
  document.body.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.dataset.retryFailedJob) {
      const project = ensureProject();
      if (!project) return;
      if (state.currentJob?.running) return window.alert("当前任务仍在运行，请等待完成或先停止任务。");
      const plan = await api(`/api/projects/${project.id}/resume-plan`);
      const plannedSteps = Array.isArray(plan?.recommended_steps)
        ? plan.recommended_steps.map((item) => String(item || "").trim()).filter(Boolean)
        : [];
      const fallbackSteps = String(target.dataset.retryFailedJob || "").split(",").map((item) => item.trim()).filter(Boolean);
      const steps = plannedSteps.length ? plannedSteps : fallbackSteps;
      if (!steps.length) return window.alert("没有可继续的生产步骤。");
      await withBusyButton(target, "正在续跑...", async () => {
        const job = await api(`/api/projects/${project.id}/jobs`, {
          method: "POST",
          body: JSON.stringify({ steps, allow_incomplete_video: true, auto_recover: true }),
        });
        state.currentJob = job;
        renderJob();
        setActiveTab("produce");
        await Promise.all([refreshLatestJob(), refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshStageGates(), refreshProjectStatus()]);
      });
      return;
    }

    if (target.dataset.stageGateRun) {
      const project = await resolveStageGateProject(target);
      if (!project) return;
      const gateKey = target.dataset.stageGateRun;
      try {
        await withBusyButton(target, "正在创建优化任务...", async () => {
          const payload = await api(`/api/projects/${project.id}/stage-gates/${encodeURIComponent(gateKey)}/run`, {
            method: "POST",
          });
          state.stageGates = { report_path: payload.report_path, result: payload.dashboard || state.stageGates?.result || {} };
          beginOptimisticGateJob(payload.job, gateKey);
        });
      } catch (error) {
        window.alert(error.message || "创建自动优化任务失败。");
      }
      return;
    }

    if (target.dataset.stageGateAccept) {
      const project = await resolveStageGateProject(target);
      if (!project) return;
      const gateKey = target.dataset.stageGateAccept;
      try {
        await withBusyButton(target, "正在放行当前版本...", async () => {
          const payload = await api(`/api/projects/${project.id}/stage-gates/${encodeURIComponent(gateKey)}/accept`, {
            method: "POST",
          });
          state.stageGates = { report_path: payload.report_path, result: payload.dashboard || state.stageGates?.result || {} };
          renderStageGates();
          renderTaskCommandBar();
          const plan = await api(`/api/projects/${project.id}/resume-plan`);
          const steps = Array.isArray(plan?.recommended_steps)
            ? plan.recommended_steps.map((item) => String(item || "").trim()).filter(Boolean)
            : [];
          if (steps.length && !state.currentJob?.running) {
            const job = await api(`/api/projects/${project.id}/jobs`, {
              method: "POST",
              body: JSON.stringify({ steps, allow_incomplete_video: true, auto_recover: true }),
            });
            state.currentJob = job;
            renderJob();
          }
          await Promise.all([refreshStageGates(), refreshProjectStatus(), refreshProductionManifest()]);
        });
      } catch (error) {
        window.alert(error.message || "跳过当前闸门失败。");
      }
      return;
    }

    if (target.dataset.qualityRefresh) {
      const project = ensureProject();
      if (!project) return;
      const payload = await api(`/api/projects/${project.id}/quality-gate`, {
        method: "POST",
        body: JSON.stringify({ brief: els.briefInput.value, content: els.contentInput.value }),
      });
      showModal("质量总检", qualityGateHtml(payload));
      await Promise.all([refreshFiles(), refreshProjectStatus()]);
    }

    if (target.dataset.qualityAction) {
      const project = ensureProject();
      if (!project) return;
      const action = target.dataset.qualityAction;
      const stepActions = {
        subtitles: "subtitles",
        "audio-subtitles": "audio,subtitles",
        "images-missing": "images_missing",
        "covers-missing": "covers_missing",
        images: "images",
        video: "video",
      };
      if (action === "image-prompts") {
        target.dataset.qualityRepair = "image-prompts";
      } else if (action === "rhythm-enhance") {
        if (!els.contentInput.value.trim()) return window.alert("请先生成或粘贴 content.md。");
        if (!window.confirm("将自动增强文案节奏、开头钩子、中段转折，并重建图片提示词。继续吗？")) return;
        await withBusyButton(target, "正在增强...", async () => {
          const payload = await api(`/api/projects/${project.id}/content/tools/rhythm-enhance`, {
            method: "POST",
            body: JSON.stringify({ content: els.contentInput.value }),
          });
          if (payload.content) {
            els.contentInput.value = payload.content;
            state.editor.lastContent = payload.content;
            state.editor.contentDirty = false;
            if (state.currentContent) {
              state.currentContent.content = payload.content;
              state.currentContent.summary = payload.summary || state.currentContent.summary;
            }
          }
          await Promise.all([refreshContentBundle(true), refreshImageReview(), refreshFiles(), refreshProjectStatus()]);
          showModal("节奏增强", rhythmEnhanceHtml(payload));
        });
        return;
      } else if (action === "viral-rewrite") {
        if (!els.contentInput.value.trim()) return window.alert("请先生成或粘贴 content.md。");
        if (!window.confirm("将让总编重新优化 content.md，并同步重建图片提示词。继续吗？")) return;
        await withBusyButton(target, "正在创建优化任务...", () => queueViralRewriteJob(target));
        return;
      } else if (stepActions[action]) {
        target.dataset.preflightRun = stepActions[action];
      }
    }

    if (target.dataset.autoOptAction) {
      const project = ensureProject();
      if (!project) return;
      const action = target.dataset.autoOptAction;
      if (action === "viral-rewrite") {
        if (!els.contentInput.value.trim()) return window.alert("请先生成或粘贴 content.md。");
        await withBusyButton(target, "正在创建优化任务...", () => queueViralRewriteJob(target));
      } else if (action === "release-checklist") {
        const payload = await api(`/api/projects/${project.id}/release-checklist`, { method: "POST" });
        setActiveTab("releases");
        showModal("发布前检查", releaseChecklistHtml(payload));
      } else if (action === "open-content") {
        closeModal();
        setActiveTab("content");
      } else {
        closeModal();
        setActiveTab("produce");
      }
    }

    if (target.dataset.preflightOpenImages) {
      closeModal();
      setActiveTab("produce");
      await Promise.all([refreshSceneStatus(), refreshFiles(), refreshImageReview()]);
      const showCovers = Number(state.imageReview?.cover_candidate_pending || 0) > 0;
      setProductionAssetTab(showCovers ? "covers" : "scenes");
      window.setTimeout(() => document.getElementById(showCovers ? "cover-grid" : "scene-grid")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
      return;
    }

    if (target.dataset.preflightConfirmImages) {
      const project = ensureProject();
      if (!project) return;
      await Promise.all([refreshSceneStatus(), refreshImageReview()]);
      const pendingCandidates = Number(state.imageReview?.scene_candidate_pending || state.sceneStatus?.candidate_group_count || 0)
        + Number(state.imageReview?.cover_candidate_pending || 0);
      if (pendingCandidates) {
        window.alert(`还有 ${pendingCandidates} 个关键位方案等待选择，请先采用封面/首镜方案。`);
        closeModal();
        setActiveTab("produce");
        window.setTimeout(() => document.getElementById("scene-grid")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
        return;
      }
      await withBusyButton(target, "正在确认...", async () => {
        if (state.imageReview?.required !== false) {
          state.imageReview = await api(`/api/projects/${project.id}/image-review`, {
            method: "POST",
            body: JSON.stringify({ required: true, confirmed: true }),
          });
        }
        await Promise.all([refreshImageReview(), refreshProjectStatus(), refreshStageGates()]);
        const payload = await api(`/api/projects/${project.id}/video-preflight`);
        showModal("成片前总检", videoPreflightHtml(payload));
      });
      return;
    }

    if (target.dataset.preflightRefresh) {
      const project = ensureProject();
      if (!project) return;
      const payload = await api(`/api/projects/${project.id}/video-preflight`);
      showModal("成片前总检", videoPreflightHtml(payload));
    }

    if (target.dataset.preflightReuseImages) {
      const project = ensureProject();
      if (!project) return;
      const continueVideo = target.dataset.preflightReuseImages === "video";
      if (!window.confirm("确认复用当前已有场景图和封面图？这会把旧图标记为适配最新版 content.md，不会重新扣费生图。")) return;
      await withBusyButton(target, "正在确认...", async () => {
        const result = await api(`/api/projects/${project.id}/video-preflight/reuse-images`, { method: "POST" });
        await Promise.all([refreshSceneStatus(), refreshImageReview(), refreshFiles(), refreshProjectStatus()]);
        const after = result.after || {};
        if (continueVideo && after.passed) {
          await api(`/api/projects/${project.id}/jobs`, {
            method: "POST",
            body: JSON.stringify({ steps: ["video"], allow_incomplete_video: true }),
          });
          closeModal();
          setActiveTab("produce");
          await Promise.all([refreshLatestJob(), refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshProjectStatus()]);
          window.alert("旧图已复用，已开始成片合成。");
          return;
        }
        showModal("成片前总检", videoPreflightHtml({ report_path: result.report_path, result: after }));
        if (continueVideo) {
          window.alert("旧图已复用，但仍有音频、字幕或时轴等阻止项，需要先处理后再成片。");
        }
      });
    }

    if (target.dataset.qualityIgnoreImages) {
      const project = ensureProject();
      if (!project) return;
      const continueVideo = target.dataset.qualityIgnoreImages === "video";
      if (!window.confirm("确认忽略亮度、对比度、风格等图片软弱项？语义错图、跨题材词、缺图、黑屏和硬失败仍会继续阻断。")) return;
      await withBusyButton(target, "正在放行...", async () => {
        const result = await api(`/api/projects/${project.id}/video-preflight/ignore-image-quality`, { method: "POST" });
        await Promise.all([refreshSceneStatus(), refreshImageReview(), refreshFiles(), refreshProjectStatus(), refreshStageGates()]);
        const after = result.after || {};
        if (continueVideo && after.passed) {
          await api(`/api/projects/${project.id}/jobs`, {
            method: "POST",
            body: JSON.stringify({ steps: ["video"], allow_incomplete_video: true }),
          });
          closeModal();
          setActiveTab("produce");
          await Promise.all([refreshLatestJob(), refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshProjectStatus(), refreshStageGates()]);
          window.alert("已忽略图片软弱项，开始成片合成。");
          return;
        }
        if (continueVideo) {
          showModal("成片前总检", videoPreflightHtml({ report_path: result.report_path, result: after }));
          window.alert("图片软弱项已忽略，但仍有音频、字幕、时轴、缺图或硬失败等问题需要先处理。");
        } else {
          showModal("质量总检", qualityGateHtml({ report_path: "reports/quality_gate.json", result: result.quality_gate || {} }));
        }
      });
    }

    if (target.dataset.preflightRun) {
      const project = ensureProject();
      if (!project) return;
      const steps = String(target.dataset.preflightRun || "").split(",").map((item) => item.trim()).filter(Boolean);
      if (!steps.length) return;
      if (steps.includes("video")) {
        if (!state.imageReview) await refreshImageReview();
        const reviewRequired = state.imageReview?.required !== false;
        if (reviewRequired && !state.imageReview?.confirmed) {
          return window.alert("请先确认当前场景图和封面图，再继续成片合成。");
        }
      }
      const stepLabels = new Map(STEP_DEFS.map((item) => [item.key, item.label]));
      const label = steps.map((step) => stepLabels.get(step) || step).join(" → ");
      await withBusyButton(target, "正在启动...", async () => {
        await api(`/api/projects/${project.id}/jobs`, {
          method: "POST",
          body: JSON.stringify({ steps, allow_incomplete_video: true }),
        });
        closeModal();
        setActiveTab("produce");
        await Promise.all([refreshLatestJob(), refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshProjectStatus()]);
        window.alert(`已开始：${label}`);
      });
    }

    if (target.dataset.applyResumeSteps) {
      const project = ensureProject();
      if (!project) return;
      const steps = String(target.dataset.applyResumeSteps || "").split(",").map((item) => item.trim()).filter(Boolean);
      const wanted = new Set(steps);
      document.querySelectorAll("[data-step]").forEach((checkbox) => {
        if (!(checkbox instanceof HTMLInputElement)) return;
        checkbox.checked = wanted.has(checkbox.dataset.step || "");
      });
      if (!steps.length) return;
      await withBusyButton(target, "正在启动续跑...", async () => {
        const job = await api(`/api/projects/${project.id}/jobs`, {
          method: "POST",
          body: JSON.stringify({ steps, allow_incomplete_video: true, auto_recover: true }),
        });
        state.currentJob = job;
        closeModal();
        setActiveTab("produce");
        renderJob();
        await Promise.all([refreshLatestJob(), refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshStageGates(), refreshProjectStatus()]);
      });
      return;
    }

    if (target.dataset.preflightRepair === "timeline") {
      const project = ensureProject();
      if (!project) return;
      await withBusyButton(target, "正在重建...", async () => {
        const result = await api(`/api/projects/${project.id}/video-preflight/repair-timeline`, { method: "POST" });
        await Promise.all([refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshContentBundle(true), refreshProjectStatus()]);
        showModal("成片前总检", videoPreflightHtml({ report_path: result.report_path, result: result.after }));
      });
    }

    if (target.dataset.qualityRepair === "image-prompts") {
      const project = ensureProject();
      if (!project) return;
      if (!window.confirm("将只重建 content.md 里的“图片提示词”区块，正文口播不会改动。继续吗？")) return;
      await withBusyButton(target, "正在重建...", async () => {
        const result = await api(`/api/projects/${project.id}/quality-gate/repair-image-prompts`, {
          method: "POST",
          body: JSON.stringify({ content: els.contentInput.value }),
        });
        if (result.content) {
          els.contentInput.value = result.content;
          state.editor.lastContent = result.content;
          state.editor.contentDirty = false;
          if (state.currentContent) {
            state.currentContent.content = result.content;
            state.currentContent.summary = result.summary || state.currentContent.summary;
          }
        }
        await Promise.all([refreshContentBundle(true), refreshImageReview(), refreshFiles(), refreshProjectStatus()]);
        showModal("质量总检", qualityGateHtml({ report_path: result.report_path, result: result.quality_gate }));
      });
    }

    if (target.dataset.openProject) {
      await openProject(Number(target.dataset.openProject));
    }

    if (target.dataset.selectTemplate) {
      await selectTemplateProjects(target.dataset.selectTemplate);
    }

    if (target.dataset.autoVideoTemplate) {
      openAutoVideoStartModal(target.dataset.autoVideoTemplate);
    }

    if (target.dataset.refreshAutoVideo) {
      await refreshAutoVideoStatus({ openCreatedProject: true });
    }

    if (target.dataset.cancelAutoVideo) {
      await api("/api/auto-video/cancel", { method: "POST" });
      await refreshAutoVideoStatus();
    }

    if (target.dataset.openAutoVideoProject) {
      await refreshProjects();
      await openProject(Number(target.dataset.openAutoVideoProject));
      closeModal();
    }

    if (target.dataset.autoVideoContinueProject) {
      const projectId = Number(target.dataset.autoVideoContinueProject);
      await withBusyButton(target, "继续中...", async () => {
        await refreshProjects();
        await openProject(projectId);
        setActiveTab("produce");
        if (state.autoVideo?.running && Number(state.autoVideo?.project_id || 0) === projectId) {
          closeModal();
          await Promise.all([refreshAutoVideoStatus(), refreshLatestJob(), refreshProjectStatus()]);
          return;
        }
        await api(`/api/auto-video/continue/${projectId}`, { method: "POST" });
        closeModal();
        await Promise.all([refreshAutoVideoStatus(), refreshLatestJob(), refreshSceneStatus(), refreshFiles(), refreshImageReview(), refreshStageGates(), refreshProjectStatus()]);
      });
    }

    if (target.dataset.deleteProject) {
      const projectId = Number(target.dataset.deleteProject);
      if (!window.confirm("确认删除这个主题项目吗？")) return;
      await api(`/api/projects/${projectId}`, { method: "DELETE" });
      clearCurrentWorkspace();
      await refreshProjects();
      if (!projectsForSelectedTemplate().length) {
        renderWorkspacePlaceholderForSelectedTemplate();
      }
    }

    if (target.dataset.templateVoice) {
      await openTemplateVoiceSettings(target.dataset.templateVoice);
    }

    if (target.dataset.editTemplate) {
      const key = target.dataset.editTemplate;
      const template = await api(`/api/templates/${encodeURIComponent(key)}`);
      const locked = isTemplateLocked(template);
      const initialVoiceMode = template.voice_mode || (key.includes("双人") ? "dual" : "auto");
      const initialRandomOrder = template.tts_random_order === true || String(template.tts_random_order).toLowerCase() === "true";
      showModal(
        `${locked ? "查看频道" : "编辑频道"} · ${key}`,
        `
          ${locked ? `<div class="banner banner--warn">内置频道的内容规则保持锁定；豆包音色、单双人模式和语速可以直接保存。</div>` : ""}
          <section class="template-production-settings">
            <div class="section-heading">
              <div>
                <strong>豆包配音角色</strong>
                <div class="muted">已同步 ${escapeHtml(String(state.ttsPreviews?.voices?.length || 0))} 个可试听音色，保存后下一次配音立即生效。</div>
              </div>
              <button id="modal-sync-voices" class="btn btn--ghost" type="button">同步音色</button>
            </div>
            <label><span>讲述模式</span><select id="modal-edit-voice-mode">
              <option value="auto" ${initialVoiceMode === "auto" ? "selected" : ""}>自动判断（按真实角色）</option>
              <option value="single" ${initialVoiceMode === "single" ? "selected" : ""}>固定单人讲述</option>
              <option value="dual" ${initialVoiceMode === "dual" ? "selected" : ""}>固定双人讲述</option>
            </select></label>
            <label><span id="modal-speaker-1-label">${initialVoiceMode === "dual" ? "角色 A 音色" : "讲述人音色"}</span><div class="secret-input">
              <select id="modal-edit-speaker-1">${doubaoVoiceOptionsHtml(template.tts_speaker_1 || "zh_female_cancan_uranus_bigtts")}</select>
              <button class="icon-btn" type="button" data-preview-voice-select="modal-edit-speaker-1" title="试听当前音色">听</button>
            </div></label>
            <label id="modal-speaker-2-row"><span>角色 B 音色</span><div class="secret-input">
              <select id="modal-edit-speaker-2">${doubaoVoiceOptionsHtml(template.tts_speaker_2 || "zh_female_mizaitongxue_v2_saturn_bigtts")}</select>
              <button class="icon-btn" type="button" data-preview-voice-select="modal-edit-speaker-2" title="试听当前音色">听</button>
            </div></label>
            <label id="modal-random-order-row"><span>角色绑定</span><select id="modal-edit-random-order">
              <option value="false" ${initialRandomOrder ? "" : "selected"}>固定 A / B 音色（推荐）</option>
              <option value="true" ${initialRandomOrder ? "selected" : ""}>每期随机交换 A / B</option>
            </select></label>
            <label><span>语速 <strong id="modal-speech-rate-value">${escapeHtml(String(template.tts_speech_rate || 1))}x</strong></span><input id="modal-edit-speech-rate" type="range" min="0.8" max="1.2" step="0.05" value="${escapeHtml(String(template.tts_speech_rate || 1))}" /></label>
            <div class="toolbar"><button id="modal-voice-save" class="btn btn--primary">保存配音角色</button></div>
          </section>
          <label><span>发布标签</span><input id="modal-edit-tags" value="${escapeHtml(template.release_tags || "")}" ${locked ? "disabled" : ""} /></label>
          <label><span>封面风格</span><input id="modal-edit-style" value="${escapeHtml(template.cover_style || "")}" ${locked ? "disabled" : ""} /></label>
          <label><span>目标受众</span><input id="modal-edit-audience" value="${escapeHtml(template.target_audience || "")}" ${locked ? "disabled" : ""} /></label>
          <label><span>频道口吻</span><input id="modal-edit-voice" value="${escapeHtml(template.channel_voice || "")}" ${locked ? "disabled" : ""} /></label>
          <label class="form-grid__wide"><span>内容与选题视觉策略</span><textarea id="modal-edit-visual" class="text-editor text-editor--small" ${locked ? "readonly" : ""}>${escapeHtml(template.visual_strategy || "")}</textarea></label>
          <label class="form-grid__wide"><span>频道色彩与材质系统</span><textarea id="modal-edit-palette" class="text-editor text-editor--small" placeholder="背景、线条、强调色及其使用比例；它会写进每张图的固定视觉合同" ${locked ? "readonly" : ""}>${escapeHtml(typeof template.visual_palette === "string" ? template.visual_palette : [template.visual_palette?.background && `背景：${template.visual_palette.background}`, template.visual_palette?.ink && `线条：${template.visual_palette.ink}`, Array.isArray(template.visual_palette?.accents) && template.visual_palette.accents.length ? `强调色：${template.visual_palette.accents.join("、")}` : "", template.visual_palette?.rule && `规则：${template.visual_palette.rule}`].filter(Boolean).join("\n"))}</textarea></label>
          <label class="form-grid__wide"><span>内容与合规禁忌</span><textarea id="modal-edit-forbidden" class="text-editor text-editor--small" ${locked ? "readonly" : ""}>${escapeHtml(template.forbidden_rules || "")}</textarea></label>
          <label class="form-grid__wide"><span>频道固定画面风格</span><textarea id="modal-edit-image-style" class="text-editor text-editor--small" placeholder="只固定摄影质感、色彩、光线、镜头、材质和信息元素气质，不写死人物、物件或场景" ${locked ? "readonly" : ""}>${escapeHtml(template.image_style_prompt || "")}</textarea></label>
          <label class="form-grid__wide"><span>生图禁止词 / 禁止元素</span><textarea id="modal-edit-image-negative" class="text-editor text-editor--small" placeholder="多个词可用逗号或换行分隔" ${locked ? "readonly" : ""}>${escapeHtml(template.image_negative_prompt || "")}</textarea></label>
          <label><span>互动目标</span><input id="modal-edit-interaction" value="${escapeHtml(template.interaction_goal || "")}" ${locked ? "disabled" : ""} /></label>
          <label><span>挖题方向</span><input id="modal-edit-mining" value="${escapeHtml(template.topic_mining_hint || "")}" ${locked ? "disabled" : ""} /></label>
          <label class="form-grid__wide"><span>prompt.md</span><textarea id="modal-edit-prompt" class="text-editor text-editor--short" ${locked ? "readonly" : ""}>${escapeHtml(template.prompt || "")}</textarea></label>
          ${locked ? "" : `<div class="toolbar"><button id="modal-edit-save" class="btn btn--primary">保存修改</button><button id="modal-template-delete" class="btn btn--danger">删除频道</button></div>`}
        `,
        (body) => {
          const voiceModeInput = body.querySelector("#modal-edit-voice-mode");
          const speaker1Input = body.querySelector("#modal-edit-speaker-1");
          const speaker2Input = body.querySelector("#modal-edit-speaker-2");
          const speaker2Row = body.querySelector("#modal-speaker-2-row");
          const randomOrderRow = body.querySelector("#modal-random-order-row");
          const speaker1Label = body.querySelector("#modal-speaker-1-label");
          const speechRateInput = body.querySelector("#modal-edit-speech-rate");
          const speechRateValue = body.querySelector("#modal-speech-rate-value");

          function renderVoiceMode() {
            const dual = voiceModeInput.value === "dual";
            const supportsSecondVoice = voiceModeInput.value !== "single";
            speaker2Row.classList.toggle("hidden", !supportsSecondVoice);
            randomOrderRow.classList.toggle("hidden", !supportsSecondVoice);
            speaker1Label.textContent = supportsSecondVoice ? "角色 A 音色" : "讲述人音色";
          }

          voiceModeInput.addEventListener("change", renderVoiceMode);
          speechRateInput.addEventListener("input", () => {
            speechRateValue.textContent = `${Number(speechRateInput.value).toFixed(2)}x`;
          });
          renderVoiceMode();

          body.querySelector("#modal-sync-voices").addEventListener("click", async (event) => {
            await withBusyButton(event.currentTarget, "同步中...", async () => {
              const selected1 = speaker1Input.value;
              const selected2 = speaker2Input.value;
              await refreshTtsPreviews();
              speaker1Input.innerHTML = doubaoVoiceOptionsHtml(selected1);
              speaker2Input.innerHTML = doubaoVoiceOptionsHtml(selected2);
              window.alert(`已同步 ${state.ttsPreviews?.voices?.length || 0} 个豆包音色。`);
            });
          });

          body.querySelector("#modal-voice-save").addEventListener("click", async (event) => {
            await withBusyButton(event.currentTarget, "保存中...", async () => {
              await api(`/api/templates/${encodeURIComponent(key)}/voice-settings`, {
                method: "PUT",
                body: JSON.stringify({
                  voice_mode: voiceModeInput.value,
                  tts_speaker_1: speaker1Input.value,
                  tts_speaker_2: speaker2Input.value,
                  tts_random_order: body.querySelector("#modal-edit-random-order").value === "true",
                  tts_speech_rate: Number(speechRateInput.value),
                }),
              });
              await refreshTemplates();
              window.alert("配音角色已保存，下一次生成配音时生效。已有音频不会被静默覆盖。");
            });
          });

          if (locked) return;
          body.querySelector("#modal-edit-save").addEventListener("click", async () => {
            const prompt = body.querySelector("#modal-edit-prompt").value;
            const promptError = validateTemplatePromptText(prompt);
            if (promptError) return window.alert(promptError);
            await api(`/api/templates/${encodeURIComponent(key)}`, {
              method: "PUT",
              body: JSON.stringify({
                ...template,
                key,
                target_audience: body.querySelector("#modal-edit-audience").value,
                channel_voice: body.querySelector("#modal-edit-voice").value,
                visual_strategy: body.querySelector("#modal-edit-visual").value,
                visual_palette: body.querySelector("#modal-edit-palette").value,
                forbidden_rules: body.querySelector("#modal-edit-forbidden").value,
                image_style_prompt: body.querySelector("#modal-edit-image-style").value,
                image_negative_prompt: body.querySelector("#modal-edit-image-negative").value,
                interaction_goal: body.querySelector("#modal-edit-interaction").value,
                topic_mining_hint: body.querySelector("#modal-edit-mining").value,
                release_tags: body.querySelector("#modal-edit-tags").value,
                cover_style: body.querySelector("#modal-edit-style").value,
                prompt,
              }),
            });
            closeModal();
            await refreshTemplates();
          });
          body.querySelector("#modal-template-delete").addEventListener("click", async () => {
            try {
              await deleteTemplateByKey(key);
            } catch (error) {
              window.alert(error.message || "删除频道失败。");
            }
          });
        }
      );
    }

    if (target.dataset.deleteTemplate) {
      const key = target.dataset.deleteTemplate;
      try {
        await deleteTemplateByKey(key);
      } catch (error) {
        window.alert(error.message || "删除频道失败。");
      }
    }

    if (target.dataset.openTemplate) {
      await api(`/api/templates/${encodeURIComponent(target.dataset.openTemplate)}/open-folder`, { method: "POST" });
    }

    if (target.dataset.openTemplateProducts) {
      await api(`/api/templates/${encodeURIComponent(target.dataset.openTemplateProducts)}/open-products-folder`, { method: "POST" });
    }

    if (target.dataset.deleteOrphanTemplate) {
      const key = target.dataset.deleteOrphanTemplate;
      if (!window.confirm(`确认清理 orphan 模板「${key}」以及它关联的历史项目吗？`)) return;
      const result = await api(`/api/orphan-templates/${encodeURIComponent(key)}`, { method: "DELETE" });
      window.alert(`已清理 ${result.deleted || 0} 个项目。`);
      await Promise.all([refreshProjects(), refreshTemplates()]);
    }

    if (target.dataset.openProjectSubpath) {
      const project = ensureProject();
      if (!project) return;
      await api(`/api/projects/${project.id}/open-folder?subpath=${encodeURIComponent(target.dataset.openProjectSubpath)}`, {
        method: "POST",
      });
    }

    if (target.dataset.openFile) {
      window.open(`${API_BASE}${target.dataset.openFile}`, "_blank", "noopener,noreferrer");
    }

    if (target.dataset.openProjectFile) {
      const fallbackProject = ensureProject();
      const projectId = Number(target.dataset.openProjectFileProject || fallbackProject?.id || 0);
      if (!projectId) return;
      await api(`/api/projects/${projectId}/open-file`, {
        method: "POST",
        body: JSON.stringify({ path: target.dataset.openProjectFile }),
      });
    }

    if (target.dataset.openPackagingTarget) {
      await api(`/api/settings/packaging/open?target=${encodeURIComponent(target.dataset.openPackagingTarget)}`, {
        method: "POST",
      });
    }

    if (target.dataset.chatgptRelogin !== undefined) {
      await relaunchChatgptLogin(null, target);
    }

    if (target.dataset.keepCurrentCover) {
      const project = ensureProject();
      if (!project) return;
      if (state.currentJob?.running) {
        window.alert("封面任务仍在运行，请等候选生成完成后再选择。");
        return;
      }
      try {
        await withBusyButton(target, "正在采用...", async () => {
          await api(`/api/projects/${project.id}/cover-images/candidates/keep-current`, { method: "POST" });
          await Promise.all([
            refreshFiles(),
            refreshImageReview(),
            refreshStageGates(),
            refreshProjectStatus(),
            refreshProductionManifest(),
          ]);
        });
      } catch (error) {
        window.alert(error.message || "采用封面方案 A 失败。");
      }
      return;
    }

    if (target.dataset.selectCoverCandidate) {
      const project = ensureProject();
      if (!project) return;
      if (state.currentJob?.running) {
        window.alert("封面任务仍在运行，请等候选生成完成后再选择。");
        return;
      }
      const variant = String(target.dataset.selectCoverCandidate || "B").trim();
      try {
        await withBusyButton(target, "正在采用...", async () => {
          await api(`/api/projects/${project.id}/cover-images/candidates/select`, {
            method: "POST",
            body: JSON.stringify({ variant }),
          });
          await Promise.all([
            refreshFiles(),
            refreshImageReview(),
            refreshStageGates(),
            refreshProjectStatus(),
            refreshProductionManifest(),
          ]);
        });
      } catch (error) {
        window.alert(error.message || "采用封面候选失败。");
      }
      return;
    }

    if (target.dataset.keepCurrentScene) {
      const project = ensureProject();
      if (!project) return;
      if (state.currentJob?.running) {
        window.alert("图片任务仍在运行，请等当前候选生成完成后再选择。");
        return;
      }
      const sceneIndex = Number(target.dataset.keepCurrentScene || 0);
      if (!window.confirm(`确认保留场景 ${sceneIndex} 的当前旧图？待审候选会被清理，并停止因旧提示词策略要求重绘。`)) return;
      try {
        await withBusyButton(target, "正在保留...", async () => {
          const payload = await api(`/api/projects/${project.id}/scene-images/candidates/keep-current`, {
            method: "POST",
            body: JSON.stringify({ scene_index: sceneIndex }),
          });
          state.sceneStatus = payload.scene_status || state.sceneStatus;
          await Promise.all([
            refreshSceneStatus(),
            refreshFiles(),
            refreshImageReview(),
            refreshStageGates(),
            refreshProjectStatus(),
            refreshProductionManifest(),
          ]);
        });
      } catch (error) {
        window.alert(error.message || "保留当前旧图失败。");
      }
      return;
    }

    if (target.dataset.selectSceneCandidate) {
      const project = ensureProject();
      if (!project) return;
      if (state.currentJob?.running) {
        window.alert("图片任务仍在运行，请等当前候选生成完成后再选择。");
        return;
      }
      const sceneIndex = Number(target.dataset.sceneCandidateIndex || 0);
      const variant = String(target.dataset.sceneCandidateVariant || "").trim();
      try {
        await withBusyButton(target, "正在采用...", async () => {
          const payload = await api(`/api/projects/${project.id}/scene-images/candidates/select`, {
            method: "POST",
            body: JSON.stringify({ scene_index: sceneIndex, variant }),
          });
          state.sceneStatus = payload.scene_status || state.sceneStatus;
          await Promise.all([
            refreshSceneStatus(),
            refreshFiles(),
            refreshImageReview(),
            refreshStageGates(),
            refreshProjectStatus(),
            refreshProductionManifest(),
          ]);
        });
      } catch (error) {
        window.alert(error.message || "采用候选图失败。");
      }
      return;
    }

    if (target.dataset.regenerateImageKind) {
      await openImageRegenerateModal(
        target.dataset.regenerateImageKind,
        target.dataset.regenerateImageTarget || "",
        target.dataset.regenerateImageLabel || target.dataset.regenerateImageTarget || "",
        target.dataset.regenerateImageAsCandidate === "true"
      );
      return;
    }


    if (target.dataset.previewReference !== undefined) {
      const project = ensureProject();
      if (!project) return;
      const payload = await api(`/api/projects/${project.id}/content/references/${encodeURIComponent(target.dataset.previewReference)}`);
      const ref = payload.reference || {};
      showModal(
        ref.title || "参考资料预览",
        `
          <div class="stack">
            <div class="card card--inner">
              <div><strong>${escapeHtml(ref.title || "未命名参考")}</strong></div>
              <div class="muted">${escapeHtml(ref.source || "未知来源")}</div>
              ${payload.resolved_path ? `<div class="mono-path mono-path--sm">${escapeHtml(payload.resolved_path)}</div>` : ""}
              ${ref.url ? `<div style="margin-top:8px;"><a class="link-btn" href="${escapeHtml(ref.url)}" target="_blank" rel="noreferrer">打开来源</a></div>` : ""}
            </div>
            <pre class="json-box" style="white-space:pre-wrap;">${escapeHtml(payload.content || "")}</pre>
          </div>
        `
      );
    }

    if (target.dataset.previewVoiceKey) {
      const fieldKey = target.dataset.previewVoiceKey;
      const input = document.querySelector(`[data-config-key="${fieldKey}"]`);
      playDoubaoVoicePreview(input, target);
    }

    if (target.dataset.previewVoiceSelect) {
      const rateInput = target.dataset.previewRateInput
        ? document.getElementById(target.dataset.previewRateInput)
        : null;
      playDoubaoVoicePreview(
        document.getElementById(target.dataset.previewVoiceSelect),
        target,
        rateInput?.value || 1
      );
    }

    if (target.dataset.toggleSecret) {
      const key = target.dataset.toggleSecret;
      state.revealedSecrets[key] = !state.revealedSecrets[key];
      renderConfig();
    }

    if (target.dataset.toggleModelDropdown === "deepseek") {
      const dropdown = document.querySelector('[data-model-options="deepseek"]');
      const opening = dropdown?.classList.contains("hidden");
      document.querySelectorAll(".model-dropdown").forEach((item) => item.classList.add("hidden"));
      if (dropdown && opening) dropdown.classList.remove("hidden");
      target.setAttribute("aria-expanded", opening ? "true" : "false");
      return;
    }

    if (target.dataset.selectModel !== undefined) {
      const input = document.querySelector('[data-config-key="DEEPSEEK_MODEL"]');
      if (input) {
        input.value = target.dataset.selectModel;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
      document.querySelectorAll(".model-dropdown-option").forEach((item) => {
        item.classList.toggle("is-selected", item.dataset.selectModel === target.dataset.selectModel);
      });
      target.closest(".model-dropdown")?.classList.add("hidden");
      document.querySelector('[data-toggle-model-dropdown="deepseek"]')?.setAttribute("aria-expanded", "false");
      const status = document.querySelector('[data-model-sync-status="deepseek"]');
      try {
        await api("/api/settings/secrets", {
          method: "POST",
          body: JSON.stringify({ values: collectConfigValues() }),
        });
        await refreshConfig();
        if (status) {
          status.className = "model-sync-status is-success";
          status.textContent = `已切换并保存：${target.dataset.selectModel}`;
        }
      } catch (error) {
        if (status) {
          status.className = "model-sync-status is-error";
          status.textContent = error.message || "模型切换保存失败。";
        }
      }
      return;
    }

    if (target.dataset.saveSelectedModel === "deepseek") {
      const modelInput = document.querySelector('[data-config-key="DEEPSEEK_MODEL"]');
      const status = document.querySelector('[data-model-sync-status="deepseek"]');
      const model = modelInput?.value?.trim() || "";
      if (!model) {
        if (status) {
          status.className = "model-sync-status is-error";
          status.textContent = "请先选择或输入模型 ID。";
        }
        return;
      }
      const originalLabel = target.textContent;
      target.disabled = true;
      target.textContent = "保存中…";
      try {
        await api("/api/settings/secrets", {
          method: "POST",
          body: JSON.stringify({ values: collectConfigValues() }),
        });
        await refreshConfig();
        if (status) {
          status.className = "model-sync-status is-success";
          status.textContent = `当前已生效模型：${model}`;
        }
      } catch (error) {
        if (status) {
          status.className = "model-sync-status is-error";
          status.textContent = error.message || "模型保存失败。";
        }
      } finally {
        target.disabled = false;
        target.textContent = originalLabel;
      }
      return;
    }

    if (target.dataset.syncModels === "deepseek") {
      const button = target;
      const status = document.querySelector('[data-model-sync-status="deepseek"]');
      const baseUrlInput = document.querySelector('[data-config-key="DEEPSEEK_BASE_URL"]');
      const apiKeyInput = document.querySelector('[data-config-key="DEEPSEEK_API_KEY"]');
      const modelInput = document.querySelector('[data-config-key="DEEPSEEK_MODEL"]');
      const originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = "同步中…";
      if (status) {
        status.className = "model-sync-status is-loading";
        status.textContent = "正在读取当前接口的模型列表…";
      }
      try {
        const result = await api("/api/settings/deepseek/models", {
          method: "POST",
          body: JSON.stringify({
            base_url: baseUrlInput?.value?.trim() || "",
            api_key: apiKeyInput?.value?.trim() || "",
          }),
        });
        const models = Array.isArray(result?.models) ? result.models : [];
        const dropdown = document.querySelector('[data-model-options="deepseek"]');
        if (dropdown) {
          dropdown.innerHTML = models.map((model) => `<button type="button" class="model-dropdown-option${model === modelInput?.value ? " is-selected" : ""}" data-select-model="${escapeHtml(model)}">${escapeHtml(model)}</button>`).join("");
        }
        for (const section of state.config?.sections || []) {
          const field = (section.fields || []).find((item) => item.key === "DEEPSEEK_MODEL");
          if (field) field.options = models.map((model) => ({ value: model, label: model }));
        }
        if (modelInput && !modelInput.value && models.length) modelInput.value = models[0];
        if (status) {
          status.className = "model-sync-status is-success";
          status.textContent = `已同步 ${models.length} 个模型，可从输入框下拉选择。`;
        }
      } catch (error) {
        if (status) {
          status.className = "model-sync-status is-error";
          status.textContent = error.message || "模型同步失败。";
        }
      } finally {
        button.disabled = false;
        button.textContent = originalLabel;
      }
      return;
    }

    if (target.dataset.validateConfig) {
      await api("/api/settings/secrets", {
        method: "POST",
        body: JSON.stringify({ values: collectConfigValues() }),
      });
      await validateConfigSections([target.dataset.validateConfig]);
    }

    if (target.dataset.deleteFile) {
      const project = ensureProject();
      if (!project) return;
      if (!window.confirm(`确认删除 ${target.dataset.deleteFile} 吗？`)) return;
      await api(`/api/projects/${project.id}/files?relative_path=${encodeURIComponent(target.dataset.deleteFile)}`, { method: "DELETE" });
      await Promise.all([refreshFiles(), refreshSceneStatus(), refreshImageReview()]);
    }

    if (target.dataset.editReleaseMetrics) {
      openReleaseMetricsModal(Number(target.dataset.editReleaseMetrics));
    }

    if (target.dataset.deleteRelease) {
      const project = ensureProject();
      if (!project) return;
      await api(`/api/projects/${project.id}/releases/${target.dataset.deleteRelease}`, { method: "DELETE" });
      await refreshReleases();
    }
  });
}

bindEvents();
boot();
