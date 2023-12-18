# SPDX-FileCopyrightText: Copyright (c) 2022 Guillaume Bellegarda. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Copyright (c) 2022 EPFL, Guillaume Bellegarda

""" Run CPG """
import time
import numpy as np
import matplotlib

# adapt as needed for your system
# from sys import platform
# if platform =="darwin":
#   matplotlib.use("Qt5Agg")
# else:
#   matplotlib.use('TkAgg')

from matplotlib import pyplot as plt

from env.hopf_network import HopfNetwork
from env.quadruped_gym_env import QuadrupedGymEnv

ADD_CARTESIAN_PD = False
PLOT = False
TIME_STEP = 0.001
foot_y = 0.0838  # this is the hip length
sideSign = np.array([-1, 1, -1, 1])  # get correct hip sign (body right is negative)

env = QuadrupedGymEnv(render=True,  # visualize
                      on_rack=False,  # useful for debugging!
                      isRLGymInterface=False,  # not using RL
                      time_step=TIME_STEP,
                      action_repeat=1,
                      motor_control_mode="TORQUE",
                      add_noise=False,  # start in ideal conditions
                      # record_video=True
                      )

gait = "WALK"

if gait == "TROT":
    cpg = HopfNetwork(time_step=TIME_STEP,
                      gait=gait,
                      omega_swing=8 * 2 * np.pi,
                      omega_stance=3 * 2 * np.pi,
                      ground_clearance=0.07)
elif gait == "PACE":
    cpg = HopfNetwork(time_step=TIME_STEP,
                      gait=gait,
                      mu=2,
                      omega_swing=6 * 2 * np.pi,
                      omega_stance=8 * 2 * np.pi,
                      robot_height=0.23)
elif gait == "BOUND":
    cpg = HopfNetwork(time_step=TIME_STEP,
                      gait=gait,
                      mu=2,
                      omega_swing=6 * 2 * np.pi,
                      omega_stance=20 * 2 * np.pi,
                      robot_height=0.2,
                      des_step_len=0.07,
                      ground_penetration=0.023,
                      ground_clearance=0.07)
elif gait == "WALK":
    cpg = HopfNetwork(time_step=TIME_STEP,
                      gait=gait,
                      mu=3,
                      omega_swing=10 * 2 * np.pi,
                      omega_stance=5 * 2 * np.pi)
else:
    raise ValueError(gait + ' not implemented.')

TEST_DURATION = 10
TEST_STEPS = int(TEST_DURATION / TIME_STEP)
t = np.arange(TEST_STEPS) * TIME_STEP

if PLOT:
    joint_pos = np.zeros((12, TEST_STEPS))

# joint PD gains
kp = np.array([100, 100, 100])
kd = np.array([2, 2, 2])
# Cartesian PD gains
kpCartesian = np.diag([50] * 3)
kdCartesian = np.diag([2] * 3)

for j in range(TEST_STEPS):
    # initialize torque array to send to motors
    action = np.zeros(12)
    # get desired foot positions from CPG
    xs, zs = cpg.update()

    q = env.robot.GetMotorAngles()
    dq = env.robot.GetMotorVelocities()

    # loop through desired foot positions and calculate torques
    for i in range(4):
        # initialize torques for legi
        tau = np.zeros(3)
        # get desired foot i pos (xi, yi, zi) in leg frame
        leg_xyz = np.array([xs[i], sideSign[i] * foot_y, zs[i]])
        # call inverse kinematics to get corresponding joint angles (see ComputeInverseKinematics() in quadruped.py)
        leg_q = env.robot.ComputeInverseKinematics(i, leg_xyz)
        # Add joint PD contribution to tau for leg i (Equation 4)
        tau += kp * (leg_q - q[i * 3:i * 3 + 3]) + kd * (-dq[i * 3:i * 3 + 3])

        # add Cartesian PD contribution
        if ADD_CARTESIAN_PD:
            # Get current Jacobian and foot position in leg frame (see ComputeJacobianAndPosition() in quadruped.py)
            J, foot_pos = env.robot.ComputeJacobianAndPosition(i)
            # Get current foot velocity in leg frame (Equation 2)
            foot_vel = J @ dq[i * 3:i * 3 + 3]
            # Calculate torque contribution from Cartesian PD (Equation 5) [Make sure you are using matrix
            # multiplications]
            tau += kpCartesian @ (leg_xyz - foot_pos) + kdCartesian @ (-foot_vel)

        # Set tau for legi in action vector
        action[3 * i:3 * i + 3] = tau

    # send torques to robot and simulate TIME_STEP seconds
    env.step(action)

    if PLOT:
        joint_pos[:, j] = q

#####################################################
# PLOTS
#####################################################

if PLOT:
    plt.figure()
    plt.plot(t, joint_pos[3 * 0 + 1, :], label='FR thigh')
    plt.plot(t, joint_pos[3 * 1 + 1, :], label='FL thigh')
    plt.plot(t, joint_pos[3 * 2 + 1, :], label='RR thigh')
    plt.plot(t, joint_pos[3 * 3 + 1, :], label='RL thigh')
    plt.legend()
    plt.figure()
    plt.plot(t, joint_pos[3 * 0 + 0, :], label='FR hip')
    plt.plot(t, joint_pos[3 * 0 + 1, :], label='FR thigh')
    plt.plot(t, joint_pos[3 * 0 + 2, :], label='FR calf')
    plt.legend()
    plt.show()
