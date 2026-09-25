"""Regression test: app.retrieval.factory._load_experiment_config must never
read a file outside app/eval/experiments/.

`experiment` can originate from choose_experiment's X-Experiment header
(app/api/main.py), client-controlled input on a normal /ask request. The
previous implementation accepted any existing .yml/.yaml file path, so a
request could read any such file the process can see. See app/api/main.py
for the separate admin-token gate on X-Experiment itself (this test only
covers the file-loading layer, which must stay safe regardless of who is
allowed to set the header).
"""
from __future__ import annotations

from app.retrieval.factory import _load_experiment_config


def test_known_experiment_resolves():
    cfg = _load_experiment_config("baseline")
    assert cfg.get("name") == "baseline"


def test_unknown_experiment_returns_empty():
    assert _load_experiment_config("definitely-not-a-real-experiment") == {}


def test_parent_directory_traversal_is_rejected():
    assert _load_experiment_config("../../../../etc/passwd") == {}
    assert _load_experiment_config("..") == {}


def test_path_with_separator_is_rejected():
    assert _load_experiment_config("foo/bar") == {}
    assert _load_experiment_config("some/../baseline") == {}


def test_absolute_path_is_rejected():
    assert _load_experiment_config("/etc/passwd") == {}
