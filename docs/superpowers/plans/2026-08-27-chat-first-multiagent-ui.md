# Chat-First Multiagent Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local chat-first interface in which each message launches one persistent, observable multiagent run against an isolated copy and an approved diff can be safely applied to the selected original project.

**Architecture:** Split durable run state, native project selection, isolated execution, safe application, and HTTP/WebSocket transport into focused backend modules. Replace the three-screen frontend state machine with a persistent chat shell whose run cards consume backend snapshots and ordered events without inventing status. Apply operations compare source hashes, back up affected files, write atomically, and verify the original project before reporting success.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic 2, LangGraph, pytest, React 18, TypeScript 5.5, Vite 5, Vitest, Testing Library, Tailwind CSS, Framer Motion.

**Spec:** `docs/superpowers/specs/2026-08-27-chat-first-multiagent-ui-design.md`

## Global Constraints

- The application is local-only; the native folder-picker operation accepts loopback clients only.
- Any existing local directory may be selected through the native Windows folder dialog.
- Each submitted chat message starts exactly one independent run and carries no previous-message context.
- Agents and quality tools operate only on `workspace/runs/<run-id>`, never directly on the source project.
- The normalized statuses are exactly `queued`, `preparing`, `running`, `review_required`, `approved`, `failed`, `applying`, `applied`, and `apply_failed`.
- An approved review never implies that source files were written.
- Applying changes requires an approved run, an actual isolated diff, path revalidation, source-conflict detection, backup, controlled writes, and tests against the original project.
- The frontend renders persisted backend facts and never derives approval, changed files, test success, or fatality from presentation logic.
- Primary interface content must remain scrollable and must not depend on fixed viewport heights or hidden overflow.
- Git commits, pushes, pull requests, remote deployment, multiuser access, and non-Windows native pickers are outside this implementation.

## File Structure

- `src/engineering_team/runs/models.py`: durable API/run/apply models and normalized status enum.
- `src/engineering_team/runs/store.py`: atomic JSON persistence, event sequencing, and in-process change notifications.
- `src/engineering_team/project_picker.py`: serialized native Windows folder picker and loopback validation.
- `src/engineering_team/project_api.py`: project-picker HTTP endpoint.
- `src/engineering_team/apply_service.py`: source manifests, conflict detection, backups, atomic writes, verification, and restoration.
- `src/engineering_team/run_api.py`: run orchestration and HTTP/WebSocket routes backed by the durable store.
- `src/engineering_team/run_events.py`: exact snapshot/report projection and warning/fatal provider semantics.
- `src/engineering_team/llm/cloud.py`: sanitized HTTP failure diagnostics.
- `sample_app/app/main.py`: composition root for project and run routers.
- `frontend/src/types/mission.ts`: TypeScript mirror of the public backend contract.
- `frontend/src/api/runClient.ts`: project, run, event, apply, and restore transport.
- `frontend/src/test/FakeRunClient.ts`: complete in-memory `RunClient` used by hook and chat tests.
- `frontend/src/hooks/usePersistentRun.ts`: snapshot-first subscription, cursor replay, and reconnect state.
- `frontend/src/components/chat/ProjectHeader.tsx`: selected project and native-picker control.
- `frontend/src/components/chat/ChatComposer.tsx`: one-message/one-run submission.
- `frontend/src/components/chat/RunCard.tsx`: progressive preparing/running/review/diff/apply presentation.
- `frontend/src/components/chat/ChatWorkspace.tsx`: session run history and active-project state.
- `frontend/src/App.tsx`: chat-shell composition only.
- `frontend/src/index.css`: responsive page-level scrolling and embedded panel sizing.
- `tests/unit/test_run_store.py`, `tests/unit/test_project_picker.py`, `tests/unit/test_apply_service.py`: focused backend behavior.
- `tests/test_run_api.py`, `tests/unit/test_cloud_runtime.py`: transport and diagnostic integration.
- `frontend/src/api/runClient.test.ts`, `frontend/src/hooks/usePersistentRun.test.tsx`, `frontend/src/components/chat/ChatWorkspace.test.tsx`: contract and UI behavior.
- `tests/e2e/test_chat_apply_flow.py`: temporary-project API-to-apply scenario.

---

### Task 1: Durable Run Models and Store

**Files:**
- Create: `src/engineering_team/runs/__init__.py`
- Create: `src/engineering_team/runs/models.py`
- Create: `src/engineering_team/runs/store.py`
- Create: `tests/unit/test_run_store.py`

**Interfaces:**
- Produces: `RunPhase`, `RunSnapshot`, `RunSummary`, `ApplyResult`, `StoredEvent`.
- Produces: `RunStore(root: str | Path)`, `create(snapshot)`, `load(run_id)`, `list_summaries()`, `transition(run_id, phase)`, `append_event(run_id, event)`, `finish(run_id, report, phase)`, and `wait_after(run_id, sequence, timeout)`.
- Persistence location: `<workspace_root>/_records/<run-id>.json`; writes use a sibling temporary file followed by `Path.replace`.

- [ ] **Step 1: Write a failing restart-persistence and event-order test**

```python
def test_store_reloads_snapshot_and_replays_only_events_after_cursor(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.QUEUED, source_hashes={"app.py": "abc"},
    ))
    first = store.append_event("run-a", {"name": "Product", "agent": "product"})
    second = store.append_event("run-a", {"name": "Developer", "agent": "developer"})

    restarted = RunStore(tmp_path)

    assert first.sequence == 1
    assert second.sequence == 2
    assert [item.sequence for item in restarted.events_after("run-a", 1)] == [2]
    assert restarted.load("run-a").message == "change one thing"
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_run_store.py -q`

