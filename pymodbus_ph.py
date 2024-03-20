from pymodbus.client.sync import ModbusSerialClient
import struct

# Create a Modbus client object
client = ModbusSerialClient(method='rtu', port='COM7', baudrate=19200, bytesize=8, parity='N', stopbits=2, timeout=1)

# Connect to the Modbus device
client.connect()

# Read 10 registers starting from address 2090
ph_values = client.read_holding_registers(address=2090, count=10, unit=1)

# Read 10 registers starting from address 2410
temp_values = client.read_holding_registers(address=2410, count=10, unit=1)

# Close the Modbus connection
client.close()

# Convert the register values to bytestrings
ph_bytes = bytearray(ph_values.registers[2:4])
temp_bytes = bytearray(temp_values.registers[2:4])

# Interpret the bytestrings as measurements
pH = struct.unpack('f', ph_bytes)[0]
temperature = struct.unpack('f', temp_bytes)[0]

# self.store_measurement(channel=0, measurement=pH)
# self.store_measurement(channel=1, measurement=temperature)

# Print the measurements
print(f"pH: {pH}")
print(f"Temperature: {temperature}")
