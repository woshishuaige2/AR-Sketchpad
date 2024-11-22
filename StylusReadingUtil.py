from monitor_ble import monitor_ble
import multiprocessing as mp
from pynput import keyboard
import matplotlib.pyplot as plt
from time import sleep, time

# Global variables
ble_process = None
ble_queue = mp.Queue()
ble_command_queue = mp.Queue()

plot_process = None
    
def start_ble_process():
    global ble_process
    global plot_process
    
    ble_process = mp.Process(
        target=monitor_ble, args=(ble_queue, ble_command_queue), daemon=False
    )
    ble_process.start()
    print("BLE process started.")
    
    plot_process = mp.Process(target=live_plot, args=(phi_queue, theta_queue))
    plot_process.start()
    print("Plot process started.")

def stop_processes():
    """Terminate both processes and wait for them to finish."""
    global ble_process
    global plot_process

    if plot_process:
        print("Terminating plot process...")
        plot_process.terminate()
        plot_process.join()
        print("Plot process terminated.")

    if ble_process:
        print("Terminating BLE process...")
        ble_process.terminate()
        ble_process.join()
        print("BLE process terminated.")
        
def on_press(key):
    try:
        if key.char == 'q':
            print("'q' key pressed. Terminating BLE process...")
            stop_processes()
            
            return False  # Stop the listener
    except AttributeError:
        pass  # Ignore special keys


# Initialize data queues
phi_queue = mp.Queue()
theta_queue = mp.Queue()

# Function to update the plot
def live_plot(phi_queue, theta_queue):
    plt.ion()  # Turn on interactive mode
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    x_data, phi_data, theta_data = [], [], []
    line1, = ax1.plot(x_data, phi_data, label="Roll (Phi)", color="blue")
    line2, = ax2.plot(x_data, theta_data, label="Pitch (Theta)", color="red")
    
    ax1.set_title("Phi (Roll Angle) vs Time")
    ax1.set_ylabel("Phi (degrees)")
    ax1.legend()
    ax1.grid(True)
    
    ax2.set_title("Theta (Pitch Angle) vs Time")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Theta (degrees)")
    ax2.legend()
    ax2.grid(True)
    
    start_time = time()
    
    while True:
        try:
            current_time = time() - start_time
            if not phi_queue.empty() and not theta_queue.empty():
                phi = phi_queue.get()
                theta = theta_queue.get()
                
                x_data.append(current_time)
                phi_data.append(phi)
                theta_data.append(theta)
                
                line1.set_xdata(x_data)
                line1.set_ydata(phi_data)
                line2.set_xdata(x_data)
                line2.set_ydata(theta_data)
                
                ax1.set_xlim(0, max(current_time, 10))
                ax2.set_xlim(0, max(current_time, 10))
                
                ax1.set_ylim(min(phi_data)-5, max(phi_data)+5)
                ax2.set_ylim(min(theta_data)-5, max(theta_data)+5)
                
                plt.pause(0.00)
        except KeyboardInterrupt:
            print("Stopping live plot...")
            plt.close(fig)
            break

def main():
    start_ble_process()  # Start BLE process at program launch
    
    # Start keyboard listener in a separate thread
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    print("Program running. Press 'q' to terminate BLE process.")
    listener.join()  # Wait for the listener to complete
    
    stop_processes()

if __name__ == '__main__':
    main()
