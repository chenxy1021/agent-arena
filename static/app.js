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

const RobotAvatar = {
  props: {
    name: { type: String, default: '' },
    color: { type: String, default: '#ff6b81' },
    state: { type: String, default: 'idle' },
    size: { type: [Number, String], default: 64 },
    spec: { type: Object, required: true },
  },
  template: `
    <svg class="robot-avatar" :class="'robot-' + state" :width="size" :height="size"
      :style="{ '--robot-color': color }" viewBox="0 0 64 64" role="img"
      :aria-label="name || '机器人头像'">
      <ellipse class="robot-shadow" cx="32" cy="57" rx="18" ry="4"/>

      <g class="robot-antenna">
        <template v-if="spec.antenna === 'straight'">
          <path d="M32 12V5"/><circle cx="32" cy="4" r="2"/>
        </template>
        <template v-else-if="spec.antenna === 'twin'">
          <path d="M25 12 21 5M39 12 43 5"/><circle cx="21" cy="4.5" r="1.7"/><circle cx="43" cy="4.5" r="1.7"/>
        </template>
        <template v-else-if="spec.antenna === 'ring'">
          <path d="M32 12V8"/><circle cx="32" cy="6" r="3.5"/>
        </template>
        <template v-else-if="spec.antenna === 'ball'">
          <path d="M32 12V8"/><circle cx="32" cy="6.5" r="2.6"/>
        </template>
      </g>

      <g class="robot-body">
        <rect v-if="spec.body === 'block'" x="22" y="38" width="20" height="15" rx="5"/>
        <circle v-else-if="spec.body === 'ball'" cx="32" cy="45" r="11"/>
        <polygon v-else-if="spec.body === 'trapezoid'" points="23,38 41,38 47,54 17,54"/>
        <path v-else d="M20 39h24l5 15H15z"/>
        <path v-if="Number(size) >= 72" class="robot-body-light" d="M27 42h10" />
      </g>

      <g class="robot-head">
        <rect v-if="spec.head === 'capsule'" x="17" y="13" width="30" height="24" rx="12"/>
        <rect v-else-if="spec.head === 'square'" x="16" y="14" width="32" height="23" rx="5"/>
        <polygon v-else-if="spec.head === 'hex'" points="22,12 42,12 50,25 42,38 22,38 14,25"/>
        <rect v-else-if="spec.head === 'crt'" x="14" y="14" width="36" height="24" rx="3"/>
        <polygon v-else-if="spec.head === 'trapezoid'" points="22,13 42,13 48,38 16,38"/>
        <circle v-else cx="32" cy="25" r="14"/>
        <rect class="robot-screen" x="21" y="20" width="22" height="11" rx="3"/>
      </g>

      <g v-if="state === 'out'" class="robot-eyes robot-x-eyes">
        <path d="m24 22 5 5m0-5-5 5M35 22l5 5m0-5-5 5"/>
      </g>
      <g v-else-if="state === 'thinking'" class="robot-eyes robot-loading-eyes">
        <circle cx="25" cy="25" r="2"/><circle cx="32" cy="25" r="2"/><circle cx="39" cy="25" r="2"/>
      </g>
      <g v-else class="robot-eyes">
        <rect v-if="spec.eyes === 'led'" x="24" y="23" width="16" height="4" rx="2"/>
        <template v-else-if="spec.eyes === 'round'"><circle cx="26" cy="25" r="3"/><circle cx="38" cy="25" r="3"/></template>
        <template v-else-if="spec.eyes === 'three'"><circle cx="24" cy="25" r="2"/><circle cx="32" cy="25" r="2"/><circle cx="40" cy="25" r="2"/></template>
        <template v-else-if="spec.eyes === 'pixel'">
          <rect x="23" y="21" width="4" height="4"/><rect x="29" y="21" width="4" height="4"/><rect x="35" y="21" width="4" height="4"/>
          <rect x="26" y="26" width="4" height="4"/><rect x="32" y="26" width="4" height="4"/>
        </template>
        <path v-else-if="spec.eyes === 'curve'" d="M23 25q5-5 9 0t9 0"/>
        <path v-else d="M23 22h18M23 25h18M23 28h18"/>
      </g>

      <g v-if="state === 'speaking'" class="robot-voice">
        <rect x="26" y="33" width="2" height="4"/><rect x="31" y="32" width="2" height="6"/><rect x="36" y="33" width="2" height="4"/>
      </g>

      <g v-if="Number(size) >= 48" class="robot-accessory">
        <path v-if="spec.accessory === 'headset'" d="M15 25a17 17 0 0 1 34 0M15 25v7h4v-7zm30 0v7h4v-7z"/>
        <polygon v-else-if="spec.accessory === 'tie'" points="32,38 28,42 32,51 36,42"/>
        <path v-else-if="spec.accessory === 'arm'" d="M42 43h9v3h-6l-3 4"/>
        <circle v-else-if="spec.accessory === 'gear'" cx="49" cy="45" r="5"/><path v-if="spec.accessory === 'gear'" d="M49 37v16M41 45h16"/>
        <path v-else-if="spec.accessory === 'scarf'" d="M22 38q10 5 20 0v5q-10 5-20 0z"/>
      </g>

      <g v-if="state === 'winner'" class="robot-halo">
        <ellipse cx="32" cy="8" rx="10" ry="3"/>
      </g>
    </svg>
  `,
};

