import json

from pathlib import Path
from typing import Optional


def get_read_length_histogram_buckets(acquisition: dict, read_length_type: str, include_outliers: bool=False) -> list[tuple[int, int, int]]:
    """
    Get the buckets of one of the read length histograms from a MinKNOW report acquisition.

    The histograms are weighted by bases (not by read count): each bucket value is the
    total number of bases in reads whose length falls in that bucket.

    :param acquisition: A single acquisition from the 'acquisitions' list of a MinKNOW report.
    :param read_length_type: One of 'BasecalledBases' (pass reads only) or 'EstimatedBases'.
    :param include_outliers: Include the long-read outlier buckets, beyond the plotted range.
    :return: List of buckets, as (start, end, num_bases) tuples. Empty if the acquisition has no histogram of that type.
    """
    buckets = []
    for histogram in acquisition.get('read_length_histogram', []):
        if histogram['plot'].get('read_length_type') != read_length_type:
            continue
        parts = [histogram['plot']]
        if include_outliers and 'outliers' in histogram:
            parts.append(histogram['outliers'])
        for part in parts:
            for histogram_data in part['histogram_data']:
                for bucket_range, bucket_value in zip(part['bucket_ranges'], histogram_data['bucket_values'], strict=True):
                    # The first bucket has no 'start' key; it starts at zero.
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


def parse_minknow_report(minknow_report_path: Path) -> dict:
    """
    Collect run-level QC metrics from a MinKNOW json report, combined across all sequencing acquisitions.

    Raises if a required field is missing from the report.

    :param minknow_report_path: Path to the MinKNOW report (report_*.json)
    :return: QC metrics. Keys: ['num_acquisitions', 'num_sequencing_acquisitions', 'total_reads',
             'total_passed_reads', 'percent_passed_reads', 'read_n50', 'read_n50_type']
    """
    with open(minknow_report_path, 'r') as f:
        report = json.load(f)

    acquisitions = report['acquisitions']
    sequencing_acquisitions = [
        a for a in acquisitions
        if a['acquisition_run_info']['config_summary']['purpose'] == 'SEQUENCING'
    ]

    total_passed_reads = 0
    total_reads = 0
    for acquisition in sequencing_acquisitions:
        yield_summary = acquisition['acquisition_run_info']['yield_summary']
        passed_reads = int(yield_summary['basecalled_pass_read_count'])
        total_passed_reads += passed_reads
        total_reads += passed_reads + int(yield_summary['basecalled_fail_read_count'])

    percent_passed_reads = None
    if total_reads > 0:
        percent_passed_reads = round(total_passed_reads / total_reads * 100.0, 3)

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
            read_n50 = round(read_n50)
            read_n50_type = read_length_type
            break

    return {
        'num_acquisitions': len(acquisitions),
        'num_sequencing_acquisitions': len(sequencing_acquisitions),
        'total_reads': total_reads,
        'total_passed_reads': total_passed_reads,
        'percent_passed_reads': percent_passed_reads,
        'read_n50': read_n50,
        'read_n50_type': read_n50_type,
    }
