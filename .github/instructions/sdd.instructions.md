---
applyTo: ".specify/**/*.md,specs/**/*.md"
---

# SDD artifact rules

Do not silently modify Constitution, Spec, Plan, or Tasks. Respect
Constitution > Spec > Plan > Tasks > implementation. Preserve FR/NFR/AC IDs,
avoid unnecessary renumbering, and maintain evidence traceability.

Constitution and Spec contain no implementation design; Plan and Tasks add no
new requirements. A contractual change must update the higher-precedence SDD
artifact before downstream artifacts. Do not change approved scenarios or
expected outcomes merely to make tests pass.
