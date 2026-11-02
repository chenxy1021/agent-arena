/* Agent Arena 前端：Vue 3，无构建。
   主题：全息议事舱。颜色属于模型，不属于界面。 */

const PALETTE = [
  '#FFB020', '#7C6BFF', '#46D0FF', '#C8F04A', '#FF6E4A', '#A8B4C4',
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

// 纯前端假数据：只用于本地预览与布局验证，不发起任何模型请求。
const DEMO_MODELS = [
  { id: 901, name: 'GPT-5', base_url: 'https://api.openai.com/v1', model: 'gpt-5', checked: true },
  { id: 902, name: 'Claude', base_url: 'https://api.anthropic.com/v1', model: 'claude-opus-4', checked: true },
  { id: 903, name: 'Gemini', base_url: 'https://generativelanguage.googleapis.com/v1', model: 'gemini-2.5-pro', checked: true },
  { id: 904, name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat', checked: true },
];

const DEMO_VIEW = '【观点】从成本结构看，真正的瓶颈不在技术而在单位经济模型。'
  + '前期投入换来的边际成本下降需要订单量支撑，否则规模只是昂贵的猜测。'
  + '【点评】把问题从技术拉回商业本质，这个视角有价值，但没有给出可验证的数据来源，结论悬空。';

const DEMO_VOTES = [
  ['GPT-5', 'Claude', '这一方的证据链最完整，反方可验证数据最少'],
  ['Claude', 'GPT-5', '结论过于依赖宏观判断，缺少可执行的第一步'],
  ['Gemini', 'GPT-5', '把范围收敛到一类用户后，转化率通常会提升'],
  ['DeepSeek', 'Claude', '忽略了执行成本，方案在真实场景里很难推下去'],
];

const DEMO_PERSONAS = ['', '审计员', '', '务实派'];

const DEMO_CLAIMS = [
  '先收定金再交付，不要免费定制',
  '效果分成需要可审计的归因口径',
  '单客贡献毛利比客户数更重要',
  '服务即研发，从付费里长产品',
];

const DEMO_SCORES = {
  'GPT-5': { 论证: 8, 证据: 6, 可执行: 9, 增量: 7 },
  Claude: { 论证: 6, 证据: 8, 可执行: 5, 增量: 9 },
  Gemini: { 论证: 7, 证据: 5, 可执行: 8, 增量: 6 },
  DeepSeek: { 论证: 5, 证据: 7, 可执行: 4, 增量: 8 },
};

const DEMO_HISTORY = [
  {
    id: 'demo-1', proposition: '远程办公是否应该永久化', status: 'done',
    winner: 'GPT-5', participants: 4, round_count: 3, duration: 252,
    started_at: '2026-11-01 21:42:00',
    participant_names: ['GPT-5', 'Claude', 'Gemini', 'DeepSeek'],
  },
  {
    id: 'demo-2', proposition: '是否应该开源内部工具', status: 'done',
    winner: 'Claude', participants: 3, round_count: 2, duration: 168,
    started_at: '2026-11-01 20:15:00',
    participant_names: ['Claude', 'GPT-5', 'Gemini'],
  },
  {
    id: 'demo-3', proposition: '用 Rust 重写核心服务', status: 'error',
    winner: null, participants: 2, round_count: 1, duration: 63,
    started_at: '2026-11-01 16:42:00',
    participant_names: ['Gemini', 'GPT-5'],
  },
];

const RollingNumber = {
  props: { text: { type: String, default: '0' } },
  computed: {
    chars() { return String(this.text).split(''); },
  },
  methods: {
    isDigit(char) { return /\d/.test(char); },
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

// 方块票位：圆桌、记录页共用。
const TallyBlocks = {
  components: { RollingNumber },
  props: {
    count: { type: Number, default: 0 },
    color: { type: String, default: 'currentColor' },
  },
  computed: {
    blocks() { return Math.min(5, Math.max(0, Number(this.count) || 0)); },
    extra() { return Math.max(0, (Number(this.count) || 0) - this.blocks); },
  },
  template: `
    <span class="tally-blocks" :style="{ color: color }">
      <i v-for="n in blocks" :key="n"></i>
      <em v-if="extra">+{{ extra }}</em>
      <em v-if="count">{{ count }}</em>
    </span>
  `,
};

// 线框全息机器人：去掉搪瓷填充，只留描边 + 发光面罩。
const RobotAvatar = {
  props: {
    name: { type: String, default: '' },
    color: { type: String, default: '#3DE8C0' },
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

// 圆桌座位的头纹：从上方看的头部 + 面罩。
const TopPiece = {
  props: {
    name: { type: String, default: '' },
    color: { type: String, default: '#3DE8C0' },
    state: { type: String, default: 'idle' },
    size: { type: [Number, String], default: 44 },
    spec: { type: Object, required: true },
  },
  template: `
    <svg class="piece-top-svg" :width="size" :height="size"
      :style="{ '--robot-color': color }" viewBox="0 0 64 64" role="img"
      :aria-label="name || '席位'">
      <g class="piece-antenna">
        <template v-if="spec.antenna === 'straight'">
          <path d="M32 18V8"/><circle cx="32" cy="6" r="3"/>
        </template>
        <template v-else-if="spec.antenna === 'twin'">
          <path d="M24 20 18 8M40 20 46 8"/><circle cx="18" cy="6" r="2.4"/><circle cx="46" cy="6" r="2.4"/>
        </template>
        <template v-else-if="spec.antenna === 'ring'">
          <path d="M32 18v-5"/><circle cx="32" cy="9" r="5"/>
        </template>
        <template v-else-if="spec.antenna === 'ball'">
          <path d="M32 18v-4"/><circle cx="32" cy="10" r="3.6"/>
        </template>
      </g>

      <g class="piece-crown">
        <rect v-if="spec.head === 'capsule'" x="13" y="18" width="38" height="30" rx="15"/>
        <rect v-else-if="spec.head === 'square'" x="12" y="20" width="40" height="28" rx="6"/>
        <polygon v-else-if="spec.head === 'hex'" points="32,14 48,22 48,42 32,50 16,42 16,22"/>
        <rect v-else-if="spec.head === 'crt'" x="10" y="20" width="44" height="28" rx="5"/>
        <polygon v-else-if="spec.head === 'trapezoid'" points="18,19 46,19 51,48 13,48"/>
        <circle v-else cx="32" cy="34" r="18"/>
      </g>

      <g class="piece-visor" v-if="state !== 'out'">
        <rect v-if="spec.eyes === 'led'" x="20" y="30" width="24" height="6" rx="3"/>
        <template v-else-if="spec.eyes === 'round'">
          <circle cx="25" cy="33" r="4"/><circle cx="39" cy="33" r="4"/>
        </template>
        <template v-else-if="spec.eyes === 'three'">
          <circle cx="24" cy="33" r="3"/><circle cx="32" cy="33" r="3"/><circle cx="40" cy="33" r="3"/>
        </template>
        <template v-else-if="spec.eyes === 'pixel'">
          <rect x="21" y="27" width="6" height="5"/><rect x="29" y="27" width="6" height="5"/><rect x="37" y="27" width="6" height="5"/>
          <rect x="25" y="34" width="6" height="5"/><rect x="33" y="34" width="6" height="5"/>
        </template>
        <path v-else-if="spec.eyes === 'curve'" d="M21 34q5-6 11 0t11 0"/>
        <template v-else>
          <rect x="21" y="27" width="22" height="4" rx="2"/>
          <rect x="21" y="33" width="22" height="4" rx="2"/>
        </template>
      </g>

      <g v-else class="piece-visor piece-x-eyes">
        <path d="m24 29 6 6m0-6-6 6M34 29l6 6m0-6-6 6"/>
      </g>

      <g v-if="state === 'speaking'" class="piece-wave">
        <rect x="28" y="42" width="2" height="6" rx="1"/>
        <rect x="32" y="40" width="2" height="8" rx="1"/>
        <rect x="36" y="42" width="2" height="6" rx="1"/>
      </g>

      <ellipse v-if="state === 'winner'" class="piece-halo" cx="32" cy="34" rx="27" ry="27"/>
    </svg>
  `,
};

// 加权票位：整块 = 1.0 票，半高方块 = 0.5 票。评审票用半高块区分。
const WeightedTally = {
  props: {
    count: { type: Number, default: 0 },
    color: { type: String, default: 'currentColor' },
  },
  computed: {
    total() { return Math.max(0, Number(this.count) || 0); },
    full() { return Math.floor(this.total); },
    half() { return this.total - this.full >= 0.5; },
    label() { return `${this.total.toFixed(1)} 票`; },
  },
  template: `
    <span class="weighted-tally" :style="{ color: color }"
      role="img" :aria-label="label">
      <i v-for="n in full" :key="'f' + n" class="weighted-tally__block"></i>
      <i v-if="half" class="weighted-tally__block weighted-tally__block--half"></i>
      <em>{{ total.toFixed(1) }}</em>
    </span>
  `,
};

// 四维评分矩阵：纯表格，明度阶梯表示分数高低。
const SCORE_DIMS = ['论证', '证据', '可执行', '增量'];

const ScoreMatrix = {
  props: {
    scores: { type: Object, default: () => ({}) },
    dims: { type: Array, default: () => SCORE_DIMS },
    sortable: { type: Boolean, default: true },
  },
  data() {
    return { sortKey: 'avg', sortDir: -1 };
  },
  computed: {
    rows() {
      const dims = this.dims;
      const list = Object.entries(this.scores || {}).map(([name, map]) => {
        const values = dims.map((dim) => Number(map?.[dim] ?? NaN));
        const valid = values.filter((v) => Number.isFinite(v));
        const avg = valid.length ? valid.reduce((a, b) => a + b, 0) / valid.length : 0;
        return { name, map, values, avg };
      });
      const key = this.sortKey;
      return list.sort((a, b) => {
        const av = key === 'avg' ? a.avg : Number(a.map?.[key] ?? -1);
        const bv = key === 'avg' ? b.avg : Number(b.map?.[key] ?? -1);
        return (av - bv) * this.sortDir || a.name.localeCompare(b.name);
      });
    },
    bestAvg() {
      return this.rows.reduce((max, row) => Math.max(max, row.avg), 0);
    },
  },
  methods: {
    sortBy(key) {
      if (!this.sortable) return;
      if (this.sortKey === key) {
        this.sortDir = -this.sortDir;
        return;
      }
      this.sortKey = key;
      this.sortDir = key === 'avg' ? -1 : -1;
    },
    barOpacity(value) {
      const v = Number(value);
      if (!Number.isFinite(v)) return 0;
      const level = Math.max(1, Math.min(5, Math.ceil(v / 2)));
      return [0.2, 0.4, 0.6, 0.8, 1][level - 1];
    },
  },
  template: `
    <table class="score-matrix">
      <thead>
        <tr>
          <th scope="col">模型</th>
          <th v-for="dim in dims" :key="dim" scope="col"
            :class="{ sortable: sortable, active: sortKey === dim }"
            @click="sortBy(dim)">
            {{ dim }}
            <span class="score-matrix__hint" :title="dim + ' = 论据与结论的匹配程度'">?</span>
          </th>
          <th scope="col" :class="{ sortable: sortable, active: sortKey === 'avg' }"
            @click="sortBy('avg')">均分</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.name">
          <th scope="row">{{ row.name }}</th>
          <td v-for="(value, index) in row.values" :key="dims[index]">
            <span class="score-cell"
              :aria-label="row.name + ' ' + dims[index] + ' ' + (Number.isFinite(value) ? value : '无') + ' 分'">
              <i class="score-cell__bar" aria-hidden="true"
                :style="{ opacity: barOpacity(value) }"></i>
              <em>{{ Number.isFinite(value) ? value.toFixed(1) : '—' }}</em>
            </span>
          </td>
          <td class="score-matrix__avg"
            :class="{ lead: row.avg > 0 && row.avg === bestAvg }">{{ row.avg.toFixed(1) }}</td>
        </tr>
      </tbody>
    </table>
  `,
};

// 主张台账：台账 / 谱系双形态。
const ClaimLedger = {
  components: { RobotAvatar },
  props: {
    claims: { type: Array, default: () => [] },
    view: { type: String, default: 'table' },
    narrow: { type: Boolean, default: false },
  },
  computed: {
    counts() {
      const out = { adopted: 0, dormant: 0, rejected: 0 };
      for (const claim of this.claims) {
        if (claim.final_status === 'adopted') out.adopted += 1;
        else if (claim.final_status === 'rejected') out.rejected += 1;
        else out.dormant += 1;
      }
      return out;
    },
    rows() {
      return [...this.claims].sort((a, b) => (a.round || 0) - (b.round || 0));
    },
    lineage() {
      return this.rows.filter((claim) => (claim.challengers || []).length
        || (claim.supporters || []).length);
    },
  },
  methods: {
    statusLabel(status) {
      if (status === 'adopted') return '采纳';
      if (status === 'rejected') return '已否定';
      return '未决';
    },
    statusClass(status) {
      if (status === 'adopted') return 'is-adopted';
      if (status === 'rejected') return 'is-rejected';
      return 'is-dormant';
    },
    agentColor,
  },
  template: `
    <div class="claim-ledger">
      <header class="claim-ledger__head">
        <h3>主张台账</h3>
        <p class="claim-ledger__counts">
          采纳 {{ counts.adopted }} · 未决 {{ counts.dormant }} · 已否定 {{ counts.rejected }}
        </p>
      </header>

      <table v-if="view === 'table'" class="claim-ledger__table">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">主张</th>
            <th scope="col">提出</th>
            <th v-if="!narrow" scope="col">轮</th>
            <th scope="col">被谁挑战</th>
            <th scope="col">结局</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="claim in rows" :key="claim.claim_id" :class="statusClass(claim.final_status)">
            <td class="claim-ledger__id">{{ claim.claim_id }}</td>
            <td class="claim-ledger__text" :title="claim.text">{{ claim.text }}</td>
            <td>
              <span class="claim-ledger__who">
                <i class="claim-ledger__chip" :style="{ '--team-color': agentColor(claim.author) }"
                  aria-hidden="true"></i>{{ claim.author }}
              </span>
            </td>
            <td v-if="!narrow" class="claim-ledger__round">{{ claim.round }}</td>
            <td>
              <span class="claim-ledger__challengers">
                <i v-for="name in (claim.challengers || [])" :key="'c' + name"
                  class="claim-ledger__chip" :style="{ '--team-color': agentColor(name) }"
                  :title="name" :aria-label="name + ' 挑战'"></i>
                <em v-if="!(claim.challengers || []).length">—</em>
              </span>
            </td>
            <td class="claim-ledger__status">{{ statusLabel(claim.final_status) }}</td>
          </tr>
        </tbody>
      </table>

      <div v-else class="claim-lineage">
        <p v-if="!lineage.length" class="empty-copy">还没有被挑战过的主张。</p>
        <ul v-else class="claim-lineage__list">
          <li v-for="claim in lineage" :key="'l' + claim.claim_id" class="claim-node">
            <span class="claim-node__round">第 {{ claim.round }} 轮</span>
            <span class="claim-node__body">
              <b>{{ claim.text }}</b>
              <small>
                {{ claim.author }} 提出
                <template v-if="(claim.challengers || []).length">
                  · 被 {{ claim.challengers.join('、') }} 挑战
                </template>
              </small>
            </span>
            <span class="claim-node__status" :class="statusClass(claim.final_status)">
              {{ statusLabel(claim.final_status) }}
            </span>
          </li>
        </ul>
      </div>
    </div>
  `,
};

// 立场离散度计：无数据时整体隐藏。
const SpreadGauge = {
  props: {
    spread: { type: Number, default: null },
    threshold: { type: Number, default: 25 },
  },
  computed: {
    visible() { return Number.isFinite(this.spread); },
    ratio() { return Math.max(0, Math.min(1, (this.spread || 0) / 100)); },
    state() {
      if (!this.visible) return '';
      if (this.spread <= this.threshold) return 'is-converged';
      if (this.spread >= 150) return 'is-diverged';
      return '';
    },
    text() {
      if (!this.visible) return '';
      if (this.spread <= this.threshold) return '已收敛';
      if (this.spread >= 150) return '分歧大';
      return '';
    },
  },
  template: `
    <span v-if="visible" class="spread-gauge" :class="state"
      role="meter" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="spread"
      :aria-valuetext="'极差 ' + spread + '，收敛阈值 ' + threshold">
      <span class="spread-gauge__label">立场离散</span>
      <span class="spread-gauge__track" aria-hidden="true">
        <i :style="{ transform: 'scaleX(' + ratio + ')' }"></i>
        <b :style="{ left: (threshold / 100 * 100) + '%' }"></b>
      </span>
      <em>{{ spread }}</em>
      <small v-if="text">{{ text }}</small>
    </span>
  `,
};

Vue.createApp({
  components: {
    RollingNumber, TallyBlocks, WeightedTally, ScoreMatrix, ClaimLedger,
    SpreadGauge, RobotAvatar, TopPiece,
  },

  data() {
    return {
      navItems: [
        ['register', '登记'],
        ['venue', '会场'],
        ['record', '记录'],
        ['archive', '档案'],
        ['models', '模型'],
      ],
      proposition: '',
      currentPage: 'register',
      mode: 'eliminate',
      timeout: 240,
      speechMode: 'parallel_buffered',
      background: '',
      constraints: [],
      criteria: [],
      propOpen: { context: false, criteria: false },
      constraintDraft: '',
      criterionDraft: '',
      budget: null,
      spread: null,
      parallelRows: [],
      parallelRound: 0,
      parallelReplayNote: false,
      claims: [],
      claimView: 'table',
      roundScores: {},
      scoreSort: 'avg',
      stopArmed: false,
      archiveMode: 'ledger',
      compareIds: [],
      persona: '',
      models: [],
      modelsLoading: true,
      showModelModal: false,
      savingModel: false,
      namingModel: false,
      hintOk: false,
      hintError: false,
      editingModelId: 0,
      modelForm: {
        name: '',
        base_url: '',
        api_key: '',
        model: '',
        system_prompt: '',
        temperature: '',
        persona: '',
      },
      history: [],
      historyLoading: true,
      viewingHistoryId: '',
      canReuseCurrentRun: false,
      participants: [],
      rounds: [],
      currentRound: 0,
      final: null,
      winnerName: '',
      status: 'idle',
      statusText: '待命',
      stopReason: '',
      converged: false,
      liveLabel: '等待开始',
      running: false,
      replaying: false,
      hint: '',
      eventSource: null,
      activeRunId: '',
      eventCount: 0,
      startedAt: 0,
      elapsed: 0,
      activeAgent: '',
      activeStage: '',
      stageStartedAt: 0,
      stageElapsed: 0,
      modelOutputs: {},
      modelStreamSeq: 0,
      timer: null,
      soundOn: false,
      soundSpun: false,
      lang: 'zh',
      votingMode: false,
      waitingMode: false,
      waitingSeconds: 0,
      tiebreakState: null,
      speechArchived: false,
      eventFx: '',
      hitAgent: '',
      liveVoteCounts: {},
      decodedNames: {},
      archiveStamp: '',
      reducedMotion: false,
      sceneWidth: 1200,
      sceneHeight: 680,
      robotVariants: {},
      recordAgentFilter: '',
      recordRoundFilter: 0,
      focusBeforeModal: null,
      stances: {},
      priorStances: {},
      voteRays: [],
      voteRaySeq: 0,
      previewMorph: false,
      expandedSeats: false,
      streamText: '',
      streamTarget: '',
      lastPaper: null,
      panelError: '',
      seatFx: {},
      tiebreakAgents: [],
      introHint: '',
      rayBright: false,
      eliminatedInfo: null,
      narrow: false,
      expandedBallots: {},
      navIndicator: { left: 0, width: 24 },
    };
  },

  computed: {
    selectedModelIds() {
      return this.models.filter((m) => m.checked).map((m) => m.id);
    },

    aliveCount() {
      return this.participants.filter((item) => item.state !== 'out').length;
    },

    navIndicatorStyle() {
      return { transform: `translateX(${this.navIndicator.left}px)`, width: `${this.navIndicator.width}px` };
    },

    ruleIndicatorStyle() {
      const active = this.mode === 'support' ? 1 : 0;
      return { transform: `translateX(${active * 100}%)`, width: '50%' };
    },

    sceneSize() {
      return { w: Math.max(1, this.sceneWidth), h: Math.max(1, this.sceneHeight) };
    },

    sceneStyle() {
      return {
        '--scene-w': `${this.sceneWidth}px`,
        '--scene-h': `${this.sceneHeight}px`,
      };
    },

    stageScale() {
      return Math.min(1, this.sceneWidth / 1160, this.sceneHeight / 900).toFixed(3);
    },

    fxClass() {
      return this.eventFx ? `fx-${this.eventFx}` : '';
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

    remainingPercent() {
      const total = Math.max(1, Number(this.timeout) || 240);
      return Math.max(0, Math.min(100, ((total - this.stageElapsed) / total) * 100));
    },

    remainingTimeText() {
      const remaining = Math.max(0, Number(this.timeout) - this.stageElapsed);
      const min = String(Math.floor(remaining / 60)).padStart(2, '0');
      const sec = String(Math.floor(remaining % 60)).padStart(2, '0');
      return `${min}:${sec}`;
    },

    votingProgressLabel() {
      const round = this.rounds.find((item) => item.no === this.currentRound);
      const total = Number(round?.votingStage?.voters || 0);
      const done = (round?.voting || []).filter(
        (row) => row.stage === round?.votingStage?.stage
          && (row.status === 'done' || row.status === 'error'),
      ).length;
      const started = Number(round?.votingStage?.startedAt || 0);
      const waited = started ? Math.max(0, Math.floor((Date.now() - started) / 1000)) : 0;
      return total
        ? `已投 ${done}/${total} · 已等待 ${waited}s · 同时投票`
        : '正在同时投票';
    },

    tiebreakActive() {
      return Boolean(
        this.tiebreakState
        && !['decided', 'failed', 'cleared'].includes(this.tiebreakState.status),
      );
    },

    tiebreakProgressLabel() {
      const state = this.tiebreakState;
      if (!state) return '';
      const agents = (state.agents || []).join(' / ');
      const stage = state.status === 'speaking'
        ? '加赛发言'
        : state.status === 'tied' ? '仍平票' : '加赛投票';
      const progress = state.status === 'voting' ? ` · ${this.votingProgressLabel}` : '';
      return `第 ${state.attempt} 次加赛 · ${agents} · ${stage}${progress}`;
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
      if (this.parallelVisible) return null;
      const stream = this.modelStreams[0];
      if (stream) {
        return {
          agent: stream.agent,
          role: stream.role,
          round: this.currentRound,
          text: this.streamText,
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

    // 投影面板的流式正文：每 45ms 吐 6–9 个字，不做逐字打字机。
    paperText() {
      return this.streamText;
    },

    tableVoteCounts() {
      const round = this.rounds.find((item) => item.no === this.currentRound);
      if (this.votingMode) return { ...this.liveVoteCounts };
      return { ...(round?.votes?.counts || {}) };
    },

    coreTally() {
      const counts = this.tableVoteCounts;
      const entries = Object.entries(counts)
        .filter(([, count]) => Number(count) > 0)
        .sort((a, b) => b[1] - a[1]);
      return entries.map(([name, count]) => ({
        name,
        count: Number(count),
        color: agentColor(name),
        blocks: Math.min(5, Number(count)),
      }));
    },

    coreTotal() {
      return Object.values(this.tableVoteCounts).reduce(
        (total, count) => total + Number(count || 0),
        0,
      );
    },

    // 立场场：桌面左=支持 / 右=反对。没有立场数据时整层 opacity 0。
    stanceField() {
      const values = Object.values(this.stances)
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value));
      if (!values.length) return { opacity: 0, background: 'none' };
      const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
      const strength = Math.min(1, Math.abs(avg) / 100);
      const tint = avg >= 0 ? '61, 232, 192' : '255, 61, 110';
      return {
        opacity: (0.05 + strength * 0.08).toFixed(3),
        background: `linear-gradient(90deg, rgba(${tint}, .5), transparent 50%, rgba(${tint}, .5))`,
      };
    },

    leadName() {
      const scores = this.participants.map((p) => ({ name: p.name, score: this.scoreFor(p.name) }));
      if (!scores.length) return '';
      const max = Math.max(...scores.map((s) => s.score));
      if (max <= 0) return '';
      const top = scores.filter((s) => s.score === max);
      return top.length === 1 ? top[0].name : '';
    },

    tiedNames() {
      const scores = this.participants
        .filter((p) => p.state !== 'out')
        .map((p) => ({ name: p.name, score: this.scoreFor(p.name) }));
      if (scores.length < 2) return [];
      const max = Math.max(...scores.map((s) => s.score));
      if (max <= 0) return [];
      return scores.filter((s) => s.score === max).map((s) => s.name);
    },

    dangerNames() {
      const alive = this.participants.filter((p) => p.state !== 'out');
      if (!alive.length) return [];
      const scores = alive.map((p) => ({ name: p.name, score: this.scoreFor(p.name) }));
      const min = Math.min(...scores.map((s) => s.score));
      const max = Math.max(...scores.map((s) => s.score));
      if (max - min <= 1) return [];
      return scores.filter((s) => s.score === min).map((s) => s.name);
    },

    // 座位：存活者按固定角度均分，出局者沉到底部外圈并保留席位号。
    seats() {
      const alive = this.participants.filter((item) => item.state !== 'out');
      const out = this.participants.filter((item) => item.state === 'out');
      // 舞台是 1100 × 760 的固定盒子，所有坐标都写死在舞台坐标系里。
      const cx = 550;
      const cy = 420;
      const rx = 460;
      // 桌面绕 X 轴倾了 56°，俯视后盘面被压扁，座位环跟着压扁。
      const ry = 148;
      // 错开半格，避免有人正好坐在桌心正上方被投影面板挡住。
      const half = 180 / Math.max(1, alive.length);
      const seatIndex = new Map(this.participants.map((item, index) => [item.name, index + 1]));

      const all = alive.map((participant, index) => {
        const angle = (-90 + half + (360 / Math.max(1, alive.length)) * index) * (Math.PI / 180);
        const sin = Math.sin(angle);
        const front = sin > 0;
        return {
          name: participant.name,
          seatNo: this.seatNo(seatIndex.get(participant.name)),
          color: agentColor(participant.name),
          front,
          x: cx + Math.cos(angle) * rx,
          y: cy + sin * ry,
          scale: front ? 1 : 0.86,
          opacity: front ? 1 : 0.74,
          line: index % 3,
          robotState: this.robotState(participant.name),
          votes: this.scoreFor(participant.name),
        };
      });

      // 窄屏且人数超过 8：只保留前排 + 后排中间三席，其余折成桌心的 +N 标记。
      let list = all;
      let folded = 0;
      if (this.narrow && all.length > 8 && !this.expandedSeats) {
        const front = all.filter((seat) => seat.front);
        const back = all.filter((seat) => !seat.front);
        const keepBack = back.length
          ? [back[Math.floor((back.length - 1) / 2)], back[Math.floor(back.length / 2)]]
          : [];
        const keep = new Set([...front, ...keepBack].map((seat) => seat.name));
        list = all.filter((seat) => keep.has(seat.name));
        folded = all.length - list.length;
      }

      const outList = out.map((participant, index) => ({
        name: participant.name,
        seatNo: this.seatNo(seatIndex.get(participant.name)),
        color: agentColor(participant.name),
        front: false,
        x: cx - (out.length - 1) * 120 + index * 240,
        y: 700,
        scale: 0.8,
        opacity: 0.55,
        line: index % 3,
        robotState: 'out',
        votes: 0,
      }));

      const seats = [...list, ...outList].map((seat) => {
        const classes = [];
        if (!seat.front) classes.push('is-back');
        if (seat.robotState === 'out') classes.push('is-out');
        if (seat.robotState === 'winner') classes.push('is-winner');
        if (this.running && this.activeAgent === seat.name) classes.push('is-speaking');
        if (seat.robotState === 'thinking') classes.push('is-thinking');
        if (this.leadName === seat.name) classes.push('is-lead');
        if (this.tiedNames.includes(seat.name)) classes.push('is-tied');
        if (this.dangerNames.includes(seat.name) && seat.robotState !== 'out') {
          classes.push('is-danger');
        }
        if (this.hitAgent === seat.name) classes.push('is-hit');
        if (this.tiebreakAgents.includes(seat.name)) classes.push('is-tiebreak');
        // 席位环图案是颜色之外的第二区分通道：实线 / 虚线 / 双线。
        classes.push(`is-line-${seat.line}`);
        const state = seat.robotState === 'out' ? '出局'
          : this.running && this.activeAgent === seat.name ? '正在发言'
            : seat.robotState === 'thinking' ? '正在思考'
              : seat.robotState === 'winner' ? '胜者' : '在场';
        return {
          ...seat,
          classes,
          aria: `${seat.name}，席位 ${seat.seatNo}，${state}`
            + (this.dangerNames.includes(seat.name) && seat.robotState !== 'out' ? '，票数最低' : ''),
          voteBlocks: Math.min(5, seat.votes),
          extraVotes: Math.max(0, seat.votes - 5),
          style: {
            '--seat-x': `${seat.x}px`,
            '--seat-y': `${seat.y}px`,
            '--seat-scale': String(seat.scale),
            opacity: String(seat.opacity),
          },
        };
      });

      if (folded > 0) {
        seats.push({
          name: '__folded__',
          seatNo: '',
          color: '#5F7488',
          front: false,
          x: cx,
          y: cy,
          scale: 1,
          opacity: 1,
          line: 0,
          robotState: 'idle',
          votes: 0,
          folded,
          classes: ['is-folded'],
          aria: `另有 ${folded} 位参赛者，点击展开`,
          voteBlocks: 0,
          extraVotes: 0,
          style: {
            '--seat-x': `${cx}px`,
            '--seat-y': `${cy}px`,
            '--seat-scale': '1',
            opacity: '1',
          },
        });
      }
      return seats;
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

    // 登记页：结构化命题的折叠组
    contextCount() {
      return this.constraints.length + (this.background.trim() ? 1 : 0);
    },

    criteriaCount() {
      return this.criteria.length;
    },

    // 会场页 HUD：立场离散度
    spreadValue() {
      if (Number.isFinite(this.spread)) return this.spread;
      const values = Object.values(this.stances)
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value));
      if (values.length < 2) return null;
      return Math.max(...values) - Math.min(...values);
    },

    // 会场页 HUD：实际运行用量，不作为停止条件。
    usageReadout() {
      const budget = this.budget;
      if (!budget) return null;
      const used = Number(budget.calls) || 0;
      const tokens = Number(budget.tokens_estimate) || 0;
      return `${used.toLocaleString()} 次调用 · ${tokens.toLocaleString()} tok`;
    },

    parallelVisible() {
      return !this.tiebreakActive
        && this.speechMode === 'parallel_buffered'
        && this.parallelRows.length > 0
        && this.parallelRound === this.currentRound;
    },

    // 并行发言看板：所有席位始终同屏，完成一位就展开一位。
    parallelPapers() {
      const round = this.rounds.find((item) => item.no === this.parallelRound);
      const speeches = new Map(
        (round?.speeches || []).map((speech) => [speech.agent, speech]),
      );
      const role = this.parallelRound === 1 ? '独立发言' : '综合发言';
      return this.parallelRows.map((row, index) => {
        const speech = speeches.get(row.name);
        const participant = this.participants.find((item) => item.name === row.name);
        const stanceValue = speech?.stance ?? row.stance;
        const stance = stanceValue == null || stanceValue === ''
          ? null
          : Number.isFinite(Number(stanceValue)) ? Number(stanceValue) : null;
        return {
          ...row,
          index: index + 1,
          role: speech?.role || role,
          persona: participant?.persona || '',
          model: participant?.label || '',
          text: speech?.text || row.text || '',
          elapsed: Number(speech?.elapsed ?? row.elapsed ?? 0),
          stance,
          error: speech?.error || row.error || '',
          startedAt: row.startedAt || 0,
          waitSeconds: Number(row.waitSeconds || 0),
          spec: this.robotSpec(row.name),
        };
      });
    },

    parallelDoneCount() {
      return this.parallelRows.filter((row) => row.done).length;
    },

    matchOutcome() {
      if (this.stopReason) {
        return { kind: 'stopped', label: '中止', title: this.stopReason, detail: '保留已完成的全部轮次与发言。' };
      }
      if (this.winnerName) {
        return {
          kind: 'winner',
          label: '胜出',
          title: this.winnerName,
          model: this.agentModel(this.winnerName),
          detail: this.converged ? '完成投票裁决；比赛过程中曾出现立场趋同。' : '比赛完成全部必要轮次。',
        };
      }
      if (this.converged) {
        return { kind: 'converged', label: '收敛', title: '立场趋于一致', detail: '收敛只作为赛况读数，不跳过投票与裁决。' };
      }
      return null;
    },

    // 记录页：评分矩阵（当轮优先，全局兜底）
    recordScores() {
      const round = this.recordActiveRound;
      if (round?.scores && Object.keys(round.scores).length) return round.scores;
      return this.roundScores || {};
    },

    recordScoreRows() {
      return Object.entries(this.recordScores)
        .map(([name, dims]) => {
          const values = Object.values(dims || {}).map(Number).filter(Number.isFinite);
          const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
          return { name, dims, avg };
        })
        .sort((a, b) => b.avg - a.avg);
    },

    // 记录页：加权票位（按票权拆分整块 / 半块）
    recordWeightGroups() {
      const round = this.recordActiveRound;
      const rows = round?.votes?.rows || [];
      const alive = rows.filter((row) => !row.is_judge && row.target);
      const judges = rows.filter((row) => row.is_judge && row.target);
      return {
        alive: alive.length,
        judges: judges.length,
        judgeWeight: round?.votes?.weight_breakdown?.judge_weight ?? 0.5,
      };
    },

    // 档案页：对比模式的可选场次（同一命题优先）
    compareCandidates() {
      return this.history.slice(0, 30);
    },

    // 档案页：模型画像（用历史战报里的分数与胜率聚合）
    modelProfiles() {
      const byName = new Map();
      for (const item of this.history) {
        const names = item.participant_names || [];
        for (const name of names) {
          if (!byName.has(name)) {
            byName.set(name, { name, runs: 0, wins: 0, scores: [], challenged: 0 });
          }
          const profile = byName.get(name);
          profile.runs += 1;
          if (item.winner === name) profile.wins += 1;
        }
      }
      return [...byName.values()]
        .map((profile) => ({
          ...profile,
          winRate: profile.runs ? Math.round((profile.wins / profile.runs) * 100) : 0,
          avgScore: profile.scores.length
            ? (profile.scores.reduce((a, b) => a + b, 0) / profile.scores.length).toFixed(1)
            : '—',
        }))
        .sort((a, b) => b.winRate - a.winRate || b.runs - a.runs);
    },

    // 最终裁决里的「保留的分歧」与「前提」单独拆出来，视觉上脱离正文。
    finalDivergence() {
      return this.finalSection('【保留的分歧】');
    },

    finalPremises() {
      return this.finalSection('【失效条件】');
    },

    personaHint() {
      const hints = {
        '': '不分配人格。',
        审计员: '只挑证据与逻辑漏洞，不给建设性方案。',
        务实派: '只看落地成本与执行难度。',
        反方: '强制唱反调，优先反对当前共识。',
        红队: '攻击当前最强论点，找出它会失效的条件。',
        归纳者: '只做分歧归纳，不给立场性主张。',
      };
      return hints[this.persona] || '';
    },
  },

  mounted() {
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.soundOn = window.localStorage.getItem('arena-sound') === 'on';
    this.lang = window.ArenaI18n?.lang || 'zh';
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
    window.addEventListener('resize', this.resizeStage);
    window.addEventListener('keydown', this.handleKeyDown);
    window.addEventListener('hashchange', this.applyRoute);
    this.$nextTick(this.setupStage);
    this.$nextTick(this.syncNavIndicator);
    this.$nextTick(() => window.ArenaI18n?.init());
    if (this.soundOn) {
      window.addEventListener('pointerdown', () => this.enableSound(), { once: true });
    }
  },

  beforeUnmount() {
    this.closeStream();
    this.stopTimer();
    window.removeEventListener('beforeunload', this.closeStream);
    window.removeEventListener('resize', this.resizeStage);
    window.removeEventListener('keydown', this.handleKeyDown);
    window.removeEventListener('hashchange', this.applyRoute);
  },

  methods: {
    agentColor,

    seatNo(no) {
      return String(no || 0).padStart(2, '0');
    },

    newMatch() {
      this.resetArena();
      this.proposition = '';
      this.goPage('register');
    },

    roundNo(no) {
      return String(no).padStart(2, '0');
    },

    durationText(seconds) {
      const total = Math.max(0, Math.round(Number(seconds) || 0));
      const min = Math.floor(total / 60);
      const sec = total % 60;
      return min ? `${min}m${String(sec).padStart(2, '0')}s` : `${sec}s`;
    },

    goPage(page, updateHash = true) {
      if (!['register', 'venue', 'record', 'archive', 'models'].includes(page)) return;
      this.currentPage = page;
      if (updateHash) this.writeRoute(page);
      window.scrollTo({ top: 0, behavior: 'auto' });
      if (page === 'venue') this.$nextTick(this.setupStage);
      this.$nextTick(this.syncNavIndicator);
    },

    syncNavIndicator() {
      const index = this.navItems.findIndex((item) => item[0] === this.currentPage);
      if (index < 0) return;
      const item = this.$el?.querySelectorAll?.('.rail__item')?.[index];
      if (!item) return;
      this.navIndicator = {
        left: item.offsetLeft + item.offsetWidth / 2 - 12,
        width: 24,
      };
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

    archiveSpec(item, name) {
      const names = Array.isArray(item.participant_names)
        ? item.participant_names.filter(Boolean)
        : [name];
      return this.robotSpecWithin(name, names);
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
      this.previewMorph = false;
      this.$nextTick(() => {
        this.previewMorph = true;
        window.setTimeout(() => { this.previewMorph = false; }, 760);
      });
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

    toggleBallot(key) {
      this.expandedBallots = { ...this.expandedBallots, [key]: !this.expandedBallots[key] };
    },

    filteredSpeeches(round) {
      if (!this.recordAgentFilter) return round.speeches || [];
      return (round.speeches || []).filter((speech) => speech.agent === this.recordAgentFilter);
    },

    parallelRatio(row) {
      const chars = Number(row.chars || 0);
      return Math.max(0.04, Math.min(1, chars / 2000));
    },

    clearParallelChunks() {
      this._parallelChunkBuffer = Object.create(null);
      if (this._parallelFlushFrame) {
        window.cancelAnimationFrame(this._parallelFlushFrame);
        this._parallelFlushFrame = 0;
      }
    },

    scheduleParallelFlush() {
      if (this._parallelFlushFrame) return;
      this._parallelFlushFrame = window.requestAnimationFrame(() => this.flushParallelChunks());
    },

    flushParallelChunks() {
      this._parallelFlushFrame = 0;
      const buffer = this._parallelChunkBuffer || {};
      this._parallelChunkBuffer = Object.create(null);
      let changed = false;
      for (const [name, chunk] of Object.entries(buffer)) {
        const row = this.parallelRows.find((item) => item.name === name);
        if (!row || !chunk) continue;
        row.text = `${row.text || ''}${chunk}`.slice(-16000);
        changed = true;
      }
      if (changed) {
        this.parallelRows = [...this.parallelRows];
        this.activeStage = '并行实时输出中';
        this.liveLabel = `第 ${this.parallelRound} 轮 · ${
          this.parallelRows.filter((row) => row.text && !row.done).length
        } 位正在实时输出`;
        this.$nextTick(this.scrollLiveOutput);
      }
    },

    scrollLiveOutput() {
      const grid = this.$refs.parallelGrid;
      if (grid) {
        grid.querySelectorAll('.parallel-paper__body').forEach((body) => {
          body.scrollTop = body.scrollHeight;
        });
      }
      const projection = this.$refs.projectionPanel?.querySelector('.projection__body');
      if (projection) projection.scrollTop = projection.scrollHeight;
    },

    parallelElapsed(row) {
      const started = Number(row.startedAt || 0);
      if (!started) return Number(row.waitSeconds || 0);
      return Math.max(
        Number(row.waitSeconds || 0),
        Math.floor((Date.now() - started) / 1000),
      );
    },

    parallelWaitingText(row) {
      const elapsed = this.parallelElapsed(row);
      const chars = Number(row.chars || 0);
      const phase = elapsed < 4 ? '正在理解命题' : elapsed < 12 ? '正在组织论证' : '正在生成回应';
      return `${phase} · 已等待 ${elapsed}s${chars ? ` · 已接收 ${chars.toLocaleString()} 字符` : ''}`;
    },

    parallelRowState(row) {
      if (row.error) return '调用失败';
      if (row.done) return '已完成';
      if (row.text) {
        const elapsed = this.parallelElapsed(row);
        return elapsed > 0 ? `实时输出 ${elapsed}s` : '实时输出中';
      }
      return `思考中 ${this.parallelElapsed(row)}s`;
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
        marker: block.kind === 'view'
          ? '【观点】'
          : block.kind === 'critique'
            ? '【点评】'
            : block.kind === 'claim' ? '【主张】' : '',
      }));
    },

    // 流式吐字：每 45ms 追加 6–9 个字，用增量拼接避免整段重渲染。
    startStream(text) {
      const target = String(text || '');
      if (!target) {
        this.streamText = '';
        this.streamTarget = '';
        return;
      }
      // 目标文本是增量追加的：只有前缀对不上时才算换了一段发言，需要从头来。
      if (target === this.streamTarget) return;
      if (this.streamTarget && !target.startsWith(this.streamTarget)) {
        this.streamText = '';
      }
      this.streamTarget = target;
      if (this.reducedMotion) {
        this.streamText = target;
        return;
      }
      window.clearInterval(this._streamTimer);
      this._streamTimer = window.setInterval(() => {
        if (this.streamText.length >= this.streamTarget.length) {
          window.clearInterval(this._streamTimer);
          this._streamTimer = null;
          return;
        }
        const step = 6 + Math.floor(Math.random() * 4);
        this.streamText = this.streamTarget.slice(0, this.streamText.length + step);
      }, 45);
    },

    stopStream() {
      window.clearInterval(this._streamTimer);
      this._streamTimer = null;
    },

    // 把正文切成字符段，标记需要错位的那几个。
    // 故障位置由文本哈希决定：纯函数，渲染期间不写任何状态。
    splitGlitch(text) {
      const raw = String(text || '');
      if (!raw || this.reducedMotion) return [{ text: raw, glitch: false }];
      const limit = Math.min(3, Math.floor(raw.length / 120));
      const spots = {};
      for (let i = 0; i < limit; i += 1) {
        let hash = 2166136261;
        const key = raw.slice(i * 97, i * 97 + 40) || String(i);
        for (let j = 0; j < key.length; j += 1) {
          hash ^= key.charCodeAt(j);
          hash = Math.imul(hash, 16777619);
        }
        spots[Math.abs(hash) % raw.length] = true;
      }
      const indices = Object.keys(spots).map(Number).sort((a, b) => a - b);
      if (!indices.length) return [{ text: raw, glitch: false }];
      const out = [];
      let cursor = 0;
      for (const index of indices) {
        if (index > cursor) out.push({ text: raw.slice(cursor, index), glitch: false });
        out.push({ text: raw[index], glitch: true });
        cursor = index + 1;
      }
      if (cursor < raw.length) out.push({ text: raw.slice(cursor), glitch: false });
      return out;
    },

    scoreFor(name) {
      return Number(this.scoreByName[name] || 0) + Number(this.liveVoteCounts[name] || 0);
    },

    // 投票射线：沿桌沿走一段圆弧再收进目标座位。
    seatPoint(name) {
      const seat = this.seats.find((item) => item.name === name);
      if (!seat) return null;
      return { x: seat.x, y: seat.y };
    },

    voteRayPath(from, to) {
      // 射线坐标用舞台坐标系（1100 × 760），与 SVG 的 viewBox 一致。
      // 起点切向沿座位角方向：控制点放在「起点 + 切向」上，于是弧线先沿桌沿走再收进目标。
      const fx = from.x;
      const fy = from.y;
      const tx = to.x;
      const ty = to.y;
      const cx = 550;
      const cy = 420;
      const rx = 460;
      const ry = 148;
      // 起点切向：绕桌心的逆时针切线。
      const ox = fx - cx;
      const oy = (fy - cy) * (rx / ry);
      const len = Math.hypot(ox, oy) || 1;
      const tx1 = (-oy / len) * 90;
      const ty1 = (ox / len) * 90 * (ry / rx);
      const c1x = fx + tx1;
      const c1y = fy + ty1;
      // 终点切向反向收进，保证射线是收进去而不是撞上去。
      const ox2 = tx - cx;
      const oy2 = (ty - cy) * (rx / ry);
      const len2 = Math.hypot(ox2, oy2) || 1;
      const tx2 = (-oy2 / len2) * 46;
      const ty2 = (ox2 / len2) * 46 * (ry / rx);
      const c2x = tx - tx2;
      const c2y = ty - ty2;
      return `M ${fx} ${fy} C ${c1x} ${c1y} ${c2x} ${c2y} ${tx} ${ty}`;
    },

    addVoteRay(voter, target, dashed = false) {
      const from = this.seatPoint(voter);
      const to = this.seatPoint(target);
      if (!from || !to) return;
      const id = ++this.voteRaySeq;
      this.voteRays = [
        ...this.voteRays.slice(-15),
        {
          id,
          path: this.voteRayPath(from, to),
          color: agentColor(voter),
          dashed,
        },
      ];
      // 射线在计票完成前一直留着，计票后统一淡出。
      window.setTimeout(() => {
        if (!this.rayBright) {
          this.voteRays = this.voteRays.filter((ray) => ray.id !== id);
        }
      }, 4200);
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
      if (route.page === 'record' && route.id && this.viewingHistoryId !== route.id) {
        this.loadHistoryRun(route.id, { updateHash: false });
      }
      if (route.page === 'venue') this.$nextTick(this.setupStage);
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

    displayName(name) {
      return this.decodedNames[name] || name;
    },

    agentModel(name) {
      return this.participants.find((item) => item.name === name)?.label || '';
    },

    historyStatus(item) {
      if (item.status === 'running') return '进行中';
      if (item.status === 'error') return '中断';
      if (item.stop_reason) return '已停止';
      if (item.converged && !item.winner) return '已收敛';
      return '完成';
    },

    beginStage(agent, text) {
      this.activeAgent = agent || '';
      this.activeStage = text;
      this.stageStartedAt = Date.now();
      this.stageElapsed = 0;
      this.speechArchived = false;
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
      }, 340);
    },

    pulseWaiting(seconds = 0) {
      window.clearTimeout(this._waitingTimer);
      this.waitingMode = true;
      this.waitingSeconds = Math.round(Number(seconds) || 0);
      this._waitingTimer = window.setTimeout(() => {
        this.waitingMode = false;
      }, 2600);
    },

    enableSound() {
      if (!this.soundOn) return;
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      this._audio ||= new AudioCtx();
      if (this._audio.state === 'suspended') this._audio.resume();
    },

    toggleSound() {
      this.soundOn = !this.soundOn;
      window.localStorage.setItem('arena-sound', this.soundOn ? 'on' : 'off');
      this.soundSpun = false;
      this.$nextTick(() => {
        this.soundSpun = true;
        window.setTimeout(() => { this.soundSpun = false; }, 460);
      });
      if (this.soundOn) {
        this.enableSound();
        this.sound('ding');
      }
    },

    toggleLanguage() {
      this.lang = window.ArenaI18n?.toggle() || this.lang;
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
    },

    setupStage() {
      const stage = this.$refs.stage;
      if (!stage) return;
      const rect = stage.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      this.sceneWidth = rect.width;
      this.sceneHeight = rect.height;
      this.narrow = window.innerWidth < 860;
    },

    resizeStage() {
      window.clearTimeout(this._resizeTimer);
      this._resizeTimer = window.setTimeout(() => {
        this.setupStage();
        this.syncNavIndicator();
      }, 160);
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
        this.hintError = true;
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
      this.hintError = false;
      this.showModelModal = true;
      this.$nextTick(() => {
        const modal = this.$refs.modelModal;
        const target = modal?.querySelector('input:not([disabled]), textarea:not([disabled])')
          || modal?.querySelector('button:not([disabled])');
        target?.focus();
      });
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
      this.hintError = false;
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
              persona: this.modelForm.persona || '',
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
        this.hintError = true;
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
        this.hintError = true;
        return;
      }
      if (!this.modelForm.api_key.trim() && !this.editingModelId) {
        this.hint = '先填写 API Key';
        this.hintError = true;
        return;
      }
      this.namingModel = true;
      this.hint = '正在连接模型并生成名称…';
      this.hintError = false;
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
        this.hintError = true;
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
        this.hintError = true;
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
        this.hintError = true;
      } finally {
        this.historyLoading = false;
      }
    },

    resetArena() {
      this.closeStream();
      this.stopDemo();
      this.participants = [];
      this.rounds = [];
      this.currentRound = 0;
      this.final = null;
      this.winnerName = '';
      this.eventCount = 0;
      this.status = 'idle';
      this.statusText = '待命';
      this.stopReason = '';
      this.converged = false;
      this.liveLabel = '等待开始';
      this.replaying = false;
      this.viewingHistoryId = '';
      this.canReuseCurrentRun = false;
      this.activeAgent = '';
      this.activeStage = '';
      this.stageStartedAt = 0;
      this.stageElapsed = 0;
      this.modelOutputs = {};
      this.votingMode = false;
      this.waitingMode = false;
      this.waitingSeconds = 0;
      this.tiebreakState = null;
      this.speechArchived = false;
      this.eventFx = '';
      this.hitAgent = '';
      this.liveVoteCounts = {};
      this.decodedNames = {};
      this.archiveStamp = '';
      this.stances = {};
      this.priorStances = {};
      this.voteRays = [];
      this.stopStream();
      this.streamText = '';
      this.streamTarget = '';
      this.panelError = '';
      this.tiebreakAgents = [];
      this.introHint = '';
      this.rayBright = false;
      this.eliminatedInfo = null;
      this.budget = null;
      this.spread = null;
      this.parallelRows = [];
      this.parallelRound = 0;
      this.parallelReplayNote = false;
      this.clearParallelChunks();
      this.claims = [];
      this.roundScores = {};
      this.stopArmed = false;
      window.clearTimeout(this._fxTimer);
      window.clearTimeout(this._hitTimer);
      window.clearTimeout(this._waitingTimer);
      window.clearTimeout(this._archiveTimer);
      window.clearTimeout(this._rayTimer);
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
        this.hintError = true;
        return;
      }
      if (this.selectedModelIds.length < 2) {
        this.hint = '至少选择 2 位参赛模型';
        this.hintError = true;
        return;
      }
      this.hint = '';
      this.hintError = false;
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
        speech_mode: this.speechMode,
        background: this.background.trim(),
        constraints: this.constraints.slice(),
        criteria: this.criteria.slice(),
      };

      try {
        const res = await fetch('/api/runs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(cleanError(data));
        this.activeRunId = data.run;
        this.openStream(data.run);
      } catch (err) {
        this.running = false;
        this.status = 'error';
        this.statusText = '启动失败';
        this.liveLabel = '启动失败';
        this.hint = err.message;
        this.hintError = true;
        this.stopTimer();
      }
    },

    // 停止本场：二次确认，不弹窗。3 秒无操作自动还原。
    async stopMatch() {
      if (!this.running) return;
      if (!this.stopArmed) {
        this.stopArmed = true;
        window.clearTimeout(this._stopTimer);
        this._stopTimer = window.setTimeout(() => { this.stopArmed = false; }, 3000);
        return;
      }
      window.clearTimeout(this._stopTimer);
      this.stopArmed = false;
      const runId = this.activeRunId;
      if (!runId) {
        this.hint = '这场没有可停止的运行';
        this.hintError = true;
        return;
      }
      try {
        await fetch(`/api/runs/${encodeURIComponent(runId)}/stop`, { method: 'POST' });
        this.liveLabel = '正在停止，保留已完成轮次';
      } catch (err) {
        this.hint = `停止失败：${err.message}`;
        this.hintError = true;
      }
    },

    addConstraint() {
      const value = this.constraintDraft.trim();
      if (!value) return;
      this.constraints = [...this.constraints, value];
      this.constraintDraft = '';
    },

    removeConstraint(index) {
      this.constraints = this.constraints.filter((_, i) => i !== index);
    },

    addCriterion() {
      const value = this.criterionDraft.trim();
      if (!value) return;
      this.criteria = [...this.criteria, value];
      this.criterionDraft = '';
    },

    removeCriterion(index) {
      this.criteria = this.criteria.filter((_, i) => i !== index);
    },

    // 演示模式：把假的 SSE 事件喂给真正的 handleEvent，用来验证页面与动效。
    async startDemo() {
      this.resetArena();
      this.proposition = this.proposition.trim() || '远程办公是否应该永久化';
      this.goPage('venue');
      this.running = true;
      this.status = 'running';
      this.startTimer();
      this.demoTimers = [];

      const push = (event, delay) => {
        this.demoTimers.push(window.setTimeout(() => this.handleEvent(event), delay));
      };
      const names = DEMO_MODELS.map((model) => model.name);

      push({
        kind: 'run_start',
        agents: names.map((name, index) => ({
          name,
          label: DEMO_MODELS[index].model,
          persona: DEMO_PERSONAS[index] || '',
        })),
      }, 100);
      push({ kind: 'round_start', no: 1, alive: names.length, order: names }, 600);

      let at = 900;
      // 第一轮：并行生成，用假流式文本验证实时卡片，不请求模型。
      push({ kind: 'parallel_start', round_no: 1, agents: names, order: names }, at);
      names.forEach((name, index) => {
        const preview = `${DEMO_VIEW}\n【主张】${DEMO_CLAIMS[index % DEMO_CLAIMS.length]}`;
        push({ kind: 'thinking', agent: name, role: '独立发言' }, at);
        at += 80;
        push({
          kind: 'parallel_progress',
          round_no: 1,
          agent: name,
          chars: preview.length,
          text: preview,
        }, at);
        at += 260;
      });
      names.forEach((name, index) => {
        push({ kind: 'parallel_done', round_no: 1, agent: name }, at);
        at += 120;
        push({ kind: 'parallel_replay', round_no: 1, agent: name, index: index + 1, total: names.length }, at);
        push({
          kind: 'speech',
          agent: name,
          role: '独立发言',
          text: `${DEMO_VIEW}\n【主张】${DEMO_CLAIMS[index % DEMO_CLAIMS.length]}`,
          elapsed: 6.4,
          stance: 20 + index * 6,
        }, at);
        at += 220;
      });
      push({ kind: 'spread', round_no: 1, spread: 18 }, at);
      at += 200;
      push({
        kind: 'claims',
        claims: DEMO_CLAIMS.map((text, index) => ({
          claim_id: `C0${index + 1}`,
          text,
          author: names[index % names.length],
          round: 1,
          stance: 20,
          challengers: index === 0 ? [names[2]] : [],
          supporters: index === 0 ? [names[1]] : [],
          final_status: index === 0 ? 'adopted' : 'dormant',
        })),
      }, at);

      push({ kind: 'round_start', no: 2, alive: names.length, order: names }, at);
      at += 400;
      names.forEach((name, index) => {
        push({ kind: 'thinking', agent: name, role: '综合发言' }, at);
        at += 100;
        push({ kind: 'model_output', agent: name, role: '综合发言', text: DEMO_VIEW }, at);
        at += 200;
        push({ kind: 'speech', agent: name, role: '综合发言', text: DEMO_VIEW, elapsed: 5.8, stance: 30 }, at);
        at += 300;
      });
      push({ kind: 'spread', round_no: 2, spread: 42 }, at);

      push({ kind: 'voting_start', round_no: 2, stage: 'main', voters: names.length, candidates: names }, at);
      at += 500;
      DEMO_VOTES.forEach(([voter, target, reason], index) => {
        push({ kind: 'voting', round_no: 2, stage: 'main', voter, status: 'thinking', weight: 1 }, at);
        at += 300;
        push({
          kind: 'voting',
          round_no: 2,
          stage: 'main',
          voter,
          status: 'done',
          target,
          reason,
          weight: 1,
          is_judge: false,
        }, at);
        at += 450;
      });

      push({
        kind: 'votes',
        round_no: 2,
        stage: 'main',
        counts: { 'GPT-5': 2, Claude: 1, Gemini: 1, DeepSeek: 0 },
        rows: DEMO_VOTES.map(([voter, target, reason]) => ({
          voter, target, reason, stage: 'main', is_judge: false, weight: 1,
        })),
        weight_breakdown: { alive_votes: 4, judge_votes: 0, judge_weight: 0.5 },
        scores: DEMO_SCORES,
      }, at);
      at += 700;
      push({ kind: 'elimination', agent: 'DeepSeek', votes: 1, tiebreak: '本轮直接出局' }, at);
      at += 1200;
      push({ kind: 'winner', agent: 'GPT-5' }, at);
      at += 500;
      push({
        kind: 'final',
        agent: 'GPT-5',
        text: '【结论】远程办公值得永久化，但前提是把协作成本重新算清楚。'
          + '【论据】规模化效应取决于异步协作工具是否真的减少了同步会议。'
          + '【行动】先用四周做对照实验，用留存而不是打卡率决定是否全面推行。'
          + '【保留的分歧】Claude 提出：异步协作只在文档型工作里成立，'
          + '对需要高频对齐的团队反而更慢，这个分歧未被采纳也未被证伪。'
          + '【失效条件】如果四周对照实验里同步会议时长没有下降超过两成，这个结论不成立。',
      }, at);
      at += 500;
      push({ kind: 'budget', calls: 24, tokens_estimate: 12480, wall_clock: 24 }, at);
      at += 300;
      push({ kind: 'saved', paths: ['runs/20261102-demo/debate.md'] }, at);
      at += 300;
      push({ kind: 'done', duration: 24, rounds: 2, winner: 'GPT-5' }, at);
    },

    stopDemo() {
      (this.demoTimers || []).forEach((timer) => window.clearTimeout(timer));
      this.demoTimers = [];
    },

    // 演示档案与记录页：用假的战报数据填充，不请求后端。
    demoTranscript() {
      const names = DEMO_MODELS.map((model) => model.name);
      return {
        proposition: '远程办公是否应该永久化',
        vote_mode: 'eliminate',
        duration: 252,
        winner: 'GPT-5',
        final_answer: '【结论】远程办公值得永久化，但前提是把协作成本重新算清楚。'
          + '【论据】规模化效应取决于异步协作工具是否真的减少了同步会议。'
          + '【行动】先用四周做对照实验，用留存而不是打卡率决定是否全面推行。'
          + '【保留的分歧】Claude 提出：异步协作只在文档型工作里成立，'
          + '对需要高频对齐的团队反而更慢，这个分歧未被采纳也未被证伪。'
          + '【失效条件】如果四周对照实验里同步会议时长没有下降超过两成，这个结论不成立。',
        claims: DEMO_CLAIMS.map((text, index) => ({
          claim_id: `C0${index + 1}`,
          text,
          author: names[index % names.length],
          round: (index % 2) + 1,
          stance: 20,
          challengers: index === 0 ? [names[2]] : [],
          supporters: index === 0 ? [names[1]] : [],
          final_status: index === 0 ? 'adopted' : 'dormant',
        })),
        budget: { calls: 24, tokens_estimate: 12480, wall_clock: 252, per_model: {} },
        stop_reason: '',
        converged: false,
        schema_version: 3,
        participants: DEMO_MODELS.map((model) => ({ name: model.name, label: model.model })),
        rounds: [
          {
            no: 1,
            order: names,
            speeches: names.map((name) => ({
              agent: name, role: '独立发言', text: DEMO_VIEW, elapsed: 6.4, stance: 20,
            })),
            votes: [],
          },
          {
            no: 2,
            order: names,
            speeches: names.map((name) => ({
              agent: name, role: '综合发言', text: DEMO_VIEW, elapsed: 5.8, stance: 30,
            })),
            votes: DEMO_VOTES.map(([voter, target, reason]) => ({
              voter, target, reason, stage: 'main', is_judge: false, weight: 1,
            })),
            counts: { 'GPT-5': 2, Claude: 1, Gemini: 1 },
            weight_breakdown: { alive_votes: 4, judge_votes: 0, judge_weight: 0.5 },
            scores: DEMO_SCORES,
            stance_spread: 42,
            eliminated: 'DeepSeek',
            votes_received: 1,
            tiebreak: '本轮直接出局',
          },
          {
            no: 3,
            order: ['GPT-5', 'Claude', 'Gemini'],
            speeches: ['GPT-5', 'Claude', 'Gemini'].map((name) => ({
              agent: name, role: '综合发言', text: DEMO_VIEW, elapsed: 4.9, stance: 35,
            })),
            votes: [
              { voter: 'GPT-5', target: 'Claude', reason: '数据来源最扎实', stage: 'main', is_judge: false },
              { voter: 'Claude', target: 'GPT-5', reason: '论证最完整', stage: 'main', is_judge: false },
              { voter: 'Gemini', target: 'GPT-5', reason: '行动建议最明确', stage: 'main', is_judge: false },
              { voter: 'DeepSeek', target: 'Claude', reason: '风险提示更完整', stage: 'main', is_judge: true },
            ],
            counts: { 'GPT-5': 2, Claude: 1, Gemini: 0 },
            eliminated: 'Gemini',
            votes_received: 0,
            tiebreak: '本轮直接出局',
          },
        ],
      };
    },

    showDemoRecord() {
      this.loadDemoTranscript();
      this.currentPage = 'record';
      this.writeRoute('record', 'demo');
    },

    loadDemoTranscript() {
      this.resetArena();
      this.replaying = true;
      this.viewingHistoryId = 'demo';
      const transcript = this.demoTranscript();
      this.proposition = transcript.proposition;
      this.mode = transcript.vote_mode;
      this.status = 'done';
      this.participants = transcript.participants.map((p) => ({
        name: p.name, label: p.label, persona: p.persona || '',
        state: 'alive', lastRole: '', lastElapsed: 0,
      }));
      this.winnerName = transcript.winner;
      for (const record of transcript.rounds) {
        const round = this.ensureRound(record.no);
        round.order = record.order || [];
        round.alive = round.order.length;
        round.speeches = record.speeches || [];
        if (record.votes?.length) {
          round.votes = {
            rows: record.votes,
            counts: record.counts || {},
            weight_breakdown: record.weight_breakdown || null,
          };
        }
        round.scores = record.scores || {};
        round.stance_spread = record.stance_spread ?? null;
        if (record.eliminated) {
          round.eliminated = {
            agent: record.eliminated,
            votes: record.votes_received,
            tiebreak: record.tiebreak,
          };
          this.setAgentState(record.eliminated, 'out');
        }
      }
      this.final = { agent: transcript.winner, text: transcript.final_answer };
      this.claims = transcript.claims || [];
      this.budget = transcript.budget || null;
      this.stopReason = transcript.stop_reason || '';
      this.converged = Boolean(transcript.converged);
      this.currentRound = transcript.rounds.length;
      this.elapsed = transcript.duration;
      this.activeAgent = transcript.winner;
    },

    showDemoArchive() {
      this.history = DEMO_HISTORY;
      this.historyLoading = false;
      this.currentPage = 'archive';
      this.writeRoute('archive');
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
        scores: {},
        weight_breakdown: null,
        stance_spread: null,
        round_claims: [],
      };
      this.rounds.push(round);
      this.currentRound = Math.max(this.currentRound, no);
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
          this.parallelRows = [];
          this.parallelRound = 0;
          this.parallelReplayNote = false;
          this.clearParallelChunks();
          this.participants = (ev.agents || []).map((a) => ({
            name: a.name,
            label: a.label,
            persona: a.persona || '',
            state: 'alive',
            lastRole: '',
            lastElapsed: 0,
          }));
          this.liveLabel = `第 1 轮即将开始 · ${this.participants.length} 位参赛`;
          this.beginStage('', '参赛阵容已就绪');
          this.introHint = `第 1 轮 · ${this.participants.length} 位参赛`;
          this.playFx('intro', 2400);
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
          // 新参赛者补一个座位，只闪一下底盘，不触发全场动画。
          this.seatFx = { ...this.seatFx, [ev.name]: 'is-lit' };
          window.setTimeout(() => {
            const next = { ...this.seatFx };
            delete next[ev.name];
            this.seatFx = next;
          }, 700);
          this.decodeAgentName(ev.name);
          break;
        }

        case 'round_start': {
          const round = this.ensureRound(ev.no);
          this.modelOutputs = {};
          this.parallelRows = [];
          this.parallelRound = 0;
          this.parallelReplayNote = false;
          this.clearParallelChunks();
          this.tiebreakState = null;
          round.alive = ev.alive;
          round.order = ev.order || [];
          this.liveLabel = `第 ${ev.no} 轮 · ${ev.alive} 人存活`;
          this.beginStage('', `第 ${ev.no} 轮准备发言`);
          this.introHint = `第 ${ev.no} 轮 · ${ev.alive} 人存活`;
          this.playFx('round-start', 550);
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
          // 换人开口，清空上一段流式正文。
          this.stopStream();
          this.streamText = '';
          this.streamTarget = '';
          this.playFx('scan', 620);
          this.decodeAgentName(ev.agent);
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
          this.activeAgent = ev.agent;
          this.activeStage = `${ev.role}中 · 模型正在逐字返回`;
          this.liveLabel = `${ev.agent} 正在实时输出`;
          this.startStream(current.text);
          break;
        }

        case 'waiting':
          this.setAgentState(ev.agent, 'thinking');
          {
            const row = this.parallelRows.find((item) => item.name === ev.agent);
            if (row) {
              row.waitSeconds = Number(ev.elapsed || 0);
              this.parallelRows = [...this.parallelRows];
            }
          }
          this.activeAgent = ev.agent;
          this.activeStage = `${ev.role}中，已等待 ${Number(ev.elapsed || 0).toFixed(1)} 秒`;
          this.stageStartedAt = Date.now() - Number(ev.elapsed || 0) * 1000;
          this.stageElapsed = Number(ev.elapsed || 0);
          this.liveLabel = `${ev.agent} · ${this.activeStage}`;
          this.pulseWaiting(Number(ev.elapsed || 0));
          break;

        case 'speech': {
          const round = this.ensureRound(this.currentRound || 1);
          round.thinking = round.thinking.filter((x) => x.agent !== ev.agent);
          const duplicate = round.speeches.some(
            (speech) => speech.agent === ev.agent
              && speech.role === ev.role
              && speech.text === ev.text,
          );
          if (!duplicate) round.speeches.push(ev);
          const parallelRow = this.parallelRows.find((row) => row.name === ev.agent);
          if (parallelRow) {
            Object.assign(parallelRow, {
              text: ev.text || '',
              elapsed: Number(ev.elapsed || 0),
              stance: Number.isFinite(Number(ev.stance)) ? Number(ev.stance) : null,
              error: ev.error || '',
              done: true,
            });
            this.parallelRows = [...this.parallelRows];
            this.$nextTick(this.scrollLiveOutput);
          }
          if (Number.isFinite(ev.stance)) {
            this.stances = { ...this.stances, [ev.agent]: ev.stance };
          }
          const outputs = { ...this.modelOutputs };
          delete outputs[ev.agent];
          this.modelOutputs = outputs;
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
          this.speechArchived = !ev.error;
          this.stopStream();
          this.playFx('settle', 380);
          this.sound('ding');
          break;
        }

        case 'voting_start': {
          const round = this.ensureRound(ev.round_no || this.currentRound || 1);
          round.votingStage = {
            stage: ev.stage || 'main',
            voters: ev.voters || 0,
            candidates: ev.candidates || [],
            startedAt: Date.now(),
          };
          if (String(ev.stage || '').startsWith('tiebreak')) {
            this.tiebreakState = {
              attempt: Number(String(ev.stage).split('-')[1]) || this.tiebreakState?.attempt || 1,
              agents: [...(this.tiebreakState?.agents || ev.candidates || [])],
              status: 'voting',
            };
          }
          this.beginStage('', `${ev.voters} 位投票者正在判断本轮发言`);
          this.liveLabel = `第 ${ev.round_no} 轮 · ${this.voteStageLabel(ev.stage)}：${ev.voters} 位投票者`;
          this.liveVoteCounts = {};
          this.votingMode = true;
          this.waitingMode = false;
          this.playFx('voting', 900);
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
            if (ev.target) {
              const weight = Number(ev.weight ?? (ev.is_judge ? 0.5 : 1));
              this.liveVoteCounts = {
                ...this.liveVoteCounts,
                [ev.target]: (this.liveVoteCounts[ev.target] || 0) + weight,
              };
              this.flashHit(ev.target);
              this.addVoteRay(ev.voter, ev.target, String(ev.stage || '').startsWith('tiebreak'));
              this.sound('ding');
            }
          } else {
            this.liveLabel = `${ev.voter} 投票失败`;
            this.beginStage(ev.voter, `${this.voteStageLabel(ev.stage)}：投票失败`);
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
          this.tiebreakAgents = ev.agents || [];
          this.tiebreakState = {
            attempt: ev.attempt,
            agents: [...(ev.agents || [])],
            status: ev.status || 'speaking',
          };
          this.playFx('tiebreak', 900);
          break;
        }

        case 'tiebreak_result': {
          const round = this.ensureRound(ev.round_no || this.currentRound || 1);
          const step = round.tiebreakSteps.find((item) => item.attempt === ev.attempt);
          if (step) Object.assign(step, ev);
          this.tiebreakState = {
            attempt: ev.attempt,
            agents: [...(this.tiebreakState?.agents || step?.agents || [])],
            status: ev.status || 'tied',
          };
          this.liveLabel = `第 ${ev.round_no} 轮 · 第 ${ev.attempt} 次加赛投票完成`;
          this.beginStage('', '加赛票已收到，正在本地汇总');
          this.liveVoteCounts = {};
          this.tiebreakAgents = [];
          this.playFx('settle', 400);
          break;
        }

        case 'votes': {
          const round = this.ensureRound(this.currentRound || 1);
          round.votes = ev;
          if (ev.weight_breakdown) round.votes.weight_breakdown = ev.weight_breakdown;
          if (ev.scores) round.scores = ev.scores;
          this.liveVoteCounts = {};
          this.votingMode = false;
          this.liveLabel = '票已收到，正在本地汇总票数';
          this.beginStage('', '票已收到，正在本地汇总票数');
          // 阶段 C：所有射线同时增亮到 100%，持续 400ms。
          this.rayBright = true;
          window.clearTimeout(this._rayTimer);
          this._rayTimer = window.setTimeout(() => {
            this.rayBright = false;
            this.voteRays = [];
          }, 400);
          this.playFx('count', 500);
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
          this.tiebreakAgents = [];
          this.tiebreakState = null;
          // 出局者保留席位号与删除线，并标记转任评审。
          this.eliminatedInfo = {
            agent: ev.agent,
            round: this.currentRound,
            votes: ev.votes,
            tiebreak: ev.tiebreak,
          };
          this.playFx('elimination', 1650);
          this.sound('thud');
          break;
        }

        case 'technical_exit': {
          const round = this.ensureRound(this.currentRound || 1);
          round.exits.push(ev);
          delete this.modelOutputs[ev.agent];
          this.setAgentState(ev.agent, 'out');
          this.liveLabel = `${ev.agent} 技术性退赛`;
          this.beginStage(ev.agent, `${ev.agent} 技术性退赛`);
          this.playFx('technical-exit', 1200);
          break;
        }

        case 'winner':
          this.winnerName = ev.agent;
          this.setAgentState(ev.agent, 'alive');
          this.liveLabel = `${ev.agent} 最终存活`;
          this.beginStage(ev.agent, `${ev.agent} 最终存活`);
          this.votingMode = false;
          this.waitingMode = false;
          this.tiebreakAgents = [];
          this.tiebreakState = null;
          this.playFx('winner', 1600);
          this.sound('winner');
          break;

        case 'final':
          this.final = ev;
          this.rounds.forEach((round) => { round.thinking = []; });
          this.setAgentState(ev.agent, 'alive');
          this.liveLabel = `${ev.agent} 正在整理最终结论`;
          this.beginStage(ev.agent, '正在整理最终结论');
          this.stopStream();
          // 最终结论一次性淡入，不做流式。
          this.streamText = ev.text || '';
          this.streamTarget = ev.text || '';
          this.speechArchived = false;
          this.playFx('final', 600);
          break;

        case 'parallel_start': {
          this.parallelRound = ev.round_no || this.currentRound || 1;
          this.clearParallelChunks();
          this.parallelRows = (ev.agents || []).map((name) => ({
            name, chars: 0, done: false, text: '', elapsed: 0, stance: null, error: '',
            startedAt: Date.now(), waitSeconds: 0,
          }));
          this.liveLabel = `第 ${this.parallelRound} 轮 · ${this.parallelRows.length} 位并行生成中`;
          this.beginStage('', '并行生成中，完成后全员观点同屏展开');
          this.playFx('scan', 620);
          break;
        }

        case 'parallel_progress': {
          const row = this.parallelRows.find((item) => item.name === ev.agent);
          const chunk = String(ev.text || ev.delta || '');
          if (row) {
            row.chars = Number(ev.chars || row.chars || 0);
            if (chunk) {
              if (!this._parallelChunkBuffer) this._parallelChunkBuffer = Object.create(null);
              this._parallelChunkBuffer[ev.agent] = `${
                this._parallelChunkBuffer[ev.agent] || ''
              }${chunk}`.slice(-16000);
              this.scheduleParallelFlush();
            }
          }
          break;
        }

        case 'parallel_done': {
          this.flushParallelChunks();
          const row = this.parallelRows.find((item) => item.name === ev.agent);
          if (row) {
            row.done = true;
            row.chars = row.chars || 0;
          }
          break;
        }

        case 'parallel_replay': {
          this.parallelReplayNote = true;
          this.liveLabel = `同屏展开 · 第 ${ev.index}/${ev.total} 位`;
          window.clearTimeout(this._parallelNoteTimer);
          this._parallelNoteTimer = window.setTimeout(() => {
            this.parallelReplayNote = false;
          }, 4000);
          break;
        }

        case 'scores': {
          this.roundScores = ev.scores || {};
          break;
        }

        case 'claims': {
          for (const claim of ev.claims || []) {
            if (!this.claims.some((item) => item.claim_id === claim.claim_id)) {
              this.claims = [...this.claims, claim];
            }
          }
          break;
        }

        case 'budget': {
          this.budget = {
            calls: Number(ev.calls || 0),
            tokens_estimate: Number(ev.tokens_estimate || 0),
            wall_clock: Number(ev.wall_clock || 0),
          };
          break;
        }

        case 'spread': {
          this.spread = Number.isFinite(Number(ev.spread)) ? Number(ev.spread) : null;
          break;
        }

        case 'converged': {
          this.converged = true;
          this.liveLabel = `立场趋同（极差 ${ev.spread}），继续完成投票裁决`;
          break;
        }

        case 'stopped': {
          this.running = false;
          this.status = 'cancelled';
          this.statusText = '已停止';
          this.stopReason = ev.reason || '用户中止';
          this.tiebreakState = null;
          this.liveLabel = `已停止 · 保留已完成轮次${ev.reason ? '（' + ev.reason + '）' : ''}`;
          this.stopTimer();
          this.playFx('settle', 500);
          break;
        }

        case 'saved':
          this.archiveStamp = String(ev.paths?.[0] || 'debate.md').split('/').pop();
          window.clearTimeout(this._archiveTimer);
          this._archiveTimer = window.setTimeout(() => { this.archiveStamp = ''; }, 4000);
          this.loadHistory();
          break;

        case 'error':
          this.hint = ev.message || '比赛出错了';
          this.hintError = true;
          this.status = 'error';
          this.statusText = '出错';
          // 错误不弹窗：投影面板顶部出现一条危险色细线 + 消息文本。
          this.panelError = ev.message || '比赛出错了';
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
          this.tiebreakState = null;
          this.stopTimer();
          this.loadHistory();
          break;
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
        this.activeRunId = data.run.id;
        this.openStream(data.run.id);
      } catch (_) {
        // 没有活动比赛时不打扰用户。
      }
    },

    async reuseHistoryRun(id) {
      if (!id || id === 'demo') {
        this.hint = '演示档案没有可复用的真实模型配置';
        this.hintError = true;
        return;
      }
      try {
        const res = await fetch(`/api/history/${encodeURIComponent(id)}/preset`);
        const preset = await res.json();
        if (!res.ok) throw new Error(cleanError(preset));

        await this.loadModels();
        const selected = new Set((preset.model_ids || []).map(Number));
        this.models = this.models.map((model) => ({
          ...model,
          checked: selected.has(Number(model.id)),
        }));

        this.resetArena();
        this.proposition = preset.proposition || '';
        this.mode = preset.vote_mode || 'eliminate';
        this.speechMode = preset.speech_mode || 'parallel_buffered';
        this.timeout = Number(preset.timeout) || 240;
        this.background = preset.background || '';
        this.constraints = [...(preset.constraints || [])];
        this.criteria = [...(preset.criteria || [])];
        this.propOpen.context = Boolean(this.background || this.constraints.length);
        this.propOpen.criteria = Boolean(this.criteria.length);

        const missing = preset.missing_models || [];
        if (missing.length || !preset.resolved) {
          const names = missing.map((item) => item.name).join('、') || '部分参赛模型';
          this.hint = `预设已载入，但 ${names} 已删除、改名或无法唯一匹配，请重新选择后再开赛。`;
          this.hintError = true;
          this.hintOk = false;
        } else {
          this.hint = `已复用这场预设：${preset.proposition}。确认阵容后开赛。`;
          this.hintError = false;
          this.hintOk = true;
        }
        this.goPage('register');
      } catch (err) {
        this.hint = `复用预设失败：${err.message}`;
        this.hintError = true;
        this.hintOk = false;
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
          this.hintError = true;
          return;
        }
        this.resetArena();
        this.replaying = true;
        this.running = false;
        this.viewingHistoryId = id;
        this.canReuseCurrentRun = (transcript.setup?.model_ids || []).length >= 2;
        this.proposition = transcript.proposition || this.proposition;
        this.mode = transcript.vote_mode || 'eliminate';
        this.status = 'done';
        this.statusText = '历史回放';
        this.liveLabel = '历史提问回放';
        this.participants = (transcript.participants || []).map((p) => ({
          name: p.name,
          label: p.label,
          persona: p.persona || '',
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
            if (Number.isFinite(speech.stance)) {
              this.stances = { ...this.stances, [speech.agent]: speech.stance };
            }
          }
          if (record.votes && record.votes.length) {
            round.votes = {
              rows: record.votes,
              counts: record.counts || {},
              vote_mode: transcript.vote_mode,
              weight_breakdown: record.weight_breakdown || null,
            };
          }
          round.scores = record.scores || {};
          round.stance_spread = Number.isFinite(record.stance_spread)
            ? record.stance_spread : null;
          round.round_claims = record.round_claims || [];
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
        this.claims = transcript.claims || [];
        this.budget = transcript.budget || null;
        this.stopReason = transcript.stop_reason || '';
        this.converged = Boolean(transcript.converged);
        this.spread = null;
        if (transcript.winner && transcript.final_answer) {
          this.final = { agent: transcript.winner, text: transcript.final_answer };
        }
        this.currentRound = Math.max(0, ...((transcript.rounds || []).map((r) => Number(r.no) || 0)));
        this.liveLabel = '历史战报已载入';
        this.activeAgent = transcript.winner || '';
        this.activeStage = '历史回放完成';
        this.elapsed = Number(transcript.duration || 0);
        this.stageElapsed = Number(transcript.duration || 0);
        this.hint = '';
        this.hintError = false;
        this.currentPage = 'record';
        if (options.updateHash !== false) this.writeRoute('record', id);
        this.$nextTick(() => {
          this.setupStage();
        });
      } catch (err) {
        this.hint = `历史回放失败：${err.message}`;
        this.hintError = true;
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
      // 立场标记是元信息，不属于发言正文。
      const raw = String(text || '').replace(/【立场】\s*[+-]?\d{1,3}\s*/g, '');
      const markers = [...raw.matchAll(/【(点评|观点|主张)】/g)];
      if (!markers.length) return [{ kind: 'plain', text: raw }];
      return markers
        .map((marker, index) => ({
          kind: marker[1] === '点评' ? 'critique' : marker[1] === '观点' ? 'view' : 'claim',
          text: raw
            .slice(marker.index + marker[0].length, markers[index + 1]?.index ?? raw.length)
            .trim(),
        }))
        .filter((block) => block.text);
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

    // 投影面板只显示最终结论；完整裁决（含分歧与前提）在记录页。
    finalConclusion() {
      const raw = String(this.final?.text || '');
      const at = raw.indexOf('【结论】');
      if (at < 0) return '';
      const rest = raw.slice(at + '【结论】'.length);
      const next = rest.search(/【[^】]+】/);
      return (next >= 0 ? rest.slice(0, next) : rest).trim();
    },

    gotoFullDecision() {
      this.goPage('record');
      this.$nextTick(() => {
        document.querySelector('.record-final')?.scrollIntoView({
          behavior: this.reducedMotion ? 'auto' : 'smooth',
          block: 'center',
        });
      });
    },

    // 从最终裁决文本里取出一个标签段落，拆成一行一条。
    finalSection(marker) {
      const raw = String(this.final?.text || '');
      const at = raw.indexOf(marker);
      if (at < 0) return [];
      const rest = raw.slice(at + marker.length);
      const next = rest.search(/【[^】]+】/);
      const body = next >= 0 ? rest.slice(0, next) : rest;
      return body
        .split(/\n+/)
        .map((line) => line.replace(/^[-·•\d.、\s]+/, '').trim())
        .filter(Boolean);
    },

    // 模型的人格标签（只影响发言）。
    agentPersona(name) {
      const participant = this.participants.find((item) => item.name === name);
      if (participant?.persona) return participant.persona;
      const model = this.models.find((item) => item.name === name);
      return model?.persona || '';
    },

  },

}).mount('#app');
