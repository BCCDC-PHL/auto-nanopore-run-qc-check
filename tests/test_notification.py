import pytest

from auto_nanopore_run_qc_check.notification import _format_thousands, _prepare_email_body
from auto_nanopore_run_qc_check.samplesheet import count_samples_by_project_id


@pytest.mark.parametrize('value, expected', [
    (1297871, '1,297,871'),
    (82.753, '82.753'),
    (236267.27, '236,267.27'),
    (None, None),
    ('PASS', 'PASS'),
])
def test_format_thousands(value, expected):
    assert _format_thousands(value) == expected


def test_email_body_formats_numbers():
    email_data = {
        'sequencing_run_id': 'run1',
        'overall_pass_fail': 'PASS',
        'checked_metrics': [{'metric': 'NumReadsPassed', 'value': 1297871, 'threshold': 100000, 'pass_fail': 'PASS'}],
        'num_samples_by_project_id': {},
    }
    body = _prepare_email_body(email_data, {'sender_email': 'a@example.org', 'recipient_email_addresses': []})['email']['body']

    assert '1,297,871' in body
    assert '100,000' in body


@pytest.mark.parametrize('minknow_report_path, expect_warning', [
    ('/runs/run1/report_run1.json', False),
    (None, True),
])
def test_email_body_warns_if_no_minknow_report(minknow_report_path, expect_warning):
    email_data = {
        'sequencing_run_id': 'run1',
        'overall_pass_fail': 'UNDETERMINED',
        'checked_metrics': [],
        'num_samples_by_project_id': {},
        'minknow_report_path': minknow_report_path,
    }
    body = _prepare_email_body(email_data, {'sender_email': 'a@example.org', 'recipient_email_addresses': []})['email']['body']

    assert ('No MinKNOW report' in body) == expect_warning


def test_count_samples_by_project_id(tmp_path):
    samplesheet_path = tmp_path / 'sample_sheet.csv'
    samplesheet_path.write_text('barcode,alias\nbarcode01,S1_proj_a\nbarcode02,S2_proj_a\nbarcode03,S3_projb\n')

    assert count_samples_by_project_id(samplesheet_path) == {'proj_a': 2, 'projb': 1}
