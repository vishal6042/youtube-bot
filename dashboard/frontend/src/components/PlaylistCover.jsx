/* Themed cover art per playlist — hand-drawn SVG, no external images.
   Each cover: a dark gradient in the series' hue + a simple thematic
   illustration with a neon glow, matching the dashboard aesthetic. */

const W = 340, H = 120;

function Base({ id, from, to, children }) {
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice" role="img">
      <defs>
        <linearGradient id={`${id}-bg`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={from} />
          <stop offset="100%" stopColor={to} />
        </linearGradient>
        <filter id={`${id}-glow`} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="2.4" result="b" />
          <feMerge>
            <feMergeNode in="b" /><feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect width={W} height={H} fill={`url(#${id}-bg)`} />
      <g stroke="rgba(255,255,255,0.05)" strokeWidth="1">
        {[20, 50, 80].map((y) => <line key={y} x1="0" y1={y} x2={W} y2={y} />)}
        {[60, 130, 200, 270].map((x) => <line key={x} x1={x} y1="0" x2={x} y2={H} />)}
      </g>
      <g filter={`url(#${id}-glow)`}>{children}</g>
    </svg>
  );
}

function Globe() {
  return (
    <Base id="cv-world" from="#07182e" to="#0b2c46">
      <g stroke="#38e1ff" strokeWidth="2" fill="none">
        <circle cx="170" cy="62" r="40" />
        <ellipse cx="170" cy="62" rx="18" ry="40" />
        <ellipse cx="170" cy="62" rx="34" ry="40" opacity="0.4" />
        <line x1="130" y1="62" x2="210" y2="62" />
        <path d="M136 40 Q170 52 204 40" opacity="0.7" />
        <path d="M136 84 Q170 72 204 84" opacity="0.7" />
      </g>
      <g fill="#8fe8ff">
        <circle cx="60" cy="30" r="2" /><circle cx="288" cy="88" r="2" />
        <circle cx="262" cy="26" r="3" /><circle cx="84" cy="94" r="3" />
      </g>
      <ellipse cx="170" cy="62" rx="58" ry="18" fill="none"
               stroke="#ff4fd8" strokeWidth="1.4" strokeDasharray="4 6" opacity="0.8"
               transform="rotate(-18 170 62)" />
      <circle cx="224" cy="44" r="3.5" fill="#ff4fd8" />
    </Base>
  );
}

function Chakra() {
  const spokes = Array.from({ length: 12 }, (_, i) => (i * 30 * Math.PI) / 180);
  return (
    <Base id="cv-india" from="#1c1206" to="#0a2415">
      <rect x="0" y="0" width={W} height="10" fill="#ff9933" opacity="0.75" />
      <rect x="0" y={H - 10} width={W} height="10" fill="#138808" opacity="0.75" />
      <g stroke="#7fb2ff" strokeWidth="2" fill="none">
        <circle cx="170" cy="60" r="34" />
        <circle cx="170" cy="60" r="6" fill="#7fb2ff" />
        {spokes.map((a, i) => (
          <line key={i}
            x1={170 + 8 * Math.cos(a)} y1={60 + 8 * Math.sin(a)}
            x2={170 + 32 * Math.cos(a)} y2={60 + 32 * Math.sin(a)} />
        ))}
      </g>
      <g fill="#ffc857" fontFamily="sans-serif" fontSize="13" fontWeight="700">
        <text x="248" y="52">भारत</text>
      </g>
      <circle cx="86" cy="46" r="3" fill="#ff9933" />
      <circle cx="256" cy="82" r="3" fill="#35e0a1" />
    </Base>
  );
}

function Neural() {
  const L = [[70, [30, 60, 90]], [170, [22, 62, 100]], [270, [40, 82]]];
  return (
    <Base id="cv-ml" from="#150b2e" to="#251043">
      <g stroke="rgba(167,139,250,0.55)" strokeWidth="1.3">
        {L[0][1].map((y1) => L[1][1].map((y2) => (
          <line key={`a${y1}${y2}`} x1="70" y1={y1} x2="170" y2={y2} />
        )))}
        {L[1][1].map((y1) => L[2][1].map((y2) => (
          <line key={`b${y1}${y2}`} x1="170" y1={y1} x2="270" y2={y2} />
        )))}
      </g>
      {L.map(([x, ys]) => ys.map((y) => (
        <circle key={`${x}${y}`} cx={x} cy={y} r="8"
                fill="#1b1038" stroke="#a78bfa" strokeWidth="2.2" />
      )))}
      <circle cx="170" cy="62" r="8" fill="#a78bfa" />
    </Base>
  );
}

