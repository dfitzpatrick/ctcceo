from datetime import datetime, timedelta
from typing import Optional
import re
TIMEDELTA_PATTERN = re.compile('^(?:(?P<weeks>\d+)[w.])?(?:(?P<days>\d+)[d.])?(?:(?P<hours>\d+)[h.])?(?:(?P<minutes>\d+)[m.])?(?:(?P<seconds>\d+)[s.])?$')


def establish_member_config(settings_dict, guild_id: str, member_id: str):
    if guild_id not in settings_dict.keys():
        settings_dict[guild_id] = {}
    if member_id not in settings_dict[guild_id].keys():
        settings_dict[guild_id][member_id] = {}

def string_timedelta(span: str) -> Optional[timedelta]:
    """
           Format is
           1w2d1h18m2s

           :param last_active:
           :return:
           """

    matches = re.search(TIMEDELTA_PATTERN, span)
    if matches is None:
        log.error(f"Invalid TimeDelta {span}")
        return
    args = {k: int(v) for k, v in matches.groupdict().items() if v and v.isdigit()}
    return timedelta(**args)
