"""Reviewed-plan preflight and actual sequential execution with inert commands."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from lean_sdd.cli import main
from lean_sdd.configuration import InstallationIdentity
from lean_sdd.installer import initialize
from lean_sdd.profiles import PYTHON, Profile, ProfileRegistry, RequiredCheck
from lean_sdd.templates import (
    STATE_PATH,
    installation_state,
    profile_installation_state,
    template_files,
)
from lean_sdd.validation import (
    ValidationPlan,
    check_execution_boundaries,
    prepare_validation,
)
from lean_sdd.validation_runner import run_validation

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Execution contract is Linux-only"
)
REGISTRY = ProfileRegistry(
    (
        PYTHON,
        Profile("fixture", "Inert fixture", (RequiredCheck("tests"),)),
        Profile("second", "Second inert fixture", (RequiredCheck("tests"),)),
    )
)


def check_text(
    name: str,
    argv: list[str],
    *,
    component: str | None = "app",
    profile: str = "fixture",
    cwd: str = ".",
    category: str = "tests",
    required: bool = True,
    timeout: float = 5,
) -> str:
    text = (
        f"\n[[checks]]\nname={json.dumps(name)}\n"
        f'scope="{"component" if component else "project"}"\n'
        f"category={json.dumps(category)}\ncwd={json.dumps(cwd)}\n"
        f"argv={json.dumps(argv)}\nrequired={str(required).lower()}\ntimeout_seconds={timeout}\n"
    )
    if component is not None:
        text += f"component={json.dumps(component)}\nprofile={json.dumps(profile)}\n"
    return text


def fixture_project(
    root: Path, checks: str, *, profiles: tuple[str, ...] = ("fixture",)
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / STATE_PATH).parent.mkdir()
    (root / STATE_PATH).write_bytes(
        profile_installation_state(
            {"rules.md": b"inert"},
            template_version="historical",
            identity=InstallationIdentity(profiles, "configured"),
        )
    )
    (root / "lean-sdd.toml").write_text(
        'schema_version=1\n[components.app]\npath="."\n'
        f"profiles={json.dumps(profiles)}\n" + checks,
        encoding="utf-8",
    )


def python_command(script: str) -> list[str]:
    return [sys.executable, "-c", script]


def test_exact_argv_cwd_order_and_full_suite_after_failure(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    script = (
        "import json, os, sys; "
        f"f=open({str(log)!r},'a',encoding='utf-8'); "
        "f.write(json.dumps([os.getcwd(),sys.argv[1:]])+'\\n'); f.close(); "
        "sys.exit(int(sys.argv[1]))"
    )
    literal = [
        "",
        "space in argument",
        "$(touch must-not-exist)",
        "; exit 9",
        "unicode-λ",
    ]
    checks = check_text("z-project", python_command(script) + ["0"], component=None)
    checks += check_text(
        "b-optional", python_command(script) + ["7"], category="extra", required=False
    )
    checks += check_text("a-required", python_command(script) + ["3", *literal])
    fixture_project(tmp_path / "project", checks)
    plan = prepare_validation(tmp_path / "project", registry=REGISTRY)
    assert not plan.problems
    result = run_validation(plan)
    assert result.exit_code == 1
    assert [(r.check.name, r.status, r.returncode) for r in result.checks] == [
        ("a-required", "failed", 3),
        ("b-optional", "failed", 7),
        ("z-project", "passed", 0),
    ]
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert events == [
        [str(plan.root), ["3", *literal]],
        [str(plan.root), ["7"]],
        [str(plan.root), ["0"]],
    ]
    assert not (plan.root / "must-not-exist").exists()


@pytest.mark.parametrize("missing", [False, True])
def test_optional_failures_alone_do_not_fail_required_suite(
    tmp_path: Path, missing: bool
) -> None:
    checks = check_text("required", python_command("pass"))
    checks += check_text(
        "optional",
        ["does-not-exist"] if missing else python_command("raise SystemExit(9)"),
        category="extra",
        required=False,
    )
    fixture_project(tmp_path, checks)
    result = run_validation(prepare_validation(tmp_path, registry=REGISTRY))
    assert result.exit_code == 0
    assert result.checks[0].status == ("missing-executable" if missing else "failed")
    assert result.checks[1].status == "passed"


def test_required_missing_executable_blocks_all_processes(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    checks = check_text("z-required", ["does-not-exist"])
    checks += check_text(
        "a-project",
        python_command(f"from pathlib import Path; Path({str(marker)!r}).touch()"),
        component=None,
    )
    fixture_project(tmp_path, checks)
    plan = prepare_validation(tmp_path, registry=REGISTRY)
    result = run_validation(plan)
    assert result.exit_code == 1
    assert [r.status for r in result.checks] == ["not-run", "missing-executable"]
    assert not marker.exists()


def python_setup(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname="example"\n', encoding="utf-8"
    )
    (root / "uv.lock").write_text("version=1\n", encoding="utf-8")


@pytest.fixture
def inert_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "uv-events.jsonl"
    script = binary / "uv"
    script.write_text(
        f"#!{sys.executable}\nimport os,sys,json\n"
        f"with open({str(log)!r},'a',encoding='utf-8') as f:\n"
        " f.write(json.dumps([os.getcwd(),sys.argv[1:]])+'\\n')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary))
    return log


@pytest.mark.parametrize("legacy", [False, True])
def test_root_python_preserves_all_four_mandatory_commands(
    tmp_path: Path, inert_uv: Path, legacy: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "project"
    if legacy:
        payload = template_files()
        for name, content in payload.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        (root / STATE_PATH).write_bytes(installation_state(payload))
    else:
        initialize(root)
    python_setup(root)
    before = (root / STATE_PATH).read_bytes()
    assert main(["validate", str(root)]) == 0
    output = capsys.readouterr().out
    assert output.count("passed:") == 4
    events = [
        json.loads(line) for line in inert_uv.read_text(encoding="utf-8").splitlines()
    ]
    assert events == [
        [str(root), argv]
        for argv in [
            ["run", "ruff", "format", "--check", "."],
            ["run", "ruff", "check", "."],
            ["run", "pytest"],
            ["run", "mypy", "."],
        ]
    ]
    assert (root / STATE_PATH).read_bytes() == before


def test_multiple_python_components_and_required_integration(
    tmp_path: Path, inert_uv: Path
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    text = (
        'schema_version=1\n[components.api]\npath="src/api"\nprofiles=["python"]\n'
        '[components.worker]\npath="src/worker"\nprofiles=["python"]\n'
    )
    for component in ("worker", "api"):
        path = root / "src" / component
        path.mkdir(parents=True)
        python_setup(path)
        for requirement in PYTHON.required_checks:
            assert requirement.argv is not None
            text += check_text(
                f"{component}-{requirement.category}",
                list(requirement.argv),
                component=component,
                profile="python",
                cwd=f"src/{component}",
                category=requirement.category,
            )
    marker = root / "integration-ran"
    text += check_text(
        "z-integration",
        python_command(f"from pathlib import Path; Path({str(marker)!r}).touch()"),
        component=None,
    )
    (root / "lean-sdd.toml").write_text(text, encoding="utf-8")
    initialize(root)
    result = run_validation(prepare_validation(root))
    assert result.exit_code == 0 and len(result.checks) == 9
    events = [
        json.loads(line) for line in inert_uv.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry[0] for entry in events] == [str(root / "src/api")] * 4 + [
        str(root / "src/worker")
    ] * 4
    assert marker.exists()


def test_multiple_profiles_on_one_component_each_run_their_obligations(
    tmp_path: Path,
) -> None:
    checks = check_text("fixture-check", python_command("pass"))
    checks += check_text(
        "second-check", python_command("raise SystemExit(2)"), profile="second"
    )
    fixture_project(tmp_path, checks, profiles=("fixture", "second"))
    result = run_validation(prepare_validation(tmp_path, registry=REGISTRY))
    assert result.exit_code == 1
    assert [(r.check.profile, r.status) for r in result.checks] == [
        ("fixture", "passed"),
        ("second", "failed"),
    ]


@pytest.mark.parametrize(
    "problem",
    [
        "missing-project",
        "bad-project",
        "missing-lock",
        "linked-lock",
        "oversized-project",
    ],
)
def test_required_python_preconditions_block_even_earlier_runnable_checks(
    tmp_path: Path, inert_uv: Path, problem: str
) -> None:
    root = tmp_path / "project"
    initialize(root)
    python_setup(root)
    if problem == "missing-project":
        (root / "pyproject.toml").unlink()
    elif problem == "bad-project":
        (root / "pyproject.toml").write_bytes(b"\xff")
    elif problem == "oversized-project":
        (root / "pyproject.toml").write_bytes(b"#" * (1024 * 1024 + 1))
    else:
        (root / "uv.lock").unlink()
        if problem == "linked-lock":
            (root / "uv.lock").symlink_to(root / "pyproject.toml")
    result = run_validation(prepare_validation(root))
    assert result.exit_code == 1 and result.problems
    assert all(r.status == "not-run" for r in result.checks)
    assert not inert_uv.exists()


@pytest.mark.parametrize(
    "change",
    [
        "optional-mandatory",
        "replacement-command",
        "bad-timeout",
        "missing-mapping",
        "unsupported-profile",
        "unsafe-cwd",
    ],
)
def test_invalid_configuration_never_executes(
    tmp_path: Path, inert_uv: Path, change: str
) -> None:
    root = tmp_path / "project"
    initialize(root)
    python_setup(root)
    path = root / "lean-sdd.toml"
    text = path.read_text(encoding="utf-8")
    if change == "missing-mapping":
        path.unlink()
    else:
        if change == "optional-mandatory":
            text = text.replace("required = true", "required = false", 1)
        elif change == "replacement-command":
            text = text.replace('"pytest"', '"not-pytest"')
        elif change == "bad-timeout":
            text = text.replace("timeout_seconds = 300", "timeout_seconds = inf", 1)
        elif change == "unsupported-profile":
            text = text.replace("python", "typescript")
        else:
            text = text.replace('cwd = "."', 'cwd = "../outside"', 1)
        path.write_text(text, encoding="utf-8")
    assert main(["validate", str(root)]) == 1
    assert not inert_uv.exists()


def test_rechecks_boundary_changed_after_plan(tmp_path: Path) -> None:
    checks = check_text("only-check", python_command("pass"), cwd="src")
    fixture_project(tmp_path, checks)
    (tmp_path / "src").mkdir()
    plan = prepare_validation(tmp_path, registry=REGISTRY)
    assert not plan.problems
    (tmp_path / "src").rmdir()
    (tmp_path / "src").symlink_to(tmp_path, target_is_directory=True)
    result = run_validation(plan)
    assert result.exit_code == 1 and result.checks[0].status == "not-run"


def test_missing_executable_after_preflight_is_reported_and_suite_continues(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "command"
    executable.write_text(f"#!{sys.executable}\n", encoding="utf-8")
    executable.chmod(0o755)
    fixture_project(
        tmp_path / "project",
        check_text("a-check", [str(executable)])
        + check_text("b-project", python_command("pass"), component=None),
    )
    plan = prepare_validation(tmp_path / "project", registry=REGISTRY)
    executable.unlink()
    result = run_validation(plan)
    assert [r.status for r in result.checks] == ["missing-executable", "passed"]
    assert result.exit_code == 1


def test_relative_command_and_path_entries_resolve_at_check_cwd(tmp_path: Path) -> None:
    root = tmp_path / "project"
    checks = check_text("a-check", ["./tool"], cwd="src")
    checks += check_text("b-project", ["tool"], cwd="src", component=None)
    fixture_project(root, checks)
    (root / "src").mkdir()
    script = root / "src/tool"
    script.write_text(f"#!{sys.executable}\n", encoding="utf-8")
    script.chmod(0o755)
    plan = prepare_validation(root, registry=REGISTRY, environment={"PATH": "."})
    assert all(item.executable == str(script) for item in plan.checks)
    assert run_validation(plan).exit_code == 0


def test_unsupported_execution_environment_never_starts_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_project(tmp_path, check_text("only-check", python_command("pass")))
    monkeypatch.setattr("lean_sdd.validation.sys.platform", "darwin")
    plan = prepare_validation(tmp_path, registry=REGISTRY)
    result = run_validation(plan)
    assert result.exit_code == 1
    assert "Linux" in result.problems[0]
    assert result.checks[0].status == "not-run"


def test_init_and_doctor_do_not_call_execution_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Unexpected validation execution")

    monkeypatch.setattr("lean_sdd.validation_runner.run_validation", forbidden)
    monkeypatch.setattr("lean_sdd.cli.validate", forbidden)
    assert main(["init", str(tmp_path)]) == 0
    main(["doctor", str(tmp_path)])


def wait_for_file(path: Path) -> None:
    deadline = time.monotonic() + 10
    while not path.exists():
        if time.monotonic() >= deadline:
            pytest.fail(f"Subprocess did not signal readiness: {path.name}")
        time.sleep(0.01)


def active_process(pid: int) -> bool:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    # Orphan zombies have terminated; their OS parent owns final reaping.
    return text[text.rfind(")") + 2 :].split()[0] != "Z"


def wait_for_terminated(pids: list[int]) -> None:
    deadline = time.monotonic() + 5
    while any(active_process(pid) for pid in pids):
        if time.monotonic() >= deadline:
            pytest.fail("An owned process-group member survived cleanup")
        time.sleep(0.01)


def kill_fixture_processes(root: Path) -> None:
    for path in root.glob("*.pid"):
        try:
            pid = int(path.read_text(encoding="utf-8"))
            if active_process(pid):
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def tree_fixture(
    root: Path, *, leader_exits: bool = False, timeout: float = 0.1
) -> None:
    root.mkdir()
    script = root / "tree.py"
    script.write_text(
        "import os, signal, time\nfrom pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "Path('parent.pid').write_text(str(os.getpid()))\n"
        "child = os.fork()\n"
        "if child == 0:\n"
        "    grandchild = os.fork()\n"
        "    name = 'grandchild.pid' if grandchild == 0 else 'child.pid'\n"
        "    Path(name).write_text(str(os.getpid()))\n"
        "    while True: time.sleep(60)\n"
        "while not Path('grandchild.pid').exists(): time.sleep(0.01)\n"
        "Path('ready').touch()\n"
        + ("raise SystemExit(0)\n" if leader_exits else "while True: time.sleep(60)\n"),
        encoding="utf-8",
    )
    fixture_project(
        root,
        check_text("a-tree", [sys.executable, str(script)], timeout=timeout)
        + check_text(
            "z-later",
            python_command("from pathlib import Path; Path('later').touch()"),
            component=None,
        ),
    )


@pytest.mark.parametrize("mode", ["timeout", "leader-exit", "monitor-error"])
def test_owned_children_and_grandchildren_are_terminated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    root = tmp_path / "project"
    tree_fixture(root, leader_exits=mode == "leader-exit")
    plan = prepare_validation(root, registry=REGISTRY)
    original = subprocess.Popen

    def spawn(
        args: tuple[str, ...],
        *,
        executable: str | None,
        cwd: Path,
        env: object,
        stdin: int,
        start_new_session: bool,
        shell: bool,
    ) -> subprocess.Popen[bytes]:
        # A real readiness handshake precedes the runner's deadline. Slow process
        # startup cannot make the timeout test pass without ever creating a tree.
        assert isinstance(env, type(plan.environment))
        process = original(
            args,
            executable=executable,
            cwd=cwd,
            env=plan.environment,
            stdin=stdin,
            start_new_session=start_new_session,
            shell=shell,
        )
        if args[1].endswith("tree.py"):
            wait_for_file(root / "ready")
            wait_for_file(root / "child.pid")
            if mode == "monitor-error":
                poll = process.poll
                failed = False

                def fail_once() -> int | None:
                    nonlocal failed
                    if not failed:
                        failed = True
                        raise OSError("sensitive-monitor-error")
                    return poll()

                monkeypatch.setattr(process, "poll", fail_once)
        return process

    try:
        with monkeypatch.context() as patch:
            patch.setattr("lean_sdd.validation_runner.subprocess.Popen", spawn)
            result = run_validation(plan)
        pids = [
            int((root / name).read_text(encoding="utf-8"))
            for name in ("parent.pid", "child.pid", "grandchild.pid")
        ]
        wait_for_terminated(pids)
        expected = {
            "timeout": "timed-out",
            "leader-exit": "passed",
            "monitor-error": "error",
        }[mode]
        assert result.checks[0].status == expected
        assert result.checks[1].status == (
            "not-run" if mode == "monitor-error" else "passed"
        )
        assert result.exit_code == (0 if mode == "leader-exit" else 1)
        assert "sensitive-monitor-error" not in repr(result)
    finally:
        kill_fixture_processes(root)


@pytest.mark.parametrize("number", [signal.SIGINT, signal.SIGTERM])
def test_real_interrupt_cleans_tree_and_reports_remaining_not_run(
    tmp_path: Path, number: int
) -> None:
    root = tmp_path / "project"
    tree_fixture(root, timeout=30)
    harness = (
        "import json,sys; from pathlib import Path; "
        "from lean_sdd.validation import prepare_validation; "
        "from lean_sdd.validation_runner import run_validation; "
        "from lean_sdd.profiles import Profile,ProfileRegistry,RequiredCheck; "
        "registry=ProfileRegistry((Profile('fixture','Inert',"
        "(RequiredCheck('tests'),)),)); "
        "plan=prepare_validation(Path(sys.argv[1]),registry=registry); "
        "result=run_validation(plan); "
        "Path(sys.argv[2]).write_text(json.dumps({'signal':result.cancellation_signal,"
        "'states':[r.status for r in result.checks]})); sys.exit(result.exit_code)"
    )
    report = tmp_path / "report.json"
    process = subprocess.Popen(
        [sys.executable, "-c", harness, str(root), str(report)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        wait_for_file(root / "ready")
        wait_for_file(root / "child.pid")
        process.send_signal(number)
        assert process.wait(timeout=10) == 128 + number
        assert json.loads(report.read_text(encoding="utf-8")) == {
            "signal": number,
            "states": ["cancelled", "not-run"],
        }
        assert not (root / "later").exists()
        pids = [int(p.read_text(encoding="utf-8")) for p in root.glob("*.pid")]
        assert len(pids) == 3
        wait_for_terminated(pids)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        kill_fixture_processes(root)


def test_large_output_is_inherited_without_runner_capture(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    fixture_project(
        tmp_path,
        check_text(
            "output",
            python_command(
                "import sys; sys.stdout.write('x'*1048576); "
                "sys.stderr.write('error-stream')"
            ),
        ),
    )
    result = run_validation(prepare_validation(tmp_path, registry=REGISTRY))
    assert result.exit_code == 0
    output = capfd.readouterr()
    assert len(output.out) == 1048576
    assert output.err == "error-stream"
    assert not hasattr(result.checks[0], "stdout")


def test_boundary_change_during_suite_stops_remaining_checks(tmp_path: Path) -> None:
    fixture_project(
        tmp_path,
        check_text(
            "a-change", python_command("from pathlib import Path; Path('src').rmdir()")
        )
        + check_text("z-project", python_command("pass"), cwd="src", component=None),
    )
    (tmp_path / "src").mkdir()
    result = run_validation(prepare_validation(tmp_path, registry=REGISTRY))
    assert [r.status for r in result.checks] == ["passed", "not-run"]
    assert result.exit_code == 1 and "Preparation changed" in result.problems[0]


def test_optional_timeout_does_not_turn_into_required_failure(tmp_path: Path) -> None:
    fixture_project(
        tmp_path,
        check_text(
            "a-optional",
            python_command("import time; time.sleep(60)"),
            category="extra",
            required=False,
            timeout=0.1,
        )
        + check_text("z-required", python_command("pass")),
    )
    result = run_validation(prepare_validation(tmp_path, registry=REGISTRY))
    assert [r.status for r in result.checks] == ["timed-out", "passed"]
    assert result.exit_code == 0


def test_cleanup_uncertainty_blocks_later_checks_without_exposing_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lean_sdd import validation_runner

    fixture_project(
        tmp_path,
        check_text("a-check", python_command("pass"))
        + check_text("z-project", python_command("pass"), component=None),
    )
    cleanup = validation_runner._cleanup

    def uncertain(process: subprocess.Popen[bytes]) -> None:
        cleanup(process)
        raise OSError("private-cleanup-detail")

    monkeypatch.setattr(validation_runner, "_cleanup", uncertain)
    result = run_validation(prepare_validation(tmp_path, registry=REGISTRY))
    assert [r.status for r in result.checks] == ["passed", "not-run"]
    assert result.exit_code == 1 and "Cleanup unconfirmed" in result.problems[0]
    assert "private-cleanup-detail" not in repr(result)


def test_negative_signal_exit_is_distinct_from_runner_cancellation(
    tmp_path: Path,
) -> None:
    fixture_project(
        tmp_path,
        check_text(
            "a-signal",
            python_command("import os,signal; os.kill(os.getpid(),signal.SIGTERM)"),
        )
        + check_text("z-project", python_command("pass"), component=None),
    )
    result = run_validation(prepare_validation(tmp_path, registry=REGISTRY))
    assert result.checks[0].status == "failed"
    assert result.checks[0].returncode == -signal.SIGTERM
    assert result.checks[1].status == "passed"
    assert result.cancellation_signal is None and result.exit_code == 1


@pytest.mark.parametrize("state", [b"{", b'{"schema_version": 9}', b"x" * 1_000_001])
def test_invalid_installation_blocks_resolution(tmp_path: Path, state: bytes) -> None:
    fixture_project(tmp_path, check_text("check", python_command("pass")))
    (tmp_path / STATE_PATH).write_bytes(state)
    with pytest.raises(ValueError, match="installation record"):
        prepare_validation(tmp_path, registry=REGISTRY)


def test_unavailable_installed_identity_is_not_replaced(tmp_path: Path) -> None:
    fixture_project(tmp_path, check_text("check", python_command("pass")))
    path = tmp_path / STATE_PATH
    state = json.loads(path.read_bytes())
    state["profiles"] = ["unavailable"]
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported profile: unavailable"):
        prepare_validation(tmp_path, registry=REGISTRY)


def test_plan_snapshots_environment_and_safe_repr(tmp_path: Path) -> None:
    fixture_project(
        tmp_path, check_text("check", python_command("pass") + ["private-argument"])
    )
    environment = {"PATH": os.defpath, "PRIVATE": "private-environment"}
    plan = prepare_validation(tmp_path, registry=REGISTRY, environment=environment)
    environment["PRIVATE"] = "changed"
    assert plan.environment["PRIVATE"] == "private-environment"
    result = run_validation(plan)
    assert result.exit_code == 0
    assert "private-argument" not in repr(plan) + repr(result)
    assert "private-environment" not in repr(plan) + repr(result)


def test_validate_rejects_unknown_cli_options() -> None:
    with pytest.raises(SystemExit) as error:
        main(["validate", "--unsupported"])
    assert error.value.code == 2


def test_cancellation_during_boundary_recheck_does_not_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lean_sdd import validation_runner

    fixture_project(
        tmp_path,
        check_text(
            "only-check",
            python_command("from pathlib import Path; Path('executed').touch()"),
        ),
    )
    plan = prepare_validation(tmp_path, registry=REGISTRY)
    boundary = check_execution_boundaries
    calls = 0

    def interrupt_at_launch(plan: ValidationPlan) -> None:
        nonlocal calls
        calls += 1
        boundary(plan)
        if calls == 2:
            os.kill(os.getpid(), signal.SIGINT)

    previous = {
        number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
    }
    monkeypatch.setattr(
        validation_runner, "check_execution_boundaries", interrupt_at_launch
    )
    result = run_validation(plan)
    assert result.exit_code == 130 and result.checks[0].status == "not-run"
    assert not (tmp_path / "executed").exists()
    assert previous == {number: signal.getsignal(number) for number in previous}
