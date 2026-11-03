/* Lightweight bilingual UI translation for the no-build Vue frontend. */
(() => {
  const STORAGE_KEY = 'arena-language';
  const ATTRIBUTES = ['title', 'aria-label', 'placeholder', 'aria-valuetext'];
  const SKIP_SELECTOR = [
    '.projection__body',
    '.parallel-paper__body',
    '.review-answer__body',
    '.review-record__synthesis p',
    '.review-record__plans .speech-block__body',
    '.review-record-card > p',
    '.speech-block__body',
    '.record-final .speech-block__para',
    '.record-final .final-divergence p',
    '.record-final .final-premise p',
    '.claim-ledger__text',
    '.claim-node__body b',
    '.ledger__topic',
    '.compare-col__topic',
    '.compare-picker__list b',
    '.roster__name',
    '.roster__model',
    '.seat__name b',
    '.projection__head b',
    '.projection__final-name',
    '.parallel-paper__head b',
    '.record-final h2',
    '.ledger__winner',
    '.model-profile th[scope="row"]',
    '.claim-ledger__who',
    '.claim-ledger__challengers',
  ].join(',');

  const exact = {
    "Agent Arena · 多智能体辩论赛": "Agent Arena · Multi-model Debate",
    "跳到主要内容": "Skip to main content",
    "回到登记页": "Back to setup",
    "主导航": "Main navigation",
    "切换到中文": "Switch to Chinese",
    "关闭声音": "Mute sound",
    "打开声音": "Enable sound",
    "切换亮色模式": "Switch to light mode",
    "切换深色模式": "Switch to dark mode",
    "亮色": "Light",
    "深色": "Dark",
    "声音": "Sound",
    "静音": "Muted",
    "登记": "Setup",
    "会场": "Arena",
    "记录": "Record",
    "档案": "Archive",
    "模型": "Models",
    "布置一场自定义赛": "Set up a custom match",
    "布置一场方案评审": "Set up a solution review",
    "多个模型独立给方案，独立裁判匿名评分，最后给出推荐与整合建议。": "Models submit independent plans, an independent judge scores them anonymously, then recommends and integrates.",
    "比赛模式": "Match mode",
    "方案评审": "Solution review",
    "自定义模式": "Custom mode",
    "定下命题与胜出标准，挑选阵容。赛制仍按淘汰推进。": "Set the topic and win condition, then choose the lineup. The format still advances by elimination.",
    "各自独立作答 · 匿名裁判评分 · 推荐与整合": "Independent answers · anonymous judging · recommendation and synthesis",
    "约 N+2 次调用 · 1–3 分钟": "About N+2 calls · 1–3 minutes",
    "逐轮交锋 · 自定义胜出标准 · 最终总结": "Round-by-round debate · custom win condition · final synthesis",
    "深挖": "Deep dive",
    "独立裁判": "Independent judge",
    "选择不参赛的模型": "Choose a non-competing model",
    "没有可用裁判模型": "No judge model available",
    "裁判不提交方案，只看到乱序后的匿名方案。": "The judge submits no plan and only sees shuffled anonymous plans.",
    "需先在模型页添加一个不参赛的裁判模型。": "Add a non-competing judge model on the Models page first.",
    "分配差异化视角": "Assign distinct perspectives",
    "成本 / 增长 / 风险 / 体验 / 技术": "Cost / growth / risk / experience / technology",
    "每份方案分别侧重成本、增长、风险、体验或技术，避免答案同质化":
      "Each plan focuses on cost, growth, risk, experience, or technology to avoid look-alike answers",
    "单次调用限时": "Call timeout",
    "评审流程": "Review flow",
    "独立作答": "Independent answers",
    "参赛模型并行提交六段式方案": "Participants submit six-part plans in parallel",
    "匿名评审": "Anonymous review",
    "裁判按四项维度评分与排名": "The judge scores and ranks four dimensions",
    "推荐整合": "Recommendation & synthesis",
    "给出理由、风险和执行步骤": "Reasons, risks, and execution steps",
    "参赛模型独立提交方案": "Participants are submitting plans independently",
    "独立裁判匿名评审": "The independent judge is reviewing anonymously",
    "生成推荐与整合建议": "Generating recommendation and synthesis",
    "评审完成": "Review complete",
    "等待评审": "Waiting for review",
    "评审舱待命": "Review chamber standing by",
    "先选择参赛方案与独立裁判，再开始评审。": "Choose participants and an independent judge before starting.",
    "布置评审": "Set up review",
    "未分配视角": "No perspective",
    "结构缺项": "Missing structure",
    "等待提交方案": "Waiting for plan",
    "模型正在输出方案": "Model is writing the plan",
    "方案已提交": "Plan submitted",
    "缺席": "Absent",
    "已提交": "Submitted",
    "作答中": "Answering",
    "方案对比": "Plan comparison",
    "未推荐说明": "Why not recommended",
    "仅限本模式内比较": "Comparable within this mode only",
    "方案评审 · 独立评分口径": "Solution review · independent scoring scale",
    "查看全部方案全文": "Show all plan texts",
    "推荐与整合": "Recommendation & synthesis",
    "推荐": "Recommended",
    "全部模式": "All modes",
    "按模式筛选": "Filter by mode",
    "每份方案、四个维度的评分、推荐与整合建议都按原样保留。": "Every plan, four-dimension score, recommendation, and synthesis is preserved.",
    "方案 ": "Plans ",
    "定下命题，挑选阵容，调整赛制。剩下的交给议事舱。": "Choose the question, line-up, and rules. The council handles the rest.",
    "参赛席位": "Seats",
    "命题": "Question",
    "写下一个有分歧、能被证据推进的问题。": "Write a question with real disagreement and room for evidence.",
    "⌘↵ 开赛": "⌘↵ Start",
    "今天让它们争论什么？": "What should they debate today?",
    "写下一个值得争论的命题": "Write a question worth debating",
    "背景与约束": "Context & constraints",
    "背景": "Context",
    "模型们需要的共同背景，例如业务现状、已有数据": "Shared context such as current operations or available data",
    "约束": "Constraints",
    "删除约束": "Delete constraint",
    "加一条约束": "Add a constraint",
    "新增约束": "New constraint",
    "添加": "Add",
    "评判标准": "Criteria",
    "删除标准": "Delete criterion",
    "加一条标准": "Add a criterion",
    "新增评判标准": "New criterion",
    "标准逐条参与投票评分，写几条，评分矩阵就有几维。": "Each criterion becomes a scoring dimension in every vote.",
    "参赛名册": "Line-up",
    "已选": "selected",
    "登记模型": "Register model",
    "＋ 登记模型": "+ Register model",
    "席位": "Seat",
    "形象": "Avatar",
    "名称": "Name",
    "模型 ID": "Model ID",
    "参赛": "In match",
    "操作": "Actions",
    "正在读取登记册…": "Loading model registry…",
    "取消参赛：": "Remove from match: ",
    "加入参赛：": "Add to match: ",
    "修改": "Edit",
    "删除": "Delete",
    "还没有登记模型。至少登记两个，才能开一场。": "No models yet. Register at least two to start a match.",
    "赛制设置": "Match rules",
    "决定胜负口径与比赛边界": "Choose the scoring rule and match boundaries",
    "胜负规则": "Decision rule",
    "胜出标准": "Win condition",
    "必填": "Required",
    "投票至最后一人": "Vote until one remains",
    "系统按淘汰制推进；该标准会写入每轮发言、投票和最终总结。": "The match advances by elimination; this condition is included in every speech, vote, and final summary.",
    "恢复默认": "Restore default",
    "比赛规则": "Match rule",
    "淘汰制": "Elimination",
    "评选制": "Selection",
    "投给观点最正确的一方，票少者出局": "Vote for the strongest case; the fewest votes is eliminated",
    "投给观点最站不住的一方，票多者出局": "Vote for the weakest case; the most votes is eliminated",
    "发言方式": "Speech mode",
    "并行生成": "Parallel",
    "逐个实时": "Live sequential",
    "同时生成，完成后全员观点同屏展开": "Generate together, then reveal every case on one board",
    "逐个实时生成，能看到每个模型的思考过程": "Generate one at a time with live streamed output",
    "单次发言限时": "Speech timeout",
    "单次发言限时秒数": "Speech timeout in seconds",
    "秒": "sec",
    "赛程预览": "Match flow",
    "赛程规则": "Match flow",
    "独立开场": "Opening round",
    "首轮保留分歧，不判收敛": "Keep disagreement; no consensus check in round one",
    "交叉裁决": "Cross-examination",
    "第 2 轮起投票，逐轮淘汰": "Voting starts in round two; one exit per round",
    "完整收束": "Full conclusion",
    "不因等待或用量中途停止": "Never stop early because of waiting time or usage",
    "位参赛": "participants",
    "至少选择 2 位参赛模型": "Select at least two models",
    "预览一场": "Preview match",
    "开始比赛": "Start match",
    "未命名赛程": "Untitled match",
    "确认停止": "Confirm stop",
    "停止本场": "Stop match",
    "实时会议室": "Live room",
    "投票流向": "Vote flow",
    "实时投票流向": "Live vote flow",
    "已收票关系": "Recorded ballots",
    "票": "votes",
    "TIEBREAK / 加赛进行中": "TIEBREAK / in progress",
    "平票模型正在补充发言，实时内容见下方。": "Tied models are adding their tiebreak speeches; live output appears below.",
    "评审正在同时投票，票数汇总后立即公布。": "Judges are voting concurrently; results publish as soon as they settle.",
    "本轮加赛仍然平票，正在准备下一次加赛。": "The tiebreak is still tied; another tiebreak is being prepared.",
    "正在汇总加赛结果。": "Summarizing the tiebreak result.",
    "仍平票 · 即将继续加赛": "Still tied · another tiebreak is next",
    "等待下一场比赛": "Waiting for the next match",
    "开赛后，模型发言、思考进度和加赛状态都会在这里实时出现。": "Once a match starts, speeches, progress, and tiebreaks appear here live.",
    "并行发言同屏看板": "Parallel speech board",
    "已生成": "generated",
    "生成完成，等待统一公开": "Generation complete; waiting for reveal",
    "所有席位同屏展开；单卡完成不会再遮住其他人的观点。": "All seats stay on one board; one completed card never hides the others.",
    "正在整理观点": "organizing the argument",
    "已归档": "Archived",
    "等待服务商响应": "Waiting for provider",
    "议事舱待命": "Council standing by",
    "灯还没亮。先登记模型，写下命题，然后开始比赛。": "The lights are off. Register models, choose a question, then start.",
    "布置比赛": "Set up match",
    "管理模型": "Manage models",
    "本轮为并行生成，正在同屏展开": "Parallel round: revealing all speakers together",
    "比赛记录": "Match record",
    "每一轮发言、每一张选票、每一次出局，都按原样留着。": "Every speech, ballot, and elimination is preserved.",
    "再赛一场": "Run again",
    "按人": "By speaker",
    "全部": "All",
    "轮次": "Rounds",
    "全部轮次": "All rounds",
    "人存活": "active",
    "结束方式": "Outcome",
    "最终总结": "Final decision",
    "保留的分歧": "Unresolved disagreement",
    "未解决": "Unresolved",
    "前提": "Premises",
    "当前筛选下没有记录。": "No records match this filter.",
    "第 2 轮起投票，逐轮淘汰": "Voting starts in round two",
    "未完成：": "Incomplete: ",
    "观点": "View",
    "点评": "Critique",
    "本轮直接出局": "Eliminated directly",
    "转任评审": "moved to judging panel",
    "已决出": "Decided",
    "仍平票": "Still tied",
    "移出投票人：": "Removed voters: ",
    "未投": "No vote",
    "评审": "Judge",
    "未说明理由": "No reason provided",
    "收起": "Collapse",
    "展开": "Expand",
    "本轮评分": "Round scores",
    "完整矩阵见战报 JSON": "Full score matrix is available in the transcript JSON",
    "首轮只发言，不投票。": "Round one only contains speeches.",
    "本轮尚无投票记录。": "No votes recorded for this round.",
    "还没有可阅读的比赛记录": "No match record to read yet",
    "先在登记页定下命题与阵容，完成一场比赛后，这里会保留完整发言和选票。": "Set a question and line-up, finish a match, and its speeches and ballots will appear here.",
    "去登记": "Go to setup",
    "主张台账视图": "Claim ledger view",
    "台账": "Ledger",
    "谱系": "Lineage",
    "历史提问": "Past questions",
    "每一场争论都保留完整发言、投票与裁决。": "Every debate keeps its speeches, votes, and decision.",
    "档案视图": "Archive view",
    "对比": "Compare",
    "读取中…": "Loading…",
    "刷新档案": "Refresh archive",
    "一次最多对比 3 场": ", up to three matches at once",
    "先选两场同一命题的比赛，再开始对比": "Select two matches on the same question to compare",
    "查看这场": "Open match",
    "模型画像（全部历史）": "Model profiles (all history)",
    "登场": "Matches",
    "胜率": "Win rate",
    "时间": "Time",
    "时长": "Duration",
    "胜者": "Winner",
    "复用这场预设": "Reuse this preset",
    "比赛尚未归档，暂不能再赛": "Match has not been archived yet",
    "再赛": "Reuse",
    "查看": "Open",
    "还没有存下任何一场争论。登记两个模型，写下一个命题，就能开始第一场。": "No debates saved yet. Register two models and write a question to begin.",
    "登记与管理": "Register & manage",
    "机器人形象由模型信息生成，登记后会自动拥有自己的全息形象。": "Each model gets a deterministic holographic avatar from its identity.",
    "修改模型": "Edit model",
    "登记新模型": "Register model",
    "显示名称": "Display name",
    "例如：GPT-5": "e.g. GPT-5",
    "测试中…": "Testing…",
    "自动取名": "Suggest name",
    "留空则保留原 Key": "Leave blank to keep the existing key",
    "例如：gpt-5": "e.g. gpt-5",
    "无": "None",
    "审计员": "Auditor",
    "务实派": "Pragmatist",
    "反方": "Opposition",
    "红队": "Red team",
    "归纳者": "Synthesizer",
    "系统提示词（选填）": "System prompt (optional)",
    "给模型的额外角色或回答要求": "Extra role or response instructions",
    "温度（选填）": "Temperature (optional)",
    "例如：0.7": "e.g. 0.7",
    "保存中…": "Saving…",
    "保存修改": "Save changes",
    "换一个外观": "Reroll avatar",
    "全部模型": "All models",
    "修改模型配置": "Edit model configuration",
    "登记参赛大模型": "Register a debate model",
    "关闭": "Close",
    "给这个模型的额外角色或回答要求": "Extra role or response instructions for this model",
    "取消": "Cancel",
    "待命": "Standby",
    "等待开始": "Waiting to start",
    "同时投票": "concurrent voting",
    "正在同时投票": "Concurrent voting in progress",
    "加赛发言": "Tiebreak speech",
    "加赛投票": "Tiebreak vote",
    "最终裁决": "Final decision",
    "出局": "Eliminated",
    "正在发言": "Speaking",
    "正在思考": "Thinking",
    "胜者": "Winner",
    "在场": "Active",
    "票数最低": "lowest votes",
    "另有": "plus",
    "位参赛者，点击展开": "participants; click to expand",
    "独立发言": "Opening statement",
    "综合发言": "Response",
    "中止": "Stopped",
    "保留已完成的全部轮次与发言。": "All completed rounds and speeches are preserved.",
    "胜出": "Winner",
    "完成投票裁决；比赛过程中曾出现立场趋同。": "Completed voting and decision; positions converged during the match.",
    "比赛完成全部必要轮次。": "All required rounds are complete.",
    "收敛": "Converged",
    "立场趋于一致": "Positions converged",
    "收敛只作为赛况读数，不跳过投票与裁决。": "Consensus is a readout only; voting and decisions still run.",
    "进行中": "Running",
    "中断": "Interrupted",
    "已停止": "Stopped",
    "完成": "Complete",
    "请求失败": "Request failed",
    "先填写 Base URL 和模型 ID": "Enter Base URL and Model ID first",
    "先填写 API Key": "Enter the API key first",
    "正在连接模型并生成名称…": "Connecting to the model and generating a name…",
    "连通性正常，已生成显示名称。": "Connection OK. Display name generated.",
    "取名失败：": "Name suggestion failed: ",
    "删除失败：": "Delete failed: ",
    "历史记录读取失败：": "Could not load history: ",
    "先写一个命题": "Write a question first",
    "比赛中": "Live",
    "正在组建参赛阵容…": "Building the line-up…",
    "正在连接参赛大模型": "Connecting to the debate models",
    "启动失败": "Failed to start",
    "这场没有可停止的运行": "This match has no active run",
    "正在停止，保留已完成轮次": "Stopping; completed rounds will be preserved",
    "停止失败：": "Stop failed: ",
    "本轮直接出局": "Eliminated directly",
    "重连中": "Reconnecting",
    "事件流断开，正在自动重连…": "Event stream disconnected; reconnecting automatically…",
    "参赛阵容已就绪": "Line-up ready",
    "正在实时输出": "Streaming live",
    "并行实时输出中": "Streaming in parallel",
    "调用失败": "Call failed",
    "已停止 · 保留已完成轮次": "Stopped; completed rounds preserved",
    "用户中止": "Stopped by user",
    "比赛出错了": "The match hit an error",
    "出错": "Error",
    "失败": "Failed",
    "已结束": "Finished",
    "比赛结束，可以回看全过程": "Match complete. The full record is available.",
    "比赛结束": "Match complete",
    "接续中": "Reconnecting",
    "正在接回比赛现场…": "Reconnecting to the live arena…",
    "正在接回比赛现场": "Reconnecting to the live arena",
    "演示档案没有可复用的真实模型配置": "Demo archives have no real model presets to reuse",
    "部分参赛模型": "some participants",
    "历史回放": "History",
    "历史提问回放": "History replay",
    "历史战报已载入": "Transcript loaded",
    "历史回放完成": "Replay ready",
    "历史回放失败：": "Could not load replay: ",
    "本轮投票": "Round vote",
    "采纳": "Adopted",
    "已否定": "Rejected",
    "未决": "Open",
    "主张台账": "Claim ledger",
    "主张": "Claim",
    "提出": "By",
    "轮": "Round",
    "被谁挑战": "Challenged by",
    "结局": "Outcome",
    "挑战": "challenge",
    "还没有被挑战过的主张。": "No claims have been challenged yet.",
    "已收敛": "Converged",
    "分歧大": "High divergence",
    "立场离散": "Stance spread",
    "均分": "Avg",
    "论证": "Argument",
    "证据": "Evidence",
    "可执行": "Execution",
    "增量": "Insight",
    "机器人头像": "Robot avatar",
    "极差": "Range",
    "收敛阈值": "Consensus threshold",
    "已投": "Voted",
    "正在理解命题": "Understanding the question",
    "正在组织论证": "Structuring the argument",
    "正在生成回应": "Generating the response",
    "已等待": "Waiting",
    "已接收": "Received",
    "字符": "chars",
    "已展开": "Revealed",
    "待公开": "Waiting for reveal",
    "思考中": "Thinking",
    "已完成": "Complete",
    "实时输出中": "Streaming",
    "结论": "Conclusion",
    "未命名赛程": "Untitled match",
    "平票加赛": "Tiebreak speech",
    "最终总结": "Final summary",
    "正在整理最终结论": "Preparing the final decision",
    "技术性退赛": "technical exit",
    "最终存活": "final survivor",
    "并行生成中，完成后全员观点同屏展开": "Generating in parallel; all cases reveal together when ready",
    "同屏展开": "Revealing",
    "继续完成投票裁决": "continuing to voting and decision",
    "共": "Total",
    "票": "votes",
    "挑战": "challenge",
  };

  const rules = [
    [/本轮上限\s*(\d+)\s*轮；收敛读数只展示赛况，不跳过裁决。/g,
      "Up to $1 rounds; consensus is a read-only signal and never skips voting."],
    [/第\s*(\d+)\s*轮 · 第\s*(\d+)\s*次加赛投票完成/g,
      "Round $1 · tiebreak $2 vote complete"],
    [/第\s*(\d+)\s*轮 · (.*?)\s*平票加赛/g, "Round $1 · $2 tiebreak"],
    [/第\s*(\d+)\s*轮 · (.*?)：(\d+)\s*位投票者/g, "Round $1 · $2: $3 voters"],
    [/第\s*(\d+)\s*轮 · (.*?)位并行生成中/g, "Round $1 · $2 generating in parallel"],
    [/同屏展开 · 第\s*(\d+)\/(\d+)\s*位/g, "Revealing · $1/$2"],
    [/第\s*(\d+)\s*轮准备发言/g, "Round $1 ready"],
    [/第\s*(\d+)\s*轮出局/g, "Eliminated in round $1"],
    [/第\s*(\d+)\s*轮/g, "Round $1"],
    [/第\s*(\d+)\s*次加赛/g, "Tiebreak $1"],
    [/(\d+)\s*位同屏发言/g, "$1 speakers on one board"],
    [/(\d+)\s*\/\s*(\d+) 已选/g, "$1 / $2 selected"],
    [/(\d+)\s*\/\s*(\d+) 已生成/g, "$1 / $2 generated"],
    [/(\d+)\s*个/g, "$1 models"],
    [/(\d+)\s*位参赛/g, "$1 participants"],
    [/(\d+)\s*人存活/g, "$1 active"],
    [/在场\s*(\d+)\s*人/g, "$1 active"],
    [/(\d+)\s*位投票者正在判断本轮发言/g, "$1 voters are judging this round"],
    [/(.*?)正在组织(独立发言|综合发言|平票加赛|最终总结)/g, "$1 is preparing $2"],
    [/(.*?)发言完成，用时\s*(\d+(?:\.\d+)?)\s*秒/g, "$1 speech complete in $2s"],
    [/(.*?)中，等待模型返回/g, "$1; waiting for provider"],
    [/(.*?)中 · 模型正在逐字返回/g, "$1 · streaming output"],
    [/(.*?)正在实时输出/g, "$1 is streaming live"],
    [/(\d+)投票：/g, "$1 vote: "],
    [/加赛投票：/g, "tiebreak vote: "],
    [/加赛投票/g, "tiebreak vote"],
    [/加赛发言/g, "tiebreak speech"],
    [/独立发言/g, "opening statement"],
    [/综合发言/g, "response"],
    [/正在判断本轮发言/g, "are judging this round"],
    [/(\d+)\s*位投票者/g, "$1 voters"],
    [/(\d+)\s*位并行生成中/g, "$1 generating in parallel"],
    [/(\d+)\s*位正在实时输出/g, "$1 streaming live"],
    [/(\d+)\s*场/g, "$1 matches"],
    [/(\d+)\s*票/g, "$1 votes"],
    [/已投\s*(\d+)\/(\d+)\s*·\s*已等待\s*(\d+)s\s*·\s*同时投票/g,
      "Voted $1/$2 · $3s elapsed · concurrent"],
    [/已投\s*(\d+)\/(\d+)\s*·\s*同时投票/g, "Voted $1/$2 · concurrent"],
    [/已等待\s*(\d+(?:\.\d+)?)\s*(?:s|秒)?/g, "Waiting $1s"],
    [/已接收\s*([\d,]+)\s*字符/g, "Received $1 chars"],
    [/([\d,]+)\s*字/g, "$1 chars"],
    [/用时\s*(\d+(?:\.\d+)?)\s*秒/g, "in $1s"],
    [/淘汰制/g, "Elimination"],
    [/评选制/g, "Selection"],
    [/限时/g, "Timeout"],
    [/最终总结/g, "Final summary"],
    [/投票与裁决/g, "Voting & decision"],
    [/存活者\s*(\d+)\s*(?:票|votes)\s*·\s*评审\s*(\d+)\s*(?:票|votes)（权重\s*([\d.]+)）/g,
      "Active $1 votes · judges $2 votes (weight $3)"],
    [/本轮直接出局/g, "eliminated directly"],
    [/转任评审/g, "moved to judging panel"],
    [/出局/g, "Eliminated"],
    [/胜出/g, "Winner"],
    [/采纳/g, "Adopted"],
    [/已否定/g, "Rejected"],
    [/未决/g, "Open"],
    [/权重/g, "weight"],
    [/评审/g, "judges"],
    [/正在理解命题/g, "Understanding the question"],
    [/正在组织论证/g, "Structuring the argument"],
    [/正在生成回应/g, "Generating the response"],
    [/审计员/g, "Auditor"],
    [/务实派/g, "Pragmatist"],
    [/反方/g, "Opposition"],
    [/红队/g, "Red team"],
    [/归纳者/g, "Synthesizer"],
    [/立场/g, "Stance"],
    [/思考中\s*(\d+)\s*s/g, "Thinking $1s"],
    [/实时输出\s*(\d+)\s*s/g, "Streaming $1s"],
    [/已进行\s*(\d+)\s*s/g, "Running $1s"],
    [/第\s*(\d+)\/(\d+)\s*位/g, "$1/$2"],
    [/极差\s*(\d+)，收敛阈值\s*(\d+)/g, "Range $1, threshold $2"],
    [/立场趋同（极差\s*([\d.]+)），继续完成投票裁决/g,
      "Positions converged (range $1); voting and decision continue"],
    [/正在组织(独立发言|综合发言|平票加赛|最终总结)/g, "Preparing $1"],
    [/正在判断谁的发言最站得住/g, "is judging the strongest case"],
    [/投票格式无法解析：/g, "Could not parse ballot: "],
    [/模型列表读取失败：/g, "Could not load models: "],
    [/删除模型「(.*?)」？/g, "Delete model \"$1\"?"],
    [/预设已载入，但\s*(.*?)\s*已删除、改名或无法唯一匹配，请重新选择后再开赛。/g,
      "Preset loaded, but $1 was deleted, renamed, or is ambiguous. Reselect the line-up before starting."],
    [/已复用这场预设：(.*?)。确认阵容后开赛。/g,
      "Reused this preset: $1. Confirm the line-up before starting."],
    [/复用预设失败：/g, "Could not reuse preset: "],
    [/这场比赛仍在运行，请回到实时现场查看。/g,
      "This match is still running. Open the live arena to watch it."],
    [/这场记录还没有可回放的完整战报。/g,
      "This record does not have a complete transcript yet."],
    [/面板|投影/g, "panel"],
  ];

  let lang = 'zh';
  try {
    lang = window.localStorage.getItem(STORAGE_KEY) === 'en' ? 'en' : 'zh';
  } catch (_) {}

  const originals = new WeakMap();
  const rendered = new WeakMap();
  const attributeOriginals = new WeakMap();
  const attributeRendered = new WeakMap();
  let observer = null;

  function translateInner(value) {
    if (!value || !/[\u3400-\u9fff]/.test(value)) return null;
    if (Object.prototype.hasOwnProperty.call(exact, value)) return exact[value];
    let output = value;
    for (const [pattern, replacement] of rules) {
      output = output.replace(pattern, replacement);
    }
    return output !== value ? output : null;
  }

  function translate(value) {
    if (!value) return null;
    const match = String(value).match(/^(\s*)([\s\S]*?)(\s*)$/);
    const translated = translateInner(match[2]);
    return translated == null ? null : `${match[1]}${translated}${match[3]}`;
  }

  function skipped(node) {
    const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    return Boolean(element?.closest(SKIP_SELECTOR));
  }

  function applyText(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE || skipped(node)) return;
    const current = node.data;
    const previousRender = rendered.get(node);
    let source = originals.get(node);
    if (source === undefined || current !== previousRender) source = current;
    const english = translate(source);
    const target = lang === 'en' && english != null ? english : source;
    originals.set(node, source);
    rendered.set(node, target);
    if (node.data !== target) node.data = target;
  }

  function applyAttribute(element, name) {
    if (!element?.getAttribute || skipped(element)) return;
    const current = element.getAttribute(name);
    if (current == null) return;
    let store = attributeOriginals.get(element);
    if (!store) {
      store = {};
      attributeOriginals.set(element, store);
    }
    let renderedStore = attributeRendered.get(element);
    if (!renderedStore) {
      renderedStore = {};
      attributeRendered.set(element, renderedStore);
    }
    let source = store[name];
    if (source === undefined || current !== renderedStore[name]) source = current;
    const english = translate(source);
    const target = lang === 'en' && english != null ? english : source;
    store[name] = source;
    renderedStore[name] = target;
    if (current !== target) element.setAttribute(name, target);
  }

  function translateElement(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      applyText(root);
      return;
    }
    if (root.nodeType === Node.ELEMENT_NODE) {
      for (const name of ATTRIBUTES) applyAttribute(root, name);
    }
    if (skipped(root)) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      applyText(node);
      node = walker.nextNode();
    }
    if (root.querySelectorAll) {
      for (const element of root.querySelectorAll('*')) {
        for (const name of ATTRIBUTES) applyAttribute(element, name);
      }
    }
  }

  function applyAll() {
    if (!document.body) return;
    document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
    document.title = lang === 'en'
      ? 'Agent Arena · Multi-model Debate'
      : 'Agent Arena · 多智能体辩论赛';
    translateElement(document.body);
  }

  function observe() {
    observer?.disconnect();
    observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'characterData') {
          applyText(mutation.target);
        } else if (mutation.type === 'attributes') {
          applyAttribute(mutation.target, mutation.attributeName);
        } else {
          for (const node of mutation.addedNodes) translateElement(node);
        }
      }
    });
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRIBUTES,
    });
  }

  function setLanguage(next) {
    lang = next === 'en' ? 'en' : 'zh';
    try {
      window.localStorage.setItem(STORAGE_KEY, lang);
    } catch (_) {}
    applyAll();
    return lang;
  }

  window.ArenaI18n = {
    get lang() {
      return lang;
    },
    translate,
    init() {
      applyAll();
      if (!observer) observe();
    },
    toggle() {
      return setLanguage(lang === 'zh' ? 'en' : 'zh');
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.ArenaI18n.init(), { once: true });
  }
})();
