# FORGEAI — UI/UX DESIGN BRIEF
## God Mode Ultra Pro Max | June 2026
## "Dark. Dense. Developer-First. Data-Obsessed."

---

## 1. DESIGN PHILOSOPHY

**Core Principle: "Invisible Until It Matters"**
ForgeAI runs in the background. Captures events silently. Trains while the developer sleeps. The UI should reflect this — minimal interruption, maximum information density when developer opens the dashboard, zero friction in the daily workflow.

**Three Design Laws:**
1. Every pixel earns its place — no decorative elements
2. Data is the hero — charts and numbers, not marketing copy
3. Speed over beauty — p90 interaction response <100ms

**Reference Products (but different):**
- Linear.app (density, speed, keyboard-first)
- Vercel dashboard (dark, professional, clear hierarchy)
- Datadog (information density, real-time data)
- Raycast (developer-first, command palette)
- NOT: Notion (too light), Figma (too creative), Canva (too consumer)

---

## 2. DESIGN SYSTEM

### 2.1 Color Palette

```
Background System:
  bg-base:      #0A0A0B    (deepest dark — main background)
  bg-surface:   #111114    (cards, modals)
  bg-elevated:  #18181C    (dropdowns, popovers)
  bg-subtle:    #1E1E23    (hover states, subtle sections)

Border System:
  border-base:  #27272C    (subtle dividers)
  border-muted: #323237    (stronger dividers)
  border-focus: #5B5BFF    (focus rings, active states)

Text System:
  text-primary:   #FAFAFA  (main content)
  text-secondary: #A1A1AA  (labels, descriptions)
  text-muted:     #71717A  (placeholders, disabled)
  text-disabled:  #3F3F46  (truly inactive)

Brand Colors (Forge Spectrum):
  forge-primary:   #5B5BFF  (main CTA, links, active states)
  forge-secondary: #7C3AED  (secondary actions, gradients)
  forge-accent:    #06B6D4  (data highlights, charts)
  forge-glow:      rgba(91,91,255,0.15)  (card highlights, focus glow)

Semantic Colors:
  success:  #22C55E   (acceptance rate up, training complete)
  warning:  #F59E0B   (low training data, partial results)
  error:    #EF4444   (training failed, connection lost)
  info:     #3B82F6   (neutral information)

Chart Palette (color-blind safe):
  chart-1: #5B5BFF   (primary metric — acceptance rate)
  chart-2: #06B6D4   (secondary metric — suggestions count)
  chart-3: #22C55E   (success metric — training improvement)
  chart-4: #F59E0B   (warning metric — rejection rate)
  chart-5: #8B5CF6   (comparison baseline)

Training Loss Gradient:
  high-loss:  #EF4444 → low-loss: #22C55E
  (red to green as training progresses)
```

### 2.2 Typography

```
Primary Font: "Geist" (Vercel's font — developer-optimized, free)
  or fallback: "Inter"
  Weights used: 400 (body), 500 (labels), 600 (headings), 700 (display)

Mono Font: "Geist Mono"
  or fallback: "JetBrains Mono", "Fira Code"
  Used: code snippets, file paths, metric numbers, training logs

Font Scale:
  display:  36px / 700 weight  (hero, major numbers)
  h1:       24px / 700 weight
  h2:       20px / 600 weight
  h3:       16px / 600 weight
  body:     14px / 400 weight
  small:    12px / 400 weight
  micro:    11px / 400 weight  (status bars, tooltips)

Numbers (special treatment):
  Metric numbers: Geist Mono, tabular-nums, 28-48px
  "74.2%" → Geist Mono 48px forge-primary color
  Always tabular so numbers don't shift width
```

### 2.3 Spacing System

```
Base unit: 4px (0.25rem)
Scale: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96

Component spacing:
  Card padding: 20px
  Section gap: 24px
  Grid gap: 16px
  Inline element gap: 8px
  Button padding: 10px 16px (md), 8px 12px (sm)
```

