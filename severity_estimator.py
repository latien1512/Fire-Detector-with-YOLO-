from typing import Dict, Any

# Helpers
def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def trimf(x: float, a: float, b: float, c: float) -> float:
    """Triangular membership function."""
    if x <= a or x >= c:
        return 0.0
    if x == b:
        return 1.0
    if a < x < b:
        return 1.0 if b == a else (x - a) / (b - a)
    if b < x < c:
        return 1.0 if c == b else (c - x) / (c - b)
    return 0.0


def trapmf(x: float, a: float, b: float, c: float, d: float) -> float:
    """Trapezoidal membership function."""
    if x <= a or x >= d:
        return 0.0
    if b <= x <= c:
        return 1.0
    if a < x < b:
        return 1.0 if b == a else (x - a) / (b - a)
    if c < x < d:
        return 1.0 if d == c else (d - x) / (d - c)
    return 0.0


# Fuzzification
def fuzzify_temperature(temp_c: float) -> Dict[str, float]:
    return {
        "low": trapmf(temp_c, 0, 0, 32, 38),
        "medium": trimf(temp_c, 36, 45, 55),
        "high": trimf(temp_c, 50, 62, 70),
        "very_high": trapmf(temp_c, 67, 85, 150, 150),
    }


def fuzzify_mq2(mq2_hi: float) -> Dict[str, float]:
    return {
        "low": trapmf(mq2_hi, 0.0, 0.0, 1.0, 1.50),
        "medium": trimf(mq2_hi, 1.45, 1.60, 2.0),
        "high": trimf(mq2_hi, 1.80, 2.50, 3.20),
        "very_high": trapmf(mq2_hi, 3.0, 3.60, 10.0, 10.0),
    }


def fuzzify_mq135(mq135_hi: float) -> Dict[str, float]:
    return {
        "low": trapmf(mq135_hi, 0.0, 0.0, 1.0, 1.50),
        "medium": trimf(mq135_hi, 1.45, 1.60, 2.0),
        "high": trimf(mq135_hi, 1.80, 2.50, 3.20),
        "very_high": trapmf(mq135_hi, 3.0, 3.60, 10.0, 10.0),
    }


def fuzzify_voc(voc_ppm: float) -> Dict[str, float]:
    return {
        "low": trapmf(voc_ppm, 0, 0, 55, 100),
        "medium": trimf(voc_ppm, 85, 140, 240),
        "high": trimf(voc_ppm, 200, 320, 450),
        "very_high": trapmf(voc_ppm, 420, 600, 2000, 2000),
    }


def fuzzify_heat_rise(heat_rise: str) -> Dict[str, float]:
    hr = (heat_rise or "").strip().lower()
    return {
        "normal": 1.0 if hr == "normal" else 0.0,
        "caution": 1.0 if hr == "caution" else 0.0,
        "high_risk": 1.0 if hr == "high_risk" else 0.0,
    }


# Severity centroids for defuzzification
SEVERITY_CENTROIDS = {
    "low": 18.0,
    "medium": 45.0,
    "high": 72.0,
    "critical": 93.0,
}


