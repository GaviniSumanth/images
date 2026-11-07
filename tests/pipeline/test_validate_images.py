import pytest

from validate_images import validate_images

pytestmark = pytest.mark.unit


def test_repository_images_pass_validation():
    validate_images()