### 2.4 Component Patterns

```
CARDS:
  Background: bg-surface (#111114)
  Border: 1px solid border-base (#27272C)
  Border-radius: 8px
  Shadow: 0 1px 3px rgba(0,0,0,0.3)
  Hover: border-color → border-muted, shadow lift
  Active/focus: border-color → forge-primary, glow effect

BUTTONS:
  Primary: bg-forge-primary, text-white, hover: opacity-90
  Secondary: bg-bg-elevated, border border-muted, hover: border-forge-primary
  Destructive: bg-transparent, text-error, hover: bg-error/10
  Ghost: bg-transparent, text-secondary, hover: bg-bg-subtle
  All: border-radius 6px, transition 150ms, font-weight 500

INPUT FIELDS:
  Background: bg-base
  Border: 1px solid border-base
  Focus: border-forge-primary, box-shadow: 0 0 0 2px forge-glow
  Placeholder: text-muted
  Error: border-error, error message below in text-error font-small

STATUS INDICATORS:
  Online (green dot): 8px circle, #22C55E, subtle pulse animation
  Warning (yellow): #F59E0B
  Error (red): #EF4444
  Training active (blue pulse): #5B5BFF with keyframe animation

CHARTS (Recharts customization):
  Background: transparent (card provides bg)
  Grid lines: border-base, strokeDasharray: "3 3"
  Tooltip: bg-bg-elevated, border border-muted, shadow
  Area chart: forge-primary stroke, forge-glow/20 fill
  Bar chart: forge-primary bars, hover: forge-secondary

CODE BLOCKS:
  Background: bg-base
  Border: 1px solid border-base
  Border-radius: 6px
  Padding: 16px
  Font: Geist Mono 13px
  Syntax highlighting: custom dark theme (VS Code Dark+ inspired)
  Line numbers: text-muted on left
  Copy button: top-right, appears on hover

BADGES / TAGS:
  Default: bg-bg-subtle, text-secondary, border border-base
  Success: bg-success/10, text-success, border border-success/20
  Warning: bg-warning/10, text-warning
  Error: bg-error/10, text-error
  Brand: bg-forge-primary/10, text-forge-primary
```

### 2.5 Animation Principles

```
Timing: 150ms for interactions, 300ms for page transitions, 500ms for charts
Easing: cubic-bezier(0.4, 0, 0.2, 1) (standard Material easing)
Principles:
  - Enter: fade + subtle upward translate (4px)
  - Exit: fade only (no translate — faster perceived)
  - Loading: skeleton screens (not spinners for content)
  - Numbers: count-up animation on first load (1000ms duration)
  - Charts: draw animation on first render (600ms, left to right)
  - Training progress: smooth bar fill (real-time WebSocket)

Micro-interactions:
  Button click: scale(0.97) on press, release
  Accept event: brief green flash on status bar counter
  Training complete: confetti burst (subtle, once) on first time
  Chart improvement: green arrow animation when rate goes up
```

---

## 3. SCREEN LAYOUTS

### 3.1 Landing Page Layout

