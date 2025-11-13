----------------------------------------------
Mycodo Custom Inputs, Outputs, and Controllers
----------------------------------------------

.. contents::
    :depth: 3

About
=====

These are custom Inputs, Outputs, and Controllers created for `Mycodo <https://github.com/kizniche/Mycodo>`__ that don't quite fit with the built-in set. This could be for a number of reasons: they're experimental/unreliable/untested, they will be rarely used, they're too complex for the average user, etc. If any of these custom modules become included in Mycodo's built-in set, they will be removed from this repository.

These modules can be imported from the Configuration submenus titled Inputs, Outputs, and Controllers.

--------------

Custom Inputs
=============

Alicat Mass Flow Controller (Modbus RTU)
----------------------------------------

Details and code: `Mycodo-custom/custom_inputs/alicat mfc/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_inputs/alicat%20mfc>`__

This Input module reads telemetry data from Alicat Mass Flow Controllers via Modbus RTU serial communication. Provides real-time monitoring of volumetric flow, mass flow, pressure, temperature, and current setpoint values. Uses RS-485 serial connection over USB adapter.

--------------

Hamilton pH Probe (Modbus RTU)
------------------------------

Details and code: `Mycodo-custom/custom_inputs/hamilton arc ph probe/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_inputs/hamilton%20arc%20ph%20probe>`__

This Input module reads pH and temperature measurements from Hamilton ARC pH probes via Modbus RTU serial communication. Provides high-accuracy pH monitoring for industrial and laboratory applications including bioreactors, fermenters, and aquaculture systems.

--------------

Hamilton DO Probe (Modbus RTU)
------------------------------

Details and code: `Mycodo-custom/custom_inputs/hamilton arc do probe/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_inputs/hamilton%20arc%20do%20probe>`__

This Input module reads dissolved oxygen (DO) and temperature measurements from Hamilton ARC DO probes via Modbus RTU serial communication. Provides high-accuracy DO monitoring for bioreactors, fermenters, and aquaculture systems with digital Modbus communication.

--------------

LoRaWAN-enabled Geiger Counter
------------------------------

By `Kyle Gabriel <https://kylegabriel.com/>`__

Blog Post: `Remote Radiation Monitoring <https://kylegabriel.com/projects/2019/08/remote-radiation-monitoring.html>`__

Details and code: `Mycodo-custom/custom_inputs/geiger counter/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_inputs/geiger%20counter>`__

This Input was designed for use with the Moteino Mega with a LoRaWAN transceiver, connected to a MightyOhm Geiger Counter (v1.0), powered by three AA batteries, for long-term remote radiation monitoring.

--------------

BME680 (Temperature Error Fix)
------------------------------

By `Kyle Gabriel <https://kylegabriel.com/>`__

Forum Post: `BME680 shows wrong temperature <https://kylegabriel.com/forum/general-discussion/sensor-bme680-occasionally-locks-up-and-shows-wrong-temperature-but-correct-humidity-until-deactivated-and-reactivated/>`__

Details and code: `Mycodo-custom/custom_inputs/bme680 temperature error fix/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_inputs/bme680%20temperature%20error%20fix>`__

A user with the BME680 sensor experienced an issue where the temperature would erroneously and continuously measure 34.54 C until the Input was deactivated and activated again. Since We don't know if this is an isolated incident because we only have one sensor to test, this module was created to fix the issue. If there are more reports of this occurring with other BME680 sensors, this module may move into the built-in set for Mycodo.

--------------

BME280 Serial to TTN
--------------------

By `Kyle Gabriel <https://kylegabriel.com/>`__

Details and code: `Mycodo-custom/custom_inputs/bme280 serial to ttn/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_inputs/bme280%20serial%20to%20ttn>`__

This Input will write the measured values from the BME280 sensor to a serial device. For my application, I have a MCU with a
LoRaWAN transceiver that then receives those measurements and transmits them to The Things Network.

--------------

K30 Serial to TTN
-----------------

By `Kyle Gabriel <https://kylegabriel.com/>`__

Details and code: `Mycodo-custom/custom_inputs/k30 serial to ttn/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_inputs/k30%20serial%20to%20ttn>`__

This Input will write the measured values from the K30 sensor to a serial device. For my application, I have a MCU with a
LoRaWAN transceiver that then receives those measurements and transmits them to The Things Network.

--------------


Custom Outputs
==============

Alicat Mass Flow Controller Setpoint (Modbus RTU)
-------------------------------------------------

Details and code: `Mycodo-custom/custom_outputs/alicat massflow setpoint/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_outputs/alicat%20massflow%20setpoint>`__

This Output module controls the setpoint of Alicat Mass Flow Controllers via Modbus RTU serial communication. Provides a value-type output that allows Mycodo automations, PID controllers, or manual commands to dynamically adjust flow rate. Includes verification by reading back the actual setpoint.

--------------

On/Off Remote GPIO (gpiozero)
-----------------------------

By `Kyle Gabriel <https://kylegabriel.com/>`__

Details and code: `Mycodo-custom/custom_outputs/remote GPIO on-off/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_outputs/remote%20GPIO%20on-off>`__

Remotely control GPIO pin states over a network with the use of [gpiozero](https://github.com/gpiozero/gpiozero).

--------------

PWM Remote GPIO (gpiozero)
--------------------------

By `Kyle Gabriel <https://kylegabriel.com/>`__

Details and code: `Mycodo-custom/custom_outputs/remote GPIO PWM/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_outputs/remote%20GPIO%20PWM>`__

Remotely control GPIO pin duty cycles over a network with the use of [gpiozero](https://github.com/gpiozero/gpiozero).

--------------

Custom Functions
================

pH Control (CO2 Mass Flow Controller)
-------------------------------------

Details and code: `Mycodo-custom/custom_functions/ph controller/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_functions/ph%20controller>`__

This Function implements PID-based control for maintaining a pH setpoint by regulating CO2 flow through an Alicat Mass Flow Controller. Automatically adjusts CO2 dosing to keep pH stable in bioreactors, fermenters, or aquaculture systems. Includes configurable PID gains, safety flow limits, and measurement timeout protection.

--------------

DO Control (Air Mass Flow Controller)
-------------------------------------

Details and code: `Mycodo-custom/custom_functions/dissolved oxygen controller/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_functions/dissolved%20oxygen%20controller>`__

This Function implements PID-based control for maintaining a dissolved oxygen (DO) setpoint by regulating air flow through an Alicat Mass Flow Controller. Automatically adjusts air/O2 dosing to keep DO stable in bioreactors, fermenters, or aquaculture systems. Includes configurable PID gains, safety flow limits, and measurement timeout protection.

--------------

CoolBot Clone
-------------

By `Kyle Gabriel <https://kylegabriel.com/>`__

Details and code: `Mycodo-custom/custom_functions/coolbot clone/ <https://github.com/kizniche/Mycodo-custom/blob/master/custom_functions/coolbot%20clone>`__

This Controller mimics the functionality of a `CoolBot <https://storeitcold.com>`__, allowing a walking cool room or freezer to be created using an inexpensive air conditioner unit.
