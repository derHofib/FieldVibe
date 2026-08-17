from pydantic import BaseModel


class SystemResourceSample(BaseModel):
    timestamp: str
    cpu_percent: float
    ram_percent: float
    ram_used_mb: int
    ram_total_mb: int
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float


class SystemResourcesRead(BaseModel):
    aktuell: SystemResourceSample
    verlauf: list[SystemResourceSample]
