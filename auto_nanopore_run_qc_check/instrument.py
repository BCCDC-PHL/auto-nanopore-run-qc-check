import re

from auto_nanopore_run_qc_check.model import InstrumentType

GRIDION_RUN_ID_REGEX = ""
PROMETHION_RUN_ID_REGEX = ""

run_id_regex_by_instrument_type = {
    'gridion': GRIDION_RUN_ID_REGEX,
    'promethion': PROMETHION_RUN_ID_REGEX,
}

def determine_instrument_type(run_id: str) -> InstrumentType:
    """
    Determine the instrument type

    :param run_id: The sequencing run ID.
    :return: The instrument type
    """
    instrument_type_str = "unknown"

    for instrument_type, regex in run_id_regex_by_instrument_type.items():
        if re.match(regex, run_id):
            instrument_type_str = instrument_type

    instrument_type = InstrumentType(instrument_type_str)

    return instrument_type
