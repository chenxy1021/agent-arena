/* Agent Arena 前端：Vue 3，无构建。 */

/* Muted identity set: one hue per model, low chroma, used only on a
   dot and a 1px rule. Never as a fill. */
const PALETTE = [
  '#7fb6a8', '#c9a76a', '#9d93c9', '#c98a8a', '#8fa8c9',
  '#9fbf87', '#c99a7a', '#7fb3bf', '#b39ac4', '#bdbd8a',
];

function agentColor(name) {
  let hash = 2166136261;
  for (let i = 0; i < String(name).length; i++) {
    hash ^= String(name).charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

function cleanError(data) {
  if (!data) return '请求失败';
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((x) => x.msg).join('；');
  return data.error || '请求失败';
}

Vue.createApp({
  data() {
    return {
      proposition: '',
      mode: 'eliminate',
      timeout: 240,
      models: [],
      modelsLoading: true,
      showModelModal: false,
      savingModel: false,
      modelForm: {
        name: '',
        base_url: '',
        api_key: '',
        model: '',
        system_prompt: '',
        temperature: '',
      },
      history: [],
      historyLoading: true,
      viewingHistoryId: '',
      participants: [],
      rounds: [],
      currentRound: 0,
      final: null,
      winnerName: '',
      status: 'idle',
      statusText: '待命',
      liveLabel: '等待开始',
      running: false,
      replaying: false,
      hint: '',
      eventSource: null,
      eventCount: 0,
      startedAt: 0,
      elapsed: 0,
      activeAgent: '',
      activeStage: '',
      stageStartedAt: 0,
      stageElapsed: 0,
      activity: [],
      activitySeq: 0,
      modelOutputs: {},
      modelOutputEls: {},
      modelStreamSeq: 0,
      timer: null,
    };
  },

  computed: {
    selectedModelIds() {
      return this.models.filter((m) => m.checked).map((m) => m.id);
    },
    modelStreams() {
      return Object.values(this.modelOutputs).sort((a, b) => b.seq - a.seq);
    },
    elapsedText() {
      const total = Math.max(0, Math.floor(this.elapsed));
      const min = String(Math.floor(total / 60)).padStart(2, '0');
      const sec = String(total % 60).padStart(2, '0');
      return `${min}:${sec}`;
    },
    stageElapsedText() {
      const total = Math.max(0, Math.floor(this.stageElapsed));
      const min = String(Math.floor(total / 60)).padStart(2, '0');
      const sec = String(total % 60).padStart(2, '0');
      return `${min}:${sec}`;
    },
    stageProgress() {
      if (!this.stageElapsed) return 0;
      return Math.min(100, (this.stageElapsed / Math.max(1, Number(this.timeout))) * 100);
    },
  },

  mounted() {
    this.loadModels();
    this.loadHistory();
    this.attachActive();
    window.addEventListener('beforeunload', this.closeStream);
  },

  beforeUnmount() {
    this.closeStream();
    this.stopTimer();
    window.removeEventListener('beforeunload', this.closeStream);
  },

  methods: {
    agentColor,

    modeLabel(mode) {
      return mode === 'support' ? '票少者出局' : '票多者出局';
    },

    historyStatus(item) {
      if (item.status === 'running') return '进行中';
      if (item.status === 'error') return '失败';
      return '已完成';
    },

    activityKind(kind) {
      const labels = {
        run_start: '启动',
        round_start: '轮次',
        thinking: '思考',
        waiting: '等待',
        speech: '发言',
        voting_start: '投票',
        votes: '计票',
        elimination: '淘汰',
        technical_exit: '退出',
        winner: '胜出',
        final: '总结',
        saved: '保存',
        error: '错误',
        done: '结束',
      };
      return labels[kind] || '事件';
    },

    pushActivity(kind, text, agent = '') {
      this.activity.unshift({
        id: ++this.activitySeq,
        kind,
        text,
        agent,
        clock: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      });
      this.activity = this.activity.slice(0, 80);
    },

    beginStage(agent, text) {
      this.activeAgent = agent || '';
      this.activeStage = text;
      this.stageStartedAt = Date.now();
      this.stageElapsed = 0;
    },

    bindOutputEl(agent, element) {
      if (element) this.modelOutputEls[agent] = element;
      else delete this.modelOutputEls[agent];
    },

    scrollOutput(agent) {
      const element = this.modelOutputEls[agent];
      if (element) element.scrollTop = element.scrollHeight;
    },

    toggleModel(model, event) {
      if (event.target.tagName !== 'INPUT') model.checked = !model.checked;
    },

    async loadModels() {
      this.modelsLoading = true;
      try {
        const res = await fetch('/api/models');
        const data = await res.json();
        if (!res.ok) throw new Error(cleanError(data));
        const selected = new Map(this.models.map((item) => [item.id, item.checked]));
        this.models = (data.models || []).map((item) => ({
          ...item,
          checked: selected.has(item.id) ? selected.get(item.id) : true,
        }));
      } catch (err) {
        this.models = [];
        this.hint = `模型列表读取失败：${err.message}`;
      } finally {
        this.modelsLoading = false;
      }
    },

    openModelModal() {
      this.modelForm = {
        name: '',
        base_url: '',
        api_key: '',
        model: '',
        system_prompt: '',
        temperature: '',
      };
      this.showModelModal = true;
    },

    closeModelModal() {
      if (!this.savingModel) this.showModelModal = false;
    },

    async saveModel() {
      if (this.savingModel) return;
      this.savingModel = true;
      this.hint = '';
      try {
        const res = await fetch('/api/models', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...this.modelForm,
            temperature: this.modelForm.temperature === ''
              ? null
              : Number(this.modelForm.temperature),
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(cleanError(data));
        this.showModelModal = false;
        await this.loadModels();
      } catch (err) {
        this.hint = err.message;
      } finally {
        this.savingModel = false;
      }
    },

    async deleteModel(model) {
      if (!window.confirm(`删除模型「${model.name}」？`)) return;
      try {
        const res = await fetch(`/api/models/${model.id}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) throw new Error(cleanError(data));
        this.models = this.models.filter((item) => item.id !== model.id);
      } catch (err) {
        this.hint = `删除失败：${err.message}`;
      }
    },

    async loadHistory() {
      this.historyLoading = true;
      try {
        const res = await fetch('/api/history?limit=80');
        const data = await res.json();
        if (!res.ok) throw new Error(cleanError(data));
        this.history = data.runs || [];
      } catch (err) {
        this.history = [];
        this.hint = `历史记录读取失败：${err.message}`;
      } finally {
        this.historyLoading = false;
      }
    },

    resetArena() {
      this.closeStream();
      this.participants = [];
      this.rounds = [];
      this.currentRound = 0;
      this.final = null;
      this.winnerName = '';
      this.eventCount = 0;
      this.status = 'idle';
      this.statusText = '待命';
      this.liveLabel = '等待开始';
      this.replaying = false;
      this.viewingHistoryId = '';
      this.activeAgent = '';
      this.activeStage = '';
      this.stageStartedAt = 0;
      this.stageElapsed = 0;
      this.activity = [];
      this.activitySeq = 0;
      this.modelOutputs = {};
      this.modelOutputEls = {};
      this.modelStreamSeq = 0;
      this.stopTimer();
    },

    startTimer() {
      this.stopTimer();
      this.startedAt = Date.now();
      this.elapsed = 0;
      this.timer = window.setInterval(() => {
        this.elapsed = (Date.now() - this.startedAt) / 1000;
        if (this.stageStartedAt) {
          this.stageElapsed = (Date.now() - this.stageStartedAt) / 1000;
        }
      }, 1000);
    },

    stopTimer() {
      if (this.timer) window.clearInterval(this.timer);
      this.timer = null;
    },

    async startMatch() {
      if (this.running) return;
      const proposition = this.proposition.trim();
      if (!proposition) {
        this.hint = '先写一个命题';
        return;
      }
      if (this.selectedModelIds.length < 2) {
        this.hint = '至少选择 2 个参赛大模型';
        return;
      }
      this.hint = '';
      this.resetArena();
      this.running = true;
      this.status = 'running';
      this.statusText = '比赛中';
      this.liveLabel = '正在组建参赛阵容…';
      this.beginStage('', '正在连接参赛大模型');
      this.startTimer();

      const payload = {
        proposition,
        vote_mode: this.mode,
        timeout: Number(this.timeout) || 240,
        model_ids: this.selectedModelIds,
      };

      try {
        const res = await fetch('/api/runs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(cleanError(data));
        this.openStream(data.run);
      } catch (err) {
        this.running = false;
        this.status = 'error';
        this.statusText = '启动失败';
        this.liveLabel = '启动失败';
        this.hint = err.message;
        this.stopTimer();
      }
    },

    openStream(runId) {
      this.closeStream();
      const url = `/api/runs/${encodeURIComponent(runId)}/events?after=${this.eventCount}`;
      const es = new EventSource(url);
      this.eventSource = es;
      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          this.eventCount += 1;
          this.handleEvent(payload);
        } catch (_) {
          // 单条坏帧不影响后续事件。
        }
      };
      es.addEventListener('end', () => {
        es.close();
        if (this.eventSource === es) this.eventSource = null;
      });
      es.onerror = () => {
        if (this.running) {
          this.statusText = '重连中';
          this.liveLabel = '事件流断开，正在自动重连…';
        }
      };
    },

    closeStream() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }
    },

    ensureRound(no) {
      let round = this.rounds.find((r) => r.no === no);
      if (round) return round;
      round = {
        no,
        alive: 0,
        order: [],
        speeches: [],
        thinking: [],
        exits: [],
        votes: null,
        eliminated: null,
      };
      this.rounds.push(round);
      this.currentRound = Math.max(this.currentRound, no);
      this.scrollDown(true);
      return round;
    },

    setAgentState(name, state) {
      const participant = this.participants.find((p) => p.name === name);
      if (participant) participant.state = state;
    },

    handleEvent(ev) {
      switch (ev.kind) {
        case 'run_start':
          this.participants = (ev.agents || []).map((a) => ({
            name: a.name,
            label: a.label,
            state: 'alive',
            lastRole: '',
            lastElapsed: 0,
          }));
          this.liveLabel = `第 1 轮即将开始 · ${this.participants.length} 位参赛`;
          this.beginStage('', '参赛阵容已就绪');
          break;

        case 'round_start': {
          const round = this.ensureRound(ev.no);
          round.alive = ev.alive;
          round.order = ev.order || [];
          this.liveLabel = `第 ${ev.no} 轮 · ${ev.alive} 人存活`;
          this.beginStage('', `第 ${ev.no} 轮准备发言`);
          this.scrollDown();
          break;
        }

        case 'thinking': {
          const round = this.ensureRound(this.currentRound || 1);
          if (!round.thinking.some((x) => x.agent === ev.agent && x.role === ev.role)) {
            round.thinking.push({ agent: ev.agent, role: ev.role });
          }
          this.modelOutputs = {
            ...this.modelOutputs,
            [ev.agent]: {
              agent: ev.agent,
              role: ev.role,
              text: '',
              seq: ++this.modelStreamSeq,
            },
          };
          this.setAgentState(ev.agent, 'thinking');
          this.liveLabel = `${ev.agent} 正在组织${ev.role}`;
          this.beginStage(ev.agent, `${ev.role}中，等待模型返回`);
          this.scrollDown();
          break;
        }

        case 'model_output': {
          const current = this.modelOutputs[ev.agent] || {
            agent: ev.agent,
            role: ev.role,
            text: '',
            seq: ++this.modelStreamSeq,
          };
          current.text = `${current.text}${ev.text || ''}`.slice(-16000);
          this.modelOutputs = { ...this.modelOutputs, [ev.agent]: current };
          this.$nextTick(() => this.scrollOutput(ev.agent));
          this.activeAgent = ev.agent;
          this.activeStage = `${ev.role}中 · 模型正在逐字返回`;
          this.liveLabel = `${ev.agent} 正在实时输出`;
          break;
        }

        case 'waiting':
          this.setAgentState(ev.agent, 'thinking');
          this.activeAgent = ev.agent;
          this.activeStage = `${ev.role}中，已等待 ${Number(ev.elapsed || 0).toFixed(1)} 秒`;
          this.stageStartedAt = Date.now() - Number(ev.elapsed || 0) * 1000;
          this.stageElapsed = Number(ev.elapsed || 0);
          this.liveLabel = `${ev.agent} · ${this.activeStage}`;
          break;

        case 'speech': {
          const round = this.ensureRound(this.currentRound || 1);
          round.thinking = round.thinking.filter((x) => x.agent !== ev.agent);
          round.speeches.push(ev);
          if (ev.text && this.modelOutputs[ev.agent] && !this.modelOutputs[ev.agent].text) {
            this.modelOutputs[ev.agent].text = ev.text;
          }
          this.setAgentState(ev.agent, 'alive');
          const participant = this.participants.find((p) => p.name === ev.agent);
          if (participant) {
            participant.lastRole = ev.role;
            participant.lastElapsed = ev.elapsed;
          }
          this.liveLabel = ev.error
            ? `${ev.agent} 发言失败`
            : `${ev.agent} 发言完成，用时 ${Number(ev.elapsed || 0).toFixed(1)} 秒`;
          this.activeAgent = ev.agent;
          this.activeStage = ev.error ? '调用失败' : `${ev.role}完成`;
          this.stageStartedAt = 0;
          this.stageElapsed = Number(ev.elapsed || 0);
          this.scrollDown();
          break;
        }

        case 'voting_start':
          this.beginStage('', `${ev.voters} 位投票者正在并行投票`);
          this.liveLabel = `第 ${ev.round_no} 轮 · 全员投票中`;
          break;

        case 'votes': {
          const round = this.ensureRound(this.currentRound || 1);
          round.votes = ev;
          round.thinking = [];
          this.liveLabel = '投票完成，正在计票';
          this.beginStage('', '投票完成，正在计票');
          this.scrollDown();
          break;
        }

        case 'elimination': {
          const round = this.ensureRound(this.currentRound || 1);
          round.eliminated = ev;
          this.setAgentState(ev.agent, 'out');
          this.liveLabel = `${ev.agent} 出局，转为评审`;
          this.beginStage(ev.agent, `${ev.agent} 出局，转为评审`);
          this.scrollDown();
          break;
        }

        case 'technical_exit': {
          const round = this.ensureRound(this.currentRound || 1);
          round.exits.push(ev);
          this.setAgentState(ev.agent, 'out');
          this.liveLabel = `${ev.agent} 技术性退赛`;
          this.beginStage(ev.agent, `${ev.agent} 技术性退赛`);
          this.scrollDown();
          break;
        }

        case 'winner':
          this.winnerName = ev.agent;
          this.setAgentState(ev.agent, 'alive');
          this.liveLabel = `${ev.agent} 最终存活`;
          this.beginStage(ev.agent, `${ev.agent} 最终存活`);
          break;

        case 'final':
          this.final = ev;
          this.rounds.forEach((round) => { round.thinking = []; });
          this.setAgentState(ev.agent, 'alive');
          this.liveLabel = `${ev.agent} 正在整理最终结论`;
          this.beginStage(ev.agent, '正在整理最终结论');
          this.scrollDown(true);
          break;

        case 'saved':
          this.loadHistory();
          break;

        case 'error':
          this.hint = ev.message || '比赛出错了';
          this.status = 'error';
          this.statusText = '出错';
          break;

        case 'done':
          this.running = false;
          this.status = this.status === 'error' ? 'error' : 'done';
          this.statusText = this.status === 'error' ? '失败' : '已结束';
          this.liveLabel = this.final ? '比赛结束，可以回看全过程' : '比赛结束';
          this.rounds.forEach((round) => { round.thinking = []; });
          this.elapsed = Number(ev.duration || this.elapsed);
          this.activeAgent = this.winnerName || '';
          this.activeStage = this.winnerName ? `${this.winnerName} 胜出` : '比赛结束';
          this.stageStartedAt = 0;
          this.stopTimer();
          this.loadHistory();
          this.scrollDown();
          break;
      }
      if (ev.kind !== 'waiting' && ev.kind !== 'model_output') {
        this.pushActivity(ev.kind, this.liveLabel, ev.agent || '');
      }
    },

    async attachActive() {
      try {
        const res = await fetch('/api/runs/active');
        const data = await res.json();
        if (!res.ok || !data.run) return;
        if (data.run.status !== 'running') return;
        this.resetArena();
        this.proposition = data.run.proposition || this.proposition;
        this.running = true;
        this.status = 'running';
        this.statusText = '接续中';
        this.liveLabel = '正在接回比赛现场…';
        this.beginStage('', '正在接回比赛现场');
        this.startTimer();
        this.openStream(data.run.id);
      } catch (_) {
        // 没有活动比赛时不打扰用户。
      }
    },

    async loadHistoryRun(id) {
      try {
        const res = await fetch(`/api/history/${encodeURIComponent(id)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(cleanError(data));
        const transcript = data.transcript;
        if (!transcript) {
          this.hint = data.meta.status === 'running'
            ? '这场比赛仍在运行，请回到实时现场查看。'
            : '这场记录还没有可回放的完整战报。';
          return;
        }
        this.resetArena();
        this.replaying = true;
        this.running = false;
        this.viewingHistoryId = id;
        this.proposition = transcript.proposition || this.proposition;
        this.mode = transcript.vote_mode || 'eliminate';
        this.status = 'done';
        this.statusText = '历史回放';
        this.liveLabel = '历史提问回放';
        this.participants = (transcript.participants || []).map((p) => ({
          name: p.name,
          label: p.label,
          state: 'alive',
          lastRole: '',
          lastElapsed: 0,
        }));
        this.winnerName = transcript.winner || '';
        for (const record of transcript.rounds || []) {
          const round = this.ensureRound(record.no);
          round.order = record.order || [];
          round.alive = round.order.length;
          round.speeches = record.speeches || [];
          round.exits = record.exits || [];
          for (const speech of round.speeches) {
            const participant = this.participants.find((p) => p.name === speech.agent);
            if (participant) {
              participant.lastRole = speech.role;
              participant.lastElapsed = speech.elapsed;
            }
          }
          if (record.votes && record.votes.length) {
            round.votes = {
              rows: record.votes,
              counts: record.counts || {},
              vote_mode: transcript.vote_mode,
            };
          }
          if (record.eliminated) {
            round.eliminated = {
              agent: record.eliminated,
              votes: record.votes_received,
              tiebreak: record.tiebreak,
            };
            this.setAgentState(record.eliminated, 'out');
          }
        }
        if (transcript.winner && transcript.final_answer) {
          this.final = { agent: transcript.winner, text: transcript.final_answer };
        }
        this.liveLabel = '历史战报已载入';
        this.activeAgent = transcript.winner || '';
        this.activeStage = '历史回放完成';
        this.stageElapsed = Number(transcript.duration || 0);
        this.pushActivity('done', `载入历史提问：${transcript.proposition || id}`, transcript.winner || '');
        this.hint = '';
        this.scrollDown(true);
      } catch (err) {
        this.hint = `历史回放失败：${err.message}`;
      }
    },

    voteBars(votes) {
      const entries = Object.entries(votes?.counts || {}).sort((a, b) => b[1] - a[1]);
      const max = Math.max(1, ...entries.map((entry) => entry[1]));
      return entries.map(([name, count], i) => ({
        name,
        count,
        lead: i === 0 && count > 0,
        width: (count / max) * 100,
      }));
    },

    speechBlocks(text) {
      const raw = String(text || '');
      const critique = raw.match(/【点评】([\s\S]*?)(?=【观点】|$)/);
      const view = raw.match(/【观点】([\s\S]*)/);
      const blocks = [];
      if (critique && critique[1].trim()) {
        blocks.push({ kind: 'critique', text: critique[1].trim() });
      }
      if (view && view[1].trim()) {
        blocks.push({ kind: 'view', text: view[1].trim() });
      }
      if (!blocks.length) blocks.push({ kind: 'plain', text: raw });
      return blocks;
    },

    finalBlocks(text) {
      const raw = String(text || '');
      const labels = [
        ['conclusion', '结论', '【结论】'],
        ['evidence', '论据', '【论据】'],
        ['action', '行动', '【行动】'],
      ];
      const positions = labels
        .map(([kind, label, marker]) => ({ kind, label, marker, at: raw.indexOf(marker) }))
        .filter((item) => item.at >= 0)
        .sort((a, b) => a.at - b.at);
      if (!positions.length) return [{ kind: 'plain', label: '', text: raw }];
      return positions.map((item, idx) => {
        const next = positions[idx + 1]?.at ?? raw.length;
        return {
          kind: item.kind,
          label: item.label,
          text: raw.slice(item.at + item.marker.length, next).trim(),
        };
      });
    },

    scrollDown(force = false) {
      const element = this.$refs.stream;
      if (!element) return;
      const nearBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 180;
      if (force || nearBottom) {
        window.requestAnimationFrame(() => {
          element.scrollTop = element.scrollHeight;
        });
      }
    },
  },
}).mount('#app');
