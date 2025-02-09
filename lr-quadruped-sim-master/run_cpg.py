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

PLOT = True
SAVEFIG = False
TEST_DURATION = 4
TIME_STEP = 0.001

ADD_CARTESIAN_PD = False
JOINT_PD = True
POSTURECTRL = False

foot_y = 0.0838  # this is the hip length
sideSign = np.array([-1, 1, -1, 1])  # get correct hip sign (body right is negative)
rmass = 15 # A1 mass in kg
hspdavg = 0
hspdh = np.zeros(1000) #avg of speed past 1 sec
hspdidx = 0

# joint PD gains
kp = np.array([100, 100, 100])
kd = np.array([2, 2, 2])
# Cartesian PD gains
kpCartesian = np.diag([1200,400,1200])
kdCartesian = np.diag([20,4,20])
# posture control
pKp = np.diag([100,100,10])
yxzshift = [0,0,0]

env = QuadrupedGymEnv(render=True,  # visualize
                      on_rack=False,  # useful for debugging!
                      isRLGymInterface=False,  # not using RL
                      time_step=TIME_STEP,
                      action_repeat=1,
                      motor_control_mode="TORQUE",
                      add_noise=False,  # start in ideal conditions
                      # record_video=True
                      )

# initialize Hopf Network, supply gait
cpg = HopfNetwork(time_step=TIME_STEP)

TEST_STEPS = int(TEST_DURATION / TIME_STEP)
t = np.arange(TEST_STEPS) * TIME_STEP

gait = "FAST_BOUND"

if gait == "TROT":
    stepfreq = 8
    duty_ratio = 2
    ratio = 1/(duty_ratio + 1)
    cpg = HopfNetwork(time_step=TIME_STEP,
                      gait=gait,
                      mu= 1,
                      des_step_len=0.05,
                      omega_swing= stepfreq*(1-ratio) * 2 * np.pi,
                      omega_stance= stepfreq*(ratio) * 2 * np.pi)
elif gait == "PACE":
    cpg = HopfNetwork(time_step=TIME_STEP,
                      gait=gait,
                      mu=2,
                      omega_swing=6 * 2 * np.pi,
                      omega_stance=8 * 2 * np.pi,
                      robot_height=0.23)
elif gait == "FAST_BOUND":
    stepfreq = 10
    ratio = 0.65
    cpg = HopfNetwork(time_step=TIME_STEP,
                      gait="BOUND",
                      ground_penetration=0.005, 
                      des_step_len=0.13,
                      omega_swing= stepfreq*(1-ratio) * 2 * np.pi,
                      omega_stance= stepfreq*(ratio) * 2 * np.pi,
                      )
elif gait == "BOUND":
    stepfreq = 8.2
    ratio = 0.5
    cpg = HopfNetwork(time_step=TIME_STEP,
                      gait=gait,
                      omega_swing= stepfreq*(1-ratio) * 2 * np.pi,
                      omega_stance= stepfreq*(ratio) * 2 * np.pi,
                      )
elif gait == "WALK":
    duty_ratio = 3
    stepfreq = 1
    ratio = 1/(duty_ratio + 1)

    cpg = HopfNetwork(time_step=TIME_STEP,
                      gait=gait,
                      mu=3,
                      des_step_len=0.05,
                      omega_swing= stepfreq*(1-ratio) * 2 * np.pi,
                      omega_stance= stepfreq*(ratio) * 2 * np.pi)
elif gait == "PRONK":
    cpg = HopfNetwork(time_step=TIME_STEP,
                      gait=gait,
                      mu=3,
                      ground_clearance=0.1,
                      des_step_len=0.05,
                      ground_penetration=0.01,
                      omega_swing=3 * 2 * np.pi,
                      omega_stance=5 * 2 * np.pi)
else:
    raise ValueError(gait + ' not implemented.')

if PLOT:
    joint_pos = np.zeros((12, TEST_STEPS))
    des_joint_pos = np.zeros((12, TEST_STEPS))
    cpg_states = np.zeros((16,TEST_STEPS))
    foots_coord = np.zeros((12,TEST_STEPS))
    cpg_coord = np.zeros((8,TEST_STEPS))
    energy = np.zeros(TEST_STEPS)
    spd = np.zeros((3,TEST_STEPS))
    Cot = np.zeros(TEST_STEPS)


