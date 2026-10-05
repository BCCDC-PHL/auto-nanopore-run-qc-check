import argparse
import collections
import logging
import math
import os
import sys
import re
import json

from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def get_read_length_histogram_buckets(acquisition: dict, read_length_type: str, include_outliers: bool=False) -> list[tuple[int, int, int]]:
    """
    Get the buckets of one of the read length histograms from a MinKNOW report acquisition.

    The histograms are weighted by bases (not by read count): each bucket value is the
    total number of bases in reads whose length falls in that bucket.

    :param acquisition: A single acquisition from the 'acquisitions' list of a MinKNOW report.
    :param read_length_type: One of 'BasecalledBases' (pass reads only) or 'EstimatedBases'.
    :param include_outliers: Include the long-read outlier buckets, beyond the plotted range.
    :return: List of buckets, as (start, end, num_bases) tuples.
    """
    buckets = []
    for histogram in acquisition.get('read_length_histogram', []):
        if histogram.get('plot', {}).get('read_length_type') != read_length_type:
            continue
        parts = [histogram.get('plot', {})]
        if include_outliers:
            parts.append(histogram.get('outliers', {}))
        for part in parts:
            bucket_ranges = part.get('bucket_ranges', [])
            for histogram_data in part.get('histogram_data', []):
                for bucket_range, bucket_value in zip(bucket_ranges, histogram_data.get('bucket_values', [])):
                    buckets.append((int(bucket_range.get('start', 0)), int(bucket_range['end']), int(bucket_value)))

    return buckets


def calculate_n50_from_histogram(buckets: list[tuple[int, int, int]]) -> Optional[float]:
    """
    Calculate N50 from base-weighted read length histogram buckets.

    Bases are assumed to be evenly distributed within each bucket. Buckets may
    come from several histograms whose bucket boundaries don't line up
    (eg. from multiple acquisitions), so the N50 is found by bisection on the
    number of bases in reads at least as long as a candidate length.

    :param buckets: List of buckets, as (start, end, num_bases) tuples.
    :return: N50, or None if the histogram is empty.
    """
    buckets = [b for b in buckets if b[2] > 0 and b[1] > b[0]]
    total_bases = sum(b[2] for b in buckets)
    if total_bases == 0:
        return None
    half_total_bases = total_bases / 2

    def bases_in_reads_at_least(length: float) -> float:
        bases = 0.0
        for start, end, num_bases in buckets:
            if length <= start:
                bases += num_bases
            elif length < end:
                bases += num_bases * (end - length) / (end - start)
        return bases

    low = min(b[0] for b in buckets)
    high = max(b[1] for b in buckets)
    while high - low > 0.5:
        mid = (low + high) / 2
        if bases_in_reads_at_least(mid) >= half_total_bases:
            low = mid
        else:
            high = mid

    return low


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
        report = json.load(f)

    acquisitions = report.get('acquisitions', [])
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
            
        except (ValueError, TypeError) as e:
            log.error({'event_type': 'failed_to_collect_acquisition_read_count',
                       'sequencing_run_id': run_id,
                       'acquisition_run_id': acquisition_run_id})
            continue

    if total_basecalled_read_count > 0:
        percent_basecalled_reads_passed = total_basecalled_pass_read_count / total_basecalled_read_count * 100.0

    # MinKNOW reports an N50 for each acquisition, but N50s can't be combined
    # across acquisitions. The read length histograms they're derived from can be,
    # since they're base-weighted. Prefer basecalled (pass reads) lengths, and fall
    # back to estimated lengths for runs without live basecalling.
    read_n50 = None
    read_n50_type = None
    for read_length_type in ['BasecalledBases', 'EstimatedBases']:
        read_length_buckets = []
        for acquisition in sequencing_acquisitions:
            read_length_buckets += get_read_length_histogram_buckets(acquisition, read_length_type)
        read_n50 = calculate_n50_from_histogram(read_length_buckets)
        if read_n50 is not None:
            read_n50_type = read_length_type
            break
    if read_n50 is None:
        log.error({'event_type': 'failed_to_calculate_read_n50',
                   'sequencing_run_id': run_id})

    minknow_report['num_acquisitions'] = num_acquisitions
    minknow_report['num_sequencing_acquisitions'] = num_sequencing_acquisitions
    minknow_report['total_reads'] = total_basecalled_read_count
    minknow_report['total_passed_reads'] = total_basecalled_pass_read_count
    if percent_basecalled_reads_passed is not None:
        minknow_report['percent_passed_reads'] = round(percent_basecalled_reads_passed, 3)
    if read_n50 is not None:
        minknow_report['read_n50'] = round(read_n50)
        minknow_report['read_n50_type'] = read_n50_type
    
    return minknow_report
