import os
import sys
import json
import signal
from datetime import datetime
from collections import deque
import csv

os.environ["QT_QPA_PLATFORM"] = "wayland"
signal.signal(signal.SIGINT, signal.SIG_DFL)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

import pyqtgraph as pg
import pyqtgraph.exporters


STATE_FILE = "/dev/shm/realtime_state.json"
HISTORY_CSV = "/home/pi/logs/fire_realtime_ml.csv"
MANUAL_FILE = "/home/pi/Desktop/Smart_HMI/manual_control.json"


# ================= STYLE =================

BG = "#20232b"
PANEL = "#272b35"
PANEL_2 = "#1f232c"
BORDER = "#3a4050"
TEXT = "#e6edf7"
MUTED = "#8d99ae"
GREEN = "#24f27e"
BLUE = "#3b82f6"
RED = "#ef233c"
ORANGE = "#ff9f1c"


class Card(QFrame):
    def __init__(self, title, value="---", subtitle=""):
        super().__init__()
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)

        self.title = QLabel(title.upper())
        self.title.setFont(QFont("Arial", 8))
        self.title.setStyleSheet(f"color:{MUTED}; letter-spacing:1px;")

        self.value = QLabel(value)
        self.value.setFont(QFont("Arial", 22, QFont.Bold))
        self.value.setStyleSheet(f"color:{TEXT};")

        self.subtitle = QLabel(subtitle)
        self.subtitle.setFont(QFont("Arial", 8))
        self.subtitle.setStyleSheet(f"color:{MUTED};")

        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.subtitle)

    def set_data(self, value, subtitle="", color=TEXT):
        self.value.setText(str(value))
        self.subtitle.setText(str(subtitle))
        self.value.setStyleSheet(f"color:{color};")


class SmallStatus(QLabel):
    def __init__(self, text="SAFE"):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(QFont("Arial", 8, QFont.Bold))
        self.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(36,242,126,0.15);
                color: {GREEN};
                border: 1px solid rgba(36,242,126,0.5);
                border-radius: 10px;
                padding: 4px 10px;
            }}
        """)

    def set_state(self, text, color=GREEN):
        self.setText(text)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(255,255,255,0.06);
                color: {color};
                border: 1px solid {color};
                border-radius: 10px;
                padding: 4px 10px;
            }}
        """)


