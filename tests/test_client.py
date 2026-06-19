"""Tests for the Claude Code headless client (code/agent/client.py).

Every test mocks ``subprocess.run`` so NO real ``claude`` CLI is ever invoked
and no network call is made. The tests pin down the exact command construction
and JSON-envelope parsing that every downstream stage depends on.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from agent import client as client_module
from agent.client import ClaudeError, run_claude_json, run_claude_text


def _envelope(result_text: str, is_error: bool = False) -> str:
    """Build a fake Claude Code JSON envelope (what stdout looks like)."""
    return json.dumps({"result": result_text, "is_error": is_error})


def _completed(stdout: str, returncode: int = 0) -> SimpleNamespace:
    """Stand-in for ``subprocess.CompletedProcess``."""
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


# ---------------------------------------------------------------------------
# run_claude_text
# ---------------------------------------------------------------------------


def test_run_claude_text_returns_result_string() -> None:
    """The plain-text path returns the envelope's ``result`` value verbatim."""
    with mock.patch.object(
        client_module.subprocess,
        "run",
        return_value=_completed(_envelope("hello world")),
    ) as run_mock:
        out = run_claude_text("say hi", model="claude-haiku-4-5")

    assert out == "hello world"
    run_mock.assert_called_once()


def test_command_has_core_flags_and_neutral_cwd() -> None:
    """Command shape: -p, --output-format json, --model, --allowedTools Read,
    and it runs from a temp cwd (never the repo root)."""
    fake_tmp = "/tmp/neutral-claude-cwd"
    with mock.patch.object(
        client_module.tempfile, "mkdtemp", return_value=fake_tmp
    ), mock.patch.object(
        client_module.subprocess,
        "run",
        return_value=_completed(_envelope("ok")),
    ) as run_mock:
        run_claude_text("prompt text", model="claude-opus-4-8")

    args, kwargs = run_mock.call_args
    command = args[0]

    assert command[0] == client_module.CLAUDE_BIN
    assert "-p" in command
    assert "prompt text" in command
    assert command[command.index("--output-format") + 1] == "json"
    assert command[command.index("--model") + 1] == "claude-opus-4-8"
    assert command[command.index("--allowedTools") + 1] == "Read"
    # Neutral cwd so the nested claude does not load the repo AGENTS.md.
    assert kwargs["cwd"] == fake_tmp
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True


def test_system_prompt_appended_when_given() -> None:
    """A non-empty system string adds --append-system-prompt <system>."""
    with mock.patch.object(
        client_module.subprocess,
        "run",
        return_value=_completed(_envelope("ok")),
    ) as run_mock:
        run_claude_text("p", model="m", system="be terse")

    command = run_mock.call_args[0][0]
    assert command[command.index("--append-system-prompt") + 1] == "be terse"


def test_no_system_flag_when_system_absent() -> None:
    """Without a system string the flag must not appear at all."""
    with mock.patch.object(
        client_module.subprocess,
        "run",
        return_value=_completed(_envelope("ok")),
    ) as run_mock:
        run_claude_text("p", model="m")

    assert "--append-system-prompt" not in run_mock.call_args[0][0]


