"""Live Playwright presentation. No mocked models, synthetic runs or dry runs."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from support import BASELINE, HERE, PROJECT, make_manifest, outcome, read_cases


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def maximize_window(context, page):
    """Resize the native Chrome window, not a simulated Playwright viewport."""
    session = context.new_cdp_session(page)
    try:
        window = session.send("Browser.getWindowForTarget")
        window_id = window["windowId"]
        session.send("Browser.setWindowBounds", {
            "windowId": window_id, "bounds": {"windowState": "maximized"}})
        page.wait_for_timeout(500)
        bounds = session.send("Browser.getWindowBounds", {"windowId": window_id})["bounds"]
        if bounds["windowState"] != "maximized":
            # Some macOS window managers report a zoomed window as normal.
            available = page.evaluate("""() => ({left: screen.availLeft, top: screen.availTop,
                width: screen.availWidth, height: screen.availHeight})""")
            session.send("Browser.setWindowBounds", {
                "windowId": window_id, "bounds": {"windowState": "normal"}})
            session.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": available})
            page.wait_for_timeout(500)
            bounds = session.send("Browser.getWindowBounds", {"windowId": window_id})["bounds"]
            if any(abs(bounds[key] - available[key]) > 10 for key in ("width", "height")):
                raise RuntimeError("Chrome could not be maximized; no demo run was submitted")
        return bounds
    finally:
        session.detach()


def presentation_browser(playwright, profile: Path, headless: bool):
    # Translation is native browser UI, not a page DOM dialog. Disable its offer
    # in this disposable profile instead of clicking unrelated page close buttons.
    preferences = profile / "Default" / "Preferences"
    preferences.parent.mkdir(parents=True, exist_ok=True)
    save(preferences, {"translate": {"enabled": False},
                       "intl": {"accept_languages": "en-US,en,es"}})
    context = playwright.chromium.launch_persistent_context(
        str(profile), channel="chrome", headless=headless,
        no_viewport=not headless,
        viewport={"width": 1440, "height": 1000} if headless else None,
        args=["--start-maximized", "--disable-features=Translate,TranslateUI",
              "--no-first-run", "--no-default-browser-check"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    try:
        bounds = {} if headless else maximize_window(context, page)
        page.bring_to_front()
        page.keyboard.press("Escape")
        return context, page, bounds
    except Exception:
        context.close()
        raise


class Presentation:
    def __init__(self, page, dwell: float, output: Path):
        self.page, self.dwell, self.output = page, dwell, output
        self.views = []
        self.last_agent = None

    def pause(self, seconds=None):
        self.page.wait_for_timeout(1000 * (self.dwell if seconds is None else seconds))

    def show(self, locator, name, *, scroll=True):
        locator.wait_for(state="visible")
        locator.evaluate("el => el.scrollIntoView({behavior:'smooth', block:'center'})")
        self.pause(1)
        shown_seconds = 1.0
        if scroll:
            # Scroll all real overflow containers in this section, in document order.
            # Dividing into 3–8 small smooth steps keeps a whole long table viewable.
            handles = locator.evaluate_handle("""el => [el, ...el.querySelectorAll('*')]
                .filter(n => n.clientHeight > 50 && n.scrollHeight > n.clientHeight + 8
                  && /auto|scroll/.test(getComputedStyle(n).overflowY))""")
            scrollables = []
            for handle in handles.get_properties().values():
                element = handle.as_element()
                if element is None:
                    continue
                size = element.evaluate("el => el.scrollHeight - el.clientHeight")
                scrollables.append((element, size))
                element.evaluate("el => el.scrollTop = 0")
            # Old/new diff panes describe the same change: scroll them together.
            # Sections and file tabs remain sequential, each visible for >=5s.
            groups = [scrollables] if name.startswith("diff") else [[item] for item in scrollables]
            for group in groups:
                if not group:
                    continue
                steps = max(3, min(8, int(max(size for _, size in group) / 180) + 1))
                for step in range(1, steps + 1):
                    for element, size in group:
                        element.evaluate("(el, y) => el.scrollTo({top:y,behavior:'smooth'})", size * step / steps)
                    seconds = max(0.7, (self.dwell - 2) / steps)
                    self.pause(seconds)
                    shown_seconds += seconds
            handles.dispose()
        self.pause(max(1, self.dwell - shown_seconds))
        self.views.append({"section": name, "at": datetime.now(timezone.utc).isoformat()})

    def follow(self):
        graph = self.page.get_by_role("region", name="Live agent graph")
        if graph.count() and graph.is_visible():
            active = graph.get_by_text("active", exact=True)
            if active.count():
                name = active.first.locator("../..").inner_text().splitlines()[0]
                active.first.evaluate("""el => el.parentElement.parentElement.scrollIntoView(
                    {behavior:'smooth',block:'center',inline:'center'})""")
                if name != self.last_agent:
                    self.last_agent = name
                    self.pause(0.45)
                    self.views.append({"section": "active agent: " + name,
                                       "at": datetime.now(timezone.utc).isoformat()})
                    self.page.screenshot(path=str(self.output / f"graph-{len(self.views)}.png"))

    def select_project(self):
        self.page.get_by_role("button", name="Enter path", exact=True).click()
        self.page.get_by_role("textbox", name="Project folder path").fill(str(PROJECT))
        self.pause()
        self.page.get_by_role("button", name="Use folder", exact=True).click()

    def reload_run(self, case, run_id):
        """Recover a disconnected UI from real history; never submit a second run."""
        self.page.reload()
        self.select_project()
        name = "Open run: " + " ".join(case["message"].split())
        self.page.get_by_role("button", name=name, exact=True).click()
        self.page.get_by_role("article", name="Run " + run_id, exact=True).wait_for()

    def debrief(self, case_id, attempt, snapshot):
        page = self.page
        # Mission debrief is a labelled div, not always a semantic region.
        report = page.locator('[aria-label="Mission debrief"]')
        if report.count() == 0:
            return
        self.show(report.locator("header").first, "debrief", scroll=False)
        diff = page.get_by_role("region", name="Code diff")
        if diff.count():
            tabs = diff.get_by_role("tab")
            if tabs.count():
                for index in range(tabs.count()):
                    label = tabs.nth(index).inner_text()
                    tabs.nth(index).click()
                    self.show(diff, "diff: " + label)
            else:
                self.show(diff, "diff (no files)")
        self.show(page.get_by_role("region", name="Reviewer scorecard"), "reviewer")
        self.show(page.get_by_role("region", name="Decision timeline"), "decision timeline")
        for label in ["RAG documents cited", "MCP tools executed", "Errors"]:
            page.get_by_role("tab", name=re.compile("^" + label)).click()
            self.show(page.get_by_role("tabpanel", name=label, exact=True), label)
        self.show(page.get_by_role("region", name="Model usage"), "model usage")
        applied = page.get_by_role("region", name="Apply result", exact=True)
        if applied.count():
            self.show(applied, "apply result")
        page.screenshot(path=str(self.output / f"case-{case_id}-attempt-{attempt}.png"), full_page=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-writes", action="store_true", required=True)
    parser.add_argument("--url", default="http://localhost:5173")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--cases", default="1,2,3,4,5,6,7")
    parser.add_argument("--resume", action="store_true", help="Explicitly allow a partially completed project")
    parser.add_argument("--dwell", type=float, default=5, help="At least 5 seconds per section")
    parser.add_argument("--cooldown", type=float, default=10)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=900, help="Deadline per run; never submits a duplicate while active")
    args = parser.parse_args()
    if args.dwell < 5 or args.cooldown < 5 or args.max_attempts < 1:
        parser.error("dwell and cooldown must be >=5s; max-attempts >=1")
    selected = [int(value) for value in args.cases.split(",")]
    if not selected or selected != sorted(set(selected)) or not set(selected) <= set(range(1, 8)):
        parser.error("cases must be unique, ordered numbers from 1 to 7")
    if not args.resume and make_manifest(PROJECT) != json.loads(BASELINE.read_text()):
        parser.error("Project differs from baseline. Run restore.sh, or use --resume intentionally.")
    cases = [case for case in read_cases(PROJECT / "README.md") if case["id"] in selected]
    output = HERE / "evidence" / datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True)
    started = time.monotonic()
    summary = {"started_at": datetime.now(timezone.utc).isoformat(), "authorize_writes": True,
               "cases_requested": selected, "attempts": [], "complete": False}
    print(f"Evidence: {output}", flush=True)
    with tempfile.TemporaryDirectory(prefix="nova-demo-browser-") as profile, sync_playwright() as playwright:
        context, page, bounds = presentation_browser(playwright, Path(profile), args.headless)
        summary["browser"] = {"headless": args.headless, "bounds": bounds, "translation_enabled": False}
        page.set_default_timeout(15000)
        view = Presentation(page, args.dwell, output)
        try:
            ready_by = time.monotonic() + 60
            while True:
                try:
                    ready = page.request.get(args.url + "/api/runs", timeout=5000)
                    if ready.ok:
                        break
                except PlaywrightError:
                    pass  # Bounded readiness retry; no provider response is logged.
                if time.monotonic() >= ready_by:
                    raise RuntimeError("System not ready; start backend and frontend before the demo")
                view.pause(2)
            page.goto(args.url)
            page.get_by_role("status", name="Backend health").filter(has_text="online").wait_for()
            runs_response = page.request.get(args.url + "/api/runs")
            if not runs_response.ok:
                raise RuntimeError("Cannot inspect active runs")
            if any(run["project_path"] == str(PROJECT) and run["phase"] in
                   {"queued", "preparing", "running", "applying"} for run in runs_response.json()):
                raise RuntimeError("A run for banca-demo is already active")
            history = page.get_by_role("region", name="Run history")
            if selected[0] == 1 and history.count():
                view.show(history, "history (first case only)")
            view.select_project()
            for case in cases:
                for attempt in range(1, args.max_attempts + 1):
                    before = make_manifest(PROJECT)
                    back = page.get_by_role("button", name="Back to history")
                    if back.count():
                        back.click()
                    page.get_by_role("textbox", name="Task", exact=True).fill(case["message"])
                    page.get_by_role("textbox", name="Test specification", exact=True).fill(case["testSpec"] or "")
                    page.get_by_role("radio", name=re.compile("^Authorize writes")).check()
                    view.pause()
                    begin = time.monotonic()
                    with page.expect_response(lambda response: response.request.method == "POST"
                                              and response.url.endswith("/api/runs")) as response_info:
                        page.get_by_role("button", name="Execute with writes", exact=True).click()
                    response = response_info.value
                    if not response.ok:
                        raise RuntimeError(f"Create run failed: HTTP {response.status}")
                    run_id = response.json()["run_id"]
                    entry = {"case": case["id"], "title": case["title"], "attempt": attempt, "run_id": run_id}
                    summary["attempts"].append(entry)
                    save(output / "summary.json", summary)
                    print(f"Case {case['id']} attempt {attempt}: {run_id}", flush=True)
                    while True:
                        result = page.request.get(args.url + "/api/runs/" + run_id)
                        if not result.ok:
                            raise RuntimeError(f"Run polling failed: HTTP {result.status}")
                        snapshot = result.json()
                        view.follow()
                        phase = snapshot["phase"]
                        # approved can be a short transition to auto-apply.
                        if phase in {"applied", "review_required", "failed", "apply_failed"}:
                            break
                        if time.monotonic() - begin > args.timeout:
                            save(output / f"{run_id}.json", snapshot)
                            raise RuntimeError(f"Deadline: {run_id} remains {phase}; no duplicate submitted")
                        view.pause(1)
                    entry.update(phase=phase, trace_id=snapshot.get("trace_id"),
                                 execution_seconds=round(time.monotonic() - begin, 2))
                    save(output / f"{run_id}.json", snapshot)
                    expected_finding = {6: "password reset tokens must expire",
                                        7: "resource access must be ownership-authorized"}.get(case["id"])
                    verdict = outcome(snapshot, negative=case["id"] > 5,
                                      expected_finding=expected_finding)
                    if case["id"] > 5 and make_manifest(PROJECT) != before:
                        raise RuntimeError("Negative case changed the source project; stop and inspect")
                    entry["outcome"] = verdict
                    save(output / "summary.json", summary)
                    print(f"  {phase}, outcome={verdict}, {entry['execution_seconds']}s", flush=True)
                    # Wait for the UI's persisted snapshot, not just network completion.
                    expected_phase = {
                        "applied": "Applied", "review_required": "Review required",
                        "failed": "Failed", "apply_failed": "Apply failed"}[phase]
                    try:
                        page.get_by_test_id("run-phase-badge").filter(has_text=expected_phase).wait_for(timeout=20000)
                    except PlaywrightError:
                        view.reload_run(case, run_id)
                        page.get_by_test_id("run-phase-badge").filter(has_text=expected_phase).wait_for()
                    await_trace = page.get_by_test_id("run-trace-id")
                    if snapshot.get("trace_id") and await_trace.get_attribute("title") != snapshot["trace_id"]:
                        raise RuntimeError("UI trace ID differs from persisted trace ID")
                    view.debrief(case["id"], attempt, snapshot)
                    if verdict == "applied":
                        expected_test = {1: "tests/test_recuperacion.py", 2: "tests/test_bloqueo.py",
                                         3: "tests/test_transacciones_recientes.py", 4: "tests/test_perfil_update.py",
                                         5: "tests/test_operacion_sensible.py"}[case["id"]]
                        if expected_test not in snapshot.get("changed_paths", []) or not (PROJECT / expected_test).is_file():
                            raise RuntimeError("Required new test file was not applied")
                        check = subprocess.run([sys.executable, "-m", "pytest", "-q", "--disable-warnings"],
                                               cwd=PROJECT, capture_output=True, text=True, check=False)
                        (output / f"case-{case['id']}-tests.txt").write_text(check.stdout + check.stderr)
                        entry["source_test_exit_code"] = check.returncode
                        if check.returncode:
                            raise RuntimeError("Applied source tests failed; inspect evidence before retry")
                        independent = subprocess.run(
                            [sys.executable, "-m", "pytest", str(HERE / "test_acceptance.py"),
                             "-q", "--disable-warnings", "--tb=short"], cwd=PROJECT,
                            env={**os.environ, "BANCA_DEMO_THROUGH": str(case["id"])},
                            capture_output=True, text=True, check=False)
                        (output / f"case-{case['id']}-acceptance.txt").write_text(independent.stdout + independent.stderr)
                        entry["acceptance_exit_code"] = independent.returncode
                        if independent.returncode:
                            raise RuntimeError("Independent acceptance failed; inspect the applied implementation")
                        break
                    if verdict == "rejected":
                        break
                    if verdict == "security_stop":
                        # Either a positive case the Security Agent rejected, or the
                        # outbound guardrail refusing to send the context at all. Both
                        # are deliberate stops, and neither is retryable.
                        raise RuntimeError(
                            f"Security stop on case {case['id']}: {(snapshot.get('report') or {}).get('review', {}).get('reason', 'unknown')}"
                            " -- inspect, do not bypass")
                    if phase == "apply_failed":
                        raise RuntimeError("Apply failed; restore the run backup before retrying")
                    if attempt == args.max_attempts:
                        raise RuntimeError("Retry limit reached; evidence preserved")
                    print("  Retrying after cooldown; previous attempt preserved.", flush=True)
                    view.pause(args.cooldown * attempt)
                view.pause(args.cooldown)
            summary["complete"] = True
        except Exception as error:
            summary["error"] = str(error)
            try:
                page.screenshot(path=str(output / "failure.png"))
            except PlaywrightError:
                pass  # Preserve the original failure when the page has closed.
            raise
        finally:
            summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
            summary["views"] = view.views
            save(output / "summary.json", summary)
            context.close()
    print(f"Completed {len(cases)} cases in {summary['elapsed_seconds']}s. Evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
