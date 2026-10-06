import json
import os

import pytest

import auto_nanopore_run_qc_check.core as core
from auto_nanopore_run_qc_check.model import Config, InstrumentType, PassFail, QcThreshold, Run

from conftest import make_acquisition

GRIDION_RUN_ID = '20260917_1024_X3_FBG77589_28704607'


@pytest.mark.parametrize('pass_above_or_below, value, expected', [
    ('above', 10, PassFail.PASS),
    ('above', 9, PassFail.FAIL),
    ('below', 10, PassFail.PASS),
    ('below', 11, PassFail.FAIL),
    ('above', 0, PassFail.FAIL),
    ('above', None, PassFail.UNDETERMINED),
])
def test_threshold_check(pass_above_or_below, value, expected):
    threshold = QcThreshold(metric='X', threshold=10, pass_above_or_below=pass_above_or_below)
    assert threshold.check(value) == expected


def test_threshold_rejects_invalid_direction():
    with pytest.raises(ValueError):
        QcThreshold(metric='X', threshold=10, pass_above_or_below='abvoe')


def test_threshold_applies_to_instrument_type():
    threshold = QcThreshold(metric='X', threshold=10, pass_above_or_below='above', instrument_type='GridION')
    assert threshold.applies_to(InstrumentType.gridion)
    assert not threshold.applies_to(InstrumentType.promethion)


@pytest.mark.parametrize('results, expected', [
    ([PassFail.PASS, PassFail.PASS], PassFail.PASS),
    ([PassFail.PASS, PassFail.FAIL], PassFail.FAIL),
    ([PassFail.UNDETERMINED, PassFail.FAIL], PassFail.FAIL),
    ([PassFail.PASS, PassFail.UNDETERMINED], PassFail.UNDETERMINED),
    ([], PassFail.UNDETERMINED),
])
def test_overall_pass_fail(results, expected):
    assert core.overall_pass_fail([{'pass_fail': r} for r in results]) == expected


def make_run_dir(parent, run_id=GRIDION_RUN_ID, upload_complete=True):
    run_dir = parent / run_id
    run_dir.mkdir()
    if upload_complete:
        (run_dir / 'upload_complete.json').write_text('{}')
    return run_dir


def test_find_run_dirs(tmp_path):
    make_run_dir(tmp_path)
    make_run_dir(tmp_path, run_id='20260918_1024_X3_FBG77589_28704608', upload_complete=False)
    make_run_dir(tmp_path, run_id='not_a_run')
    config = Config(run_parent_dirs=[tmp_path, tmp_path / 'missing'])

    runs = list(core.find_run_dirs(config))

    assert [r.sequencing_run_id for r in runs] == [GRIDION_RUN_ID]
    assert runs[0].instrument_type == InstrumentType.gridion


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read files regardless of permissions")
@pytest.mark.parametrize('unreadable_filename', ['upload_complete.json', 'report_FBG00000_20260101_0000_00000000.json'])
def test_find_run_dirs_skips_unreadable_runs(tmp_path, unreadable_filename):
    run_dir = make_run_dir(tmp_path)
    (run_dir / 'report_FBG00000_20260101_0000_00000000.json').write_text('{}')
    config = Config(run_parent_dirs=[tmp_path])

    (run_dir / unreadable_filename).chmod(0o000)
    try:
        assert list(core.find_run_dirs(config)) == []
    finally:
        (run_dir / unreadable_filename).chmod(0o644)

    assert [r.sequencing_run_id for r in core.find_run_dirs(config)] == [GRIDION_RUN_ID]


def test_qc_check(tmp_path, write_report):
    run_dir = make_run_dir(tmp_path)
    write_report([make_acquisition(pass_reads=900, fail_reads=100, basecalled_histogram=[(0, 10000, 1000)])], run_dir=run_dir)
    config = Config(qc_thresholds=[
        {'metric': 'PercentReadsPassed', 'threshold': 70, 'pass_above_or_below': 'above'},
        {'metric': 'ReadN50', 'threshold': 4000, 'pass_above_or_below': 'above'},
        {'metric': 'NumReadsPassed', 'threshold': 500000, 'pass_above_or_below': 'above', 'instrument_type': 'promethion'},
    ])
    run = Run(sequencing_run_id=GRIDION_RUN_ID, path=run_dir, instrument_type=InstrumentType.gridion)

    result = core.qc_check(config, run)

    assert result['overall_pass_fail'] == PassFail.PASS
    assert [m['metric'] for m in result['checked_metrics']] == ['PercentReadsPassed', 'ReadN50']
    with open(run_dir / 'qc_check_complete.json') as f:
        assert json.load(f)['overall_pass_fail'] == 'PASS'


def test_qc_check_without_report_is_undetermined(tmp_path):
    run_dir = make_run_dir(tmp_path)
    config = Config(qc_thresholds=[
        {'metric': 'ReadN50', 'threshold': 4000, 'pass_above_or_below': 'above'},
    ])
    run = Run(sequencing_run_id=GRIDION_RUN_ID, path=run_dir, instrument_type=InstrumentType.gridion)

    result = core.qc_check(config, run)

    assert result['overall_pass_fail'] == PassFail.UNDETERMINED
    assert result['minknow_report_path'] is None
    assert (run_dir / 'qc_check_complete.json').exists()


def test_qc_check_with_multiple_reports_raises(tmp_path):
    run_dir = make_run_dir(tmp_path)
    (run_dir / 'report_a.json').write_text('{}')
    (run_dir / 'report_b.json').write_text('{}')
    run = Run(sequencing_run_id=GRIDION_RUN_ID, path=run_dir, instrument_type=InstrumentType.gridion)

    with pytest.raises(ValueError):
        core.qc_check(Config(), run)
    assert not (run_dir / 'qc_check_complete.json').exists()