Expected: collection fails because `engineering_team.runs` does not exist.

- [ ] **Step 3: Implement strict models and atomic persistence**

```python
class RunPhase(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    FAILED = "failed"
    APPLYING = "applying"
    APPLIED = "applied"
    APPLY_FAILED = "apply_failed"

class StoredEvent(BaseModel):
    sequence: int = Field(ge=1)
    payload: dict[str, Any]

class ApplyResult(BaseModel):
    status: Literal["applied", "apply_failed", "restored", "conflict"]
    written_paths: list[str] = Field(default_factory=list)
    test_exit_code: int | None = None
    test_output: str = ""
    backup_path: str | None = None
    message: str

class RunSnapshot(BaseModel):
    run_id: str
    project_path: str
    workspace_path: str
    message: str
    phase: RunPhase
    source_hashes: dict[str, str | None]
    events: list[StoredEvent] = Field(default_factory=list)
    report: dict[str, Any] | None = None
    changed_paths: list[str] = Field(default_factory=list)
    apply_result: ApplyResult | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Use one `threading.RLock` and one `threading.Condition` per store. `append_event` assigns `last sequence + 1` while holding the lock; callers never supply sequence numbers.

- [ ] **Step 4: Add transition validation tests and minimal transition rules**

```python
def test_store_rejects_applying_before_approval(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.RUNNING, source_hashes={},
    ))
    with pytest.raises(ValueError, match="running -> applying"):
        store.transition("run-a", RunPhase.APPLYING)
```

Implement explicit allowed transitions rather than ordinal comparisons. Terminal run completion allows `running -> approved|review_required|failed`; application allows `approved -> applying -> applied|apply_failed`; a successful explicit restore allows `apply_failed -> approved` while retaining an `ApplyResult(status="restored", ...)` audit record.

- [ ] **Step 5: Run focused and existing API tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_run_store.py tests\test_run_api.py -q`

Expected: new store tests pass; existing API tests remain green before integration.

- [ ] **Step 6: Commit**

```powershell
git add src/engineering_team/runs tests/unit/test_run_store.py
git commit -m "feat: persist durable run snapshots"
```

---

### Task 2: Native Windows Project Picker

**Files:**
- Create: `src/engineering_team/project_picker.py`
- Create: `src/engineering_team/project_api.py`
- Create: `tests/unit/test_project_picker.py`
- Modify: `sample_app/app/main.py`

**Interfaces:**
- Produces: `FolderPicker.pick() -> Path | None` and `WindowsFolderPicker`.
- Produces: `create_project_router(picker: FolderPicker | None = None) -> APIRouter`.
- Endpoint: `POST /api/projects/pick -> {status: "selected", project: {path, name}} | {status: "cancelled", project: null}`.

- [ ] **Step 1: Write failing endpoint tests for selection, cancellation, and non-loopback rejection**

```python
class StaticPicker:
    def __init__(self, selected: Path | None) -> None:
        self.selected = selected
    def pick(self) -> Path | None:
        return self.selected

def test_picker_returns_canonical_selected_directory(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(tmp_path / ".")))
    response = TestClient(app).post("/api/projects/pick")
    assert response.json() == {
        "status": "selected",
        "project": {"path": str(tmp_path.resolve()), "name": tmp_path.name},
    }

def test_picker_cancel_is_not_an_error() -> None:
    app = FastAPI()
    app.include_router(create_project_router(StaticPicker(None)))
    response = TestClient(app).post("/api/projects/pick")
    assert response.status_code == 200
    assert response.json() == {"status": "cancelled", "project": None}
```

Use a request scope with a non-loopback client tuple and assert status `403` with stable code `LOCAL_ONLY`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_project_picker.py -q`

Expected: import failure for `project_picker` and `project_api`.

- [ ] **Step 3: Implement the serialized Windows adapter**

```python
class FolderPicker(Protocol):
    def pick(self) -> Path | None: ...

class WindowsFolderPicker:
    _lock = threading.Lock()

    def pick(self) -> Path | None:
        if sys.platform != "win32":
            raise RuntimeError("native folder selection requires Windows")
        with self._lock:
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                selected = filedialog.askdirectory(parent=root, mustexist=True)
            finally:
                root.destroy()
        return Path(selected).resolve() if selected else None
```

Keep Tk imports inside `pick` so headless test collection does not initialize a display.

- [ ] **Step 4: Implement loopback-only project route and compose it into FastAPI**

```python
def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    return ipaddress.ip_address(host).is_loopback

@router.post("/api/projects/pick")
def pick_project(request: Request) -> ProjectPickResponse:
    if not _is_loopback(request.client.host if request.client else None):
        raise HTTPException(403, detail={"code": "LOCAL_ONLY", "message": "Folder selection is local-only"})
    selected = chosen_picker.pick()
    if selected is None:
        return ProjectPickResponse(status="cancelled", project=None)
    if not selected.is_dir():
        raise HTTPException(422, detail={"code": "INVALID_PROJECT", "message": "Selected path is not a directory"})
    return ProjectPickResponse(status="selected", project=ProjectRef(path=str(selected), name=selected.name))
```

Modify `sample_app/app/main.py` to include both `project_router` and `runs_router`.

- [ ] **Step 5: Run tests and a Windows picker smoke test**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_project_picker.py -q`

Manual smoke: start the API on `127.0.0.1`, call `POST /api/projects/pick` from the frontend, select a directory, and verify the canonical path is returned. Cancel once and verify the current project remains unchanged.

- [ ] **Step 6: Commit**

```powershell
git add src/engineering_team/project_picker.py src/engineering_team/project_api.py sample_app/app/main.py tests/unit/test_project_picker.py
git commit -m "feat: select local projects with native picker"
```

---

