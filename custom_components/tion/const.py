"""Consts for Tion component"""
from homeassistant.components.climate import PLATFORM_SCHEMA
from homeassistant.components.climate.const import (
    ATTR_PRESET_MODE,
    CURRENT_HVAC_FAN,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_OFF,
    HVAC_MODE_HEAT,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_OFF,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_NONE,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_FAN_MODE,
 )
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_NAME,
    EVENT_HOMEASSISTANT_START,
    PRECISION_WHOLE,
)
DOMAIN = 'tion'
DEFAULT_NAME = "Tion Breezer"

CONF_TARGET_TEMP = "target_temp"
CONF_KEEP_ALIVE = "keep_alive"
CONF_INITIAL_HVAC_MODE = "initial_hvac_mode"
CONF_AWAY_TEMP = "away_temp"
CONF_MAC = "mac"
SUPPORTED_DEVICES = ['S3']
SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE | SUPPORT_FAN_MODE

TION_SCHEMA = {
    'name': {'type': str, 'default': DEFAULT_NAME, 'required': True},
    CONF_MAC: {'type': str, 'required': True},
    CONF_KEEP_ALIVE: {'type': int, 'default': 60, 'required': False},
    CONF_AWAY_TEMP: {'type': int, 'default': 15, 'required': False},
    'pair': {'type': bool, 'default': True, 'required': False},
}
