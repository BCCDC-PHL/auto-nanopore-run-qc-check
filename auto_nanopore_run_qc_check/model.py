from dataclasses import dataclass, field, fields
from enum import StrEnum
from pathlib import Path
from typing import Optional


class InstrumentType(StrEnum):
    """
    Instrument type ('gridion', 'promethion' or 'unknown')
    """
    gridion   = "gridion"
    promethion = "promethion"
    unknown = "unknown"


class PassFail(StrEnum):
    """
    Result of a QC check, either for a single metric or for the overall run.
    """
    PASS = "PASS"
    FAIL = "FAIL"
    UNDETERMINED = "UNDETERMINED"


@dataclass
class QcThreshold:
    """
    A threshold that a single QC metric is checked against.
    If `instrument_type` is set, the threshold only applies to runs from that instrument type.
    """
    metric: str
    threshold: float
    pass_above_or_below: str
    instrument_type: Optional[InstrumentType] = None

    def __post_init__(self):
        if self.pass_above_or_below not in ('above', 'below'):
            raise ValueError(f"Invalid pass_above_or_below for metric {self.metric}: {self.pass_above_or_below!r} (expected 'above' or 'below')")
        if self.instrument_type is not None:
            self.instrument_type = InstrumentType(self.instrument_type.lower())

    def applies_to(self, instrument_type: InstrumentType) -> bool:
        return self.instrument_type is None or self.instrument_type == instrument_type

    def check(self, value: Optional[float]) -> PassFail:
        if value is None:
            return PassFail.UNDETERMINED
        if self.pass_above_or_below == 'above':
            passed = value >= self.threshold
        else:
            passed = value <= self.threshold

        return PassFail.PASS if passed else PassFail.FAIL


@dataclass
class Config:
    """
    Main application config.
    """
    scan_interval_seconds: float = 3600
    notification: dict = field(default_factory=dict)
    qc_thresholds: list[QcThreshold] = field(default_factory=list)
    run_parent_dirs: list[Path] = field(default_factory=list)
    excluded_runs_list: Optional[Path] = None
    excluded_runs: list[str] = field(default_factory=list)
    projects_definition_file: Optional[Path] = None
    projects: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.scan_interval_seconds = float(self.scan_interval_seconds)
        self.run_parent_dirs = [Path(p) for p in self.run_parent_dirs]
        self.qc_thresholds = [t if isinstance(t, QcThreshold) else QcThreshold(**t) for t in self.qc_thresholds]

    @classmethod
    def from_dict(cls, data: dict):
        # Get all valid field names for this dataclass
        valid_fields = {f.name for f in fields(cls)}
        # Filter the input dictionary
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


@dataclass
class Run:
    """
    A sequencing run directory that is ready to be QC checked.
    """
    sequencing_run_id: str
    path: Path
    instrument_type: InstrumentType
