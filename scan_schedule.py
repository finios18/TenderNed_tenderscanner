"""Calendar-day intervals anchored to a company-specific start date."""
import argparse
from datetime import date, datetime
import os
from zoneinfo import ZoneInfo

from scanner_config import load_config, validate_schedule


def is_due(schedule, today):
    validate_schedule(schedule)
    elapsed = (today - date.fromisoformat(schedule["start_date"])).days
    return schedule["enabled"] and elapsed >= 0 and elapsed % schedule["interval_days"] == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    scheduled = os.environ.get("RESPECT_SCHEDULE", "false").lower() == "true"
    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    if scheduled and "schedule" not in config:
        parser.error("Geplande scans vereisen een schedule-blok in het bedrijfsprofiel")
    due = is_due(config["schedule"], today) if scheduled else True
    result = f"run_scan={str(due).lower()}\n"
    print(f"{config['id']}: {today}, {result.strip()}, terugkijkperiode={config['scan']['days']} dagen")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(result)


if __name__ == "__main__":
    main()