```
┌─────────────────────────────────────────────────┐
│  NAV: ForgeAI logo | Docs | Pricing | GitHub    │
│       [Sign in]  [Install Free →]               │
├─────────────────────────────────────────────────┤
│  HERO SECTION (dark, full width)                │
│                                                 │
│  "The AI that gets smarter every time you code" │
│  [Geist 48px, text-primary, centered]           │
│                                                 │
│  "Real model fine-tuning. Not prompts.          │
│   Your codebase. Your weights. Your server."    │
│  [16px, text-secondary, centered]               │
│                                                 │
│  [Install in 5 minutes →] [View Demo]           │
│  [Primary CTA: 48px height, forge-primary]      │
│                                                 │
│  Social proof: "Trusted by 2,400 developers"   │
│  [Company logo strip — placeholder initially]   │
├─────────────────────────────────────────────────┤
│  PROOF SECTION (acceptance rate demo)           │
│                                                 │
│  "Same Team. Real Data."                        │
│                                                 │
│  Week 1: ████░░░░░░ 31%   Week 12: ████████ 74%│
│                                                 │
│  [Animated chart — draws in on scroll]          │
│  Training run markers visible on chart          │
├─────────────────────────────────────────────────┤
│  HOW IT WORKS (3 columns, icon + text)          │
│                                                 │
│  [Capture]        [Train]          [Improve]    │
│  Accept code  →  Weekly LoRA   →  Better model  │
│                                                 │
│  [See full technical details ↗]                │
├─────────────────────────────────────────────────┤
│  COMPETITOR COMPARISON TABLE                    │
│                                                 │
│  Feature        | ForgeAI | Copilot | Cursor    │
│  Model learning |   ✓     |   ✗     |   ✗       │
│  On-premise     |   ✓     |   ✗     |   ✗       │
│  ...            |         |         |           │
├─────────────────────────────────────────────────┤
│  PRICING PREVIEW (3 cards)                      │
├─────────────────────────────────────────────────┤
│  FOOTER: Links, GitHub, Discord, Twitter        │
└─────────────────────────────────────────────────┘
```

### 3.2 Main Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  SIDEBAR (240px, fixed)    │  MAIN CONTENT                      │
│  ─────────────────────     │  ─────────────────────────────     │
│  [ForgeAI logo]           │  TOP BAR:                          │
│                           │  "Dashboard" [project selector ▼]  │
│  ● Dashboard              │  Model: qwen2.5-14b+v12 [change]   │
│  ○ Agent Chat             │                                    │
│  ○ Training               │  METRICS ROW (4 cards):            │
│  ○ Projects               │  ┌──────┐ ┌──────┐ ┌──────┐ ┌───┐ │
│  ○ Skills Market          │  │ 74.2%│ │+43pp │ │  12  │ │ ✓ │ │
│  ○ Analytics              │  │accept│ │since │ │runs  │ │ok │ │
│  ─────────────────────    │  │ rate │ │wk 1  │ │total │ │   │ │
│  ○ Settings               │  └──────┘ └──────┘ └──────┘ └───┘ │
│  ─────────────────────    │                                    │
│  FREE TIER BANNER         │  ACCEPTANCE RATE CHART (full width)│
│  "Upgrade to train your   │  [12-week area chart, forge-primary]│
│   model → Go $9/mo"       │  [Training run markers as dots]    │
│                           │                                    │
│  ─────────────────────    │  2-COL GRID:                       │
│  Status: ● Connected      │  ┌─────────────────┐ ┌──────────┐ │
│  Model: v12 active        │  │ Recent Runs     │ │ ROI Calc │ │
│  Events today: 47         │  │ [list, 5 items] │ │ $24,500  │ │
│  Next training: Sun 2AM   │  │                 │ │ /month   │ │
│                           │  └─────────────────┘ └──────────┘ │
│                           │                                    │
│                           │  RECENT SIGNALS FEED               │
│                           │  [accept/reject events stream]     │
└───────────────────────────┴────────────────────────────────────┘
```

### 3.3 Agent Chat Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ SIDEBAR      │ FILE TREE (240px)  │ CHAT PANEL                  │
│ (240px)      │ ──────────────     │ ─────────────────────────   │
│              │ 📁 src/            │ ForgeAI Chat           [⚙] │
│              │  ├ 📄 main.py      │                             │
│              │  ├ 📁 api/         │ ┌─────────────────────────┐ │
│              │  │  ├ 📄 routes.py │ │ You: "Refactor          │ │
│              │  │  └ 📄 models.py │ │ authenticate_user to    │ │
│              │  └ 📁 utils/       │ │ use JWT"               │ │
│              │ ──────────────     │ └─────────────────────────┘ │
│              │ ──────────────     │                             │
│              │ MONACO EDITOR      │ ┌─────────────────────────┐ │
│              │                    │ │ ForgeAI: Based on your  │ │
│              │ [file content]     │ │ team's pattern (learned │ │
│              │ [syntax highlight] │ │ from 12 similar accepts)│ │
│              │                    │ │ here's the refactored   │ │
│              │                    │ │ version:               │ │
│              │                    │ │                         │ │
│              │                    │ │ ```python               │ │
│              │                    │ │ def authenticate_user():│ │
│              │                    │ │   ...                   │ │
│              │                    │ │ ```                     │ │
│              │                    │ │ [Apply] [Reject] [Edit] │ │
│              │                    │ └─────────────────────────┘ │
│              │                    │                             │
│              │                    │ ┌─────────────────────────┐ │
│              │                    │ │ Type a message...       │ │
│              │                    │ │ [Model: 14b ▼] [Send]   │ │
│              │                    │ └─────────────────────────┘ │
│              │                    │ Signals today: 47 ✓         │
└──────────────┴────────────────────┴─────────────────────────────┘
```