### Task 3: Persistent Isolated Run Lifecycle and Replayable Transport

**Files:**
- Modify: `src/engineering_team/run_api.py`
- Modify: `src/engineering_team/run_events.py`
- Modify: `tests/test_run_api.py`

**Interfaces:**
- Consumes: `RunStore`, `RunSnapshot`, `RunPhase` from Task 1.
- Produces: `RunExecutor = Callable[[RunSnapshot, Callable[[dict[str, Any]], None]], dict[str, Any]]`; deterministic tests replace only this slow LLM/workflow boundary.
- Endpoint: `POST /api/runs` body `{projectPath: string, message: string}`.
- Endpoint: `GET /api/runs`, `GET /api/runs/{run_id}`, `GET /api/runs/{run_id}/events?after=<sequence>`.
- WebSocket: `/ws/runs/{run_id}?after=<sequence>` replays stored events, then waits for new events.
- Execution: always calls `execute_on_project(..., project_path=isolated, authorize_writes=True)` so writes occur only in the run copy.

- [ ] **Step 1: Replace launch-contract tests with one-message/one-run and snapshot tests**

```python
def test_post_creates_independent_persisted_runs(tmp_path: Path) -> None:
    def executor(snapshot: RunSnapshot, emit: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        emit({"name": snapshot.message, "agent": "product", "type": "model",
              "level": "info", "status_message": "completed", "metadata": {},
              "iteration": 0, "at": 1})
        return _completed_state(snapshot.run_id)

    manager = RunManager(store=RunStore(tmp_path / "records"), executor=executor)
    app = FastAPI()
    app.include_router(create_runs_router(manager))
    client = TestClient(app)
    first = client.post("/api/runs", json={"projectPath": str(tmp_path), "message": "alpha"})
    second = client.post("/api/runs", json={"projectPath": str(tmp_path), "message": "beta"})
    assert first.status_code == second.status_code == 202
    assert first.json()["run_id"] != second.json()["run_id"]
    assert client.get(f"/api/runs/{first.json()['run_id']}").json()["message"] == "alpha"
    assert client.get(f"/api/runs/{second.json()['run_id']}").json()["message"] == "beta"
```

Add a restart test that creates a second `RunManager` with the same store root and reads the completed snapshot without opening a WebSocket.

Change the existing fixture signature to `def _completed_state(run_id: str = "run-1") -> dict[str, Any]` and set its first field to `"run_id": run_id`; keep all implementation, review, model-usage, evidence, tool-result, and error fields so the executor fake mirrors a real terminal state.

- [ ] **Step 2: Run the exact tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_run_api.py -q`

Expected: the new request shape and GET routes are unsupported.

- [ ] **Step 3: Refactor RunManager around durable snapshots**

```python
class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    project_path: str = Field(alias="projectPath", min_length=1)
    message: str = Field(min_length=1)

def start(self, request: LaunchRequest) -> str:
    run_id = f"run-{uuid.uuid4()}"
    source = Path(request.project_path).expanduser().resolve()
    workspace = create_run_copy(run_id, source, self.settings.workspace_root)
    snapshot = RunSnapshot(
        run_id=run_id, project_path=str(source), workspace_path=str(workspace),
        message=request.message.strip(), phase=RunPhase.QUEUED,
        source_hashes=snapshot_project(source),
    )
    self.store.create(snapshot)
    threading.Thread(target=self._worker, args=(run_id,), daemon=True).start()
    return run_id
```

The worker transitions `queued -> preparing -> running`, emits all events through `store.append_event`, executes with `authorize_writes=True` against `workspace_path`, and finishes with `approved`, `review_required`, or `failed` based on the persisted final report.

- [ ] **Step 4: Add cursor replay and disconnect tests**

```python
def test_websocket_reconnect_replays_only_missing_events(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "records")
    snapshot = RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="work",
        phase=RunPhase.APPROVED, source_hashes={}, report={"review": {"status": "APPROVED"}},
    )
    store.create(snapshot)
    for name in ("one", "two", "three"):
        store.append_event("run-a", {"name": name, "agent": "product", "type": "model",
                                     "level": "info", "status_message": name,
                                     "metadata": {}, "iteration": 0, "at": 1})
    manager = RunManager(store=store, executor=lambda *_: _completed_state("run-a"))
    app = FastAPI()
    app.include_router(create_runs_router(manager))
    client = TestClient(app)
    run_id = "run-a"
    with client.websocket_connect(f"/ws/runs/{run_id}?after=1") as websocket:
        assert websocket.receive_json()["sequence"] == 2
        assert websocket.receive_json()["sequence"] == 3
        assert websocket.receive_json()["kind"] == "snapshot"
    assert client.get(f"/api/runs/{run_id}").status_code == 200
```

The terminal WebSocket envelope contains the persisted snapshot and never deletes the run.

- [ ] **Step 5: Preserve real final-report distinctions**

Extend `final_report_from_state` with `workspace_changed`, `source_applied=False`, and actual test/tool evidence. A model proposal with no workspace writes must return `workspace_changed=False` even if `changed_files` contains proposed paths.

- [ ] **Step 6: Run backend transport regression tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_run_api.py tests\integration\test_observability.py -q`

Expected: all tests pass and completed runs remain queryable after WebSocket completion.

- [ ] **Step 7: Commit**

```powershell
git add src/engineering_team/run_api.py src/engineering_team/run_events.py tests/test_run_api.py
git commit -m "feat: persist and replay isolated agent runs"
```

---

### Task 4: Conflict-Safe Apply, Verification, and Restore

**Files:**
- Create: `src/engineering_team/apply_service.py`
- Create: `tests/unit/test_apply_service.py`
- Modify: `src/engineering_team/run_api.py`
- Modify: `src/engineering_team/runs/models.py`

