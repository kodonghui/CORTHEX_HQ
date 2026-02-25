// ── 성능 최적화: CDN 라이브러리 동적 로드 헬퍼 ──
const _scriptCache = {};
function _loadScript(url) {
  if (_scriptCache[url]) return _scriptCache[url];
  _scriptCache[url] = new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${url}"]`)) { resolve(); return; }
    const s = document.createElement('script');
    s.src = url;
    s.onload = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
  });
  return _scriptCache[url];
}
const _CDN = {
  marked:       'https://cdn.jsdelivr.net/npm/marked/marked.min.js',
  chartjs:      'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js',
  mermaid:      'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js',
  forcegraph3d: 'https://unpkg.com/3d-force-graph@1/dist/3d-force-graph.min.js',
  drawflow:     'https://cdn.jsdelivr.net/npm/drawflow/dist/drawflow.min.js',
  drawflowcss:  'https://cdn.jsdelivr.net/npm/drawflow/dist/drawflow.min.css',
};
function _loadCSS(url) {
  return new Promise(resolve => {
    if (document.querySelector(`link[href="${url}"]`)) return resolve();
    const l = document.createElement('link');
    l.rel = 'stylesheet'; l.href = url;
    l.onload = resolve; document.head.appendChild(l);
  });
}

function corthexApp() {
  return {
    // State
    inputText: '',
    targetAgentId: '',  // 수신자 선택 (빈 문자열 = 자동 라우팅)
    messages: [],
    // 멀티턴 대화 세션
    currentConversationId: null,
    conversationList: [],
    showConversationDrawer: false,
    conversationTurnCount: 0,
    showScrollBtn: false,
    newMsgCount: 0,
    systemStatus: 'idle',
    wsConnected: false,
    totalCost: 0,
    totalTokens: 0,
    activityLogs: [],
    toolLogs: [],
    qaLogs: [],
    commsLogSubTab: 'activity',  // 'activity' | 'comms' | 'qa' | 'tools' — 통신로그 탭 내 서브탭
    activeAgents: {},
    agentToolCallCount: {},  // 에이전트별 도구 호출 횟수 (진행률 계산용)
    // 내부통신 (delegation log)
    showDelegationLog: false,
    delegationLogs: [],
    delegationLogLoading: false,
    delegationLogFilter: 'all',
    _delegationLogInterval: null,
    ws: null,
    logExpanded: true,
    sidebarOpen: window.innerWidth > 768,

    // ── Tab System ──
    activeTab: 'home',
    tabs: [
      { id: 'home', label: '작전현황', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1"/></svg>' },
      { id: 'command', label: '사령관실', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>' },
      { id: 'performance', label: '전력분석', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>' },
      { id: 'history', label: '작전일지', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>' },
      { id: 'schedule', label: '크론기지', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>' },
      { id: 'workflow', label: '자동화', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z"/></svg>' },
      { id: 'activityLog', label: '통신로그', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>' },
      { id: 'knowledge', label: '정보국', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>' },
      { id: 'archive', label: '기밀문서', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8"/></svg>' },
      { id: 'sns', label: '통신국', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z"/></svg>' },
      { id: 'archmap', label: '조직도', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>' },
      { id: 'trading', label: '전략실', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>' },
      { id: 'flowchart', label: 'NEXUS', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/><circle cx="12" cy="12" r="2.5"/><path stroke-linecap="round" d="M8 6h8M6 8v8M18 8v8M8 18h8M9 10.5l2 1M15 10.5l-2 1M9 13.5l2-1M15 13.5l-2-1"/></svg>' },
      { id: 'agora', label: 'AGORA', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3"/></svg>' },
    ],

    // ── Dashboard (홈) ──
    dashboard: { todayTasks: 0, todayCompleted: 0, todayFailed: 0, runningCount: 0, totalCost: 0, totalTokens: 0, agentCount: 0, recentCompleted: [], systemHealth: 'ok', loaded: false },

    // ── 사령관실: 최근 완료 작업 (새로고침 후에도 표시) ──
    recentCommandTasks: [],

    // ── Presets (명령 템플릿) ──
    presets: { items: [], showModal: false, editName: '', editCommand: '' },

    // ── Task History (작업내역) ──
    taskHistory: { items: [], search: '', filterStatus: 'all', filterDateFrom: '', filterDateTo: '', bookmarkOnly: false, selectedIds: [], expandedId: null, replayData: {}, compareMode: false, compareA: null, compareB: null, loaded: false, isSample: false, loading: false, error: null },

    // ── Performance (성능) ──
    performance: { agents: [], totalCalls: 0, totalCost: 0, totalTasks: 0, avgSuccessRate: 0, maxCost: 0, loaded: false },

    // ── Soul 자동 진화 ──
    soulEvolution: { proposals: [], loading: false, message: '' },

    // ── 품질 대시보드 ──
    qualityDash: { totalReviews: 0, passRate: 0, avgScore: 0, failed: 0, topRejections: [], loaded: false },
    _qualityChart: null,

    // ── Architecture Map (아키텍처 맵) ──
    archMap: {
      hierarchy: null, costByAgent: [], costByDivision: [], costSummary: null,
      costPeriod: 'month', loaded: false, mermaidRendered: false, subTab: 'orgchart',
    },
    _divDonutChart: null,
    _agentBarChart: null,

    // ── Error Alert ──
    errorAlert: { visible: false, message: '', severity: 'error' },

    // ── Schedules (예약) ──
    schedules: {
      items: [], showModal: false, editName: '', editCommand: '',
      editCronPreset: '매일 오전 9시',
      cronPresets: ['매일 오전 9시', '매일 오후 6시', '매주 월요일 오전 10시', '매주 금요일 오후 5시', '매시간', '30분마다'],
    },

    // ── Workflows (워크플로우) ──
    workflows: { items: [], showEditor: false, editing: null, editName: '', editDesc: '', editSteps: [{ name: '', command: '' }], runningId: null, lastResult: null },
    workflowExec: { show: false, workflowId: null, workflowName: '', mode: 'realtime', steps: [], currentStep: -1, done: false, error: null, finalResult: null },

    // ── Auth (인증) ──
    auth: { user: null, token: null, showLogin: false, loginUser: '', loginPass: '', loginError: '', role: 'ceo', bootstrapMode: true },

    // ── Memory Modal (에이전트 기억) ──
    memoryModal: { visible: false, agentId: '', agentName: '', items: [], newKey: '', newValue: '' },

    // Dark/Light mode
    darkMode: true,

    // ── Universal Delete Confirm (범용 삭제 확인) ──
    confirmDelete: { type: null, id: null, name: null },

    // Toast/Notification
    toasts: [],
    toastCounter: 0,
    notificationsEnabled: false,
    connectionLost: false,
    reconnectAttempt: 0,

    // Input experience
    commandHistory: [],
    historyIndex: -1,
    // 퀵 액션
    quickActionTab: 'routine',
    recentCommands: [],
    showMentionDropdown: false,
    mentionQuery: '',
    mentionResults: [],
    mentionGroups: [],
    // 슬래시 명령어 자동완성
    showSlashDropdown: false,
    slashSelectedIndex: 0,
    slashCommands: [
      { cmd: '/전체', args: '[메시지]', desc: '6명 처장에게 동시 지시', icon: '📡' },
      { cmd: '/순차', args: '[메시지]', desc: '에이전트 릴레이 모드', icon: '🔗' },
      { cmd: '/도구점검', args: '', desc: '전체 도구 상태 확인', icon: '🔧' },
      { cmd: '/배치실행', args: '', desc: '대기 중인 AI 요청 일괄 전송', icon: '📤' },
      { cmd: '/배치상태', args: '', desc: '배치 작업 진행 확인', icon: '📊' },
      { cmd: '/명령어', args: '', desc: '전체 명령어 목록', icon: '📋' },
      { cmd: '/토론', args: '[주제]', desc: '6명 처장 임원 토론 (2라운드)', icon: '🗣️' },
      { cmd: '/심층토론', args: '[주제]', desc: '6명 처장 심층 토론 (3라운드)', icon: '💬' },
    ],
    filteredSlashCommands: [],
    currentTaskId: null,

    // Welcome screen
    greeting: '',
    presetTab: '전체',
    presetTabs: ['전체', '전략', '분석', '법무', '마케팅'],
    backendPresets: [],
    // presetsLoaded 제거됨 (loadPresets에 통합)

    // View mode (chat panel)
    viewMode: 'chat',

    // Quality gate settings
    showQualitySettings: false,
    qualityRules: { rules: {}, rubrics: {}, known_divisions: [] },
    availableModels: [],
    selectedReviewModel: '',
    editingRubric: null,
    rubricEditName: '',
    rubricEditPrompt: '',
    rubricEditModel: '',
    rubricEditReasoning: '',
    qualitySaveStatus: '',

    // CEO profile modal
    showCeoProfile: false,

    // Tool detail modal
    toolDetailVisible: false,
    toolDetailData: null,

    // Agent config modal
    showAgentConfig: false,
    agentConfigData: null,
    agentConfigId: '',
    agentConfigTab: 'info',
    agentConfigLoading: false,
    agentSoulText: '',
    agentModelSelection: '',
    agentReasoningSelection: '',
    agentReasoningOptions: [],
    agentConfigSaveStatus: '',

    // Health check
    healthData: null,
    showHealthPopover: false,

    // Deploy status (배포 현황)
    deployStatus: { build: null, time: null, status: 'loading', commit: null },
    deployLogs: [],

    // Dashboard extras (budget, quality, task detail)
    dashboardRefreshTimer: null,
    budget: {},
    modelMode: 'auto',
    modelOverride: '',
    bulkModelSelection: '',
    bulkReasoningSelection: '',
    bulkReasoningOptions: [],
    bulkModelSaving: false,
    quality: {},
    showTaskDetail: false,
    taskDetailData: null,
    taskReplay: null,
    taskDetailTab: 'result',

    // Preset management
    showAddPreset: false,
    newPresetName: '',
    newPresetCommand: '',

    // More menu + new views
    // showMoreMenu 제거됨 (탭 바로 대체)
    activityLogFilter: 'all',

    // Knowledge management
    knowledge: { files: [], loading: false, selectedFile: null, content: '', editMode: false, saving: false, newFileName: '', newFolder: '', showCreateForm: false },

    // Archive browser
    archive: { files: [], loading: false, selectedReport: null, content: '', filterDivision: 'all', filterTier: 'all', searchCorrelation: '', selectedFiles: [], selectMode: false },
    archiveImportanceFilter: 'all',
    archiveTagFilter: [],
    showDeleteAllArchiveModal: false,

    // SNS management
    sns: { tab: 'status', status: {}, oauthStatus: {}, queue: [], events: [], loading: false,
           igCaption: '', igImageUrl: '', igVideoUrl: '', igReelCaption: '',
           ytFilePath: '', ytTitle: '', ytDesc: '', ytTags: '', ytPrivacy: 'private',
           rejectReason: '', rejectingId: null, queueFilter: 'all',
           mediaImages: [], mediaVideos: [],
           mediaSelectMode: false, selectedMedia: [],
           showDeleteAllMediaModal: false, showClearQueueModal: false },

    // ── Trading (자동매매 시스템) ──
    trading: {
      tab: 'dashboard',
      loading: false,
      refreshInterval: null,
      priceRefreshInterval: null,
      lastRefresh: '',
      summary: { portfolio: {}, strategies: {}, watchlist_count: 0, today: {}, signals_count: 0, bot_active: false, settings: {} },
      portfolio: { cash: 0, initial_cash: 50000000, holdings: [] },
      strategies: [],
      watchlist: [],
      history: [],
      signals: [],
      settings: {},
      botActive: false,
      runningNow: false,
      calibration: null,
      loadingSignals: false,
      decisions: [],
      expandedDecision: null,
      cioLogs: [],
      showCioLogs: true,
      // 활동로그 전용 탭
      activityLog: { logs: [], loading: false, filter: 'all', subTab: 'activity', autoScroll: true },
      // 주문 폼
      orderForm: { action: 'buy', ticker: '', name: '', qty: 0, price: 0, market: 'KR' },
      // 전략 추가 폼
      strategyForm: { name: '', type: 'rsi', indicator: 'RSI', buy_condition: 'RSI < 30', sell_condition: 'RSI > 70', target_tickers: '', stop_loss_pct: -5, take_profit_pct: 10, order_size: 1000000 },
      showStrategyModal: false,
      showOrderModal: false,
      showSettingsModal: false,
      // 관심종목 추가 폼
      watchForm: { ticker: '', name: '', target_price: 0, notes: '', market: 'KR' },
      showWatchModal: false,
      watchEditForm: { ticker: '', name: '', target_price: 0, notes: '', alert_type: 'above', market: 'KR' },
      showWatchEditModal: false,
      // 관심종목 선택 분석
      selectedWatchlist: [],
      analyzingSelected: false,
      // 관심종목 필터 + 드래그
      watchMarketFilter: 'all',
      draggedTicker: null,
      dragOverTicker: null,
      watchDragHint: true,
      // 관심종목 실시간 가격
      watchPrices: {},
      watchPricesLoading: false,
      watchPricesUpdatedAt: '',
      // 관심종목 차트
      showChartModal: false,
      chartTicker: '',
      chartName: '',
      chartMarket: 'KR',
      chartData: [],
      chartLoading: false,
      // 초기자금 설정
      initialCashInput: 50000000,
      // 모의거래 섹션 접기/펼치기
      showPaper: false,
      // 대시보드 서브탭 (실거래/모의투자)
      subTab: 'real',
      // 코크핏 상세 드롭다운 (실거래/모의투자)
      detailAccount: 'real',
    },

    // ── NEXUS 풀스크린 오버레이 ──
    nexusOpen: false,

    // ── NEXUS (3D / Canvas) ──
    flowchart: {
      mode: '3d',         // '3d' | 'canvas'
      // ── 3D 시스템 맵 ──
      graph3dLoaded: false,
      graph3dInstance: null,
      // ── 비주얼 캔버스 ──
      canvasLoaded: false,
      canvasEditor: null,
      canvasDirty: false,
      canvasName: '',
      canvasItems: [],
      showCanvasNameModal: false,
    },

    // ── AGORA (토론/논쟁 엔진) ──
    agoraOpen: false,
    agora: {
        sessionId: null,
        status: '',           // active/paused/completed
        totalRounds: 0,
        totalCost: 0,
        issues: [],           // [{id, title, status, parent_id, _depth}]
        selectedIssueId: null,
        rounds: [],           // 현재 선택된 쟁점의 라운드
        rightTab: 'diff',     // 'diff' | 'book'
        diffHtml: '',
        bookChapters: [],
        showPaperInput: false,
        inputTitle: '',
        inputPaper: '',
        sseSource: null,
    },

    // Org tree expand state
    expanded: {
      secretary: false,
      leet_master: true,
      tech: false,
      strategy: false,
      legal: false,
      marketing: false,
      investment: true,
      finance: false,
      publishing: false,
      tools: false,
    },

    // Agent name mapping (v4 — 6팀장 체제)
    agentNames: {
      'chief_of_staff': '비서실장',
      
      'cso_manager': '사업기획팀장',
      'clo_manager': '법무팀장',
      'cmo_manager': '마케팅팀장',
      'cio_manager': '금융분석팀장',
      'cpo_manager': '콘텐츠팀장',
      'argos': 'ARGOS',
    },

    // Agent initials for avatars
    agentInitials: {
      'chief_of_staff': 'CS',
      
      'cso_manager': '사업기',
      'clo_manager': '법무',
      'cmo_manager': '마케팅',
      'cio_manager': '금융분',
      'cpo_manager': '콘텐츠',
      'argos': '⚙',
    },

    // Division mapping for auto-expand
    agentDivision: {
      'chief_of_staff': 'secretary',
      
      'cso_manager': 'strategy',
      'clo_manager': 'legal',
      'cmo_manager': 'marketing',
      'cio_manager': 'finance',
      'cpo_manager': 'publishing',
      'argos': 'system',
    },

    // Agent color mapping
    agentColorMap: {
      'secretary': 'bg-hq-yellow/20 text-hq-yellow',
      'tech': 'bg-hq-cyan/20 text-hq-cyan',
      'strategy': 'bg-hq-cyan/20 text-hq-cyan',
      'legal': 'bg-hq-cyan/20 text-hq-cyan',
      'marketing': 'bg-hq-cyan/20 text-hq-cyan',
      'finance': 'bg-hq-purple/20 text-hq-purple',
      'publishing': 'bg-hq-green/20 text-hq-green',
    },
    agentRoles: {},
    agentModels: {},
    agentModelRaw: {},
    agentReasonings: {},

    // Dynamic agents/tools list (#5)
    agentsList: [],
    toolsList: [],

    // Feedback stats (#7)
    feedbackStats: { good: 0, bad: 0, total: 0, satisfaction_rate: 0 },

    // Budget edit (#8)
    showBudgetEdit: false,
    budgetEditDaily: 0,
    budgetEditMonthly: 0,

    // Tab grouping (#12)
    showMoreTabs: false,

    // Mobile responsive (#12-2)
    mobileMoreOpen: false,

    // Task history pagination (#14)
    taskHistoryPage: 1,
    taskHistoryPageSize: 20,

    // Batch mode toggle (#5)
    useBatch: false,

    // 배치 진행 상태 타이머
    batchProgress: { active: false, message: '', step: '', startedAt: null, elapsed: '00:00' },

    // Input hint — 고정 텍스트 (#18)
    inputHints: ['명령을 입력하세요 · /명령어 로 명령어 목록 확인'],
    inputHintIndex: 0,

    // ── Lazy load 플래그 (탭별 1회만 로드) ──
    _commandLoaded: false,
    _activityLogLoaded: false,
    _mermaidInited: false,

    init() {
      // ── Stage 1: 즉시 필요 (모든 화면 공통) ──
      const savedTheme = localStorage.getItem('corthex-theme');
      if (savedTheme === 'light') {
        this.darkMode = false;
        document.documentElement.classList.remove('dark');
      }
      this.greeting = this.getGreeting();
      this.requestNotificationPermission();
      this.checkAuth();

      // Marked 비동기 프리로드 (blocking 아님, 사령관실 진입 전까지 로드 완료)
      _loadScript(_CDN.marked);

      // 에이전트 목록 + WebSocket + 진행중 작업: 병렬
      this.loadAgentsAndTools();
      this.connectWebSocket();
      this.restoreRunningTask();

      // ── Stage 2: 기본 탭(홈) 데이터 ──
      this.loadDashboard();

      // ── Stage 3: 나머지는 switchTab()에서 lazy load ──
      // loadFeedbackStats → loadDashboard 안에 포함
      // restoreActivityLogs, fetchDelegationLogs, _connectCommsSSE → activityLog 탭 진입 시
      // loadConversation, loadPresets → command 탭 진입 시

      // 키보드 단축키 + 기타
      this.initKeyboardShortcuts();
      try { this.recentCommands = JSON.parse(localStorage.getItem('corthex-recent-cmds') || '[]'); } catch(e) { this.recentCommands = []; }

      // 타이머 (전역 필수만)
      this._batchTimer = setInterval(() => {
        if (this.batchProgress.active && this.batchProgress.startedAt) {
          const sec = Math.floor((Date.now() - this.batchProgress.startedAt) / 1000);
          const m = String(Math.floor(sec / 60)).padStart(2, '0');
          const s = String(sec % 60).padStart(2, '0');
          this.batchProgress.elapsed = `${m}:${s}`;
        }
      }, 1000);
      this.startElapsedTimer();
      this._budgetTimer = setInterval(async () => {
        try {
          const r = await fetch('/api/budget');
          if (r.ok) { const d = await r.json(); if (d.today_cost !== undefined) this.totalCost = d.today_cost; }
        } catch(e) {}
      }, 30000);

      // 페이지 언로드 시 정리
      window.addEventListener('beforeunload', () => {
        try { if (this.ws) this.ws.close(); } catch(e) {}
        try { if (this._commsSSE) this._commsSSE.close(); } catch(e) {}
        try { if (this.trading?.refreshInterval) clearInterval(this.trading.refreshInterval); } catch(e) {}
        try { if (this._batchTimer) clearInterval(this._batchTimer); } catch(e) {}
        try { if (this._budgetTimer) clearInterval(this._budgetTimer); } catch(e) {}
        try { if (this._elapsedTimer) clearInterval(this._elapsedTimer); } catch(e) {}
      });
      window.addEventListener('resize', () => {
        const w = window.innerWidth;
        if (w > 768 && !this.sidebarOpen) this.sidebarOpen = true;
        if (w <= 768 && this.sidebarOpen) this.sidebarOpen = false;
        if (w > 768) this.mobileMoreOpen = false;
      });
    },

    // ── Theme ──
    toggleTheme() {
      this.darkMode = !this.darkMode;
      if (this.darkMode) {
        document.documentElement.classList.add('dark');
        localStorage.setItem('corthex-theme', 'dark');
      } else {
        document.documentElement.classList.remove('dark');
        localStorage.setItem('corthex-theme', 'light');
      }
    },

    // 콘텐츠 파이프라인 — 제거됨 (2026-02-21)

    // ── Toast/Notification ──
    showToast(message, type = 'info') {
      const id = ++this.toastCounter;
      this.toasts.push({ id, message, type, visible: true });
      setTimeout(() => this.removeToast(id), 4000);
    },
    removeToast(id) {
      const t = this.toasts.find(t => t.id === id);
      if (t) t.visible = false;
      setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 300);
    },
    requestNotificationPermission() {
      if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission().then(p => { this.notificationsEnabled = p === 'granted'; });
      } else if ('Notification' in window && Notification.permission === 'granted') {
        this.notificationsEnabled = true;
      }
    },
    sendDesktopNotification(title, body) {
      if (this.notificationsEnabled && document.hidden) {
        new Notification(title, { body });
      }
    },

    // ── WebSocket ──
    connectWebSocket() {
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      this.ws = new WebSocket(`${protocol}//${location.host}/ws`);

      this.ws.onopen = () => {
        this.wsConnected = true;
        if (this.connectionLost) {
          this.connectionLost = false;
          this.reconnectAttempt = 0;
          this.showToast('서버에 다시 연결되었습니다.', 'success');
        }
      };

      this.ws.onclose = () => {
        this.wsConnected = false;
        this.connectionLost = true;
        this.reconnectAttempt++;
        setTimeout(() => this.connectWebSocket(), 3000);
      };

      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        this.handleWsMessage(msg);
      };
    },

    handleWsMessage(msg) {
      switch (msg.event) {
        case 'processing_start':
        case 'task_accepted':
          this.systemStatus = 'working';
          if (msg.data?.task_id) this.currentTaskId = msg.data.task_id;
          if (!this.messages.some(m => m.type === 'processing')) {
            this.messages.push({ type: 'processing', id: Date.now(), timestamp: new Date().toISOString() });
          }
          break;

        case 'agent_status': {
          const d = msg.data;
          const prev = this.activeAgents[d.agent_id] || {};
          const tools = prev.tools_used ? [...prev.tools_used] : [];
          if (d.tool_name && !tools.includes(d.tool_name)) tools.push(d.tool_name);
          this.activeAgents = { ...this.activeAgents, [d.agent_id]: {
            status: d.status,
            detail: d.detail || '',
            tools_used: d.status === 'working' ? tools : [],
            started_at: prev.started_at || (d.status === 'working' ? Date.now() : null),
            elapsed: prev.elapsed || '00:00',
            progress: d.progress ?? prev.progress ?? 0,
          }};
          if (d.status === 'working') {
            const div = this.agentDivision[d.agent_id];
            if (div) {
              this.expanded[div] = true;
              if (['tech','strategy','legal','marketing'].includes(div)) {
                this.expanded.leet_master = true;
              }
              if (div === 'finance') {
                this.expanded.investment = true;
                // P2-5: 새로고침 복구 — CIO팀 작업 중이면 runningNow 자동 활성화
                if (!this.trading.runningNow) {
                  this.trading.runningNow = true;
                  this._connectCommsSSE();
                }
              }
            }
          }
          break;
        }

        // P2-6: 시세 실시간 푸시 (WebSocket)
        case 'price_update': {
          const pd = msg.data;
          if (pd && pd.prices) {
            this.trading.watchPrices = pd.prices;
            if (pd.updated_at) {
              const dt = new Date(pd.updated_at);
              this.trading.watchPricesUpdatedAt = dt.toLocaleTimeString('ko-KR', {hour:'2-digit', minute:'2-digit'});
            }
          }
          break;
        }

        case 'activity_log':
          { const now = new Date(); const d = now.toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).replace(/\.\s*/g, '.').replace(/\.$/, ''); const t = now.toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false, hour: '2-digit', minute: '2-digit' }); msg.data.timeDate = d; msg.data.timeClock = t; msg.data.time = d + ' ' + t; }
          if (!msg.data.timestamp) msg.data.timestamp = Date.now();
          msg.data.action = msg.data.message || msg.data.action || '';
          if (!msg.data.action) break;
          // system 로그 숨기기 (B안 — 노이즈 제거)
          if (msg.data.agent_id === 'system') break;
          // level별 배열 분류 (4탭 지원)
          if (msg.data.level === 'tool') {
            const _tlTs = msg.data.timestamp || 0;
            const _tlAid = msg.data.agent_id || '';
            if (!this.toolLogs.find(l => l.timestamp === _tlTs && l.agent_id === _tlAid)) {
              this.toolLogs.push(msg.data);
              if (this.toolLogs.length > 100) this.toolLogs = this.toolLogs.slice(-100);
            }
          } else if (msg.data.level === 'qa_pass' || msg.data.level === 'qa_fail' || msg.data.level === 'qa_detail') {
            const _qaTs = msg.data.timestamp || 0;
            const _qaAid = msg.data.agent_id || '';
            const _qaAct = (msg.data.action || '').substring(0, 60);
            if (!this.qaLogs.find(l => l.timestamp === _qaTs && l.agent_id === _qaAid && (l.action || '').substring(0, 60) === _qaAct)) {
              this.qaLogs.push(msg.data);
              if (this.qaLogs.length > 200) this.qaLogs = this.qaLogs.slice(-200);
            }
          } else {
            // 중복 방지: timestamp + agent_id 기반 dedup
            const _alTs = msg.data.timestamp || 0;
            const _alAid = msg.data.agent_id || '';
            if (!this.activityLogs.find(l => l.timestamp === _alTs && l.agent_id === _alAid)) {
              this.activityLogs.push(msg.data);
              if (this.activityLogs.length > 50) this.activityLogs = this.activityLogs.slice(-50);
            }
          }
          this.saveActivityLogs();
          // 전략실 활동로그에도 CIO 관련이면 실시간 추가
          { const cioAgents = ['cio_manager', 'stock_analysis', 'market_condition', 'technical_analysis', 'risk_management'];
            const aid = (msg.data.agent_id || '').toLowerCase();
            if (cioAgents.some(k => aid.includes(k))) {
              const alId = 'al_' + (msg.data.timestamp || Date.now());
              if (!this.trading.activityLog.logs.find(l => l.id === alId)) {
                this.trading.activityLog.logs.unshift({
                  id: alId, type: 'activity', sender: msg.data.agent_id || '',
                  receiver: '', message: msg.data.action || msg.data.message || '',
                  tools: [], level: msg.data.level || 'info',
                  time: new Date().toISOString(), _ts: Date.now(),
                });
                if (this.trading.activityLog.logs.length > 300) this.trading.activityLog.logs = this.trading.activityLog.logs.slice(0, 300);
              }
            }
          }
          break;

        case 'cost_update':
          this.totalCost = msg.data.total_cost;
          this.totalTokens = msg.data.total_tokens;
          this.dashboard.todayCost = msg.data.total_cost;
          break;

        case 'delegation_log_update':
          if (msg.data) {
            // SSE와 중복 방지: ID를 dl_ 접두사로 정규화하여 통일
            const _rawWsId = String(msg.data.id || '');
            const wsId = _rawWsId.startsWith('dl_') ? _rawWsId : 'dl_' + _rawWsId;
            msg.data.id = wsId;  // REST/SSE 형식과 통일
            if (!this.delegationLogs.find(l => l.id === wsId)) {
              msg.data.source = msg.data.source || 'delegation';
              this.delegationLogs.unshift(msg.data);
              // 시간순 내림차순 정렬
              this.delegationLogs.sort((a, b) => {
                const ta = new Date(a.created_at || 0).getTime();
                const tb = new Date(b.created_at || 0).getTime();
                return tb - ta;
              });
              if (this.delegationLogs.length > 100) {
                this.delegationLogs = this.delegationLogs.slice(0, 100);
              }
            }
            // 전략실 활동로그에도 CIO 관련이면 실시간 추가
            const cioKw = ['CIO', '투자분석', 'stock_analysis', 'market_condition', 'technical_analysis', 'risk_management'];
            const dlSR = (msg.data.sender || '') + (msg.data.receiver || '');
            if (cioKw.some(k => dlSR.includes(k))) {
              const dlId = msg.data.id;  // line 677에서 이미 dl_ 접두사 정규화됨
              if (!this.trading.activityLog.logs.find(l => l.id === dlId)) {
                const rawTools = msg.data.tools_used || '';
                const tList = typeof rawTools === 'string'
                  ? rawTools.split(',').map(t => t.trim()).filter(Boolean)
                  : (Array.isArray(rawTools) ? rawTools : []);
                this.trading.activityLog.logs.unshift({
                  id: dlId,
                  type: msg.data.log_type || 'delegation',
                  sender: msg.data.sender || '',
                  receiver: msg.data.receiver || '',
                  message: msg.data.message || '',
                  tools: tList,
                  time: msg.data.created_at ? new Date(msg.data.created_at * 1000).toISOString() : new Date().toISOString(),
                  _ts: (msg.data.created_at || 0) * 1000 || Date.now(),
                });
                if (this.trading.activityLog.logs.length > 300) {
                  this.trading.activityLog.logs = this.trading.activityLog.logs.slice(0, 300);
                }
              }
            }
          }
          break;

        case 'batch_chain_progress':
          this.batchProgress.active = msg.data.step !== 'completed' && msg.data.step !== 'failed';
          this.batchProgress.message = msg.data.message || '';
          this.batchProgress.step = msg.data.step_label || msg.data.step || '';
          if (this.batchProgress.active && !this.batchProgress.startedAt) {
            this.batchProgress.startedAt = Date.now();
          }
          if (!this.batchProgress.active) {
            this.batchProgress.startedAt = null;
            this.batchProgress.elapsed = '00:00';
          }
          break;

        case 'workflow_progress':
          this.handleWorkflowProgress(msg.data);
          break;

        case 'pipeline_progress':
          this.handlePipelineProgress(msg.data);
          break;

        case 'trading_run_complete':
          // CIO 백그라운드 분석 완료 알림
          {
            if (this._tradingRunPoll) { clearInterval(this._tradingRunPoll); this._tradingRunPoll = null; }
            const d = msg.data || {};
            if (d.success) {
              this.showToast(`CIO 분석 완료! 시그널 ${d.signals_count||0}건 · 주문 ${d.orders_triggered||0}건 → 시그널탭 확인`, d.orders_triggered > 0 ? 'success' : 'info');
            } else {
              this.showToast('CIO 분석 완료 (결과 확인 필요)', 'info');
            }
            this.trading.tab = 'signals';
            this.loadTradingSummary();
            this.trading.runningNow = false;
            this.trading.analyzingSelected = false;
            this.trading.selectedWatchlist = [];
          }
          break;

        case 'telegram_message':
          // 텔레그램에서 온 CEO 메시지를 웹 채팅에 표시
          this.messages.push({ type: 'user', text: msg.data.text, source: 'telegram', timestamp: new Date().toISOString() });
          if (this.showScrollBtn) this.newMsgCount++;
          this.$nextTick(() => this.scrollToBottom());
          break;

        case 'proactive_message':
          // 능동적 에이전트가 자동 전송한 보고 메시지
          this.messages = this.messages.filter(m => m.type !== 'processing');
          const proactiveMsg = {
            type: 'result',
            content: `🤖 **[자동 보고: ${msg.data.schedule_name || '능동 에이전트'}]**\n\n${msg.data.content}`,
            agent_id: msg.data.agent_id,
            timestamp: new Date().toISOString(),
            isProactive: true
          };
          this.messages.push(proactiveMsg);
          this.systemStatus = 'idle';
          if (this.showScrollBtn) this.newMsgCount++;
          this.$nextTick(() => this.scrollToBottom());
          this.showToast(`🤖 자동 보고 도착: ${msg.data.schedule_name || '능동 에이전트'}`, 'info');
          break;

        case 'result':
        case 'task_completed':
          this.messages = this.messages.filter(m => m.type !== 'processing');
          const resultMsg = {
            type: 'result',
            content: msg.data.content,
            sender_id: msg.data.sender_id || 'chief_of_staff',
            handled_by: msg.data.handled_by || '비서실장',
            delegation: msg.data.delegation || '',
            model: msg.data.model || '',
            time_seconds: msg.data.time_seconds,
            cost: msg.data.cost,
            quality_score: msg.data.quality_score || null,
            task_id: this.currentTaskId || msg.data.task_id || '',
            collapsed: false,
            feedbackSent: false,
            feedbackRating: null,
            source: msg.data.source || 'web',
            timestamp: new Date().toISOString(),
          };
          // ── 중복 응답 방지 ── 같은 task_id+content가 이미 있으면 무시
          const _tid = resultMsg.task_id;
          const _cSnip = (resultMsg.content || '').slice(0, 200);
          const isDup = this.messages.some(m =>
            m.type === 'result' &&
            m.task_id && _tid && m.task_id === _tid &&
            (m.content || '').slice(0, 200) === _cSnip
          );
          if (isDup) {
            console.log('[WS] 중복 result 무시:', _tid);
            break;
          }
          this.messages.push(resultMsg);
          if (this.showScrollBtn) this.newMsgCount++;

          // DB에 AI 응답 저장
          (async () => {
            try {
              await fetch('/api/conversation/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  type: 'result',
                  content: resultMsg.content,
                  sender_id: resultMsg.sender_id,
                  handled_by: resultMsg.handled_by,
                  delegation: resultMsg.delegation,
                  model: resultMsg.model,
                  time_seconds: resultMsg.time_seconds,
                  cost: resultMsg.cost,
                  quality_score: resultMsg.quality_score,
                  task_id: resultMsg.task_id,
                  source: resultMsg.source,
                  conversation_id: this.currentConversationId,
                }),
              });
            } catch (e) {
              console.warn('AI 응답 저장 실패:', e);
            }
          })();

          this.systemStatus = 'idle';
          this.currentTaskId = null;
          this.totalCost = msg.data.cost || this.totalCost;
          this.showToast('작업이 완료되었습니다.', 'success');
          this.sendDesktopNotification('CORTHEX HQ', '작업이 완료되었습니다.');
          this.$nextTick(() => this.scrollToBottom());
          // 이중 스크롤: 마크다운 렌더링 후에도 스크롤
          setTimeout(() => this.scrollToBottom(), 300);
          // 남아있는 working 에이전트를 done으로 전환
          Object.keys(this.activeAgents).forEach(id => {
            if (this.activeAgents[id]?.status === 'working') {
              this.activeAgents[id].status = 'done';
              this.activeAgents[id].progress = 1.0;
              this.agentToolCallCount[id] = 0;  // 도구 호출 카운터 리셋
            }
          });
          // (#17) 에이전트 완료 상태 5초 유지 후 idle로
          Object.keys(this.activeAgents).forEach(id => {
            if (this.activeAgents[id]?.status === 'done') {
              setTimeout(() => {
                if (this.activeAgents[id]?.status === 'done') {
                  delete this.activeAgents[id];
                }
              }, 5000);
            }
          });
          // Refresh dashboard/history/feedback if currently viewing
          if (this.activeTab === 'home') { this.loadDashboard(); this.loadFeedbackStats(); }
          if (this.activeTab === 'history') this.loadTaskHistory();
          break;

        case 'error':
          this.messages = this.messages.filter(m => m.type !== 'processing');
          this.messages.push({ type: 'error', text: msg.data.message, timestamp: new Date().toISOString() });
          if (this.showScrollBtn) this.newMsgCount++;
          this.systemStatus = 'error';
          this.currentTaskId = null;
          this.errorAlert = { visible: true, message: msg.data.message || '오류가 발생했습니다', severity: 'error' };
          this.showToast(msg.data.message || '오류가 발생했습니다.', 'error');
          setTimeout(() => { this.systemStatus = 'idle'; }, 3000);
          setTimeout(() => { this.errorAlert.visible = false; }, 10000);
          break;

        case 'error_alert':
          this.errorAlert = { visible: true, message: msg.data.message, severity: msg.data.severity || 'error' };
          if (msg.data.severity !== 'critical') {
            setTimeout(() => { this.errorAlert.visible = false; }, 10000);
          }
          break;
      }
    },

    // 하드 리프레시(Ctrl+Shift+R) 후 서버에서 실행 중인 작업 상태 복원
    async restoreRunningTask() {
      try {
        const res = await fetch('/api/tasks?status=running&limit=5');
        if (!res.ok) return;
        const tasks = await res.json();
        if (!Array.isArray(tasks) || tasks.length === 0) return;
        // 10분 이상 된 running task는 무시 (좀비 태스크 방지)
        const TEN_MIN = 10 * 60 * 1000;
        const now = Date.now();
        const recentTasks = tasks.filter(t => {
          const created = new Date(t.started_at || t.created_at).getTime();
          return (now - created) < TEN_MIN;
        });
        if (recentTasks.length === 0) {
          // 오래된 running task는 서버에 취소 요청
          for (const t of tasks) {
            try { await fetch(`/api/tasks/${t.task_id}/cancel`, { method: 'POST' }); } catch(e) {}
          }
          return;
        }
        const task = recentTasks[0];
        this.currentTaskId = task.task_id;
        this.systemStatus = 'working';
        if (!this.messages.some(m => m.type === 'processing')) {
          this.messages.push({
            type: 'processing',
            id: Date.now(),
            timestamp: task.created_at || new Date().toISOString(),
            restoredCommand: task.command || ''
          });
        }
      } catch (e) {
        // 복원 실패 시 조용히 무시
      }
    },

    startElapsedTimer() {
      this._elapsedTimer = setInterval(() => {
        const updated = { ...this.activeAgents };
        let changed = false;
        Object.keys(updated).forEach(id => {
          if (updated[id].status === 'working' && updated[id].started_at) {
            const secs = Math.floor((Date.now() - updated[id].started_at) / 1000);
            const mm = String(Math.floor(secs / 60)).padStart(2, '0');
            const ss = String(secs % 60).padStart(2, '0');
            const elapsed = mm + ':' + ss;
            if (updated[id].elapsed !== elapsed) {
              updated[id] = { ...updated[id], elapsed };
              changed = true;
            }
          }
        });
        if (changed) this.activeAgents = updated;
      }, 1000);
    },

    // ── Input Experience ──
    async sendMessage() {
      const text = this.inputText.trim();
      if (!text || this.systemStatus === 'working') return;

      this.commandHistory.push(text);
      if (this.commandHistory.length > 50) this.commandHistory.shift();
      this.historyIndex = -1;

      // 최근 사용 명령 저장 (슬래시 명령 제외, 중복 제거, 최대 5개)
      if (!text.startsWith('/')) {
        this.recentCommands = [text, ...this.recentCommands.filter(c => c !== text)].slice(0, 5);
        localStorage.setItem('corthex-recent-cmds', JSON.stringify(this.recentCommands));
      }

      this.messages.push({ type: 'user', text, timestamp: new Date().toISOString() });
      this.inputText = '';
      this.activeAgents = {};
      this.agentToolCallCount = {};

      if (this.$refs.inputArea) this.$refs.inputArea.style.height = 'auto';

      // 대화 세션 자동 생성 (첫 메시지 시)
      if (!this.currentConversationId) {
        try {
          const sessRes = await fetch('/api/conversation/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              title: text.slice(0, 30) + (text.length > 30 ? '...' : ''),
              agent_id: this.targetAgentId || null,
            }),
          });
          const sessData = await sessRes.json();
          if (sessData.success) {
            this.currentConversationId = sessData.session.conversation_id;
          }
        } catch (e) {
          console.warn('대화 세션 생성 실패:', e);
        }
      }
      this.conversationTurnCount++;

      // DB에 사용자 메시지 저장
      try {
        await fetch('/api/conversation/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: 'user', text, conversation_id: this.currentConversationId }),
        });
      } catch (e) {
        console.warn('메시지 저장 실패:', e);
      }

      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          type: 'command',
          text,
          batch: this.useBatch,
          target_agent_id: this.targetAgentId || null,
          conversation_id: this.currentConversationId,
        }));
      }

      this.$nextTick(() => this.scrollToBottom());
      setTimeout(() => this.scrollToBottom(), 150);
    },

    sendPreset(text) {
      this.inputText = text;
      this.sendMessage();
    },

    handleInputKeydown(e) {
      // 슬래시 팝업이 열려있을 때 키보드 내비게이션
      if (this.showSlashDropdown) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          this.slashSelectedIndex = Math.min(this.slashSelectedIndex + 1, this.filteredSlashCommands.length - 1);
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          this.slashSelectedIndex = Math.max(0, this.slashSelectedIndex - 1);
          return;
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault();
          if (this.filteredSlashCommands[this.slashSelectedIndex]) {
            this.insertSlashCommand(this.filteredSlashCommands[this.slashSelectedIndex]);
          }
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          this.showSlashDropdown = false;
          return;
        }
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
        return;
      }
      if (e.key === 'ArrowUp' && !this.inputText.trim()) {
        e.preventDefault();
        if (this.commandHistory.length > 0) {
          if (this.historyIndex < this.commandHistory.length - 1) this.historyIndex++;
          this.inputText = this.commandHistory[this.commandHistory.length - 1 - this.historyIndex];
        }
        return;
      }
      if (e.key === 'ArrowDown' && this.historyIndex >= 0) {
        e.preventDefault();
        this.historyIndex--;
        this.inputText = this.historyIndex < 0 ? '' : this.commandHistory[this.commandHistory.length - 1 - this.historyIndex];
        return;
      }
      if (e.key === 'Escape') { this.showMentionDropdown = false; this.showSlashDropdown = false; }
    },

    handleInputChange(e) {
      const el = e.target;
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 200) + 'px';

      const text = this.inputText;

      // 슬래시 명령어 감지 — /로 시작하고 공백 전까지
      if (text.startsWith('/')) {
        const spaceIdx = text.indexOf(' ');
        const query = spaceIdx === -1 ? text : text.substring(0, spaceIdx);
        if (spaceIdx === -1) {
          this.filteredSlashCommands = this.slashCommands.filter(c =>
            c.cmd.startsWith(query) || c.cmd.includes(query)
          );
          this.showSlashDropdown = this.filteredSlashCommands.length > 0;
          this.slashSelectedIndex = 0;
        } else {
          this.showSlashDropdown = false;
        }
        this.showMentionDropdown = false;
        return;
      }
      this.showSlashDropdown = false;

      // @멘션 감지 — inputText에서 직접 패턴 추출 (커서 위치 의존 제거로 안정화)
      const atMatch = text.match(/(?:^| )@(\S*)$/);

      if (atMatch) {
        this.mentionQuery = atMatch[1].toLowerCase();
        const divLabels = {
          'secretary': '비서실', 'tech': '기술개발처', 'strategy': '사업기획처',
          'legal': '법무처', 'marketing': '마케팅처', 'finance': '투자분석처', 'publishing': '출판기록처'
        };
        const divOrder = ['secretary', 'tech', 'strategy', 'legal', 'marketing', 'finance', 'publishing'];
        const matches = Object.entries(this.agentNames)
          .filter(([id, name]) => !this.mentionQuery || id.toLowerCase().includes(this.mentionQuery) || name.toLowerCase().includes(this.mentionQuery))
          .map(([id, name]) => ({ id, name, div: this.agentDivision[id] || '' }));
        const groupMap = {};
        matches.forEach(a => { if (!groupMap[a.div]) groupMap[a.div] = []; groupMap[a.div].push(a); });
        this.mentionGroups = divOrder
          .filter(d => groupMap[d] && groupMap[d].length > 0)
          .map(d => ({ label: divLabels[d] || d, agents: groupMap[d] }));
        this.mentionResults = matches;
        this.showMentionDropdown = matches.length > 0;
      } else {
        this.showMentionDropdown = false;
        this.mentionGroups = [];
      }
    },

    insertSlashCommand(cmd) {
      this.inputText = cmd.args ? cmd.cmd + ' ' : cmd.cmd;
      this.showSlashDropdown = false;
      this.$nextTick(() => {
        const el = this.$refs.inputArea;
        if (el) { el.focus(); el.selectionStart = el.selectionEnd = this.inputText.length; el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 200) + 'px'; }
      });
    },

    insertMention(agent) {
      const el = this.$refs.inputArea;
      const cursorPos = el.selectionStart;
      const textBefore = this.inputText.substring(0, cursorPos);
      const textAfter = this.inputText.substring(cursorPos);
      const replaced = textBefore.replace(/@\S*$/, `@${agent.name} `);
      this.inputText = replaced + textAfter;
      this.showMentionDropdown = false;
      // @멘션 선택 시 수신자 드롭다운도 해당 에이전트로 자동 세팅
      this.targetAgentId = agent.id;
      this.$nextTick(() => { el.focus(); el.selectionStart = el.selectionEnd = replaced.length; el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 200) + 'px'; });
    },

    // 수신자 드롭다운용 부서별 에이전트 그룹 (mentionGroups와 동기화)
    getRecipientGroups() {
      const divLabels = {
        'secretary': '비서실', 'tech': '기술개발처', 'strategy': '사업기획처',
        'legal': '법무처', 'marketing': '마케팅처', 'finance': '투자분석처', 'publishing': '출판기록처'
      };
      const divOrder = ['secretary', 'tech', 'strategy', 'legal', 'marketing', 'finance', 'publishing'];
      const allAgents = Object.entries(this.agentNames)
        .map(([id, name]) => ({ id, name, div: this.agentDivision[id] || '' }));
      const groupMap = {};
      allAgents.forEach(a => { if (!groupMap[a.div]) groupMap[a.div] = []; groupMap[a.div].push(a); });
      return divOrder
        .filter(d => groupMap[d] && groupMap[d].length > 0)
        .map(d => ({ label: divLabels[d] || d, agents: groupMap[d] }));
    },

    cancelTask() {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'cancel', task_id: this.currentTaskId }));
      }
      this.systemStatus = 'idle';
      this.currentTaskId = null;
      this.messages = this.messages.filter(m => m.type !== 'processing');
      this.showToast('작업 취소를 요청했습니다.', 'warning');
    },

    // ── Welcome Screen ──
    getGreeting() {
      const hour = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Seoul' })).getHours();
      if (hour < 6) return '새벽에도 열일하시네요, 고동희 대표님';
      if (hour < 12) return '좋은 아침입니다, 고동희 대표님';
      if (hour < 18) return '환영합니다, 고동희 대표님';
      if (hour < 22) return '좋은 저녁입니다, 고동희 대표님';
      return '오늘도 수고하셨습니다, 고동희 대표님';
    },

    // loadBackendPresets는 loadPresets()에 통합됨

    getFilteredPresets() {
      const defaults = [
        { name: '기술 스택 제안', command: 'LEET MASTER 서비스의 기술 스택을 제안해줘', category: '전략', color: 'hq-cyan', desc: 'CTO + 기술팀이 최적의 아키텍처를 설계합니다' },
        { name: '주가 분석', command: '삼성전자 주가를 분석해줘', category: '분석', color: 'hq-purple', desc: '4명의 투자분석팀이 병렬로 분석합니다' },
        { name: '이용약관 작성', command: '서비스 이용약관 초안을 만들어줘', category: '법무', color: 'hq-green', desc: 'CLO + 법무팀이 법적 문서를 작성합니다' },
        { name: '마케팅 전략', command: '마케팅 콘텐츠 전략을 수립해줘', category: '마케팅', color: 'hq-yellow', desc: 'CMO + 마케팅팀이 전략을 수립합니다' },
        { name: '사업계획서', command: '스타트업 사업계획서 초안을 작성해줘', category: '전략', color: 'hq-cyan', desc: 'CSO + 사업기획팀이 사업계획을 수립합니다' },
        { name: '특허 분석', command: '우리 서비스의 특허 가능성을 분석해줘', category: '법무', color: 'hq-green', desc: 'CLO + 법무팀이 특허 가능성을 분석합니다' },
        ...this.backendPresets.map(p => ({
          name: p.name, command: p.command, category: '전체', color: 'hq-accent',
          desc: p.command.length > 40 ? p.command.substring(0, 40) + '...' : p.command,
          isServer: true,
        })),
      ];
      if (this.presetTab === '전체') return defaults;
      return defaults.filter(p => p.category === this.presetTab);
    },

    // ── Result Helpers ──
    copyToClipboard(text) {
      navigator.clipboard.writeText(text).then(
        () => this.showToast('클립보드에 복사되었습니다.', 'success'),
        () => this.showToast('복사에 실패했습니다.', 'error')
      );
    },
    isLongContent(content) { return content && content.length > 1500; },
    getQualityBadge(score) {
      // 1~5 스케일 (하이브리드 검수 가중 평균)
      if (!score) return { label: '-', cls: 'bg-hq-muted/10 text-hq-muted' };
      if (score >= 4.5) return { label: 'A+', cls: 'bg-hq-green/20 text-hq-green border-hq-green/30' };
      if (score >= 3.5) return { label: 'A', cls: 'bg-hq-green/15 text-hq-green/80 border-hq-green/20' };
      if (score >= 3.0) return { label: 'B', cls: 'bg-hq-yellow/15 text-hq-yellow border-hq-yellow/20' };
      if (score >= 2.0) return { label: 'C', cls: 'bg-hq-yellow/10 text-hq-yellow/80 border-hq-yellow/15' };
      return { label: 'D', cls: 'bg-hq-red/15 text-hq-red border-hq-red/20' };
    },

    // ── Agent Helpers ──
    scrollToAgent(agentId) {
      const div = this.agentDivision[agentId];
      if (div) {
        this.expanded[div] = true;
        if (['tech','strategy','legal','marketing'].includes(div)) this.expanded.leet_master = true;
        if (div === 'finance') this.expanded.investment = true;
      }
      this.$nextTick(() => {
        const el = document.getElementById('agent-' + agentId);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.classList.add('bg-hq-yellow/10');
          setTimeout(() => el.classList.remove('bg-hq-yellow/10'), 2000);
        }
      });
    },

    // ── Task Detail Modal ──
    async openTaskDetail(taskId) {
      this.taskDetailData = null;
      this.taskReplay = null;
      this.taskDetailTab = 'result';
      this.showTaskDetail = true;
      try {
        const res = await fetch(`/api/tasks/${taskId}`);
        if (res.ok) this.taskDetailData = await res.json();
        else this.showToast('작업 정보를 불러올 수 없습니다.', 'error');
      } catch {
        this.showToast('작업 상세 로드 실패', 'error');
      }
    },

    async loadTaskReplay(taskId) {
      this.taskReplay = null;
      try {
        const res = await fetch(`/api/replay/${taskId}`);
        if (res.ok) this.taskReplay = await res.json();
        else {
          const latest = await fetch('/api/replay/latest');
          if (latest.ok) this.taskReplay = await latest.json();
          else this.taskReplay = {};
        }
      } catch {
        this.taskReplay = {};
      }
    },

    renderTaskDetailReplay(node, depth) {
      if (!node) return '';
      const indent = depth * 20;
      const color = depth === 0 ? 'hq-accent' : depth === 1 ? 'hq-cyan' : 'hq-purple';
      let html = `<div style="margin-left:${indent}px" class="flex items-start gap-2 p-2 bg-hq-surface rounded-lg mb-1">
        <span class="w-2 h-2 rounded-full bg-${color} mt-1.5 shrink-0"></span>
        <div>
          <span class="text-xs font-bold text-${color}">${this.getAgentName(node.agent_id || node.agent || '')}</span>
          ${node.action ? `<span class="text-xs text-hq-muted ml-2">${node.action}</span>` : ''}
          ${node.result ? `<div class="text-xs text-hq-text/60 mt-1 truncate max-w-lg">${(node.result || '').substring(0, 100)}${(node.result||'').length > 100 ? '...' : ''}</div>` : ''}
        </div>
      </div>`;
      if (node.children && Array.isArray(node.children)) {
        node.children.forEach(child => { html += this.renderTaskDetailReplay(child, depth + 1); });
      }
      return html;
    },

    // ── Existing Helpers ──
    toggleSection(section) {
      this.expanded[section] = !this.expanded[section];
    },

    getAgentName(id) {
      return this.agentNames[id] || id;
    },

    fetchDelegationLogs(silent = false) {
      if (!silent) this.delegationLogLoading = true;
      fetch('/api/comms/messages?limit=50')
        .then(r => r.json())
        .then(data => {
          const newLogs = (Array.isArray(data) ? data : []);
          // 시간순 내림차순 정렬 (최신 → 오래된 순)
          newLogs.sort((a, b) => {
            const ta = new Date(a.created_at || 0).getTime();
            const tb = new Date(b.created_at || 0).getTime();
            return tb - ta;
          });
          if (newLogs.length !== this.delegationLogs.length ||
              (newLogs[0]||{}).id !== (this.delegationLogs[0]||{}).id) {
            this.delegationLogs = newLogs;
          }
          if (!silent) this.delegationLogLoading = false;
        })
        .catch(() => { if (!silent) this.delegationLogLoading = false; });
    },
    _commsSSE: null,
    _connectCommsSSE() {
      if (this._commsSSE) return;
      try {
        this._commsSSE = new EventSource('/api/comms/stream');
        const cioKeywords = ['CIO', '투자분석', '시황분석', '종목분석', '기술적분석', '리스크관리'];
        this._commsSSE.addEventListener('comms', (e) => {
          try {
            const msg = JSON.parse(e.data);
            // ID 정규화: REST는 "dl_123" 형식, SSE/WS는 123 원본 → dl_ 접두사 통일
            const rawId = msg.id;
            const dlId = String(rawId).startsWith('dl_') ? rawId : 'dl_' + rawId;
            msg.id = dlId;
            // 사령관실 교신로그 (중복 방지 — 원본 ID + dl_ 접두사 ID 모두 체크)
            if (!this.delegationLogs.find(l => l.id === dlId || l.id === rawId)) {
              this.delegationLogs.unshift(msg);
              this.delegationLogs.sort((a, b) => {
                const ta = new Date(a.created_at || 0).getTime();
                const tb = new Date(b.created_at || 0).getTime();
                return tb - ta;
              });
              if (this.delegationLogs.length > 100) this.delegationLogs = this.delegationLogs.slice(0, 100);
            }
            // CIO 전략실 로그 (키워드 필터링)
            const s = (msg.sender || '') + (msg.receiver || '');
            if (cioKeywords.some(k => s.includes(k))) {
              if (!this.trading.cioLogs.find(l => l.id === dlId || l.id === rawId)) {
                msg._fresh = true;
                this.trading.cioLogs.unshift(msg);
                if (this.trading.cioLogs.length > 50) this.trading.cioLogs = this.trading.cioLogs.slice(0, 50);
                setTimeout(() => { msg._fresh = false; }, 2000);
                // 전략실 활동로그에도 추가
                const toolsRaw = msg.tools_used || '';
                const toolsList = typeof toolsRaw === 'string'
                  ? toolsRaw.split(',').map(t => t.trim()).filter(Boolean)
                  : (Array.isArray(toolsRaw) ? toolsRaw : []);
                const alEntry = {
                  id: msg.id,  // line 1327에서 이미 dl_ 접두사 정규화됨
                  type: msg.log_type || 'delegation',
                  sender: msg.sender || '',
                  receiver: msg.receiver || '',
                  message: msg.message || '',
                  tools: toolsList,
                  time: msg.created_at ? new Date(msg.created_at * 1000).toISOString() : new Date().toISOString(),
                  _ts: (msg.created_at || 0) * 1000 || Date.now(),
                };
                if (!this.trading.activityLog.logs.find(l => l.id === alEntry.id)) {
                  this.trading.activityLog.logs.unshift(alEntry);
                  if (this.trading.activityLog.logs.length > 300) this.trading.activityLog.logs = this.trading.activityLog.logs.slice(0, 300);
                }
              }
            }
          } catch(err) {}
        });
        this._commsSSE.onerror = () => {};
      } catch(err) {}
    },
    toggleDelegationLog() {
      this.showDelegationLog = !this.showDelegationLog;
      if (this.showDelegationLog) {
        this.fetchDelegationLogs();
        this._connectCommsSSE();
      }
    },
    getFilteredDelegationLogs() {
      if (this.delegationLogFilter === 'all') return this.delegationLogs;
      if (this.delegationLogFilter === 'p2p') return this.delegationLogs.filter(l => l.source === 'cross_agent');
      return this.delegationLogs.filter(l => l.log_type === this.delegationLogFilter);
    },

    getAgentInitials(id) {
      if (!id) return '??';
      return this.agentInitials[id] || id.substring(0, 2).toUpperCase();
    },

    getAgentAvatarClass(id) {
      if (!id) return 'bg-hq-accent/20 text-hq-accent';
      const div = this.agentDivision[id];
      return this.agentColorMap[div] || 'bg-hq-accent/20 text-hq-accent';
    },

    getAgentDotClass(id) {
      const status = this.activeAgents[id];
      if (!status) return 'bg-hq-muted/40';
      switch (status.status) {
        case 'working': return 'bg-hq-green pulse-dot';
        case 'waiting': return 'bg-amber-400 animate-pulse shadow-[0_0_10px_rgba(251,191,36,0.6)]';
        case 'done': return 'bg-hq-green/40';
        case 'idle': return 'bg-hq-muted/40';
        default: return 'bg-hq-muted/30';
      }
    },

    getAgentColor(agentId) {
      if (!agentId) return '';
      const id = agentId.toLowerCase();
      if (id.includes('cio')) return 'text-yellow-400';
      if (id.includes('cmo') || id.includes('marketing')) return 'text-purple-400';
      if (id.includes('cto') || id.includes('tech')) return 'text-blue-400';
      if (id.includes('clo') || id.includes('legal')) return 'text-red-400';
      if (id.includes('cho') || id.includes('hr')) return 'text-green-400';
      if (id.includes('cso') || id.includes('strategy')) return 'text-orange-400';
      return '';
    },

    toggleArchiveTag(tag) {
      const idx = this.archiveTagFilter.indexOf(tag);
      if (idx > -1) this.archiveTagFilter.splice(idx, 1);
      else this.archiveTagFilter.push(tag);
    },

    getSectionBadgeClass(section) {
      const ids = this.getSectionAgentIds(section);
      const hasWorking = ids.some(id => this.activeAgents[id]?.status === 'working');
      if (hasWorking) return 'bg-hq-yellow/15 text-hq-yellow border border-hq-yellow/20';
      const hasDone = ids.some(id => this.activeAgents[id]?.status === 'done');
      if (hasDone) return 'bg-hq-green/15 text-hq-green border border-hq-green/20';
      return 'hidden';
    },

    getSectionStatusColor(section) {
      const ids = this.getSectionAgentIds(section);
      const hasWorking = ids.some(id => this.activeAgents[id]?.status === 'working');
      if (hasWorking) return 'text-hq-yellow';
      const hasDone = ids.some(id => this.activeAgents[id]?.status === 'done');
      if (hasDone) return 'text-hq-green';
      return 'text-hq-muted/70';
    },

    getSectionStatusText(section) {
      const ids = this.getSectionAgentIds(section);
      const working = ids.filter(id => this.activeAgents[id]?.status === 'working').length;
      if (working > 0) return `${working}명 작업중`;
      const done = ids.filter(id => this.activeAgents[id]?.status === 'done').length;
      if (done > 0) return `${done}명 완료`;
      return '';
    },

    getSectionAgentIds(section) {
      if (section === 'leet_master') {
        return Object.entries(this.agentDivision)
          .filter(([_, div]) => ['tech','strategy','legal','marketing'].includes(div))
          .map(([id]) => id);
      }
      if (section === 'investment') {
        return Object.entries(this.agentDivision)
          .filter(([_, div]) => div === 'finance')
          .map(([id]) => id);
      }
      return Object.entries(this.agentDivision)
        .filter(([_, div]) => div === section)
        .map(([id]) => id);
    },

    stripMarkdown(text) {
      if (!text) return '';
      return text
        .replace(/\*\*(.*?)\*\*/g, '$1')
        .replace(/\*(.*?)\*/g, '$1')
        .replace(/#{1,6}\s*/g, '')
        .replace(/---+/g, '')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/^\s*[-*+]\s/gm, '')
        .replace(/\n+/g, ' ')
        .trim();
    },

    renderMarkdown(text) {
      if (typeof marked === 'undefined') {
        // marked 미로드 시 plaintext 반환 (init에서 비동기 프리로드 중)
        return (text || '').replace(/</g, '&lt;').replace(/\n/g, '<br>');
      }
      try {
        let html = marked.parse(text || '');
        html = html.replace(/■\s*/g, '<span class="badge-marker badge-marker-primary"></span>');
        return html;
      }
      catch { return text; }
    },

    // ── Quality Gate Settings ──────────────────

    sortModels(models) {
      const tierOrder = { executive: 0, manager: 1, specialist: 2, worker: 3 };
      return models.sort((a, b) => {
        const ta = tierOrder[a.tier] ?? 99;
        const tb = tierOrder[b.tier] ?? 99;
        if (ta !== tb) return ta - tb;
        return (b.cost_output || 0) - (a.cost_output || 0);
      });
    },

    getModelDisplayName(modelName) {
      const names = {
        'claude-opus-4-6': 'Claude Opus 4.6',
        'claude-sonnet-4-6': 'Claude Sonnet 4.6',
        'claude-haiku-4-5-20251001': 'Claude Haiku 4.5',
        'gpt-5.2-pro': 'GPT-5.2 Pro',
        'gpt-5.2': 'GPT-5.2',
        'gpt-5': 'GPT-5',
        'gpt-5-mini': 'GPT-5 Mini',
        'gemini-3.1-pro-preview': 'Gemini 3.1 Pro Preview',
        'gemini-2.5-pro': 'Gemini 2.5 Pro',
        'gemini-2.5-flash': 'Gemini 2.5 Flash',
      };
      return names[modelName] || modelName;
    },

    // 모델별 기본 추론 옵션 (서버에서 reasoning_levels를 못 받았을 때 fallback)
    _getDefaultReasoning(modelName) {
      const map = {
        'claude-opus-4-6': ['low','medium','high'],
        'claude-sonnet-4-6': ['low','medium','high'],
        'claude-haiku-4-5-20251001': [],
        'gpt-5-mini': ['low','medium','high'],
        'gpt-5': ['none','low','medium','high'],
        'gpt-5.2': ['none','low','medium','high','xhigh'],
        'gpt-5.2-pro': ['medium','high','xhigh'],
        'gemini-3.1-pro-preview': ['low','high'],
        'gemini-2.5-pro': ['low','medium','high'],
        'gemini-2.5-flash': ['none','low','medium','high'],
      };
      return map[modelName] || [];
    },

    // 에이전트 카드 라벨 업데이트
    _updateAgentCardLabel(agentId) {
      const modelName = this.agentConfigData?.model_name || this.agentModelRaw[agentId] || '';
      const reasoning = this.agentConfigData?.reasoning_effort || this.agentReasonings[agentId] || '';
      this.agentModels[agentId] = modelName;
      this.agentModelRaw[agentId] = modelName;
      this.agentReasonings[agentId] = reasoning;
    },

    getModelTierLabel(tier) {
      const labels = { executive: '임원급', manager: '매니저급', specialist: '전문가급', worker: '실무급' };
      return labels[tier] || tier;
    },

    getModelsByProvider() {
      const ordered = { 'Anthropic (Claude)': [], 'Google (Gemini)': [], 'OpenAI': [] };
      for (const m of (this.availableModels || [])) {
        const prov = m.provider || 'other';
        const label = prov === 'anthropic' ? 'Anthropic (Claude)' : prov === 'google' ? 'Google (Gemini)' : prov === 'openai' ? 'OpenAI' : prov;
        if (!ordered[label]) ordered[label] = [];
        ordered[label].push(m);
      }
      // 빈 그룹 제거
      for (const key of Object.keys(ordered)) {
        if (ordered[key].length === 0) delete ordered[key];
      }
      return ordered;
    },

    async loadQualityRules() {
      try {
        const rulesRes = await fetch('/api/quality-rules').then(r => r.json());
        this.qualityRules = rulesRes;
      } catch (e) {
        console.error('Failed to load quality rules:', e);
      }
    },

    startEditRubric(division) {
      this.editingRubric = division;
    },

    async saveRubric() {
      if (!this.editingRubric) return;
      this.qualitySaveStatus = 'saving';
      try {
        const res = await fetch(`/api/quality-rules/rubric/${this.editingRubric}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: this.rubricEditName,
            prompt: this.rubricEditPrompt,
            model: this.rubricEditModel || null,
            reasoning_effort: this.rubricEditReasoning || null,
          }),
        }).then(r => r.json());
        if (res.success) {
          if (!this.qualityRules.rubrics) this.qualityRules.rubrics = {};
          this.qualityRules.rubrics[this.editingRubric] = {
            name: this.rubricEditName,
            prompt: this.rubricEditPrompt,
            model: this.rubricEditModel,
            reasoning_effort: this.rubricEditReasoning,
          };
          this.editingRubric = null;
          this.qualitySaveStatus = 'saved';
        } else {
          this.qualitySaveStatus = 'error';
        }
      } catch {
        this.qualitySaveStatus = 'error';
      }
      setTimeout(() => { this.qualitySaveStatus = ''; }, 2500);
    },

    async deleteRubric(division) {
      if (!division || division === 'default') return;
      this.qualitySaveStatus = 'saving';
      try {
        const res = await fetch(`/api/quality-rules/rubric/${division}`, {
          method: 'DELETE',
        }).then(r => r.json());
        if (res.success) {
          if (this.qualityRules.rubrics) delete this.qualityRules.rubrics[division];
          this.editingRubric = null;
          this.qualitySaveStatus = 'saved';
        } else {
          this.qualitySaveStatus = 'error';
        }
      } catch {
        this.qualitySaveStatus = 'error';
      }
      setTimeout(() => { this.qualitySaveStatus = ''; }, 2500);
    },

    // ── Office & Agent Config ──
    getAgentStatusLight(agentId) {
      const agent = this.activeAgents[agentId];
      if (!agent) return 'status-light-idle';
      if (agent.status === 'working') return 'status-light-working';
      if (agent.status === 'done') return 'status-light-done';
      return 'status-light-idle';
    },

    showToolDetail(tool) {
      this.toolDetailData = tool;
      this.toolDetailVisible = true;
    },

    async openAgentConfig(agentId) {
      this.agentConfigId = agentId;
      this.agentConfigLoading = true;
      this.showAgentConfig = true;
      this.agentConfigTab = 'info';
      this.agentConfigSaveStatus = '';
      try {
        const [agentRes, modelsRes] = await Promise.all([
          fetch(`/api/agents/${agentId}`).then(r => r.json()),
          this.availableModels.length ? Promise.resolve(this.availableModels) :
            fetch('/api/available-models').then(r => r.json()),
        ]);
        // 서버 에러 체크 (서버 초기화 실패 등)
        if (agentRes.error) {
          this.showToast('에이전트 로드 실패: ' + agentRes.error, 'error');
          this.showAgentConfig = false;
          return;
        }
        this.agentConfigData = agentRes;
        if (!this.availableModels.length && Array.isArray(modelsRes)) {
          this.availableModels = this.sortModels(modelsRes);
        }
        this.agentSoulText = agentRes.system_prompt || '';
        this.agentModelSelection = agentRes.model_name || '';
        this.agentReasoningSelection = agentRes.reasoning_effort || '';
        // 현재 모델의 추론 정도 옵션 조회
        const currentModel = this.availableModels.find(m => m.name === this.agentModelSelection);
        this.agentReasoningOptions = currentModel?.reasoning_levels || [];
        // Fallback: 모델 목록 로딩 실패해도 기본 추론 옵션 제공
        if (this.agentReasoningOptions.length === 0 && this.agentModelSelection) {
          this.agentReasoningOptions = this._getDefaultReasoning(this.agentModelSelection);
        }
      } catch (e) {
        this.showToast('에이전트 정보를 불러올 수 없습니다: ' + (e.message || '서버 연결 실패'), 'error');
        this.showAgentConfig = false;
      } finally {
        this.agentConfigLoading = false;
      }
    },

    async saveAgentSoul() {
      this.agentConfigSaveStatus = 'saving';
      try {
        const res = await fetch(`/api/agents/${this.agentConfigId}/soul`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ system_prompt: this.agentSoulText }),
        }).then(r => r.json());
        if (res.error) {
          this.showToast(res.error, 'error');
          this.agentConfigSaveStatus = 'error';
        } else {
          this.agentConfigData.system_prompt = this.agentSoulText;
          this.agentConfigSaveStatus = 'saved';
          this.showToast('소울이 저장되었습니다.', 'success');
        }
      } catch (e) {
        this.agentConfigSaveStatus = 'error';
        this.showToast('소울 저장 실패: ' + (e.message || '서버 연결 오류'), 'error');
      }
      setTimeout(() => { this.agentConfigSaveStatus = ''; }, 2500);
    },

    async saveAgentModel() {
      this.agentConfigSaveStatus = 'saving';
      try {
        const res = await fetch(`/api/agents/${this.agentConfigId}/model`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_name: this.agentModelSelection }),
        }).then(r => r.json());
        if (res.error) {
          this.showToast(res.error, 'error');
          this.agentConfigSaveStatus = 'error';
        } else {
          this.agentConfigData.model_name = this.agentModelSelection;
          // 모델 변경 시 추론 옵션도 갱신
          const newModel = this.availableModels.find(m => m.name === this.agentModelSelection);
          this.agentReasoningOptions = newModel?.reasoning_levels || [];
          // Fallback
          if (this.agentReasoningOptions.length === 0 && this.agentModelSelection) {
            this.agentReasoningOptions = this._getDefaultReasoning(this.agentModelSelection);
          }
          // 현재 선택된 추론 정도가 새 모델에서 지원 안 되면 초기화
          if (this.agentReasoningSelection && !this.agentReasoningOptions.includes(this.agentReasoningSelection)) {
            this.agentReasoningSelection = '';
            this.agentConfigData.reasoning_effort = '';
          }
          // 사무실 뷰 카드에도 반영 (표시명 + 추론레벨 형식)
          this._updateAgentCardLabel(this.agentConfigId);
          // 개별 모델 변경 → 자동으로 '수동' 모드 전환
          if (this.modelMode !== 'manual') {
            this.modelMode = 'manual';
            fetch('/api/model-mode', {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ mode: 'manual' }),
            }).catch(() => {});
          }
          this.agentConfigSaveStatus = 'saved';
          this.showToast('모델이 변경되었습니다.', 'success');
        }
      } catch (e) {
        this.agentConfigSaveStatus = 'error';
        this.showToast('모델 변경 실패: ' + (e.message || '서버 연결 오류'), 'error');
      }
      setTimeout(() => { this.agentConfigSaveStatus = ''; }, 2500);
    },

    async saveAgentReasoning() {
      this.agentConfigSaveStatus = 'saving';
      try {
        const res = await fetch(`/api/agents/${this.agentConfigId}/reasoning`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reasoning_effort: this.agentReasoningSelection }),
        }).then(r => r.json());
        if (res.error) {
          this.showToast(res.error, 'error');
          this.agentConfigSaveStatus = 'error';
        } else {
          this.agentConfigData.reasoning_effort = this.agentReasoningSelection;
          // 사무실 뷰 카드에도 반영 (표시명 + 추론레벨 형식)
          this._updateAgentCardLabel(this.agentConfigId);
          // 개별 추론 변경 → 자동으로 '수동' 모드 전환
          if (this.modelMode !== 'manual') {
            this.modelMode = 'manual';
            fetch('/api/model-mode', {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ mode: 'manual' }),
            }).catch(() => {});
          }
          this.agentConfigSaveStatus = 'saved';
          this.showToast('추론 정도가 변경되었습니다.', 'success');
        }
      } catch (e) {
        this.agentConfigSaveStatus = 'error';
        this.showToast('추론 정도 변경 실패: ' + (e.message || '서버 연결 오류'), 'error');
      }
      setTimeout(() => { this.agentConfigSaveStatus = ''; }, 2500);
    },

    // ── Tab Switching ──

    switchTab(tabId) {
      this.activeTab = tabId;
      if (window.innerWidth <= 768) this.sidebarOpen = false;
      if (tabId !== 'command' && this.dashboardRefreshTimer) {
        clearInterval(this.dashboardRefreshTimer);
        this.dashboardRefreshTimer = null;
      }
      // ── Lazy load per tab (init에서 제거된 호출들) ──
      if (tabId === 'home' && !this.dashboard.loaded) this.loadDashboard();
      if (tabId === 'command') {
        if (!this._commandLoaded) {
          this._commandLoaded = true;
          this.loadConversation();
          this.loadPresets();
        }
        this.$nextTick(() => { this.scrollToBottom(); });
        this.loadRecentTasksForCommand();
      }
      if (tabId === 'activityLog') {
        if (!this._activityLogLoaded) {
          this._activityLogLoaded = true;
          this.restoreActivityLogs();
          this.fetchDelegationLogs(true);
          this._connectCommsSSE();
        }
      }
      if (tabId === 'performance' && !this.performance.loaded) this.loadPerformance();
      if (tabId === 'performance') { this.loadSoulEvolutionProposals(); if (!this.qualityDash.loaded) this.loadQualityDashboard(); }
      if (tabId === 'history') this.loadTaskHistory();
      if (tabId === 'schedule') this.loadSchedules();
      if (tabId === 'workflow') this.loadWorkflows();
      if (tabId === 'knowledge') this.loadKnowledge();
      if (tabId === 'archive') this.loadArchive();
      if (tabId === 'archmap' && !this.archMap.loaded) this.loadArchMap();
      if (tabId === 'sns') this.loadSNS();
      if (tabId === 'agora') { this._connectAgoraSSE(); this._loadAgoraStatus(); }
      if (tabId === 'trading') {
        this.loadTradingSummary();
        this._connectCommsSSE(); // SSE 통합: CIO 로그도 여기서 처리
        clearInterval(this.trading.refreshInterval);
        clearInterval(this.trading.priceRefreshInterval);
        this.trading.refreshInterval = setInterval(() => {
          if (this.activeTab === 'trading') this.loadTradingSummary(true);
        }, 30000);
        this.trading.priceRefreshInterval = setInterval(() => {
          if (this.activeTab === 'trading' && this.trading.watchlist.length > 0) {
            this.loadWatchlistPrices();
          }
        }, 60000);
      } else {
        clearInterval(this.trading.refreshInterval);
        clearInterval(this.trading.priceRefreshInterval);
      }
      // NEXUS는 openNexus()에서 독립적으로 초기화 (풀스크린 오버레이)
    },

    // ── Command Tab: 최근 작업 로드 (새로고침 후에도 표시) ──

    async loadRecentTasksForCommand() {
      try {
        const data = await fetch('/api/tasks?limit=5&status=completed').then(r => r.ok ? r.json() : []);
        this.recentCommandTasks = Array.isArray(data) ? data : (data.tasks || []);
      } catch (e) {
        // 조용히 실패 (사령관실 기본 동작에 영향 없음)
      }
    },

    // ── Dashboard ──

    async loadDashboard() {
      try {
        const [data, budgetRes, qualityRes] = await Promise.all([
          fetch('/api/dashboard').then(r => r.ok ? r.json() : {}),
          fetch('/api/budget').then(r => r.ok ? r.json() : {}),
          fetch('/api/quality').then(r => r.ok ? r.json() : {}),
        ]);
        this.loadModelMode();
        this.dashboard = {
          todayTasks: data.total_tasks_today || 0,
          todayCompleted: data.today_completed || 0,
          todayFailed: data.today_failed || 0,
          runningCount: data.active_agents || 0,
          totalCost: data.total_cost || 0,
          todayCost: data.today_cost || 0,
          totalTokens: data.total_tokens || 0,
          agentCount: data.total_agents || 0,
          notionConnected: data.notion_connected || false,
          recentCompleted: data.recent_completed || [],
          systemHealth: data.system_status || 'ok',
          apiKeys: data.api_keys || {},
          providerCalls: data.provider_calls || {},
          totalAiCalls: data.total_ai_calls || 0,
          dailyLimit: data.daily_limit || 7,
          batchActive: data.batch_active || 0,
          batchDone: data.batch_done || 0,
          toolCount: data.tool_count || 0,
          apiConnected: data.api_connected || 0,
          apiTotal: data.api_total || 5,
          loaded: true,
        };
        this.budget = budgetRes;
        this.quality = qualityRes;
      } catch (e) { console.error('Dashboard load failed:', e); }
      // 배포 상태도 함께 로드
      this.loadDeployStatus();
    },

    async loadDeployStatus() {
      // 1) 서버의 deploy-status.json 읽기
      try {
        const res = await fetch('/deploy-status.json?t=' + Date.now());
        if (res.ok) {
          const d = await res.json();
          this.deployStatus = { build: d.build, time: d.time, status: d.status || 'success', commit: d.commit || '' };
        } else {
          this.deployStatus.status = 'error';
        }
      } catch (e) {
        this.deployStatus.status = 'error';
      }
      // 2) GitHub Actions API에서 최근 배포 기록 가져오기
      try {
        const res = await fetch('https://api.github.com/repos/kodonghui/CORTHEX_HQ/actions/runs?per_page=5&event=workflow_dispatch');
        if (res.ok) {
          const data = await res.json();
          this.deployLogs = (data.workflow_runs || [])
            .filter(r => r.name === 'Deploy to Oracle Cloud Server')
            .slice(0, 5)
            .map(r => ({
              id: r.id,
              number: r.run_number,
              title: r.display_title,
              conclusion: r.conclusion || 'in_progress',
              time: r.created_at,
            }));
        }
      } catch (e) {
        console.error('Deploy logs fetch failed:', e);
      }
    },

    // ── Presets ──

    async loadPresets() {
      try {
        const data = await fetch('/api/presets').then(r => r.json());
        this.presets.items = data || [];
        this.backendPresets = data || [];
      } catch (e) { console.error('Presets load failed:', e); }
    },

    // ── Performance ──

    async loadPerformance() {
      try {
        const data = await fetch('/api/performance').then(r => r.json());
        const agents = data.agents || [];
        const maxCost = Math.max(...agents.map(a => a.cost_usd || 0), 0.0001);
        const totalTasks = agents.reduce((s, a) => s + (a.tasks_completed || 0), 0);
        const rates = agents.filter(a => a.tasks_completed > 0).map(a => a.success_rate || 0);
        const avgRate = rates.length > 0 ? rates.reduce((s, r) => s + r, 0) / rates.length : 0;
        this.performance = {
          agents,
          totalCalls: data.total_llm_calls || 0,
          totalCost: data.total_cost_usd || 0,
          totalTasks,
          avgSuccessRate: avgRate,
          maxCost,
          loaded: true,
        };
      } catch (e) { console.error('Performance load failed:', e); }
    },

    // ── Soul 자동 진화 ──
    async loadSoulEvolutionProposals() {
      try {
        const data = await fetch('/api/soul-evolution/proposals').then(r => r.json());
        this.soulEvolution.proposals = data.proposals || [];
      } catch (e) { console.error('Soul evolution load failed:', e); }
    },

    // ── 품질 대시보드 ──
    async loadQualityDashboard() {
      try {
        const [stats, scores, rejections] = await Promise.all([
          fetch('/api/quality').then(r => r.json()),
          fetch('/api/quality/scores?days=30').then(r => r.json()),
          fetch('/api/quality/top-rejections').then(r => r.json()),
        ]);
        this.qualityDash.totalReviews = stats.total_reviews || 0;
        this.qualityDash.passRate = stats.pass_rate || 0;
        this.qualityDash.avgScore = stats.average_score || 0;
        this.qualityDash.failed = stats.failed || 0;
        this.qualityDash.topRejections = rejections.rejections || [];
        this.qualityDash.loaded = true;

        // Chart.js 차트 렌더링
        if (scores.by_agent && Object.keys(scores.by_agent).length > 0) {
          await _loadScript(_CDN.chartjs);
          this.$nextTick(() => this._renderQualityChart(scores.by_agent));
        }
      } catch (e) { console.error('Quality dashboard load failed:', e); }
    },

    _renderQualityChart(byAgent) {
      const canvas = document.getElementById('qualityScoreChart');
      if (!canvas) return;
      if (this._qualityChart) this._qualityChart.destroy();

      const colors = ['#00d4aa', '#00b4d8', '#fbbf24', '#f87171', '#a78bfa', '#34d399'];
      const datasets = Object.entries(byAgent).map(([aid, points], idx) => ({
        label: aid.replace('_specialist', '').replace('_', ' '),
        data: points.map(p => ({ x: p.date, y: p.score })),
        borderColor: colors[idx % colors.length],
        backgroundColor: colors[idx % colors.length] + '20',
        tension: 0.3,
        pointRadius: 3,
        borderWidth: 2,
        fill: false,
      }));

      this._qualityChart = new Chart(canvas, {
        type: 'line',
        data: { datasets },
        options: {
          responsive: true, maintainAspectRatio: false,
          scales: {
            x: { type: 'time', time: { unit: 'day' }, grid: { color: '#ffffff10' }, ticks: { color: '#888', font: { size: 9 } } },
            y: { min: 0, max: 5, grid: { color: '#ffffff10' }, ticks: { color: '#888', font: { size: 9 } } },
          },
          plugins: {
            legend: { labels: { color: '#ccc', font: { size: 10 } } },
            tooltip: { mode: 'index', intersect: false },
          },
        },
      });
    },

    // ── Architecture Map (아키텍처 맵) ──

    async loadArchMap() {
      try {
        // Chart.js + Mermaid 동적 로드 (archmap 탭 최초 진입 시만)
        await Promise.all([
          _loadScript(_CDN.chartjs),
          _loadScript(_CDN.mermaid),
        ]);
        // Mermaid 초기화 (최초 1회)
        if (typeof mermaid !== 'undefined' && !this._mermaidInited) {
          mermaid.initialize({ startOnLoad: false, theme: 'dark', themeVariables: {
            primaryColor: '#FF6B3520', primaryBorderColor: '#FF6B35', primaryTextColor: '#E5E7EB',
            lineColor: '#4B5563', secondaryColor: '#1F2937', tertiaryColor: '#111827', fontSize: '13px',
          }, flowchart: { curve: 'basis', padding: 15 } });
          this._mermaidInited = true;
        }
        const [hierarchy, costSummary] = await Promise.all([
          fetch('/api/architecture/hierarchy').then(r => r.json()),
          fetch('/api/architecture/cost-summary').then(r => r.json()),
        ]);
        this.archMap.hierarchy = hierarchy;
        this.archMap.costSummary = costSummary;
        this.archMap.loaded = true;
        this.loadArchMapCosts();
        this.$nextTick(() => this.renderMermaidOrgChart());
      } catch (e) { console.error('Architecture map load failed:', e); }
    },

    async loadArchMapCosts() {
      try {
        const [byAgent, byDivision] = await Promise.all([
          fetch('/api/architecture/cost-by-agent?period=' + this.archMap.costPeriod).then(r => r.json()),
          fetch('/api/architecture/cost-by-division?period=' + this.archMap.costPeriod).then(r => r.json()),
        ]);
        this.archMap.costByAgent = byAgent.agents || [];
        this.archMap.costByDivision = byDivision.divisions || [];
        this.$nextTick(() => this.renderCostCharts());
      } catch (e) { console.error('Cost data load failed:', e); }
    },

    async changeCostPeriod(period) {
      this.archMap.costPeriod = period;
      await this.loadArchMapCosts();
    },

    renderMermaidOrgChart() {
      const container = document.getElementById('mermaid-orgchart');
      if (!container || !this.archMap.hierarchy || !window.mermaid) return;

      const { nodes, edges } = this.archMap.hierarchy;
      const divColorMap = {
        'secretary': '#FFD200', 'leet_master.tech': '#00E6FF', 'leet_master.strategy': '#00C8FF',
        'leet_master.legal': '#00B4FF', 'leet_master.marketing': '#00A0FF',
        'finance.investment': '#8C64FF', 'publishing': '#00FF88',
      };

      let code = 'graph TD\n';
      code += '  CEO["CEO\\n고동희 대표님"]\n';
      for (const n of nodes) {
        const model = n.model_name ? '\\n' + n.model_name.replace('claude-', 'c-').replace('gemini-', 'g-').replace('-preview', '') : '';
        const icon = n.role === 'manager' ? '📋' : '🔧';
        code += '  ' + n.id + '["' + icon + ' ' + n.name_ko + model + '"]\n';
      }
      code += '  CEO --> chief_of_staff\n';
      for (const e of edges) code += '  ' + e.from + ' --> ' + e.to + '\n';
      code += '\n';
      for (const n of nodes) {
        const c = divColorMap[n.division] || '#888';
        code += '  style ' + n.id + ' fill:' + c + '20,stroke:' + c + ',color:#E5E7EB\n';
      }
      code += '  style CEO fill:#FF6B3520,stroke:#FF6B35,color:#E5E7EB\n';

      container.innerHTML = '';
      container.removeAttribute('data-processed');
      mermaid.render('orgchart-svg', code).then(({ svg }) => {
        container.innerHTML = svg;
        this.archMap.mermaidRendered = true;
        this.$nextTick(() => this.bindOrgChartClicks());
      }).catch(e => console.error('Mermaid render failed:', e));
    },

    bindOrgChartClicks() {
      const svg = document.querySelector('#mermaid-orgchart svg');
      if (!svg) return;
      svg.querySelectorAll('.node').forEach(el => {
        const rawId = el.id || '';
        const nodeId = rawId.replace('flowchart-', '').replace(/-\d+$/, '');
        if (nodeId && nodeId !== 'CEO') {
          el.style.cursor = 'pointer';
          el.addEventListener('click', () => {
            this.targetAgentId = nodeId;
            this.switchTab('command');
            this.$nextTick(() => { const inp = this.$refs.inputArea; if (inp) inp.focus(); });
          });
        }
      });
    },

    renderCostCharts() {
      this._renderDivisionDonut();
      this._renderAgentBarChart();
    },

    _renderDivisionDonut() {
      const canvas = document.getElementById('division-cost-chart');
      if (!canvas || !this.archMap.costByDivision.length) return;
      const colors = {
        'secretary': 'rgb(255,210,0)', 'tech': 'rgb(0,230,255)', 'strategy': 'rgb(0,200,255)',
        'legal': 'rgb(0,180,255)', 'marketing': 'rgb(0,160,255)',
        'finance': 'rgb(140,100,255)', 'publishing': 'rgb(0,255,136)',
      };
      const data = this.archMap.costByDivision;
      if (this._divDonutChart) this._divDonutChart.destroy();
      this._divDonutChart = new Chart(canvas, {
        type: 'doughnut',
        data: {
          labels: data.map(d => d.label),
          datasets: [{ data: data.map(d => d.cost_usd), backgroundColor: data.map(d => colors[d.division] || 'rgb(128,128,128)'), borderWidth: 0 }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'right', labels: { color: '#9CA3AF', font: { size: 11 } } },
            tooltip: { callbacks: { label: ctx => ctx.label + ': $' + ctx.parsed.toFixed(4) } } },
          cutout: '65%',
        }
      });
    },

    _renderAgentBarChart() {
      const canvas = document.getElementById('agent-cost-chart');
      if (!canvas || !this.archMap.costByAgent.length) return;
      const top10 = this.archMap.costByAgent.slice(0, 10);
      if (this._agentBarChart) this._agentBarChart.destroy();
      this._agentBarChart = new Chart(canvas, {
        type: 'bar',
        data: {
          labels: top10.map(a => this.agentNames[a.agent_id] || a.agent_id),
          datasets: [{ label: '비용 (USD)', data: top10.map(a => a.cost_usd),
            backgroundColor: 'rgba(0,230,255,0.6)', borderColor: 'rgb(0,230,255)', borderWidth: 1 }]
        },
        options: {
          indexAxis: 'y', responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false },
            tooltip: { callbacks: { label: ctx => '$' + ctx.parsed.x.toFixed(4) + ' (' + top10[ctx.dataIndex].call_count + '회)' } } },
          scales: {
            x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9CA3AF', callback: v => '$' + v.toFixed(3) } },
            y: { grid: { display: false }, ticks: { color: '#9CA3AF', font: { size: 11 } } }
          }
        }
      });
    },

    getDeptAgents(deptKey) {
      return Object.entries(this.agentDivision).filter(([, d]) => d === deptKey).map(([id]) => id);
    },

    getDeptWorkingCount(deptKey) {
      return this.getDeptAgents(deptKey).filter(id => this.activeAgents[id]?.status === 'working').length;
    },

    // ── Task History ──

    async loadTaskHistory() {
      try {
        this.taskHistory.loading = true;
        const params = new URLSearchParams();
        if (this.taskHistory.search) params.set('keyword', this.taskHistory.search);
        if (this.taskHistory.filterStatus === 'archived') {
          params.set('archived', 'true');
        } else if (this.taskHistory.filterStatus !== 'all') {
          params.set('status', this.taskHistory.filterStatus);
        }
        if (this.taskHistory.bookmarkOnly) params.set('bookmarked', 'true');
        const resp = await fetch('/api/tasks?' + params.toString());
        if (!resp.ok) throw new Error('API 응답 오류: ' + resp.status);
        const data = await resp.json();
        if (data && data.length > 0) {
          this.taskHistory.items = data;
          this.taskHistory.isSample = false;
        } else {
          this.taskHistory.items = this._getSampleTaskHistory();
          this.taskHistory.isSample = true;
        }
        this.taskHistory.loaded = true;
        this.taskHistory.error = null;
      } catch (e) {
        console.error('Task history load failed:', e);
        this.taskHistory.error = e.message || '데이터를 불러올 수 없습니다';
        this.taskHistory.items = this._getSampleTaskHistory();
        this.taskHistory.isSample = true;
        this.taskHistory.loaded = true;
      } finally {
        this.taskHistory.loading = false;
      }
    },

    _getSampleTaskHistory() {
      const now = Date.now();
      return [
        { task_id: 'sample_1', command: '@CTO 이번 주 기술 현황 리포트 작성해줘', status: 'completed', created_at: new Date(now - 3600000).toISOString(), summary: '기술 현황 리포트 완료 — 서버 가동률 99.7%, 응답 시간 평균 120ms', time_seconds: 12.4, cost: 0.0156, bookmarked: true, correlation_id: null },
        { task_id: 'sample_2', command: '전 부서 일일 업무 현황 보고', status: 'completed', created_at: new Date(now - 7200000).toISOString(), summary: '29개 에이전트의 일일 업무 현황을 종합했습니다', time_seconds: 28.7, cost: 0.0423, bookmarked: false, correlation_id: 'corr_sample_1' },
        { task_id: 'sample_3', command: '@CMO 경쟁사 마케팅 전략 분석', status: 'completed', created_at: new Date(now - 14400000).toISOString(), summary: '주요 경쟁사 3곳의 마케팅 전략을 비교 분석했습니다', time_seconds: 45.2, cost: 0.0687, bookmarked: false, correlation_id: null },
        { task_id: 'sample_4', command: '@CFO 이번 달 예산 집행 현황 정리', status: 'failed', created_at: new Date(now - 21600000).toISOString(), summary: '예산 데이터 소스 접근 실패 — API 키 만료', time_seconds: 3.1, cost: 0.0012, bookmarked: false, correlation_id: null },
        { task_id: 'sample_5', command: '@CLO 개인정보처리방침 최신 법령 반영 검토', status: 'completed', created_at: new Date(now - 43200000).toISOString(), summary: '2026년 2월 기준 개인정보보호법 개정사항 3건을 반영했습니다', time_seconds: 67.8, cost: 0.0934, bookmarked: true, correlation_id: 'corr_sample_2' },
        { task_id: 'sample_6', command: '@CSO 보안 취약점 스캔 실행', status: 'running', created_at: new Date(now - 300000).toISOString(), summary: '시스템 보안 취약점을 스캔하고 있습니다...', time_seconds: null, cost: 0.0045, bookmarked: false, correlation_id: null },
      ];
    },

    async loadTaskDetail(taskId) {
      try {
        const data = await fetch(`/api/tasks/${taskId}`).then(r => r.json());
        const task = this.taskHistory.items.find(t => t.task_id === taskId);
        if (task) {
          task._fullResult = data.result_data || '';
          task.correlation_id = data.correlation_id || '';
        }
      } catch (e) { console.error('Task detail load failed:', e); }
    },

    async toggleBookmark(taskId) {
      try {
        const res = await fetch(`/api/tasks/${taskId}/bookmark`, { method: 'POST' }).then(r => r.json());
        const task = this.taskHistory.items.find(t => t.task_id === taskId);
        if (task) task.bookmarked = res.bookmarked;
      } catch (e) { console.error('Bookmark toggle failed:', e); }
    },

    async deleteTask(taskId) {
      if (!confirm('이 작업 기록을 삭제하시겠습니까?')) return;
      try {
        await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
        this.taskHistory.items = this.taskHistory.items.filter(t => t.task_id !== taskId);
        this.showToast('작업 기록 삭제됨', 'success');
      } catch (e) { this.showToast('삭제 실패', 'error'); }
    },

    toggleTaskSelect(taskId) {
      const idx = this.taskHistory.selectedIds.indexOf(taskId);
      if (idx >= 0) {
        this.taskHistory.selectedIds.splice(idx, 1);
      } else {
        this.taskHistory.selectedIds.push(taskId);
      }
    },

    selectAllTasks() {
      if (this.taskHistory.selectedIds.length === this.taskHistory.items.length) {
        this.taskHistory.selectedIds = [];
      } else {
        this.taskHistory.selectedIds = this.taskHistory.items.map(t => t.task_id);
      }
    },
    isAllSelected() {
      const items = this.taskHistory.items || [];
      return items.length > 0 && items.every(t => this.taskHistory.selectedIds.includes(t.task_id));
    },
    toggleSelectAll() {
      if (this.isAllSelected()) {
        this.taskHistory.selectedIds = [];
      } else {
        this.taskHistory.selectedIds = (this.taskHistory.items || []).map(t => t.task_id);
      }
    },
    getTaskColorBarClass(task) {
      let agentId = task.agent_id;
      if (!agentId && task.command) {
        const m = task.command.match(/@(\S+)/);
        if (m) {
          const k = m[1].toLowerCase();
          const map = {'cto':'cto_manager','cso':'cso_manager','clo':'clo_manager','cmo':'cmo_manager','cio':'cio_manager','cpo':'cpo_manager','비서실장':'chief_of_staff'};
          agentId = map[k] || null;
        }
      }
      const div = agentId ? (this.agentDivision[agentId] || '') : '';
      const colors = {
        'secretary': 'bg-amber-400/60',
        'tech': 'bg-cyan-400/60',
        'leet_master.tech': 'bg-cyan-400/60',
        'strategy': 'bg-purple-400/60',
        'leet_master.strategy': 'bg-purple-400/60',
        'legal': 'bg-rose-400/60',
        'leet_master.legal': 'bg-rose-400/60',
        'marketing': 'bg-emerald-400/60',
        'leet_master.marketing': 'bg-emerald-400/60',
        'finance': 'bg-blue-400/60',
        'finance.investment': 'bg-blue-400/60',
        'publishing': 'bg-purple-400/60',
      };
      return colors[div] || 'bg-hq-accent/40';
    },

    async bulkDelete() {
      const count = this.taskHistory.selectedIds.length;
      if (!confirm(`${count}개 작업을 영구 삭제합니다. 되돌릴 수 없습니다. 계속할까요?`)) return;
      try {
        await fetch('/api/tasks/bulk', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'delete', task_ids: this.taskHistory.selectedIds }),
        });
        this.showToast(`${count}개 작업을 삭제했습니다`, 'success');
        this.taskHistory.selectedIds = [];
        this.loadTaskHistory();
      } catch (e) { this.showToast('삭제 실패: ' + e.message, 'error'); }
    },

    async bulkBookmark() {
      try {
        await fetch('/api/tasks/bulk', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'bookmark', task_ids: this.taskHistory.selectedIds }),
        });
        this.showToast(`${this.taskHistory.selectedIds.length}개 작업에 북마크를 설정했습니다`, 'success');
        this.taskHistory.selectedIds = [];
        this.loadTaskHistory();
      } catch (e) { this.showToast('북마크 실패: ' + e.message, 'error'); }
    },

    async bulkTag() {
      const tag = prompt('추가할 태그를 입력하세요:');
      if (!tag || !tag.trim()) return;
      try {
        await fetch('/api/tasks/bulk', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'tag', task_ids: this.taskHistory.selectedIds, tag: tag.trim() }),
        });
        this.showToast(`${this.taskHistory.selectedIds.length}개 작업에 "${tag.trim()}" 태그를 달았습니다`, 'success');
        this.taskHistory.selectedIds = [];
        this.loadTaskHistory();
      } catch (e) { this.showToast('태그 추가 실패: ' + e.message, 'error'); }
    },

    async bulkArchive() {
      const count = this.taskHistory.selectedIds.length;
      try {
        await fetch('/api/tasks/bulk', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'archive', task_ids: this.taskHistory.selectedIds }),
        });
        this.showToast(`${count}개 작업을 보관했습니다. 필터에서 "보관"을 선택하면 다시 볼 수 있습니다.`, 'success');
        this.taskHistory.selectedIds = [];
        this.loadTaskHistory();
      } catch (e) { this.showToast('보관 실패: ' + e.message, 'error'); }
    },

    async openComparison() {
      if (this.taskHistory.selectedIds.length !== 2) return;
      try {
        const [a, b] = await Promise.all(
          this.taskHistory.selectedIds.map(id => fetch(`/api/tasks/${id}`).then(r => r.json()))
        );
        this.taskHistory.compareA = a;
        this.taskHistory.compareB = b;
        this.taskHistory.compareMode = true;
      } catch (e) { console.error('Comparison load failed:', e); }
    },

    async loadReplay(correlationId, taskId) {
      if (this.taskHistory.replayData[taskId]) {
        this.taskHistory.replayData[taskId] = null;
        return;
      }
      try {
        const data = await fetch(`/api/replay/${correlationId}`).then(r => r.json());
        this.taskHistory.replayData[taskId] = data;
      } catch (e) { console.error('Replay load failed:', e); }
    },

    renderReplayTree(data) {
      if (!data || !data.root) return '<div class="text-xs text-hq-muted">데이터 없음</div>';
      const renderNode = (node, depth = 0) => {
        const indent = depth * 16;
        const icon = node.type === 'task_request' ? '→' : '←';
        const color = node.success === false ? 'text-hq-red' : node.type === 'task_result' ? 'text-hq-green' : 'text-hq-cyan';
        let html = `<div style="margin-left:${indent}px" class="py-1 text-[11px]">`;
        html += `<span class="${color} font-semibold">${icon} ${node.sender_id || ''}</span>`;
        html += `<span class="text-hq-muted ml-1">${(node.detail || node.summary || '').substring(0, 100)}</span>`;
        if (node.time) html += `<span class="text-hq-muted/80 ml-1 font-mono">${node.time}s</span>`;
        html += '</div>';
        if (node.children) {
          for (const child of node.children) {
            html += renderNode(child, depth + 1);
          }
        }
        return html;
      };
      return renderNode(data.root);
    },

    // ── Memory (에이전트 기억) ──

    async openMemoryModal(agentId, agentName) {
      this.memoryModal.agentId = agentId;
      this.memoryModal.agentName = agentName;
      this.memoryModal.newKey = '';
      this.memoryModal.newValue = '';
      this.memoryModal.visible = true;
      await this.loadMemory(agentId);
    },

    async loadMemory(agentId) {
      try {
        const data = await fetch(`/api/memory/${agentId}`).then(r => r.json());
        this.memoryModal.items = Array.isArray(data) ? data : [];
      } catch (e) { this.memoryModal.items = []; }
    },

    async addMemory() {
      const key = this.memoryModal.newKey.trim();
      const value = this.memoryModal.newValue.trim();
      if (!key || !value) return;
      try {
        await fetch(`/api/memory/${this.memoryModal.agentId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key, value }),
        });
        this.memoryModal.newKey = '';
        this.memoryModal.newValue = '';
        await this.loadMemory(this.memoryModal.agentId);
      } catch (e) { console.error('Add memory failed:', e); }
    },

    async deleteMemory(memoryId) {
      try {
        await fetch(`/api/memory/${this.memoryModal.agentId}/${memoryId}`, { method: 'DELETE' });
        await this.loadMemory(this.memoryModal.agentId);
      } catch (e) { console.error('Delete memory failed:', e); }
    },

    // ── Schedules ──

    _cronToKorean(cron) {
      if (!cron || cron.trim().split(' ').length !== 5) return '';
      const [min, hour, dom, mon, dow] = cron.trim().split(' ');
      const h = hour === '*' ? '' : hour.padStart(2,'0');
      const m = min === '*' ? '00' : min.padStart(2,'0');
      const time = h ? `${h}:${m}` : '';
      const dowMap = {'1':'월','2':'화','3':'수','4':'목','5':'금','6':'토','0':'일'};
      if (dow === '1-5' && dom === '*' && mon === '*') return `평일 ${time}`;
      if (dow === '0-6' || (dow === '*' && dom === '*' && mon === '*')) return `매일 ${time}`;
      if (dow.includes(',')) { const days = dow.split(',').map(d => dowMap[d] || d).join('·'); return `${days} ${time}`; }
      if (dowMap[dow]) return `매주 ${dowMap[dow]}요일 ${time}`;
      if (dom !== '*' && mon === '*') return `매월 ${dom}일 ${time}`;
      return `${time} (${cron})`;
    },

    async loadSchedules() {
      try {
        const data = await fetch('/api/schedules').then(r => r.json());
        this.schedules.items = (Array.isArray(data) ? data : data.schedules || []).map(s => ({
          ...s, id: s.id || s.schedule_id, cron_label: this._cronToKorean(s.cron) || s.cron_preset || s.cron || '',
        }));
      } catch (e) { this.schedules.items = []; }
    },

    async addSchedule() {
      const name = this.schedules.editName.trim();
      const command = this.schedules.editCommand.trim();
      const cron_preset = this.schedules.editCronPreset;
      if (!name || !command) return;
      try {
        await fetch('/api/schedules', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, command, cron_preset }),
        });
        this.schedules.editName = '';
        this.schedules.editCommand = '';
        this.schedules.showModal = false;
        await this.loadSchedules();
      } catch (e) { console.error('Add schedule failed:', e); }
    },

    async toggleSchedule(id) {
      try {
        await fetch(`/api/schedules/${id}/toggle`, { method: 'POST' });
        await this.loadSchedules();
      } catch (e) { console.error('Toggle schedule failed:', e); }
    },

    async deleteSchedule(id) {
      try {
        await fetch(`/api/schedules/${id}`, { method: 'DELETE' });
        await this.loadSchedules();
      } catch (e) { console.error('Delete schedule failed:', e); }
    },

    // ── Workflows ──

    async loadWorkflows() {
      try {
        const data = await fetch('/api/workflows').then(r => r.json());
        this.workflows.items = (Array.isArray(data) ? data : data.workflows || []).map(w => ({
          ...w, id: w.id || w.workflow_id,
        }));
      } catch (e) { this.workflows.items = []; }
    },

    editWorkflow(wf) {
      this.workflows.editing = wf.id || wf.workflow_id;
      this.workflows.editName = wf.name;
      this.workflows.editDesc = wf.description || '';
      this.workflows.editSteps = wf.steps.map(s => ({ ...s }));
      this.workflows.showEditor = true;
    },

    async saveWorkflow() {
      const name = this.workflows.editName.trim();
      if (!name || this.workflows.editSteps.length === 0) return;
      const body = {
        name,
        description: this.workflows.editDesc,
        steps: this.workflows.editSteps.filter(s => s.command.trim()),
      };
      try {
        if (this.workflows.editing) {
          await fetch(`/api/workflows/${this.workflows.editing}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });
        } else {
          await fetch('/api/workflows', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });
        }
        this.workflows.showEditor = false;
        await this.loadWorkflows();
      } catch (e) { console.error('Save workflow failed:', e); }
    },

    async deleteWorkflow(id) {
      try {
        await fetch(`/api/workflows/${id}`, { method: 'DELETE' });
        await this.loadWorkflows();
      } catch (e) { console.error('Delete workflow failed:', e); }
    },

    // ── 워크플로우 바로 실행 (모달 없이) ──
    async runWorkflowDirect(wf) {
      if (this.workflows.runningId) return;
      const mode = wf._mode || 'realtime';
      this.workflows.runningId = wf.id;
      wf._progress = 0;
      wf._currentStep = 0;
      wf._progressText = '실행 시작...';
      wf._lastResult = null;
      wf._showResult = false;
      wf._resultTime = '';

      // 타임아웃 안전망
      if (this._wfTimeout) clearTimeout(this._wfTimeout);
      if (this._wfFinalTimeout) clearTimeout(this._wfFinalTimeout);
      this._wfTimeout = setTimeout(() => {
        if (this.workflows.runningId === wf.id) {
          wf._progressText = 'AI 응답 대기 중... (시간이 걸릴 수 있습니다)';
        }
      }, 30000);
      this._wfFinalTimeout = setTimeout(() => {
        if (this.workflows.runningId === wf.id) {
          wf._progressText = '시간 초과 — 작전일지에서 결과를 확인해주세요';
          this.workflows.runningId = null;
        }
      }, 180000);

      try {
        const resp = await fetch(`/api/workflows/${wf.id}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode }),
        });
        const data = await resp.json();
        if (!data.success) {
          wf._progressText = data.error || '실행 실패';
          this.workflows.runningId = null;
          clearTimeout(this._wfTimeout);
          clearTimeout(this._wfFinalTimeout);
          this.showToast('워크플로우 실행 실패', 'error');
        }
        // 성공 시: WebSocket workflow_progress 메시지를 기다림
      } catch (e) {
        wf._progressText = e.message;
        this.workflows.runningId = null;
        clearTimeout(this._wfTimeout);
        clearTimeout(this._wfFinalTimeout);
        this.showToast('워크플로우 실행 중 오류', 'error');
      }
    },

    // 기존 호환용 (모달이 열려있을 때)
    async runWorkflow(id) { const wf = this.workflows.items.find(w => w.id === id); if (wf) this.runWorkflowDirect(wf); },
    async executeWorkflow() { /* 미사용 — runWorkflowDirect로 대체 */ },

    handleWorkflowProgress(data) {
      // 카드 직접 업데이트 로직
      const wfId = data.workflow_id;
      const wf = wfId ? this.workflows.items.find(w => w.id === wfId) : null;

      if (data.workflow_done) {
        if (wf) {
          wf._progress = 100;
          wf._currentStep = data.total_steps || wf.steps?.length || 0;
          wf._progressText = '완료!';
          wf._lastResult = data.final_result || data.result || '완료되었습니다.';
          wf._resultTime = new Date().toLocaleTimeString('ko-KR', {hour:'2-digit', minute:'2-digit'});
          wf._showResult = true;
          this.showToast(`${wf.name || '워크플로우'} 완료`, 'success');
        }
        this.workflows.runningId = null;
        if (this._wfTimeout) clearTimeout(this._wfTimeout);
        if (this._wfFinalTimeout) clearTimeout(this._wfFinalTimeout);
      } else if (wf) {
        const totalSteps = data.total_steps || wf.steps?.length || 1;
        const stepIdx = (data.step_index ?? 0) + 1;
        wf._currentStep = stepIdx;
        wf._progress = Math.round((stepIdx / totalSteps) * 100);
        wf._progressText = data.step_name || `${stepIdx}/${totalSteps} 단계 진행 중...`;
      }
    },

    handlePipelineProgress(data) {
      const stepLabels = {
        'analyze': '분석 중', 'write': '작성 중', 'edit': '편집 중',
        'review': '승인 대기', 'publishing': '발행 중', 'published': '발행 완료',
      };
      const label = stepLabels[data.step] || data.step_label || data.step;
      if (data.status === 'waiting') {
        this.showToast(`📰 콘텐츠 준비 완료! 승인해주세요.`, 'info');
      } else if (data.status === 'completed' && data.step === 'published') {
        this.showToast(`📰 콘텐츠 발행 완료!`, 'success');
      } else if (data.status === 'failed') {
        this.showToast(`📰 파이프라인 오류: ${label}`, 'error');
      } else if (data.status === 'running') {
        this.showToast(`📰 ${label}...`, 'info');
      }
    },

    closeWorkflowExec() {
      this.workflowExec.show = false;
    },

    // ── Auth (인증) ──

    async checkAuth() {
      try {
        const token = localStorage.getItem('corthex_token');
        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
        const data = await fetch('/api/auth/status', { headers }).then(r => r.json());
        this.auth.bootstrapMode = data.bootstrap_mode;
        if (data.authenticated) {
          this.auth.role = data.role || 'ceo';
          this.auth.showLogin = false;
          if (token) {
            this.auth.token = token;
            const userJson = localStorage.getItem('corthex_user');
            if (userJson) this.auth.user = JSON.parse(userJson);
          }
          return;
        }
        // 인증 실패
        localStorage.removeItem('corthex_token');
        localStorage.removeItem('corthex_user');
        this.auth.showLogin = true;
      } catch (e) {
        this.auth.bootstrapMode = true;
        this.auth.role = 'ceo';
      }
    },

    async doLogin() {
      this.auth.loginError = '';
      const password = this.auth.loginPass.trim();
      if (!password) { this.auth.loginError = '비밀번호를 입력하세요'; return; }
      try {
        const data = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password }),
        }).then(r => r.json());
        if (data.success) {
          localStorage.setItem('corthex_token', data.token);
          localStorage.setItem('corthex_user', JSON.stringify(data.user || {role:'ceo'}));
          this.auth.token = data.token;
          this.auth.user = data.user || {role:'ceo'};
          this.auth.role = 'ceo';
          this.auth.showLogin = false;
          this.auth.loginPass = '';
          this.showToast('로그인 성공', 'success');
        } else {
          this.auth.loginError = data.error || '로그인 실패';
        }
      } catch (e) { this.auth.loginError = '서버 연결 오류'; }
    },

    async doLogout() {
      try {
        const token = localStorage.getItem('corthex_token');
        if (token) {
          await fetch('/api/auth/logout', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
          });
        }
      } catch (e) { /* 무시 */ }
      localStorage.removeItem('corthex_token');
      localStorage.removeItem('corthex_user');
      this.auth.token = null;
      this.auth.user = null;
      this.auth.role = 'viewer';
      if (!this.auth.bootstrapMode) {
        this.auth.showLogin = true;
      }
      this.showToast('로그아웃 되었습니다', 'info');
    },

    // ── Dynamic Loading ──
    async loadAgentsAndTools() {
      try {
        const [agents, tools] = await Promise.all([
          fetch('/api/agents').then(r => r.ok ? r.json() : []),
          fetch('/api/tools').then(r => r.ok ? r.json() : []),
        ]);
        // 대시보드 통계 카드용 배열 저장
        this.agentsList = Array.isArray(agents) ? agents : [];
        this.toolsList = Array.isArray(tools) ? tools : [];
        if (Array.isArray(agents) && agents.length > 0) {
          agents.forEach(a => {
            this.agentNames[a.agent_id] = a.name_ko || a.agent_id;
            const nameKo = a.name_ko || a.agent_id;
            this.agentInitials[a.agent_id] = nameKo.length >= 2 ? nameKo.substring(0, 2) : nameKo.toUpperCase();
            this.agentRoles[a.agent_id] = a.role || '';
            // 모델 원본 이름과 추론 레벨 저장 (내부 데이터용)
            this.agentModelRaw[a.agent_id] = a.model_name || '';
            this.agentReasonings[a.agent_id] = a.reasoning_effort || '';
            // 에이전트 카드에 표시명 저장 (추론레벨은 템플릿에서 별도 표시)
            this.agentModels[a.agent_id] = a.model_name || '';
            if (a.division) {
              const divMap = { '비서실': 'secretary', '기술개발처': 'tech', '사업기획처': 'strategy',
                               '법무처': 'legal', '마케팅처': 'marketing', '투자분석처': 'finance',
                               '출판기록처': 'publishing', '출판처': 'publishing',
                               'leet_master.tech': 'tech', 'leet_master.strategy': 'strategy',
                               'leet_master.legal': 'legal', 'leet_master.marketing': 'marketing',
                               'finance.investment': 'finance',
                               'secretary': 'secretary', 'publishing': 'publishing' };
              this.agentDivision[a.agent_id] = divMap[a.division] || a.division;
            }
          });
        }
      } catch (e) {
        console.warn('에이전트/도구 동적 로딩 실패, 하드코딩 사용:', e);
      }
    },

    async loadConversation() {
      try {
        // 대화 목록도 함께 로드
        this.loadConversationList();

        if (this.currentConversationId) {
          // 특정 세션 로드
          const res = await fetch(`/api/conversation/sessions/${this.currentConversationId}/messages`);
          if (res.ok) {
            const messages = await res.json();
            this.messages = Array.isArray(messages) ? messages : [];
          }
        } else {
          // 레거시: 전체 대화 로드
          const res = await fetch('/api/conversation');
          if (!res.ok) return;
          const messages = await res.json();
          if (Array.isArray(messages) && messages.length > 0) {
            this.messages = messages;
          }
        }
        // 복원 후 스크롤
        this.$nextTick(() => this.scrollToBottom());
        setTimeout(() => this.scrollToBottom(), 200);
        setTimeout(() => this.scrollToBottom(), 500);
        setTimeout(() => this.scrollToBottom(), 1000);
      } catch (e) {
        console.warn('대화 기록 복원 실패:', e);
      }
    },

    async sendFeedback(msg, rating) {
      // 토글 로직: 같은 버튼 다시 누르면 취소, 다른 버튼 누르면 변경
      let action = 'send';
      let previous_rating = null;

      if (msg.feedbackSent && msg.feedbackRating === rating) {
        // 같은 버튼 다시 클릭 → 피드백 취소
        action = 'cancel';
      } else if (msg.feedbackSent && msg.feedbackRating !== rating) {
        // 다른 버튼 클릭 → 피드백 변경
        action = 'change';
        previous_rating = msg.feedbackRating;
      }

      try {
        const res = await fetch('/api/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            correlation_id: msg.task_id || '',
            rating,
            action,
            previous_rating,
            agent_id: msg.sender_id || '',
          }),
        });
        const data = await res.json();
        if (data.success) {
          if (action === 'cancel') {
            // 취소: 피드백 상태 초기화
            msg.feedbackSent = false;
            msg.feedbackRating = null;
            this.showToast('피드백을 취소했습니다.', 'success');
          } else {
            // 보내기 또는 변경
            msg.feedbackSent = true;
            msg.feedbackRating = rating;
            if (action === 'change') {
              this.showToast(rating === 'good' ? '긍정 피드백으로 변경했습니다.' : '부정 피드백으로 변경했습니다.', 'success');
            } else {
              this.showToast(rating === 'good' ? '긍정 피드백을 보냈습니다.' : '부정 피드백을 보냈습니다.', 'success');
            }
          }
        } else {
          this.showToast(data.error || '피드백 전송 실패', 'error');
        }
      } catch {
        this.showToast('피드백 전송에 실패했습니다.', 'error');
      }
    },

    async loadHealth() {
      try {
        const res = await fetch('/api/health');
        if (res.ok) this.healthData = await res.json();
      } catch { /* 무시 */ }
    },

    // ── Preset Management (웰컴화면용) ──
    async addPreset() {
      const name = this.newPresetName.trim();
      const command = this.newPresetCommand.trim();
      if (!name || !command) { this.showToast('이름과 명령어를 모두 입력하세요.', 'warning'); return; }
      try {
        const res = await fetch('/api/presets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, command }),
        });
        const data = await res.json();
        if (data.success) {
          this.showAddPreset = false;
          this.newPresetName = '';
          this.newPresetCommand = '';
          this.showToast('프리셋이 추가되었습니다.', 'success');
          await this.loadPresets();
        } else {
          this.showToast(data.error || '프리셋 추가 실패', 'error');
        }
      } catch { this.showToast('프리셋 추가에 실패했습니다.', 'error'); }
    },

    async deletePreset(name) {
      try {
        const res = await fetch(`/api/presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
          this.showToast(`프리셋 '${name}'이 삭제되었습니다.`, 'success');
          await this.loadPresets();
        } else {
          this.showToast(data.error || '프리셋 삭제 실패', 'error');
        }
      } catch { this.showToast('프리셋 삭제에 실패했습니다.', 'error'); }
    },

    // ── Knowledge Management ──
    async loadKnowledge() {
      this.knowledge.loading = true;
      try {
        const res = await fetch('/api/knowledge');
        if (res.ok) {
          const data = await res.json();
          this.knowledge.files = data.entries || data || [];
        }
      } catch { this.showToast('지식 파일 목록을 불러올 수 없습니다.', 'error'); }
      finally { this.knowledge.loading = false; }
    },

    async selectKnowledgeFile(file) {
      this.knowledge.selectedFile = file;
      this.knowledge.editMode = false;
      try {
        const res = await fetch(`/api/knowledge/${encodeURIComponent(file.folder)}/${encodeURIComponent(file.filename)}`);
        if (res.ok) {
          const data = await res.json();
          this.knowledge.content = data.content || '';
        }
      } catch { this.showToast('파일 내용을 불러올 수 없습니다.', 'error'); }
    },

    async saveKnowledge() {
      if (!this.knowledge.selectedFile) return;
      this.knowledge.saving = true;
      try {
        const res = await fetch('/api/knowledge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folder: this.knowledge.selectedFile.folder, filename: this.knowledge.selectedFile.filename, content: this.knowledge.content }),
        });
        const data = await res.json();
        if (data.success) {
          this.showToast('파일이 저장되었습니다.', 'success');
          this.knowledge.editMode = false;
        } else { this.showToast(data.error || '저장 실패', 'error'); }
      } catch { this.showToast('파일 저장에 실패했습니다.', 'error'); }
      finally { this.knowledge.saving = false; }
    },

    async deleteKnowledge() {
      if (!this.knowledge.selectedFile) return;
      const f = this.knowledge.selectedFile;
      try {
        const res = await fetch(`/api/knowledge/${encodeURIComponent(f.folder)}/${encodeURIComponent(f.filename)}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
          this.knowledge.files = this.knowledge.files.filter(x => x.folder !== f.folder || x.filename !== f.filename);
          this.knowledge.selectedFile = null;
          this.knowledge.content = '';
          this.showToast('파일이 삭제되었습니다.', 'success');
        } else { this.showToast(data.error || '삭제 실패', 'error'); }
      } catch { this.showToast('파일 삭제에 실패했습니다.', 'error'); }
    },

    async createKnowledgeFile() {
      const folder = this.knowledge.newFolder.trim() || 'general';
      const filename = this.knowledge.newFileName.trim();
      if (!filename) { this.showToast('파일명을 입력하세요.', 'warning'); return; }
      try {
        const res = await fetch('/api/knowledge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folder, filename, content: '' }),
        });
        const data = await res.json();
        if (data.success) {
          await this.loadKnowledge();
          this.knowledge.showCreateForm = false;
          this.knowledge.newFolder = '';
          this.knowledge.newFileName = '';
          this.showToast('파일이 생성되었습니다.', 'success');
        } else { this.showToast(data.error || '생성 실패', 'error'); }
      } catch { this.showToast('파일 생성에 실패했습니다.', 'error'); }
    },

    // ── Archive Browser ──
    async loadArchive() {
      this.archive.content = '';
      this.archive.selectedReport = null;
      this.archive.loading = true;
      try {
        const res = await fetch('/api/archive');
        if (res.ok) this.archive.files = await res.json();
      } catch { this.showToast('아카이브를 불러올 수 없습니다.', 'error'); }
      finally { this.archive.loading = false; }
    },

    async readArchiveReport(file) {
      this.archive.selectedReport = file;
      try {
        const res = await fetch(`/api/archive/${encodeURIComponent(file.division)}/${encodeURIComponent(file.filename)}`);
        if (res.ok) {
          const data = await res.json();
          this.archive.content = data.content || '';
        }
      } catch { this.showToast('보고서를 불러올 수 없습니다.', 'error'); }
    },

    async searchArchiveByCorrelation() {
      const id = this.archive.searchCorrelation.trim();
      if (!id) return;
      try {
        const res = await fetch(`/api/archive/by-correlation/${encodeURIComponent(id)}`);
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            this.archive.content = data.map(d => `### ${d.division}/${d.filename}\n\n${d.content}`).join('\n\n---\n\n');
            this.archive.selectedReport = { filename: `검색: ${id}` };
          } else {
            this.showToast('해당 작업 ID의 보고서를 찾을 수 없습니다.', 'warning');
          }
        }
      } catch { this.showToast('검색에 실패했습니다.', 'error'); }
    },

    downloadArchiveReport(file) {
      if (!file || !file.content) {
        // 내용이 캐시에 없으면 API에서 가져와서 다운로드
        fetch(`/api/archive/${encodeURIComponent(file.division)}/${encodeURIComponent(file.filename)}`)
          .then(r => r.json())
          .then(doc => {
            if (doc.content) this._triggerDownload(doc.content, file.filename);
            else this.showToast('내용을 불러올 수 없습니다', 'error');
          })
          .catch(() => this.showToast('다운로드 실패', 'error'));
      } else {
        this._triggerDownload(file.content, file.filename);
      }
    },

    _triggerDownload(content, filename) {
      const blob = new Blob([content], { type: 'text/markdown; charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename.endsWith('.md') ? filename : filename + '.md';
      a.click();
      URL.revokeObjectURL(url);
    },

    downloadArchiveZip() {
      const div = this.archive.filterDivision !== 'all' ? this.archive.filterDivision : null;
      const tier = this.archive.filterTier !== 'all' ? this.archive.filterTier : null;
      const params = new URLSearchParams();
      if (div) params.set('division', div);
      if (tier) params.set('tier', tier);
      const url = `/api/archive/export-zip${params.toString() ? '?' + params.toString() : ''}`;
      const a = document.createElement('a');
      a.href = url;
      a.click();
      this.showToast('ZIP 내보내기 시작...', 'success');
    },

    async deleteArchiveReport(file) {
      if (!file || !file.division || !file.filename) return;
      if (!confirm(`이 보고서를 삭제하시겠습니까?\n${file.filename}`)) return;
      try {
        const res = await fetch(`/api/archive/${encodeURIComponent(file.division)}/${encodeURIComponent(file.filename)}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
          this.archive.files = this.archive.files.filter(f => !(f.division === file.division && f.filename === file.filename));
          if (this.archive.selectedReport?.filename === file.filename) {
            this.archive.selectedReport = null;
            this.archive.content = '';
          }
          this.showToast('보고서가 삭제되었습니다', 'success');
        } else {
          this.showToast(data.error || '삭제 실패', 'error');
        }
      } catch { this.showToast('삭제 중 오류가 발생했습니다.', 'error'); }
    },

    async downloadSelectedAsZip() {
      if (!this.archive.selectedFiles.length) return;
      const filenames = this.archive.selectedFiles.map(f => `${f.division}/${f.filename}`).join(',');
      const url = `/api/archive/export-zip?files=${encodeURIComponent(filenames)}`;
      const a = document.createElement('a');
      a.href = url;
      a.download = `corthex-selected-${Date.now()}.zip`;
      a.click();
      this.archive.selectedFiles = [];
    },
    async deleteSelectedFiles() {
      if (!this.archive.selectedFiles.length) return;
      if (!confirm(`${this.archive.selectedFiles.length}개 파일을 삭제하시겠습니까?`)) return;
      for (const file of this.archive.selectedFiles) {
        await fetch(`/api/archive/${encodeURIComponent(file.division)}/${encodeURIComponent(file.filename)}`, { method: 'DELETE' });
      }
      this.archive.selectedFiles = [];
      await this.loadArchive();
      this.showToast(`삭제 완료`, 'success');
    },

    async deleteAllArchives() {
      try {
        const res = await fetch('/api/archive/all', { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
          this.archive.files = [];
          this.archive.selectedReport = null;
          this.archive.content = '';
          this.showDeleteAllArchiveModal = false;
          this.showToast('모든 기밀문서가 삭제되었습니다', 'success');
        } else {
          this.showToast(data.error || '전체 삭제 실패', 'error');
        }
      } catch { this.showToast('전체 삭제 중 오류가 발생했습니다.', 'error'); }
    },

    // ── SNS Management ──
    async loadSNS() {
      this.sns.loading = true;
      try {
        const [status, oauth] = await Promise.all([
          fetch('/api/sns/status').then(r => r.ok ? r.json() : {}),
          fetch('/api/sns/oauth/status').then(r => r.ok ? r.json() : {}),
        ]);
        this.sns.status = status;
        this.sns.oauthStatus = oauth;
      } catch { /* 무시 */ }
      finally { this.sns.loading = false; }
    },

    async connectPlatform(platform) {
      const platformNames = {instagram:'Instagram',youtube:'YouTube',tistory:'Tistory',naver_blog:'네이버 블로그',naver_cafe:'네이버 카페',daum_cafe:'다음 카페'};
      const name = platformNames[platform] || platform;
      try {
        const res = await fetch(`/api/sns/auth/${platform}`);
        if (res.ok) {
          const data = await res.json();
          if (data.auth_url) {
            window.open(data.auth_url, '_blank', 'width=600,height=700');
            this.showToast(`${name} 인증 창이 열렸습니다. 인증 완료 후 이 페이지를 새로고침하세요.`, 'info');
          } else {
            this.showToast(`${name} API 키가 설정되지 않았습니다. .env 파일에 해당 플랫폼의 API 키를 추가해주세요.`, 'warning');
          }
        } else {
          this.showToast(`${name} 연결 실패: API 키가 설정되지 않았거나 서버에서 응답이 없습니다. .env 파일을 확인해주세요.`, 'warning');
        }
      } catch { this.showToast(`${name} 연결에 실패했습니다. 서버가 실행 중인지 확인해주세요.`, 'error'); }
    },

    async postInstagramPhoto() {
      if (!this.sns.igImageUrl.trim()) { this.showToast('이미지 URL을 입력하세요.', 'warning'); return; }
      try {
        const res = await fetch('/api/sns/instagram/photo', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_url: this.sns.igImageUrl, caption: this.sns.igCaption }),
        });
        const data = await res.json();
        data.success ? this.showToast('Instagram 사진이 게시되었습니다.', 'success') : this.showToast(data.error || '게시 실패', 'error');
      } catch { this.showToast('게시에 실패했습니다.', 'error'); }
    },

    async postInstagramReel() {
      if (!this.sns.igVideoUrl.trim()) { this.showToast('비디오 URL을 입력하세요.', 'warning'); return; }
      try {
        const res = await fetch('/api/sns/instagram/reel', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ video_url: this.sns.igVideoUrl, caption: this.sns.igReelCaption }),
        });
        const data = await res.json();
        data.success ? this.showToast('Instagram 릴스가 게시되었습니다.', 'success') : this.showToast(data.error || '게시 실패', 'error');
      } catch { this.showToast('게시에 실패했습니다.', 'error'); }
    },

    async postYouTubeVideo() {
      if (!this.sns.ytFilePath.trim() || !this.sns.ytTitle.trim()) { this.showToast('파일 경로와 제목을 입력하세요.', 'warning'); return; }
      try {
        const res = await fetch('/api/sns/youtube/upload', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_path: this.sns.ytFilePath, title: this.sns.ytTitle, description: this.sns.ytDesc,
            tags: this.sns.ytTags.split(',').map(t => t.trim()).filter(Boolean), privacy: this.sns.ytPrivacy,
          }),
        });
        const data = await res.json();
        data.success ? this.showToast('YouTube 업로드가 완료되었습니다.', 'success') : this.showToast(data.error || '업로드 실패', 'error');
      } catch { this.showToast('업로드에 실패했습니다.', 'error'); }
    },

    async loadSNSQueue() {
      this.sns.loading = true;
      try {
        const res = await fetch('/api/sns/queue');
        if (res.ok) {
          const data = await res.json();
          this.sns.queue = data.items || [];
        }
      } catch { /* 무시 */ }
      finally { this.sns.loading = false; }
    },

    async loadMediaGallery() {
      this.sns.loading = true;
      try {
        const res = await fetch('/api/media/list');
        if (res.ok) {
          const data = await res.json();
          this.sns.mediaImages = data.images || [];
          this.sns.mediaVideos = data.videos || [];
        }
      } catch { /* 무시 */ }
      finally { this.sns.loading = false; }
    },

    toggleMediaItem(type, item) {
      const idx = this.sns.selectedMedia.findIndex(m => m.filename === item.filename);
      if (idx >= 0) { this.sns.selectedMedia.splice(idx, 1); }
      else { this.sns.selectedMedia.push({ type, filename: item.filename }); }
    },
    toggleSelectAllMedia(type) {
      const items = type === 'images' ? this.sns.mediaImages : this.sns.mediaVideos;
      const allSelected = items.every(i => this.sns.selectedMedia.find(m => m.filename === i.filename));
      if (allSelected) {
        this.sns.selectedMedia = this.sns.selectedMedia.filter(m => m.type !== type);
      } else {
        for (const i of items) {
          if (!this.sns.selectedMedia.find(m => m.filename === i.filename)) {
            this.sns.selectedMedia.push({ type, filename: i.filename });
          }
        }
      }
    },
    async deleteSelectedMedia() {
      if (!this.sns.selectedMedia.length) return;
      if (!confirm(`${this.sns.selectedMedia.length}개 파일을 삭제하시겠습니까?`)) return;
      try {
        const res = await fetch('/api/media/delete-batch', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ files: this.sns.selectedMedia })
        });
        const data = await res.json();
        if (data.success) {
          this.showToast(`${data.deleted}개 삭제 완료`, 'success');
          this.sns.selectedMedia = [];
          this.sns.mediaSelectMode = false;
          await this.loadMediaGallery();
        } else { this.showToast('삭제 실패', 'error'); }
      } catch { this.showToast('삭제 중 오류', 'error'); }
    },
    async deleteAllMedia(type) {
      try {
        const res = await fetch(`/api/media/${type}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
          this.showToast(`${data.deleted}개 ${type === 'images' ? '이미지' : '영상'} 삭제`, 'success');
          this.sns.showDeleteAllMediaModal = false;
          await this.loadMediaGallery();
        }
      } catch { this.showToast('전체 삭제 실패', 'error'); }
    },
    async deleteAllMediaBoth() {
      try {
        await fetch('/api/media/images', { method: 'DELETE' });
        await fetch('/api/media/videos', { method: 'DELETE' });
        this.showToast('모든 미디어 삭제 완료', 'success');
        this.sns.showDeleteAllMediaModal = false;
        this.sns.selectedMedia = [];
        this.sns.mediaSelectMode = false;
        await this.loadMediaGallery();
      } catch { this.showToast('전체 삭제 실패', 'error'); }
    },
    async clearSNSQueue() {
      try {
        const res = await fetch('/api/sns/queue', { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
          this.showToast(`${data.removed}개 항목 초기화`, 'success');
          this.sns.showClearQueueModal = false;
          this.sns.queue = [];
        }
      } catch { this.showToast('큐 초기화 실패', 'error'); }
    },

    async approveSNS(id) {
      try {
        const res = await fetch(`/api/sns/approve/${id}`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          this.showToast('승인되었습니다.', 'success');
          this.loadSNSQueue();
        } else { this.showToast(data.error || '승인 실패', 'error'); }
      } catch { this.showToast('승인에 실패했습니다.', 'error'); }
    },

    async rejectSNS(id) {
      try {
        const res = await fetch(`/api/sns/reject/${id}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: this.sns.rejectReason }),
        });
        const data = await res.json();
        if (data.success) {
          this.showToast('거절되었습니다.', 'success');
          this.sns.rejectingId = null;
          this.sns.rejectReason = '';
          this.loadSNSQueue();
        } else { this.showToast(data.error || '거절 실패', 'error'); }
      } catch { this.showToast('거절에 실패했습니다.', 'error'); }
    },

    async publishSNS(id) {
      try {
        this.showToast('발행 중...', 'info');
        const res = await fetch(`/api/sns/publish/${id}`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          this.showToast(`발행 완료! ${data.result?.post_url || ''}`, 'success');
          this.loadSNSQueue();
        } else { this.showToast(data.error || '발행 실패', 'error'); }
      } catch { this.showToast('발행에 실패했습니다.', 'error'); }
    },

    async loadSNSEvents() {
      this.sns.loading = true;
      try {
        const res = await fetch('/api/sns/events?limit=50');
        if (res.ok) {
          const data = await res.json();
          this.sns.events = data.items || [];
        }
      } catch { /* 무시 */ }
      finally { this.sns.loading = false; }
    },

    // ── Trading (자동매매 시스템) 함수 ──
    async deleteSignal(signalId) {
      if (!confirm('이 시그널을 삭제하시겠습니까?')) return;
      try {
        const resp = await fetch(`/api/trading/signals/${signalId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (data.success) {
          this.trading.signals = this.trading.signals.filter(s => s.id !== signalId);
          this.showToast('시그널이 삭제되었습니다.', 'success');
        } else {
          this.showToast(data.error || '삭제 실패', 'error');
        }
      } catch (e) {
        console.error('Signal delete error:', e);
        this.showToast('시그널 삭제 중 오류가 발생했습니다.', 'error');
      }
    },

    async loadTradingSummary(isRefresh = false) {
      // 첫 로드만 로딩 표시, 30초 폴링 갱신 시에는 화면 유지 (깜빡임 방지)
      if (!isRefresh) this.trading.loading = true;
      try {
        const results = await Promise.allSettled([
          fetch('/api/trading/summary').then(r => r.ok ? r.json() : {}),
          fetch('/api/trading/portfolio').then(r => r.ok ? r.json() : {}),
          fetch('/api/trading/strategies').then(r => r.ok ? r.json() : []),
          fetch('/api/trading/watchlist').then(r => r.ok ? r.json() : []),
          fetch('/api/trading/history').then(r => r.ok ? r.json() : []),
          fetch('/api/trading/signals').then(r => r.ok ? r.json() : []),
        ]);
        const defaults = [{}, {}, [], [], [], []];
        const [summary, portfolio, strategies, watchlist, history, signals] = results.map((r, i) =>
          r.status === 'fulfilled' ? r.value : defaults[i]
        );
        this.trading.summary = summary;
        this.trading.portfolio = portfolio;
        this.trading.strategies = Array.isArray(strategies) ? strategies : [];
        this.trading.watchlist = Array.isArray(watchlist) ? watchlist : [];
        this.trading.history = Array.isArray(history) ? history : [];
        this.trading.signals = Array.isArray(signals) ? signals : [];
        this.trading.botActive = summary.bot_active || false;
        this.trading.settings = summary.settings || {};
        this.trading.schedule = summary.schedule || {};
        this.trading.lastRefresh = new Date().toLocaleTimeString('ko-KR', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
        // 관심종목이 있으면 시세도 자동 조회 (캐시가 비어있을 때만)
        if (this.trading.watchlist.length > 0 && Object.keys(this.trading.watchPrices).length === 0) {
          this.loadWatchlistPrices();
        }
      } catch(e) { console.error('Trading load error:', e); }
      finally { this.trading.loading = false; }
    },

    async tradingOrder() {
      const f = this.trading.orderForm;
      if (!f.ticker || !f.qty || !f.price) { this.showToast('종목코드, 수량, 가격을 입력하세요', 'error'); return; }
      const isReal = (this.trading.summary.settings||{}).paper_trading === false;
      const ko = f.action === 'buy' ? '매수' : '매도';
      if (isReal && !confirm(`[실거래] ${f.name||f.ticker} ${f.qty}주 ${ko} — 실제 증권 계좌에서 실행됩니다. 계속하시겠습니까?`)) return;
      try {
        const res = await fetch('/api/trading/order', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({action: f.action, ticker: f.ticker, name: f.name || f.ticker, qty: parseInt(f.qty), price: parseInt(f.price), market: f.market || 'KR'}),
        }).then(r => r.json());
        if (res.success) {
          const modeTag = res.mode ? ` [${res.mode}]` : '';
          this.showToast(`${ko} 완료${modeTag}: ${f.name || f.ticker} ${f.qty}주`, 'success');
          this.trading.showOrderModal = false;
          this.trading.orderForm = {action:'buy', ticker:'', name:'', qty:0, price:0, market:'KR'};
          await this.loadTradingSummary();
        } else { this.showToast(res.error || '주문 실패', 'error'); }
      } catch { this.showToast('주문 실행 오류', 'error'); }
    },

    async addTradingStrategy() {
      const f = this.trading.strategyForm;
      if (!f.name) { this.showToast('전략 이름을 입력하세요', 'error'); return; }
      try {
        const tickers = f.target_tickers ? f.target_tickers.split(',').map(t => t.trim()).filter(Boolean) : [];
        const res = await fetch('/api/trading/strategies', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({...f, target_tickers: tickers}),
        }).then(r => r.json());
        if (res.success) {
          this.showToast(`전략 저장: ${f.name}`, 'success');
          this.trading.showStrategyModal = false;
          this.trading.strategyForm = {name:'', type:'rsi', indicator:'RSI', buy_condition:'RSI < 30', sell_condition:'RSI > 70', target_tickers:'', stop_loss_pct:-5, take_profit_pct:10, order_size:1000000};
          await this.loadTradingSummary();
        } else { this.showToast(res.error || '전략 저장 실패', 'error'); }
      } catch { this.showToast('전략 저장 오류', 'error'); }
    },

    async deleteTradingStrategy(id) {
      try {
        await fetch(`/api/trading/strategies/${id}`, {method:'DELETE'});
        await this.loadTradingSummary();
        this.showToast('전략 삭제됨', 'success');
      } catch { this.showToast('삭제 실패', 'error'); }
    },

    async toggleTradingStrategy(id) {
      try {
        await fetch(`/api/trading/strategies/${id}/toggle`, {method:'PUT'});
        await this.loadTradingSummary();
      } catch { this.showToast('토글 실패', 'error'); }
    },

    async addWatchlistItem() {
      const f = this.trading.watchForm;
      if (!f.ticker) { this.showToast('종목코드를 입력하세요', 'error'); return; }
      try {
        const res = await fetch('/api/trading/watchlist', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify(f),
        }).then(r => r.json());
        if (res.success) {
          this.showToast(`관심종목 추가: ${f.name || f.ticker}`, 'success');
          this.trading.showWatchModal = false;
          this.trading.watchForm = {ticker:'', name:'', target_price:0, notes:'', market:'KR'};
          await this.loadTradingSummary();
          this.loadWatchlistPrices();  // 새 종목 가격도 바로 조회
        } else { this.showToast(res.error || '추가 실패', 'error'); }
      } catch { this.showToast('관심종목 추가 오류', 'error'); }
    },

    openWatchlistEdit(w) {
      this.trading.watchEditForm = {
        ticker: w.ticker,
        name: w.name,
        target_price: w.target_price || 0,
        notes: w.notes || '',
        alert_type: w.alert_type || 'above',
        market: w.market || 'KR',
      };
      this.trading.showWatchEditModal = true;
    },

    async updateWatchlistItem() {
      const f = this.trading.watchEditForm;
      try {
        const res = await fetch(`/api/trading/watchlist/${f.ticker}`, {
          method: 'PUT', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ target_price: f.target_price, alert_type: f.alert_type, notes: f.notes }),
        }).then(r => r.json());
        if (res.success) {
          this.showToast(`${f.name} 수정됨`, 'success');
          this.trading.showWatchEditModal = false;
          await this.loadTradingSummary();
        } else { this.showToast(res.error || '수정 실패', 'error'); }
      } catch { this.showToast('수정 오류', 'error'); }
    },

    // 관심종목 체크 선택/해제
    toggleWatchlistSelect(ticker) {
      if (!this.trading.selectedWatchlist) this.trading.selectedWatchlist = [];
      const idx = this.trading.selectedWatchlist.indexOf(ticker);
      if (idx >= 0) {
        this.trading.selectedWatchlist.splice(idx, 1);
      } else {
        this.trading.selectedWatchlist.push(ticker);
      }
    },

    // 선택 종목 즉시 분석 및 자동매매
    async analyzeSelectedWatchlist() {
      if (!this.trading.selectedWatchlist || this.trading.selectedWatchlist.length === 0) {
        this.showToast('분석할 종목을 선택하세요', 'warning');
        return;
      }
      this.trading.analyzingSelected = true;
      try {
        const resp = await fetch('/api/trading/watchlist/analyze-selected', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tickers: this.trading.selectedWatchlist }),
        });
        const data = await resp.json();
        if (data.success) {
          const names = this.trading.selectedWatchlist.map(t => {
            const w = this.trading.watchlist.find(x => x.ticker === t);
            return w ? w.name : t;
          }).join(', ');
          this.showToast(`${names} 분석 시작! 활동로그에서 진행 확인`, 'success');
        } else {
          this.showToast(data.message || '분석 실패', 'error');
          this.trading.analyzingSelected = false;
        }
      } catch {
        this.showToast('분석 요청 실패', 'error');
        this.trading.analyzingSelected = false;
      }
    },

    async removeWatchlistItem(ticker) {
      try {
        await fetch(`/api/trading/watchlist/${ticker}`, {method:'DELETE'});
        delete this.trading.watchPrices[ticker];
        await this.loadTradingSummary();
        this.showToast('관심종목 삭제됨', 'success');
      } catch { this.showToast('삭제 실패', 'error'); }
    },

    // 관심종목 드래그 순서 변경
    async watchlistDropReorder(targetTicker) {
      const dragged = this.trading.draggedTicker;
      if (!dragged || dragged === targetTicker) return;
      const list = [...this.trading.watchlist];
      const fromIdx = list.findIndex(w => w.ticker === dragged);
      const toIdx = list.findIndex(w => w.ticker === targetTicker);
      if (fromIdx < 0 || toIdx < 0) return;
      const [moved] = list.splice(fromIdx, 1);
      list.splice(toIdx, 0, moved);
      this.trading.watchlist = list;
      this.trading.draggedTicker = null;
      this.trading.dragOverTicker = null;
      // 백엔드에 순서 저장
      try {
        await fetch('/api/trading/watchlist/reorder', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tickers: list.map(w => w.ticker) }),
        });
      } catch {}
    },

    // 관심종목 실시간 가격 조회
    async loadWatchlistPrices() {
      if (this.trading.watchlist.length === 0) return;
      this.trading.watchPricesLoading = true;
      try {
        const res = await fetch('/api/trading/watchlist/prices').then(r => r.ok ? r.json() : {prices:{}});
        this.trading.watchPrices = res.prices || {};
        if (res.updated_at) {
          const d = new Date(res.updated_at);
          this.trading.watchPricesUpdatedAt = d.toLocaleTimeString('ko-KR', {hour:'2-digit', minute:'2-digit'});
        }
      } catch(e) { console.error('Price load error:', e); }
      finally { this.trading.watchPricesLoading = false; }
    },

    // 종목 차트 열기 (관심종목용)
    async openWatchlistChart(w) {
      this.openStockChart(w.ticker, w.name, w.market || 'KR');
    },

    // 종목 차트 열기 (대시보드/포트폴리오 범용)
    async openStockChart(ticker, name, market) {
      this.trading.chartTicker = ticker;
      this.trading.chartName = name || ticker;
      this.trading.chartMarket = market || 'KR';
      this.trading.chartData = [];
      this.trading.chartLoading = true;
      this.trading.showChartModal = true;
      try {
        const res = await fetch(`/api/trading/watchlist/chart/${ticker}?market=${market||'KR'}&days=30`).then(r => r.ok ? r.json() : {chart:[]});
        this.trading.chartData = res.chart || [];
      } catch(e) { console.error('Chart load error:', e); }
      finally { this.trading.chartLoading = false; }
    },

    // SVG 차트: 선 좌표 계산
    getChartLinePoints() {
      const data = this.trading.chartData;
      if (!data || data.length === 0) return '';
      const closes = data.map(d => d.close);
      const min = Math.min(...closes);
      const max = Math.max(...closes);
      const range = max - min || 1;
      const xStart = 45, xEnd = 550, yStart = 10, yEnd = 170;
      const xStep = (xEnd - xStart) / Math.max(data.length - 1, 1);
      return data.map((d, i) => {
        const x = xStart + i * xStep;
        const y = yEnd - ((d.close - min) / range) * (yEnd - yStart);
        return `${x},${y}`;
      }).join(' ');
    },

    // SVG 차트: 영역(면) 좌표 계산
    getChartAreaPoints() {
      const data = this.trading.chartData;
      if (!data || data.length === 0) return '';
      const closes = data.map(d => d.close);
      const min = Math.min(...closes);
      const max = Math.max(...closes);
      const range = max - min || 1;
      const xStart = 45, xEnd = 550, yStart = 10, yEnd = 170;
      const xStep = (xEnd - xStart) / Math.max(data.length - 1, 1);
      let pts = data.map((d, i) => {
        const x = xStart + i * xStep;
        const y = yEnd - ((d.close - min) / range) * (yEnd - yStart);
        return `${x},${y}`;
      });
      // 아래쪽 닫기
      const lastX = xStart + (data.length - 1) * xStep;
      pts.push(`${lastX},${yEnd}`);
      pts.push(`${xStart},${yEnd}`);
      return pts.join(' ');
    },

    // SVG 차트: Y축 라벨
    getChartYLabel(ratio) {
      const data = this.trading.chartData;
      if (!data || data.length === 0) return '';
      const closes = data.map(d => d.close);
      const min = Math.min(...closes);
      const max = Math.max(...closes);
      const val = min + (max - min) * ratio;
      if (val >= 1000000) return (val / 10000).toFixed(0) + '만';
      if (val >= 1000) return val.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      return val.toFixed(2);
    },

    // CIO SSE/폴링 제거됨 — _connectCommsSSE()에서 통합 처리

    // ── 활동로그 전용 탭 ──
    async loadCioActivityLog() {
      const al = this.trading.activityLog;
      al.loading = true;
      try {
        const [delegLogs, actLogs] = await Promise.all([
          fetch('/api/delegation-log?division=cio&limit=50').then(r => r.ok ? r.json() : []).catch(() => []),
          fetch('/api/activity-logs?limit=100').then(r => r.ok ? r.json() : []).catch(() => []),
        ]);
        // CIO 관련 activity_logs 필터링
        const cioKeywords = ['cio', 'stock_analysis', 'market_condition', 'technical_analysis', 'risk_management'];
        const cioActs = (Array.isArray(actLogs) ? actLogs : []).filter(l => {
          const aid = (l.agent_id || '').toLowerCase();
          return cioKeywords.some(k => aid.includes(k));
        });
        // 통합: delegation_log + activity_logs → 타임라인
        const merged = [];
        for (const d of (Array.isArray(delegLogs) ? delegLogs : [])) {
          const toolsRaw = d.tools_used || '';
          const toolsList = typeof toolsRaw === 'string'
            ? toolsRaw.split(',').map(t => t.trim()).filter(Boolean)
            : (Array.isArray(toolsRaw) ? toolsRaw : []);
          merged.push({
            id: String(d.id || '').startsWith('dl_') ? String(d.id) : 'dl_' + d.id,
            type: d.log_type || 'delegation',
            sender: d.sender || '',
            receiver: d.receiver || '',
            message: d.message || '',
            tools: toolsList,
            time: d.created_at || '',
            _ts: new Date(d.created_at || 0).getTime(),
          });
        }
        for (const a of cioActs) {
          merged.push({
            id: 'al_' + (a.timestamp || Math.random()),
            type: 'activity',
            sender: a.agent_id || '',
            receiver: '',
            message: a.message || '',
            tools: [],
            level: a.level || 'info',
            time: a.created_at || a.time || '',
            _ts: a.timestamp || 0,
          });
        }
        // 시간순 정렬 (최신 먼저)
        merged.sort((a, b) => b._ts - a._ts);
        al.logs = merged.slice(0, 100);
      } catch (e) {
        console.warn('활동로그 로드 실패:', e);
      }
      al.loading = false;
    },

    getCioLogIcon(log) {
      if (log.level === 'qa_pass') return '✅';
      if (log.level === 'qa_fail') return '❌';
      if (log.level === 'qa_detail') return (log.message || '').startsWith('✅') ? '✅' : '❌';
      if (log.level === 'tool') return '🔧';
      if (log.type === 'delegation') return '📡';
      if (log.type === 'report') return '📊';
      if (log.type === 'activity') {
        if (log.level === 'error') return '🔴';
        if (log.level === 'warning') return '⚠️';
        return '📋';
      }
      return '💬';
    },

    getCioLogColor(log) {
      // #4: 에이전트별 색상 구분 (CIO팀 내부)
      const sender = (log.sender || log.agent_id || '').toLowerCase();
      if (sender.includes('cio_manager') || sender.includes('투자분석처장')) return 'text-hq-accent';
      if (sender.includes('market_condition') || sender.includes('시황')) return 'text-hq-cyan';
      if (sender.includes('stock_analysis') || sender.includes('종목')) return 'text-hq-green';
      if (sender.includes('technical_analysis') || sender.includes('기술')) return 'text-hq-yellow';
      if (sender.includes('risk_management') || sender.includes('리스크')) return 'text-hq-red';
      // 로그 타입 폴백
      if (log.type === 'delegation') return 'text-hq-yellow';
      if (log.type === 'report') return 'text-hq-green';
      return 'text-hq-muted';
    },

    // #5: CIO팀 발신자 표기 통일 — 짧고 일관된 이름
    getCioShortName(agentIdOrName) {
      if (!agentIdOrName) return '';
      const id = agentIdOrName.toLowerCase();
      if (id.includes('cio_manager') || id.includes('투자분석처장')) return 'CIO';
      if (id.includes('market_condition') || id.includes('시황분석')) return '시황분석';
      if (id.includes('stock_analysis') || id.includes('종목분석')) return '종목분석';
      if (id.includes('technical_analysis') || id.includes('기술적분석') || id.includes('기술분석')) return '기술분석';
      if (id.includes('risk_management') || id.includes('리스크')) return '리스크';
      return this.getAgentName(agentIdOrName) || agentIdOrName;
    },

    getFilteredCioLogs() {
      const tab = this.trading.activityLog.subTab;
      const logs = this.trading.activityLog.logs;
      if (tab === 'activity') return logs.filter(l => l.level !== 'tool' && l.level !== 'qa_pass' && l.level !== 'qa_fail' && l.level !== 'qa_detail' && l.type !== 'delegation' && l.type !== 'report');
      if (tab === 'comms') return logs.filter(l => l.type === 'delegation' || l.type === 'report');
      if (tab === 'qa') return logs.filter(l => l.level === 'qa_pass' || l.level === 'qa_fail' || l.level === 'qa_detail');
      if (tab === 'tools') return logs.filter(l => (l.tools || []).length > 0 || l.level === 'tool');
      return logs;
    },
    clearCioLogsTab(tab) {
      const logs = this.trading.activityLog.logs;
      if (tab === 'activity') { this.trading.activityLog.logs = logs.filter(l => l.level === 'tool' || l.level === 'qa_pass' || l.level === 'qa_fail' || l.type === 'delegation' || l.type === 'report'); fetch('/api/activity-logs', {method:'DELETE'}); }
      else if (tab === 'comms') { this.trading.activityLog.logs = logs.filter(l => l.type !== 'delegation' && l.type !== 'report'); fetch('/api/delegation-log', {method:'DELETE'}); }
      else if (tab === 'qa') { this.trading.activityLog.logs = logs.filter(l => l.level !== 'qa_pass' && l.level !== 'qa_fail'); fetch('/api/activity-logs?level=qa', {method:'DELETE'}); }
      else if (tab === 'tools') { this.trading.activityLog.logs = logs.filter(l => !(l.tools || []).length && l.level !== 'tool'); fetch('/api/activity-logs?level=tool', {method:'DELETE'}); }
    },

    formatLogTime(timeStr) {
      if (!timeStr) return '';
      try {
        const d = new Date(timeStr);
        if (isNaN(d.getTime())) return timeStr;
        return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      } catch { return timeStr; }
    },

    async stopAnalysis() {
      try {
        const res = await fetch('/api/trading/bot/stop', { method: 'POST' }).then(r => r.json());
        if (res.success) {
          this.showToast('분석이 중지되었습니다.', 'info');
          this.trading.runningNow = false;
          this.trading.analyzingSelected = false;
          if (this._tradingRunPoll) { clearInterval(this._tradingRunPoll); this._tradingRunPoll = null; }
        } else {
          this.showToast(res.message || '중지할 분석이 없습니다.', 'info');
        }
      } catch { this.showToast('중지 요청 실패', 'error'); }
    },

    async runTradingNow() {
      if (this.trading.runningNow) return;
      this.trading.runningNow = true;
      this.trading.cioLogs = [];
      this.trading.activityLog.logs = [];
      this._connectCommsSSE(); // SSE 통합: CIO 로그 실시간 수신
      this.showToast('CIO + 전문가 4명 즉시 분석 + 매매결정 중... (5~10분)', 'info');
      try {
        const resp = await fetch('/api/trading/bot/run-now', {method:'POST'});
        if (!resp.ok) throw new Error(`서버 오류 (${resp.status})`);
        const res = await resp.json();
        if (res.already_running) {
          this.showToast('CIO 분석이 이미 진행 중입니다', 'info');
        } else if (res.background) {
          this.showToast('CIO 분석 시작! 활동 로그에서 실시간 확인하세요', 'success');
          // 백그라운드 완료 대기 (폴링)
          this._tradingRunPoll = setInterval(async () => {
            try {
              const st = await fetch('/api/trading/bot/run-status').then(r => r.json());
              if (st.status === 'completed') {
                clearInterval(this._tradingRunPoll);
                this._tradingRunPoll = null;
                if (st.success) {
                  const sigs = st.signals || [];
                  const buy = sigs.filter(s => s.action === 'buy').length;
                  const sell = sigs.filter(s => s.action === 'sell').length;
                  const orders = st.orders_triggered || 0;
                  if (st.calibration) this.trading.calibration = st.calibration;
                  let msg = `분석 완료! 매수 ${buy} · 매도 ${sell}`;
                  msg += orders > 0 ? ` · 주문 ${orders}건 실행됨!` : ' · 매매 조건 미충족';
                  this.showToast(msg + ' → 시그널탭 확인', orders > 0 ? 'success' : 'info');
                } else {
                  this.showToast(st.message || '분석 실패', 'error');
                }
                this.trading.tab = 'signals';
                // 최종 데이터 로드
                try {
                  const [dec, logs] = await Promise.all([
                    fetch('/api/trading/decisions').then(r=>r.ok?r.json():{decisions:[]}).catch(()=>({decisions:[]})),
                    fetch('/api/delegation-log?division=cio&limit=30').then(r=>r.ok?r.json():[]).catch(()=>[]),
                  ]);
                  this.trading.decisions = dec.decisions || [];
                  this.trading.cioLogs = Array.isArray(logs) ? logs : [];
                  await this.loadTradingSummary();
                } catch {}
                this.trading.runningNow = false;
              }
            } catch {}
          }, 5000); // 5초마다 폴링
        } else if (!res.success) {
          this.showToast(res.message || '분석 실패', 'error');
          this.trading.runningNow = false;
        }
      } catch (err) {
        this.showToast(`분석 오류: ${err.message || '서버 연결 실패'}`, 'error');
        this.trading.runningNow = false;
      }
    },

    async toggleTradingBot() {
      try {
        const res = await fetch('/api/trading/bot/toggle', {method:'POST'}).then(r => r.json());
        if (res.success) {
          this.trading.botActive = res.bot_active;
          this.showToast(res.bot_active ? 'CIO 자동매매 가동!' : 'CIO 자동매매 중지', res.bot_active ? 'success' : 'info');
        }
      } catch { this.showToast('봇 토글 실패', 'error'); }
    },

    async generateTradingSignals() {
      this.trading.loadingSignals = true;
      this.showToast('CIO + 전문가 4명 분석 중... (5~10분 소요)', 'info');
      try {
        const res = await fetch('/api/trading/signals/generate', {method:'POST'}).then(r => r.json());
        if (res.success) {
          const ps = res.parsed_signals || [];
          const buy = ps.filter(s => s.action === 'buy').length;
          const sell = ps.filter(s => s.action === 'sell').length;
          this.showToast(`CIO 분석 완료! 매수 ${buy}건, 매도 ${sell}건`, 'success');
          await this.loadTradingSummary();
        } else { this.showToast(res.error || '분석 실패', 'error'); }
      } catch { this.showToast('CIO 분석 요청 오류', 'error'); }
      finally { this.trading.loadingSignals = false; }
    },

    async resetTradingPortfolio() {
      if (!confirm('모의투자를 초기화하시겠습니까? 모든 보유종목과 거래 내역이 삭제됩니다.')) return;
      try {
        const res = await fetch('/api/trading/portfolio/reset', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({initial_cash: parseInt(this.trading.initialCashInput) || 50000000}),
        }).then(r => r.json());
        if (res.success) {
          this.showToast('모의투자 초기화 완료!', 'success');
          await this.loadTradingSummary();
        }
      } catch { this.showToast('초기화 실패', 'error'); }
    },

    async saveTradingSettings() {
      try {
        const res = await fetch('/api/trading/settings', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify(this.trading.settings),
        }).then(r => r.json());
        if (res.success) {
          this.showToast('자동매매 설정 저장됨', 'success');
          this.trading.showSettingsModal = false;
          await this.loadTradingSummary();
        }
      } catch { this.showToast('설정 저장 실패', 'error'); }
    },

    tradingPnlColor(val) {
      if (val > 0) return 'text-hq-green';
      if (val < 0) return 'text-hq-red';
      return 'text-hq-muted';
    },

    formatKRW(val) {
      if (Math.abs(val) >= 100000000) return (val / 100000000).toFixed(1) + '억';
      if (Math.abs(val) >= 10000) return (val / 10000).toFixed(0) + '만';
      return val.toLocaleString();
    },

    // #5: loadToolsList 삭제 — loadAgentsAndTools()에서 tools도 함께 로드

    // ── #7: Feedback Stats ──
    async loadFeedbackStats() {
      try {
        const data = await fetch('/api/feedback').then(r => r.ok ? r.json() : {});
        this.feedbackStats = {
          good: data.good || 0,
          bad: data.bad || 0,
          total: data.total || 0,
          satisfaction_rate: data.total > 0 ? Math.round((data.good / data.total) * 100) : 0,
        };
      } catch { /* 무시 */ }
    },

    // ── #8: Budget Edit ──
    async saveBudget() {
      try {
        const res = await fetch('/api/budget', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ daily_limit: this.budgetEditDaily, monthly_limit: this.budgetEditMonthly }),
        }).then(r => r.json());
        if (res.success) {
          this.budget.daily_limit = res.daily_limit;
          this.budget.monthly_limit = res.monthly_limit;
          this.showBudgetEdit = false;
          this.loadDashboard();
          this.showToast('예산 한도가 수정되었습니다.', 'success');
        } else {
          this.showToast(res.error || '예산 수정 실패', 'error');
        }
      } catch { this.showToast('예산 수정에 실패했습니다.', 'error'); }
    },

    // ── Model Mode (자동/수동) ──
    async loadModelMode() {
      try {
        const [res, modelsRes] = await Promise.all([
          fetch('/api/model-mode').then(r => r.json()),
          !this.availableModels.length ? fetch('/api/available-models').then(r => r.json()) : Promise.resolve(null),
        ]);
        this.modelMode = res.mode || 'auto';
        this.modelOverride = res.override || '';
        if (modelsRes && Array.isArray(modelsRes)) {
          this.availableModels = this.sortModels(modelsRes);
        }
      } catch {}
    },
    async saveModelMode() {
      try {
        await fetch('/api/model-mode', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: this.modelMode }),
        });
        const label = this.modelMode === 'auto' ? '자동 모드 (질문에 따라 자동 선택)' : '수동 모드 (에이전트별 개별 모델)';
        this.showToast(label, 'success');
      } catch { this.showToast('모델 모드 변경 실패', 'error'); }
    },

    async applyRecommendedModels() {
      try {
        const res = await fetch('/api/agents/apply-recommended', { method: 'POST' }).then(r => r.json());
        if (res.error) {
          this.showToast(res.error, 'error');
          return;
        }
        if (res.success) {
          this.modelMode = 'recommended';
          await fetch('/api/model-mode', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'recommended' }),
          }).catch(() => {});
          // 에이전트 목록 새로고침 → 카드 모델 표시 갱신
          await this.loadAgentsAndTools();
          this.showToast(`권장 모델 적용 완료 (${res.applied_count}명)`, 'success');
        } else {
          this.showToast('적용 실패: 서버 응답 오류', 'error');
        }
      } catch(e) { this.showToast('적용 실패: ' + (e.message || '네트워크 오류'), 'error'); }
    },

    async saveAgentDefaults() {
      try {
        const res = await fetch('/api/agents/save-defaults', { method: 'POST' }).then(r => r.json());
        if (res.success) this.showToast(`기본값 저장 완료 (${res.saved_count}명)`, 'success');
        else this.showToast('저장 실패', 'error');
      } catch { this.showToast('저장 실패', 'error'); }
    },

    async restoreAgentDefaults() {
      if (!confirm('저장된 기본값으로 전체 에이전트 모델을 복원합니다.\n계속할까요?')) return;
      try {
        const res = await fetch('/api/agents/restore-defaults', { method: 'POST' }).then(r => r.json());
        if (res.success) {
          const src = res.source === 'snapshot' ? '내가 저장한 기본값' : 'YAML 기본값';
          this.showToast(`${src}으로 복원 완료 (${res.restored_count}명)`, 'success');
          this.loadDashboard();
        } else {
          this.showToast(res.error || '복원 실패', 'error');
        }
      } catch { this.showToast('복원 실패', 'error'); }
    },

    async applyBulkModel() {
      if (!this.bulkModelSelection) return;
      const displayName = this.getModelDisplayName(this.bulkModelSelection);
      const label = this.bulkReasoningSelection ? `${displayName} (${this.bulkReasoningSelection})` : displayName;
      if (!confirm(`29명 전체 에이전트의 모델을 "${label}"(으)로 변경합니다.\n\n정말 진행할까요?`)) return;
      this.bulkModelSaving = true;
      try {
        const res = await fetch('/api/agents/bulk-model', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_name: this.bulkModelSelection, reasoning_effort: this.bulkReasoningSelection }),
        }).then(r => r.json());
        if (res.error) {
          this.showToast(res.error, 'error');
        } else {
          // 모든 에이전트 카드 표시 갱신
          for (const a of Object.keys(this.agentModels)) {
            this.agentModelRaw[a] = this.bulkModelSelection;
            this.agentReasonings[a] = this.bulkReasoningSelection;
            this.agentModels[a] = this.bulkReasoningSelection ? `${displayName} (${this.bulkReasoningSelection})` : displayName;
          }
          this.showToast(`${res.changed}명 에이전트 → ${label} 변경 완료`, 'success');
          // 모달이 열려있으면 데이터 재로드
          if (this.showAgentConfig && this.agentConfigId) {
            try {
              const updatedAgent = await fetch(`/api/agents/${this.agentConfigId}`).then(r => r.json());
              if (!updatedAgent.error) {
                this.agentConfigData = updatedAgent;
                this.agentModelSelection = updatedAgent.model_name || '';
                this.agentReasoningSelection = updatedAgent.reasoning_effort || '';
              }
            } catch (e) { /* 무시 */ }
          }
        }
      } catch (e) {
        this.showToast('일괄 변경 실패: ' + (e.message || '서버 연결 오류'), 'error');
      } finally {
        this.bulkModelSaving = false;
      }
    },

    // ── #13: Activity Log Persistence ──
    restoreActivityLogs() {
      // DB에서 최근 활동 로그 불러오기 (페이지 새로고침해도 이력 유지)
      fetch('/api/activity-logs?limit=100')
        .then(r => r.json())
        .then(logs => {
          if (Array.isArray(logs)) {
            const formatted = logs.reverse().filter(l => l.agent_id !== 'system').map(l => {
              const d = l.created_at ? new Date(l.created_at) : new Date();
              const dateStr = d.toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).replace(/\.\s*/g, '.').replace(/\.$/, '');
              const timeStr = d.toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false, hour: '2-digit', minute: '2-digit' });
              return { ...l, action: l.message || l.action || '', timeDate: dateStr, timeClock: timeStr, time: dateStr + ' ' + timeStr, timestamp: l.timestamp || d.getTime() };
            });
            // level별 분류 (4탭 복원)
            this.activityLogs = formatted.filter(l => l.level !== 'tool' && l.level !== 'qa_pass' && l.level !== 'qa_fail' && l.level !== 'qa_detail');
            this.toolLogs = formatted.filter(l => l.level === 'tool');
            this.qaLogs = formatted.filter(l => l.level === 'qa_pass' || l.level === 'qa_fail' || l.level === 'qa_detail');
          }
        })
        .catch(() => { this.activityLogs = []; });
    },
    saveActivityLogs() {
      // DB에 자동 저장되므로 별도 저장 불필요
    },
    // ── 탭별 전체삭제 (DB + 화면) ──
    clearLogsTab(tab) {
      if (tab === 'activity') { this.activityLogs = []; fetch('/api/activity-logs', {method:'DELETE'}); }
      else if (tab === 'comms') { this.delegationLogs = []; fetch('/api/delegation-log', {method:'DELETE'}); }
      else if (tab === 'qa') { this.qaLogs = []; fetch('/api/activity-logs?level=qa', {method:'DELETE'}); }
      else if (tab === 'tools') { this.toolLogs = []; fetch('/api/activity-logs?level=tool', {method:'DELETE'}); }
    },

    // ── #14: Task History Pagination ──
    getPagedTaskHistory() {
      const end = this.taskHistoryPage * this.taskHistoryPageSize;
      return this.taskHistory.items.slice(0, end);
    },
    getGroupedTaskHistory() {
      try {
        const items = this.getPagedTaskHistory();
        if (!items || items.length === 0) return [];
        const groups = [];
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        let currentLabel = '';
        let currentGroup = null;
        for (const task of items) {
          try {
            const d = new Date(task.created_at || Date.now());
            d.setHours(0, 0, 0, 0);
            let label;
            if (d.getTime() === today.getTime()) label = '오늘';
            else if (d.getTime() === yesterday.getTime()) label = '어제';
            else label = d.toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric' });
            if (label !== currentLabel) {
              currentLabel = label;
              currentGroup = { label, items: [] };
              groups.push(currentGroup);
            }
            currentGroup.items.push(task);
          } catch (itemErr) {
            console.warn('Task date parse error:', itemErr, task);
          }
        }
        return groups;
      } catch (e) {
        console.error('getGroupedTaskHistory error:', e);
        return [];
      }
    },
    loadMoreTasks() {
      this.taskHistoryPage++;
    },
    hasMoreTasks() {
      return this.taskHistoryPage * this.taskHistoryPageSize < this.taskHistory.items.length;
    },

    // ── #15: Conversation Export ──
    exportConversation() {
      let md = '# CORTHEX HQ 대화 기록\n\n';
      md += `날짜: ${new Date().toLocaleDateString('ko-KR')}\n\n---\n\n`;
      this.messages.forEach(msg => {
        if (msg.type === 'user') {
          md += `## CEO 명령\n\n${msg.text}\n\n`;
        } else if (msg.type === 'result') {
          md += `## 결과 (${msg.sender_id || 'system'})\n\n${msg.content || ''}\n\n---\n\n`;
        } else if (msg.type === 'error') {
          md += `## 오류\n\n${msg.text}\n\n`;
        }
      });
      const blob = new Blob([md], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `corthex-대화-${new Date().toISOString().slice(0, 10)}.md`;
      a.click();
      URL.revokeObjectURL(url);
      this.showToast('대화 기록이 다운로드되었습니다.', 'success');
    },

    // ── 대화 비우기 ──
    async clearConversation() {
      if (this.messages.length === 0) return;
      if (!confirm('현재 대화를 비우고 새 대화를 시작하시겠습니까?')) return;
      try {
        if (this.currentConversationId) {
          // 세션 보관 처리 (삭제 대신 비활성화)
          await fetch(`/api/conversation/sessions/${this.currentConversationId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: 0 }),
          });
        } else {
          // 레거시: 전체 삭제
          await fetch('/api/conversation', { method: 'DELETE' });
        }
        this.messages = [];
        this.currentConversationId = null;
        this.conversationTurnCount = 0;
        this.activeAgents = {};
        this.systemStatus = 'idle';
        this.showToast('대화가 비워졌습니다. 새 대화를 시작하세요.', 'success');
        this.loadConversationList();
      } catch (e) {
        this.showToast('대화 삭제에 실패했습니다.', 'error');
      }
    },

    // ── 멀티턴 대화 세션 관리 ──
    async newConversation(agentId = null) {
      try {
        const res = await fetch('/api/conversation/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ agent_id: agentId }),
        });
        const data = await res.json();
        if (data.success) {
          this.currentConversationId = data.session.conversation_id;
          this.messages = [];
          this.conversationTurnCount = 0;
          this.activeAgents = {};
          this.systemStatus = 'idle';
          this.loadConversationList();
          this.showToast('새 대화가 시작되었습니다.', 'success');
        }
      } catch (e) {
        console.warn('새 대화 생성 실패:', e);
      }
    },

    async loadConversationList() {
      try {
        const res = await fetch('/api/conversation/sessions?limit=30');
        if (res.ok) {
          this.conversationList = await res.json();
        }
      } catch (e) {
        console.warn('대화 목록 로딩 실패:', e);
      }
    },

    async switchConversation(conversationId) {
      try {
        const res = await fetch(`/api/conversation/sessions/${conversationId}/messages`);
        if (!res.ok) return;
        this.messages = await res.json();
        this.currentConversationId = conversationId;
        const meta = await fetch(`/api/conversation/sessions/${conversationId}`);
        if (meta.ok) {
          const session = await meta.json();
          this.conversationTurnCount = session.turn_count || 0;
        }
        this.showConversationDrawer = false;
        this.activeAgents = {};
        this.systemStatus = 'idle';
        this.$nextTick(() => this.scrollToBottom());
        setTimeout(() => this.scrollToBottom(), 300);
      } catch (e) {
        console.warn('대화 전환 실패:', e);
      }
    },

    async deleteConversationSession(conversationId) {
      if (!confirm('이 대화를 삭제하시겠습니까?')) return;
      try {
        await fetch(`/api/conversation/sessions/${conversationId}`, { method: 'DELETE' });
        this.conversationList = this.conversationList.filter(c => c.conversation_id !== conversationId);
        if (this.currentConversationId === conversationId) {
          this.currentConversationId = null;
          this.messages = [];
          this.conversationTurnCount = 0;
        }
      } catch (e) {
        console.warn('대화 삭제 실패:', e);
      }
    },

    // ── #16: Keyboard Shortcuts ──
    initKeyboardShortcuts() {
      document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + K → 명령 입력창으로 포커스
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
          e.preventDefault();
          this.activeTab = 'command';
          this.viewMode = 'chat';
          this.$nextTick(() => {
            if (this.$refs.inputArea) this.$refs.inputArea.focus();
            this.scrollToBottom();
          });
          setTimeout(() => this.scrollToBottom(), 300);
        }
        // Esc → 모달 닫기
        if (e.key === 'Escape') {
          if (this.nexusOpen) {
            this.nexusOpen = false;
            if (this.flowchart.graph3dLabelsAnimId) { cancelAnimationFrame(this.flowchart.graph3dLabelsAnimId); this.flowchart.graph3dLabelsAnimId = 0; }
            return;
          }
          if (this.agoraOpen) { this.agoraOpen = false; if (this.agora.sseSource) { this.agora.sseSource.close(); this.agora.sseSource = null; } return; }
          if (this.showAgentConfig) { this.showAgentConfig = false; return; }
          if (this.showQualitySettings) { this.showQualitySettings = false; return; }
          if (this.showTaskDetail) { this.showTaskDetail = false; return; }
          if (this.showBudgetEdit) { this.showBudgetEdit = false; return; }
          if (this.taskHistory.compareMode) { this.taskHistory.compareMode = false; return; }
          if (this.memoryModal.visible) { this.memoryModal.visible = false; return; }
        }
      });
    },

    // ── #12: Tab grouping helpers ──
    getPrimaryTabs() {
      // 메인 탭 순서: 작전현황 / 사령관실 / 통신로그 / 전략실 / 작전일지
      const order = ['home', 'command', 'activityLog', 'trading', 'history'];
      return order.map(id => this.tabs.find(t => t.id === id)).filter(Boolean);
    },
    getSecondaryTabs() {
      // 더보기: 전력분석 / 기밀문서 / 자동화 / 크론기지 / 정보국 / 통신국 (조직도·NEXUS → 헤더로 이동)
      const order = ['performance', 'archive', 'workflow', 'schedule', 'knowledge', 'sns'];
      return order.map(id => this.tabs.find(t => t.id === id)).filter(Boolean);
    },

    // ── #4: Publishing division support ──
    getDivisionLabel(division) {
      const labels = {
        'default': '기본 (전체 공통)',
        'secretary': '비서실',
        'leet_master.tech': '기술개발팀 (CTO)',
        'leet_master.strategy': '전략기획팀 (CSO)',
        'leet_master.legal': '법무팀 (CLO)',
        'leet_master.marketing': '마케팅팀 (CMO)',
        'finance.investment': '금융분석팀 (CIO)',
        'publishing': '콘텐츠팀 (CPO)',
      };
      return labels[division] || division;
    },

    // 에이전트 직급 분류
    getAgentTier(agentId) {
      if (!agentId) return 'unknown';
      if (agentId === 'argos') return 'system';
      const executives = ['chief_of_staff','cto_manager','cso_manager','clo_manager','cmo_manager','cio_manager','cpo_manager'];
      const staffList = ['report_specialist','schedule_specialist','relay_specialist'];
      if (executives.includes(agentId)) return 'executive';
      if (staffList.includes(agentId)) return 'staff';
      if (agentId.includes('specialist') || agentId.includes('_specialist')) return 'specialist';
      return 'specialist';
    },

    getAgentTierLabel(agentId) {
      const tier = this.getAgentTier(agentId);
      if (tier === 'system') return 'SYSTEM';
      if (tier === 'executive') return '임원급';
      if (tier === 'staff') return '보좌관급';
      return '전문가급';
    },

    // 기밀문서 카드용: agent_id → 한글 이름
    getArchiveAuthor(agentId) {
      if (!agentId) return '알 수 없음';
      return this.agentNames[agentId] || agentId;
    },

    // 기밀문서 카드용: created_at → "2/16 오후 4:36" 형태
    formatArchiveDate(dateStr) {
      if (!dateStr) return '';
      try {
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        const m = d.getMonth() + 1;
        const day = d.getDate();
        const h = d.getHours();
        const min = String(d.getMinutes()).padStart(2, '0');
        const ampm = h < 12 ? '오전' : '오후';
        const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
        return `${m}/${day} ${ampm} ${h12}:${min}`;
      } catch { return dateStr; }
    },

    getDivisionStyle(division) {
      const styles = {
        'secretary': { icon: '📋', bg: 'from-amber-500/10 to-orange-500/10' },
        'leet_master.tech': { icon: '💻', bg: 'from-blue-500/10 to-cyan-500/10' },
        'leet_master.strategy': { icon: '📊', bg: 'from-purple-500/10 to-violet-500/10' },
        'leet_master.legal': { icon: '⚖️', bg: 'from-emerald-500/10 to-green-500/10' },
        'leet_master.marketing': { icon: '📣', bg: 'from-orange-500/10 to-amber-500/10' },
        'finance.investment': { icon: '💰', bg: 'from-red-500/10 to-rose-500/10' },
        'publishing': { icon: '✍️', bg: 'from-fuchsia-500/10 to-pink-500/10' },
      };
      return styles[division] || { icon: '📌', bg: 'from-gray-500/10 to-slate-500/10' };
    },

    getToolDisplayName(toolId) {
      const t = (this.toolsList || []).find(t => t.tool_id === toolId || t.name === toolId);
      return t?.name_ko || toolId;
    },

    getToolDescription(toolId) {
      const t = (this.toolsList || []).find(t => t.tool_id === toolId || t.name === toolId);
      return t?.description || '';
    },

    // ── SNS platform name mapping (#6) ──
    getSNSPlatformName(platform) {
      const names = {
        'instagram': 'Instagram',
        'youtube': 'YouTube',
        'tistory': 'Tistory',
        'naver_blog': '네이버 블로그',
        'naver_cafe': '네이버 카페',
        'daum_cafe': '다음 카페',
      };
      return names[platform] || platform;
    },

    shouldShowDateSeparator(messages, i) {
      if (i === 0) return true;
      const prev = messages[i-1]?.timestamp;
      const curr = messages[i]?.timestamp;
      if (!prev || !curr) return i === 0;
      return new Date(prev).toDateString() !== new Date(curr).toDateString();
    },
    formatDate(ts) {
      if (!ts) return '';
      const d = new Date(ts);
      const days = ['일요일','월요일','화요일','수요일','목요일','금요일','토요일'];
      return `${d.getFullYear()}년 ${d.getMonth()+1}월 ${d.getDate()}일 ${days[d.getDay()]}`;
    },
    // UTC 타임스탬프 파싱 헬퍼 (SQLite CURRENT_TIMESTAMP = UTC 기준, 'Z' 붙여서 강제 UTC 파싱)
    _parseTS(ts) {
      if (!ts) return null;
      const s = String(ts).replace(' ', 'T');
      return new Date((s.includes('+') || s.includes('Z')) ? s : s + 'Z');
    },
    formatTime(ts) {
      const d = this._parseTS(ts);
      if (!d || isNaN(d)) return '';
      return d.toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    },
    // 내부통신 — 상대시간 ("방금", "3분 전", hover 시 정확한 시간)
    relativeTimeStr(ts) {
      const d = this._parseTS(ts);
      if (!d || isNaN(d)) return '';
      const diff = Date.now() - d.getTime();
      const sec = Math.floor(diff / 1000);
      if (sec < 60) return '방금';
      const min = Math.floor(sec / 60);
      if (min < 60) return min + '분 전';
      const hr = Math.floor(min / 60);
      if (hr < 24) return hr + '시간 전';
      return Math.floor(hr / 24) + '일 전';
    },
    // 내부통신 — 에이전트별 컬러 (발신자 agentId 기반)
    getDeptColor(agentId) {
      if (!agentId) return '#6b7280';
      const id = agentId.toLowerCase();
      // CIO 팀 — 개별 색상 구분 (#4)
      if (id.includes('cio_manager') || id === 'cio' || id.includes('투자분석처장')) return '#00d4aa';  // 청록 (처장)
      if (id.includes('market_condition') || id.includes('시황분석')) return '#00b4d8';  // 시안 (시황)
      if (id.includes('stock_analysis') || id.includes('종목분석')) return '#34d399';   // 초록 (종목)
      if (id.includes('technical_analysis') || id.includes('기술적분석')) return '#fbbf24';  // 노랑 (기술)
      if (id.includes('risk_management') || id.includes('리스크')) return '#f87171';    // 빨강 (리스크)
      // CIO 팀 기타 (finance division)
      if (id.includes('finance')) return '#fbbf24';
      // CTO / 기술개발처 (청록색)
      if (id.includes('cto') || id.includes('기술개발') || id.includes('frontend') || id.includes('프론트엔드') || id.includes('backend') || id.includes('백엔드') || id.includes('infra') || id.includes('인프라') || id.includes('ai_model') || id.includes('ai모델')) return '#22d3ee';
      // CMO / 마케팅고객처 (보라색)
      if (id.includes('cmo') || id.includes('마케팅') || id.includes('community') || id.includes('커뮤니티') || id.includes('content_spec') || id.includes('콘텐츠') || id.includes('survey') || id.includes('설문')) return '#a855f7';
      // CLO / 법무IP처 (빨간색)
      if (id.includes('clo') || id.includes('법무') || id.includes('copyright') || id.includes('저작권') || id.includes('patent') || id.includes('특허')) return '#f43f5e';
      // CSO / 사업기획처 (주황색)
      if (id.includes('cso') || id.includes('사업기획') || id.includes('business_plan') || id.includes('사업계획') || id.includes('market_research') || id.includes('시장조사') || id.includes('financial_model') || id.includes('재무모델')) return '#f97316';
      // CPO / 출판기록처 (바이올렛)
      if (id.includes('cpo') || id.includes('출판') || id.includes('chronicle') || id.includes('연대기') || id.includes('editor') || id.includes('편집') || id.includes('archive') || id.includes('아카이브')) return '#8b5cf6';
      // 비서실 (앰버)
      if (id.includes('chief') || id.includes('비서') || id.includes('relay') || id.includes('소통') || id.includes('report_spec') || id.includes('기록') || id.includes('schedule') || id.includes('일정')) return '#f59e0b';
      return '#6b7280';
    },
    // 내부통신 — 마크다운 제거 + 150자 미리보기
    stripMarkdownPreview(text) {
      if (!text) return '';
      return text.replace(/^#+\s*/gm, '').replace(/\*\*([^*]+)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1').replace(/`([^`]+)`/g, '$1').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/\n+/g, ' ').trim().slice(0, 150);
    },

    onChatScroll(e) {
      const el = e.target;
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
      this.showScrollBtn = !atBottom;
      if (atBottom) this.newMsgCount = 0;
    },
    scrollToBottomSmooth() {
      const el = this.$refs.chatArea;
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
      this.showScrollBtn = false;
      this.newMsgCount = 0;
    },

    scrollToBottom() {
      const el = this.$refs.chatArea || document.getElementById('chatArea');
      if (el) {
        el.scrollTop = el.scrollHeight;
        // 마크다운 렌더링 이후에도 한 번 더
        requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
      }
    },

    // ── 설계실: 초기화 (Mermaid 로드) ──
    async _initMermaid() {
      await _loadScript(_CDN.mermaid);
      window.mermaid.initialize({
        startOnLoad: false, theme: 'dark',
        themeVariables: {
          primaryColor: '#1e3a5f', primaryTextColor: '#e2e8f0',
          primaryBorderColor: '#3b82f6', lineColor: '#6b7280',
          secondaryColor: '#1F2937', tertiaryColor: '#111827',
          background: '#0f172a', mainBkg: '#1e293b',
          fontSize: '14px', fontFamily: 'JetBrains Mono, monospace'
        }
      });
    },

    // ── NEXUS: 풀스크린 오버레이 열기 ──
    openNexus() {
      this.nexusOpen = true;
      setTimeout(() => {
        if (this.flowchart.mode === '3d' && !this.flowchart.graph3dLoaded) this.initNexus3D();
        if (this.flowchart.mode === 'canvas' && !this.flowchart.canvasLoaded) this.initNexusCanvas();
      }, 200);
    },

    // ══════════════════════════════════════════════ AGORA ══
    openAgora() {
      this.agoraOpen = true;
      this._connectAgoraSSE();
      this._loadAgoraStatus();
    },
    async _loadAgoraStatus() {
      try {
        const r = await fetch('/api/agora/status');
        if (!r.ok) return;
        const d = await r.json();
        if (d.session) {
          this.agora.sessionId = d.session.id;
          this.agora.status = d.session.status;
          this.agora.totalRounds = d.session.total_rounds || 0;
          this.agora.totalCost = d.session.total_cost_usd || 0;
          await this._loadAgoraIssues();
          await this._loadAgoraBook();
        }
      } catch(e) { console.warn('AGORA status:', e); }
    },
    async _loadAgoraIssues() {
      if (!this.agora.sessionId) return;
      try {
        const r = await fetch(`/api/agora/issues?session_id=${this.agora.sessionId}`);
        if (!r.ok) return;
        const d = await r.json();
        const issues = d.issues || [];
        const depthMap = {};
        issues.forEach(i => {
          if (!i.parent_id) { i._depth = 0; depthMap[i.id] = 0; }
          else { i._depth = (depthMap[i.parent_id] || 0) + 1; depthMap[i.id] = i._depth; }
        });
        this.agora.issues = issues;
        const active = issues.find(i => i.status === 'active');
        if (active) this.selectAgoraIssue(active.id);
        else if (issues.length > 0 && !this.agora.selectedIssueId) this.selectAgoraIssue(issues[issues.length-1].id);
      } catch(e) { console.warn('AGORA issues:', e); }
    },
    async selectAgoraIssue(issueId) {
      this.agora.selectedIssueId = issueId;
      try {
        const r = await fetch(`/api/agora/rounds/${issueId}`);
        if (!r.ok) return;
        const d = await r.json();
        this.agora.rounds = d.rounds || [];
        this.$nextTick(() => { const el = this.$refs.agoraLive; if (el) el.scrollTop = el.scrollHeight; });
      } catch(e) {}
      await this._loadAgoraDiff();
    },
    async _loadAgoraDiff() {
      if (!this.agora.sessionId) return;
      try {
        const r = await fetch(`/api/agora/paper/latest?session_id=${this.agora.sessionId}`);
        if (!r.ok) return;
        const d = await r.json();
        this.agora.diffHtml = d.diff_html || '';
      } catch(e) {}
    },
    async _loadAgoraBook() {
      if (!this.agora.sessionId) return;
      try {
        const r = await fetch(`/api/agora/book?session_id=${this.agora.sessionId}`);
        if (!r.ok) return;
        const d = await r.json();
        this.agora.bookChapters = d.chapters || [];
      } catch(e) {}
    },
    startAgora() { this.agora.showPaperInput = true; },
    async submitAgora() {
      const title = this.agora.inputTitle.trim();
      const paper = this.agora.inputPaper.trim();
      if (!title || !paper) return;
      this.agora.showPaperInput = false;
      try {
        const r = await fetch('/api/agora/start', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({title, paper_text: paper}),
        });
        const d = await r.json();
        this.agora.sessionId = d.session_id;
        this.agora.status = 'active';
        this.agora.totalRounds = 0;
        this.agora.totalCost = 0;
        this.agora.issues = [];
        this.agora.rounds = [];
        this.agora.diffHtml = '';
        this.agora.bookChapters = [];
      } catch(e) { console.error('AGORA start:', e); }
    },
    async pauseAgora() {
      if (!this.agora.sessionId) return;
      await fetch('/api/agora/pause', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({session_id: this.agora.sessionId}) });
      this.agora.status = 'paused';
    },
    async resumeAgora() {
      if (!this.agora.sessionId) return;
      await fetch('/api/agora/resume', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({session_id: this.agora.sessionId}) });
      this.agora.status = 'active';
    },
    _connectAgoraSSE() {
      if (this.agora.sseSource) return;
      try {
        const es = new EventSource('/api/agora/stream');
        this.agora.sseSource = es;
        es.addEventListener('agora', (e) => {
          try { this._handleAgoraEvent(JSON.parse(e.data)); } catch(err) {}
        });
        es.onerror = () => {
          es.close(); this.agora.sseSource = null;
          setTimeout(() => { if (this.agoraOpen) this._connectAgoraSSE(); }, 3000);
        };
      } catch(e) {}
    },
    _handleAgoraEvent(msg) {
      const t = msg.type, d = msg.data;
      if (t === 'agora_issue_created' || t === 'agora_derived_issue') { this._loadAgoraIssues(); }
      else if (t === 'agora_round_complete') {
        if (d.issue_id === this.agora.selectedIssueId) {
          this.agora.rounds.push(d);
          this.$nextTick(() => { const el = this.$refs.agoraLive; if (el) el.scrollTop = el.scrollHeight; });
        }
        this.agora.totalRounds = (this.agora.totalRounds || 0) + 1;
      }
      else if (t === 'agora_round_start' && d.issue_id !== this.agora.selectedIssueId) { this.selectAgoraIssue(d.issue_id); }
      else if (t === 'agora_consensus') { this._loadAgoraIssues(); }
      else if (t === 'agora_paper_updated') { this._loadAgoraDiff(); }
      else if (t === 'agora_chapter_written') { this._loadAgoraBook(); }
      else if (t === 'agora_cost_update') { this.agora.totalCost = d.total_cost_usd || 0; }
      else if (t === 'agora_debate_complete') { this.agora.status = 'completed'; this._loadAgoraIssues(); }
    },
    agoraIssueIcon(status) {
      return {pending:'⬜',active:'🔴',resolved:'✅',shelved:'🟡'}[status] || '⬜';
    },
    agoraSpeakerColor(speaker) {
      return {kodh:'text-blue-400',psb:'text-red-400',kdw:'text-purple-400'}[speaker] || 'text-gray-400';
    },
    agoraSpeakerName(speaker) {
      return {kodh:'고동희',psb:'박성범',kdw:'권대옥'}[speaker] || speaker;
    },
    // ══════════════════════════════════════════════ AGORA 끝 ══

    // ── NEXUS: 모드 전환 ──
    async onNexusModeChange(mode) {
      this.flowchart.mode = mode;
      await this.$nextTick();
      if (mode === '3d' && !this.flowchart.graph3dLoaded) await this.initNexus3D();
      if (mode === 'canvas' && !this.flowchart.canvasLoaded) await this.initNexusCanvas();
      if (mode === 'canvas') await this.loadCanvasList();
    },

    // ── NEXUS 3D: 시스템 전체 그래프 데이터 빌드 ──
    _buildSystemGraphData(agentNodes, agentEdges) {
      const CAT = {
        core:    { color: '#e879f9', label: 'CORTHEX' },
        tab:     { color: '#60a5fa', label: 'UI 탭' },
        division:{ color: '#a78bfa', label: '부서' },
        agent:   { color: '#34d399', label: '에이전트' },
        store:   { color: '#fbbf24', label: '저장소' },
        service: { color: '#fb923c', label: '외부서비스' },
        process: { color: '#f87171', label: '핵심프로세스' },
      };

      const nodes = [];
      const links = [];

      // ① 코어 허브
      nodes.push({ id: 'corthex_hq', name: 'CORTHEX HQ', category: 'core' });

      // ② UI 탭 (13개)
      const tabs = [
        { id: 't_home', name: '홈' }, { id: 't_command', name: '사령관실' },
        { id: 't_activity', name: '모니터링' }, { id: 't_trading', name: '투자' },
        { id: 't_history', name: '기록보관소' }, { id: 't_performance', name: '전력분석' },
        { id: 't_archive', name: '기밀문서' }, { id: 't_workflow', name: '자동화' },
        { id: 't_schedule', name: '크론기지' }, { id: 't_knowledge', name: '정보국' },
        { id: 't_sns', name: '통신국' }, { id: 't_nexus', name: 'NEXUS' },
        { id: 't_dashboard', name: '대시보드' },
      ];
      tabs.forEach(t => {
        nodes.push({ id: t.id, name: t.name, category: 'tab' });
        links.push({ source: 'corthex_hq', target: t.id });
      });

      // ③ 부서 (7개)
      const divisions = [
        { id: 'd_secretary', name: '비서실' }, { id: 'd_tech', name: '기술개발처' },
        { id: 'd_strategy', name: '전략기획처' }, { id: 'd_legal', name: '법무처' },
        { id: 'd_marketing', name: '마케팅처' }, { id: 'd_investment', name: '금융분석처' },
        { id: 'd_publishing', name: '콘텐츠처' },
      ];
      divisions.forEach(d => {
        nodes.push({ id: d.id, name: d.name, category: 'division' });
        links.push({ source: 'corthex_hq', target: d.id });
      });

      // ④ 에이전트 (API에서)
      const divMap = { secretary:'d_secretary', tech:'d_tech', strategy:'d_strategy',
                       legal:'d_legal', marketing:'d_marketing', investment:'d_investment',
                       publishing:'d_publishing' };
      agentNodes.forEach(a => {
        nodes.push({ id: a.id, name: a.name_ko || a.id, category: 'agent' });
        const div = a.division?.split('.')[0];
        if (divMap[div]) links.push({ source: divMap[div], target: a.id });
        else links.push({ source: 'corthex_hq', target: a.id });
      });
      agentEdges.forEach(e => links.push({ source: e.from, target: e.to }));

      // ⑤ 저장소
      const stores = [
        { id: 's_sqlite', name: 'SQLite DB' }, { id: 's_archive', name: '기밀문서 아카이브' },
        { id: 's_knowledge', name: '지식베이스' }, { id: 's_notion', name: '노션' },
      ];
      stores.forEach(s => {
        nodes.push({ id: s.id, name: s.name, category: 'store' });
        links.push({ source: 'corthex_hq', target: s.id });
      });

      // ⑥ 외부 서비스
      const services = [
        { id: 'x_anthropic', name: 'Anthropic API' }, { id: 'x_openai', name: 'OpenAI API' },
        { id: 'x_google', name: 'Google AI' }, { id: 'x_telegram', name: '텔레그램' },
        { id: 'x_kis', name: '한국투자증권' }, { id: 'x_github', name: 'GitHub' },
        { id: 'x_cloudflare', name: 'Cloudflare' }, { id: 'x_oracle', name: 'Oracle Cloud' },
      ];
      services.forEach(s => {
        nodes.push({ id: s.id, name: s.name, category: 'service' });
        links.push({ source: 'corthex_hq', target: s.id });
      });

      // ⑦ 핵심 프로세스
      const processes = [
        { id: 'p_routing', name: '지능형 라우팅' }, { id: 'p_qa', name: 'QA 검수' },
        { id: 'p_rework', name: '재작업 루프' }, { id: 'p_kelly', name: '켈리 크라이터리온' },
        { id: 'p_soul', name: '에이전트 소울' },
      ];
      processes.forEach(p => {
        nodes.push({ id: p.id, name: p.name, category: 'process' });
        links.push({ source: 'corthex_hq', target: p.id });
      });

      return { nodes, links, CAT };
    },

    // ── NEXUS 3D: 초기화 (방사형 계층 + 라벨 오버레이 + 화살표) ──
    async initNexus3D() {
      try {
        await _loadScript(_CDN.forcegraph3d);
        const r = await fetch('/api/architecture/hierarchy');
        if (!r.ok) throw new Error('시스템 데이터 로드 실패');
        const { nodes: agentNodes = [], edges: agentEdges = [] } = await r.json();

        const { nodes, links, CAT } = this._buildSystemGraphData(agentNodes, agentEdges);
        const SIZES = { core: 30, division: 15, tab: 8, agent: 6, store: 10, service: 9, process: 10 };
        const graphNodes = nodes.map(n => ({
          id: n.id, name: n.name, category: n.category,
          color: CAT[n.category]?.color || '#6b7280',
          val: SIZES[n.category] || 5,
        }));
        const graphLinks = links.map(l => ({ source: l.source, target: l.target }));

        // DOM 준비 + 컨테이너 크기 확인
        let el = document.getElementById('nexus-3d');
        let retries = 0;
        while ((!el || el.clientWidth === 0) && retries < 10) {
          await new Promise(resolve => setTimeout(resolve, 200));
          el = document.getElementById('nexus-3d');
          retries++;
        }
        if (!el || el.clientWidth === 0 || typeof ForceGraph3D === 'undefined') throw new Error('3D 렌더러 초기화 실패');

        const Graph = ForceGraph3D()(el)
          .graphData({ nodes: graphNodes, links: graphLinks })
          .backgroundColor('#060a14')
          // ★ 방사형 계층 구조 (허브 중심 → 바깥 확산)
          .dagMode('radialout')
          .dagLevelDistance(50)
          // 노드
          .nodeColor(n => n.color)
          .nodeVal(n => n.val)
          .nodeOpacity(0.85)
          .nodeLabel(n => `${n.name}\n(${CAT[n.category]?.label || n.category})`)
          // ★ 연결선: 두껍고 + 색깔 + 화살표 + 흐르는 입자
          .linkColor(link => {
            const srcId = typeof link.source === 'object' ? link.source.id : link.source;
            const src = graphNodes.find(n => n.id === srcId);
            return (src?.color || '#ffffff') + '50';
          })
          .linkWidth(1.5)
          .linkOpacity(0.5)
          .linkDirectionalArrowLength(5)
          .linkDirectionalArrowRelPos(0.85)
          .linkDirectionalArrowColor(link => {
            const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
            const tgt = graphNodes.find(n => n.id === tgtId);
            return (tgt?.color || '#ffffff') + '90';
          })
          .linkDirectionalParticles(2)
          .linkDirectionalParticleWidth(1.5)
          .linkDirectionalParticleSpeed(0.005)
          .linkDirectionalParticleColor(link => {
            const srcId = typeof link.source === 'object' ? link.source.id : link.source;
            const src = graphNodes.find(n => n.id === srcId);
            return src?.color || '#ffffff';
          })
          // 클릭
          .onNodeClick(n => {
            if (n.category === 'agent') {
              this.nexusOpen = false;
              this.switchTab('command');
              this.$nextTick(() => { this.inputText = `@${n.id} `; });
            }
          })
          .d3AlphaDecay(0.03)
          .d3VelocityDecay(0.4)
          .warmupTicks(120)
          .cooldownTicks(300);

        // ★ HTML 오버레이 라벨 (3D 위에 텍스트 표시)
        const labelBox = document.createElement('div');
        labelBox.id = 'nexus-3d-labels';
        labelBox.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;overflow:hidden;z-index:10;';
        el.style.position = 'relative';
        el.appendChild(labelBox);

        const labelEls = {};
        const fontSizes = { core: '15px', division: '12px', store: '11px', service: '11px', process: '11px', tab: '10px', agent: '9px' };
        graphNodes.forEach(n => {
          const lbl = document.createElement('div');
          lbl.textContent = n.name;
          lbl.style.cssText = `position:absolute;left:0;top:0;color:${n.color};font-size:${fontSizes[n.category] || '9px'};font-weight:${n.category === 'core' ? '800' : '600'};font-family:Pretendard,system-ui,sans-serif;white-space:nowrap;pointer-events:none;text-shadow:0 0 6px #060a14,0 0 12px #060a14,0 1px 3px rgba(0,0,0,0.9);opacity:0;will-change:transform;`;
          labelBox.appendChild(lbl);
          labelEls[n.id] = lbl;
        });

        // 프레임마다 라벨 위치 갱신
        let animId;
        const updateLabels = () => {
          if (!this.nexusOpen || !this.flowchart.graph3dLoaded) { animId = 0; return; }
          const w = el.clientWidth, h = el.clientHeight;
          graphNodes.forEach(n => {
            const le = labelEls[n.id];
            if (!le || n.x === undefined) return;
            const sc = Graph.graph2ScreenCoords(n.x, n.y, n.z);
            if (sc.x > -50 && sc.x < w + 50 && sc.y > -50 && sc.y < h + 50) {
              le.style.transform = `translate(${sc.x}px,${sc.y - (n.val || 5) * 1.1}px) translate(-50%,-100%)`;
              le.style.opacity = '1';
            } else {
              le.style.opacity = '0';
            }
          });
          animId = requestAnimationFrame(updateLabels);
        };

        // 카메라 줌아웃 + 라벨 시작
        setTimeout(() => {
          Graph.cameraPosition({ z: 500 });
          updateLabels();
        }, 800);

        this.flowchart.graph3dInstance = Graph;
        this.flowchart.graph3dLabelsAnimId = animId;
        this.flowchart.graph3dLoaded = true;
      } catch (e) {
        this.showToast('3D 뷰 오류: ' + e.message, 'error');
        console.error('initNexus3D:', e);
      }
    },

    // ── NEXUS 캔버스: 초기화 (dblclick 노드 이름 편집 포함) ──
    async initNexusCanvas() {
      try {
        await Promise.all([_loadScript(_CDN.drawflow), _loadCSS(_CDN.drawflowcss)]);
        await this.$nextTick();
        const el = document.getElementById('nexus-canvas');
        if (!el || typeof Drawflow === 'undefined') throw new Error('캔버스 초기화 실패');
        const editor = new Drawflow(el);
        editor.reroute = true;
        editor.reroute_fix_curvature = true;
        editor.start();
        // 변경 감지
        ['nodeCreated','connectionCreated','nodeRemoved','connectionRemoved','nodeMoved'].forEach(ev => {
          editor.on(ev, () => { this.flowchart.canvasDirty = true; });
        });
        // 더블클릭 노드 이름 편집
        el.addEventListener('dblclick', (e) => {
          const nodeEl = e.target.closest('.nexus-node');
          if (!nodeEl) return;
          const current = nodeEl.textContent.trim();
          const input = document.createElement('input');
          input.type = 'text';
          input.value = current;
          input.style.cssText = 'background:rgba(0,0,0,0.6);color:#fff;border:1px solid #8b5cf6;border-radius:4px;padding:2px 6px;font-size:12px;width:100%;text-align:center;outline:none;font-family:Pretendard,sans-serif';
          nodeEl.textContent = '';
          nodeEl.appendChild(input);
          input.focus();
          input.select();
          const commit = () => {
            const val = input.value.trim() || current;
            nodeEl.textContent = val;
            this.flowchart.canvasDirty = true;
          };
          input.addEventListener('blur', commit, { once: true });
          input.addEventListener('keydown', (ke) => {
            if (ke.key === 'Enter') { ke.preventDefault(); input.blur(); }
            if (ke.key === 'Escape') { input.value = current; input.blur(); }
          });
        });
        this.flowchart.canvasEditor = editor;
        this.flowchart.canvasLoaded = true;
      } catch (e) {
        this.showToast('캔버스 오류: ' + e.message, 'error');
        console.error('initNexusCanvas:', e);
      }
    },

    // ── NEXUS 캔버스: 파일 목록 ──
    async loadCanvasList() {
      try {
        const r = await fetch('/api/knowledge');
        if (!r.ok) return;
        const data = await r.json();
        this.flowchart.canvasItems = (data.files || []).filter(f => f.folder === 'flowcharts' && f.name.endsWith('.json'));
      } catch(e) { console.error('loadCanvasList:', e); }
    },

    // ── NEXUS 캔버스: 팔레트 노드 추가 ──
    addCanvasNode(type) {
      const editor = this.flowchart.canvasEditor;
      if (!editor) return;
      const labels = { agent:'에이전트', system:'시스템', api:'외부 API', decide:'결정 분기', start:'시작', end:'종료', note:'메모' };
      const colors = { agent:'#8b5cf6', system:'#3b82f6', api:'#059669', decide:'#f59e0b', start:'#22c55e', end:'#ef4444', note:'#6b7280' };
      const html = `<div class="nexus-node" style="background:${colors[type]||'#6b7280'};padding:6px 12px;border-radius:8px;color:#fff;font-size:12px;font-family:Pretendard,sans-serif;min-width:80px;text-align:center;cursor:move">${labels[type]||type}</div>`;
      editor.addNode(type, 1, 1, 200, 200, type, { label: labels[type] }, html);
    },

    // ── NEXUS 캔버스: 저장 ──
    async saveNexusCanvas() {
      if (!this.flowchart.canvasEditor) return;
      let name = (this.flowchart.canvasName || '').trim();
      if (!name) {
        const input = prompt('캔버스 이름을 입력하세요:');
        if (!input || !input.trim()) return;
        name = input.trim();
        this.flowchart.canvasName = name;
      }
      const filename = name.endsWith('.json') ? name : name + '.json';
      try {
        const data = this.flowchart.canvasEditor.export();
        const r = await fetch('/api/knowledge', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folder: 'flowcharts', filename, content: JSON.stringify(data, null, 2) })
        });
        if (!r.ok) throw new Error('저장 실패');
        this.flowchart.canvasDirty = false;
        this.showToast('캔버스 저장됐습니다', 'success');
        await this.loadCanvasList();
      } catch (e) { this.showToast('저장 실패: ' + e.message, 'error'); }
    },

    // ── NEXUS 캔버스: 불러오기 ──
    async loadNexusCanvas(item) {
      if (!this.flowchart.canvasEditor) return;
      try {
        const r = await fetch(`/api/knowledge/${item.folder}/${item.name}`);
        if (!r.ok) throw new Error('불러오기 실패');
        const data = await r.json();
        const parsed = JSON.parse(data.content || '{}');
        this.flowchart.canvasEditor.import(parsed);
        this.flowchart.canvasName = item.name.replace('.json', '');
        this.flowchart.canvasDirty = false;
        this.showToast(`"${item.name}" 불러왔습니다`, 'success');
      } catch (e) { this.showToast('불러오기 실패: ' + e.message, 'error'); }
    },

    // ── NEXUS 캔버스: 초기화 ──
    clearNexusCanvas() {
      if (this.flowchart.canvasEditor) {
        this.flowchart.canvasEditor.clearModuleSelected();
        this.flowchart.canvasEditor.load({ drawflow: { Home: { data: {} } } });
        this.flowchart.canvasDirty = false;
        this.flowchart.canvasName = '';
      }
    },
  };
}
