/* Agent Arena 前端：Vue 3，无构建。 */

/* Stage-light identity set. Colour belongs to the models, not the interface. */
const PALETTE = [
  '#ff6b81', '#ffc15e', '#4fe3c1', '#5fa8ff', '#b98cff', '#f27ac0',
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

const TALLY_STROKES = [
  { x1: 2, y1: 2, x2: 16, y2: 2 },
  { x1: 9, y1: 2, x2: 9, y2: 20 },
  { x1: 2, y1: 10, x2: 16, y2: 10 },
  { x1: 5, y1: 10, x2: 5, y2: 18 },
  { x1: 2, y1: 20, x2: 16, y2: 20 },
];

const RollingNumber = {
  props: {
    text: { type: String, default: '0' },
  },
  computed: {
    chars() {
      return String(this.text).split('');
    },
  },
  methods: {
    isDigit(char) {
      return /\d/.test(char);
    },
  },
  template: `
    <span class="rolling-number" :aria-label="text">
      <template v-for="(char, index) in chars" :key="index">
        <span v-if="isDigit(char)" class="roll-digit">
          <span class="roll-track" :style="{ transform: 'translateY(-' + (Number(char) * 10) + '%)' }">
            <i v-for="digit in 10" :key="digit">{{ digit - 1 }}</i>
          </span>
        </span>
        <span v-else class="roll-separator">{{ char }}</span>
      </template>
    </span>
  `,
};

const TallyMarks = {
  components: { RollingNumber },
  props: {
    count: { type: Number, default: 0 },
    color: { type: String, default: 'currentColor' },
  },
  computed: {
    groups() {
      const groups = [];
      let remaining = Math.max(0, Number(this.count) || 0);
      while (remaining > 0) {
        groups.push(TALLY_STROKES.slice(0, Math.min(5, remaining)));
        remaining -= 5;
      }
      return groups;
    },
  },
  template: `
    <span class="tally-marks" :style="{ color: color }">
      <span class="tally-glyphs" v-if="count > 0">
        <svg v-for="(strokeGroup, groupIndex) in groups" :key="groupIndex"
          class="tally-glyph" viewBox="0 0 18 22" aria-hidden="true">
          <line v-for="(stroke, strokeIndex) in strokeGroup" :key="strokeIndex"
            :x1="stroke.x1" :y1="stroke.y1" :x2="stroke.x2" :y2="stroke.y2"
            :style="{ animationDelay: ((groupIndex * 5 + strokeIndex) * 60) + 'ms' }" />
        </svg>
      </span>
      <span v-else class="tally-zero">〇</span>
      <rolling-number class="tally-number" :text="String(count)" />
    </span>
  `,
};

Vue.createApp({
  components: { RollingNumber, TallyMarks },

  data() {
    return {
      proposition: '',
      mode: 'eliminate',
      timeout: 240,
      models: [],
      modelsLoading: true,
      showModelModal: false,
      savingModel: false,
      namingModel: false,
      hintOk: false,
      editingModelId: 0,
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
      soundOn: false,
      votingMode: false,
      waitingMode: false,
      eventFx: '',
      hitAgent: '',
      leaderFlicker: false,
      liveVoteCounts: {},
      decodedNames: {},
      archiveStamp: '',
      settledKey: '',
      pointerX: 0,
      pointerY: 0,
      reducedMotion: false,
    };
  },

  computed: {
    selectedModelIds() {
      return this.models.filter((m) => m.checked).map((m) => m.id);
    },
    modelStreams() {
      return Object.values(this.modelOutputs)
        .filter((stream) => stream.round === this.currentRound)
        .filter((stream) => {
          const participant = this.participants.find((item) => item.name === stream.agent);
          return !participant || participant.state !== 'out';
        })
        .sort((a, b) => b.seq - a.seq);
    },
    roundsNewestFirst() {
      return [...this.rounds].sort((a, b) => b.no - a.no);
    },
    scoreByName() {
      const scores = {};
      for (const participant of this.participants) scores[participant.name] = 0;
      for (const round of this.rounds) {
        for (const [name, count] of Object.entries(round.votes?.counts || {})) {
          scores[name] = (scores[name] || 0) + Number(count);
        }
      }
      return scores;
    },
    beamMax() {
      return Math.max(0, ...this.participants.map((participant) => this.scoreFor(participant.name)));
    },
    outCount() {
      return this.participants.filter((item) => item.state === 'out').length;
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
    stageTiltStyle() {
      return {
        '--stage-tilt-x': `${(-this.pointerY * 1.2).toFixed(2)}deg`,
        '--stage-tilt-y': `${(this.pointerX * 1.2).toFixed(2)}deg`,
        '--stage-shift-x': `${(this.pointerX * 6).toFixed(2)}px`,
        '--stage-shift-y': `${(this.pointerY * 4).toFixed(2)}px`,
      };
    },
  },

  mounted() {
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.soundOn = window.localStorage.getItem('arena-sound') === 'on';
    this.loadModels();
    this.loadHistory();
    this.attachActive();
    window.addEventListener('beforeunload', this.closeStream);
    window.addEventListener('beforeunload', this.teardownStage);
    window.addEventListener('resize', this.resizeStage);
    this.$nextTick(this.setupStage);
    if (this.soundOn) {
      window.addEventListener('pointerdown', () => this.enableSound(), { once: true });
    }
  },

  beforeUnmount() {
    this.closeStream();
    this.stopTimer();
    this.teardownStage();
    window.removeEventListener('beforeunload', this.closeStream);
    window.removeEventListener('beforeunload', this.teardownStage);
    window.removeEventListener('resize', this.resizeStage);
  },

  methods: {
    agentColor,

    newMatch() {
      this.resetArena();
      this.proposition = '';
    },

    roundNo(no) {
      return String(no).padStart(2, '0');
    },

    scoreFor(name) {
      return (this.scoreByName[name] || 0) + (this.liveVoteCounts[name] || 0);
    },

    beamHeight(name) {
      const score = this.scoreFor(name);
      const ratio = this.beamMax > 0 ? score / this.beamMax : 0;
      const speakingBoost = name === this.activeAgent ? this.stageProgress * 0.09 : 0;
      return Math.min(100, 9 + ratio * 81 + speakingBoost);
    },

    beamScale(name) {
      return Math.max(.09, this.beamHeight(name) / 100);
    },

    agentModel(name) {
      return this.participants.find((item) => item.name === name)?.label || '';
    },

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
        voting: '投票中',
        tiebreak: '加赛',
        tiebreak_result: '加赛计票',
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

    displayName(name) {
      return this.decodedNames[name] || name;
    },

    decodeAgentName(name) {
      if (!name || this.reducedMotion || this.replaying) return;
      window.clearInterval(this._nameTimers?.[name]);
      this._nameTimers ||= {};
      const glyphs = 'ABCDEF0123456789#$%&*<>/';
      let step = 0;
      const total = Math.max(8, Math.min(13, name.length + 5));
      const timer = window.setInterval(() => {
        step += 1;
        const settled = Math.floor((step / total) * name.length);
        const scrambled = name
          .split('')
          .map((char, index) => (
            index < settled || step >= total
              ? char
              : glyphs[Math.floor(Math.random() * glyphs.length)]
          ))
          .join('');
        this.decodedNames = { ...this.decodedNames, [name]: scrambled };
        if (step >= total) {
          window.clearInterval(timer);
          delete this._nameTimers[name];
          this.decodedNames = { ...this.decodedNames, [name]: name };
        }
      }, 30);
      this._nameTimers[name] = timer;
    },

    streamChars(stream) {
      return [...String(stream?.text || '')].length;
    },

    streamProgress(stream) {
      return Math.min(96, this.streamChars(stream) / 8);
    },

    moveStage(event) {
      if (this.reducedMotion || this.replaying || !this.$refs.stage) return;
      const rect = this.$refs.stage.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      this.pointerX = Math.max(-.5, Math.min(.5, (event.clientX - rect.left) / rect.width - .5));
      this.pointerY = Math.max(-.5, Math.min(.5, (event.clientY - rect.top) / rect.height - .5));
    },

    playFx(name, duration = 900) {
      window.clearTimeout(this._fxTimer);
      this.eventFx = '';
      window.requestAnimationFrame(() => {
        this.eventFx = name;
        this._fxTimer = window.setTimeout(() => {
          if (this.eventFx === name) this.eventFx = '';
        }, this.reducedMotion ? 1 : duration);
      });
    },

    flashHit(name) {
      if (!name) return;
      window.clearTimeout(this._hitTimer);
      this.hitAgent = name;
      this._hitTimer = window.setTimeout(() => {
        if (this.hitAgent === name) this.hitAgent = '';
      }, 320);
    },

    pulseWaiting() {
      window.clearTimeout(this._waitingTimer);
      this.waitingMode = true;
      this._waitingTimer = window.setTimeout(() => {
        this.waitingMode = false;
      }, 2350);
    },

    enableSound() {
      if (!this.soundOn) return;
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      this._audio ||= new AudioCtx();
      if (this._audio.state === 'suspended') this._audio.resume();
      this.startAmbient();
    },

    toggleSound() {
      this.soundOn = !this.soundOn;
      window.localStorage.setItem('arena-sound', this.soundOn ? 'on' : 'off');
      if (this.soundOn) {
        this.enableSound();
        this.sound('ding');
      } else {
        this.stopAmbient();
      }
    },

    startAmbient() {
      if (!this._audio || this._ambient) return;
      const gain = this._audio.createGain();
      const low = this._audio.createOscillator();
      const high = this._audio.createOscillator();
      low.type = 'sine';
      high.type = 'sine';
      low.frequency.value = 44;
      high.frequency.value = 66;
      gain.gain.value = .006;
      low.connect(gain);
      high.connect(gain);
      gain.connect(this._audio.destination);
      low.start();
      high.start();
      this._ambient = { low, high, gain };
    },

    stopAmbient() {
      if (!this._ambient) return;
      const current = this._ambient;
      this._ambient = null;
      try {
        current.gain.gain.setTargetAtTime(0, this._audio.currentTime, .08);
        window.setTimeout(() => {
          current.low.stop();
          current.high.stop();
        }, 280);
      } catch (_) {
        // Audio may already be closed by the browser.
      }
    },

    sound(kind) {
      if (!this.soundOn) return;
      this.enableSound();
      if (!this._audio) return;
      const tone = (frequency, duration, type = 'sine', volume = .035, delay = 0) => {
        const start = this._audio.currentTime + delay;
        const oscillator = this._audio.createOscillator();
        const gain = this._audio.createGain();
        oscillator.type = type;
        oscillator.frequency.setValueAtTime(frequency, start);
        gain.gain.setValueAtTime(0, start);
        gain.gain.linearRampToValueAtTime(volume, start + .012);
        gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
        oscillator.connect(gain);
        gain.connect(this._audio.destination);
        oscillator.start(start);
        oscillator.stop(start + duration + .03);
      };
      if (kind === 'ding') tone(880, .16, 'sine', .028);
      if (kind === 'thud') {
        tone(74, .3, 'sine', .075);
        tone(111, .16, 'triangle', .025);
      }
      if (kind === 'winner') {
        [523.25, 659.25, 783.99].forEach((frequency, index) => {
          tone(frequency, 1.2, 'sine', .026, index * .09);
        });
      }
      if (kind === 'tick') tone(320, .045, 'square', .01);
    },

    beamIndex(name) {
      return this.participants.findIndex((participant) => participant.name === name);
    },

    setupStage() {
      const canvas = this.$refs.stageCanvas;
      const stage = this.$refs.stage;
      if (!canvas || !stage) return;
      const rect = stage.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      const ctx = canvas.getContext('2d', { alpha: true });
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const count = Math.max(1, this.participants.length);
      const column = rect.width / count;
      const dust = [];
      this.participants.forEach((participant, index) => {
        const score = this.scoreFor(participant.name);
        const ratio = this.beamMax ? score / this.beamMax : 0;
        const amount = 6 + Math.round(ratio * 4);
        for (let i = 0; i < amount; i += 1) {
          dust.push({
            x: (index + .5) * column + (Math.random() - .5) * column * .28,
            y: rect.height - 38 - Math.random() * rect.height * .72,
            speed: .012 + Math.random() * .022,
            size: .8 + Math.random() * .9,
            phase: Math.random() * Math.PI * 2,
            color: agentColor(participant.name),
          });
        }
      });
      const audience = Array.from({ length: 20 }, (_, index) => ({
        x: 18 + Math.random() * Math.max(1, rect.width - 36),
        y: rect.height - 12 - Math.random() * 46,
        phase: index * .61 + Math.random() * .8,
        size: 1.2 + Math.random() * 1.4,
      }));
      this._scene = {
        canvas,
        ctx,
        width: rect.width,
        height: rect.height,
        column,
        dust,
        audience,
        trails: [],
        fragments: [],
        confetti: [],
        startedAt: performance.now(),
      };
      this.scheduleVoltage();
      this.drawStage(performance.now());
      if (!this.reducedMotion && !this.replaying) this.startStageLoop();
    },

    resizeStage() {
      window.clearTimeout(this._resizeTimer);
      this._resizeTimer = window.setTimeout(() => this.setupStage(), 160);
    },

    startStageLoop() {
      window.cancelAnimationFrame(this._stageFrame);
      const frame = (now) => {
        this.drawStage(now);
        if (!this.reducedMotion && !this.replaying && !document.hidden) {
          this._stageFrame = window.requestAnimationFrame(frame);
        }
      };
      this._stageFrame = window.requestAnimationFrame(frame);
    },

    drawStage(now) {
      const scene = this._scene;
      if (!scene) return;
      const { ctx, width, height } = scene;
      const seconds = now / 1000;
      ctx.clearRect(0, 0, width, height);

      ctx.globalCompositeOperation = 'lighter';
      for (const particle of scene.dust) {
        if (!this.reducedMotion) {
          particle.y -= particle.speed * 2.4;
          particle.x += Math.sin(seconds * .55 + particle.phase) * .035;
          if (particle.y < 44) particle.y = height - 42;
        }
        ctx.globalAlpha = .2 + Math.sin(seconds * 1.4 + particle.phase) * .08;
        ctx.fillStyle = particle.color;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
        ctx.fill();
      }
      for (const seat of scene.audience) {
        ctx.globalAlpha = .08 + (Math.sin(seconds * .7 + seat.phase) + 1) * .055;
        ctx.fillStyle = '#dce4ff';
        ctx.beginPath();
        ctx.arc(seat.x, seat.y, seat.size, 0, Math.PI * 2);
        ctx.fill();
      }

      if (this.waitingMode) {
        const x = ((now % 2400) / 2400) * width;
        const gradient = ctx.createRadialGradient(x, height - 40, 0, x, height - 40, 70);
        gradient.addColorStop(0, 'rgba(255,255,255,.38)');
        gradient.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.globalAlpha = .7;
        ctx.fillStyle = gradient;
        ctx.fillRect(x - 70, height - 70, 140, 60);
      }

      scene.trails = scene.trails.filter((trail) => now - trail.at < 620);
      for (const trail of scene.trails) {
        const progress = Math.min(1, (now - trail.at) / 420);
        const fromX = (trail.from + .5) * scene.column;
        const toX = (trail.to + .5) * scene.column;
        ctx.globalAlpha = (1 - progress) * .8;
        ctx.strokeStyle = '#ff2e63';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(fromX, height - 34);
        ctx.quadraticCurveTo((fromX + toX) / 2, height - 65, toX, height - 34);
        ctx.stroke();
      }

      scene.fragments = scene.fragments.filter((piece) => piece.life > 0);
      for (const piece of scene.fragments) {
        if (!this.reducedMotion) {
          piece.life -= .012;
          piece.x += piece.vx;
          piece.y += piece.vy;
          piece.vy += .06;
        }
        ctx.globalAlpha = Math.max(0, piece.life);
        ctx.fillStyle = piece.color;
        ctx.fillRect(piece.x, piece.y, piece.size, piece.size * 1.6);
      }

      scene.confetti = scene.confetti.filter((piece) => piece.life > 0);
      for (const piece of scene.confetti) {
        if (!this.reducedMotion) {
          piece.life -= .0035;
          piece.x += piece.vx + Math.sin(seconds * 3 + piece.phase) * .25;
          piece.y += piece.vy;
          piece.vy += .018;
        }
        ctx.save();
        ctx.globalAlpha = Math.min(1, piece.life * 1.8);
        ctx.translate(piece.x, piece.y);
        ctx.rotate(seconds * piece.spin + piece.phase);
        ctx.fillStyle = piece.color;
        ctx.fillRect(-piece.size / 2, -piece.size / 4, piece.size, piece.size / 2);
        ctx.restore();
      }
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
    },

    emitVoteTrail(voter, target) {
      if (!this._scene) return;
      const from = this.beamIndex(voter);
      const to = this.beamIndex(target);
      if (from < 0 || to < 0 || from === to) return;
      this._scene.trails.push({ from, to, at: performance.now() });
    },

    emitEliminationParticles(name) {
      if (!this._scene) return;
      const index = this.beamIndex(name);
      if (index < 0) return;
      const scene = this._scene;
      const x = (index + .5) * scene.column;
      const color = agentColor(name);
      for (let i = 0; i < 28; i += 1) {
        scene.fragments.push({
          x: x + (Math.random() - .5) * 26,
          y: scene.height - 54 - Math.random() * scene.height * .55,
          vx: (Math.random() - .5) * 1.8,
          vy: -Math.random() * 1.1,
          size: 1 + Math.random() * 2.4,
          life: .7 + Math.random() * .3,
          color,
        });
      }
    },

    emitWinnerConfetti() {
      if (!this._scene) return;
      const scene = this._scene;
      const colors = ['#f2c14e', '#ffe7a0', '#ffffff', '#b98cff', '#4fe3c1'];
      for (let i = 0; i < 60; i += 1) {
        scene.confetti.push({
          x: Math.random() * scene.width,
          y: -10 - Math.random() * scene.height * .4,
          vx: (Math.random() - .5) * .5,
          vy: .55 + Math.random() * .9,
          size: 3 + Math.random() * 4,
          spin: (Math.random() - .5) * 4,
          phase: Math.random() * Math.PI * 2,
          life: .8 + Math.random() * .5,
          color: colors[Math.floor(Math.random() * colors.length)],
        });
      }
    },

    scheduleVoltage() {
      window.clearTimeout(this._voltageTimer);
      if (this.reducedMotion) return;
      const delay = 2600 + Math.random() * 6200;
      this._voltageTimer = window.setTimeout(() => {
        if (this.running && this.beamMax > 0 && !this.replaying) {
          this.leaderFlicker = true;
          window.setTimeout(() => { this.leaderFlicker = false; }, 130);
        }
        this.scheduleVoltage();
      }, delay);
    },

    teardownStage() {
      window.cancelAnimationFrame(this._stageFrame);
      window.clearTimeout(this._resizeTimer);
      window.clearTimeout(this._fxTimer);
      window.clearTimeout(this._hitTimer);
      window.clearTimeout(this._waitingTimer);
      window.clearTimeout(this._voltageTimer);
      window.clearTimeout(this._archiveTimer);
      window.clearTimeout(this._settleTimer);
      Object.values(this._nameTimers || {}).forEach((timer) => window.clearInterval(timer));
      this._nameTimers = {};
      this.stopAmbient();
      if (this._audio) {
        try {
          this._audio.close().catch?.(() => {});
        } catch (_) {
          // Audio may already be closed by the browser.
        }
        this._audio = null;
      }
      this._scene = null;
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

    openModelModal(model = null) {
      this.modelForm = {
        name: model?.name || '',
        base_url: model?.base_url || '',
        api_key: '',
        model: model?.model || '',
        system_prompt: model?.system_prompt || '',
        temperature: model?.temperature ?? '',
      };
      this.editingModelId = model?.id || 0;
      this.hint = '';
      this.hintOk = false;
      this.showModelModal = true;
    },

    closeModelModal() {
      if (this.savingModel) return;
      this.showModelModal = false;
      this.editingModelId = 0;
      this.hintOk = false;
    },

    async saveModel() {
      if (this.savingModel || this.namingModel) return;
      this.savingModel = true;
      this.hint = '';
      this.hintOk = false;
      try {
        const res = await fetch(
          this.editingModelId ? `/api/models/${this.editingModelId}` : '/api/models',
          {
            method: this.editingModelId ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              ...this.modelForm,
              temperature: this.modelForm.temperature === ''
                ? null
                : Number(this.modelForm.temperature),
            }),
          },
        );
        const data = await res.json();
        if (!res.ok) throw new Error(cleanError(data));
        this.showModelModal = false;
        this.editingModelId = 0;
        await this.loadModels();
      } catch (err) {
        this.hint = err.message;
        this.hintOk = false;
      } finally {
        this.savingModel = false;
      }
    },

    async suggestModelName() {
      if (this.namingModel || this.savingModel) return;
      const baseUrl = this.modelForm.base_url.trim();
      const model = this.modelForm.model.trim();
      if (!baseUrl || !model) {
        this.hint = '先填写 Base URL 和模型 ID';
        this.hintOk = false;
        return;
      }
      if (!this.modelForm.api_key.trim() && !this.editingModelId) {
        this.hint = '先填写 API Key';
        this.hintOk = false;
        return;
      }
      this.namingModel = true;
      this.hint = '正在连接模型并生成名称…';
      this.hintOk = false;
      try {
        const res = await fetch('/api/models/suggest-name', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model_id: this.editingModelId || null,
            ...this.modelForm,
            temperature: this.modelForm.temperature === ''
              ? null
              : Number(this.modelForm.temperature),
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(cleanError(data));
        this.modelForm.name = data.name;
        this.hint = '连通性正常，已生成显示名称。';
        this.hintOk = true;
      } catch (err) {
        this.hint = `取名失败：${err.message}`;
        this.hintOk = false;
      } finally {
        this.namingModel = false;
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
      this.votingMode = false;
      this.waitingMode = false;
      this.eventFx = '';
      this.hitAgent = '';
      this.leaderFlicker = false;
      this.liveVoteCounts = {};
      this.decodedNames = {};
      this.archiveStamp = '';
      this.settledKey = '';
      this.pointerX = 0;
      this.pointerY = 0;
      window.clearTimeout(this._fxTimer);
      window.clearTimeout(this._hitTimer);
      window.clearTimeout(this._waitingTimer);
      window.clearTimeout(this._voltageTimer);
      window.clearTimeout(this._archiveTimer);
      window.clearTimeout(this._settleTimer);
      Object.values(this._nameTimers || {}).forEach((timer) => window.clearInterval(timer));
      this._nameTimers = {};
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
        voting: [],
        votingStage: null,
        tiebreakSteps: [],
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
          this.modelOutputs = {};
          this.participants = (ev.agents || []).map((a) => ({
            name: a.name,
            label: a.label,
            state: 'alive',
            lastRole: '',
            lastElapsed: 0,
          }));
          this.liveLabel = `第 1 轮即将开始 · ${this.participants.length} 位参赛`;
          this.beginStage('', '参赛阵容已就绪');
          this.playFx('run-start', 1450);
          this.$nextTick(this.setupStage);
          break;

        case 'agent_info': {
          let participant = this.participants.find((item) => item.name === ev.name);
          if (!participant) {
            participant = {
              name: ev.name,
              label: ev.label,
              state: 'alive',
              lastRole: '',
              lastElapsed: 0,
            };
            this.participants.push(participant);
          } else if (ev.label) {
            participant.label = ev.label;
          }
          this.decodeAgentName(ev.name);
          break;
        }

        case 'round_start': {
          const round = this.ensureRound(ev.no);
          this.modelOutputs = {};
          round.alive = ev.alive;
          round.order = ev.order || [];
          this.liveLabel = `第 ${ev.no} 轮 · ${ev.alive} 人存活`;
          this.beginStage('', `第 ${ev.no} 轮准备发言`);
          this.playFx('round-start', 550);
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
              round: this.currentRound || 1,
              seq: ++this.modelStreamSeq,
            },
          };
          this.setAgentState(ev.agent, 'thinking');
          this.liveLabel = `${ev.agent} 正在组织${ev.role}`;
          this.beginStage(ev.agent, `${ev.role}中，等待模型返回`);
          this.waitingMode = false;
          this.playFx('scan', 620);
          this.decodeAgentName(ev.agent);
          this.scrollDown();
          break;
        }

        case 'model_output': {
          const current = this.modelOutputs[ev.agent] || {
            agent: ev.agent,
            role: ev.role,
            text: '',
            round: this.currentRound || 1,
            seq: ++this.modelStreamSeq,
          };
          current.round = this.currentRound || current.round;
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
          this.pulseWaiting();
          break;

        case 'speech': {
          const round = this.ensureRound(this.currentRound || 1);
          round.thinking = round.thinking.filter((x) => x.agent !== ev.agent);
          round.speeches.push(ev);
          this.settledKey = `${round.no}-${round.speeches.length - 1}`;
          window.clearTimeout(this._settleTimer);
          this._settleTimer = window.setTimeout(() => { this.settledKey = ''; }, 420);
          const outputs = { ...this.modelOutputs };
          delete outputs[ev.agent];
          this.modelOutputs = outputs;
          delete this.modelOutputEls[ev.agent];
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
          this.waitingMode = false;
          this.playFx('settle', 380);
          this.sound('tick');
          this.scrollDown();
          break;
        }

        case 'voting_start': {
          const round = this.ensureRound(ev.round_no || this.currentRound || 1);
          round.votingStage = {
            stage: ev.stage || 'main',
            voters: ev.voters || 0,
            candidates: ev.candidates || [],
          };
          this.beginStage('', `${ev.voters} 位投票者正在判断本轮发言`);
          this.liveLabel = `第 ${ev.round_no} 轮 · ${this.voteStageLabel(ev.stage)}：${ev.voters} 位投票者`;
          this.liveVoteCounts = {};
          this.votingMode = true;
          this.waitingMode = false;
          this.playFx('voting-start', 680);
          break;
        }

        case 'voting': {
          const round = this.ensureRound(ev.round_no || this.currentRound || 1);
          const index = round.voting.findIndex(
            (item) => item.stage === ev.stage && item.voter === ev.voter,
          );
          const row = index >= 0 ? round.voting[index] : {};
          Object.assign(row, ev);
          if (index >= 0) round.voting.splice(index, 1, row);
          else round.voting.push(row);
          if (ev.status === 'thinking') {
            this.liveLabel = `${ev.voter} 正在判断谁的发言最站得住`;
            this.beginStage(ev.voter, `${this.voteStageLabel(ev.stage)}：正在判断`);
          } else if (ev.status === 'done') {
            this.liveLabel = `${ev.voter} 已投给 ${ev.target}`;
            this.beginStage(ev.voter, `${this.voteStageLabel(ev.stage)}：已投票`);
            this.pushActivity('voting', `${ev.voter} 投给 ${ev.target}`, ev.voter);
            if (ev.target) {
              this.liveVoteCounts = {
                ...this.liveVoteCounts,
                [ev.target]: (this.liveVoteCounts[ev.target] || 0) + 1,
              };
              this.emitVoteTrail(ev.voter, ev.target);
              this.flashHit(ev.target);
              this.sound('ding');
            }
          } else {
            this.liveLabel = `${ev.voter} 投票失败`;
            this.beginStage(ev.voter, `${this.voteStageLabel(ev.stage)}：投票失败`);
            this.pushActivity('voting', `${ev.voter} 投票失败：${ev.error || '未知错误'}`, ev.voter);
          }
          break;
        }

        case 'tiebreak': {
          const round = this.ensureRound(ev.round_no || this.currentRound || 1);
          const index = round.tiebreakSteps.findIndex((item) => item.attempt === ev.attempt);
          const step = index >= 0 ? round.tiebreakSteps[index] : {};
          Object.assign(step, ev);
          if (index >= 0) round.tiebreakSteps.splice(index, 1, step);
          else round.tiebreakSteps.push(step);
          this.beginStage('', `${ev.agents.join('、')} 平票，进入第 ${ev.attempt} 次加赛`);
          this.liveLabel = `第 ${ev.round_no} 轮 · ${ev.agents.join('、')} 平票加赛`;
          this.playFx('tiebreak', 850);
          this.scrollDown();
          break;
        }

        case 'tiebreak_result': {
          const round = this.ensureRound(ev.round_no || this.currentRound || 1);
          const step = round.tiebreakSteps.find((item) => item.attempt === ev.attempt);
          if (step) Object.assign(step, ev);
          this.liveLabel = `第 ${ev.round_no} 轮 · 第 ${ev.attempt} 次加赛投票完成`;
          this.beginStage('', '加赛票已收到，正在本地汇总');
          this.liveVoteCounts = {};
          break;
        }

        case 'votes': {
          const round = this.ensureRound(this.currentRound || 1);
          round.votes = ev;
          this.liveVoteCounts = {};
          this.votingMode = false;
          this.liveLabel = '票已收到，正在本地汇总票数';
          this.beginStage('', '票已收到，正在本地汇总票数');
          this.scrollDown();
          break;
        }

        case 'elimination': {
          const round = this.ensureRound(this.currentRound || 1);
          round.eliminated = ev;
          delete this.modelOutputs[ev.agent];
          this.setAgentState(ev.agent, 'out');
          this.liveLabel = `${ev.agent} 出局，转为评审`;
          this.beginStage(ev.agent, `${ev.agent} 出局，转为评审`);
          this.votingMode = false;
          this.liveVoteCounts = {};
          this.playFx('elimination', 1650);
          this.emitEliminationParticles(ev.agent);
          this.sound('thud');
          this.scrollDown();
          break;
        }

        case 'technical_exit': {
          const round = this.ensureRound(this.currentRound || 1);
          round.exits.push(ev);
          delete this.modelOutputs[ev.agent];
          this.setAgentState(ev.agent, 'out');
          this.liveLabel = `${ev.agent} 技术性退赛`;
          this.beginStage(ev.agent, `${ev.agent} 技术性退赛`);
          this.playFx('elimination', 1200);
          this.emitEliminationParticles(ev.agent);
          this.scrollDown();
          break;
        }

        case 'winner':
          this.winnerName = ev.agent;
          this.setAgentState(ev.agent, 'alive');
          this.liveLabel = `${ev.agent} 最终存活`;
          this.beginStage(ev.agent, `${ev.agent} 最终存活`);
          this.votingMode = false;
          this.waitingMode = false;
          this.playFx('winner', 1600);
          this.emitWinnerConfetti();
          this.sound('winner');
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
          this.archiveStamp = String(ev.paths?.[0] || 'debate.md').split('/').pop();
          window.clearTimeout(this._archiveTimer);
          this._archiveTimer = window.setTimeout(() => { this.archiveStamp = ''; }, 2800);
          this.playFx('saved', 1250);
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
          this.modelOutputs = {};
          this.elapsed = Number(ev.duration || this.elapsed);
          this.activeAgent = this.winnerName || '';
          this.activeStage = this.winnerName ? `${this.winnerName} 胜出` : '比赛结束';
          this.stageStartedAt = 0;
          this.votingMode = false;
          this.waitingMode = false;
          this.stopTimer();
          this.loadHistory();
          this.scrollDown();
          break;
      }
      if (!['waiting', 'model_output', 'voting'].includes(ev.kind)) {
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
          round.tiebreakSteps = record.tiebreak_steps || [];
          round.voting = [];
          round.votingStage = null;
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
        this.elapsed = Number(transcript.duration || 0);
        this.stageElapsed = Number(transcript.duration || 0);
        this.pushActivity('done', `载入历史提问：${transcript.proposition || id}`, transcript.winner || '');
        this.hint = '';
        this.scrollDown(true);
        this.$nextTick(() => {
          this.setupStage();
          this.drawStage(performance.now());
        });
      } catch (err) {
        this.hint = `历史回放失败：${err.message}`;
      }
    },

    voteStageLabel(stage) {
      if (!stage || stage === 'main') return '本轮投票';
      const match = String(stage).match(/^tiebreak-(\d+)$/);
      return match ? `第 ${match[1]} 次加赛投票` : String(stage);
    },

    voteStageGroups(votes) {
      const rows = votes?.rows || [];
      const groups = new Map();
      for (const row of rows) {
        const stage = row.stage || 'main';
        if (!groups.has(stage)) groups.set(stage, []);
        groups.get(stage).push(row);
      }
      return [...groups.entries()]
        .map(([stage, stageRows]) => ({
          stage,
          label: this.voteStageLabel(stage),
          rows: stageRows,
          counts: stageRows.reduce((counts, row) => {
            if (row.target) counts[row.target] = (counts[row.target] || 0) + 1;
            return counts;
          }, {}),
        }))
        .sort((a, b) => {
          if (a.stage === 'main') return -1;
          if (b.stage === 'main') return 1;
          return a.stage.localeCompare(b.stage, undefined, { numeric: true });
        });
    },

    liveVotingRows(round) {
      const stage = round.votingStage?.stage;
      if (!stage || !round.voting?.length) return [];
      if (round.votes?.rows?.some((row) => (row.stage || 'main') === stage)) return [];
      return round.voting
        .filter((row) => row.stage === stage)
        .sort((a, b) => Number(a.is_judge) - Number(b.is_judge) || a.voter.localeCompare(b.voter));
    },

    currentVoteStage(round) {
      const stage = round.votingStage?.stage;
      return stage ? this.voteStageLabel(stage) : '投票';
    },

    voteBars(counts) {
      const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
      const max = Math.max(1, ...entries.map((entry) => entry[1]));
      return entries.map(([name, count]) => ({
        name,
        count,
        lead: count > 0 && count === max,
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
