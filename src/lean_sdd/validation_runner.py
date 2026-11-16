"""Linux sequential execution with owned process groups and bounded cleanup."""

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from types import FrameType

from lean_sdd.configuration import ConfigurationError
from lean_sdd.validation import (
    CheckResult,
    PlannedCheck,
    ValidationPlan,
    ValidationResult,
    check_execution_boundaries,
)

POLL_SECONDS = 0.05
TERMINATION_GRACE_SECONDS = 0.5
KILL_WAIT_SECONDS = 1.0


@dataclass
class _Cancellation:
    number: int | None = None

    def receive(self, number: int, frame: FrameType | None) -> None:
        # Record rather than raise: a signal between Popen and ownership
        # assignment must not strand a process. Repeated signals cannot abort cleanup.
        if self.number is None:
            self.number = number


def _group_exists(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    return True


def _signal_group(group: int, number: int) -> None:
    try:
        os.killpg(group, number)
    except ProcessLookupError:
        pass


def _cleanup(process: subprocess.Popen[bytes]) -> None:
    """Terminate remaining group members even after the leading command exits.

    Descendants must remain in the new process group. This is process ownership,
    not confinement of malicious commands that detach into another session.
    """
    if _group_exists(process.pid):
        _signal_group(process.pid, signal.SIGTERM)
        deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
        while _group_exists(process.pid) and time.monotonic() < deadline:
            process.poll()  # Reap our direct child while giving descendants grace.
            time.sleep(POLL_SECONDS)
        if _group_exists(process.pid):
            _signal_group(process.pid, signal.SIGKILL)
    process.wait(timeout=KILL_WAIT_SECONDS)


def _run_check(
    item: PlannedCheck, plan: ValidationPlan, cancellation: _Cancellation
) -> tuple[CheckResult, str | None]:
    process: subprocess.Popen[bytes] | None = None
    outcome = CheckResult(
        item.check, "error", detail="Runner error; inspect the reviewed command."
    )
    problem: str | None = None
    try:
        process = subprocess.Popen(
            item.check.argv,
            executable=item.executable,
            cwd=item.directory,
            env=plan.environment,
            stdin=subprocess.DEVNULL,
            # Inherit stdout/stderr: no pipe buffers, unbounded capture, or log files.
            start_new_session=True,
            shell=False,
        )
        deadline = time.monotonic() + item.check.timeout_seconds
        while True:
            if cancellation.number is not None:
                outcome = CheckResult(
                    item.check, "cancelled", detail="Execution interrupted."
                )
                break
            returncode = process.poll()
            if returncode is not None:
                outcome = CheckResult(
                    item.check, "passed" if returncode == 0 else "failed", returncode
                )
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                outcome = CheckResult(
                    item.check, "timed-out", detail="Configured timeout exceeded."
                )
                break
            time.sleep(min(POLL_SECONDS, remaining))
    except FileNotFoundError:
        outcome = CheckResult(
            item.check,
            "missing-executable",
            detail="Executable disappeared or its interpreter is missing.",
        )
    except KeyboardInterrupt:
        cancellation.number = signal.SIGINT
        outcome = CheckResult(item.check, "cancelled", detail="Execution interrupted.")
    except (OSError, ValueError):
        # Do not echo exceptions: they may embed argv, paths or environment data.
        outcome = CheckResult(
            item.check, "error", detail="Unable to start or monitor the command."
        )
        if process is not None:
            problem = "Runner failed while monitoring the command; execution stopped."
    finally:
        if process is not None:
            try:
                _cleanup(process)
            except (OSError, subprocess.TimeoutExpired):
                problem = "Cleanup unconfirmed; inspect remaining processes."
    return outcome, problem


def run_validation(plan: ValidationPlan) -> ValidationResult:
    """Execute only a plan returned by prepare_validation, in stable check-name order.

    All required preparation failures block every process. Optional unavailable
    executables are visible but do not block other checks. Ordinary failure,
    timeout, or launch error does not skip the remaining runnable suite. Boundary
    failure, interruption, or uncertain cleanup stops the invocation. Child output
    is inherited verbatim; callers must review commands and credential exposure.
    """
    results = [
        CheckResult(
            item.check,
            "missing-executable",
            detail="Executable unavailable; inspect argv and PATH.",
        )
        if item.executable is None
        else CheckResult(item.check, "not-run", detail="Execution has not started.")
        for item in plan.checks
    ]
    if plan.problems:
        return ValidationResult(tuple(results), plan.problems)
    try:
        check_execution_boundaries(plan)
    except ConfigurationError as error:
        return ValidationResult(tuple(results), (str(error),))
    except KeyboardInterrupt:
        return ValidationResult(tuple(results), cancellation_signal=signal.SIGINT)
    cancellation = _Cancellation()
    signals = (signal.SIGINT, signal.SIGTERM)
    previous = {number: signal.getsignal(number) for number in signals}
    problems: list[str] = []
    try:
        for number in signals:
            signal.signal(number, cancellation.receive)
        for index, item in enumerate(plan.checks):
            if cancellation.number is not None:
                break
            if item.executable is None:
                continue
            try:
                check_execution_boundaries(plan)
            except ConfigurationError as error:
                problems.append(
                    f"Preparation changed before check {item.check.name}: {error}"
                )
                break
            if cancellation.number is not None:
                break
            result, problem = _run_check(item, plan, cancellation)
            results[index] = result
            if problem:
                problems.append(f"Check {item.check.name}: {problem}")
                break
    except KeyboardInterrupt:
        cancellation.number = signal.SIGINT
    finally:
        for number in signals:
            signal.signal(number, previous[number])
    return ValidationResult(tuple(results), tuple(problems), cancellation.number)