# Main estimator
def estimate_severity(
    temperature_c: float,
    heat_rise: str,
    mq2_hi: float,
    mq135_hi: float,
    voc_ppm: float,
) -> Dict[str, Any]:


    # Hard safety overrides
    if temperature_c >= 65:
        return _build_override_result(
            score=98.0,
            level="CRITICAL",
            action="EMERGENCY",
            reason="hard override: temperature extremely high",
            temperature_c=temperature_c,
            heat_rise=heat_rise,
            mq2_hi=mq2_hi,
            mq135_hi=mq135_hi,
            voc_ppm=voc_ppm,
        )

    if heat_rise == "high_risk" and temperature_c >= 50:
        return _build_override_result(
            score=96.0,
            level="CRITICAL",
            action="EMERGENCY",
            reason="hard override: rapid heat rise with high temperature",
            temperature_c=temperature_c,
            heat_rise=heat_rise,
            mq2_hi=mq2_hi,
            mq135_hi=mq135_hi,
            voc_ppm=voc_ppm,
        )

    if mq2_hi >= 4.0 and voc_ppm < 120:
        return _build_override_result(
            score=95.0,
            level="CRITICAL",
            action="EMERGENCY",
            reason="hard override: severe gas pattern on MQ2",
            temperature_c=temperature_c,
            heat_rise=heat_rise,
            mq2_hi=mq2_hi,
            mq135_hi=mq135_hi,
            voc_ppm=voc_ppm,
        )

    if voc_ppm >= 400:
        return _build_override_result(
            score=94.0,
            level="CRITICAL",
            action="EMERGENCY",
            reason="hard override: voc extremely high",
            temperature_c=temperature_c,
            heat_rise=heat_rise,
            mq2_hi=mq2_hi,
            mq135_hi=mq135_hi,
            voc_ppm=voc_ppm,
        )


    # Fuzzification
    temp = fuzzify_temperature(temperature_c)
    mq2 = fuzzify_mq2(mq2_hi)
    mq135 = fuzzify_mq135(mq135_hi)
    voc = fuzzify_voc(voc_ppm)
    rise = fuzzify_heat_rise(heat_rise)

    temp_h = max(temp["high"], temp["very_high"])
    mq2_h = max(mq2["high"], mq2["very_high"])
    mq135_h = max(mq135["high"], mq135["very_high"])
    voc_h = max(voc["high"], voc["very_high"])


    # Rule base
    rules = {}

    # SAFE / LOW
    rules["all_low"] = min(
        temp["low"], mq2["low"], mq135["low"], voc["low"], rise["normal"]
    )

    # MEDIUM
    rules["temp_medium"] = temp["medium"]
    rules["mq2_medium"] = mq2["medium"]
    rules["mq135_medium"] = mq135["medium"]
    rules["voc_medium"] = voc["medium"]
    rules["heat_rise_caution"] = rise["caution"]

    # HIGH — one strong phenomenon can be enough
    rules["temp_high"] = temp_h
    rules["mq2_high"] = mq2_h
    rules["mq135_high"] = mq135_h
    rules["voc_high"] = voc_h
    rules["heat_rise_high_risk"] = rise["high_risk"]

    # HIGH — two-signal combinations
    rules["temp_and_mq2_high"] = min(temp_h, mq2_h)
    rules["temp_and_mq135_high"] = min(temp_h, mq135_h)
    rules["temp_and_voc_high"] = min(temp_h, voc_h)
    rules["mq2_and_mq135_high"] = min(mq2_h, mq135_h)
    rules["mq2_and_voc_high"] = min(mq2_h, voc_h)
    rules["mq135_and_voc_high"] = min(mq135_h, voc_h)

    # CRITICAL — clear danger patterns
    rules["temp_very_high_and_heat_rise_high"] = min(temp["very_high"], rise["high_risk"])
    rules["mq2_very_high_and_temp_high"] = min(mq2["very_high"], temp_h)
    rules["mq135_very_high_and_temp_high"] = min(mq135["very_high"], temp_h)
    rules["voc_very_high_and_temp_high"] = min(voc["very_high"], temp_h)

    # CRITICAL — 3 or 4 sensors high
    high_list = [temp_h, mq2_h, mq135_h, voc_h]
    high_list_sorted = sorted(high_list, reverse=True)
    rules["three_sensors_high"] = high_list_sorted[2]
    rules["all_four_high"] = min(high_list)

    # Pattern-based CRITICAL rules
    rules["possible_fire_pattern"] = min(temp_h, mq2_h, rise["high_risk"])
    rules["possible_smoke_fire_pattern"] = min(temp_h, mq135_h, rise["high_risk"])
    rules["possible_chemical_pattern"] = min(voc["very_high"], mq135_h)
    rules["possible_gas_pattern"] = min(mq2["very_high"], max(rise["caution"], rise["high_risk"]))
    rules["temp_vhigh_and_any_gas_high"] = min(temp["very_high"], max(mq2_h, mq135_h, voc_h))


    # Aggregate output classes
    low_strength = rules["all_low"]

    medium_strength = max(
        rules["temp_medium"],
        rules["mq2_medium"],
        rules["mq135_medium"],
        rules["voc_medium"],
        rules["heat_rise_caution"],
    )

    high_strength = max(
        rules["temp_high"],
        rules["mq2_high"],
        rules["mq135_high"],
        rules["voc_high"],
        rules["heat_rise_high_risk"],
        rules["temp_and_mq2_high"],
        rules["temp_and_mq135_high"],
        rules["temp_and_voc_high"],
        rules["mq2_and_mq135_high"],
        rules["mq2_and_voc_high"],
        rules["mq135_and_voc_high"],
    )

    critical_strength = max(
        rules["temp_very_high_and_heat_rise_high"],
        rules["mq2_very_high_and_temp_high"],
        rules["mq135_very_high_and_temp_high"],
        rules["voc_very_high_and_temp_high"],
        rules["three_sensors_high"],
        rules["all_four_high"],
        rules["possible_fire_pattern"],
        rules["possible_smoke_fire_pattern"],
        rules["possible_chemical_pattern"],
        rules["possible_gas_pattern"],
        rules["temp_vhigh_and_any_gas_high"],
    )


    # Defuzzification
    numerator = (
        low_strength * SEVERITY_CENTROIDS["low"] +
        medium_strength * SEVERITY_CENTROIDS["medium"] +
        high_strength * SEVERITY_CENTROIDS["high"] +
        critical_strength * SEVERITY_CENTROIDS["critical"]
    )
    denominator = low_strength + medium_strength + high_strength + critical_strength

    severity_score = 0.0 if denominator == 0 else numerator / denominator
    severity_score = clamp(severity_score, 0.0, 100.0)


    # Crisp label
    if severity_score < 30:
        severity_level = "LOW"
        action_level = "MONITOR"
    elif severity_score < 55:
        severity_level = "MEDIUM"
        action_level = "ALERT"
    elif severity_score < 80:
        severity_level = "HIGH"
        action_level = "INTERVENE"
    else:
        severity_level = "CRITICAL"
        action_level = "EMERGENCY"


    # Reason generation
    reasons = []

    if rise["high_risk"] > 0.5:
        reasons.append("rapid temperature rise")
    elif rise["caution"] > 0.5:
        reasons.append("temperature rising")

    if temp["very_high"] > 0.4:
        reasons.append("temperature very high")
    elif temp["high"] > 0.4:
        reasons.append("temperature high")

    if mq2["very_high"] > 0.4:
        reasons.append("mq2 very high")
    elif mq2["high"] > 0.4:
        reasons.append("mq2 high")

    if mq135["very_high"] > 0.4:
        reasons.append("mq135 very high")
    elif mq135["high"] > 0.4:
        reasons.append("mq135 high")

    if voc["very_high"] > 0.4:
        reasons.append("voc very high")
    elif voc["high"] > 0.4:
        reasons.append("voc high")

    if rules["three_sensors_high"] > 0.4:
        reasons.append("multiple sensors high")

    if not reasons:
        reasons.append("mostly low-risk condition")

    reason = ", ".join(reasons)

    return {
        "severity_score": round(severity_score, 2),
        "severity_level": severity_level,
        "action_level": action_level,
        "reason": reason,
        "memberships": {
            "temperature": {k: round(v, 3) for k, v in temp.items()},
            "mq2": {k: round(v, 3) for k, v in mq2.items()},
            "mq135": {k: round(v, 3) for k, v in mq135.items()},
            "voc": {k: round(v, 3) for k, v in voc.items()},
            "heat_rise": {k: round(v, 3) for k, v in rise.items()},
            "output": {
                "low": round(low_strength, 3),
                "medium": round(medium_strength, 3),
                "high": round(high_strength, 3),
                "critical": round(critical_strength, 3),
            },
        },
        "rule_strengths": {k: round(v, 3) for k, v in rules.items()},
    }

