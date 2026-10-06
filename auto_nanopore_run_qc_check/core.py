import datetime
import json
import logging
import os

from typing import Iterator, Optional
from pathlib import Path

import auto_nanopore_run_qc_check.parsers as parsers
import auto_nanopore_run_qc_check.instrument as instrument

from auto_nanopore_run_qc_check.model import Config, InstrumentType, PassFail, Run
from auto_nanopore_run_qc_check.notification import send_notification_email

log = logging.getLogger(__name__)


def is_readable(run_dir: Path) -> bool:
    """
    Check whether the files needed for the QC check are readable.
    Newly-uploaded runs are only readable by the uploading user until permissions are updated,
    and the run directory may be readable before the files inside it are.

    :param run_dir: Path to the run directory.
    :return: True if the run directory, 'upload_complete.json' and MinKNOW report (if present) are all readable.
    """
    if not os.access(run_dir, os.R_OK | os.X_OK):
        return False
    paths = [run_dir / 'upload_complete.json', *run_dir.glob('report_*.json')]

    return all(os.access(path, os.R_OK) for path in paths)


def find_run_dirs(config: Config) -> Iterator[Run]:
    """
    Find sequencing run directories under the 'run_parent_dirs' listed in the config
    that are ready to be QC checked.

    :param config: Application config.
    :return: Runs that are ready to be QC checked.
    """
    for run_parent_dir in config.run_parent_dirs:
        try:
            subdirs = list(os.scandir(run_parent_dir))
        except OSError as e:
            # Parent dirs may be on network storage that's temporarily unavailable.
            # Skip it for this scan, and try again on the next one.
            log.error({"event_type": "failed_to_scan_run_parent_dir", "run_parent_dir": str(run_parent_dir), "error": str(e)})
            continue

        for subdir in subdirs:
            run_id = subdir.name
            run_dir = Path(subdir.path).resolve()
            instrument_type = instrument.determine_instrument_type(run_id)

            conditions_checked = {
                "is_directory": subdir.is_dir(),
                "supported_run_id_format": instrument_type != InstrumentType.unknown,
                "upload_complete": (run_dir / 'upload_complete.json').exists(),
                "readable": is_readable(run_dir),
                "qc_check_not_complete": not (run_dir / 'qc_check_complete.json').exists(),
                "not_excluded": run_id not in config.excluded_runs,
            }

            if all(conditions_checked.values()):
                log.info({"event_type": "run_directory_found", "sequencing_run_id": run_id, "run_directory_path": str(run_dir)})
                yield Run(sequencing_run_id=run_id, path=run_dir, instrument_type=instrument_type)
            else:
                log.debug({"event_type": "directory_skipped", "run_directory_path": str(run_dir), "conditions_checked": conditions_checked})


def scan(config: Config) -> Iterator[Run]:
    """
    Scan the run parent dirs for runs that are ready to be QC checked.

    :param config: Application config.
    :return: Runs that are ready to be QC checked.
    """
    log.info({"event_type": "scan_start"})
    yield from find_run_dirs(config)


def get_sum_sample_fastq_file_sizes_mb(run: Run) -> float:
    """
    Get the sum of all sample fastq file sizes in the run directory.
    Files for barcodes without a sample alias assigned (eg. 'barcode01') aren't counted.

    :param run: The sequencing run.
    :return: Sum of all sample fastq file sizes in the run directory, in megabytes.
    """
    fastq_path = run.path / 'fastq_pass'
    if not fastq_path.exists():
        log.warning({"event_type": "no_fastq_paths_found", "sequencing_run_id": run.sequencing_run_id})
        return 0.0

    # Fastq files are written to 'fastq_pass/{alias}/'
    sum_bytes = sum(
        fastq_file.stat().st_size
        for fastq_file in fastq_path.glob('*/*.f*q.gz')
        if not fastq_file.parent.name.startswith('barcode')
    )

    return sum_bytes / (1024 * 1024)


def find_minknow_report(run: Run) -> Optional[Path]:
    """
    Find the MinKNOW json report in a run directory.

    :param run: The sequencing run.
    :return: Path to the report, or None if there isn't one (eg. if the run was interrupted).
    :raises ValueError: If there is more than one report in the run directory.
    """
    minknow_reports = list(run.path.glob('report_*.json'))
    if len(minknow_reports) > 1:
        raise ValueError(f"Expected at most one MinKNOW report (report_*.json) in {run.path}, found {len(minknow_reports)}")

    return minknow_reports[0] if minknow_reports else None