def test_add_dir_for_each_unique_image_parent(tmp_path: Path) -> None:
    """One --add-dir per UNIQUE parent directory of the supplied images."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    img1 = dir_a / "img_1.png"
    img2 = dir_a / "img_2.png"  # same parent as img1 -> dedup
    img3 = dir_b / "img_3.png"
    for image in (img1, img2, img3):
        image.write_bytes(b"fake")

    with mock.patch.object(
        client_module.subprocess,
        "run",
        return_value=_completed(_envelope("ok")),
    ) as run_mock:
        run_claude_text(
            "p",
            model="m",
            image_paths=[str(img1), str(img2), str(img3)],
        )

    command = run_mock.call_args[0][0]
    add_dir_values = [
        command[i + 1] for i, tok in enumerate(command) if tok == "--add-dir"
    ]
    # Exactly the two unique parent dirs, as absolute paths.
    assert sorted(add_dir_values) == sorted(
        [str(dir_a.resolve()), str(dir_b.resolve())]
    )
    assert len(add_dir_values) == 2


# ---------------------------------------------------------------------------
# run_claude_json
# ---------------------------------------------------------------------------


def test_run_claude_json_parses_bare_object() -> None:
    """A bare JSON object inside the result is parsed into a dict."""
    payload = {"status": "replied", "score": 3}
    with mock.patch.object(
        client_module.subprocess,
        "run",
        return_value=_completed(_envelope(json.dumps(payload))),
    ):
        out = run_claude_json("p", model="m")

    assert out == payload


def test_run_claude_json_strips_code_fences() -> None:
    """```json fenced blocks are stripped before parsing."""
    fenced = "```json\n{\"ok\": true, \"n\": 1}\n```"
    with mock.patch.object(
        client_module.subprocess,
        "run",
        return_value=_completed(_envelope(fenced)),
    ):
        out = run_claude_json("p", model="m")

    assert out == {"ok": True, "n": 1}


def test_run_claude_json_extracts_first_balanced_block() -> None:
    """Leading/trailing prose around the object is tolerated."""
    noisy = 'Here is the result:\n{"a": 1, "b": {"c": 2}}\nThanks!'
    with mock.patch.object(
        client_module.subprocess,
        "run",
        return_value=_completed(_envelope(noisy)),
    ):
        out = run_claude_json("p", model="m")

    assert out == {"a": 1, "b": {"c": 2}}


def test_run_claude_json_retries_once_on_unparseable_then_succeeds() -> None:
    """First result has no JSON -> nudge retry -> second result parses."""
    bad = _completed(_envelope("no json here at all"))
    good = _completed(_envelope('{"recovered": true}'))
    with mock.patch.object(
        client_module.subprocess, "run", side_effect=[bad, good]
    ) as run_mock:
        out = run_claude_json("p", model="m")

    assert out == {"recovered": True}
    assert run_mock.call_count == 2
    # The retry prompt must carry a "valid JSON" nudge.
    retry_prompt = run_mock.call_args_list[1][0][0]
    assert any("JSON" in token for token in retry_prompt)


def test_run_claude_json_raises_when_never_parseable() -> None:
    """Both attempts unparseable -> ClaudeError."""
    bad = _completed(_envelope("still no json"))
    with mock.patch.object(
        client_module.subprocess, "run", return_value=bad
    ):
        with pytest.raises(ClaudeError):
            run_claude_json("p", model="m")


# ---------------------------------------------------------------------------
# error / retry behaviour
# ---------------------------------------------------------------------------


def test_retries_on_is_error_then_succeeds() -> None:
    """is_error=True triggers a retry; a later clean envelope wins."""
    err = _completed(_envelope("boom", is_error=True))
    ok = _completed(_envelope("fine"))
    with mock.patch.object(
        client_module.time, "sleep", return_value=None
    ), mock.patch.object(
        client_module.subprocess, "run", side_effect=[err, ok]
    ) as run_mock:
        out = run_claude_text("p", model="m", max_retries=2)

    assert out == "fine"
    assert run_mock.call_count == 2


def test_raises_claude_error_after_exhausting_retries() -> None:
    """Persistent is_error raises ClaudeError after max_retries attempts."""
    err = _completed(_envelope("boom", is_error=True))
    with mock.patch.object(
        client_module.time, "sleep", return_value=None
    ), mock.patch.object(
        client_module.subprocess, "run", return_value=err
    ) as run_mock:
        with pytest.raises(ClaudeError):
            run_claude_text("p", model="m", max_retries=2)

    # 1 initial attempt + 2 retries = 3 invocations.
    assert run_mock.call_count == 3


def test_raises_claude_error_on_nonzero_exit() -> None:
    """A nonzero return code is treated as failure and retried, then raised."""
    failed = _completed("", returncode=1)
    with mock.patch.object(
        client_module.time, "sleep", return_value=None
    ), mock.patch.object(
        client_module.subprocess, "run", return_value=failed
    ):
        with pytest.raises(ClaudeError):
            run_claude_text("p", model="m", max_retries=1)


def test_raises_claude_error_on_timeout() -> None:
    """A subprocess timeout is retried and ultimately raises ClaudeError."""
    import subprocess as real_subprocess

    with mock.patch.object(
        client_module.time, "sleep", return_value=None
    ), mock.patch.object(
        client_module.subprocess,
        "run",
        side_effect=real_subprocess.TimeoutExpired(cmd="claude", timeout=1),
    ):
        with pytest.raises(ClaudeError):
            run_claude_text("p", model="m", max_retries=1)


# ---------------------------------------------------------------------------
# caching of json results when images are involved
# ---------------------------------------------------------------------------


def test_json_with_images_is_cached_and_not_recomputed(tmp_path: Path) -> None:
    """With image_paths, a second identical call hits the disk cache and does
    NOT invoke subprocess.run again."""
    image = tmp_path / "img_1.png"
    image.write_bytes(b"stable-bytes")
    cache_dir = tmp_path / "cache"

    payload = {"object": "car", "confidence": 0.9}
    ok = _completed(_envelope(json.dumps(payload)))

    with mock.patch.object(
        client_module, "CACHE_DIR", cache_dir
    ), mock.patch.object(
        client_module.subprocess, "run", return_value=ok
    ) as run_mock:
        first = run_claude_json("describe", model="m", image_paths=[str(image)])
        second = run_claude_json("describe", model="m", image_paths=[str(image)])

    assert first == payload == second
    # Only the first call shells out; the second is served from cache.
    assert run_mock.call_count == 1
