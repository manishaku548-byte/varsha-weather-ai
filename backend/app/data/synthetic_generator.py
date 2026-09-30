"""Deterministic generator for the VARSHA development dataset.

⚠️ Synthetic Development Dataset — Not Operational Weather Data ⚠️

This script creates *controlled synthetic* data for development, testing and
demo purposes only. It is NOT IMD, NCMRWF, Open-Meteo or any other real
weather data source, and it must never be presented as operational data.

What it produces (per district, default 120 valid dates):

* A plausible daily rainfall series containing dry days, light, moderate,
  heavy, very-heavy and a few extreme days, clustered into wet spells.
* Heatwave episodes (hot + dry) so regime detection has real variety.
* Three forecast sources with realistic, imperfect behaviour:
    - NWP          : systematically underpredicts heavy rainfall events.
    - Ensemble     : well-calibrated mean plus spread/percentile columns.
    - AI local     : excellent in moderate rain, occasionally misses extremes.
* Source disturbances: scattered delayed/unavailable/anomalous records plus a
  recent NWP delay burst and a recent AI anomaly burst so source health can be
  demonstrated as Healthy / Delayed / Unavailable / Anomalous.

Time convention (documented in docs/data_dictionary.md):

* ``valid_date`` is the END of the accumulation window (rainfall *ending on*
  that date), therefore ``issue_time = valid_date - lead_hours``.
* lead 24h -> rainfall of the calendar day before ``valid_date``.
* lead 6h  -> the last 6 hours of that day.
* lead 72h -> the three days ending at ``valid_date``.

Usage:
    python -m app.data.synthetic_generator
    python -m app.data.synthetic_generator --data-dir ../data --seed 42
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import SOURCE_DEFINITIONS, settings

SEED = 42
VALID_START = "2025-06-01"
DEFAULT_VALID_DAYS = 120
LEAD_HOURS = (6, 24, 72)
SPELL_LENGTHS = (2, 3, 4, 3, 3, 4, 2, 3, 4, 3)
_SEVERITY = {"moderate": 0, "heavy": 1, "very_heavy": 2, "extreme": 3}

FORECAST_COLUMNS = [
    "district_id",
    "valid_date",
    "lead_hours",
    "source_id",
    "issue_time",
    "forecast_rain_mm",
    "unit",
    "status",
    "quality_flag",
    "ensemble_spread_mm",
    "ensemble_p10_mm",
    "ensemble_p90_mm",
]

OBSERVATION_COLUMNS = [
    "district_id",
    "valid_date",
    "lead_hours",
    "observed_rain_mm",
    "observed_temp_c",
    "observed_humidity_pct",
    "observed_wind_kmph",
    "unit",
]

LABEL = "Synthetic Development Dataset — Not Operational Weather Data"


# --------------------------------------------------------------------------------------
# Series construction
# --------------------------------------------------------------------------------------
def _day_types(rng: np.random.Generator, n_series: int) -> np.ndarray:
    """Assign a day type to every day of the latent series.

    Heavy / very-heavy / extreme days are concentrated inside wet spells so the
    regime detector later sees realistic clustered monsoon activity.
    """
    spell_days = sum(SPELL_LENGTHS)
    light, moderate, heavy, very_heavy, extreme = 26, 16, 12, 8, 3
    dry = n_series - (light + moderate + heavy + very_heavy + extreme)
    if dry < 15:
        raise ValueError(
            f"series too short ({n_series} days): need at least "
            f"{65 + 15} days for a plausible distribution"
        )

    # --- place wet spells -------------------------------------------------------
    starts: list[int] = []
    cursor = 2
    for length in SPELL_LENGTHS:
        cursor += int(rng.integers(0, 3))
        if cursor + length > n_series:
            cursor = n_series - length
        starts.append(cursor)
        cursor += length + int(rng.integers(4, 8))
    for i in range(len(starts) - 1):
        if starts[i + 1] <= starts[i] + SPELL_LENGTHS[i]:
            raise RuntimeError("wet spells overlapped; adjust spacing")

    types = np.full(n_series, "", dtype=object)

    severe = ["heavy"] * heavy + ["very_heavy"] * very_heavy + ["extreme"] * extreme
    if len(severe) > spell_days:
        raise RuntimeError("more severe days than spell slots")
    spell_pool = severe + ["moderate"] * (spell_days - len(severe))
    rng.shuffle(spell_pool)

    idx = 0
    for start, length in zip(starts, SPELL_LENGTHS):
        for k in range(length):
            types[start + k] = spell_pool[idx]
            idx += 1

    # ramp up inside each spell (build-up to the peak day)
    for start, length in zip(starts, SPELL_LENGTHS):
        segment = sorted(
            [types[start + k] for k in range(length)], key=_SEVERITY.__getitem__
        )
        for k, day_type in enumerate(segment):
            types[start + k] = day_type

    # --- remaining days ---------------------------------------------------------
    non_spell = np.where(types == "")[0]
    spell_moderate = spell_days - len(severe)
    rest = (
        ["moderate"] * (moderate - spell_moderate)
        + ["light"] * light
        + ["dry"] * dry
    )
    if len(rest) != len(non_spell):
        raise RuntimeError(
            f"day-type quota mismatch: {len(rest)} values for {len(non_spell)} days"
        )
    rng.shuffle(rest)
    for i, day_type in zip(non_spell, rest):
        types[i] = day_type

    return types


def _day_values(rng: np.random.Generator, types: np.ndarray) -> np.ndarray:
    """Draw a plausible rainfall amount (mm) for each day type."""
    values = np.zeros(len(types), dtype=float)
    for i, day_type in enumerate(types):
        if day_type == "dry":
            value = 0.0
        elif day_type == "light":
            value = rng.uniform(0.1, 15.5)
        elif day_type == "moderate":
            value = rng.uniform(15.6, 64.4)
        elif day_type == "heavy":
            value = rng.uniform(64.5, 115.5)
        elif day_type == "very_heavy":
            value = rng.uniform(115.6, 204.4)
        else:  # extreme
            value = rng.uniform(204.5, 300.0)
        values[i] = round(float(value), 1)
    return values


def _weather(
    rng: np.random.Generator, types: np.ndarray, values: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, set[int]]:
    """Temperature / humidity / wind plus the heatwave day indices."""
    n = len(values)
    doy = np.arange(n)
    base = 31.0 + 2.5 * np.sin(2 * np.pi * (doy - 12) / max(n, 1))
    temp = base + rng.normal(0, 1.7, n) - np.where(values > 0.1, 2.5, 0.0)

    dry_candidates = [i for i, t in enumerate(types) if t == "dry" and 3 <= i < n - 3]
    if len(dry_candidates) < 4:
        raise RuntimeError("not enough dry days for heatwave episodes")

    def _cluster(target: int, used: set[int]) -> int:
        nearby = [i for i in dry_candidates if i not in used and abs(i - target) <= 5]
        pool = nearby or [i for i in dry_candidates if i not in used]
        return int(rng.choice(pool))

    h1 = _cluster(int(rng.integers(18, 26)), set())
    h2 = _cluster(int(rng.integers(92, 102)), {h1})
    heat = {i for i in (h1, h1 + 1, h1 + 2, h2, h2 + 1) if i < n and types[i] == "dry"}

    for i in sorted(heat):
        temp[i] = float(rng.uniform(42.0, 46.5))

    humidity = 60.0 + 20.0 * np.clip(values / 60.0, 0, 1) + rng.normal(0, 6, n)
    for i in sorted(heat):
        humidity[i] = float(rng.uniform(18.0, 34.0))
    humidity = np.clip(humidity, 15, 98)

    wind = 6.0 + rng.gamma(2.0, 4.0, n)
    wet_storm = values >= 64.5
    wind[wet_storm] += rng.uniform(8, 20, int(wet_storm.sum()))
    wind = np.clip(wind, 3, 75)

    return (
        np.round(temp, 1),
        np.round(humidity, 1),
        np.round(wind, 1),
        set(heat),
    )


# --------------------------------------------------------------------------------------
# Source behaviour
# --------------------------------------------------------------------------------------
def _source_forecast(
    rng: np.random.Generator, source_id: str, truth: float
) -> tuple[float, float, float, float]:
    """Return (value, spread, p10, p90) for one source. NaN spread for non-ensemble."""
    nan = float("nan")

    if source_id == "nwp_model_a":
        if truth >= 64.5:
            # Known weakness: underpredicts heavy rainfall events.
            value = truth * rng.uniform(0.45, 0.75) + rng.normal(0, 5.0)
        elif truth < 1.0:
            value = rng.normal(2.0, 3.0)  # occasional false alarm on dry days
        else:
            value = truth * rng.normal(0.92, 0.12) + rng.normal(0, 2.5)
        return round(max(0.0, float(value)), 1), nan, nan, nan

    if source_id == "ensemble_mean":
        value = max(0.0, float(truth * rng.normal(1.0, 0.07) + rng.normal(0, 3.0)))
        spread = max(1.0, 0.22 * truth + abs(float(rng.normal(0, 2.0))) + 1.5)
        p10 = max(0.0, value - 1.28 * spread)
        p90 = value + 1.28 * spread
        return round(value, 1), round(spread, 1), round(p10, 1), round(p90, 1)

    # ai_local_v1
    if truth >= 64.5:
        if rng.random() < 0.35:
            # occasional large miss on extremes
            value = truth * rng.uniform(1.25, 1.75) + rng.normal(0, 6.0)
        else:
            value = truth * rng.uniform(0.75, 1.10) + rng.normal(0, 5.0)
    elif truth < 1.0:
        value = rng.normal(1.0, 2.0)
    else:
        # Strong local skill for light/moderate rainfall.
        value = truth * rng.normal(1.0, 0.07) + rng.normal(0, 1.8)
    return round(max(0.0, float(value)), 1), nan, nan, nan


def _record_status(
    rng: np.random.Generator, source_id: str, day_index: int, burst: dict[str, tuple[int, int]]
) -> tuple[str, str]:
    """Scattered disturbances plus two recent bursts so source health is demonstrable."""
    r = float(rng.random())
    delayed_window = burst["nwp_delayed"]
    anomalous_window = burst["ai_anomalous"]

    if source_id == "nwp_model_a" and delayed_window[0] <= day_index <= delayed_window[1] and r < 0.50:
        return "delayed", "low_confidence"
    if source_id == "ai_local_v1" and anomalous_window[0] <= day_index <= anomalous_window[1] and r < 0.40:
        return "anomalous", "suspect"
    if r < 0.015:
        return "unavailable", "missing"
    if r < 0.030:
        return "delayed", "low_confidence"
    if r < 0.045:
        return "anomalous", "suspect"
    return "ok", "good"


# --------------------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------------------
def generate_dataset(
    data_dir: Path | str,
    *,
    seed: int = SEED,
    valid_days: int = DEFAULT_VALID_DAYS,
) -> dict[str, int]:
    """Generate both CSV datasets next to an existing ``districts.csv``."""
    data_dir = Path(data_dir)
    districts_path = data_dir / settings.districts_file
    if not districts_path.is_file():
        raise FileNotFoundError(
            f"{settings.districts_file} not found in '{data_dir}'. "
            "District metadata must exist before forecasts can be generated."
        )
    districts = pd.read_csv(districts_path)
    required = {"district_id", "district_name"}
    missing = required - set(districts.columns)
    if missing:
        raise ValueError(f"{settings.districts_file} is missing column(s): {sorted(missing)}")

    rng = np.random.default_rng(seed)

    # Latent series starts 3 days before the first valid date (72h windows).
    n_series = valid_days + 2
    series_start = pd.Timestamp(VALID_START) - pd.Timedelta(days=3)
    valid_dates = pd.date_range(VALID_START, periods=valid_days, freq="D")
    assert series_start + pd.Timedelta(days=3) == valid_dates[0], "series/valid alignment"

    burst = {
        "nwp_delayed": (valid_days - 10, valid_days - 3),   # e.g. 110..117
        "ai_anomalous": (valid_days - 8, valid_days - 1),   # e.g. 112..119
    }

    obs_rows: list[dict] = []
    fc_rows: list[dict] = []
    source_ids = list(SOURCE_DEFINITIONS)
    heatwave_total = 0

    for d_index, d_row in enumerate(districts.to_dict("records")):
        d_id = str(d_row["district_id"])
        types = _day_types(rng, n_series)
        values = _day_values(rng, types)
        temp, humidity, wind, heat_days = _weather(rng, types, values)
        heatwave_total += len(heat_days)

        for j, valid_ts in enumerate(valid_dates):
            ref = 2 + j  # index of the day whose rain ends at valid_date
            rain24 = float(values[ref])
            rain6 = round(rain24 * float(rng.uniform(0.10, 0.45)), 1) if rain24 > 0 else 0.0
            rain72 = round(float(values[j] + values[j + 1] + values[j + 2]), 1)
            obs_by_lead = {6: rain6, 24: rain24, 72: rain72}

            valid_str = valid_ts.strftime("%Y-%m-%d")

            for lead in LEAD_HOURS:
                obs_rows.append(
                    {
                        "district_id": d_id,
                        "valid_date": valid_str,
                        "lead_hours": lead,
                        "observed_rain_mm": obs_by_lead[lead],
                        "observed_temp_c": float(temp[ref]),
                        "observed_humidity_pct": float(humidity[ref]),
                        "observed_wind_kmph": float(wind[ref]),
                        "unit": settings.forecast_unit,
                    }
                )

                truth = obs_by_lead[lead]
                issue_str = (
                    valid_ts - pd.Timedelta(hours=lead)
                ).strftime("%Y-%m-%dT%H:%M:%SZ")

                for source_id in source_ids:
                    value, spread, p10, p90 = _source_forecast(rng, source_id, truth)
                    status, quality_flag = _record_status(rng, source_id, j, burst)

                    if status == "unavailable":
                        value, spread, p10, p90 = (
                            float("nan"),
                            float("nan"),
                            float("nan"),
                            float("nan"),
                        )
                    elif status == "anomalous":
                        # Deliberately implausible raw value so quality flags fire.
                        value = 999.0 if rng.random() < 0.5 else -12.0

                    fc_rows.append(
                        {
                            "district_id": d_id,
                            "valid_date": valid_str,
                            "lead_hours": lead,
                            "source_id": source_id,
                            "issue_time": issue_str,
                            "forecast_rain_mm": value,
                            "unit": settings.forecast_unit,
                            "status": status,
                            "quality_flag": quality_flag,
                            "ensemble_spread_mm": spread,
                            "ensemble_p10_mm": p10,
                            "ensemble_p90_mm": p90,
                        }
                    )

    forecasts = pd.DataFrame(fc_rows, columns=FORECAST_COLUMNS)
    observations = pd.DataFrame(obs_rows, columns=OBSERVATION_COLUMNS)

    forecasts.to_csv(
        data_dir / settings.forecasts_file, index=False, float_format="%.1f"
    )
    observations.to_csv(
        data_dir / settings.observations_file, index=False, float_format="%.1f"
    )

    return {
        "districts": int(len(districts)),
        "valid_days": int(valid_days),
        "forecast_records": int(len(forecasts)),
        "observation_records": int(len(observations)),
        "heatwave_days_total": int(heatwave_total),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the VARSHA synthetic development dataset."
    )
    parser.add_argument(
        "--data-dir",
        default=str(settings.data_dir),
        help="Output directory that contains districts.csv (default: <project>/data)",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed (default: 42)")
    parser.add_argument(
        "--days", type=int, default=DEFAULT_VALID_DAYS, help="Valid days per district"
    )
    args = parser.parse_args(argv)

    counts = generate_dataset(args.data_dir, seed=args.seed, valid_days=args.days)
    print(f"[OK] {LABEL}")
    print(f"  directory : {args.data_dir}")
    print(f"  seed      : {args.seed}")
    for key, value in counts.items():
        print(f"  {key:26s}: {value}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
