import csv
import json
import logging
import os

from auto_nanopore_run_qc_check.model import Config

log = logging.getLogger(__name__)


def _load_optional_list_file(path: os.PathLike, setting: str) -> list[str]:
    """
    Load a file with one entry per line. A missing file is treated as an empty list.

    :param path: Path to the file.
    :param setting: Name of the config setting the path came from (for logging).
    :return: Non-blank lines of the file.
    """
    if not os.path.exists(path):
        log.warning({"event_type": "config_file_not_found", "setting": setting, "path": str(path)})
        return []

    with open(path, 'r') as f:
        return [line.strip() for line in f if line.strip()]


def load_config(config_path: os.PathLike) -> Config:
    """
    Load the application config file.

    Raises if the config file (or a file it depends on) can't be loaded or is invalid.

    :param config_path: Path to config file.
    :return: The application config.
    """
    with open(config_path, 'r') as f:
        config_dict = json.load(f)

    if 'excluded_runs_list' in config_dict:
        config_dict['excluded_runs'] = _load_optional_list_file(config_dict['excluded_runs_list'], 'excluded_runs_list')

    projects_definition_file = config_dict.get('projects_definition_file')
    if projects_definition_file and os.path.exists(projects_definition_file):
        with open(projects_definition_file, 'r') as f:
            config_dict['projects'] = list(csv.DictReader(f, dialect='unix'))

    # The notification system config holds credentials, so it's kept in a separate file.
    # It's only required if notification emails are enabled.
    notification = config_dict.get('notification', {})
    if notification.get('send_notification_emails', False):
        with open(notification['system_config_file'], 'r') as f:
            notification.update(json.load(f))

    return Config.from_dict(config_dict)
