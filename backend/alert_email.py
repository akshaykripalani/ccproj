"""Readable SNS equipment emails, using the recorded activation reading."""

from decimal import Decimal

from backend.domain import RULES, parse_time


def number(value):
    # Preserve small threshold breaches instead of rounding them back to the limit.
    text = format(Decimal(str(value)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def render_email(intent, dashboard_url):
    reading = intent["reading"]
    motor = intent["deviceId"].replace("motor-", "Motor ")
    rule = intent["rule"]
    field, limit = RULES[rule]
    label, unit, description = {
        "temperature": ("Temperature", "°C", "over its temperature limit"),
        "vibration": ("Vibration", "mm/s", "over its vibration limit"),
    }[rule]
    detected = parse_time(reading["observedAt"]).strftime("%d %b %Y, %H:%M:%S UTC")
    other_field, other_label, other_unit = (
        ("vibrationMmS", "Vibration", "mm/s")
        if rule == "temperature"
        else ("temperatureC", "Temperature", "°C")
    )
    return {
        "Subject": f"Forge alert: {motor} {'over temperature' if rule == 'temperature' else 'high vibration'}",
        "Message": (
            f"{motor} is {description}.\n\n"
            f"{label}: {number(reading[field])} {unit}\n"
            f"Limit: {number(limit)} {unit}\n"
            f"Detected: {detected}\n"
            "Confirmed by 3 consecutive readings above the limit.\n\n"
            "Other readings at detection\n"
            f"{other_label}: {number(reading[other_field])} {other_unit}\n"
            f"Power: {number(reading['powerWatts'])} W\n"
            f"Operating state: {reading['operatingState'].capitalize()}\n\n"
            f"View {motor}\n"
            f"{dashboard_url.rstrip('/')}/#/devices/{intent['deviceId']}\n\n"
            "Check Forge for the current state; this email records the fault at detection.\n"
            "Operators can use Reset on the dashboard to return this motor to normal.\n"
        ),
    }
