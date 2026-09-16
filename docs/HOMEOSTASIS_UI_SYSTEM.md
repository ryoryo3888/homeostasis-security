# HOMEOSTASIS SECURITY UI SYSTEM

Status: design source of truth for v1, v2 and future extensions.

## 1. Principle

HOMEOSTASIS SECURITY is one research series. Every dashboard must look like the same observation terminal, even when the simulated system changes.

**Fixed shell + evolving Earth.**

The frame is shared. The central Earth visualization is version-specific.

- v1: bilateral homeostasis — A国 ↔ B国 communication / interaction around Earth.
- v2: planetary homeostasis — three satellites orbit Earth and represent global observation.
- v2 extended: eight sovereign state agents + resource / governance network around Earth.
- future versions: keep the shell; change only the research-specific Earth layer and necessary domain panels.

Do not redesign the dashboard from scratch for each extension.

## 2. Shared shell — MUST remain visually consistent

All versions use the same visual grammar:

1. HOMEOSTASIS SECURITY brand/header block
2. version navigation in the same position and style
3. dark navy radial background
4. cyan primary accent / magenta secondary accent
5. same panel border, radius, translucent fill and glow
6. same typography hierarchy
7. same spacing scale and overall dashboard width
8. same TURN control language
9. same KPI card language
10. same Agent card language
11. same Event Log language
12. same chart / timeline language
13. same responsive breakpoints and mobile behavior
14. Earth remains the visual center of the primary dashboard

The UI must remain a **visual monitoring system**, not degrade into a text report.

## 3. Core design tokens

Use these tokens as the common family baseline. Individual semantic states may add colors, but must not replace the family palette.

```css
:root {
  color-scheme: dark;
  --hs-bg: #030b14;
  --hs-bg-deep: #07111d;
  --hs-panel: #071827;
  --hs-panel-2: #0b2132;
  --hs-line: rgba(91,220,247,.20);
  --hs-cyan: #67e8f9;
  --hs-cyan-2: #22d3ee;
  --hs-magenta: #d88cff;
  --hs-amber: #fbbf24;
  --hs-green: #34d399;
  --hs-red: #fb7185;
  --hs-text: #edf7fb;
  --hs-muted: #96afbb;
  --hs-radius: 14px;
  --hs-gap: 10px;
  --hs-panel-bg: linear-gradient(180deg,rgba(8,27,42,.94),rgba(3,15,25,.95));
  --hs-panel-shadow: inset 0 0 30px rgba(34,211,238,.025), 0 16px 45px rgba(0,0,0,.22);
}
```

## 4. Shared page hierarchy

Every primary dashboard should follow this hierarchy unless the research requires an explicit exception.

### A. Header / global state
- Brand and Japanese research title
- short research question / subtitle
- version navigation
- global KPI strip
- current TURN / run state

### B. Simulation control
- current condition / scenario when applicable
- previous / direct TURN / next
- state label
- controls must not move to a completely different visual location between versions

### C. Primary observation field
The visual center of the product.

- left: state / Agent information
- center: Earth and version-specific interaction layer
- right: state / Agent / coordinator / event information

Exact column counts may change, but the Earth must remain visually dominant and the panels must use the common component language.

### D. Secondary metrics
Research-specific KPI cards using the shared card design.

### E. Timeline / graphs / event log
Use the same chart, legend and log conventions.

### F. Research detail
Dense tables, methodology, limitations and detailed text belong below the visual dashboard, not in place of it.

## 5. Earth layer by version

### v1 — Bilateral communication Earth
Preserve the identity already established by v1:
- Earth at center
- A国 and B国 as the principal nodes
- visible communication / interaction connection
- state changes reflected around the Earth
- no satellites merely for decoration

### v2 — Planetary observation Earth
Preserve the current v2 identity:
- Earth at center
- three satellites in distinct orbits
- global observation / propagation feeling
- A/B/C and coordinator information around the same shell

### v2 extended — Eight-state closed-loop Earth
Do **not** make this a text-only list of eight countries.

Visualize the closed loop:

`国家 → 地球状態 → 地球調整機関 → 国家判断 → 同時決済 → 新しい地球状態 → 派生イベント`

Recommended Earth-layer semantics:
- 8 sovereign state nodes arranged around the Earth
- node state visible by glow / ring / compact badge
- resource-flow arcs distinct from diplomatic / coordination links
- coordinator represented as a system-level node, not a ninth country
- ACCEPT / REJECT / CONDITIONAL_ACCEPT visible as state responses, not only prose
- resource shortage / congestion visible in the network
- Atomic Settlement result visible as flow outcome
- derived event visible as a new pulse/event marker

Do not force all details into the Earth. Earth shows relationships and state; detailed reasoning remains in Agent panels.

## 6. Component contract

### Panel
Same radius, border, background, glow and internal padding family across all versions.

### KPI
- label: small muted Japanese-first label
- value: large high-contrast value
- optional mini bar / delta
- semantic color only when meaningful

### Agent card
Every Agent card uses the same information order where fields exist:
1. Agent / country name
2. archetype / role
3. compact state metrics
4. current concern / belief
5. action
6. reason
7. response to coordination proposal
8. expandable detail if needed

### Event log
- TURN identifier
- event category
- concise Japanese description
- semantic accent
- chronological order

### TURN control
Same button geometry, active state, arrow behavior and current-turn emphasis across versions.

## 7. Language rules

- Japanese is primary.
- English may be used as a small system label (CURRENT TURN, EVENT LOG, etc.), not as the only explanation.
- Avoid unexplained abbreviations.
- Avoid converting research state into long prose when it can be visualized.
- Detailed methodology text belongs below the main dashboard.

## 8. What may change between versions

Allowed to change:
- Earth interaction layer
- number and role of Agents
- research-specific KPIs
- research-specific secondary panels
- scenario / condition controls
- lower research visualizations

Must remain recognizably shared:
- page shell
- header placement and hierarchy
- version navigation
- palette
- panel grammar
- typography
- TURN grammar
- KPI grammar
- Event Log grammar
- graph grammar
- overall density and futuristic observation-terminal character

## 9. Anti-regression rules

A new version fails visual review if any of the following is true:

- the main dashboard becomes primarily paragraphs of text
- Earth is no longer the visual center without a research reason
- panels use unrelated radius / colors / shadows
- version navigation moves or changes language without reason
- TURN controls are redesigned from scratch
- Agent information loses its card hierarchy and becomes raw text
- Event Log becomes an unstructured text dump
- the page looks like a separate project rather than HOMEOSTASIS SECURITY
- visual density drops substantially because new research fields were rendered only as prose

## 10. Implementation sequence

1. Keep current public main untouched.
2. Work on `homeostasis-ui-system-20260916`.
3. Normalize v1 and v2 to this shared shell while preserving their working data and interactions.
4. Verify that v1 retains bilateral A/B Earth communication.
5. Verify that v2 retains the three-satellite Earth.
6. Build the eight-state extension using the same shell.
7. Keep rejected pilot results out of research aggregation / public dashboard.
8. Only after visual + functional review should any publication or main integration be considered.

## 11. Source-of-truth rule

When future AI work adds a dashboard or research phase, this file is the visual contract. New features extend this system; they do not invent a new dashboard identity.
