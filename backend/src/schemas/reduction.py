from typing import Literal
from pydantic import BaseModel,Field
class ReductionInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    dataset_id:int=Field(gt=0)
    config_id:int=Field(gt=0)
    fault:Literal['drop_tombstones_in_tiered','keep_stale_version_in_tiered','read_oldest_version','drop_latest_in_final_compaction']
    budget:int=Field(default=2000,ge=1,le=200000)
class ReductionExtend(BaseModel):
    # Additional replays granted to a reduction that ran out of budget.
    amount:int=Field(ge=1,le=200000)
