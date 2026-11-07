import re
from pathlib import Path

import pytest

from release_config import load_repositories

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOSITORIES = load_repositories()


def containerfile(entry):
    return REPO_ROOT / entry["containerfile"]


def final_stage(text):
    matches = list(re.finditer(r"(?im)^\s*FROM\s+(.+)$", text))
    assert matches, "Containerfile has no FROM instruction"
    return matches[-1].group(1).strip(), text[matches[-1].end() :]


def build_args(text):
    values = {}
    for match in re.finditer(
        r"(?im)^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)=(\S+)", text
    ):
        values[match.group(1)] = match.group(2)
    return values


def expand(value, arguments):
    return re.sub(
        r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?",
        lambda match: arguments.get(match.group(1), match.group(0)),
        value,
    )


def runtime_base(entry):
    text = containerfile(entry).read_text()
    base, _ = final_stage(text)
    return expand(base.split()[0], build_args(text))


@pytest.mark.parametrize("entry", REPOSITORIES, ids=lambda entry: entry["image"])
def test_no_healthcheck(entry):
    text = containerfile(entry).read_text()
    assert not re.search(r"(?im)^\s*HEALTHCHECK\b", text), entry["image"]


@pytest.mark.parametrize("entry", REPOSITORIES, ids=lambda entry: entry["image"])
def test_runtime_user_is_non_root(entry):
    _, stage = final_stage(containerfile(entry).read_text())
    users = re.findall(r"(?im)^\s*USER\s+(\S+)\s*$", stage)
    assert users, f"{entry['image']} runtime stage has no USER"
    assert users[-1] == "1000:1000", entry["image"]


@pytest.mark.parametrize("entry", REPOSITORIES, ids=lambda entry: entry["image"])
def test_runtime_has_expose_and_start_command(entry):
    _, stage = final_stage(containerfile(entry).read_text())
    assert re.search(r"(?im)^\s*EXPOSE\s+", stage), entry["image"]
    assert re.search(r"(?im)^\s*(ENTRYPOINT|CMD)\s+", stage), entry["image"]


@pytest.mark.parametrize("entry", REPOSITORIES, ids=lambda entry: entry["image"])
def test_runtime_base_is_hardened(entry):
    image = runtime_base(entry)
    assert image == "scratch" or image.startswith("dhi.io/"), (
        f"{entry['image']} runtime base is not hardened: {image}"
    )


@pytest.mark.parametrize("entry", REPOSITORIES, ids=lambda entry: entry["image"])
def test_no_oci_labels_in_containerfile(entry):
    for line in containerfile(entry).read_text().splitlines():
        if line.strip().upper().startswith("LABEL"):
            assert "org.opencontainers.image." not in line, entry["image"]
