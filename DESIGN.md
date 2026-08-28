---
name: Multiagent Chat
description: Flight-deck console for an autonomous six-agent engineering team.
colors:
  telemetry-blue: "#3fb6ff"
  verdict-green: "#49e08a"
  gate-amber: "#ffb545"
  fault-red: "#ff5c6e"
  retrieval-violet: "#a98bff"
  void: "#04060c"
  hull-900: "#05080f"
  hull-800: "#080d18"
  hull-700: "#0b1120"
  hull-600: "#101a2d"
  hull-400: "#243352"
  mist: "#8fa3c4"
  ink: "#dce6f7"
typography:
  display:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "34px"
    fontWeight: 500
    lineHeight: 1
    fontFeature: "tabular-nums"
  headline:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.45
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "0.14em"
  micro:
    fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace"
    fontSize: "10px"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "0.12em"
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "16px"
  pill: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
components:
  button-primary:
    backgroundColor: "#3fb6ff26"
    textColor: "#f8fafc"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "#3fb6ff40"
    textColor: "#f8fafc"
  button-ghost:
    backgroundColor: "#00000000"
    textColor: "{colors.mist}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
    height: "44px"
  button-ghost-hover:
    backgroundColor: "{colors.hull-600}"
    textColor: "#f1f5f9"
  input-field:
    backgroundColor: "{colors.hull-800}"
    textColor: "#f1f5f9"
    rounded: "{rounded.md}"
    padding: "6px 12px"
    height: "56px"
  panel:
    backgroundColor: "{colors.hull-700}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xl}"
    padding: "20px"
  badge-phase:
    backgroundColor: "#3fb6ff1a"
    textColor: "{colors.telemetry-blue}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "4px 12px"
---

# Design System: Multiagent Chat

## 1. Overview

**Creative North Star: "The Flight Deck"**

Instrumentation you trust because it reads live. The operator is watching six agents
work on a real repository and deciding whether the result reaches their source tree.
Every panel is an instrument: it is connected to something the run actually recorded, it
is ordered by how much it matters to that decision, and it stops moving when the
underlying work stops. The dark hull is not a mood choice — it is the ground that lets
a small number of saturated status colors read instantly as signal.