**Interfaces:**
- Consumes: approved `RunSnapshot` and `RunStore`.
- Produces: `snapshot_project(root) -> dict[str, str | None]` and `ApplyService.apply(run_id) -> ApplyResult`, `restore(run_id) -> ApplyResult`.
- `create_runs_router` gains an explicit `apply_service: ApplyService` dependency used only by apply/restore endpoints.
- Endpoint: `POST /api/runs/{run_id}/apply` body `{projectPath: string, confirmed: true}`.
- Endpoint: `POST /api/runs/{run_id}/restore` body `{confirmed: true}`.

- [ ] **Step 1: Write failing real-filesystem tests for apply and conflict behavior**

```python
def test_apply_writes_workspace_content_and_keeps_backup(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, ["app.py"])
    service = ApplyService(store, verification=PassingVerification())
    result = service.apply("run-a", confirmed_project=source)
    assert (source / "app.py").read_text(encoding="utf-8") == "new\n"
    assert (Path(result.backup_path) / "app.py").read_text(encoding="utf-8") == "old\n"
    assert result.status == "applied"

def test_apply_blocks_when_source_changed_after_run_started(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("agent\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, ["app.py"])
    service = ApplyService(store, verification=PassingVerification())
    (source / "app.py").write_text("human\n", encoding="utf-8")
    result = service.apply("run-a", confirmed_project=source)
    assert result.status == "conflict"
    assert (source / "app.py").read_text(encoding="utf-8") == "human\n"
```

These tests exercise real temporary files; fake only the external test-command runner.

Define the test utilities in `tests/unit/test_apply_service.py`:

```python
class PassingVerification:
    def run(self, project: Path) -> tuple[int, str]:
        return 0, "24 passed"

def approved_store(root: Path, source: Path, workspace: Path, paths: list[str]) -> RunStore:
    store = RunStore(root)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(source.resolve()),
        workspace_path=str(workspace.resolve()), message="work",
        phase=RunPhase.APPROVED, source_hashes=snapshot_project(source),
        changed_paths=paths, report={"review": {"status": "APPROVED"}},
    ))
    return store
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_apply_service.py -q`

Expected: import failure for `ApplyService`.

- [ ] **Step 3: Implement canonical path and manifest helpers**

```python
def file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def safe_target(root: Path, relative: str) -> Path:
    requested = Path(relative)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValueError("unsafe project-relative path")
    target = (root / requested).resolve()
    if target != root and root not in target.parents:
        raise ValueError("path resolves outside project")
    if target.is_symlink():
        raise ValueError("symbolic-link targets are not writable")
    return target
```

`snapshot_project` skips `.git`, `.venv`, `__pycache__`, `workspace/runs`, and `rag/chroma`, and records hashes using POSIX relative paths.

- [ ] **Step 4: Implement backup, atomic replacement, rollback, and restore**

Stage each workspace file beside its source target with a unique `.nova-<run-id>.tmp` name, flush it, then replace the target. Store `_backup/manifest.json` with each relative path and whether it originally existed. On a write exception, restore all paths already replaced and return `apply_failed`.

Restoration rejects a source file whose post-apply hash no longer matches the recorded applied hash; this prevents erasing edits made after application.

- [ ] **Step 5: Add post-apply verification behavior**

```python
class VerificationRunner(Protocol):
    def run(self, project: Path) -> tuple[int, str]: ...

class PytestVerificationRunner:
    def __init__(self, paths: list[str] | None = None) -> None:
        self.paths = paths or []

    def run(self, project: Path) -> tuple[int, str]:
        process = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *self.paths], cwd=project,
            capture_output=True, text=True, timeout=120, check=False,
        )
        return process.returncode, (process.stdout + process.stderr)[-8000:]
```

If verification returns nonzero, preserve the written files, record `apply_failed`, and expose restore. If writing itself fails, roll back automatically.

- [ ] **Step 6: Add API tests for authorization, idempotency, and confirmation path**

Assert that unapproved runs return `409`, mismatched `projectPath` returns `409`, `confirmed=false` returns `422`, and repeating a successful apply returns the same stored result without changing file timestamps.

- [ ] **Step 7: Run focused and security tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_apply_service.py tests\test_run_api.py tests\unit\test_guardrails.py tests\mcp\test_repository.py -q`

- [ ] **Step 8: Commit**

```powershell
git add src/engineering_team/apply_service.py src/engineering_team/run_api.py src/engineering_team/runs/models.py tests/unit/test_apply_service.py tests/test_run_api.py
git commit -m "feat: safely apply approved workspace changes"
```

---

### Task 5: Actionable Sanitized Provider Diagnostics

**Files:**
- Modify: `src/engineering_team/llm/cloud.py`
- Modify: `src/engineering_team/contracts/models.py`
- Modify: `src/engineering_team/run_events.py`
- Create: `tests/unit/test_cloud_runtime.py`
- Modify: `tests/test_run_api.py`

**Interfaces:**
- Extends `ModelExecutionInfo` with `http_status: int | None`, `error_category: str | None`, and `retryable: bool | None`.
- Public events expose these sanitized fields; raw response bodies and credentials remain absent.

- [ ] **Step 1: Write a failing 401 classification test**

```python
def test_cloud_http_401_is_sanitized_and_classified() -> None:
    settings = Settings(
        cloud_enabled=True, local_first=False, gemini_api_key="fixture-key",
    )
    transport = httpx.MockTransport(lambda _: httpx.Response(
        401, json={"error": {"message": "api key sk-secret is invalid"}}
    ))
    runtime = CloudModelRuntime(settings, client=httpx.Client(transport=transport), primary=True)
    with pytest.raises(RuntimeError, match="authentication"):
        runtime.invoke_artifact(AgentRole.PRODUCT, cloud_envelope(), product_candidate())
    attempt = runtime.attempts[-1]
    assert attempt.http_status == 401
    assert attempt.error_category == "authentication"
    assert attempt.retryable is False
    assert "sk-secret" not in attempt.error
