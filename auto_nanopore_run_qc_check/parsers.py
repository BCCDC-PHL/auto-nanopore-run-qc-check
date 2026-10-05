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
    minknow_report = {
        'num_acquisitions': None,
        'num_sequencing_acquisitions': None,
        'total_reads': None,
        'total_passed_reads': None,
        'percent_passed_reads': None,
        'read_n50': None,
        
    }
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
    total_basecalled_read_count = 0
    total_basecalled_pass_read_count = 0
    percent_basecalled_reads_passed = None
    for acquisition in sequencing_acquisitions:
        acquisition_run_id = acquisition.get('acquisition_run_info', {}).get('run_id')
        try:
            basecalled_pass_read_count = int(acquisition.get('acquisition_run_info', {}).get('yield_summary',{}).get('basecalled_pass_read_count'))
            basecalled_fail_read_count = int(acquisition.get('acquisition_run_info', {}).get('yield_summary',{}).get('basecalled_fail_read_count'))
            total_basecalled_read_count += basecalled_pass_read_count + basecalled_fail_read_count
            total_basecalled_pass_read_count += basecalled_pass_read_count
            
        except ValueError as e:
            log.error({'event_type': 'failed_to_collect_acquisition_read_count',
                       'sequencing_run_id': run_id,
                       'acquisition_run_id': acquisition_run_id})
            continue

    percent_basecalled_reads_passed = basecalled_pass_read_count / total_basecalled_read_count * 100.0
    minknow_report['num_acquisitions'] = num_acquisitions
    minknow_report['num_sequencing_acquisitions'] = num_sequencing_acquisitions
    minknow_report['total_reads'] = total_basecalled_read_count
    minknow_report['total_passed_reads'] = total_basecalled_pass_read_count
    minknow_report['percent_passed_reads'] = round(percent_basecalled_reads_passed, 3)
    
    return minknow_report
