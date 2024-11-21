import struct
from typing import NamedTuple
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
import asyncio
import multiprocessing as mp
import math
from time import sleep, time

import numpy as np


class StylusReading(NamedTuple):
    accel: np.ndarray
    gyro: np.ndarray
    t: int
    pressure: float

    def format_aligned(self):
        return f"p={self.pressure:<8.5f}: |a|={np.linalg.norm(self.accel):<7.3f} a={self.accel}, g={self.gyro}"
    
    def to_json(self):
        return {
            "accel": self.accel.tolist(),
            "gyro": self.gyro.tolist(),
            "t": self.t,
            "pressure": self.pressure
        }
    
    def from_json(dict):
        return StylusReading(
            np.array(dict["accel"]),
            np.array(dict["gyro"]),
            dict["t"],
            dict["pressure"]
        )


class StopCommand(NamedTuple):
    pass


def calc_accel(a):
    """Remap raw accelerometer measurements to Gs."""
    accel_range = 4  # Should match settings.accelRange in microcontroller code
    return a * 0.061 * (accel_range / 2) / 1000


def calc_gyro(g):
    """Remap raw gyro measurements to degrees per second."""
    gyro_range = 500  # Should match settings.gyroRange in microcontroller code
    return g * 4.375 * (gyro_range / 125) / 1000

def unpack_imu_data_packet(data: bytearray):
    """Unpacks an IMUDataPacket struct from the given data buffer."""
    #-ay, ax, -az, gy, -gx, gz, pressure = struct.unpack("<3h3hH", data)
    ay, ax, az, gy, gx, gz, pressure = struct.unpack("<3h3hH", data)
    ay = -ay
    az = -az
    gx = -gx
    accel = calc_accel(np.array([ax, ay, az], dtype=np.float64) * 9.8)
    gyro = calc_gyro(np.array([gx, gy, gz], dtype=np.float64) * np.pi / 180.0)

    # pitch = -math.atan(ay / math.sqrt(ax**2 + az**2)) #why is pitch and roll negative?
    # roll = -math.atan(-ax / math.sqrt(ay**2 + az**2))
    # TODO:
    # 1 manually figure out the pitch so that it covers 360 degrees, currently -90 to +90
    # 2 add yaw
    # 3 low pass filter - place this as unpacking data

    # print("pitch: " + str(pitch) + "  roll: " + str(roll))

    return StylusReading(accel, gyro, 0, pressure / 2**16)


characteristic = "19B10013-E8F2-537E-4F6C-D104768A1214"

sleep_time = 0.01

# Initialise matrices and variables
C = np.array([[1, 0, 0, 0], [0, 0, 1, 0]])
P = np.eye(4)
Q = np.eye(4)
R = np.eye(2)

state_estimate = np.array([[0], [0], [0], [0]])

phi_hat = 0.0
theta_hat = 0.0

# Calculate accelerometer offsets
N = 100
phi_offset = 0.0
theta_offset = 0.0

for i in range(N):
    [phi_acc, theta_acc] = [0,0] 
    phi_offset += phi_acc
    theta_offset += theta_acc
    sleep(sleep_time)

phi_offset = float(phi_offset) / float(N)
theta_offset = float(theta_offset) / float(N)

sleep(2)

# Measured sampling time
dt = 0.0
start_time = time()

async def monitor_ble_async(data_queue: mp.Queue, command_queue: mp.Queue):
    while True:
        device = await BleakScanner.find_device_by_name("DPOINT", timeout=5)
        if device is None:
            print("could not find device with name DPOINT. Retrying in 1 second...")
            await asyncio.sleep(1)
            continue
        
        def queue_notification_handler(_: BleakGATTCharacteristic, data: bytearray):
            reading = unpack_imu_data_packet(data)
            #print("reading.accel: " + str(reading.accel))
            #print("reading.gyro: " + str(reading.gyro))
            #print("reading.pressure: " + str(reading.pressure))
            data_queue.put(reading)

            # Sampling time
            global start_time
            global phi_hat
            global theta_hat
            global state_estimate
            global P

            dt = time() - start_time
            start_time = time()

            ax = reading.accel[0]
            ay = reading.accel[1]
            az = reading.accel[2]
            gx = reading.gyro[0]
            gy = reading.gyro[1]
            gz = reading.gyro[2]
            # Get accelerometer measurements and remove offsets
            [phi_acc, theta_acc] = [math.atan2(ay, math.sqrt(ax ** 2.0 + az ** 2.0)), math.atan2(-ax, math.sqrt(ay ** 2.0 + az ** 2.0))] # phi = math.atan2(ay, math.sqrt(ax ** 2.0 + az ** 2.0))  theta = math.atan2(-ax, math.sqrt(ay ** 2.0 + az ** 2.0))
            phi_acc -= phi_offset
            theta_acc -= theta_offset
            
            # Get gyro measurements and calculate Euler angle derivatives gx, gy, gz
            [p, q, r] = [gx, gy, gz]
            phi_dot = p + math.sin(phi_hat) * math.tan(theta_hat) * q + math.cos(phi_hat) * math.tan(theta_hat) * r
            theta_dot = math.cos(phi_hat) * q - math.sin(phi_hat) * r

            # Kalman filter
            A = np.array([[1, -dt, 0, 0], [0, 1, 0, 0], [0, 0, 1, -dt], [0, 0, 0, 1]])
            B = np.array([[dt, 0], [0, 0], [0, dt], [0, 0]])

            gyro_input = np.array([[phi_dot], [theta_dot]])
            state_estimate = A.dot(state_estimate) + B.dot(gyro_input)
            P = A.dot(P.dot(np.transpose(A))) + Q

            measurement = np.array([[phi_acc], [theta_acc]])
            y_tilde = measurement - C.dot(state_estimate)
            S = R + C.dot(P.dot(np.transpose(C)))
            K = P.dot(np.transpose(C).dot(np.linalg.inv(S)))
            state_estimate = state_estimate + K.dot(y_tilde)
            P = (np.eye(4) - K.dot(C)).dot(P)

            phi_hat = state_estimate[0]
            theta_hat = state_estimate[2]

            # Display results
            print("Phi: " + str(np.round(phi_hat * 180.0 / math.pi, 1)) + " Theta: " + str(np.round(theta_hat * 180.0 / math.pi, 1)))

            sleep(sleep_time)

        disconnected_event = asyncio.Event()
        print("Connecting to BLE device...")
        try:
            async with BleakClient(
                device, disconnected_callback=lambda _: disconnected_event.set()
            ) as client:
                print("Connected!")
                await client.start_notify(characteristic, queue_notification_handler)
                command = asyncio.create_task(
                    asyncio.to_thread(lambda: command_queue.get())
                )
                disconnected_task = asyncio.create_task(disconnected_event.wait())
                await asyncio.wait(
                    [disconnected_task, command], return_when=asyncio.FIRST_COMPLETED
                )
                if command.done():
                    print("Quitting BLE process")
                    return
                print("Disconnected from BLE")
        except Exception as e:
            print(f"BLE Exception: {e}")
            print("Retrying in 1 second...")
            await asyncio.sleep(1)


def monitor_ble(data_queue: mp.Queue, command_queue: mp.Queue):
    asyncio.run(monitor_ble_async(data_queue, command_queue))