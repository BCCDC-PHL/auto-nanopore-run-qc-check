import collections
import csv

from pathlib import Path
from typing import Optional


def find_samplesheet_path(run_dir: Path) -> Optional[Path]:
    """
    Given a run directory path, find the path to the sample sheet that can be used
    to summarize num samples by project ID.

    :param run_dir: Path to the run directory
    :return: Path to the sample sheet, or None if not found. If there are several, the last one (by name) is used.
    """
    samplesheets_found = sorted(run_dir.glob('sample_sheet_*.csv'))
    if not samplesheets_found:
        return None

    return samplesheets_found[-1].resolve()


def count_samples_by_project_id(samplesheet_path: Path) -> dict[str, int]:
    """
    Count the samples on a MinKNOW sample sheet, by project ID.
    Sample aliases are expected to be in the format '{sample_id}_{project_id}'.

    :param samplesheet_path: Path to the sample sheet
    :return: Number of samples, by project ID
    """
    with open(samplesheet_path, 'r') as f:
        aliases = [row['alias'] for row in csv.DictReader(f)]

    project_ids = [alias.split('_', 1)[1] for alias in aliases]

    return dict(collections.Counter(project_ids))