```

Add literal cases for `404 -> model_unavailable`, `429 -> rate_limit`, and `503 -> provider_unavailable` with retryability `False`, `True`, and `True` respectively.

Define complete governed inputs in the same test module:

```python
def cloud_envelope() -> ContextEnvelope:
    return ContextEnvelope(
        agent=AgentRole.PRODUCT, current_task="classify requirement",
        state_projection={"requirement": "Add a health endpoint"},
        rag_evidence=[], tool_results=[], remediation_feedback=None,
        output_schema="", allowed_tools=[], model_profile="CLOUD_FALLBACK",
        projection_fingerprint="fixture-fingerprint",
    )

def product_candidate() -> ProductSpecification:
    return ProductSpecification(
        objective="Add a health endpoint", actors=["operator"],
        business_rules=["Return healthy status"], constraints=["Keep compatibility"],
        acceptance_criteria=["GET health returns 200"], nfrs=["Deterministic"],
        ambiguities=[], assumptions=[], source_requirement="Add a health endpoint",
    )
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_cloud_runtime.py -q`

Expected: `ModelExecutionInfo` lacks diagnostic fields.

- [ ] **Step 3: Implement status classification at the caught HTTP boundary**

```python
def _http_category(status: int) -> tuple[str, bool]:
    if status in {401, 403}:
        return "authentication", False
    if status == 404:
        return "model_unavailable", False
    if status == 429:
        return "rate_limit", True
    if status >= 500:
        return "provider_unavailable", True
    return "request_rejected", False
```

Catch `httpx.HTTPStatusError` before the broader `httpx.HTTPError`, extract only `response.status_code`, classify it, and record `CLOUD_FALLBACK_UNAVAILABLE: <category> (HTTP <status>)`. Never include `response.text`.

- [ ] **Step 4: Verify warning versus fatal projection**

Add a run-event test where a failed cloud attempt followed by a successful local attempt remains an error-level attempt event but the run phase finishes `approved`. The UI-facing metadata must contain `fallback_succeeded=true` after the local completion.

- [ ] **Step 5: Run cloud, observability, and API tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_cloud_runtime.py tests\integration\test_observability.py tests\test_run_api.py -q`

- [ ] **Step 6: Commit**

```powershell
git add src/engineering_team/llm/cloud.py src/engineering_team/contracts/models.py src/engineering_team/run_events.py tests/unit/test_cloud_runtime.py tests/test_run_api.py
git commit -m "fix: expose sanitized provider failure causes"
```

---

### Task 6: TypeScript Contract and Persistent Run Client

**Files:**
- Modify: `frontend/src/types/mission.ts`
- Modify: `frontend/src/api/runClient.ts`
- Modify: `frontend/src/api/runClient.test.ts`
- Create: `frontend/src/hooks/usePersistentRun.ts`
- Create: `frontend/src/hooks/usePersistentRun.test.tsx`
- Create: `frontend/src/test/FakeRunClient.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/test/setup.ts`

**Interfaces:**
- Mirrors `RunPhase`, `RunSnapshot`, `StoredEvent`, `ProjectPickResponse`, and `ApplyResult` exactly.
- Produces `RunClient` with `pickProject`, `createRun`, `listRuns`, `getRun`, `eventsAfter`, `subscribe`, `apply`, and `restore`.
- Produces `usePersistentRun(runId, client)`, which loads a snapshot before subscribing and deduplicates by sequence.

- [ ] **Step 1: Install frontend test dependencies**

Run from `frontend`: `npm.cmd install --save-dev @testing-library/react@^16 @testing-library/jest-dom@^6 @testing-library/user-event@^14 jsdom@^25`

Update Vite test configuration with `environment: 'jsdom'` and a `frontend/src/test/setup.ts` import of `@testing-library/jest-dom/vitest`.

- [ ] **Step 2: Write failing contract tests for all public envelopes**

```typescript
it('rejects an approved snapshot without a persisted report', () => {
  expect(isRunSnapshot({
    run_id: 'run-a', project_path: 'C:\\work', workspace_path: 'C:\\runs\\run-a',
    message: 'change it', phase: 'approved', source_hashes: {}, events: [],
    report: null, changed_paths: [], apply_result: null,
    created_at: '2026-08-27T10:00:00-06:00', updated_at: '2026-08-27T10:01:00-06:00'
  })).toBe(false);
});
```

Add valid literal fixtures for selected/cancelled picker responses, every phase, cursor events, apply conflict, apply success, and recoverable API error.

- [ ] **Step 3: Run the contract test and verify RED**

Run from `frontend`: `npm.cmd test -- src/api/runClient.test.ts`

Expected: missing validators and client methods.

- [ ] **Step 4: Implement strict TypeScript guards and HTTP methods**

```typescript
export interface RunClient {
  pickProject(signal?: AbortSignal): Promise<ProjectPickResponse>;
  createRun(projectPath: string, message: string, signal?: AbortSignal): Promise<string>;
  listRuns(signal?: AbortSignal): Promise<RunSummary[]>;
  getRun(runId: string, signal?: AbortSignal): Promise<RunSnapshot>;
  eventsAfter(runId: string, after: number, signal?: AbortSignal): Promise<StoredEvent[]>;
  subscribe(
    runId: string, after: number,
    onEnvelope: (value: StoredEvent | RunSnapshot) => void,
    onClose: () => void,
  ): () => void;
  apply(runId: string, projectPath: string): Promise<ApplyResult>;
  restore(runId: string): Promise<ApplyResult>;
}
```

