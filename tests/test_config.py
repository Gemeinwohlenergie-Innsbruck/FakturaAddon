"""Template path resolution.

A packaged install shipped with settings naming `email_template.html`, a file
that has never existed in this repository, so it loaded no email template at
all. These cover the resolution rules that fix it.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_empty_stays_empty():
    assert config.resolve_resource("") == ""
    assert config.resolve_resource(None) == ""


def test_a_shipped_name_resolves_to_the_shipped_file():
    resolved = config.resolve_resource("email_template_clean.html")
    assert os.path.isabs(resolved)
    assert os.path.exists(resolved)
    assert resolved.startswith(REPO)


def test_absolute_path_is_returned_untouched(tmp_path):
    f = tmp_path / "meine_vorlage.html"
    f.write_text("<p>x</p>", encoding="utf-8")
    assert config.resolve_resource(str(f)) == str(f)


def test_legacy_default_is_migrated_to_the_file_actually_shipped():
    """The regression: older settings name a template that never existed."""
    resolved = config.resolve_resource("email_template.html")
    assert os.path.basename(resolved) == "email_template_clean.html"
    assert os.path.exists(resolved)


def test_legacy_invoice_default_is_migrated_too():
    resolved = config.resolve_resource("template_invoice.docx")
    assert os.path.basename(resolved) == "template_invoice_clean.docx"
    assert os.path.exists(resolved)


def test_an_operators_own_missing_file_is_not_silently_swapped():
    """Only the known-bad defaults migrate. A deliberate choice that is
    missing must be reported, not replaced with a different template."""
    resolved = config.resolve_resource("unsere_eigene_vorlage.html")
    assert resolved == "unsere_eigene_vorlage.html"
    assert not os.path.exists(resolved)


@pytest.mark.parametrize("platform,expected", [
    ("darwin", "Library/Application Support/FakturaAddon"),
    ("win32", "FakturaAddon"),
])
def test_config_dir_follows_platform_convention(platform, expected, monkeypatch):
    monkeypatch.setattr(sys, "platform", platform)
    assert expected.replace("/", os.sep) in str(config._user_config_dir())