# Hard override result builder
def _build_override_result(
    score: float,
    level: str,
    action: str,
    reason: str,
    temperature_c: float,
    heat_rise: str,
    mq2_hi: float,
    mq135_hi: float,
    voc_ppm: float,
) -> Dict[str, Any]:
    return {
        "severity_score": round(score, 2),
        "severity_level": level,
        "action_level": action,
        "reason": reason,
        "memberships": {
            "temperature": {k: round(v, 3) for k, v in fuzzify_temperature(temperature_c).items()},
            "mq2": {k: round(v, 3) for k, v in fuzzify_mq2(mq2_hi).items()},
            "mq135": {k: round(v, 3) for k, v in fuzzify_mq135(mq135_hi).items()},
            "voc": {k: round(v, 3) for k, v in fuzzify_voc(voc_ppm).items()},
            "heat_rise": {k: round(v, 3) for k, v in fuzzify_heat_rise(heat_rise).items()},
            "output": {
                "low": 0.0,
                "medium": 0.0,
                "high": 0.0,
                "critical": 1.0,
            },
        },
        "rule_strengths": {
            "hard_override": 1.0
        },
    }


# Optional wrapper for easier integration
def estimate_severity_from_dict(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    return estimate_severity(
        temperature_c=float(sensor_data.get("temperature_c", 0.0)),
        heat_rise=str(sensor_data.get("heat_rise", "normal")),
        mq2_hi=float(sensor_data.get("mq2_hi", 0.0)),
        mq135_hi=float(sensor_data.get("mq135_hi", 0.0)),
        voc_ppm=float(sensor_data.get("voc_ppm", 0.0)),
    )
