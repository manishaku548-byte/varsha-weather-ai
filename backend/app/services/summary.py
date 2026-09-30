"""Builds the /data/summary payload from a validated dataset.

Only descriptive counts computed from the loaded data are returned — no
forecast values, no metrics, no claims.

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

import pandas as pd

from ..config import OBSERVATION_SOURCE, SOURCE_DEFINITIONS, settings
from ..schemas import (
    DataSummaryResponse,
    DistrictDataSummary,
    SourceInfo,
)
from .dataset import Dataset, available_district_names, resolve_district
from .rainfall import bucket_counts
from .source_health import compute_source_health


def _date_str(value) -> str | None:
    if value is None or (isinstance(value, float) and value != value):
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%d")


def build_summary(ds: Dataset, district: str | None = None) -> DataSummaryResponse:
    """Summarise the dataset, optionally restricted to one district."""
    district_id: str | None
    try:
        district_id = resolve_district(ds, district)
    except KeyError:
        raise KeyError(
            f"Unknown district '{district}'. Available districts: "
            f"{', '.join(available_district_names(ds))}"
        ) from None

    districts_df = ds.districts
    forecasts = ds.forecasts
    observations = ds.observations
    if district_id is not None:
        districts_df = districts_df[
            districts_df["district_id"].astype(str) == district_id
        ]
        forecasts = forecasts[forecasts["district_id"].astype(str) == district_id]
        observations = observations[
            observations["district_id"].astype(str) == district_id
        ]

    known_ids = set(districts_df["district_id"].astype(str))

    obs_dates = pd.to_datetime(observations["valid_date"], errors="coerce")
    fc_dates = pd.to_datetime(forecasts["valid_date"], errors="coerce")
    all_dates = pd.concat([obs_dates, fc_dates], ignore_index=True).dropna()

    obs24 = observations[pd.to_numeric(observations["lead_hours"], errors="coerce") == 24]
    obs24_values = pd.to_numeric(obs24["observed_rain_mm"], errors="coerce")

    source_record_counts = {
        str(k): int(v)
        for k, v in forecasts.groupby(forecasts["source_id"].astype(str)).size().items()
    }
    source_status_counts: dict[str, dict[str, int]] = {}
    if len(forecasts):
        pivot = (
            forecasts.assign(source_id=forecasts["source_id"].astype(str),
                             status=forecasts["status"].astype(str))
            .groupby(["source_id", "status"])
            .size()
        )
        for (src, status), count in pivot.items():
            source_status_counts.setdefault(str(src), {})[str(status)] = int(count)

    district_summaries: list[DistrictDataSummary] = []
    for row in districts_df.to_dict("records"):
        d_id = str(row["district_id"])
        d_obs = observations[observations["district_id"].astype(str) == d_id]
        d_fc = forecasts[forecasts["district_id"].astype(str) == d_id]
        d_obs24 = d_obs[pd.to_numeric(d_obs["lead_hours"], errors="coerce") == 24]
        values = pd.to_numeric(d_obs24["observed_rain_mm"], errors="coerce").dropna()
        d_dates = pd.to_datetime(d_obs["valid_date"], errors="coerce").dropna()

        district_summaries.append(
            DistrictDataSummary(
                district_id=d_id,
                district_name=str(row["district_name"]),
                first_valid_date=_date_str(d_dates.min()) if len(d_dates) else None,
                last_valid_date=_date_str(d_dates.max()) if len(d_dates) else None,
                observation_records=int(len(d_obs)),
                forecast_records=int(len(d_fc)),
                rainfall_24h=bucket_counts(values.tolist()),
                max_observed_24h_mm=round(float(values.max()), 1) if len(values) else None,
                mean_observed_24h_mm=round(float(values.mean()), 1) if len(values) else None,
            )
        )

    sources = [
        SourceInfo(
            source_id=source_id,
            source_type=meta["source_type"],
            display_name=meta["display_name"],
            description=meta["description"],
        )
        for source_id, meta in SOURCE_DEFINITIONS.items()
    ]
    sources.append(
        SourceInfo(
            source_id=str(OBSERVATION_SOURCE["source_id"]),
            source_type=str(OBSERVATION_SOURCE["source_type"]),
            display_name=str(OBSERVATION_SOURCE["display_name"]),
            description=str(OBSERVATION_SOURCE["description"]),
        )
    )

    return DataSummaryResponse(
        data_mode=settings.data_mode,
        data_label=settings.synthetic_data_label,
        disclaimer=settings.decision_support_disclaimer,
        district_count=int(len(districts_df)),
        first_valid_date=_date_str(all_dates.min()) if len(all_dates) else None,
        last_valid_date=_date_str(all_dates.max()) if len(all_dates) else None,
        lead_hours=list(settings.allowed_lead_hours),
        total_observation_records=int(len(observations)),
        total_forecast_records=int(len(forecasts)),
        sources=sources,
        source_record_counts=source_record_counts,
        source_status_counts=source_status_counts,
        source_health=compute_source_health(forecasts),
        rainfall_24h_overall=bucket_counts(obs24_values.tolist()),
        districts=district_summaries,
        validation=ds.validation,
    )
