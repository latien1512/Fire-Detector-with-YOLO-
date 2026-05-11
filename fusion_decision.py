SAFE = 0
GAS_LEAK = 1
VOC_CHEMICAL = 2
SMOKE_AIR = 3
FIRE = 4

HAZARD_NAME = {
    SAFE: "SAFE",
    GAS_LEAK: "GAS_LEAK",
    VOC_CHEMICAL: "VOC_CHEMICAL",
    SMOKE_AIR: "SMOKE_AIR",
    FIRE: "FIRE"
}


def _build_result(
    label: int,
    reason: str,
    source: str,
    urgency: str,
    buzzer: bool,
    fan: bool,
    mist: bool,
    emergency: bool,
):
    return {
        "label": int(label),
        "hazard": HAZARD_NAME[int(label)],
        "reason": reason,
        "source": source,          # hard_rule / physics / ml / severity_override
        "urgency": urgency,        # immediate / confirm / monitor
        "actuator": {
        "buzzer": bool(buzzer),
        "fan": bool(fan),
        "mist": bool(mist),
        "emergency": bool(emergency),
        }
    }


def fusion_decision(
    *,
    temp_c: float,
    temp_status: str,
    temp_rise: str,
    mq2_hi: float,
    mq135_hi: float,
    voc_ppm: int,
    ml_label: int,
    severity_score: float,
    severity_level: str,
    action_level: str,
):
    """
    Instant fusion decision.

    Inputs:
        temp_c         : current temperature
        temp_status    : safe / warning / danger
        temp_rise      : normal / caution / high_risk
        mq2_hi         : MQ-2 HI
        mq135_hi       : MQ-135 HI
        voc_ppm        : VOC ppm
        ml_label       : ML predicted hazard label (int)
        severity_score : 0..100
        severity_level : LOW / MEDIUM / HIGH / CRITICAL
        action_level   : MONITOR / ALERT / INTERVENE / EMERGENCY

    Returns dict:
        {
            "label": int,
            "hazard": str,
            "reason": str,
            "source": str,
            "urgency": str,
            "actuator": {...}
        }
    """

    # =====================================================
    # 1) HARD SAFETY OVERRIDE
    # =====================================================

    # Extreme temperature -> immediate FIRE
    if temp_c >= 90:
        return _build_result(
            label=FIRE,
            reason="Hard override: temperature extremely high",
            source="hard_rule",
            urgency="immediate",
            buzzer=True,
            fan=True,
            mist=True,
            emergency=True,
        )

    # Rapid temperature rise + already hot -> FIRE
    if temp_rise == "high_risk" and temp_c >= 60:
        return _build_result(
            label=FIRE,
            reason="Hard override: rapid heat rise with high temperature",
            source="hard_rule",
            urgency="immediate",
            buzzer=True,
            fan=True,
            mist=True,
            emergency=True,
        )

    # Strong gas pattern on MQ2 with low VOC -> GAS LEAK
    if mq2_hi >= 3.5 and voc_ppm < 120:
        return _build_result(
            label=GAS_LEAK,
            reason="Hard override: strong gas signature on MQ2 with low VOC",
            source="hard_rule",
            urgency="immediate",
            buzzer=True,
            fan=True,
            mist=False,
            emergency=True,
        )

    # VOC extremely high -> severe chemical event
    if voc_ppm >= 900 and temp_c < 50:
        return _build_result(
            label=VOC_CHEMICAL,
            reason="Hard override: VOC extremely high while temperature not yet critical",
            source="hard_rule",
            urgency="immediate",
            buzzer=True,
            fan=True,
            mist=False,
            emergency=True,
        )

    # =====================================================
    # 2) SENSOR PHYSICS INTERPRETATION
    # =====================================================
    # Do NOT default to SAFE here.
    # If no dominant physical pattern appears, keep physics_label = None.

    physics_label = None
    physics_reason = "No dominant physical hazard pattern"

    # Likely chemical vapor / solvent
    if voc_ppm >= 250 and temp_c < 45 and temp_rise == "normal":
        physics_label = VOC_CHEMICAL
        physics_reason = "Physics: high VOC with stable temperature"

    # Likely smoke / degraded air quality
    elif mq135_hi >= 1.8 and mq2_hi < 1.6 and voc_ppm < 180:
        physics_label = SMOKE_AIR
        physics_reason = "Physics: MQ135 elevated with limited gas signature"

    # Likely gas leak (moderate)
    elif mq2_hi >= 2.0 and voc_ppm < 120 and temp_c < 45:
        physics_label = GAS_LEAK
        physics_reason = "Physics: MQ2 elevated with low VOC and no heat buildup"

    # Likely fire pattern even before hard override
    elif temp_c >= 55 and temp_rise in ("caution", "high_risk") and mq2_hi >= 1.8:
        physics_label = FIRE
        physics_reason = "Physics: heat buildup + gas/smoke signature"

    # =====================================================
    # 3) SEVERITY-BASED OVERRIDE / SUPPORT
    # =====================================================

    # Severity indicates very dangerous condition
    if severity_level == "CRITICAL":
        # If strong heat exists, treat as FIRE
        if temp_c >= 55 or temp_rise == "high_risk":
            return _build_result(
                label=FIRE,
                reason=f"Severity override: CRITICAL severity ({severity_score}) with heat evidence",
                source="severity_override",
                urgency="immediate",
                buzzer=True,
                fan=True,
                mist=True,
                emergency=True,
            )

        # If no heat but gas strong -> GAS or VOC depending on dominant signature
        if mq2_hi >= 2.5 and voc_ppm < 150:
            return _build_result(
                label=GAS_LEAK,
                reason=f"Severity override: CRITICAL severity ({severity_score}) with gas-dominant pattern",
                source="severity_override",
                urgency="immediate",
                buzzer=True,
                fan=True,
                mist=False,
                emergency=True,
            )

        if voc_ppm >= 250:
            return _build_result(
                label=VOC_CHEMICAL,
                reason=f"Severity override: CRITICAL severity ({severity_score}) with VOC-dominant pattern",
                source="severity_override",
                urgency="immediate",
                buzzer=True,
                fan=True,
                mist=False,
                emergency=True,
            )

    # Severity HIGH but not enough for hard emergency
    if severity_level == "HIGH" and physics_label is not None:
        return _build_result(
            label=physics_label,
            reason=f"{physics_reason} | Severity support: HIGH ({severity_score})",
            source="physics",
            urgency="confirm",
            buzzer=True,
            fan=(physics_label in [GAS_LEAK, VOC_CHEMICAL, SMOKE_AIR, FIRE]),
            mist=(physics_label == FIRE),
            emergency=False,
        )

    # =====================================================
    # 4) ML SANITY CHECK
    # =====================================================

    # ML says FIRE but no heat evidence -> likely smoke, not confirmed fire
    if ml_label == FIRE and temp_c < 45 and temp_rise == "normal":
        return _build_result(
            label=SMOKE_AIR,
            reason="ML sanity check: ML predicted FIRE but no supporting thermal evidence",
            source="ml",
            urgency="confirm",
            buzzer=True,
            fan=True,
            mist=False,
            emergency=False,
        )

    # ML says SAFE but sensor strongly suggests gas
    if ml_label == SAFE and mq2_hi >= 2.0 and voc_ppm < 120:
        return _build_result(
            label=GAS_LEAK,
            reason="ML sanity check: SAFE overridden by gas-dominant MQ2 pattern",
            source="physics",
            urgency="confirm",
            buzzer=True,
            fan=True,
            mist=False,
            emergency=True,
        )

    # ML says SAFE but thermal pattern is dangerous
    if ml_label == SAFE and temp_c >= 55 and temp_rise in ("caution", "high_risk"):
        return _build_result(
            label=FIRE,
            reason="ML sanity check: SAFE overridden by dangerous thermal pattern",
            source="physics",
            urgency="immediate",
            buzzer=True,
            fan=True,
            mist=True,
            emergency=True,
        )

    # =====================================================
    # 5) FINAL FUSION DECISION
    # =====================================================

    # If physics has a meaningful interpretation, prefer it over ML
    if physics_label is not None:
        if physics_label == FIRE:
            return _build_result(
                label=physics_label,
                reason=f"{physics_reason} | Physics accepted over ML",
                source="physics",
                urgency="confirm",
                buzzer=True,
                fan=True,
                mist=True,
                emergency=True,
            )

        if physics_label == GAS_LEAK:
            return _build_result(
                label=physics_label,
                reason=f"{physics_reason} | Physics accepted over ML",
                source="physics",
                urgency="confirm",
                buzzer=True,
                fan=True,
                mist=False,
                emergency=True,
            )

        if physics_label == VOC_CHEMICAL:
            return _build_result(
                label=physics_label,
                reason=f"{physics_reason} | Physics accepted over ML",
                source="physics",
                urgency="confirm",
                buzzer=True,
                fan=True,
                mist=False,
                emergency=True,
            )

        if physics_label == SMOKE_AIR:
            return _build_result(
                label=physics_label,
                reason=f"{physics_reason} | Physics accepted over ML",
                source="physics",
                urgency="confirm",
                buzzer=True,
                fan=True,
                mist=False,
                emergency=False,
            )

    # If no dominant physics pattern, use ML result
    if ml_label == FIRE:
        return _build_result(
            label=FIRE,
            reason=f"ML accepted | severity={severity_score}, action={action_level}",
            source="ml",
            urgency="confirm",
            buzzer=True,
            fan=True,
            mist=True,
            emergency=True,
        )

    if ml_label == GAS_LEAK:
        return _build_result(
            label=GAS_LEAK,
            reason=f"ML accepted | severity={severity_score}, action={action_level}",
            source="ml",
            urgency="confirm",
            buzzer=True,
            fan=True,
            mist=False,
            emergency=True,
        )

    if ml_label == VOC_CHEMICAL:
        return _build_result(
            label=VOC_CHEMICAL,
            reason=f"ML accepted | severity={severity_score}, action={action_level}",
            source="ml",
            urgency="confirm",
            buzzer=True,
            fan=True,
            mist=False,
            emergency=True,
        )

    if ml_label == SMOKE_AIR:
        return _build_result(
            label=SMOKE_AIR,
            reason=f"ML accepted | severity={severity_score}, action={action_level}",
            source="ml",
            urgency="confirm",
            buzzer=True,
            fan=True,
            mist=False,
            emergency=False,
        )

    # SAFE default
    return _build_result(
        label=SAFE,
        reason=f"ML accepted safe state | severity={severity_score}, action={action_level}",
        source="ml",
        urgency="monitor",
        buzzer=False,
        fan=False,
        mist=False,
        emergency=False,
    )
