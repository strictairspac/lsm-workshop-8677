from datetime import datetime
from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,JSON,ForeignKey,DateTime,func
from ..config.database import Base
from ..constants.enums import REDUCTION_STATUSES
class Reduction(Base):
    __tablename__='reductions'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(120),unique=True)
    dataset_id:Mapped[int]=mapped_column(ForeignKey('datasets.id'))
    config_id:Mapped[int]=mapped_column(ForeignKey('configs.id'))
    fault:Mapped[str]=mapped_column(String(60))
    budget:Mapped[int]=mapped_column(default=2000)
    status:Mapped[str]=mapped_column(String(20),default=REDUCTION_STATUSES[0])
    input_snapshot:Mapped[dict]=mapped_column(JSON)
    target:Mapped[dict]=mapped_column(JSON)
    search_state:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
