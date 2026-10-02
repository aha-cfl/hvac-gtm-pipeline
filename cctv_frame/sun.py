"""Sun position from lat/lng + UTC time (NOAA approximation, ~0.5 deg accuracy).

Lets the playlist know which cameras are in daylight without any network call
or time-zone database.
"""

from datetime import datetime, timedelta, timezone
from math import acos, cos, degrees, pi, radians, sin

NIGHT_BELOW = -4.0  # deg; below this the scene is dark enough for the night palette
DAY_ABOVE = 6.0     # deg; above this it's full daylight (between = dusk/dawn)


def _parts(when):
    when = when.astimezone(timezone.utc)
    hour = when.hour + when.minute / 60 + when.second / 3600
    g = 2 * pi / 365 * (when.timetuple().tm_yday - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * cos(g) - 0.032077 * sin(g)
                       - 0.014615 * cos(2 * g) - 0.040849 * sin(2 * g))
    decl = (0.006918 - 0.399912 * cos(g) + 0.070257 * sin(g) - 0.006758 * cos(2 * g)
            + 0.000907 * sin(2 * g) - 0.002697 * cos(3 * g) + 0.00148 * sin(3 * g))
    return hour, eqtime, decl


def elevation(lat, lng, when):
    """Solar elevation in degrees (negative = below the horizon)."""
    hour, eqtime, decl = _parts(when)
    true_solar_min = hour * 60 + eqtime + 4 * lng
    ha = radians(true_solar_min / 4 - 180)
    la = radians(lat)
    cos_zen = sin(la) * sin(decl) + cos(la) * cos(decl) * cos(ha)
    return 90 - degrees(acos(max(-1.0, min(1.0, cos_zen))))


def phase(lat, lng, when):
    """'day', 'dusk' (twilight, either end) or 'night'."""
    e = elevation(lat, lng, when)
    if e >= DAY_ABOVE:
        return "day"
    return "dusk" if e >= NIGHT_BELOW else "night"


def local_time(lng, when, tz=None):
    """Local clock time. Uses the IANA zone if given, else mean solar time."""
    if tz:
        try:
            from zoneinfo import ZoneInfo
            return when.astimezone(ZoneInfo(tz)).strftime("%H:%M")
        except Exception:  # missing tzdata or bad name: fall back to solar time
            pass
    solar = when.astimezone(timezone.utc) + timedelta(hours=lng / 15)
    return "~" + solar.strftime("%H:%M")


def now_utc():
    return datetime.now(timezone.utc)
