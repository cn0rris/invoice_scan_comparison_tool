from typing import Optional

from pydantic import BaseModel


class StartRunRequest(BaseModel):
    models: list[str]
    prompt: str
    invoice_dir: Optional[str] = None
    ground_truth_dir: Optional[str] = None
    force: bool = False


class StartRunResponse(BaseModel):
    run_id: str
