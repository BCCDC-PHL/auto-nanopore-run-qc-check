import json
import logging
import os
import time

from auto_nanopore_run_qc_check.logging_config import JSONFormatter, make_log_handler


def make_logger(handler):
    handler.setFormatter(JSONFormatter())
    logger = logging.getLogger('test_logging_config')
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger


def read_events(path):
    with open(path) as f:
        return [json.loads(line)['message']['event_type'] for line in f]


def test_log_file_is_appended_to_on_restart(tmp_path):
    log_file = tmp_path / 'qc-check.jsonl'
    for event_type in ['first_start', 'second_start']:
        handler = make_log_handler(log_file)
        make_logger(handler).info({'event_type': event_type})
        handler.close()

    assert read_events(log_file) == ['first_start', 'second_start']


def test_log_file_is_rotated_by_date(tmp_path):
    log_file = tmp_path / 'qc-check.jsonl'
    handler = make_log_handler(log_file, log_retention_days=2)
    logger = make_logger(handler)

    logger.info({'event_type': 'yesterday'})
    yesterday = time.time() - 24 * 60 * 60
    os.utime(log_file, (yesterday, yesterday))
    handler.rolloverAt = time.time() - 1
    logger.info({'event_type': 'today'})
    handler.close()

    rotated_log_file = tmp_path / f"qc-check.jsonl.{time.strftime('%Y-%m-%d', time.localtime(yesterday))}"
    assert read_events(rotated_log_file) == ['yesterday']
    assert read_events(log_file) == ['today']


def test_old_rotated_log_files_are_deleted(tmp_path):
    log_file = tmp_path / 'qc-check.jsonl'
    for day in ['2026-10-01', '2026-10-02', '2026-10-03']:
        (tmp_path / f'qc-check.jsonl.{day}').write_text('')
    handler = make_log_handler(log_file, log_retention_days=2)
    logger = make_logger(handler)

    logger.info({'event_type': 'before_rotation'})
    handler.rolloverAt = time.time() - 1
    logger.info({'event_type': 'after_rotation'})
    handler.close()

    rotated = sorted(p.name for p in tmp_path.glob('qc-check.jsonl.*'))
    assert len(rotated) == 2
    assert 'qc-check.jsonl.2026-10-01' not in rotated