Vue.createApp({
  components: { RollingNumber, TallyMarks, RobotAvatar },

  data() {
    return {
      proposition: '',
      currentPage: 'register',
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
      liveVoteCounts: {},
      decodedNames: {},
      archiveStamp: '',
      pointerX: 0,
      pointerY: 0,
      reducedMotion: false,
      stageWidth: 960,
      stageHeight: 680,
      tableIntro: false,
      venueScrolled: false,
      voteChips: [],
      voteChipSeq: 0,
      robotVariants: {},
      recordAgentFilter: '',
      recordRoundFilter: 0,
      focusBeforeModal: null,
      liveMessage: '',
    };
  },

  computed: {
    currentPageLabel() {
      return {
        register: '登记',
        venue: '会场',
        record: '记录',
        archive: '档案',
        models: '模型',
      }[this.currentPage] || '登记';
    },
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
    currentPaper() {
      if (this.final) {
        return {
          agent: this.final.agent,
          role: '最终裁决',
          round: 'FINAL',
          text: this.final.text,
          elapsed: this.elapsed,
          final: true,
        };
      }
      const stream = this.modelStreams[0];
      if (stream) {
        return {
          agent: stream.agent,
          role: stream.role,
          round: this.currentRound,
          text: stream.text,
          elapsed: this.stageElapsed,
        };
      }
      const round = this.rounds.find((item) => item.no === this.currentRound);
      const thinking = round?.thinking?.[0];
      if (thinking) {
        return {
          agent: thinking.agent,
          role: thinking.role,
          round: this.currentRound,
          text: '',
          elapsed: this.stageElapsed,
        };
      }
      return null;
    },
    tableVoteCounts() {
      const round = this.rounds.find((item) => item.no === this.currentRound);
      if (this.votingMode) return { ...this.liveVoteCounts };
      return { ...(round?.votes?.counts || {}) };
    },
    tableVoteTotal() {
      return Object.values(this.tableVoteCounts).reduce(
        (total, count) => total + Number(count || 0),
        0,
      );
    },
    recentVoteRows() {
      const round = this.rounds.find((item) => item.no === this.currentRound);
      const rows = [
        ...(round?.votes?.rows || []),
        ...(round?.voting || []).filter((row) => row.status === 'done'),
      ];
      const unique = new Map();
      rows.forEach((row) => {
        if (row.target) unique.set(`${row.stage || 'main'}-${row.voter}`, row);
      });
      return [...unique.values()].slice(-3).reverse();
    },
    paperTickCount() {
      return Math.max(1, Math.ceil((Number(this.timeout) || 240) / 30));
    },
    remainingTimeText() {
      const remaining = Math.max(0, Number(this.timeout) - this.stageElapsed);
      const min = String(Math.floor(remaining / 60)).padStart(2, '0');
      const sec = String(Math.floor(remaining % 60)).padStart(2, '0');
      return `${min}:${sec}`;
    },
    recordVisibleRounds() {
      let rounds = [...this.rounds];
      if (this.recordRoundFilter) {
        rounds = rounds.filter((round) => round.no === this.recordRoundFilter);
      }
      return rounds.sort((a, b) => b.no - a.no);
    },
    recordActiveRound() {
      if (this.recordRoundFilter) {
        return this.rounds.find((round) => round.no === this.recordRoundFilter) || null;
      }
      return this.rounds.find((round) => round.no === this.currentRound)
        || this.rounds[this.rounds.length - 1]
        || null;
    },
    recordAgents() {
      return this.participants.map((participant) => participant.name);
    },
    modelPreviewKey() {
      return this.modelForm.name || this.modelForm.model || 'new-model';
    },
    tableVoteTotal() {
      return Object.values(this.tableVoteCounts).reduce((total, count) => total + Number(count || 0), 0);
    },
    voteRingLabel() {
      const counts = this.participants
        .map((participant) => `${participant.name} ${this.tableVoteCounts[participant.name] || 0} 票`);
      return `当前票数：${counts.join('，')}，共 ${this.tableVoteTotal} 票`;
    },
  },

  mounted() {
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.soundOn = window.localStorage.getItem('arena-sound') === 'on';
    try {
      this.robotVariants = JSON.parse(window.localStorage.getItem('arena-robot-variants') || '{}');
    } catch (_) {
      this.robotVariants = {};
    }
    this.loadModels();
    this.loadHistory();
    this.applyRoute();
    if (!window.location.hash.startsWith('#record/')) this.attachActive();
    window.addEventListener('beforeunload', this.closeStream);
    window.addEventListener('beforeunload', this.teardownStage);
    window.addEventListener('resize', this.resizeStage);
    window.addEventListener('keydown', this.handleKeyDown);
    window.addEventListener('hashchange', this.applyRoute);
    window.addEventListener('scroll', this.handleScroll, { passive: true });
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
    window.removeEventListener('keydown', this.handleKeyDown);
    window.removeEventListener('hashchange', this.applyRoute);
    window.removeEventListener('scroll', this.handleScroll);
  },

  methods: {
    agentColor,

    newMatch() {
      this.resetArena();
      this.proposition = '';
      this.goPage('register');
    },

    roundNo(no) {
      return String(no).padStart(2, '0');
    },

    goPage(page, updateHash = true) {
      if (!['register', 'venue', 'record', 'archive', 'models'].includes(page)) return;
      this.currentPage = page;
      this.venueScrolled = false;
      if (updateHash) this.writeRoute(page);
      window.scrollTo({ top: 0, behavior: 'auto' });
      if (page === 'venue') this.$nextTick(this.setupStage);
    },

    robotHash(name) {
      const text = String(name || 'robot');
      let hash = 2166136261;
      for (let i = 0; i < text.length; i += 1) {
        hash ^= text.charCodeAt(i);
        hash = Math.imul(hash, 16777619);
      }
      hash ^= Number(this.robotVariants[text] || 0) + 0x9e3779b9;
      hash = Math.imul(hash ^ (hash >>> 16), 2246822507);
      hash = Math.imul(hash ^ (hash >>> 13), 3266489909);
      hash ^= hash >>> 16;
      return Math.abs(hash);
    },

    robotSpecWithin(name, names) {
      const heads = ['capsule', 'square', 'hex', 'crt', 'trapezoid', 'round'];
      const eyes = ['led', 'round', 'three', 'pixel', 'curve', 'grille'];
      const antennas = ['straight', 'twin', 'ring', 'ball', 'none'];
      const bodies = ['block', 'ball', 'trapezoid', 'shoulder'];
      const accessories = ['headset', 'tie', 'arm', 'gear', 'scarf', 'none'];
      const pool = [...new Set((names || [name]).map((item) => String(item || 'robot')))];
      const previous = [];
      let current = null;
      for (const key of pool) {
        const hash = this.robotHash(key);
        let candidate = null;
        for (let shift = 0; shift < 30; shift += 1) {
          candidate = {
            head: heads[hash % heads.length],
            eyes: eyes[(Math.floor(hash / 8) + shift) % eyes.length],
            antenna: antennas[(Math.floor(hash / 128) + shift * 2) % antennas.length],
            body: bodies[Math.floor(hash / 2048) % bodies.length],
            accessory: accessories[Math.floor(hash / 32768) % accessories.length],
          };
          const distinct = previous.every((other) => (
            Number(other.head !== candidate.head)
            + Number(other.eyes !== candidate.eyes)
            + Number(other.antenna !== candidate.antenna)
          ) >= 2);
          if (distinct) break;
        }
        current = candidate;
        if (key === name) return current;
        previous.push(current);
      }
      return current;
    },

    robotSpec(name) {
      const key = String(name || 'robot');
      const participantNames = this.participants.map((item) => item.name);
      const modelNames = this.models.map((item) => item.name);
      const pool = participantNames.includes(key)
        ? participantNames
        : modelNames.includes(key) ? modelNames : [key];
      return this.robotSpecWithin(key, pool);
    },

    robotState(name) {
      const participant = this.participants.find((item) => item.name === name);
      if (this.winnerName === name) return 'winner';
      if (participant?.state === 'out') return 'out';
      if (participant?.state === 'thinking') return 'thinking';
      if (this.running && this.activeAgent === name) return 'speaking';
      return 'idle';
    },

    rerollRobot(name) {
      const key = String(name || 'new-model');
      this.robotVariants = {
        ...this.robotVariants,
        [key]: Number(this.robotVariants[key] || 0) + 1,
      };
      window.localStorage.setItem('arena-robot-variants', JSON.stringify(this.robotVariants));
    },

    archiveRobots(item) {
      const names = Array.isArray(item.participant_names)
        ? item.participant_names.filter(Boolean)
        : [];
      if (!names.length && item.winner) names.push(item.winner);
      const eliminated = new Set(item.eliminated_names || []);
      return names.map((name) => ({
        name,
        winner: name === item.winner,
        out: eliminated.has(name),
        spec: this.robotSpecWithin(name, names),
      }));
    },

    selectRecordAgent(name) {
      this.recordAgentFilter = this.recordAgentFilter === name ? '' : name;
    },

    selectRecordRound(no) {
      this.recordRoundFilter = no;
      this.$nextTick(() => {
        document.querySelector(`[data-record-round="${no}"]`)?.scrollIntoView({
          behavior: this.reducedMotion ? 'auto' : 'smooth',
          block: 'start',
        });
      });
    },

    filteredSpeeches(round) {
      if (!this.recordAgentFilter) return round.speeches || [];
      return (round.speeches || []).filter((speech) => speech.agent === this.recordAgentFilter);
    },

    paperBlocks(text) {
      const blocks = this.speechBlocks(text);
      if (blocks.length === 1 && blocks[0].kind === 'plain' && String(text || '').includes('【结论】')) {
        return this.finalBlocks(text).map((block) => ({
          ...block,
          marker: block.label ? `【${block.label}】` : '',
        }));
      }
      return blocks.map((block) => ({
        ...block,
        marker: block.kind === 'view' ? '【观点】' : block.kind === 'critique' ? '【点评】' : '',
      }));
    },

    orderedAlive() {
      const alive = this.participants.filter((item) => item.state !== 'out');
      const activeIndex = alive.findIndex((item) => item.name === this.activeAgent);
      return activeIndex > 0 ? [...alive.slice(activeIndex), ...alive.slice(0, activeIndex)] : alive;
    },

    seatStyle(participant) {
      const alive = this.orderedAlive();
      const aliveIndex = alive.findIndex((item) => item.name === participant.name);
      if (participant.state === 'out' || aliveIndex < 0) {
        const outIndex = this.participants
          .filter((item) => item.state === 'out')
          .findIndex((item) => item.name === participant.name);
        const compact = window.innerWidth <= 720;
        return {
          '--seat-x': `${this.stageWidth * (-.36 + Math.max(0, outIndex) * .105)}px`,
          '--seat-y': `${-this.stageHeight * (compact ? .34 : .39)}px`,
          '--seat-scale': .58,
          '--seat-width': '100px',
          '--seat-z': 72 + outIndex,
          '--seat-order': outIndex,
        };
      }
      const angle = (90 + (aliveIndex * 360) / Math.max(1, alive.length)) * (Math.PI / 180);
      const depth = (Math.sin(angle) + 1) / 2;
      const compact = window.innerWidth <= 720;
      return {
        '--seat-x': `${Math.cos(angle) * this.stageWidth * (compact ? .41 : .4)}px`,
        '--seat-y': `${compact
          ? -this.stageHeight * .205 + Math.sin(angle) * 105
          : this.stageHeight * (.07 + Math.sin(angle) * .25)}px`,
        '--seat-scale': (.84 + depth * .16).toFixed(3),
        '--seat-width': alive.length >= 8 ? '104px' : alive.length >= 7 ? '118px' : '132px',
        '--seat-label-x': compact
          ? `${Math.cos(angle) > .35 ? -90 : Math.cos(angle) < -.35 ? -10 : -50}%`
          : '-50%',
        '--seat-z': Math.round(20 + depth * 50),
        '--seat-order': aliveIndex,
      };
    },

    seatPoint(name) {
      const participant = this.participants.find((item) => item.name === name);
      if (!participant) return { x: 500, y: 310 };
      if (participant.state === 'out') {
        const outIndex = this.participants
          .filter((item) => item.state === 'out')
          .findIndex((item) => item.name === name);
        return { x: 760 + Math.max(0, outIndex) * 55, y: 90 };
      }
      const alive = this.orderedAlive();
      const index = alive.findIndex((item) => item.name === name);
      const angle = (90 + (index * 360) / Math.max(1, alive.length)) * (Math.PI / 180);
      return {
        x: 500 + Math.cos(angle) * 410,
        y: 310 + Math.sin(angle) * 155,
      };
    },

    rimSpotStyle() {
      const alive = this.orderedAlive();
      let index = alive.findIndex((item) => item.name === this.activeAgent);
      if (index < 0) index = 0;
      const target = (
        (Math.PI / 2 + (index * Math.PI * 2) / Math.max(1, alive.length))
        + Math.PI * 2
      ) % (Math.PI * 2);
      const rx = 420;
      const ry = 155;
      const steps = 240;
      let total = 0;
      let walked = 0;
      let previous = { x: rx, y: 0 };
      for (let step = 1; step <= steps; step += 1) {
        const angle = (step / steps) * Math.PI * 2;
        const point = { x: rx * Math.cos(angle), y: ry * Math.sin(angle) };
        const segment = Math.hypot(point.x - previous.x, point.y - previous.y);
        total += segment;
        if (angle <= target) walked += segment;
        previous = point;
      }
      const fraction = total ? walked / total : 0;
      return {
        strokeDasharray: '.06 .94',
        strokeDashoffset: String(-fraction + .03),
        opacity: this.running && alive.length ? 1 : 0,
      };
    },

    voteChipPath(chip) {
      const from = this.seatPoint(chip.voter);
      const to = this.seatPoint(chip.target);
      const midX = (from.x + to.x) / 2;
      const midY = Math.min(from.y, to.y) + 26;
      return `M ${from.x} ${from.y} Q ${midX} ${midY} ${to.x} ${to.y}`;
    },

    addVoteChip(voter, target) {
      if (!voter || !target || voter === target) return;
      const id = ++this.voteChipSeq;
      this.voteChips = [
        ...this.voteChips.slice(-8),
        { id, voter, target, color: agentColor(target) },
      ];
      window.setTimeout(() => {
        this.voteChips = this.voteChips.filter((chip) => chip.id !== id);
      }, 900);
    },

    voteArcStyle(name, index) {
      const radius = 76;
      const circumference = 2 * Math.PI * radius;
      const values = this.participants.map((item) => Number(this.tableVoteCounts[item.name] || 0));
      const total = Math.max(1, values.reduce((sum, value) => sum + value, 0));
      const before = values.slice(0, index).reduce((sum, value) => sum + value, 0);
      const length = (values[index] / total) * circumference;
      return {
        strokeDasharray: `${length} ${circumference - length}`,
        strokeDashoffset: `${-((before / total) * circumference)}`,
        opacity: values[index] > 0 ? .95 : .12,
      };
    },

    parseRoute() {
      const raw = decodeURIComponent(window.location.hash.replace(/^#/, ''));
      const [page, id = ''] = raw.split('/');
      return {
        page: ['register', 'venue', 'record', 'archive', 'models'].includes(page)
          ? page
          : 'register',
        id,
      };
    },

    writeRoute(page, id = '') {
      const next = `#${page}${id ? `/${encodeURIComponent(id)}` : ''}`;
      if (window.location.hash !== next) window.history.pushState(null, '', next);
    },

    applyRoute() {
      const route = this.parseRoute();
      this.currentPage = route.page;
      this.venueScrolled = false;
      if (route.page === 'record' && route.id && this.viewingHistoryId !== route.id) {
        this.loadHistoryRun(route.id, { updateHash: false });
      }
      if (route.page === 'venue') this.$nextTick(this.setupStage);
    },

    handleScroll() {
      this.venueScrolled = this.currentPage === 'venue' && window.scrollY > 120;
    },

    handleKeyDown(event) {
      if (event.key === 'Escape' && this.showModelModal) {
        event.preventDefault();
        this.closeModelModal();
        return;
      }
      if (event.key !== 'Tab' || !this.showModelModal || !this.$refs.modelModal) return;
      const focusable = [...this.$refs.modelModal.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!this.$refs.modelModal.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },

    startTableIntro() {
      if (this.replaying || this.reducedMotion) return;
      window.clearTimeout(this._tableIntroTimer);
      this.tableIntro = true;
      this._tableIntroTimer = window.setTimeout(() => {
        this.tableIntro = false;
      }, 2550);
    },

    scoreFor(name) {
      return Number(this.scoreByName[name] || 0) + Number(this.liveVoteCounts[name] || 0);
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

    setupStage() {
      const stage = this.$refs.stage;
      if (!stage) return;
      const rect = stage.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      this.stageWidth = rect.width;
      this.stageHeight = rect.height;
    },

    resizeStage() {
      window.clearTimeout(this._resizeTimer);
      this._resizeTimer = window.setTimeout(() => this.setupStage(), 160);
    },

    teardownStage() {
      window.clearTimeout(this._resizeTimer);
      window.clearTimeout(this._fxTimer);
      window.clearTimeout(this._hitTimer);
      window.clearTimeout(this._waitingTimer);
      window.clearTimeout(this._archiveTimer);
      window.clearTimeout(this._tableIntroTimer);
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
      this.focusBeforeModal = document.activeElement;
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
      this.$nextTick(() => {
        this.$refs.modelModal?.querySelector('input, textarea, button')?.focus();
      });
    },

    editModelInline(model = null) {
      this.openModelModal(model);
      this.showModelModal = false;
    },

    closeModelModal() {
      if (this.savingModel) return;
      this.showModelModal = false;
      this.editingModelId = 0;
      this.hintOk = false;
      this.$nextTick(() => {
        if (this.focusBeforeModal instanceof HTMLElement) this.focusBeforeModal.focus();
        this.focusBeforeModal = null;
      });
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
      this.liveVoteCounts = {};
      this.decodedNames = {};
      this.archiveStamp = '';
      this.liveMessage = '';
      this.tableIntro = false;
      this.voteChips = [];
      this.pointerX = 0;
      this.pointerY = 0;
      window.clearTimeout(this._fxTimer);
      window.clearTimeout(this._hitTimer);
      window.clearTimeout(this._waitingTimer);
      window.clearTimeout(this._archiveTimer);
      window.clearTimeout(this._tableIntroTimer);
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
      this.goPage('venue');
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
          this.liveMessage = '比赛开始，第 1 轮即将发言';
          this.beginStage('', '参赛阵容已就绪');
          this.startTableIntro();
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
          this.liveMessage = `第 ${ev.no} 轮开始，在场 ${ev.alive} 人`;
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
          this.liveMessage = `${ev.agent} 开始${ev.role}`;
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
              this.flashHit(ev.target);
              this.addVoteChip(ev.voter, ev.target);
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
          this.liveMessage = `${ev.agent} 出局`;
          this.beginStage(ev.agent, `${ev.agent} 出局，转为评审`);
          this.votingMode = false;
          this.liveVoteCounts = {};
          this.playFx('elimination', 1650);
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
          this.liveMessage = `${ev.agent} 技术性退赛`;
          this.beginStage(ev.agent, `${ev.agent} 技术性退赛`);
          this.playFx('elimination', 1200);
          this.scrollDown();
          break;
        }

        case 'winner':
          this.winnerName = ev.agent;
          this.setAgentState(ev.agent, 'alive');
          this.liveLabel = `${ev.agent} 最终存活`;
          this.liveMessage = `${ev.agent} 获胜`;
          this.beginStage(ev.agent, `${ev.agent} 最终存活`);
          this.votingMode = false;
          this.waitingMode = false;
          this.playFx('winner', 1600);
          this.sound('winner');
          break;

        case 'final':
          this.final = ev;
          this.rounds.forEach((round) => { round.thinking = []; });
          this.setAgentState(ev.agent, 'alive');
          this.liveLabel = `${ev.agent} 正在整理最终结论`;
          this.liveMessage = `${ev.agent} 正在整理最终结论`;
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
          this.tableIntro = false;
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
        this.goPage('venue');
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

    async loadHistoryRun(id, options = {}) {
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
        this.currentRound = Math.max(0, ...((transcript.rounds || []).map((r) => Number(r.no) || 0)));
        this.liveLabel = '历史战报已载入';
        this.activeAgent = transcript.winner || '';
        this.activeStage = '历史回放完成';
        this.elapsed = Number(transcript.duration || 0);
        this.stageElapsed = Number(transcript.duration || 0);
        this.pushActivity('done', `载入历史提问：${transcript.proposition || id}`, transcript.winner || '');
        this.hint = '';
        this.currentPage = 'record';
        if (options.updateHash !== false) this.writeRoute('record', id);
        this.scrollDown(true);
        this.$nextTick(() => {
          this.setupStage();
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
