"""Dynamic Trust Engine (SRS FR-DTE-01..06, core formulae section).

Score components per source, all computed from records strictly earlier than
the selected date plus the current forecast situation:

    historical skill : inverse MAE over ALL prior usable records      (40%)
    recent skill     : inverse MAE over the most recent 14 prior ones (25%)
    source health    : Healthy/Delayed/Anomalous/Unavailable mapping  (20%)
    agreement        : distance from the peer median of corrected fcs (15%)
    context          : configurable regime + lead-time multiplicative factor

    trust = (0.40*S + 0.25*R + 0.20*Q + 0.15*A) * context_factor
    weight = trust / sum(trust of eligible sources)

Rules:
* An unavailable/ineligible source has trust score **exactly 0.0** and
  weight **exactly 0.0**.
* Eligible weights are normalized to sum to 1.
* A single eligible source gets weight 1.0 (single-source fallback).
* No eligible source -> the engine raises ForecastUnavailableError.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import SOURCE_DEFINITIONS, Settings, settings as default_settings


@dataclass
class TrustSource:
    source_id: str
    source_type: str
    display_name: str
    eligible: bool
    health_status: str
    health_score: float
    historical_mae_mm: float | None
    historical_record_count: int
    historical_skill: float
    recent_mae_mm: float | None
    recent_record_count: int
    recent_skill: float
    agreement: float
    context_factor: float
    trust_score: float
    weight: float
    reason: str
    ineligible_reason: str | None = None


@dataclass
class TrustResult:
    sources: list[TrustSource] = field(default_factory=list)
    eligible_count: int = 0
    median_corrected_mm: float | None = None
    total_trust: float = 0.0
    weights: dict[str, float] = field(default_factory=dict)


def inverse_mae_skill(mae_mm: float | None, cfg: Settings) -> float:
    """Inverse-MAE skill mapped to 0..1: 1 / (1 + MAE / scale)."""
    if mae_mm is None:
        return cfg.skill_score_when_no_history
    return float(1.0 / (1.0 + max(0.0, mae_mm) / cfg.skill_mae_scale_mm))


def agreement_score(
    corrected_mm: float, median_mm: float, cfg: Settings
) -> float:
    """1.0 at the peer median, falling linearly with distance (floor 0.0)."""
    scale = max(abs(median_mm), cfg.agreement_scale_mm)
    distance = abs(corrected_mm - median_mm)
    return float(max(0.0, 1.0 - distance / scale))


def compute_trust(
    *,
    eligible: dict[str, bool],
    ineligible_reasons: dict[str, str],
    health_status: dict[str, str],
    corrected_mm: dict[str, float | None],
    historical_mae_mm: dict[str, float | None],
    historical_counts: dict[str, int],
    recent_mae_mm: dict[str, float | None],
    recent_counts: dict[str, int],
    regime_label: str,
    lead_hours: int,
    cfg: Settings | None = None,
) -> TrustResult:
    """Compute trust components and normalized weights for all sources."""
    s = cfg or default_settings

    eligible_ids = [sid for sid in SOURCE_DEFINITIONS if eligible.get(sid, False)]
    corrected_values = [
        corrected_mm.get(sid)
        for sid in eligible_ids
        if corrected_mm.get(sid) is not None
    ]
    median_mm = sorted(corrected_values)[len(corrected_values) // 2] if corrected_values else None
    if median_mm is not None and len(corrected_values) % 2 == 0:
        median_mm = (sorted(corrected_values)[len(corrected_values) // 2 - 1] + median_mm) / 2.0

    result = TrustResult(eligible_count=len(eligible_ids), median_corrected_mm=median_mm)
    raw_scores: dict[str, float] = {}
    records: dict[str, TrustSource] = {}

    for source_id, meta in SOURCE_DEFINITIONS.items():
        source_type = meta["source_type"]
        health = health_status.get(source_id, "Unavailable")
        health_score = float(s.health_score_map.get(health, 0.0))
        is_eligible = bool(eligible.get(source_id, False)) and health != "Unavailable"

        h_mae = historical_mae_mm.get(source_id)
        r_mae = recent_mae_mm.get(source_id)
        h_count = int(historical_counts.get(source_id, 0))
        r_count = int(recent_counts.get(source_id, 0))
        h_skill = inverse_mae_skill(h_mae, s)
        r_skill = inverse_mae_skill(r_mae, s)

        if not is_eligible:
            reason = ineligible_reasons.get(
                source_id, "Source is not eligible for this forecast."
            )
            if health == "Unavailable":
                reason = f"Source health is Unavailable. {reason}"
            record = TrustSource(
                source_id=source_id,
                source_type=source_type,
                display_name=str(meta["display_name"]),
                eligible=False,
                health_status=health,
                health_score=0.0,
                historical_mae_mm=h_mae,
                historical_record_count=h_count,
                historical_skill=0.0,
                recent_mae_mm=r_mae,
                recent_record_count=r_count,
                recent_skill=0.0,
                agreement=0.0,
                context_factor=1.0,
                trust_score=0.0,
                weight=0.0,
                reason=reason,
                ineligible_reason=reason,
            )
            records[source_id] = record
            raw_scores[source_id] = 0.0
            continue

        value = corrected_mm.get(source_id)
        agree = (
            agreement_score(float(value), float(median_mm), s)
            if value is not None and median_mm is not None
            else 0.0
        )
        regime_factor = s.context_regime_factors.get(source_id, {}).get(regime_label, 1.0)
        lead_factor = s.context_lead_factors.get(source_id, {}).get(str(lead_hours), 1.0)
        context = float(regime_factor) * float(lead_factor)

        trust = (
            s.trust_weights["historical_skill"] * h_skill
            + s.trust_weights["recent_skill"] * r_skill
            + s.trust_weights["health"] * health_score
            + s.trust_weights["agreement"] * agree
        ) * context

        raw_scores[source_id] = max(0.0, float(trust))

        history_part = (
            f"prior skill MAE {h_mae:.1f} mm over {h_count} record(s)"
            if h_mae is not None
            else "insufficient prior history (neutral skill applied)"
        )
        recent_part = (
            f"recent-14 MAE {r_mae:.1f} mm over {r_count} record(s)"
            if r_mae is not None
            else "no recent records (neutral skill applied)"
        )
        reason = (
            f"{history_part}; {recent_part}; source health {health} "
            f"(score {health_score:.2f}); agreement {agree:.2f} with peer median "
            f"{median_mm:.1f} mm; context factor x{context:.2f} "
            f"({regime_label}, {lead_hours}h)."
        )

        records[source_id] = TrustSource(
            source_id=source_id,
            source_type=source_type,
            display_name=str(meta["display_name"]),
            eligible=True,
            health_status=health,
            health_score=health_score,
            historical_mae_mm=h_mae,
            historical_record_count=h_count,
            historical_skill=round(h_skill, 6),
            recent_mae_mm=r_mae,
            recent_record_count=r_count,
            recent_skill=round(r_skill, 6),
            agreement=round(agree, 6),
            context_factor=round(context, 6),
            trust_score=round(raw_scores[source_id], 6),
            weight=0.0,
            reason=reason,
        )

    # --- normalize -----------------------------------------------------------------
    total = sum(raw_scores[sid] for sid in eligible_ids)
    result.total_trust = float(total)

    if total <= 0.0:
        # Eligible sources exist but every score collapsed to zero -> unusable.
        for source_id in eligible_ids:
            records[source_id].ineligible_reason = (
                "Trust score collapsed to 0.0 for all eligible sources."
            )
        result.sources = [records[sid] for sid in SOURCE_DEFINITIONS]
        result.weights = {sid: 0.0 for sid in SOURCE_DEFINITIONS}
        return result

    weights: dict[str, float] = {}
    for source_id in SOURCE_DEFINITIONS:
        if source_id in eligible_ids:
            weights[source_id] = float(raw_scores[source_id]) / float(total)
        else:
            weights[source_id] = 0.0

    for source_id, record in records.items():
        record.weight = weights.get(source_id, 0.0)
        if record.eligible:
            record.reason += f" Trust {record.trust_score:.3f} -> weight {record.weight:.3f}."
        record.weight = float(record.weight)

    result.sources = [records[sid] for sid in SOURCE_DEFINITIONS]
    result.weights = weights
    return result
