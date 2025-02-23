from time import sleep
from pywinusb import hid
from dataclasses import dataclass
import utils
import pymem


pid = utils.pid_from_window("MUSECA")
if pid:
    try:
        pm = pymem.Pymem(pid)
    except pymem.exception.CouldNotOpenProcess:
        print(f'Could not open process {pid}. Ensure that you are running the program as admin.')
        exit()
else:
    raise ProcessLookupError('Could not find game window.')


# A hook to expose the CGameSceneComponent class to a static location in memory
entrypoint = 0x1801F291C
hook = bytes.fromhex('EB 5E 90 90 90')
codelocation = 0x1801F297C
mycode = bytes.fromhex('48 89 35 65 97 28 0E EB 9C 90 90 90')
pm.write_bytes(entrypoint, hook, len(hook))
pm.write_bytes(codelocation, mycode, len(mycode))


p_cGSC = 0x18E47C0E8
off_hispeedstruct = 0xA40
off_x = off_hispeedstruct + 0x13C
off_z = off_hispeedstruct + 0x140
off_y = off_hispeedstruct + 0x144
off_rx = off_hispeedstruct + 0x148
off_ry = off_hispeedstruct + 0x14C
off_rz = off_hispeedstruct + 0x150


@dataclass
class SpaceMouse:
    x: int = 0
    y: int = 0
    z: int = 0
    rx: int = 0
    ry: int = 0
    rz: int = 0

    def getstr(self) -> str:
        return f"{self.x=}, {self.y=}, {self.z=}, {self.rx=}, {self.ry=}, {self.rz=}"


class CameraController:
    def __init__(self, translation_speed=5.0, rotation_speed=1.0, deadzone=0.05):
        self.translation_speed = translation_speed  # units per second
        self.rotation_speed = rotation_speed        # degrees per second
        self.deadzone = deadzone

    def apply_deadzone(self, value):
        if value:
            return 0.0 if abs(value) < self.deadzone else value
        else:
            return 0.0

    def normalize(self, value):
        if value:
            return value / 255.0
        else:
            return 0.0

    def update(self, x, y, z, rx, ry, rz, delta_time):
        # Normalize and apply deadzone
        x = self.apply_deadzone(self.normalize(x))
        y = self.apply_deadzone(self.normalize(y))
        z = self.apply_deadzone(self.normalize(z))
        rx = self.apply_deadzone(self.normalize(rx))
        ry = self.apply_deadzone(self.normalize(ry))
        rz = self.apply_deadzone(self.normalize(rz))

        # Apply translation (relative movement)
        dx = x * self.translation_speed * delta_time
        dy = y * self.translation_speed * delta_time
        dz = z * self.translation_speed * delta_time

        # Apply rotation (relative rotation)
        pitch = rx * self.rotation_speed * delta_time
        yaw = rz * self.rotation_speed * delta_time
        roll = ry * self.rotation_speed * delta_time

        try:
            gsc = pm.read_longlong(p_cGSC)
            old_x = pm.read_float(gsc + off_x)
            old_y = pm.read_float(gsc + off_y)
            old_z = pm.read_float(gsc + off_z)
            old_rx = pm.read_float(gsc + off_rx)
            old_ry = pm.read_float(gsc + off_ry)
            old_rz = pm.read_float(gsc + off_rz)

            pm.write_float(gsc + off_x, old_x - dx)
            pm.write_float(gsc + off_y, old_y + dy)
            pm.write_float(gsc + off_z, old_z + dz)
            pm.write_float(gsc + off_rx, old_rx + pitch)
            pm.write_float(gsc + off_ry, old_ry - yaw)
        except pymem.exception.MemoryReadError:
            print('Could not read memory. Try starting a song.')
            print(f'CGameSceneComponent pointer: {hex(gsc)}')
        except pymem.exception.MemoryWriteError:
            print('Could not write memory. Try starting a song.')
            print(f'CGameSceneComponent pointer: {hex(gsc)}')
        # pm.write_float(gsc + off_rz, old_rz - roll) # lock roll cause the red lines on the lane don't seem to track correctly

        # print(f"Move: Δx={dx:.2f}, Δy={dy:.2f}, Δz={dz:.2f} | Rotate: pitch={pitch:.2f}°, yaw={yaw:.2f}°, roll={roll:.2f}°")
    def reset(self):
        try:
            gsc = pm.read_longlong(p_cGSC)
            pm.write_float(gsc + off_x, 0.0)
            pm.write_float(gsc + off_y, 0.0)
            pm.write_float(gsc + off_z, 10.0)
            pm.write_float(gsc + off_rx, 76.0)
            pm.write_float(gsc + off_ry, 0.0)
            pm.write_float(gsc + off_rz, 0.0)
        except pymem.exception.MemoryWriteError:
            print('Could not write memory. Try starting a song.')
            print(f'CGameSceneComponent pointer: {hex(gsc)}')

class Handler(object):
    time = 0
    sm = SpaceMouse()
    camera = CameraController()

    @staticmethod
    def run(data):
        # if time() - Handler.time < 0.0001:  # This was causing packets to be missed
        #     return
        # Handler.time = time()
        cam = Handler.camera
        sm = Handler.sm
        type_ = data[0]
        if type_ == 1:
            sm.x = data[2] - data[1]
            sm.y = data[4] - data[3]
            sm.z = data[6] - data[5]
        if type_ == 2:
            sm.rx = data[2] - data[1]
            sm.ry = data[4] - data[3]
            sm.rz = data[6] - data[5]
        if data[0]:
            cam.update(sm.x, sm.y, sm.z, sm.rx, sm.ry, sm.rz, delta_time=1)
        # print(sm.getstr())
        if type_ == 3:
            cam.reset()


def open_device():
    devices = hid.HidDeviceFilter(vendor_id=0x46d).get_devices()
    for device in devices:
        device: hid.HidDevice = device
        device.open()
        in_reports = device.find_input_reports()
        out_reports = device.find_output_reports()
        if in_reports and out_reports:
            device.set_raw_data_handler(Handler.run)
            print("Device found %s", device)
            return device
        else:
            device.close()
    print('No device found')
    return None


def list_all_devices():
    import pywinusb.hid as hid
    hids = hid.find_all_hid_devices()
    for hid in set(hids):
        print(hid)

if __name__ == '__main__':
    # list_all_devices()
    device = open_device()
    while device:
        sleep(10)
