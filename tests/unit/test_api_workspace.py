import os

from engineering_team.workspace.isolation import create_api_workspace


def test_copies_project_excluding_git_env_and_caches(tmp_path):
    source = tmp_path / "project"
    (source / ".git").mkdir(parents=True)
    (source / ".git" / "HEAD").write_text("ref: refs/heads/main")
    (source / ".venv").mkdir()
    (source / ".venv" / "pyvenv.cfg").write_text("home = /usr")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    (source / ".env").write_text("SECRET=1")
    (source / "app").mkdir()
    (source / "app" / "main.py").write_text("print('hi')\n")

    fingerprint = create_api_workspace("run-1", source, tmp_path / "runs")

    copied = {p.relative_to(fingerprint.workspace_path).as_posix() for p in fingerprint.workspace_path.rglob("*") if p.is_file()}
    assert copied == {"app/main.py"}
    assert not (fingerprint.workspace_path / ".git").exists()
    assert not (fingerprint.workspace_path / ".env").exists()


def test_rejects_symlinks_that_escape_the_source(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "app").mkdir()
    (source / "app" / "main.py").write_text("print('hi')\n")
    outside = tmp_path / "outside.py"
    outside.write_text("import os\n")
    os.symlink(outside, source / "app" / "linked.py")

    fingerprint = create_api_workspace("run-2", source, tmp_path / "runs")

    assert not (fingerprint.workspace_path / "app" / "linked.py").exists()


def test_records_a_sha256_hash_per_copied_file(tmp_path):
    import hashlib

    source = tmp_path / "project"
    source.mkdir()
    (source / "main.py").write_bytes(b"print(1)\n")
    expected = hashlib.sha256(b"print(1)\n").hexdigest()

    fingerprint = create_api_workspace("run-3", source, tmp_path / "runs")

    assert fingerprint.file_hashes["main.py"] == expected
    assert fingerprint.source_path == source.resolve()
