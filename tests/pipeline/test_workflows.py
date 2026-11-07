import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
WORKFLOW_FILES = sorted(WORKFLOW_DIR.glob("*.yml"))


def workflow(name):
    return yaml.load(
        (WORKFLOW_DIR / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def uses_values(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "uses":
                yield item
            else:
                yield from uses_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from uses_values(item)


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda path: path.name)
def test_external_actions_are_pinned_to_commits(path):
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    for uses in uses_values(data):
        if uses.startswith("./"):
            continue
        assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", uses), uses


def test_no_candidate_tags_remain_in_workflows():
    for path in WORKFLOW_FILES:
        assert "candidate-" not in path.read_text(encoding="utf-8"), path


def test_workflows_do_not_condition_on_image_names():
    for path in WORKFLOW_FILES:
        text = path.read_text(encoding="utf-8")
        assert "if: matrix.release.image ==" not in text, path


def test_prebuild_step_is_unconditional():
    steps = workflow("container-pipeline.yml")["jobs"]["build"]["steps"]
    step = next(
        step
        for step in steps
        if step.get("name") == "Run pre-build validation tests"
    )
    assert "if" not in step
    assert "matrix.release.prebuild_test" in step["run"]


def test_build_job_uses_the_matrix_prebuild_test():
    text = (WORKFLOW_DIR / "container-pipeline.yml").read_text(encoding="utf-8")
    assert "matrix.release.prebuild_test" in text
    assert "UPSTREAM_SOURCE" in text
    assert "PREBUILD_IMAGE" not in text


def test_pipeline_has_build_test_scan_publish_and_verify_jobs():
    jobs = workflow("container-pipeline.yml")["jobs"]
    assert {"build", "test", "scan", "publish", "verify"} <= set(jobs)


def test_build_produces_an_oci_archive():
    text = (WORKFLOW_DIR / "container-pipeline.yml").read_text(encoding="utf-8")
    assert "type=oci" in text
    assert "actions/upload-artifact@" in text
    assert "actions/download-artifact@" in text


def test_publish_uses_the_tested_archive():
    text = (WORKFLOW_DIR / "container-pipeline.yml").read_text(encoding="utf-8")
    assert "publish_image.py" in text
    assert "promote_image.py" not in text


def test_build_workflow_passes_both_matrices():
    text = (WORKFLOW_DIR / "build-container.yml").read_text(encoding="utf-8")
    assert "build_matrix" in text
    assert "verify_matrix" in text


def test_detect_reconciles_unpublished_verify_entries():
    detect = workflow("build-container.yml")["jobs"]["detect"]
    assert detect["outputs"]["build_matrix"] == (
        "${{ steps.reconcile.outputs.build_matrix }}"
    )
    assert detect["outputs"]["verify_matrix"] == (
        "${{ steps.reconcile.outputs.verify_matrix }}"
    )

    step = next(
        step
        for step in detect["steps"]
        if step.get("name") == "Reconcile unpublished verify entries"
    )
    assert "reconcile_verify.py" in step["run"]
    assert step["env"]["BUILD_MATRIX"] == "${{ steps.changes.outputs.build_matrix }}"
    assert step["env"]["VERIFY_MATRIX"] == "${{ steps.changes.outputs.verify_matrix }}"


def test_unit_tests_run_before_dispatch():
    text = (WORKFLOW_DIR / "build-container.yml").read_text(encoding="utf-8")
    assert "pytest" in text
    assert "-m unit" in text
    assert "validate_upstream_tags" not in text


def test_test_job_uses_the_matrix_test_file():
    text = (WORKFLOW_DIR / "container-pipeline.yml").read_text(encoding="utf-8")
    assert "matrix.release.test_file" in text


def test_build_job_does_not_push():
    text = (WORKFLOW_DIR / "container-pipeline.yml").read_text(encoding="utf-8")
    assert "push: true" not in text


def test_publish_job_can_write_packages():
    jobs = workflow("container-pipeline.yml")["jobs"]
    assert jobs["publish"]["permissions"]["packages"] == "write"


def test_verify_job_pulls_the_alias():
    text = (WORKFLOW_DIR / "container-pipeline.yml").read_text(encoding="utf-8")
    assert "outputs.alias" in text
