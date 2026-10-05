import argparse
import json
import logging
import os
import uuid

from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

from jinja2 import Environment, BaseLoader
from importlib.resources import files

from auto_nanopore_run_qc_check.config import load_config
from auto_nanopore_run_qc_check.logging_config import configure_logging

import auto_nanopore_run_qc_check.samplesheet as samplesheet

log = logging.getLogger(__name__)

# (connect, read) timeouts for requests to the notification API, in seconds.
REQUEST_TIMEOUT_SECONDS = (10, 60)


def _get_access_token(email_config: dict) -> str:
    """
    Get an access token from the MCMS auth service.

    :param email_config: A dict containing the MCMS auth service URL, client ID, and client secret.
                         Required keys are: ['auth_url', 'client_id', 'client_secret'].
    :return: The access token.
    :raises requests.HTTPError: If authentication fails.
    """
    client_id = email_config['client_id']
    auth = HTTPBasicAuth(client_id, email_config['client_secret'])
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "client_id": client_id,
        "grant_type": "client_credentials",
    }
    response = requests.post(email_config['auth_url'], data=data, headers=headers, auth=auth, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    return response.json()['access_token']


def _format_thousands(value):
    """
    Jinja filter to format numbers with thousands separators (eg. 1297871 -> '1,297,871').
    Non-numeric values (eg. None or strings) are returned unchanged.

    :param value: The value to format
    :return: The formatted value
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:,}"

    return value


def _prepare_email_body(email_data: dict, notification_config: dict) -> dict:
    """
    Prepare the email request body, prior to calling notification API.

    :param email_data: Data needed to render HTML template
    :param notification_config: Configuration for connecting to notification API. Required keys: ['sender_email', 'recipient_email_addresses']
    :return: The body for the POST request to the notification API.
    """
    sequencing_run_id = email_data['sequencing_run_id']
    subject = f"[auto-nanopore-run-qc-check] QC Check Complete: {sequencing_run_id}"

    template_text = files("auto_nanopore_run_qc_check.templates").joinpath("qc_check_complete_email.html").read_text()
    env = Environment(loader=BaseLoader())
    env.filters['thousands'] = _format_thousands
    body = env.from_string(template_text).render(email_data)

    return {
        "messageId": str(uuid.uuid4()),
        "from": notification_config['sender_email'],
        "email": {
            "to": notification_config['recipient_email_addresses'],
            "subject": subject,
            "bodyType": "html",
            "body": body,
        }
    }


def _collect_email_data(run_dir: Path, qc_check_complete_filename: str = "qc_check_complete.json") -> dict:
    """
    Collect data needed for populating the email template.

    :param run_dir: Path to the sequencing run directory
    :param qc_check_complete_filename: The filename of the QC Check Complete file to look for (default: `qc_check_complete.json`)
    :return: The collected data
    """
    with open(run_dir / qc_check_complete_filename, 'r') as f:
        email_data = json.load(f)

    email_data.setdefault('sequencing_run_id', run_dir.name)
    email_data['num_samples_by_project_id'] = {}

    samplesheet_path = samplesheet.find_samplesheet_path(run_dir)
    if samplesheet_path:
        email_data['num_samples_by_project_id'] = samplesheet.count_samples_by_project_id(samplesheet_path)

    return email_data


def send_notification_email(run_dir: Path, notification_config: dict) -> dict:
    """
    Collect relevant data from a run dir and send a notification email.

    :param run_dir: Sequencing run output dir (must include a "qc_check_complete.json" file).
    :param notification_config: Notification-related config. Required keys: ['auth_url', 'email_url', 'client_id', 'client_secret', 'sender_email', 'recipient_email_addresses']
    :return: Response data from the notification API.
    :raises requests.HTTPError: If the notification API returns an error.
    """
    email_data = _collect_email_data(Path(run_dir))
    log.debug({"event_type": "collected_email_data", "email_data": email_data})
    email_body = _prepare_email_body(email_data, notification_config)

    access_token = _get_access_token(notification_config)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": "Bearer " + access_token,
    }
    response = requests.post(notification_config['email_url'], data=json.dumps(email_body), headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    return response.json()


def main(args):
    configure_logging(args.log_level)
    config = load_config(args.config)
    response_data = send_notification_email(args.run_dir, config.notification)
    log.debug(response_data)
    log.info({"event_type": "email_notification_sent", "run_dir": os.path.abspath(args.run_dir)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--run-dir', type=Path, required=True)
    parser.add_argument('-c', '--config', type=Path, required=True)
    parser.add_argument('--log-level', type=str, default="info")
    args = parser.parse_args()
    main(args)
