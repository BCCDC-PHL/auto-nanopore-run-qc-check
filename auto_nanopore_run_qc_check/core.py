import datetime
import glob
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid

from typing import Iterator, Optional
from pathlib import Path

import auto_nanopore_run_qc_check.parsers as parsers
import auto_nanopore_run_qc_check.instrument as instrument

from auto_nanopore_run_qc_check.model import Config
from auto_nanopore_run_qc_check.notification import send_notification_email

log = logging.getLogger(__name__)


def find_run_dirs(config: Config, check_upload_complete: bool=True) -> Iterator[Optional[dict]]:
    """
    Find sequencing run directories under the 'run_parent_dirs' listed in the config.

    :param config: Application config.
    :param check_upload_complete: Check for presence of 'upload_complete.json' file.
    :return: Run directory, or None. Keys: ['sequencing_run_id', 'path', 'instrument_type']
    """

    for run_parent_dir in config.run_parent_dirs:
        subdirs = os.scandir(run_parent_dir)

        for subdir in subdirs:
            run_id = subdir.name
            instrument_type = instrument.determine_instrument_type(run_id)  
                    
            upload_complete = os.path.exists(os.path.join(subdir, 'upload_complete.json'))
            not_excluded = False
            not_excluded = run_id not in config.excluded_runs

            qc_check_complete = os.path.exists(os.path.join(subdir, 'qc_check_complete.json'))

            conditions_checked = {
                "is_directory": subdir.is_dir(),
                "supported_run_id_format": instrument_type != "unknown",
                "upload_complete": upload_complete,
                "qc_check_not_complete": not qc_check_complete,
                "not_excluded": not_excluded,
            }
            log.debug({"run_id": run_id, "conditions_checked": conditions_checked})

            conditions_met = list(conditions_checked.values())
            run = {}
            if all(conditions_met):
                log.info({"event_type": "run_directory_found", "sequencing_run_id": run_id, "run_directory_path": os.path.abspath(subdir.path)})
                run['path'] = os.path.abspath(subdir.path)
                run['sequencing_run_id'] = run_id
                run['instrument_type'] = instrument_type
                yield run
            else:
                log.debug({"event_type": "directory_skipped", "run_directory_path": os.path.abspath(subdir.path), "conditions_checked": conditions_checked})
                yield None


def get_sum_sample_fastq_file_sizes(run: dict) -> float:
    """
    Get the sum of all sample fastq file sizes in the run directory.

    :param run: Run directory. Keys: ['sequencing_run_id', 'path', 'instrument_type']
    :return: Sum of all sample fastq file sizes in the run directory.
    """
    sum_sample_fastq_file_sizes = 0.0
    fastq_path = os.path.join(run['path'], 'fastq_pass')

    if not os.path.exists(fastq_path):
        log.error({"event_type": "no_fastq_paths_found", "sequencing_run_id": run['sequencing_run_id']})
        return sum_sample_fastq_file_sizes

    fastq_files_glob = os.path.join(fastq_path, '*', '*.f*q.gz')
    fastq_files = glob.glob(fastq_files_glob)

    for fastq_file in fastq_files:
        file_basename = os.path.basename(fastq_file)
        library_id = file_basename.split('_')[2]
        if not library_id.startswith('barcode'):
            file_size_mb = os.path.getsize(fastq_file) / (1024 * 1024)
            sum_sample_fastq_file_sizes += file_size_mb

    return sum_sample_fastq_file_sizes
    

def scan(config: Config) -> Iterator[Optional[dict]]:
    """
    Scanning involves looking for all existing runs and storing them to the database,
    then looking for all existing symlinks and storing them to the database.
    At the end of a scan, we should be able to determine which (if any) symlinks need to be created.

    :param config: Application config.
    :return: A run directory to analyze, or None
    """
    log.info({"event_type": "scan_start"})
    for run_dir in find_run_dirs(config):    
        yield run_dir

def collect_qc_metrics(run: dict):
    """
    """
    run_dir = run.get('path')
    run_id = os.path.basename(run_dir)
    minknow_report_json_path = None
    minknow_report_json_glob = os.path.join(str(run_dir), 'report_*.json')
    minknow_reports = glob.glob(minknow_report_json_glob)
    if len(minknow_reports) == 1:
        minknow_report_json_path = minknow_reports[0]
        log.info({"event_type": "found_minknow_report", "sequencing_run_id": run_id, "minknow_report_path": minknow_report_json_path})
    else:
        log.error({"event_type": "failed_to_find_minknow_report", "sequencing_run_id": run_id})
        return None
    minknow_report = parsers.parse_minknow_report(minknow_report_json_path, run_id)

    qc_metrics = {
        'NumAcquisitions': minknow_report.get('num_acquisitions'),
        'NumSequencingAcquisitions': minknow_report.get('num_sequencing_acquisitions'),
        'PercentReadsPassed': minknow_report.get('percent_passed_reads'),
        'NumReadsPassed': minknow_report.get('total_passed_reads'),
        'EstimatedReadN50': minknow_report.get('estimated_read_n50'),
    }

    return qc_metrics


