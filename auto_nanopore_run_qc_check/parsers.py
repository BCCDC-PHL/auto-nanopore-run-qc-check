import argparse
import collections
import logging
import math
import os
import sys
import re
import json

from pathlib import Path

log = logging.getLogger(__name__)


def parse_minknow_report(minknow_report_path: Path, run_id: str):
    """
    """
    minknow_report = None
    with open(minknow_report_path, 'r') as f:
        minknow_report = json.load(f)

    acquisitions = minknow_report.get('acquisitions', [])
    num_acquisitions = len(acquisitions)
    acquisitions_by_purpose = {}
    for acquisition in acquisitions:
        acquisition_run_id = acquisition.get('acquisition_run_info', {}).get('run_id')
        acquisition_purpose = acquisition.get('acquisition_run_info', {}).get('config_summary', {}).get('purpose')
        if acquisition_purpose not in acquisitions_by_purpose:
            acquisitions_by_purpose[acquisition_purpose] = []
        acquisitions_by_purpose[acquisition_purpose].append(acquisition)

    sequencing_acquisitions = acquisitions_by_purpose.get('SEQUENCING', [])
    num_sequencing_acquisitions = len(sequencing_acquisitions)
    total_read_count = 0
    for acquisition in sequencing_acquisitions:
        acquisition_run_id = acquisition.get('acquisition_run_info', {}).get('run_id')
        read_count = acquisition.get('acquisition_run_info' {}).get('yield_summary',{}).get('read_count')
        if not read_count:
            log.error({'event_type': 'failed_to_collect_acquisition_read_count',
                       'sequencing_run_id': run_id,
                       'acquisition_run_id': acquisition_run_id})
        else:
            total_read_count += read_count

    minknow_report['total_sequencing_reads'] = total_read_count
    
    return minknow_report
