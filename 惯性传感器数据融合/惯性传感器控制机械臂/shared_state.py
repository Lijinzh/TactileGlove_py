# shared_state.py
# Description:
# Defines a simple, shared state object to facilitate communication
# between the GUI frontend and the robot control backend.

import numpy as np
from threading import Lock

class SharedState:
    """A thread-safe class to hold data shared between processes."""
    def __init__(self):
        self.lock = Lock()

        # --- States controlled by the GUI ---
        self.control_active = False
        self.reset_zero_pose_requested = True
        self.is_running = True # Set to False by either process to signal a shutdown

        # --- States updated by the Controller, read by the GUI ---
        self.robot_connected = False
        self.latest_imu_euler = np.zeros(3)
        self.latest_velocity_command = np.zeros(6)
        self.controller_status = "PENDING"

# Create a single, global instance of the state.
# Both frontend and backend will import this exact instance.
shared_state = SharedState()