All response methods validate before returning. Convert FastAPI error envelopes to `RunApiError(code, message, recoverable, details)`.

Implement the shared test client with complete interface methods:

```typescript
export class FakeRunClient implements RunClient {
  requests: Array<{ projectPath: string; message: string }> = [];
  private listener?: (value: StoredEvent | RunSnapshot) => void;
  constructor(public snapshot: RunSnapshot = approvedFixture()) {}
  async pickProject(): Promise<ProjectPickResponse> {
    return { status: 'selected', project: { path: 'C:\\projects\\calculator', name: 'calculator' } };
  }
  async createRun(projectPath: string, message: string): Promise<string> {
    this.requests.push({ projectPath, message });
    return `run-${this.requests.length}`;
  }
  async listRuns(): Promise<RunSummary[]> { return []; }
  async getRun(): Promise<RunSnapshot> { return this.snapshot; }
  async eventsAfter(_runId: string, after: number): Promise<StoredEvent[]> {
    return this.snapshot.events.filter(event => event.sequence > after);
  }
  subscribe(
    _runId: string, _after: number,
    onEnvelope: (value: StoredEvent | RunSnapshot) => void,
  ): () => void {
    this.listener = onEnvelope;
    return () => { this.listener = undefined; };
  }
  async apply(): Promise<ApplyResult> {
    return { status: 'applied', written_paths: ['app.py'], test_exit_code: 0,
             test_output: '1 passed', backup_path: 'backup', message: 'Applied' };
  }
  async restore(): Promise<ApplyResult> {
    return { status: 'restored', written_paths: ['app.py'], test_exit_code: null,
             test_output: '', backup_path: 'backup', message: 'Restored' };
  }
  emit(value: StoredEvent | RunSnapshot): void { this.listener?.(value); }
}
```

Define the literal fixture builders beside the fake:

```typescript
export const storedEvent = (sequence: number, name: string): StoredEvent => ({
  sequence,
  payload: { id: `run-a-${sequence}`, name, type: 'model', level: 'info',
    status_message: `${name} complete`, metadata: {}, agent: 'product',
    iteration: 0, at: sequence },
});

export const approvedFixture = (events: StoredEvent[] = []): RunSnapshot => ({
  run_id: 'run-a', project_path: 'C:\\projects\\calculator',
  workspace_path: 'C:\\runs\\run-a', message: 'change it', phase: 'approved',
  source_hashes: {}, events,
  report: {
    route_history: [], model_usage: [], changed_files: [{
      path: 'app.py', language: 'python', additions: 1, deletions: 1,
      lines: [{ type: 'del', text: 'old', oldNo: 1 },
              { type: 'add', text: 'new', newNo: 1 }],
    }],
    applied_diff: true, workspace_changed: true, source_applied: false,
    review: { status: 'APPROVED', score: 100,
      subscores: { requirements: 100, architecture: 100, security: 100,
        testing: 100, implementation: 100, rag_grounding: 100 },
      problems: [], reason: 'approved' },
    errors: [], rag_evidence: [], tool_results: [],
  },
  changed_paths: ['app.py'], apply_result: null,
  created_at: '2026-08-27T10:00:00-06:00',
  updated_at: '2026-08-27T10:01:00-06:00',
});
```

- [ ] **Step 5: Write the failing reconnect/deduplication hook test**

```typescript
it('loads a snapshot and ignores replayed event sequences', async () => {
  const client = new FakeRunClient(approvedFixture([storedEvent(1, 'Product'), storedEvent(2, 'Developer')]));
  const { result } = renderHook(() => usePersistentRun('run-a', client));
  await waitFor(() => expect(result.current.events.map(e => e.sequence)).toEqual([1, 2]));
  act(() => client.emit(storedEvent(2, 'duplicate')));
  act(() => client.emit(storedEvent(3, 'Testing')));
  expect(result.current.events.map(e => e.sequence)).toEqual([1, 2, 3]);
});
```

The fake implements the complete `RunClient`; it does not replace React or the hook under test.

- [ ] **Step 6: Implement snapshot-first subscription with bounded reconnect**

Load `getRun`, set the cursor to the maximum persisted sequence, connect, and merge only events whose sequence is greater than the current cursor. On close before a terminal phase, reload the snapshot and reconnect after `250ms`, `500ms`, `1000ms`, then cap at `2000ms`. Abort timers and sockets on unmount.

- [ ] **Step 7: Run frontend contract and hook tests**

Run from `frontend`: `npm.cmd test -- src/api/runClient.test.ts src/hooks/usePersistentRun.test.tsx`

- [ ] **Step 8: Commit**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/test/setup.ts frontend/src/test/FakeRunClient.ts frontend/src/types/mission.ts frontend/src/api/runClient.ts frontend/src/api/runClient.test.ts frontend/src/hooks/usePersistentRun.ts frontend/src/hooks/usePersistentRun.test.tsx
git commit -m "feat: add persistent run frontend contract"
```

---

### Task 7: Chat Shell and Progressive Run Cards

**Files:**
- Create: `frontend/src/components/chat/ProjectHeader.tsx`
- Create: `frontend/src/components/chat/ChatComposer.tsx`
- Create: `frontend/src/components/chat/RunCard.tsx`
- Create: `frontend/src/components/chat/ChatWorkspace.tsx`
- Create: `frontend/src/components/chat/ChatWorkspace.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/mission/AgentGraph.tsx`
- Modify: `frontend/src/components/mission/ActionTicker.tsx`
- Modify: `frontend/src/components/debrief/MissionDebrief.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Consumes: `RunClient` and `usePersistentRun` from Task 6.
- `ChatWorkspace` owns the selected project and ordered session run identifiers.
- `RunCard` embeds existing graph, activity, scorecard, diff, evidence, apply, and restore controls.