Density is welcome; competition for attention is not. Screens carry a great deal of
information at once — a graph, a live event ticker, a diff, a scorecard, model usage —
and stay legible because only one thing is primary per surface and because nearly all
supporting data is set in monospace at label scale. The largest type in the entire system
is a tabular monospaced number (the reviewer's score). That is deliberate: the loudest
element is a measurement, not a headline.

This system explicitly rejects the generic SaaS dashboard — identical card grids,
oversized hero metrics with gradients, decorative iconography standing in for
information. It equally rejects the CI log viewer: raw output with flat hierarchy is
what this interface exists to replace. Above all it rejects performing activity it is
not doing; motion here is evidence, and a graph that looks alive while receiving no
data is a defect this codebase has already had to fix.

**Key Characteristics:**
- Dark hull ground (`#04060c`–`#0b1120`) with a fine circuit-grid texture
- Translucent glass panels as the single container material
- Five saturated status colors, each with one fixed meaning
- Monospace for all data, identifiers, telemetry and labels; Inter for prose
- Tonal depth by default; glow reserved exclusively for live state

## 2. Colors: The Telemetry Palette

A near-black blue hull carrying five saturated signal colors, each with exactly one
job. Because the ground is so dark and so desaturated, any saturated pixel reads as
meaningful — which is precisely why saturation is rationed.

### Primary
- **Telemetry Blue** (`#3fb6ff`): The live-system color. Active agent, current route
  hop, forward edges and their particle flow, focus rings, primary actions, selected
  tabs. If something is happening right now or is the one action to take, it is this
  color. Nothing decorative may use it.

### Secondary
- **Verdict Green** (`#49e08a`): Settled positive outcomes — approved, applied, added
  diff lines, a completed agent node, a passing tool result. Reserved for facts that
  are finished, never for progress.
- **Gate Amber** (`#ffb545`): Human attention required and remediation. Review-required
  phase, rejection loops in the graph, iteration badges, provider warnings, the
  operator gate. Amber means the run needs a person or is going around again.

### Tertiary
- **Retrieval Violet** (`#a98bff`): The RAG and provenance channel — retrieved
  documents, relevance scores, hunk headers, cloud provider badges. It separates
  "where this came from" from "what happened".
- **Fault Red** (`#ff5c6e`): Failure and removal only. Failed phases, error events,
  deleted diff lines, apply failures.

### Neutral
- **Void** (`#04060c`): The page ground beneath the circuit grid.
- **Hull 900 / 800 / 700 / 600** (`#05080f`, `#080d18`, `#0b1120`, `#101a2d`): The
  surface ramp. 900 anchors the sticky composer, 800 fills inputs and inset wells, 700
  is the glass panel body, 600 is the hover state for interactive rows.
- **Hull 400** (`#243352`): The border and divider color, used at low opacity almost
  everywhere. The most-used token in the system.
- **Mist** (`#8fa3c4`): Secondary and tertiary text — labels, units, line numbers. Exactly
  two steps exist: solid (7.4:1) and 80% (5.1:1).
- **Ink** (`#dce6f7`): Body text on hull surfaces.

### Named Rules

**The One Meaning Rule.** Each status color has exactly one semantic job across the
entire product. Green is never "primary action", amber is never "highlight", violet is
never "pretty accent". A reader who learns the five colors once can read any screen.

**The Signal Ration Rule.** Saturated color covers a small minority of any screen. The
hull ramp and mist carry structure; color carries state. If a screen looks colorful,
state has been diluted into decoration.

**The Mist Floor Rule.** Mist is legible at 80% opacity and above; every step below that
measures under 4.5:1 on all three hull surfaces. Prohibited: `text-mist` at 45–70%, which
once produced five failing steps that no reader could tell apart anyway.

**The Never-Color-Alone Rule.** Color always travels with a word or a symbol. Phase
badges carry their label, diff lines carry `+`/`-`, agent nodes carry `active`/`done`,
tool results carry `SUCCESS`/`FAIL`. Prohibited: encoding any status in hue alone.

## 3. Typography

**Display / Data Font:** JetBrains Mono (with `ui-monospace`, `SFMono-Regular`, monospace)
**Body Font:** Inter (with `ui-sans-serif`, `system-ui`, sans-serif)

**Character:** A single humanist sans for language and a single monospace for
everything measured. The pairing is not stylistic contrast for its own sake — it is a
functional split. If a value could be compared, counted, copied or correlated with a
log, it is monospaced. Inter appears only where a human is being addressed in sentences.

### Hierarchy
- **Display** (Mono, 500, 34px, line-height 1, tabular): The reviewer's total score, and
  nothing else. The system's largest element is a measurement.
- **Headline** (Inter, 600, 14px, tracking -0.01em): Panel titles — "Code changes",
  "Run history", "Mission Debrief".
- **Title** (Inter, 500, 13px): Run instructions, agent node names, primary row text.
- **Body** (Inter, 400, 12px, line-height 1.6): Explanatory prose, empty-state guidance,
  error recovery text. Capped at 62–75ch.
- **Label** (Mono, 11px, tracking 0.14em, uppercase): The workhorse. Phase badges, metric
  captions, provider chips, route hops, column headers, timestamps.
- **Micro** (Mono, 10px, tracking 0.12em, uppercase): The floor. Legends, units, ordinals,
  relative times. Nothing renders below this.

### Named Rules

**The Measured-Is-Mono Rule.** Identifiers, counts, durations, token totals, paths,
model names, trace IDs, scores and code are always monospace with `tabular-nums` where
they sit in a column. Prohibited: a run identifier or latency value set in Inter.

**The Tracking Floor Rule.** Uppercase mono labels carry 0.10em–0.18em tracking; at
10–11px, uppercase without tracking is unreadable. Sentence-case text never gets
positive tracking.

**The Seven Steps Rule.** The ramp is 34 / 16 / 14 / 13 / 12 / 11 / 10 and nothing else.
Every step is a perceptible move. Prohibited: half-pixel steps and 9px, which produced
four indistinguishable sizes inside a 1.5px band and read as drift, not hierarchy.

## 4. Elevation

Depth is tonal, not cast. Hierarchy comes from where a surface sits on the hull ramp and
from a 1px `hull-400` border at low opacity — not from stacked shadows. Exactly one
ambient shadow exists (`panel`), and it is a grounding device for glass containers rather
than a lift: a deep, wide, very dark drop plus a 1px inset white highlight that reads as
the top edge catching light.

Glow is the system's only other shadow vocabulary, and it is strictly a **state**
response. A glow means something is live, approved, or failing right now. Nothing glows
at rest.

### Shadow Vocabulary
- **Panel** (`box-shadow: 0 18px 50px -24px rgba(0,0,0,0.9), inset 0 1px 0 rgba(255,255,255,0.05)`):
  Every glass container. Ambient and permanent; grounds the panel against the circuit grid.
- **Glow Electric** (`box-shadow: 0 0 0 1px rgba(63,182,255,0.45), 0 0 24px -4px rgba(63,182,255,0.55)`):
  The currently-executing agent node. One at a time, ever.
- **Glow Neon** (`0 0 0 1px rgba(73,224,138,0.45), 0 0 24px -4px rgba(73,224,138,0.5)`):
  Approved / applied confirmation.
- **Glow Amber** (`0 0 0 1px rgba(255,181,69,0.45), 0 0 24px -4px rgba(255,181,69,0.5)`):
  Human review required.
- **Glow Alert** (`0 0 0 1px rgba(255,92,110,0.5), 0 0 26px -4px rgba(255,92,110,0.55)`):
  Failure states.

### Named Rules

**The Glow-Is-State Rule.** A glow is a claim that something is happening. It is
forbidden as emphasis, as hover, or as decoration. If the state ends, the glow ends.

**The Glass-Is-Structure Rule.** `.glass` (`rgba(11,17,32,0.66)`, `blur(14px)`, 1px
`rgba(90,122,170,0.22)` border) is the panel material and `.glass-soft`
(`rgba(11,17,32,0.42)`, `blur(10px)`) is the nested-content material. Blur is how a
container separates from the circuit grid behind it — never a decorative frosting
applied to arbitrary elements.

## 5. Components

Controls are tactile and have presence: real weight, visible contrast, and an
unmistakable response to press. That tactility is achieved with color, border and
opacity — never by moving anything.

### Buttons
- **Shape:** Tightly rounded corners (6px, `rounded-md`), never pill-shaped for actions.
- **Primary:** Telemetry-blue wash (`#3fb6ff` at 15%) inside a 50%-opacity
  telemetry-blue border, near-white label, 16px horizontal padding, minimum 44px tall.
- **Hover / Focus:** Background deepens to 25% on hover; focus shows a 2px
  telemetry-blue outline offset 4px from the control. Transition is color only, 200ms.
- **Ghost / Secondary:** No fill at rest, mist label; on hover the surface fills to
  `hull-600` and the label lifts to near-white. Used for "Enter path", "Back to history".
- **Destructive-adjacent:** Restore actions take gate amber, visually separated from
  primary actions rather than sitting beside them.
- **Disabled:** 40–50% opacity with `not-allowed` cursor; never merely dimmed text.

### Chips and Badges
- **Phase badge:** 1px border, 10–12% tinted fill, uppercase mono label at 0.14em
  tracking, in whichever status color the phase maps to.
- **Provider chip:** Same construction, carrying an inline 10px icon (CPU for local,
  cloud for hosted) plus the provider name — the icon is redundant with the color by
  design.
- **Iteration badge:** Gate amber, appears in the route trace only where the iteration
  number actually changes.

### Cards / Containers
- **Corner Style:** Generously rounded (16px, `rounded-2xl`) for top-level panels; 12px
  for inset wells; 8px for rows inside a list.
- **Background:** `.glass` for panels, `.glass-soft` for nested content, `hull-800` at
  40% for inset wells.
- **Shadow Strategy:** `panel` only. See Elevation.
- **Border:** 1px `hull-400` at 30–55% opacity. Full borders only.
- **Internal Padding:** 20px for panels, 12px for wells, 10–12px for list rows.

### Inputs / Fields
- **Style:** `hull-800` fill inside a solid 1px `hull-400` border, 8px radius, mist
  placeholder, near-white value text.
- **Focus:** Border shifts to telemetry blue with a 1px ring of the same color. No glow.
- **Sizing:** Minimum 44px tall on touch; the composer's textareas relax to 56px on
  pointer-fine screens where vertical space is scarce.
- **Labels:** Always visible above the field, paired with the equivalent CLI flag in
  mono (`--spec`, `--test-spec`) so screen and command line share one vocabulary.

### Navigation
- **Sticky header** carrying the brand mark, the selected project path in mono, a
  backend health badge, and folder selection. **Sticky composer** at the bottom, capped
  at roughly two-thirds of its natural height so the middle of the screen stays for work.
- **Tabs** (changed files, evidence) use a 2px telemetry-blue underline that animates
  between tabs via a shared layout transition; inactive tabs are mist and fill to
  `hull-600` on hover. Every tablist is wired to its panel with `aria-controls`.

### Signature Component: The Agent Graph
The product's centerpiece: seven positioned agent nodes on a 1400×520 canvas connected
by SVG paths. Nodes hold three states — idle (60% opacity, muted), active (telemetry
border, electric glow, pulsing ring, spinning indicator, `active` label), and done
(verdict-green border and icon, `done` label). Forward edges are telemetry blue, rejection
loops amber, human branches amber dashed. The traversed edge carries three glowing
particles moving continuously via SMIL `animateMotion`, staggered at 0 / 0.34 / 0.67 of
the cycle. Beneath it, a **route trace** lists every hop the run actually walked, marking
remediation loops with a turn-back icon and opening each new iteration with an amber badge.

Every one of those states is derived from recorded run events. The graph has no
simulation path and must never acquire one.

## 6. Do's and Don'ts

### Do:
- **Do** derive every animated or stateful visual from recorded run events. If the data
  is absent, render the absence honestly — a trace not yet assigned reads `pending`, a
  file with no hunks explains why.
- **Do** pair every status color with a word or symbol.
- **Do** keep body and data text at or above 4.5:1 against its surface. Line numbers,
  units and captions are data, not decoration; `mist` below 70% opacity fails this.
- **Do** withhold SMIL animation in JavaScript when `prefers-reduced-motion` is set. The
  global CSS rule in `index.css` neutralizes CSS transitions but cannot touch
  `<animateMotion>`.
- **Do** give every interactive control a visible focus ring: 2px telemetry blue, offset
  4px. There are 56 of these in the codebase; the count should only grow.
- **Do** keep touch targets at 44px minimum, relaxing only above the `md` breakpoint.
- **Do** bound provider-authored text (tool details, status messages, RAG snippets) and
  offer the full value behind an explicit disclosure.

### Don't:
- **Don't** build a **generic SaaS dashboard**: no identical card grids, no oversized
  hero metric with a gradient, no decorative iconography standing in for information.
- **Don't** fall back to a **CI log viewer**: raw output with flat hierarchy is the
  thing this interface replaces.
- **Don't** ship a system that **performs activity it is not doing** — animated state not
  driven by recorded events, progress that advances on a timer, or a graph that looks
  alive while receiving no data.
- **Don't** use `border-left` or `border-right` greater than 1px as a colored accent
  stripe. Diff lines, list rows and callouts use background tint plus a sign or label.
  This was removed from the diff viewer; it does not come back.
- **Don't** apply `background-clip: text` with a gradient. Emphasis comes from weight,
  size and color, never from gradient text.
- **Don't** use blur decoratively. Glass is the container material; it is not a finish
  to apply to arbitrary elements.
- **Don't** animate layout properties for press feedback. Tactility comes from
  background, border and opacity; a control that shifts its neighbors on press is broken.
- **Don't** let a glow, a pulse or a spinner persist once the state that justified it
  has ended.
- **Don't** set an identifier, latency, token count or path in Inter. If it is measured,
  it is monospace.
- **Don't** introduce a sixth status color. Five have fixed meanings; a sixth dilutes all
  of them.
