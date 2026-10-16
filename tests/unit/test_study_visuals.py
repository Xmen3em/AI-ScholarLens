import io
import os

from PIL import Image
from src.services.study.content import EvidenceBlock
from src.services.study.tutor import validate_lesson
from src.services.study.visuals import study_map

from tests.unit.test_study_tutor import lesson


def test_map_uses_validated_sections_and_produces_a_bounded_real_image():
    document = validate_lesson(lesson(), [EvidenceBlock(id="p1b1", page=1, section="Method", text="The model uses attention.")])
    data = study_map(document)
    if data is None:
        # Non-Windows installations require a Pillow build with libraqm.
        assert os.name != "nt"
        return
    assert data.startswith(b"\x89PNG") and len(data) < 180000
    with Image.open(io.BytesIO(data)) as image:
        assert image.width == 1000 and 300 <= image.height <= 800
