# Product

## Register

product

## Platform

web

## Users

The primary user is the engineer who owns the repository being changed: they know the
codebase, they know what a correct change looks like there, and they are the one who
decides whether the agents' work gets applied. Their context is an ordinary engineering
task, not an experiment — they have a change they want made and they are evaluating
whether this system made it correctly.

Two further audiences use the same surface without that owner's context. Other software
engineers run it against repositories they own but did not build this tool for, so
nothing may assume familiarity with the agent pipeline. Technical stakeholders watch a
run live during a demo and judge, in a single execution, whether the system is credible.
Both read the interface cold; neither gets a briefing first.

## Product Purpose

Six specialized agents — Product, Architecture, Developer, Security, Testing and
Reviewer — take a plain-language change request and carry it through requirements,
design, implementation, security scanning, testing and review against an isolated copy
of a real project. The operator reviews the result and decides whether it reaches their
source tree.

A run succeeded when the proposed change was correct and the operator applied it.
That is the outcome the product is measured on. Everything the interface shows —
the diff, the scorecard, the route the run took, the models that answered — exists to
make that one decision well-founded. Evidence is not the deliverable; the applied
change is, and the evidence is how the operator earns confidence in it.

## Positioning

Every claim the interface makes is backed by something the run actually recorded.
No inferred status, no simulated progress, no number the system cannot show the
provenance of.

## Brand Personality

A live mission console. The interface should convey that a real, complex system is
executing right now: current stage, telemetry, state that moves because the underlying
work moved. Precise and technical, addressing someone fluent in the domain, but never
theatrical — the drama comes from the run being genuinely underway, not from the
presentation.

The tone is factual under pressure. When something fails, it says what failed and what
the operator can do, without softening or alarm.

## Anti-references

No anti-references were specified, so these are design judgment, grounded in failures
this codebase has already had to correct.

Not a generic SaaS dashboard: no identical card grids, no oversized hero metric with a
gradient, no decorative iconography standing in for information. Not a CI log viewer
either — raw output with flat hierarchy is the opposite of legible to someone reading
a run cold.

Most importantly, not a system that performs activity it is not doing. Animated state
that is not driven by recorded events, progress that advances on a timer, or a graph
that looks alive while receiving no data all contradict the positioning directly. This
has been a real defect here, not a hypothetical one.

## Design Principles

**Evidence serves the decision.** Every panel earns its place by helping the operator
answer "should I apply this?" Evidence displayed for its own sake is noise, and evidence
the operator needs but cannot reach is a defect.

**The console is honest.** Motion, status and provenance are derived from what the run
recorded. If the system does not know something yet, the interface says so rather than
filling the gap — a pending trace reads as pending, an absent diff explains why it is
absent.

**Nothing reaches the source tree implicitly.** Isolation and explicit approval are
product guarantees, so the interface must always make the current blast radius legible:
which project, which files, workspace or source, applied or proposed.

**Readable cold, in one run.** Two of the three audiences arrive without context. A
person who has never seen the pipeline should be able to follow what happened from the
screen alone, without the vocabulary of the implementation.

**Density without noise.** The operator is working, not browsing. Dense information is
welcome; competing emphasis is not. One thing is primary per surface.

## Accessibility & Inclusion

WCAG 2.2 AA is the floor, not an aspiration: 4.5:1 for body and data text, visible focus
on every interactive element, full keyboard operation, and semantic structure that
survives a screen reader.

State is never carried by color alone — phase, diff lines, tool results and node status
each pair color with a label or symbol. Reduced motion is honored for real: the global
CSS rule does not reach SVG SMIL animation, so motion driven by SMIL must be withheld in
code when the user has asked for less of it.
