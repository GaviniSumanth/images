from pathlib import Path

import pytest

import validate_test_config
from validate_test_config import ValidationError, integration_test_file, validate_test_config as validate


pytestmark = pytest.mark.unit


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    monkeypatch.setattr(validate_test_config, "REPO_ROOT", tmp_path)
    (tmp_path / "tests" / "images").mkdir(parents=True)
    (tmp_path / "tests" / "requirements-test.txt").write_text("pytest\n")
    return tmp_path


def test_integration_test_file_uses_normalized_name(fake_root):
    assert integration_test_file("error-pages") == (
        fake_root / "tests" / "images" / "test_error_pages.py"
    )


def test_valid_test_config(fake_root):
    (fake_root / "tests" / "images" / "test_example.py").write_text("")
    validate("example")


def test_missing_test_file_is_rejected(fake_root):
    with pytest.raises(ValidationError, match="Missing pytest entrypoint"):
        validate("example")


def test_missing_requirements_is_rejected(fake_root):
    (fake_root / "tests" / "images" / "test_example.py").write_text("")
    (fake_root / "tests" / "requirements-test.txt").unlink()
    with pytest.raises(ValidationError, match="Missing test requirements"):
        validate("example")


def test_invalid_image_is_rejected(fake_root):
    with pytest.raises(ValidationError, match="Invalid image name"):
        validate("Bad")
