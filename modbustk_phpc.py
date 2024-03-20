import modbus_tk.defines as cst
import modbus_tk.modbus_rtu as modbus_rtu
import serial

# Create a Modbus RTU master
master = modbus_rtu.RtuMaster(
    serial.Serial(port='/dev/ttyUSB1', baudrate=19200, bytesize=8, parity='N', stopbits=2, xonxoff=0)
)
master.set_timeout(1.0)
master.set_verbose(True)

try:
    # Connect to the Modbus RTU master
    master.open()

    # Read 10 registers starting from 2090
    ph_values = master.execute(1, cst.READ_HOLDING_REGISTERS, 2089, 10)

    # Read 10 registers starting from 2410
    temp_values = master.execute(1, cst.READ_HOLDING_REGISTERS, 2409, 10)

    # Interpret the register values as measurements
    pH = ph_values[2]
    temperature = temp_values[2]

    # # Store measurements
    # self.store_measurement(channel=0, measurement=pH)
    # self.store_measurement(channel=1, measurement=temperature)

    # Print the measurements
    print(f"pH: {pH}")
    print(f"Temperature: {temperature}")


finally:
    # Close the connection
    master.close()