- [ ] **Step 1: Write a failing one-message/one-run component test**

```typescript
it('creates independent runs with only the current message', async () => {
  const client = new FakeRunClient();
  render(<ChatWorkspace client={client} />);
  await userEvent.click(screen.getByRole('button', { name: /select folder/i }));
  await userEvent.type(screen.getByRole('textbox', { name: /task/i }), 'first change');
  await userEvent.click(screen.getByRole('button', { name: /execute/i }));
  await userEvent.type(screen.getByRole('textbox', { name: /task/i }), 'second change');
  await userEvent.click(screen.getByRole('button', { name: /execute/i }));
  expect(client.requests).toEqual([
    { projectPath: 'C:\\projects\\calculator', message: 'first change' },
    { projectPath: 'C:\\projects\\calculator', message: 'second change' },
  ]);
  expect(screen.getAllByRole('article')).toHaveLength(2);
});
```

This test catches accidental conversation concatenation and duplicate POSTs. The fake returns complete snapshots consumed by real `RunCard` components.

- [ ] **Step 2: Run the component test and verify RED**

Run from `frontend`: `npm.cmd test -- src/components/chat/ChatWorkspace.test.tsx`

Expected: chat components do not exist.

- [ ] **Step 3: Implement project header and composer**

`ProjectHeader` shows the canonical path, backend health, and native picker button. Picker cancellation leaves state unchanged. `ChatComposer` trims input, disables submit without a selected project or during the POST, clears only after a successful `createRun`, and restores the message if creation fails.

- [ ] **Step 4: Implement progressive RunCard from persisted phase**

```typescript
const PHASE_LABEL: Record<RunPhase, string> = {
  queued: 'Queued', preparing: 'Preparing workspace', running: 'Agents working',
  review_required: 'Review required', approved: 'Approved', failed: 'Failed',
  applying: 'Applying changes', applied: 'Applied', apply_failed: 'Apply failed',
};
```

Render graph and ticker for `preparing|running`; render debrief and diff when `report` exists; enable Apply only for `approved` with `report.workspace_changed === true`; show Restore only when `apply_result.status === 'apply_failed'` and a backup path exists. All labels derive from the snapshot.

- [ ] **Step 5: Add apply confirmation and error-state tests**

Test that confirmation names the exact canonical project and affected paths, conflicts leave the card approved with a visible conflict message, and a successful result changes the card label to Applied. Test that a cloud fallback warning does not render the run as Failed.

- [ ] **Step 6: Replace the App screen state machine and embed existing visual components**

```tsx
export function App({ client = runClient }: { client?: RunClient }) {
  return (
    <main className="circuit-grid min-h-screen w-full">
      <ChatWorkspace client={client} />
    </main>
  );
}
```

Remove launch/mission/debrief navigation from `App.tsx`. Keep their reusable graph, evidence, score, timeline, and diff internals; change their outer containers to embedded sections.

- [ ] **Step 7: Make the layout responsive and fully scrollable**

Replace `h-screen`, fixed `h-[560px]`, and page-level `overflow-hidden` in active paths with `min-h-*`, content-driven sizing, `overflow-x-auto` only for the wide graph, and responsive grid rules. Keep the composer sticky with safe bottom padding so it never covers the final run card.

- [ ] **Step 8: Run UI tests, typecheck, and build**

Run from `frontend`:

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

Expected: all commands exit `0`; Vite produces `frontend/dist` without TypeScript errors.

- [ ] **Step 9: Commit**

```powershell
git add frontend/src/App.tsx frontend/src/index.css frontend/src/components/chat frontend/src/components/mission/AgentGraph.tsx frontend/src/components/mission/ActionTicker.tsx frontend/src/components/debrief/MissionDebrief.tsx
git commit -m "feat: replace launch form with multiagent chat"
```

---

### Task 8: End-to-End Temporary Project Flow and Operator Documentation

**Files:**
- Create: `tests/e2e/test_chat_apply_flow.py`
- Modify: `README.md`
- Modify: `frontend/README.md`
- Modify: `demo-projects/calculadora-qa-demo/README.md`

**Interfaces:**
- Consumes all backend API and apply interfaces from Tasks 1–5.
- Uses a deterministic executor only at the external LLM boundary; workspace copy, event persistence, report projection, apply, backup, and verification remain real.
- Test helpers are local to `tests/e2e/test_chat_apply_flow.py`: `copy_calculator_demo`, `calculator_change_executor`, `chat_app_client`, and `wait_for_phase` use the production `RunStore`, `RunManager`, routers, and `ApplyService`.

- [ ] **Step 1: Write a failing API-to-source end-to-end test**

```python
def test_message_runs_in_copy_then_applies_to_source(tmp_path: Path) -> None:
    source = copy_calculator_demo(tmp_path / "calculator")
    client = chat_app_client(tmp_path / "runs", executor=calculator_change_executor)
    created = client.post("/api/runs", json={
        "projectPath": str(source),
        "message": "Add a public VERSION constant with value 2",
    })
    run_id = created.json()["run_id"]
    wait_for_phase(client, run_id, "approved")
    assert "VERSION = 2" not in (source / "calculadora" / "__init__.py").read_text()
    applied = client.post(f"/api/runs/{run_id}/apply", json={
        "projectPath": str(source.resolve()), "confirmed": True,
    })
    assert applied.json()["status"] == "applied"
    assert "VERSION = 2" in (source / "calculadora" / "__init__.py").read_text()
    assert applied.json()["test_exit_code"] == 0
```

