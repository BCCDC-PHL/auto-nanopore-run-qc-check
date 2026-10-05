import pytest

from auto_nanopore_run_qc_check.parsers import calculate_n50_from_histogram, parse_minknow_report

from conftest import make_acquisition


def test_n50_of_empty_histogram_is_none():
    assert calculate_n50_from_histogram([]) is None
    assert calculate_n50_from_histogram([(0, 1000, 0)]) is None


def test_n50_interpolates_within_bucket():
    # 1000 bases spread evenly over 0-1000, 1000 bases over 1000-2000.
    # Half of all bases are in reads >= 1000.
    n50 = calculate_n50_from_histogram([(0, 1000, 1000), (1000, 2000, 1000)])
    assert n50 == pytest.approx(1000, abs=1)


def test_n50_handles_misaligned_buckets():
    # Same distribution, split into differently-aligned buckets.
    buckets = [(0, 1000, 1000), (1000, 2000, 1000)]
    rebucketed = [(0, 500, 500), (500, 1500, 1000), (1500, 2000, 500)]
    assert calculate_n50_from_histogram(buckets + rebucketed) == pytest.approx(calculate_n50_from_histogram(buckets), abs=1)


def test_parse_report_combines_sequencing_acquisitions(write_report):
    report_path = write_report([
        make_acquisition(purpose='CALIBRATION', pass_reads=0, fail_reads=0),
        make_acquisition(pass_reads=800, fail_reads=200, basecalled_histogram=[(0, 1000, 1000)]),
        make_acquisition(pass_reads=100, fail_reads=900, basecalled_histogram=[(1000, 2000, 1000)]),
    ])
    report = parse_minknow_report(report_path)

    assert report['num_acquisitions'] == 3
    assert report['num_sequencing_acquisitions'] == 2
    assert report['total_reads'] == 2000
    assert report['total_passed_reads'] == 900
    assert report['percent_passed_reads'] == 45.0
    assert report['read_n50'] == pytest.approx(1000, abs=1)
    assert report['read_n50_type'] == 'BasecalledBases'


def test_parse_report_falls_back_to_estimated_n50(write_report):
    report_path = write_report([make_acquisition(estimated_histogram=[(0, 1000, 1000)])])
    report = parse_minknow_report(report_path)

    assert report['read_n50'] == pytest.approx(500, abs=1)
    assert report['read_n50_type'] == 'EstimatedBases'


def test_parse_report_without_reads_or_histograms(write_report):
    report = parse_minknow_report(write_report([make_acquisition(pass_reads=0, fail_reads=0)]))

    assert report['percent_passed_reads'] is None
    assert report['read_n50'] is None


def test_parse_report_missing_read_counts_raises(write_report):
    acquisition = make_acquisition()
    del acquisition['acquisition_run_info']['yield_summary']['basecalled_fail_read_count']

    with pytest.raises(KeyError):
        parse_minknow_report(write_report([acquisition]))
