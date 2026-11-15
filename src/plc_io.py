"""OpenPLC v3: %MW0 is zero-based Modbus holding address 1024."""
from pymodbus.client import ModbusTcpClient

class PLC:
    def __init__(self, host='127.0.0.1', port=1502):
        self.client = ModbusTcpClient(host, port=port, timeout=1, retries=0)
        if not self.client.connect():
            raise RuntimeError('Cannot connect to OpenPLC. Start Runtime and its Modbus server.')

    def read(self):
        r = self.client.read_holding_registers(1024, count=8, slave=1)
        if r.isError():
            raise RuntimeError(f'Modbus read failed: {r}')
        return r.registers

    def write(self, offset, values):
        r = self.client.write_registers(1024 + offset, values, slave=1)
        if r.isError():
            raise RuntimeError(f'Modbus write failed: {r}')

    def close(self):
        self.client.close()

if __name__ == '__main__':
    p = PLC()
    print(dict(zip(('recipe','sequence','enable','measured','ack','valve','done','fault'), p.read())))
    p.close()
