# auto-nanopore-run-qc-check

Automated run-level QC check for Oxford Nanopore sequencing runs.

# Installation

Clone this repo:

```
git clone git@github.com:BCCDC-PHL/auto-nanopore-run-qc-check.git
cd auto-nanopore-run-qc-check
```

Create a conda env, including python, pip and uv:

```
conda create -n auto-nanopore-run-qc-check python pip uv
```

Activate the conda env

```
conda activate auto-nanopore-run-qc-check
```

Use pip to install:

```
uv pip install .
```

If you're developing/editing the source code then you can install in 'editable' mode:

```
uv pip install -e .
```

This will allow any changes to the codebase to be made immediately reflected in the tool.

## Testing

Install `pytest` and run the tests from the root of the repo:

```
uv pip install pytest
pytest tests
```

# Usage
Start the tool as follows:

```bash
auto-nanopore-run-qc-check --config config.json
```

See the Configuration section of this document for details on preparing a configuration file.

More detailed logs can be produced by controlling the log level using the `--log-level` flag:

```bash
auto-nanopore-run-qc-check --config config.json --log-level debug
```

# Configuration
This tool takes a single config file, in JSON format, with the following structure:

```json
{
    "excluded_runs_list": "excluded_runs.csv",
    "scan_interval_seconds": 10,
    "run_parent_dirs": [
	"/path/to/GXB05792/26"
    ],
    "qc_thresholds": [
        {
            "metric": "PercentReadsPassed",
            "threshold": 70,
            "pass_above_or_below": "above"
        },
        {
            "metric": "EstimatedReadN50",
            "threshold": 4000,
            "pass_above_or_below": "above"
        },
        {
            "metric": "NumReadsPassed",
            "threshold": 100000,
            "pass_above_or_below": "above",
            "instrument_type": "gridion"
        },
	    {
            "metric": "NumReadsPassed",
            "threshold": 500000,
            "pass_above_or_below": "above",
            "instrument_type": "promethion"
        }
    ]
}
```

Note that the key `instrument_type` is optional for each threshold. If included, they will only be applied to runs matching those values.
The only supported instrument types are `gridion` and `promethion`. If those keys are not included, the threshold will be applied to all runs regardless of instrument
type or flowcell version.

## Notification Emails

Notification emails can be enabled by adding the following `"notification"` section to the config:

```json
{
    ...
    "notification": {
        "system_config_file": "/path/to/notification/config.json",
        "recipient_email_addresses": [
            "someone@example.org"
        ],
        "send_notification_emails": true
    },
    ...
}
```

...where `"system_config_file"` points to a json file with the following structure:

```json
{
    "auth_url": "",
    "email_url": "",
    "client_id": "",
    "client_secret": "",
     "sender_email": ""
}
```

# Outputs

This tool will write a file named `qc_check_complete.json`, with the following format:

```
{
  "checked_metrics": [
    {
      "metric": "PercentReadsPassed",
      "value": 81.3,
      "threshold": 60,
      "pass_above_or_below": "above",
      "pass_fail": "PASS"
    },
    {
      "metric": "NumReadsPassed",
      "value": 1893877,
      "threshold": 100000,
      "pass_above_or_below": "above",
      "pass_fail": "PASS"
    },
    {
      "metric": "ReadN50",
      "value": 8900,
      "threshold": 4000,
      "pass_above_or_below": "above",
      "pass_fail": "PASS"
    },
    {
      "metric": "SumSampleFastqFileSizesMb",
      "value": 236267.27,
      "threshold": 100.0,
      "pass_above_or_below": "above",
      "pass_fail": "PASS"
    }
  ],
  "overall_pass_fail": "PASS",
  "sequencing_run_id": "20260917_1024_X3_FAG67189_28701687",
  "instrument_type": "gridion",
  "minknow_report_path": "/path/to/20260917_1024_X3_FAG67189_28701687/report_FAG67189_20260917_1024_28701687.json",
  "timestamp_qc_check_started": "2026-09-18T15:45:28.074190",
  "timestamp_qc_check_completed": "2026-09-18T15:45:28.152267"
}
```

If a run has no MinKNOW report (`report_*.json`), which can happen when a run is interrupted, the QC check still completes.
`minknow_report_path` will be `null`, metrics that come from the report will have a `null` value and an `UNDETERMINED` result,
and the notification email will say that the report was missing.

# Logging
This tool outputs [structured logs](https://www.honeycomb.io/blog/structured-logging-and-your-team/) in [JSON Lines](https://jsonlines.org/) format:

Every log line should include the fields:

- `timestamp`
- `level`
- `module`
- `function_name`
- `line_num`
- `message`

...and the contents of the `message` key will be a JSON object that includes at `event_type`. The remaining keys inside the `message` will vary by event type.

```json
{"timestamp": "2022-09-22T11:32:52.287", "level": "INFO", "module": "core", "function_name": "scan", "line_num": 56, "message": {"event_type": "scan_start"}}
```
