import csv
import glob
import json
import logging
import os

from pathlib import Path

import auto_nanopore_run_qc_check.instrument as instrument
from auto_nanopore_run_qc_check.model import InstrumentType

from typing import Optional, Iterator

def find_samplesheet_path(run_dir: Path) -> Optional[Path]:
    """
    Given a run directory path, find the path to the SampleSheet.csv file that can be used
    to summarize num samples by project ID.
    
    :param run_dir: Path to the run directory
    :return: Path to the SampleSheet.csv file, or None if not found.
    """
    samplesheet_path = None
    run_id = run_dir.name
    instrument_type = instrument.determine_instrument_type(run_id)

    samplesheet_paths_glob = 'sample_sheet_*.csv'

    samplesheets_found = glob.glob(samplesheet_paths_glob)
    if len(samplesheets_found) == 0:
        return None
    last_samplesheet = samplesheets_found[-1]

    if os.path.exists(last_samplesheet):
        samplesheet_path = Path(os.path.abspath(last_samplesheet))

    return samplesheet_path


    
def parse_samplesheet(samplesheet_path: Path, instrument_type: InstrumentType) -> list[dict]:
    """
    Parse a SampleSheet, given the path to the SampleSheet file and the Instrument type.
    """
    parsed_samplesheet = []
    with open(samplesheet_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed_samplesheet.append(row)
    
    return parsed_samplesheet