def qc_check(config: Config, run: dict) -> Optional[dict]:
    """
    Initiate an analysis on one directory of fastq files.

    :param config: Application config.
    :param run: Run directory. Keys: ['sequencing_run_id', 'path', 'instrument_type']
    :return: The QC check results
    """
    run_id = run['sequencing_run_id']
    run_dir = Path(run['path'])

    log.info({"event_type": "qc_check_started", "sequencing_run_id": run_id})
    timestamp_qc_check_started = datetime.datetime.now().isoformat()
    timestamp_qc_check_completed = None

    qc_check_complete = False

    qc_check_result = None
    qc_metrics = collect_qc_metrics(run)
    sum_sample_fastq_file_sizes = get_sum_sample_fastq_file_sizes(run)
    qc_metrics['SumSampleFastqFileSizesMb'] = round(sum_sample_fastq_file_sizes, 2)
    qc_metrics_output_path = os.path.join(run['path'], run_id + '_qc_metrics.json')
    with open(qc_metrics_output_path, 'w') as f:
        json.dump(qc_metrics, f, indent=2)
        f.write("\n")
    qc_check_result = {}
    qc_check_result['checked_metrics'] = []
    for qc_threshold in config.qc_thresholds:
        instrument_type_matches = qc_threshold.get('instrument_type', '').lower() == run['instrument_type']
        instrument_type_not_specified = 'instrument_type' not in qc_threshold
        qc_threshold_application_conditions_met = [
            (instrument_type_matches or instrument_type_not_specified)
        ]
        if all(qc_threshold_application_conditions_met):
            metric = qc_threshold['metric']
            threshold = qc_threshold['threshold']
            checked_metric = {}
            checked_metric['metric'] = metric
            checked_metric['threshold'] = threshold
            checked_metric['pass_above_or_below'] = qc_threshold['pass_above_or_below']
            checked_metric['value'] = qc_metrics.get(metric)

            if not checked_metric.get('value'):
                log.error({'event_type': 'failed_to_compare_metric_value',
                           'sequencing_run_id': run_id,
                           'metric': metric})
                checked_metric['pass_fail'] = "UNDETERMINED"
                qc_check_result['checked_metrics'].append(checked_metric)
                continue

            if qc_threshold['pass_above_or_below'] == 'above':
                if qc_metrics[metric] >= threshold:
                    checked_metric['pass_fail'] = "PASS"
                else:
                    checked_metric['pass_fail'] = "FAIL"
            elif qc_threshold['pass_above_or_below'] == 'below':
                if qc_metrics[metric] <= threshold:
                    checked_metric['pass_fail'] = "PASS"
                else:
                    checked_metric['pass_fail'] = "FAIL"
            qc_check_result['checked_metrics'].append(checked_metric)

    qc_check_result['overall_pass_fail'] = "UNDETERMINED"
    qc_pass_conditions_met = [m['pass_fail'] == "PASS" for m in qc_check_result['checked_metrics']]

    if all(qc_pass_conditions_met):
        qc_check_result['overall_pass_fail'] = "PASS"

    for result in qc_check_result['checked_metrics']:
        if result.get('pass_fail', '') == "FAIL":
            qc_check_result['overall_pass_fail'] = "FAIL"

    timestamp_qc_check_completed = datetime.datetime.now().isoformat()

    qc_check_result['sequencing_run_id'] = run_id
    qc_check_result['instrument_type'] = run['instrument_type']
    qc_check_result['timestamp_qc_check_started'] = timestamp_qc_check_started
    qc_check_result['timestamp_qc_check_completed'] = timestamp_qc_check_completed
    qc_check_complete_output_path = os.path.join(run['path'], 'qc_check_complete.json')
    with open(qc_check_complete_output_path, 'w') as f:
        json.dump(qc_check_result, f, indent=2)
        f.write("\n")
    log.info({"event_type": "qc_check_complete",
              "sequencing_run_id": run_id,
              "qc_check_result": qc_check_result['overall_pass_fail']})

    notification_emails_enabled = config.notification.get('send_notification_emails', False)
    if  notification_emails_enabled:
        try:
            send_notification_email(run_dir, config.notification)
            log.info({"event_type": "send_notification_email_complete", "sequencing_run_id": run_id, "qc_check_result": qc_check_result.get('overall_pass_fail', "Unknown")})
        except Exception as e:
            log.error({"event_type": "send_notification_email_failed", "sequencing_run_id": run_id, "exception": str(e)})

    return qc_check_result
