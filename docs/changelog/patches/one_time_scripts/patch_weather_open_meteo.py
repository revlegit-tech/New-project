from pathlib import Path

path = Path("weather_collector.py")
text = path.read_text(encoding="utf-8")

text = text.replace('"apparent_temperature_2m"', '"apparent_temperature"')
text = text.replace("'apparent_temperature_2m'", "'apparent_temperature'")

old = '''"feelsLikeF": value("apparent_temperature", value("temperature_2m")),'''
if old not in text:
    # Handle older fallback pattern if present.
    text = text.replace(
        '''"feelsLikeF": value("apparent_temperature_2m", value("temperature_2m")),''',
        '''"feelsLikeF": value("apparent_temperature", value("temperature_2m")),'''
    )

path.write_text(text, encoding="utf-8")
print("Patched weather_collector.py to use Open-Meteo apparent_temperature.")
