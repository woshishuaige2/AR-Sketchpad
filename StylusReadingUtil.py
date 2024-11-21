from monitor_ble import monitor_ble
import multiprocessing as mp
from pynput import keyboard
import threading

# Global variables
ble_process = None
ble_queue = mp.Queue()
ble_command_queue = mp.Queue()

def start_ble_process():
    global ble_process
    ble_process = mp.Process(
        target=monitor_ble, args=(ble_queue, ble_command_queue), daemon=False
    )
    ble_process.start()
    print("BLE process started.")

def on_press(key):
    try:
        if key.char == 'q':
            print("'q' key pressed. Terminating BLE process...")
            if ble_process:
                ble_process.terminate()
            return False  # Stop the listener
    except AttributeError:
        pass  # Ignore special keys

def main():
    start_ble_process()  # Start BLE process at program launch
    
    # Start keyboard listener in a separate thread
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    print("Program running. Press 'q' to terminate BLE process.")
    listener.join()  # Wait for the listener to complete

if __name__ == '__main__':
    main()
