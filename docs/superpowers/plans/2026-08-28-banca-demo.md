# Banca Demo: implementation and validation

Continue the existing FastAPI/SQLite demo design. Keep tooling and evidence outside
the agent target, in `demo-projects/banca-demo-support/`. Do not commit or push.

1. Verify baseline tests and security scan. Freeze the original text files in a
   checksummed manifest. Test reset on a disposable copy before using the target.
2. Keep seven prompts and test specifications in the demo README; parse those
   blocks as the automation's single source of truth. Require authorized writes.
3. Drive the actual UI with Python Playwright and Chrome. Show history once,
   select project, submit sequential cases, follow active agents, wait for durable
   terminal state, and present every debrief/diff/evidence tab with >=5s dwell.
4. Check positive runs have applied changes, passing source tests, and independent
   feature acceptance checks. Negative runs require security findings, rejected
   review, and unchanged source. Never interpret infrastructure failure as rejection.
5. Preserve attempts, trace IDs, phase, timing, verification and screenshots outside
   the target. Retry non-security failures with cooldown, bounded to prevent endless
   charges. Diagnose failures before changing prompts or infrastructure.
6. Execute all seven live, verify reset and report actual elapsed time. The 10–12
   minute target is a target, not a reason to skip checks or conceal retries.
