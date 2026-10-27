"""
Pydantic Data Models for Ingest API Payload & Response Contract
Conforms strictly to schemas/telemetry_schema.json and docs/api_contract.md.
"""

from typing import List, Literal, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field, model_validator


class SummaryData(BaseModel):
    interval_seconds: float = Field(default=60.0, description="Sampling window duration in seconds")
    peak_acceleration_g: float = Field(..., description="Maximum absolute ground acceleration in g")
    rms_acceleration_g: float = Field(..., description="Root-Mean-Square acceleration in g")
    sample_count: int = Field(..., description="Total raw samples collected in the interval")
    temperature_c: Optional[float] = Field(default=None, description="Sensor operating temperature in Celsius")


class WaveformSample(BaseModel):
    t_offset_ms: int = Field(..., description="Millisecond offset from measured_at_start")
    x: Optional[float] = Field(default=0.0, description="Lateral X acceleration in g")
    y: Optional[float] = Field(default=0.0, description="Lateral Y acceleration in g")
    z: float = Field(..., description="Vertical Z acceleration in g")


class WaveformData(BaseModel):
    sampling_rate_hz: int = Field(default=1000, description="Sampling frequency in Hz")
    measured_at_start: str = Field(..., description="ISO 8601 start timestamp of the waveform window")
    samples: List[WaveformSample] = Field(..., min_length=1, description="Raw tri-axial acceleration samples")


class TelemetryBatch(BaseModel):
    device_id: str = Field(..., pattern=r"^node-[0-9]{3}$", description="Sensor node identifier (e.g. node-042)")
    batch_id: UUID = Field(default_factory=uuid4, description="Unique UUIDv4 per batch for idempotency")
    sector: Literal["A", "B", "C", "D", "E"] = Field(..., description="City sector identifier")
    sent_at: str = Field(..., description="ISO 8601 transmission timestamp")
    is_backfill: bool = Field(default=False, description="True if retransmitted backlog batch")
    payload_type: Literal["summary", "waveform"] = Field(..., description="Payload type: summary or waveform")
    summary: Optional[SummaryData] = Field(default=None, description="Present when payload_type == 'summary'")
    waveform: Optional[WaveformData] = Field(default=None, description="Present when payload_type == 'waveform'")

    @model_validator(mode="after")
    def validate_payload_matches_type(self):
        if self.payload_type == "summary":
            if self.summary is None:
                raise ValueError("Payload type 'summary' requires 'summary' data block")
            if self.waveform is not None:
                raise ValueError("Payload type 'summary' must not contain 'waveform' block")
        elif self.payload_type == "waveform":
            if self.waveform is None:
                raise ValueError("Payload type 'waveform' requires 'waveform' data block")
            if self.summary is not None:
                raise ValueError("Payload type 'waveform' must not contain 'summary' block")
        return self


class IngestAcceptedResponse(BaseModel):
    status: str = "accepted"
    batch_id: str
    queue: str
    received_at: str


class ErrorResponse(BaseModel):
    status: str = "error"
    code: str
    detail: str
