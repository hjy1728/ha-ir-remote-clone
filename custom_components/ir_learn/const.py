"""Constants for the IR Learn integration."""

from __future__ import annotations

DOMAIN = "ir_learn"

CONF_ESPHOME_NODE = "esphome_node"
CONF_CODE_SENSOR = "code_sensor"
CONF_PROTOCOL = "protocol"

PROTOCOL_RAW = "raw"
PROTOCOL_NEC = "nec"
PROTOCOL_PRONTO = "pronto"
PROTOCOLS = [PROTOCOL_RAW, PROTOCOL_NEC, PROTOCOL_PRONTO]

DEFAULT_ESPHOME_NODE = "ir_controller"
DEFAULT_CODE_SENSOR = "text_sensor.ir_controller_zuijin_hongwai_ma"
DEFAULT_PROTOCOL = PROTOCOL_RAW

SERVICE_SEND_RAW = "send_raw_ir"
SERVICE_SEND_NEC = "send_nec_ir"
SERVICE_SEND_PRONTO = "send_pronto_ir"

SERVICE_ADD_BUTTON = "add_button"
SERVICE_DELETE_BUTTON = "delete_button"
SERVICE_SEND_BUTTON = "send_button"
SERVICE_CLEAR_BUFFER = "clear_buffer"
SERVICE_RECEIVE_CODE = "receive_code"

ATTR_NAME = "name"
ATTR_NAMES = "names"
ATTR_CODE = "code"
ATTR_REPEATS = "repeats"
ATTR_PULSES = "pulses"

STORAGE_VERSION = 1
STORAGE_KEY = "ir_learn"

IGNORED_STATES = {"", "unknown", "unavailable", "none", "waiting"}
MIN_RAW_VALUES = 4

PLATFORMS = ["switch", "button", "select", "sensor"]
