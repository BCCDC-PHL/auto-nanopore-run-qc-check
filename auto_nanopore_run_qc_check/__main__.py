#!/usr/bin/env python

import argparse
import datetime
import logging
import os
import time

import auto_nanopore_run_qc_check.core as core
from auto_nanopore_run_qc_check.config import load_config
from auto_nanopore_run_qc_check.model import Config
from auto_nanopore_run_qc_check.logging_config import configure_logging

log = logging.getLogger(__name__)


def reload_config(config_path: os.PathLike, current_config: Config) -> Config:
    """
    Reload the config file, so that changes take effect without restarting.
    If the config can't be loaded, continue with the last valid config.

    :param config_path: Path to the config file.
    :param current_config: The last valid config.
    :return: The reloaded config, or the current config if reloading failed.
    """
    try:
        config = load_config(config_path)
        log.info({"event_type": "config_loaded", "config_file": os.path.abspath(config_path)})
        return config
    except Exception as e:
        log.error({"event_type": "load_config_failed", "config_file": os.path.abspath(config_path), "error": str(e)})
        return current_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True)
    parser.add_argument('--log-level', default='info', choices=['debug', 'info', 'warning', 'error'])
    args = parser.parse_args()

    configure_logging(args.log_level)
    log.debug({"event_type": "debug_logging_enabled"})

    # Fail fast if the config is invalid at startup.
    config = load_config(args.config)
    log.info({"event_type": "config_loaded", "config_file": os.path.abspath(args.config)})

    try:
        while True:
            scan_start_timestamp = datetime.datetime.now()
            for run in core.scan(config):
                config = reload_config(args.config, config)
                try:
                    core.qc_check(config, run)
                # A problem with one run shouldn't stop other runs from being checked.
                # No 'qc_check_complete.json' is written, so the run will be retried on the next scan.
                except OSError as e:
                    # Expected, environmental problems (missing files, permissions, network storage).
                    # The message says what went wrong, so a traceback wouldn't add anything.
                    log.error({"event_type": "qc_check_failed", "sequencing_run_id": run.sequencing_run_id,
                               "error_type": type(e).__name__, "error": str(e)})
                except Exception as e:
                    # Unexpected problems are probably bugs, so include the traceback.
                    log.error({"event_type": "qc_check_failed", "sequencing_run_id": run.sequencing_run_id,
                               "error_type": type(e).__name__, "error": str(e)}, exc_info=True)

            scan_duration_seconds = (datetime.datetime.now() - scan_start_timestamp).total_seconds()
            next_scan_timestamp = scan_start_timestamp + datetime.timedelta(seconds=config.scan_interval_seconds)
            log.info({
                "event_type": "scan_complete",
                "scan_duration_seconds": scan_duration_seconds,
                "scan_interval_seconds": config.scan_interval_seconds,
                "timestamp_next_scan_start": next_scan_timestamp.isoformat(),
            })
            time.sleep(max(0, (next_scan_timestamp - datetime.datetime.now()).total_seconds()))
            config = reload_config(args.config, config)
    except KeyboardInterrupt:
        log.info({"event_type": "quit"})


if __name__ == '__main__':
    main()