for j in range(TEST_STEPS):
    # initialize torque array to send to motors
    action = np.zeros(12) 
    # get desired foot positions from CPG 
    xs,zs = cpg.update()

    q = env.robot.GetMotorAngles()
    dq = env.robot.GetMotorVelocities()
    ori = env.robot.GetBaseOrientationRollPitchYaw()

    # loop through desired foot positions and calculate torques
    for i in range(4):
        # initialize torques for legi
        tau = np.zeros(3)
        # get desired foot i pos (xi, yi, zi) in leg frame
        if gait == "PRONK":
            leg_xyz = np.array([xs[i] - 0.1, sideSign[i] * foot_y, zs[i]])
        elif gait == "FAST_BOUND":
            leg_xyz = np.array([xs[i] - 0.077, sideSign[i] * foot_y, zs[i]])
        else:
            leg_xyz = np.array([xs[i], sideSign[i] * foot_y, zs[i]])
        # call inverse kinematics to get corresponding joint angles (see ComputeInverseKinematics() in quadruped.py)
        leg_q = env.robot.ComputeInverseKinematics(i, leg_xyz)
        if PLOT:
            des_joint_pos[3*i:3*i+3,j] = leg_q[:]
        
        if JOINT_PD:
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
            tau += np.transpose(J) @ (kpCartesian @ (leg_xyz - foot_pos) + kdCartesian @ (-foot_vel))

        if POSTURECTRL:
            J, foot_pos = env.robot.ComputeJacobianAndPosition(i)
            front = 1 if i<2 else -1
            zcont = (front*-ori[1]) + (sideSign[i]*ori[0])
            leg_corr_xyz = leg_xyz + [-foot_pos[2]*np.tan(ori[1])*yxzshift[0],foot_pos[2]*np.tan(ori[0])*yxzshift[1],zcont*yxzshift[2]]
            tau += np.transpose(J) @ (pKp @ (leg_corr_xyz - foot_pos))

        # Set tau for legi in action vector
        action[3 * i : 3 * i + 3] = tau

    if PLOT:
        energy[j] = abs(np.dot(env.robot.GetMotorTorques(),dq))
        spd[:,j] = env.robot.GetBaseLinearVelocity()
        Cot[j] = (energy[j]*TIME_STEP)/(np.linalg.norm(spd[:,j])*TIME_STEP*rmass)
        hspdh[hspdidx] = np.linalg.norm(spd[0:2,j])
        hspdidx = hspdidx+1 if hspdidx+1<1000 else 0
        hspdavg = np.mean(hspdh)
        joint_pos[:, j] = q
        cpg_states[0:4,j] = cpg.get_r()
        cpg_states[4:8,j] = cpg.get_theta()
        cpg_states[8:12,j] = cpg.get_dr()
        cpg_states[12:16,j] = cpg.get_dtheta()
        cpg_coord[:,j] = np.reshape([xs,zs],(8,))
        _,rpos = env.robot.ComputeJacobianAndPosition(0)
        foots_coord[0:3,j] = rpos
        _,rpos = env.robot.ComputeJacobianAndPosition(1)
        foots_coord[3:6,j] = rpos
        _,rpos = env.robot.ComputeJacobianAndPosition(2)
        foots_coord[6:9,j] = rpos
        _,rpos = env.robot.ComputeJacobianAndPosition(3)
        foots_coord[9:12,j] = rpos

    # send torques to robot and simulate TIME_STEP seconds
    env.step(action)

if PLOT: 
    print('\033[91m' + "##### FINAL SPEED = {} #####".format(hspdavg) + '\033[0m')

#####################################################
# PLOTS
#####################################################

