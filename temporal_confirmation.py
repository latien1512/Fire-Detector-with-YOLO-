SAFE = 0

class TemporalConfirmation:
    def __init__(self, safe_confirm_count: int = 5, hazard_confirm_count: int = 3):
        self.safe_confirm_count = safe_confirm_count
        self.hazard_confirm_count = hazard_confirm_count

        self.last_seen_label = None
        self.current_streak = 0

        self.confirmed_label = SAFE
        self.confirmed_hazard = "SAFE"
        self.confirmed_reason = "Initial safe state"
        self.confirmed_source = "init"
        self.confirmed_urgency = "monitor"

        self.confirmed_actuator = {
            "buzzer": False,
            "fan": False,
            "mist": False,
            "emergency": False,
            "relay_active": False,
        }

    def update(self, fusion_result: dict) -> dict:

        instant_label = int(fusion_result["label"])
        instant_hazard = fusion_result["hazard"]
        instant_reason = fusion_result["reason"]
        instant_source = fusion_result["source"]
        instant_urgency = fusion_result["urgency"]
        instant_actuator = fusion_result["actuator"]


        # 1) Update streak
        if instant_label == self.last_seen_label:
            self.current_streak += 1
        else:
            self.last_seen_label = instant_label
            self.current_streak = 1


        # 2) Immediate actions for urgency == immediate
        if instant_urgency == "immediate" and instant_label != SAFE:
            self.confirmed_label = instant_label
            self.confirmed_hazard = instant_hazard
            self.confirmed_reason = instant_reason
            self.confirmed_source = instant_source
            self.confirmed_urgency = instant_urgency

            self.confirmed_actuator = {
                **instant_actuator,
                "relay_active": True
            }

            return {
                "instant_label": instant_label,
                "instant_hazard": instant_hazard,
                "confirmed_label": self.confirmed_label,
                "confirmed_hazard": self.confirmed_hazard,
                "confirmed_reason": self.confirmed_reason,
                "confirmed_source": self.confirmed_source,
                "confirmed_urgency": self.confirmed_urgency,
                "streak": self.current_streak,
                "required_count": 1,
                "relay_active": True,
                "actuator": self.confirmed_actuator,
            }


        # 3) SAFE requires 5 consecutive samples to clear/reset
        if instant_label == SAFE:
            required_count = self.safe_confirm_count

            if self.current_streak >= required_count:
                self.confirmed_label = SAFE
                self.confirmed_hazard = "SAFE"
                self.confirmed_reason = f"SAFE confirmed for {required_count} consecutive samples"
                self.confirmed_source = "temporal"
                self.confirmed_urgency = "monitor"
                self.confirmed_actuator = {
                    "buzzer": False,
                    "fan": False,
                    "mist": False,
                    "emergency": False,
                    "relay_active": False,
                }

            return {
                "instant_label": instant_label,
                "instant_hazard": instant_hazard,
                "confirmed_label": self.confirmed_label,
                "confirmed_hazard": self.confirmed_hazard,
                "confirmed_reason": self.confirmed_reason,
                "confirmed_source": self.confirmed_source,
                "confirmed_urgency": self.confirmed_urgency,
                "streak": self.current_streak,
                "required_count": required_count,
                "relay_active": self.confirmed_actuator["relay_active"],
                "actuator": self.confirmed_actuator,
            }


        # 4) Non-safe hazards require 3 consecutive samples
        required_count = self.hazard_confirm_count

        if self.current_streak >= required_count:
            self.confirmed_label = instant_label
            self.confirmed_hazard = instant_hazard
            self.confirmed_reason = (
                f"{instant_reason} | confirmed for {required_count} consecutive samples"
            )
            self.confirmed_source = f"{instant_source}+temporal"
            self.confirmed_urgency = "confirmed"

            self.confirmed_actuator = {
                **instant_actuator,
                "relay_active": True
            }

        return {
            "instant_label": instant_label,
            "instant_hazard": instant_hazard,
            "confirmed_label": self.confirmed_label,
            "confirmed_hazard": self.confirmed_hazard,
            "confirmed_reason": self.confirmed_reason,
            "confirmed_source": self.confirmed_source,
            "confirmed_urgency": self.confirmed_urgency,
            "streak": self.current_streak,
            "required_count": required_count,
            "relay_active": self.confirmed_actuator["relay_active"],
            "actuator": self.confirmed_actuator,
        }