function Chip() {
  return (
    <Base id="cv-ai" from="#20081f" to="#3a0d33">
      <g stroke="#ff4fd8" strokeWidth="2" fill="none">
        <rect x="140" y="32" width="60" height="60" rx="8" />
        {[46, 62, 78].map((y) => (
          <g key={y}>
            <line x1="122" y1={y} x2="140" y2={y} />
            <line x1="200" y1={y} x2="218" y2={y} />
          </g>
        ))}
        {[154, 170, 186].map((x) => (
          <g key={x}>
            <line x1={x} y1="14" x2={x} y2="32" />
            <line x1={x} y1="92" x2={x} y2="110" />
          </g>
        ))}
        <path d="M122 46 H96 V22" opacity="0.6" />
        <path d="M218 78 H250 V102" opacity="0.6" />
      </g>
      <text x="170" y="69" textAnchor="middle" fill="#ff9df0"
            fontFamily="sans-serif" fontSize="20" fontWeight="800">AI</text>
      <circle cx="96" cy="22" r="3" fill="#ff4fd8" />
      <circle cx="250" cy="102" r="3" fill="#ff4fd8" />
    </Base>
  );
}

function Coins() {
  const stack = (x, n, c) =>
    Array.from({ length: n }, (_, i) => (
      <ellipse key={i} cx={x} cy={100 - i * 9} rx="24" ry="7"
               fill="#241a06" stroke={c} strokeWidth="2" />
    ));
  return (
    <Base id="cv-money" from="#1c1206" to="#2a1c08">
      {stack(110, 5, "#ffc857")}
      {stack(170, 8, "#ffd98a")}
      {stack(230, 3, "#ffc857")}
      <text x="170" y="36" textAnchor="middle" fill="#ffd98a"
            fontFamily="sans-serif" fontSize="22" fontWeight="800">₹ $ €</text>
    </Base>
  );
}

function LieChart() {
  return (
    <Base id="cv-lie" from="#230a12" to="#301027">
      <g stroke="#8fa3c8" strokeWidth="2" fill="none">
        <line x1="70" y1="20" x2="70" y2="96" />
        <line x1="70" y1="96" x2="280" y2="96" />
        {/* broken axis */}
        <path d="M70 62 l8 -6 l-8 -6" stroke="#ff6b81" strokeWidth="2.4" />
      </g>
      <path d="M84 88 L130 74 L168 80 L214 38 L262 30"
            fill="none" stroke="#ff6b81" strokeWidth="3" />
      <g transform="translate(238 52)">
        <path d="M14 0 L28 24 L0 24 Z" fill="none" stroke="#ffc857" strokeWidth="2.4" />
        <text x="14" y="20" textAnchor="middle" fill="#ffc857"
              fontFamily="sans-serif" fontSize="13" fontWeight="800">!</text>
      </g>
    </Base>
  );
}

function Sports() {
  return (
    <Base id="cv-sports" from="#06231a" to="#0a3324">
      {/* cricket ball */}
      <g>
        <circle cx="120" cy="62" r="30" fill="#26100c" stroke="#ff6b5e" strokeWidth="2.4" />
        <path d="M104 38 Q96 62 104 86" fill="none" stroke="#ff9d8f" strokeWidth="2" strokeDasharray="3 4" />
        <path d="M136 38 Q144 62 136 86" fill="none" stroke="#ff9d8f" strokeWidth="2" strokeDasharray="3 4" />
      </g>
      {/* football */}
      <g stroke="#e8f2ff" strokeWidth="2" fill="none">
        <circle cx="222" cy="62" r="30" />
        <polygon points="222,50 233,58 229,72 215,72 211,58" fill="#e8f2ff" opacity="0.9" />
        <line x1="222" y1="50" x2="222" y2="34" /><line x1="233" y1="58" x2="248" y2="52" />
        <line x1="229" y1="72" x2="240" y2="84" /><line x1="215" y1="72" x2="204" y2="84" />
        <line x1="211" y1="58" x2="196" y2="52" />
      </g>
      <circle cx="286" cy="30" r="3" fill="#35e0a1" />
      <circle cx="62" cy="92" r="3" fill="#35e0a1" />
    </Base>
  );
}

function Reel() {
  return (
    <Base id="cv-any" from="#0b1526" to="#12203a">
      <g stroke="#38e1ff" strokeWidth="2" fill="none">
        <rect x="130" y="32" width="80" height="60" rx="10" />
        <path d="M162 48 L186 62 L162 76 Z" fill="#38e1ff" />
      </g>
      {[86, 100, 254, 268].map((x) => (
        <rect key={x} x={x} y={54 - (x % 30)} width="7" height={30 + (x % 40)}
              rx="3" fill="#2b74c9" opacity="0.8" />
      ))}
    </Base>
  );
}

const COVERS = {
  world_in_data: Globe,
  india_in_data: Chakra,
  ml_concept: Neural,
  ai_trends: Chip,
  money: Coins,
  charts_lie: LieChart,
  sports: Sports,
};

export default function PlaylistCover({ series }) {
  const Cover = COVERS[series] || Reel;
  return <div className="pl-cover"><Cover /></div>;
}
