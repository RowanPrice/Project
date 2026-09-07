"""The shared Session and the static browser build.

The Flask server and the GitHub Pages build run the same simulation through
the same Session object, so these tests cover both front ends at once.
"""

import json
import pathlib
import subprocess
import sys

import pytest

from reactorsim.web import Session

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def session():
    return Session(scenario="full_power", seed=5)


def test_state_carries_history(session):
    session.advance(60.0)
    state = session.state()
    assert state["history"]
    assert state["history"][0]["power"] == pytest.approx(100.0, abs=3.0)


def test_history_is_bounded(session):
    for _ in range(400):
        session.advance(30.0)
    assert len(session.history) <= Session.HISTORY_LENGTH
    assert len(session.state()["history"]) <= Session.HISTORY_WINDOW


def test_actions_return_the_new_state(session):
    result = session.act("scram")
    assert result["ok"]
    assert result["state"]["reactor"]["tripped"] is True


def test_reset_switches_scenario(session):
    result = session.reset("commissioning")
    assert result["ok"]
    assert result["state"]["scenario"] == "commissioning"
    assert session.history == []


def test_reset_rejects_an_unknown_scenario(session):
    assert session.reset("nonsense")["ok"] is False


def test_scenarios_are_listed_with_briefings():
    scenarios = Session.scenarios()
    assert len(scenarios) >= 6
    for scenario in scenarios:
        assert scenario["key"] and scenario["name"] and scenario["briefing"]


# -- the JSON surface the in-browser build calls through Pyodide -----------

def test_json_api_surface(session):
    session.advance(30.0)
    assert json.loads(session.state_json())["clock"]["time"] > 0
    assert isinstance(json.loads(session.history_json()), list)
    assert json.loads(session.scenarios_json())[0]["key"]
    assert json.loads(session.save_json())["version"] == 2

    action = json.loads(session.act_json(json.dumps(
        {"action": "turbine", "payload": {"demand": 0.8}})))
    assert action["ok"] is True
    assert action["state"]["thermal"]["turbine_demand"] == pytest.approx(0.8)

    started = json.loads(session.new_json(json.dumps({"scenario": "sandbox"})))
    assert started["ok"] and started["state"]["scenario"] == "sandbox"


def test_act_json_tolerates_an_empty_body(session):
    assert json.loads(session.act_json(""))["ok"] is False


# -- the static build ------------------------------------------------------

def test_reactorsim_imports_only_the_standard_library():
    """The browser build runs this package under Pyodide, which has no pip."""
    import ast

    allowed = {"math", "random", "json", "time", "dataclasses", "__future__",
               "typing", "collections", "itertools", "functools", "enum"}
    for path in sorted((ROOT / "reactorsim").glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in allowed, f"{path}: {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                root = node.module.split(".")[0]
                assert root in allowed or root == "reactorsim", f"{path}: {node.module}"


def test_docs_build_is_up_to_date():
    """``docs/`` is committed, so it must match the sources it was built from."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_pages.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr


def test_docs_bundle_contains_every_module():
    modules = {path.name for path in (ROOT / "reactorsim").glob("*.py")}
    built = {path.name for path in (ROOT / "docs" / "reactorsim").glob("*.py")}
    assert modules == built
    boot = (ROOT / "docs" / "boot.js").read_text()
    for name in modules:
        assert name in boot


def test_docs_html_has_no_template_syntax():
    html = (ROOT / "docs" / "index.html").read_text()
    assert "url_for" not in html
    assert "{{" not in html
    assert 'src="boot.js"' in html
