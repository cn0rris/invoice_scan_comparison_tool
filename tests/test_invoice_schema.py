import json
from pathlib import Path

import pytest

from app.models.invoice import InvoiceExtraction, generate_default_prompt

GT_DIR = Path(__file__).resolve().parent.parent / "data" / "ground_truth"


def test_default_prompt_mentions_every_field():
    prompt = generate_default_prompt()
    for name in InvoiceExtraction.model_fields:
        assert name in prompt, f"default prompt is missing field '{name}'"


@pytest.mark.parametrize("gt_file", sorted(GT_DIR.glob("*.json")))
def test_sample_ground_truth_validates(gt_file: Path):
    data = json.loads(gt_file.read_text())
    InvoiceExtraction.model_validate(data)
