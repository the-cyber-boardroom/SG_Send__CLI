import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

BATCH_OP__REGEX      = re.compile(r'^(write|write-if-match|delete)$')
BATCH_OP__MAX_LENGTH = 16

class Safe_Str__Batch_Op(Safe_Str):
    regex             = BATCH_OP__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = BATCH_OP__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = True
    to_lower_case     = True
    strict_validation = True
