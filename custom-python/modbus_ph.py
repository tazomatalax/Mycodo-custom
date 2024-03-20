import minimalmodbus
import serial
import struct

# Create an instrument object
instrument = minimalmodbus.Instrument('/dev/ttyUSB0', slaveaddress=1, debug=False)
instrument.serial.baudrate = 19200
instrument.serial.bytesize = 8
instrument.serial.parity = serial.PARITY_NONE
instrument.serial.stopbits = 2
instrument.serial.timeout = 1
instrument.mode = minimalmodbus.MODE_RTU
instrument.clear_buffers_before_each_transaction = True

# Read 10 registers starting from 2090
ph_values = instrument.read_registers(2089, 10, functioncode=3)

# Read 10 registers starting from 2410
temp_values = instrument.read_registers(2409, 10, functioncode=3)

# Combine the register values to form 32-bit integers
ph_int = (ph_values[3] << 16) | ph_values[2]
temp_int = (temp_values[3] << 16) | temp_values[2]

# Convert the 32-bit integers to bytes
ph_bytes = ph_int.to_bytes(4, 'little')
temp_bytes = temp_int.to_bytes(4, 'little')

# Interpret the bytes as 32-bit floats
pH = struct.unpack('f', ph_bytes)[0]
temperature = struct.unpack('f', temp_bytes)[0]


# # Store measurements
# self.store_measurement(channel=0, measurement=pH)
# self.store_measurement(channel=1, measurement=temperature)

# Print the measurements
print(f"pH: {pH:.2f}")
print(f"Temperature: {temperature:.2f}")