if PLOT:
    if False: #joint pos
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

    
    if False: #Cot speed
   
        fig = plt.figure(figsize=(8, 10)) 
        fig.suptitle("{} at {:.2f} m/s".format(gait,hspdavg)) 

        cot = plt.subplot(211)
        cot.set(ylabel='inst CoT')
        plt.tick_params('x', labelbottom=False)
        plt.plot(t, Cot)
        mcot = np.mean(Cot)
        plt.plot([0,TEST_DURATION],[mcot,mcot])

        spdh = plt.subplot(212, sharex=cot)
        spdh.set(ylabel='horizontal speed [m/s]')
        plt.tick_params('x')
        hspd = np.linalg.norm(spd[0:3,:],axis=0)
        plt.plot(t, hspd)
 
        plt.tight_layout()  
        plt.show()

    if False: # joint tracking
        fig, ax = plt.subplots(3, 1, figsize=(8, 6))  # Adjust the figure size as needed
        fig.suptitle("Joint Positions: {} \n PD kp: {}, kd: {}\n cart PD ckp: {} ckd: {}".format(gait,kp,kd,kpCartesian.diagonal(),kdCartesian.diagonal()))
        
        plots = [
            ('Hip', 0),
            ('Thigh', 1),
            ('Calf', 2),
        ]

        for title, idx in plots:
            axis = ax[idx]
            axis.plot(t,joint_pos[idx], label='sim')
            axis.plot(t,des_joint_pos[idx],'--',label='ref',color='#55555555')
            axis.set_title(title)
            axis.set_ylabel("angle [rad]")
            #axis.sharex(ax[idx-1]) if idx<0 else axis.sharex(ax[0])
            axis.sharey(ax[idx-1]) if idx<0 else axis.sharey(ax[0])
            axis.legend()

        ax[2].set_xlabel("time [s]")

        plt.tight_layout()
        plt.show()

    if False: # foot pos
        fig, ax = plt.subplots(2, 2, figsize=(10, 8))  # Adjust the figure size as needed
        fig.suptitle("Foot Positions: {} \n PD kp: {}, kd: {} \n Cart PD kp: {}, kd: {}".format(gait,kp[0],kd[0],kpCartesian[0][0],kdCartesian[0][0]))

        plots = [
            (0, 1, 'Front Right', [0, 4, 0, 2]),
            (0, 0, 'Front Left', [1, 5, 3, 5]),
            (1, 1, 'Rear Right', [2, 6, 6, 8]),
            (1, 0, 'Rear Left', [3, 7, 9, 11])
        ]

        for i, j, title, indices in plots:
            axis = ax[i, j]
            axis.plot(cpg_coord[indices[0], :], cpg_coord[indices[1], :], label='desired')
            axis.plot(foots_coord[indices[2], :], foots_coord[indices[3], :], label='real')
            axis.axis('equal')
            axis.set_title(title)
            axis.legend()

        plt.tight_layout()
        if SAVEFIG:
            plt.savefig("..\PLOTS\CPG\\foot{}_{}-{}-{}-{}".format(gait,kp[0],kd[0],kpCartesian[0],kdCartesian[0]))
        plt.show()

    if False: # cpg states   
        fig = plt.figure(figsize=(8, 10)) 
        fig.suptitle("CPG states: "+gait) 
        r_plot = plt.subplot(411)
        r_plot.set(ylabel='R')
        plt.tick_params('x', labelbottom=False)
        plt.plot(t, cpg_states[0:4, :].T)
        r_plot.legend(['FR', 'FL', 'RR', 'RL'], loc='upper right')  
        theta_plot = plt.subplot(412, sharex=r_plot)
        theta_plot.set(ylabel='Theta')
        plt.tick_params('x', labelbottom=False)
        plt.plot(t, cpg_states[4:8, :].T)
        theta_plot.legend(['FR', 'FL', 'RR', 'RL'], loc='upper right') 
        rdot_plot = plt.subplot(413, sharex=r_plot)
        rdot_plot.set(ylabel='R dot')
        plt.tick_params('x', labelbottom=False)
        plt.plot(t, cpg_states[8:12, :].T)
        rdot_plot.legend(['FR', 'FL', 'RR', 'RL'], loc='upper right') 
        thetadot_plot = plt.subplot(414, sharex=r_plot)
        thetadot_plot.set(ylabel='Theta dot', xlabel='time (s)')
        plt.plot(t, cpg_states[12:16, :].T)
        thetadot_plot.legend(['FR', 'FL', 'RR', 'RL'], loc='upper right')  
        plt.tight_layout()  
        plt.show()

    if False: #joint angle
        fig, axs = plt.subplots(3, 1, figsize=(8, 8))  # Adjust the figure size as needed
        fig.suptitle('Joint Angles')

        plots = [
            (0, 'Hip', [0, 3, 6, 9]),
            (1, 'Thigh', [1, 4, 7, 10]),
            (2, 'Calf', [2, 5, 8, 11])
        ]

        for i, title, indices in plots:
            ax = axs[i]
            ax.set(ylabel= title +'(rad)')
            if i < 2:
                ax.tick_params('x', labelbottom=False)
            else:
                ax.set(xlabel='time (s)')
            for j in range(4):
                ax.plot(t, joint_pos[indices[j], :], label=f'Leg{j + 1}')
            ax.legend()

        plt.tight_layout()
        if SAVEFIG:
            if ADD_CARTESIAN_PD:
                plt.savefig("..\PLOTS\CPG\\joint{}_kp{}kd{}_ckp{}ckd{}".format(gait,kp[0],kd[0],kpCartesian[0][0],kdCartesian[0][0]))
            else:
                plt.savefig("..\PLOTS\CPG\\joint{}_kp{}kd{}".format(gait,kp[0],kd[0]))
        plt.show()
