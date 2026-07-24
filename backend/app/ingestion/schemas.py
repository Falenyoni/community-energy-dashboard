from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

# Must stay in sync with app.models.CONTROLLER_CHANNELS / SWITCHING_STATES
ControllerChannel = Literal["geyser", "fridge", "lighting", "plugs", "cooking", "background"]
SwitchingState = Literal["on", "off", "standby", "fault"]


class RawReading(BaseModel):
    """
    The canonical ingestion contract from DATA_SPECIFICATION.md — any source
    (simulated CSV, manual export, future API) must parse into this shape
    before anything downstream touches it.

    quality_flag is deliberately NOT accepted here even if a source CSV
    includes one: it's computed fresh by app.ingestion.validators, not
    trusted from the source. Pydantic's default extra='ignore' behavior
    means an incoming quality_flag column is simply dropped.
    """

    reading_id: str
    site_id: str
    device_id: str
    controller_channel: ControllerChannel
    timestamp: datetime
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    power_kw: Optional[float] = None
    energy_kwh_interval: Optional[float] = None
    cumulative_energy_kwh: Optional[float] = None
    switching_state: SwitchingState
