from pathlib import Path

import pytest

from prepare_build_context import BuildContextError, stage_image_assets

pytestmark = pytest.mark.unit


def test_stages_nested_image_assets(tmp_path):
    build_context = tmp_path / "source"
    assets = tmp_path / "image" / "assets"
    build_context.mkdir()
    config = assets / "config" / "qBittorrent.conf"
    config.parent.mkdir(parents=True)
    config.write_text("[Preferences]\nDownloads\\SavePath=/downloads/\n")

    assert stage_image_assets(build_context, assets)
    assert (
        build_context / "container-assets" / "config" / "qBittorrent.conf"
    ).read_text() == config.read_text()


def test_skips_missing_image_assets(tmp_path):
    build_context = tmp_path / "source"
    build_context.mkdir()

    assert not stage_image_assets(build_context, tmp_path / "image" / "assets")
    assert not (build_context / "container-assets").exists()


def test_rejects_reserved_build_context_path(tmp_path):
    build_context = tmp_path / "source"
    assets = tmp_path / "image" / "assets"
    build_context.mkdir()
    assets.mkdir(parents=True)
    (build_context / "container-assets").mkdir()

    with pytest.raises(BuildContextError, match="reserved path"):
        stage_image_assets(build_context, assets)


def test_rejects_symlinked_image_assets(tmp_path):
    build_context = tmp_path / "source"
    assets = tmp_path / "image" / "assets"
    build_context.mkdir()
    assets.mkdir(parents=True)
    outside_file = tmp_path / "outside.conf"
    outside_file.write_text("not an image asset")
    (assets / "outside.conf").symlink_to(outside_file)

    with pytest.raises(BuildContextError, match="must not contain symlinks"):
        stage_image_assets(build_context, assets)