class SmartFireHMI(QMainWindow):
    def write_manual_state(self):
        data = {
            "mode": "MANUAL" if self.mode_btn.isChecked() else "AUTO",

            "buzzer": self.btn_buzzer.isChecked(),
            "fan": self.btn_fan.isChecked(),
            "mist": self.btn_mist.isChecked(),
            "emergency": self.btn_emergency.isChecked()
        }

        try:
            with open(MANUAL_FILE, "w") as f:
                json.dump(data, f)

        except Exception as e:
            print("WRITE MANUAL ERROR:", e)
        
    def toggle_mode(self):
        if self.mode_btn.isChecked():
            # AUTO -> MANUAL
            self.mode_btn.setText("Manual mode")

            self.mode_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(239,35,60,0.18);
                    color: {RED};
                    border: 1px solid {RED};
                    border-radius: 10px;
                    padding: 10px;
                    font-weight: bold;
                    text-align:left;
                }}
            """)

            # Copy trạng thái relay hiện tại từ hệ thống sang manual
            buzzer = bool(self.latest_state.get("buzzer", False))
            fan = bool(self.latest_state.get("fan", False))
            mist = bool(self.latest_state.get("mist", False))
            emergency = bool(self.latest_state.get("emergency", False))

            self.btn_buzzer.setChecked(buzzer)
            self.btn_fan.setChecked(fan)
            self.btn_mist.setChecked(mist)
            self.btn_emergency.setChecked(emergency)

            self.update_manual_button(self.btn_buzzer, "Buzzer", buzzer, write=False)
            self.update_manual_button(self.btn_fan, "Fan", fan, write=False)
            self.update_manual_button(self.btn_mist, "Mist", mist, write=False)
            self.update_manual_button(self.btn_emergency, "Emergency", emergency, write=False)

        else:
            # MANUAL -> AUTO
            self.mode_btn.setText("Auto mode")

            self.mode_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(36,242,126,0.14);
                    color: {GREEN};
                    border: 1px solid {GREEN};
                    border-radius: 10px;
                    padding: 10px;
                    font-weight: bold;
                    text-align:left;
                }}
            """)

        self.write_manual_state()
        
    def force_off_all(self):
        # Return to AUTO mode
        self.mode_btn.setChecked(False)
        self.mode_btn.setText("Auto mode")

        self.mode_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(36,242,126,0.14);
                color: {GREEN};
                border: 1px solid {GREEN};
                border-radius: 10px;
                padding: 10px;
                font-weight: bold;
                text-align:left;
            }}
        """)

        # Turn off all manual relay buttons
        self.btn_buzzer.setChecked(False)
        self.btn_fan.setChecked(False)
        self.btn_mist.setChecked(False)
        self.btn_emergency.setChecked(False)

        self.update_manual_button(self.btn_buzzer, "Buzzer", False)
        self.update_manual_button(self.btn_fan, "Fan", False)
        self.update_manual_button(self.btn_mist, "Mist", False)
        self.update_manual_button(self.btn_emergency, "Emergency", False)

        # Write AUTO + all OFF to manual_control.json
        self.write_manual_state()

        # Optional event log message
        try:
            self.event_items.insert(
                0,
                datetime.now().strftime("%H:%M:%S") + "   MANUAL CONTROL   Force off all and returned to AUTO"
            )
            self.event_items = self.event_items[:5]
            self.event_log.setText("◷  EVENT LOG\n\n" + "\n\n".join(self.event_items))
        except:
            pass
            
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Smart PCCC - AI Fire Detection")
        self.resize(1450, 900)

        self.temp_hist = deque(maxlen=60)
        self.mq2_hist = deque(maxlen=60)
        self.mq135_hist = deque(maxlen=60)
        self.voc_hist = deque(maxlen=60)
        
        self.latest_state = {}
        self.history_mode = False       # HISTORY MODE 
        
        # ================= EVENT LOG =================
        self.last_event_status = None
        self.event_items = []

        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(14)

        # ================= HEADER =================
        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title = QLabel("SMART FIRE MONITORING")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setStyleSheet(f"color:{TEXT};")

        subtitle = QLabel("AI Fire Detection · Raspberry Pi 5")
        subtitle.setFont(QFont("Arial", 9))
        subtitle.setStyleSheet(f"color:{MUTED};")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.mqtt_status = SmallStatus("● Connecting...")
        self.pi_status = SmallStatus("● pi01 online")
        self.clock = QLabel("--:--:--")
        self.clock.setStyleSheet(f"color:{MUTED};")
        self.clock.setFont(QFont("Arial", 10))

        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self.mqtt_status)
        header.addWidget(self.pi_status)
        header.addWidget(self.clock)

        root.addLayout(header)

        # ================= STATUS BANNER =================
        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(22, 18, 22, 18)

        self.status_big = QLabel("SAFE")
        self.status_big.setFont(QFont("Arial", 28, QFont.Bold))
        self.status_big.setStyleSheet(f"color:{GREEN};")

        self.reason = QLabel("System initialized.")
        self.reason.setFont(QFont("Arial", 13, QFont.Bold))
        self.reason.setStyleSheet(f"color:{TEXT};")

        status_text = QVBoxLayout()
        status_text.addWidget(self.status_big)
        status_text.addWidget(self.reason)

        self.action_badge = SmallStatus("monitor")

        banner_layout.addLayout(status_text)
        banner_layout.addStretch()
        banner_layout.addWidget(self.action_badge)

        root.addWidget(self.banner)

        # ================= MAIN GRID =================
        grid = QGridLayout()
        grid.setSpacing(12)

        self.temp_card = Card("Temperature", "--- °C", "normal")
        self.mq2_card = Card("MQ2 Gas", "---", "normal · HI ratio")
        self.mq135_card = Card("MQ135 Air", "---", "normal · HI ratio")
        self.voc_card = Card("VOC", "--- ppm", "safe range")

        grid.addWidget(self.temp_card, 0, 0)
        grid.addWidget(self.mq2_card, 0, 1)
        grid.addWidget(self.mq135_card, 0, 2)
        grid.addWidget(self.voc_card, 0, 3)
        
        for i in range(4):
            grid.setColumnStretch(i, 1)

        self.temp_card.setMinimumHeight(95)
        self.mq2_card.setMinimumHeight(95)
        self.mq135_card.setMinimumHeight(95)
        self.voc_card.setMinimumHeight(95)
        # ================= SEVERITY PANEL =================
        self.severity_panel = QFrame()
        self.severity_panel.setObjectName("Panel")
        sev_layout = QVBoxLayout(self.severity_panel)

        sev_title = QLabel("◎  SEVERITY LEVEL")
        sev_title.setStyleSheet(f"color:{MUTED};")
        sev_title.setFont(QFont("Arial", 9))

        self.sev_value = QLabel("LOW")
        self.sev_value.setFont(QFont("Arial", 26, QFont.Bold))
        self.sev_value.setStyleSheet(f"color:{GREEN};")

        self.sev_score = QLabel("0 / 100")
        self.sev_score.setFont(QFont("Arial", 22, QFont.Bold))
        self.sev_score.setStyleSheet(f"color:{GREEN};")

        self.sev_action = QLabel("MONITOR")
        self.sev_action.setFont(QFont("Arial", 11, QFont.Bold))
        self.sev_action.setStyleSheet(f"color:{GREEN};")

        self.sev_reason = QLabel("Mostly low-risk condition.")
        self.sev_reason.setWordWrap(True)
        self.sev_reason.setFont(QFont("Arial", 12))
        self.sev_reason.setStyleSheet(f"color:{TEXT}; line-height: 130%;")

        sev_layout.addWidget(sev_title)
        sev_layout.addStretch()
        sev_layout.addWidget(self.sev_score)
        sev_layout.addWidget(self.sev_value)
        sev_layout.addWidget(self.sev_action)
        sev_layout.addStretch()
        sev_layout.addWidget(self.sev_reason)

        grid.addWidget(self.severity_panel, 1, 0)

        # ================= AI PANEL =================
        self.ai_panel = QFrame()
        self.ai_panel.setObjectName("Panel")
        ai_layout = QVBoxLayout(self.ai_panel)

        ai_title = QLabel("⚙  AI DECISION")
        ai_title.setStyleSheet(f"color:{MUTED};")
        ai_title.setFont(QFont("Arial", 9))

        self.ml_row = self.decision_row("ML prediction")
        self.fusion_row = self.decision_row("Fusion result")
        self.yolo_row = self.decision_row("YOLO camera")

        self.ai_reason = QLabel("---")
        self.ai_reason.setWordWrap(True)
        self.ai_reason.setAlignment(Qt.AlignCenter)
        self.ai_reason.setFont(QFont("Arial", 11))
        self.ai_reason.setStyleSheet(f"color:{TEXT};")

        ai_layout.addWidget(ai_title)
        ai_layout.addWidget(self.ml_row["frame"])
        ai_layout.addWidget(self.fusion_row["frame"])
        ai_layout.addWidget(self.yolo_row["frame"])
        ai_layout.addStretch()
        ai_layout.addWidget(self.ai_reason)

        grid.addWidget(self.ai_panel, 1, 1)

        # ================= TEMPORAL + RELAY =================
        self.temporal_panel = QFrame()
        self.temporal_panel.setObjectName("Panel")
        t_layout = QVBoxLayout(self.temporal_panel)

        t_title = QLabel("◷  TEMPORAL CONFIRMATION")
        t_title.setStyleSheet(f"color:{MUTED};")
        t_title.setFont(QFont("Arial", 9))

        self.temporal_status = QLabel("SAFE")
        self.temporal_status.setAlignment(Qt.AlignCenter)
        self.temporal_status.setFont(QFont("Arial", 26, QFont.Bold))
        self.temporal_status.setStyleSheet(f"color:{GREEN};")

        self.streak_label = QLabel("5 / 5 samples")
        self.streak_label.setAlignment(Qt.AlignCenter)
        self.streak_label.setStyleSheet(f"color:{MUTED};")
        
        self.temporal_reason = QLabel("---")
        self.temporal_reason.setAlignment(Qt.AlignCenter)
        self.temporal_reason.setWordWrap(True)

        self.temporal_reason.setFont(QFont("Arial", 11))

        self.temporal_reason.setStyleSheet(f"""
            color:{TEXT};
            padding:6px;
        """)

        relay_title = QLabel("⌁  RELAY / ACTUATORS")
        relay_title.setStyleSheet(f"color:{MUTED};")

        relay_grid = QGridLayout()
        self.buzzer = self.relay_badge("Buzzer")
        self.fan = self.relay_badge("Fan")
        self.mist = self.relay_badge("Mist")
        self.emergency = self.relay_badge("Emergency")

        relay_grid.addWidget(self.buzzer["frame"], 0, 0)
        relay_grid.addWidget(self.fan["frame"], 0, 1)
        relay_grid.addWidget(self.mist["frame"], 1, 0)
        relay_grid.addWidget(self.emergency["frame"], 1, 1)

        t_layout.addWidget(t_title)
        t_layout.addWidget(self.temporal_status)
        t_layout.addWidget(self.streak_label)
        t_layout.addWidget(self.temporal_reason)
        t_layout.addSpacing(8)
        t_layout.addWidget(relay_title)
        t_layout.addLayout(relay_grid)

        grid.addWidget(self.temporal_panel, 1, 2, 1, 2)

        # ================= TREND PANEL =================
        self.trend_panel = QFrame()
        self.trend_panel.setObjectName("Panel")
        trend_layout = QVBoxLayout(self.trend_panel)

        trend_title = QLabel("▥  REALTIME TREND")
        trend_title.setStyleSheet(f"color:{MUTED};")
        trend_title.setFont(QFont("Arial", 9))

        self.graph = pg.PlotWidget()
        self.graph.setBackground(PANEL_2)
        self.graph.showGrid(x=True, y=True, alpha=0.25)
        self.graph.setLabel("left", "Value")
        self.graph.setLabel("bottom", "Samples")
        self.graph.addLegend()

        self.temp_curve = self.graph.plot(pen=pg.mkPen("#ff4d4d", width=2), name="Temp")
        self.mq2_curve = self.graph.plot(pen=pg.mkPen("#ffb703", width=2), name="MQ2")
        self.mq135_curve = self.graph.plot(pen=pg.mkPen("#38bdf8", width=2), name="MQ135")
        self.voc_curve = self.graph.plot(pen=pg.mkPen("#24f27e", width=2), name="VOC/10")

        self.payload = QLabel("{}")
        self.payload.setWordWrap(True)
        self.payload.setStyleSheet(f"""
            QLabel {{
                background-color:{PANEL_2};
                color:#9bd1ff;
                border-radius:8px;
                padding:10px;
                font-family:monospace;
                font-size:9px;
            }}
        """)

        trend_layout.addWidget(trend_title)
        trend_layout.addWidget(self.graph)
        trend_layout.addWidget(QLabel("‹›  LAST MQTT PAYLOAD"))
        trend_layout.addWidget(self.payload)

        grid.addWidget(self.trend_panel, 2, 0, 1, 2)

        # ================= MANUAL PANEL =================
        self.manual_panel = QFrame()
        self.manual_panel.setObjectName("Panel")
        m_layout = QVBoxLayout(self.manual_panel)

        m_title = QLabel("☚  MANUAL RELAY CONTROL")
        m_title.setStyleSheet(f"color:{MUTED};")
        m_title.setFont(QFont("Arial", 9))

        self.mode_btn = QPushButton("Auto mode")
        self.mode_btn.clicked.connect(self.toggle_mode)
        self.mode_btn.setCheckable(True)
        self.mode_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(36,242,126,0.14);
                color: {GREEN};
                border: 1px solid {GREEN};
                border-radius: 10px;
                padding: 10px;
                font-weight: bold;
                text-align:left;
            }}
        """)

        self.btn_buzzer = self.manual_button("Buzzer")
        self.btn_fan = self.manual_button("Fan")
        self.btn_mist = self.manual_button("Mist")
        self.btn_emergency = self.manual_button("Emergency")

        self.force_off = QPushButton("⏻  Force off all + return to auto")
        self.force_off.setStyleSheet(self.force_button_style())
        self.force_off.clicked.connect(self.force_off_all)

        self.event_log = QLabel("◷  EVENT LOG\n-- waiting --")
        self.event_log.setWordWrap(True)
        self.event_log.setStyleSheet(f"""
            color:{TEXT};
            font-size:11px;
        """)

        m_layout.addWidget(m_title)
        m_layout.addWidget(self.mode_btn)
        m_layout.addWidget(self.btn_buzzer)
        m_layout.addWidget(self.btn_fan)
        m_layout.addWidget(self.btn_mist)
        m_layout.addWidget(self.btn_emergency)
        m_layout.addWidget(self.force_off)
        m_layout.addWidget(self.event_log)
        
        # ================= HISTORY BUTTONS =================

        self.load_history_btn = QPushButton("Load Historical Trend")

        self.load_history_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255,159,28,0.12);
                color: {ORANGE};
                border: 1px solid {ORANGE};
                border-radius: 10px;
                padding: 10px;
                font-weight: bold;
            }}
        """)

        self.load_history_btn.clicked.connect(self.load_history_chart)

        self.back_realtime_btn = QPushButton("↻ Back to Realtime")

        self.back_realtime_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(36,242,126,0.12);
                color: {GREEN};
                border: 1px solid {GREEN};
                border-radius: 10px;
                padding: 10px;
                font-weight: bold;
            }}
        """)

        self.back_realtime_btn.clicked.connect(self.back_to_realtime)

        m_layout.addWidget(self.load_history_btn)
        m_layout.addWidget(self.back_realtime_btn)
        
        # ================= EXPORT CHART BUTTON =================
        self.export_chart_btn = QPushButton("Export Trend Chart")
        self.export_chart_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0,180,255,0.12);
                color: {BLUE};
                border: 1px solid {BLUE};
                border-radius: 10px;
                padding: 10px;
                font-weight: bold;
            }}

            QPushButton:hover {{
                background-color: rgba(0,180,255,0.22);
            }}
        """)
        self.export_chart_btn.clicked.connect(self.export_trend_chart)

        m_layout.addWidget(self.export_chart_btn)

        grid.addWidget(self.manual_panel, 2, 2, 1, 2)

        root.addLayout(grid)

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {BG};
            }}
            QFrame#Card, QFrame#Panel {{
                background-color: {PANEL};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
            QFrame#Banner {{
                background-color: rgba(36,242,126,0.08);
                border: 1px solid {GREEN};
                border-radius: 14px;
            }}
            QLabel {{
                color: {TEXT};
            }}
        """)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(1000)

    # ================= COMPONENTS =================

    def decision_row(self, name):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color:{PANEL_2};
                border:1px solid {BORDER};
                border-radius:8px;
            }}
        """)
        layout = QHBoxLayout(frame)
        label = QLabel(name)
        value = SmallStatus("SAFE")
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(value)
        return {"frame": frame, "value": value}

    def relay_badge(self, name):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color:{PANEL_2};
                border:1px solid {BORDER};
                border-radius:8px;
            }}
        """)
        layout = QHBoxLayout(frame)
        label = QLabel(name)
        value = SmallStatus("off")
        value.set_state("off", MUTED)
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(value)
        return {"frame": frame, "value": value}

    def manual_button(self, text):
        btn = QPushButton(text + "     OFF")
        btn.setCheckable(True)
        btn.setStyleSheet(self.button_style(False))
        btn.clicked.connect(lambda checked, b=btn, t=text: self.update_manual_button(b, t, checked))
        return btn

    def update_manual_button(self, btn, text, checked, write=True):
        btn.setText(f"{text}     {'ON' if checked else 'OFF'}")
        btn.setStyleSheet(self.button_style(checked))

        if write:
            self.write_manual_state()

    def button_style(self, active):
        color = GREEN if active else BORDER
        bg = "rgba(36,242,126,0.14)" if active else PANEL_2
        return f"""
            QPushButton {{
                background-color:{bg};
                color:{TEXT};
                border:1px solid {color};
                border-radius:10px;
                padding:10px;
                text-align:left;
                font-weight:bold;
            }}
        """

    def force_button_style(self):
        return f"""
            QPushButton {{
                background-color:{PANEL_2};
                color:{TEXT};
                border:1px solid #777;
                border-radius:10px;
                padding:10px;
                font-weight:bold;
            }}
            QPushButton:hover {{
                border:1px solid {RED};
                color:{RED};
            }}
        """

    # ================= UPDATE =================

    def update_ui(self):
        self.clock.setText(datetime.now().strftime("%H:%M:%S"))

        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                self.latest_state = data
        except Exception:
            self.mqtt_status.set_state("● no data", ORANGE)
            return

        status = data.get("system_status", "SAFE")
        severity = data.get("severity_level", "LOW")
        score = data.get("severity_score", 0)

        if status == "SAFE":
            color = GREEN
            banner_bg = "rgba(36,242,126,0.08)"
        elif status == "FIRE":
            color = RED
            banner_bg = "rgba(239,35,60,0.14)"
        elif status == "GAS_LEAK":
            color = ORANGE
            banner_bg = "rgba(255,159,28,0.13)"
        else:
            color = "#ffd166"
            banner_bg = "rgba(255,209,102,0.12)"

        self.banner.setStyleSheet(f"""
            QFrame#Banner {{
                background-color:{banner_bg};
                border:1px solid {color};
                border-radius:14px;
            }}
        """)

        self.status_big.setText(status)
        self.status_big.setStyleSheet(f"color:{color};")
        self.reason.setText(data.get("final_reason", "---"))
        self.action_badge.set_state(data.get("severity_level", "monitor").lower(), color)
        
        temp_status = data.get("temp_status", "safe")
        temp_trend = data.get("temp_trend", "stable")
        heat_rise = data.get("heat_rise", "normal")

        if temp_status == "danger" or heat_rise == "high_risk":
            temp_color = RED
        elif temp_status == "warning" or heat_rise == "caution" or temp_trend == "rising":
            temp_color = ORANGE
        else:
            temp_color = BLUE

        self.temp_card.set_data(
            f"{data.get('temp_c', 0):.2f} °C",
            f"{temp_status.upper()} · {temp_trend.upper()} · {heat_rise.upper()}",
            temp_color
        )
        
        self.mq2_card.set_data(f"{data.get('mq2_hi', 0):.3f}", "HI ratio")
        self.mq135_card.set_data(f"{data.get('mq135_hi', 0):.3f}", "HI ratio")
        self.voc_card.set_data(f"{data.get('voc_ppm', 0)} ppm", "VOC level", GREEN)

        self.sev_value.setText(severity)
        self.sev_value.setStyleSheet(f"color:{color};")
        self.sev_score.setText(f"{score} / 100")
        self.sev_score.setStyleSheet(f"color:{color}; font-weight:bold;")
        self.sev_action.setText(data.get("action_level", "MONITOR"))
        self.sev_action.setStyleSheet(f"color:{color};")
        self.sev_reason.setText(data.get("severity_reason", data.get("final_reason", "---")))

        self.ml_row["value"].set_state(data.get("ml_hazard", "---"), color if data.get("ml_hazard") != "SAFE" else GREEN)
        self.fusion_row["value"].set_state(data.get("fusion_hazard", "---"), color if data.get("fusion_hazard") != "SAFE" else GREEN)
        self.yolo_row["value"].set_state(data.get("yolo_status", "---"), RED if data.get("yolo_status") == "FIRE" else GREEN)

        self.ai_reason.setText(
            f"Fusion reason: {data.get('fusion_reason', '---')}\n"
            f"Source: {data.get('fusion_source', '---')} | Urgency: {data.get('fusion_urgency', '---')}"
        )

        self.temporal_status.setText(status)
        self.temporal_status.setStyleSheet(f"color:{color};")
        streak = data.get("streak", 0)
        required = data.get("required_count", 0)

        self.streak_label.setText(f"{streak} / {required} samples")
        self.temporal_reason.setText(
            data.get("confirmed_reason",
            data.get("final_reason", "---"))
        )

        self.set_relay(self.buzzer, data.get("buzzer"))
        self.set_relay(self.fan, data.get("fan"))
        self.set_relay(self.mist, data.get("mist"))
        self.set_relay(self.emergency, data.get("emergency"))

        if not self.history_mode:

            self.temp_hist.append(float(data.get("temp_c", 0)))
            self.mq2_hist.append(float(data.get("mq2_hi", 0)))
            self.mq135_hist.append(float(data.get("mq135_hi", 0)))
            self.voc_hist.append(float(data.get("voc_ppm", 0)) / 10.0)

            self.temp_curve.setData(list(self.temp_hist))
            self.mq2_curve.setData(list(self.mq2_hist))
            self.mq135_curve.setData(list(self.mq135_hist))
            self.voc_curve.setData(list(self.voc_hist))

        payload_preview = json.dumps({
            "system_status": status,
            "temp_c": data.get("temp_c"),
            "severity_score": score,
            "relay_active": any([
                data.get("buzzer"), data.get("fan"),
                data.get("mist"), data.get("emergency")
            ])
        }, ensure_ascii=False)

        self.payload.setText(payload_preview)

        self.mqtt_status.set_state("● data online", BLUE)
        self.pi_status.set_state("● pi01 online", GREEN)
        current_event = data.get("system_status", "SAFE")
        reason_event = data.get("final_reason", "---")
        time_event = datetime.now().strftime("%H:%M:%S")

        if current_event != self.last_event_status:
            self.last_event_status = current_event

            self.event_items.insert(
                0,
                f"{time_event}   {current_event}   {reason_event}"
            )

            self.event_items = self.event_items[:5]

        self.event_log.setText("◷  EVENT LOG\n\n" + "\n\n".join(self.event_items))

    def set_relay(self, relay, state):
        if state:
            relay["value"].set_state("on", GREEN)
        else:
            relay["value"].set_state("off", MUTED)

    def export_trend_chart(self):       # EXPORT TREND CHART
        try:
            # ================= FILE NAME =================
            filename = (
                "/home/pi/Desktop/Smart_HMI/"
                f"trend_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )

            # ================= EXPORT GRAPH =================
            exporter = pg.exporters.ImageExporter(
                self.graph.plotItem
            )

            exporter.parameters()["width"] = 1600

            exporter.export(filename)

            # ================= EVENT LOG =================
            self.event_items.insert(
                0,
                datetime.now().strftime("%H:%M:%S")
                + f"   EXPORT SUCCESS → {filename}"
            )

            self.event_items = self.event_items[:5]

            self.event_log.setText(
                "◷  EVENT LOG\n\n"
                + "\n\n".join(self.event_items)
            )

            print(f"✅ Chart exported: {filename}")

        except Exception as e:
            print("EXPORT ERROR:", e)

    def load_history_chart(self):       # LOAD HISTORY CHART
        try:
                temp_data = []
                mq2_data = []
                mq135_data = []
                voc_data = []

                with open(HISTORY_CSV, "r") as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                # bỏ header nếu có
                if rows and rows[0][0] == "date":
                    rows = rows[1:]

                rows = rows[-300:]

                for row in rows:
                    try:
                        temp_data.append(float(row[2]))
                        mq2_data.append(float(row[6]))
                        mq135_data.append(float(row[7]))
                        voc_data.append(float(row[8]) / 10.0)
                    except:
                        continue

                if len(temp_data) == 0:
                    print("⚠️ No valid history data loaded")
                    return

                self.history_mode = True

                self.temp_curve.setData(temp_data)
                self.mq2_curve.setData(mq2_data)
                self.mq135_curve.setData(mq135_data)
                self.voc_curve.setData(voc_data)

                self.event_items.insert(
                    0,
                    datetime.now().strftime("%H:%M:%S")
                    + f"   HISTORY   Loaded {len(temp_data)} historical samples"
                )

                self.event_items = self.event_items[:5]
                self.event_log.setText("◷  EVENT LOG\n\n" + "\n\n".join(self.event_items))

                print(f"✅ Historical chart loaded: {len(temp_data)} samples")

        except Exception as e:
            print("LOAD HISTORY ERROR:", e)


    def back_to_realtime(self):     # BACK TO REALTIME CHART

        self.history_mode = False
        self.event_items.insert(
            0,
            datetime.now().strftime("%H:%M:%S")
            + "   REALTIME   Returned to live mode"
        )

        self.event_items = self.event_items[:5]
        self.event_log.setText(
            "◷  EVENT LOG\n\n"
            + "\n\n".join(self.event_items)
        )

        print("↻ Back to realtime")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SmartFireHMI()
    window.show()
    sys.exit(app.exec())
