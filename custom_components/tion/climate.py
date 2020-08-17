"""Adds support for generic thermostat units."""
import asyncio
import logging
import time
from bluepy import btle
from typing import Tuple, Callable
from tion import s3 as tion

import voluptuous as vol

from homeassistant.components.climate import ClimateEntity
from homeassistant.core import callback
from homeassistant.helpers import condition
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from .const import *

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_MAC): cv.string,
        vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
        vol.Optional(CONF_KEEP_ALIVE, default=30): vol.All(cv.time_period, cv.positive_timedelta),
        vol.Optional(CONF_INITIAL_HVAC_MODE): vol.In(
            [HVAC_MODE_FAN_ONLY, HVAC_MODE_HEAT, HVAC_MODE_OFF]
        ),
        vol.Optional(CONF_AWAY_TEMP): vol.Coerce(float),
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the generic thermostat platform."""
    async_add_entities(
        [
            Tion(
                config.get(CONF_NAME),
                config.get(CONF_MAC),
                config.get(CONF_TARGET_TEMP),
                config.get(CONF_KEEP_ALIVE),
                config.get(CONF_INITIAL_HVAC_MODE),
                config.get(CONF_AWAY_TEMP),
                hass.config.units.temperature_unit,
            )
        ]
    )

class Tion(ClimateEntity, RestoreEntity):
    """Representation of a Tion device."""

    def __init__(
            self,
            name,
            mac,
            target_temp,
            keep_alive,
            initial_hvac_mode,
            away_temp,
            unit,
    ):
        """Initialize the thermostat."""
        #General part
        self._name = name

        self._keep_alive = keep_alive
        self._hvac_mode = initial_hvac_mode
        self._last_mode = self._hvac_mode
        self._saved_target_temp = target_temp or away_temp
        self._is_on = False
        self._heater = False
        self._cur_temp = None
        self._temp_lock = asyncio.Lock()
        self._target_temp = target_temp
        self._unit = unit
        self._support_flags = SUPPORT_FLAGS
        self._preset = PRESET_NONE
        if away_temp:
            self._support_flags = SUPPORT_FLAGS | SUPPORT_PRESET_MODE
        self._away_temp = away_temp
        self._is_away = False
        self._is_boost: bool = False
        self._saved_fan_mode = 0

        self._hvac_list = [ HVAC_MODE_HEAT, HVAC_MODE_FAN_ONLY, HVAC_MODE_OFF ]
        self._fan_speed = 1
        self._is_heating: bool = False
        #tion part
        self._tion = tion(mac)
        self._delay = 600  #if we could not connect wait a little
        self._next_update = 0


    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        if self._keep_alive:
            async_track_time_interval(
                self.hass, self._async_update_state, self._keep_alive
            )
        await self._async_update_state(force=True)



        @callback
        def _async_startup(event):
            """Init on startup."""

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)

        # Check If we have an old state
        old_state = await self.async_get_last_state()
        if old_state is not None:
            # If we have no initial temperature, restore
            if self._target_temp is None:
                # If we have a previously saved temperature
                if old_state.attributes.get(ATTR_TEMPERATURE) is None:
                    self._target_temp = self.target_temp
                    _LOGGER.warning(
                        "Undefined target temperature, falling back to %s",
                        self._target_temp,
                    )
                else:
                    self._target_temp = float(old_state.attributes[ATTR_TEMPERATURE])
            if old_state.attributes.get(ATTR_PRESET_MODE):
                self._preset = old_state.attributes.get(ATTR_PRESET_MODE)
            if self.preset_mode == PRESET_AWAY:
                self._is_away = True
            if not self._hvac_mode and old_state.state:
                self._hvac_mode = old_state.state

        else:
            # No previous state, try and restore defaults
            if self._target_temp is None:
                self._target_temp = self.target_temp

            _LOGGER.warning(
                "No previously saved temperature, setting to %s", self._target_temp
            )

        # Set default state to off
        if not self._hvac_mode:
            self._hvac_mode = HVAC_MODE_OFF



    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def current_temperature(self):
        """Return the sensor temperature."""
        return self._cur_temp

    @property
    def hvac_mode(self):
        """Return current operation."""
        if self._is_on:
            if self._heater:
                return HVAC_MODE_HEAT
            else:
                return HVAC_MODE_FAN_ONLY
        else:
            return HVAC_MODE_OFF

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._hvac_list

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported.
        Need to be one of CURRENT_HVAC_*.
        """

        if self._is_on:
            if self._is_heating:
                current_hvac_operation = CURRENT_HVAC_HEAT
            else:
                current_hvac_operation = CURRENT_HVAC_FAN
        else:
            current_hvac_operation = CURRENT_HVAC_OFF
        return current_hvac_operation

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temp



    @property
    def preset_mode(self):
        """Return the current preset mode, e.g., home, away, temp."""
        return self._preset

    @property
    def preset_modes(self):
        """Return a list of available preset modes or PRESET_NONE if _away_temp is undefined."""
        modes = [PRESET_NONE, PRESET_BOOST]
        if self._away_temp:
            modes.append(PRESET_AWAY)
        return modes

    async def async_set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        _LOGGER.warning("Need to set mode to " + hvac_mode)
        if hvac_mode == self._hvac_mode:
            if hvac_mode == HVAC_MODE_HEAT:
                hvac_mode = HVAC_MODE_FAN_ONLY
            elif hvac_mode == HVAC_MODE_OFF:
                try:
                    hvac_mode = self._last_mode
                except AttributeError:
                    hvac_mode = HVAC_MODE_FAN_ONLY

        if hvac_mode == HVAC_MODE_HEAT:
            await self._async_set_state(heater=True, is_on=True)
        elif hvac_mode == HVAC_MODE_FAN_ONLY:
            await self._async_set_state(heater=False, is_on=True)
        elif hvac_mode == HVAC_MODE_OFF:
            self._last_mode = self._hvac_mode
            await self._async_set_state(is_on=False)
        else:
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return
        self._hvac_mode = hvac_mode
        # Ensure we update the current operation after changing the mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._target_temp = temperature
        await self._async_set_state(heater_temp=temperature)
        self.async_write_ha_state()

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags

    async def async_set_preset_mode(self, preset_mode: str):
        """Set new preset mode."""
        if preset_mode == PRESET_AWAY and not self._is_away:
            self._is_away = True
            self._saved_target_temp = self._target_temp
            self._target_temp = self._away_temp
            await self._async_set_state(heater_temp=self._target_temp)

        if preset_mode == PRESET_BOOST and not self._is_boost:
            self._is_boost = True
            self._saved_fan_mode = int(self.fan_mode)
            await self.async_set_fan_mode(self.boost_fan_mode)
        elif preset_mode != PRESET_BOOST and self.preset_mode == PRESET_BOOST:
            # returning from boost mode
            _LOGGER.debug("Returning from boost mode. Going to set fan speed %d" % self._saved_fan_mode)
            self._is_boost = False
            await self.async_set_fan_mode(self._saved_fan_mode)

        self._preset = preset_mode
        self.async_write_ha_state()
    @property
    def fan_mode(self):
        return self._fan_speed

    @property
    def boost_fan_mode(self) -> int:
        """Fan speed for boost mode

        :return: maximum of supported fan_modes
        """
        return max(self.fan_modes)

    @property
    def fan_modes(self):
        return [1, 2, 3, 4, 5, 6]

    @property
    def precision(self):
        """Return the precision of the system."""
        return PRECISION_WHOLE

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    async def async_set_fan_mode(self, fan_mode):
        if (self.preset_mode == PRESET_BOOST and self._is_boost) and fan_mode != self.boost_fan_mode:
            _LOGGER.debug("I'm in boost mode. Will ignore requested fan speed %s" % fan_mode)
            fan_mode = self.boost_fan_mode
        if fan_mode != self.fan_mode or not self._is_on:
            self._fan_speed = fan_mode
            await self._async_set_state(fan_speed=fan_mode, is_on=True)
            self.async_write_ha_state()

    async def _async_update_state(self, time = None, force: bool = False, keep_connection: bool = False) -> dict:
        def decode_state(state:str) -> bool:
            return True if state == "on" else False

        _LOGGER.debug("Update fired force = " + str(force) + ". Keep connection is " + str(keep_connection))
        if time:
            _LOGGER.debug("Now is %s", time)
            now = int(time.timestamp())
        else:
            now = 0

        if self._next_update < now or force:
            try:
                response = self._tion.get(keep_connection)

                self._cur_temp = response["out_temp"]
                self._target_temp = response["heater_temp"]
                self._is_on = decode_state(response["status"])
                self._heater = decode_state(response["heater"])
                self._fan_speed = response["fan_speed"]
                self._is_heating = decode_state(response["is_heating"])
                self._hvac_mode = self.hvac_mode
                self.async_write_ha_state()
                self._next_update = 0
                if self.fan_mode != self.boost_fan_mode and (self._is_boost or self.preset_mode == PRESET_BOOST):
                    _LOGGER.warning("I'm in boost mode, but current speed %d is not equal boost speed %d. Dropping boost mode" % (
                        self.fan_mode,
                        self.boost_fan_mode
                    ))
                    self._is_boost = False
                    self._preset = PRESET_NONE
            except Exception as e:
                _LOGGER.critical("Got exception %s", str(e))
                _LOGGER.critical("Will delay next check")
                self._next_update = now + self._delay
                response = {}
        else:
            response = {}

        return response

    async def _async_set_state(self, **kwargs):
        if "is_on" in kwargs:
            kwargs["status"] = "on" if kwargs["is_on"] else "off"
            del kwargs["is_on"]
        if "heater" in kwargs:
            kwargs["heater"] = "on" if kwargs["heater"] else "off"
        if "fan_speed" in kwargs:
            kwargs["fan_speed"] = int(kwargs["fan_speed"])

        args = ', '.join('%s=%r' % x for x in kwargs.items())
        _LOGGER.info("Need to set: " + args)
        self._tion.set(kwargs)
        await self._async_update_state(force=True, keep_connection=False)