### 3.4 Training Monitor Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ SIDEBAR │   TRAINING MONITOR                                     │
│         │   ─────────────────────────────────────────────────   │
│         │   ACTIVE RUN (if training in progress):               │
│         │   ┌────────────────────────────────────────────────┐  │
│         │   │ Training v13 — Started 2:00 AM Sunday          │  │
│         │   │ Examples: 847 | Phase: 1 (QLoRA)               │  │
│         │   │                                                │  │
│         │   │ Progress: ████████████░░░░ 68% (136/200 steps) │  │
│         │   │                                                │  │
│         │   │ Current loss: 0.0847 (↓ from 0.2341)          │  │
│         │   │ ETA: 14 minutes                                │  │
│         │   │                                                │  │
│         │   │ [Cancel run]                                   │  │
│         │   └────────────────────────────────────────────────┘  │
│         │                                                       │
│         │   TRAINING HISTORY:                                   │
│         │   ┌────┬──────────┬────────┬──────┬─────────┬──────┐  │
│         │   │ v  │ Date     │ Status │ Exmpl│ Δ Rate  │ BLEU │  │
│         │   ├────┼──────────┼────────┼──────┼─────────┼──────┤  │
│         │   │ 12 │ Jun 8    │ ✅     │ 847  │ +3.2pp  │ 0.72 │  │
│         │   │ 11 │ Jun 1    │ ✅     │ 791  │ +4.1pp  │ 0.69 │  │
│         │   │ 10 │ May 25   │ ⚠ RB  │ 456  │ -2.1pp  │ 0.61 │  │
│         │   │ 9  │ May 18   │ ✅     │ 812  │ +5.8pp  │ 0.67 │  │
│         │   └────┴──────────┴────────┴──────┴─────────┴──────┘  │
│         │   (click any row → full details + loss curve chart)   │
│         │                                                       │
│         │   [Force Training Run]  [Change Schedule]             │
└─────────┴───────────────────────────────────────────────────────┘
```

---

## 4. KEY UX DECISIONS

### 4.1 Keyboard Navigation
Every action keyboard-accessible:
- `Cmd+K` — Command palette (search everything)
- `Cmd+Shift+A` — Open ForgeAI agent chat
- `Cmd+Shift+T` — View training status
- `Tab/Escape` — Accept/reject suggestion (VS Code)
- `Cmd+Enter` — Send message in chat
- `Cmd+P` — Switch project

### 4.2 Onboarding Progressive Disclosure
Day 1: Show only what's needed — extension install, first project.
Day 3: Unlock training preferences card.
Week 2: Unlock skills marketplace when 100+ accepts captured.
Month 2: Unlock analytics after 2 training runs complete.
This prevents overwhelming first-time users.

### 4.3 Empty States — Every State Handled
Charts with no data: Illustration + "Accept 50 suggestions to start training"
Training history empty: "Your first training run will appear here Sunday"
Skills marketplace browsing with no projects: "Add a project to install adapters"
Agent with no RAG index: Warning banner + "Index your project for better suggestions"

### 4.4 Toast Notification System
Position: Bottom-right
Duration: 4 seconds (success), 6 seconds (warning), persistent (error)
Types:
- "✓ Training complete — +5.2% acceptance rate" (success, auto-dismiss)
- "⚠ Low training data — only 23 examples this week" (warning, auto-dismiss)
- "✗ Training failed — GPU out of memory" (error, with action button)
- "↺ Model rolled back to v11 — quality guard triggered" (warning, persistent)

### 4.5 Loading States
Skeleton screens for: dashboard cards, training history table, marketplace grid
Shimmer animation: same width as expected content
No spinners for content — only for actions (button clicks, form submits)
Real-time data (training progress): WebSocket updates, no loading state

### 4.6 Mobile Responsive
Dashboard: readable on mobile, charts scroll horizontally
Agent chat: full-screen on mobile, editor hidden, chat-only mode
Training monitor: card-based on mobile, no horizontal tables
Priority: Desktop first (developer tool), tablet second, mobile read-only

### 4.7 Accessibility
WCAG 2.1 AA compliance
Contrast ratios: all text passes 4.5:1 minimum
Focus indicators: visible forge-primary outline on all interactive elements
Screen reader: ARIA labels on all custom components
Color: never used as sole differentiator (always paired with shape/text)
Reduced motion: respects prefers-reduced-motion, disables all animations

---

## 5. VS CODE EXTENSION UI

```
STATUS BAR (bottom of VS Code):
┌──────────────────────────────────────────────────────────────────┐
│ ... [●  ForgeAI  v12  |  47 signals today  |  Training: Sun 2AM]│
└──────────────────────────────────────────────────────────────────┘
- Click → opens ForgeAI sidebar panel
- ● = green (connected), ⚠ = yellow (warning), ✗ = red (disconnected)
- Signals counter: animates +1 on each accept (for 500ms)
- During training: shows progress % instead of next training time