def collect_qc_metrics(run: Run, minknow_report_path: Optional[Path]) -> dict:
    """
    Collect the QC metrics for a run.
    Without a MinKNOW report, the metrics that come from the report are None.

    :param run: The sequencing run.
    :param minknow_report_path: Path to the MinKNOW report, or None if there isn't one.
    :return: QC metrics, by metric name.
    """
    minknow_report = {}
    if minknow_report_path is not None:
        minknow_report = parsers.parse_minknow_report(minknow_report_path)

    return {
        'NumAcquisitions': minknow_report.get('num_acquisitions'),
        'NumSequencingAcquisitions': minknow_report.get('num_sequencing_acquisitions'),
        'PercentReadsPassed': minknow_report.get('percent_passed_reads'),
        'NumReadsPassed': minknow_report.get('total_passed_reads'),
        'ReadN50': minknow_report.get('read_n50'),
        'SumSampleFastqFileSizesMb': round(get_sum_sample_fastq_file_sizes_mb(run), 2),
    }


def overall_pass_fail(checked_metrics: list[dict]) -> PassFail:
    """
    Combine the results of each checked metric into an overall result.
    Any failure fails the run. The run only passes if at least one metric was checked, and all passed.

    :param checked_metrics: Checked metrics. Required keys: ['pass_fail']
    :return: The overall result.
    """
    results = {m['pass_fail'] for m in checked_metrics}
    if PassFail.FAIL in results:
        return PassFail.FAIL
    if results == {PassFail.PASS}:
        return PassFail.PASS

    return PassFail.UNDETERMINED


def write_json(path: Path, data: dict):
    """
    Write a json file atomically, so other processes never see a partially-written file.

    :param path: Path to write to.
    :param data: Data to write.
    """
    tmp_path = path.with_name(path.name + '.tmp')
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)


def qc_check(config: Config, run: Run) -> dict:
    """
    Check the QC metrics for a run against the configured thresholds,
    and write the result to 'qc_check_complete.json' in the run directory.

    :param config: Application config.
    :param run: The sequencing run.
    :return: The QC check results
    """
    run_id = run.sequencing_run_id
    log.info({"event_type": "qc_check_started", "sequencing_run_id": run_id})
    timestamp_qc_check_started = datetime.datetime.now().isoformat()

    minknow_report_path = find_minknow_report(run)
    if minknow_report_path is None:
        # Interrupted runs can have usable fastq files but no report. Complete the QC check
        # anyway (metrics from the report will be UNDETERMINED) so that someone is notified.
        log.warning({"event_type": "minknow_report_not_found", "sequencing_run_id": run_id})
    else:
        log.info({"event_type": "found_minknow_report", "sequencing_run_id": run_id, "minknow_report_path": str(minknow_report_path)})

    qc_metrics = collect_qc_metrics(run, minknow_report_path)
    write_json(run.path / f"{run_id}_qc_metrics.json", qc_metrics)

    checked_metrics = []
    for qc_threshold in config.qc_thresholds:
        if not qc_threshold.applies_to(run.instrument_type):
            continue
        value = qc_metrics.get(qc_threshold.metric)
        pass_fail = qc_threshold.check(value)
        if pass_fail == PassFail.UNDETERMINED:
            log.error({'event_type': 'failed_to_compare_metric_value',
                       'sequencing_run_id': run_id,
                       'metric': qc_threshold.metric})
        checked_metrics.append({
            'metric': qc_threshold.metric,
            'threshold': qc_threshold.threshold,
            'pass_above_or_below': qc_threshold.pass_above_or_below,
            'value': value,
            'pass_fail': pass_fail,
        })

    qc_check_result = {
        'checked_metrics': checked_metrics,
        'overall_pass_fail': overall_pass_fail(checked_metrics),
        'sequencing_run_id': run_id,
        'instrument_type': run.instrument_type,
        'minknow_report_path': str(minknow_report_path) if minknow_report_path else None,
        'timestamp_qc_check_started': timestamp_qc_check_started,
        'timestamp_qc_check_completed': datetime.datetime.now().isoformat(),
    }
    write_json(run.path / 'qc_check_complete.json', qc_check_result)
    log.info({"event_type": "qc_check_complete",
              "sequencing_run_id": run_id,
              "qc_check_result": qc_check_result['overall_pass_fail']})

    if config.notification.get('send_notification_emails', False):
        # The QC check is already complete at this point, so a failure to send
        # the notification shouldn't cause the QC check to be repeated.
        try:
            send_notification_email(run.path, config.notification)
            log.info({"event_type": "send_notification_email_complete", "sequencing_run_id": run_id, "qc_check_result": qc_check_result['overall_pass_fail']})
        except Exception as e:
            log.error({"event_type": "send_notification_email_failed", "sequencing_run_id": run_id, "error": str(e)}, exc_info=True)

    return qc_check_result
