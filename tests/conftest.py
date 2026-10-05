import json

import pytest


def make_acquisition(purpose='SEQUENCING', pass_reads=900, fail_reads=100, basecalled_histogram=None, estimated_histogram=None):
    """
    Build a minimal MinKNOW report acquisition.
    Histograms are given as lists of (start, end, num_bases) buckets.
    """
    acquisition = {
        'acquisition_run_info': {
            'run_id': 'abc123',
            'config_summary': {'purpose': purpose},
            'yield_summary': {
                'basecalled_pass_read_count': str(pass_reads),
                'basecalled_fail_read_count': str(fail_reads),
            },
        },
    }
    histograms = []
    for read_length_type, buckets in [('BasecalledBases', basecalled_histogram), ('EstimatedBases', estimated_histogram)]:
        if buckets is None:
            continue
        histograms.append({
            'bucket_value_type': 'ReadLengths',
            'read_length_type': read_length_type,
            'plot': {
                'read_length_type': read_length_type,
                'bucket_ranges': [{'start': str(s), 'end': str(e)} if s else {'end': str(e)} for s, e, _ in buckets],
                'histogram_data': [{'bucket_values': [str(v) for _, _, v in buckets]}],
            },
        })
    if histograms:
        acquisition['read_length_histogram'] = histograms

    return acquisition


@pytest.fixture
def write_report(tmp_path):
    def _write_report(acquisitions, run_dir=tmp_path):
        path = run_dir / 'report_FBG00000_20260101_0000_00000000.json'
        with open(path, 'w') as f:
            json.dump({'acquisitions': acquisitions}, f)
        return path

    return _write_report