SIDEBAR PANEL (ForgeAI tab):
┌─────────────────────────┐
│ 🔥 ForgeAI              │
│ ─────────────────────── │
│ Model: qwen2.5-14b + v12│
│ 74.2% acceptance rate   │
│ ↑ 43pp since week 1     │
│                         │
│ Today's signals:  47 ✓  │
│ ─────────────────────── │
│ [Open Dashboard ↗]      │
│ [Open Agent Chat ↗]     │
│ [Force Training Run]    │
│ ─────────────────────── │
│ Latest run: Jun 8 ✅    │
│ Examples: 847           │
│ Improvement: +3.2pp     │
└─────────────────────────┘

INLINE SUGGESTION UI (in editor):
- Accept: Tab key (standard VS Code behavior intercepted)
- Reject: Escape (standard)
- Quick tag (optional): Cmd+Shift+R → floating tag picker
  [wrong_lib] [wrong_pattern] [style] [other]
  → Richer rejection signal for training
```

---

## 6. DESIGN DELIVERABLES CHECKLIST

For first launch, these screens need full design:
- [ ] Landing page (desktop + mobile)
- [ ] Signup / Login pages
- [ ] Onboarding wizard (4 steps)
- [ ] Main dashboard
- [ ] Agent chat interface
- [ ] Training monitor
- [ ] Settings pages (5 tabs)
- [ ] VS Code extension sidebar
- [ ] Empty states for all main screens
- [ ] Error states for all main screens
- [ ] Pricing page

For Month 3 launch:
- [ ] Skills marketplace
- [ ] Analytics dashboard (Team tier)
- [ ] Mobile-optimized dashboard
- [ ] Dark/light mode toggle (default: dark)