The deterministic executor writes only inside the provided workspace and returns the same full state shape as `execute_on_project`.

Define the helpers explicitly:

```python
def copy_calculator_demo(destination: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "demo-projects" / "calculadora-qa-demo"
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return destination

def calculator_change_executor(
    snapshot: RunSnapshot, emit: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    target = Path(snapshot.workspace_path) / "calculadora" / "__init__.py"
    original = target.read_text(encoding="utf-8")
    target.write_text(original + "\nVERSION = 2\n", encoding="utf-8")
    emit({"name": "Developer write", "agent": "developer", "type": "tool",
          "level": "info", "status_message": "calculadora/__init__.py updated",
          "metadata": {"status": "SUCCESS"}, "iteration": 0, "at": 1})
    return approved_state_with_applied_diff(
        snapshot.run_id, "calculadora/__init__.py", original, original + "\nVERSION = 2\n"
    )

def approved_state_with_applied_diff(
    run_id: str, path: str, before: str, after: str,
) -> dict[str, Any]:
    diff = "\n".join(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="",
    ))
    return {
        "run_id": run_id, "iteration": 0, "final_status": "APPROVED",
        "route_history": ["Product", "Architecture", "Developer", "Security",
                          "Testing", "Reviewer", "FinalReport"],
        "implementation": {
            "action_mode": "APPLIED", "changed_files": [path], "diff": diff,
            "evidence": [path], "validation_result": "workspace tests passed",
            "security_surface_changed": False, "file_contents": {path: after},
        },
        "review": {
            "status": "APPROVED", "score": 100,
            "subscores": {"requirements": 100, "architecture": 100, "security": 100,
                          "testing": 100, "implementation": 100, "rag_grounding": 100},
            "problems": [], "reason": "validated evidence satisfies acceptance checks",
            "remediation_category": None, "return_to": None, "confidence": 1,
            "evidence_references": [path],
        },
        "model_usage": [], "rag_evidence": [],
        "tool_results": [{
            "tool_name": "run_tests", "status": "SUCCESS", "duration_ms": 1,
            "allowed_role": "Testing", "input_summary": "safe",
            "output_summary": "21 passed", "error": None,
        }],
        "errors": [],
    }

def chat_app_client(records: Path, executor: RunExecutor) -> TestClient:
    settings = Settings(workspace_root=str(records / "workspaces"))
    store = RunStore(records)
    manager = RunManager(settings=settings, store=store, executor=executor)
    apply_service = ApplyService(
        store, verification=PytestVerificationRunner(paths=["tests/test_operaciones.py"]),
    )
    app = FastAPI()
    app.include_router(create_runs_router(manager, apply_service=apply_service))
    return TestClient(app)

def wait_for_phase(client: TestClient, run_id: str, phase: str) -> dict[str, Any]:
    for _ in range(200):
        payload = client.get(f"/api/runs/{run_id}").json()
        if payload["phase"] == phase:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach {phase}")
```

The executor fake replaces only model orchestration; file copying, event persistence, diff projection, application, backup, and the post-apply pytest subprocess are production implementations.

- [ ] **Step 2: Run the E2E test and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\e2e\test_chat_apply_flow.py -q`

Expected: the composed persistent/apply API is incomplete until all preceding tasks are integrated.

- [ ] **Step 3: Add only the composition glue required to make the E2E test pass**

Wire `RunStore(Settings().workspace_root)`, `RunManager`, `ApplyService`, project router, and run router in `sample_app/app/main.py`. Do not add a second execution path for the test.

- [ ] **Step 4: Document setup and the calculator dependency**

Document these exact local commands:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[sample-app,rag,observability,dev]"
.\.venv\Scripts\python.exe -m pip install -e .\demo-projects\calculadora-qa-demo
.\.venv\Scripts\python.exe -m uvicorn sample_app.app.main:app --host 127.0.0.1 --port 8000
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Explain that traces confirm execution, workspace changes confirm implementation, and `applied` plus post-apply tests confirm source modification.

- [ ] **Step 5: Run all automated verification**

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
Set-Location frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

- [ ] **Step 6: Run the live calculator smoke scenario**

Start the backend and frontend, select a temporary copy of `demo-projects/calculadora-qa-demo`, submit one bounded change, confirm the graph reflects real backend events, inspect the actual workspace diff, apply it, and verify the card reports the original-project test exit code. Confirm the committed calculator demo remains unchanged.

- [ ] **Step 7: Commit**

```powershell
git add tests/e2e/test_chat_apply_flow.py README.md frontend/README.md demo-projects/calculadora-qa-demo/README.md sample_app/app/main.py
git commit -m "test: verify chat run and safe apply end to end"
```

---

## Final Verification

- [ ] Run `git status --short` and confirm only intentional files remain modified.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest -q` and record the passing count.
- [ ] Run `.\.venv\Scripts\python.exe -m ruff check src tests` and record exit code `0`.
- [ ] Run `npm.cmd test`, `npm.cmd run typecheck`, and `npm.cmd run build` from `frontend` and record exit code `0` for each.
- [ ] Confirm a cancelled folder picker leaves the selected project unchanged.
- [ ] Confirm two chat messages create two run IDs and neither request contains the other message.
- [ ] Confirm browser reload reconstructs a completed run from `GET /api/runs/{run_id}`.
- [ ] Confirm a dry proposal is never labeled as written and an isolated write is never labeled as source-applied.
- [ ] Confirm source changes made after run creation block Apply before any write.
- [ ] Confirm an applied temporary calculator change has a backup and real post-apply test result.
- [ ] Confirm provider HTTP failures show sanitized status/category without credentials or raw response bodies.
