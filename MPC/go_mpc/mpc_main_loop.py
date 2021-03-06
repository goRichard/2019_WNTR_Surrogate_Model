#!/usr/bin/env python
# coding: utf-8

import os
import pandas as pd
# import sklearn
import numpy as np
import scipy.io as sio
import matplotlib.pyplot as plt
from multiprocessing import Process

import time

import sys
sys.path.append('../../Code/')

from testWN import testWN as twm
import wntr
import wntr.network.controls as controls
import wntr.metrics.economic as economics

from casadi import *

import pickle
import random
import pdb

from mpc_backend import go_mpc

# %% ::: Loading .inp file
inp_file = '../../Code/c-town_true_network_simplified_controls.inp'
ctown = twm(inp_file)
nw_node_df = pd.DataFrame(ctown.wn.nodes.todict())
nw_link_df = pd.DataFrame(ctown.wn.links.todict())
link_names = ctown.getLinkName()

# %% ::: Setting up time and options for simulation
nDaysSim = 30
nHourDay = 24
simTimeSteps = nDaysSim*nHourDay  # Sampling frequency of 15 min


ctown.wn.options.time.hydraulic_timestep = 3600  # 1 hr
ctown.wn.options.time.quality_timestep = 3600  # 1 hr
ctown.wn.options.time.report_timestep = 3600
ctown.wn.options.quality.mode = 'AGE'
ctown.wn.options.results.energystr = True
ctown.wn.options.time.duration = 0

# ::: Getting tank elevations
tankEl = []
for tank, name in ctown.wn.tanks():
    tankEl.append(name.elevation)
np.array(tankEl)
nodeNames = ctown.getNodeName()

# ::: Setting upper and lower bounds to control elements
control_components = ctown.wn.pump_name_list + ctown.wn.valve_name_list
min_control = np.array([0.34, 0.64, 0.64, 0.54, 0.54, 0., 0., 0., 0.])  # Lower bondary for controls
max_control = np.array([1., 1., 1., 1., 1., 150.0, 150.0, 150.0, 70.])  # Upper bondary for controls

# Load clustering information:
nn_model_path = './model/015_man_5x50_only_mpc_b0/'
nn_model_name = '015_man_5x50_only_mpc_b0'
cluster_labels = pd.read_json(nn_model_path+'cluster_labels_only_mpc_03.json')
pressure_factor = pd.read_json(nn_model_path+'pressure_factor_only_mpc_03.json')

result_name = '026_mod_015_results'

# Create controller:
n_horizon = 10
gmpc = go_mpc(n_horizon, nn_model_path, nn_model_name, cluster_labels, pressure_factor, min_control, max_control)

# Create container to store full MPC solution:
x_mpc_full = np.empty((0, gmpc.obj_x_num.shape[0]))
mpc_aux_full = np.empty((0, gmpc.obj_aux_num.shape[0]))
mpc_flag = []
# Plotting function:


def plot_pred(gmpc, results, time_arr):
    # pdb.set_trace()
    plt.close('all')
    fig, ax = plt.subplots(4, 1)
    t_start = np.maximum(0, time_arr[0]-20*3600)
    t_end = time_arr[-1]

    results.tankLevels.plot(ax=ax[0], legend=False)
    x = horzcat(*gmpc.obj_x_num['x']).T.full()
    ax[0].set_prop_cycle(None)
    ax[0].plot(time_arr.reshape(-1, 1), x, '--')
    ax[0].set_xlim(t_start, t_end)

    u_pump = horzcat(*gmpc.obj_x_num['u']).T.full()[:, :5]
    head_pump_speed = results.link['setting'][nw_link_df.keys()[nw_link_df.loc['link_type'] == 'Pump']]
    # head_pump_status = results.link['status'][nw_link_df.keys()[nw_link_df.loc['link_type'] == 'Pump']]
    ax[1].step(time_arr[:-1], u_pump, '--')
    ax[1].set_prop_cycle(None)
    head_pump_speed.plot(ax=ax[1], legend=False)
    ax[1].set_xlim(t_start, t_end)

    p_min = horzcat(*gmpc.obj_aux_num['nl_cons', :, 'jun_cl_press_min']).T.full()
    results.press_cl_min.plot(legend=False, ax=ax[2])
    ax[2].set_prop_cycle(None)
    ax[2].plot(time_arr[:-1], p_min, '--')
    ax[2].set_xlim(t_start, t_end)
    ax[2].set_ylim(-20, 150)
    #
    e_pump = horzcat(*gmpc.obj_aux_num['nl_cons', :, 'pump_energy']).T.full()
    energy_real = results.energy[link_names[0]]/1000
    energy_real.plot(legend=False, ax=ax[3])
    ax[3].set_prop_cycle(None)
    ax[3].plot(time_arr[:-1], e_pump, '--')
    ax[3].set_xlim(t_start, t_end)
    plt.show()


"""
---------------------------------------------------
Initialize simlation:
---------------------------------------------------
"""
# control_vector = np.zeros(9)
# # ::::::::::::::::::::::::::::::::::::::
# ctown.control_action(control_components, control_vector, 0, ctown.wn.options.time.hydraulic_timestep)
#
# # ::: Run the simulation up to the current time step
# sim = wntr.sim.EpanetSimulator(ctown.wn)
# results = sim.run_sim()
# results.tankLevels = results.node['head'][nodeNames[0]]-tankEl
# results.energy = economics.pump_energy(results.link['flowrate'], results.node['head'], ctown.wn)

# %% ::: Simulation with updated controls at each time step
for t in range(simTimeSteps):

    # ::: Initializing random seed
    random.seed(t)

    # ::: Loading .inp file from previous step
    if t > 0:
        ctown.wn.reset_initial_values()
        ctown = twm(tempInpFile)
        # Setting simulation options
        ctown.wn.options.time.hydraulic_timestep = 3600  # 1 hr
        ctown.wn.options.time.quality_timestep = 3600  # 1 hr
        ctown.wn.options.time.report_timestep = 3600
        ctown.wn.options.quality.mode = 'AGE'
        ctown.wn.options.results.energystr = True
        ctown.wn.options.time.duration = 0
        ctown.wn.options.time.duration = t*3600

        """
        ---------------------------------------------------
        Forecasting water demand for the next k steps
        ---------------------------------------------------
        """
        startT = t
        dt_hyd = ctown.wn.options.time.hydraulic_timestep
        lbound_noise = 1.
        ubound_noise = 1.
        demand_pred = ctown.forecast_demand_gnoise(n_horizon, startT*dt_hyd, dt_hyd, lbound_noise, ubound_noise)

        # Cluster demand:
        demand_pred_cl = demand_pred.groupby(cluster_labels.loc['pressure_cluster'], axis=1).sum()

        """
        ---------------------------------------------------
        Get current state:
        ---------------------------------------------------
        """
        x0 = np.maximum(results.tankLevels.iloc[t-1].to_numpy(), 1e-3)
        print(results.tankLevels.iloc[t-1])

        """
        ---------------------------------------------------
        Setup (for current time) and Run controller
        ---------------------------------------------------
        """
        # Setup controller for time t:
        gmpc.obj_p_num['x_0'] = x0
        gmpc.obj_p_num['tvp', :, 'jun_cl_demand_sum'] = vertsplit(demand_pred_cl.to_numpy())
        gmpc.obj_p_num['tvp', :, 'u_prev'] = gmpc.obj_x_num['u']

        gmpc.solve()
        control_vector = gmpc.obj_x_num['u', 0].full().flatten()

        if True:
            x_mpc_full = np.append(x_mpc_full, gmpc.obj_x_num.cat.full().T, axis=0)
            mpc_aux_full = np.append(mpc_aux_full, gmpc.obj_aux_num.cat.full().T, axis=0)
            mpc_flag.append(gmpc.solver_stats['success'])

        # ::::::::::::::::::::::::::::::::::::::
        ctown.control_action(control_components, control_vector, t-1, ctown.wn.options.time.hydraulic_timestep)


    # ::: Running the simulation
    start_time = time.time()
    # ::: Run the simulation up to the current time step
    sim = wntr.sim.EpanetSimulator(ctown.wn)
    results = sim.run_sim()
    results.tankLevels = results.node['head'][nodeNames[0]]-tankEl
    results.energy = economics.pump_energy(results.link['flowrate'], results.node['head'], ctown.wn)
    results.press_cl_min = results.node['pressure'][nodeNames[2]].groupby(cluster_labels.loc['pressure_cluster'], axis=1).min()
    # ::: Saving simulation output
    with open("tempResults/{}_sim_time.pkl".format(result_name), "wb") as f:
        pickle.dump(results, f)
        f.close()

    if False:
        if t >= 1:
            if t >= 2:
                p.terminate()
            time_arr = np.arange(dt_hyd*t, dt_hyd*(t+n_horizon+1), dt_hyd)-dt_hyd
            p = Process(target=plot_pred, args=(gmpc, results.head(-1), time_arr))
            p.start()

    sio.savemat('./tempResults/{}_full_mpc_sol.mat'.format(result_name), {'x_mpc_full': x_mpc_full, 'mpc_aux_full': mpc_aux_full, 'mpc_flag': mpc_flag})

    tempInpFile = "tempResults/{}_tempInpFile.inp".format(result_name)
    ctown.wn.write_inpfile(tempInpFile)
    print('-----------------------------------------------------------')
    print('Step {} of {}'.format(t, simTimeSteps))
    print('Total simulation time: %.3f s' % (time.time()-start_time))
    print('-----------------------------------------------------------')
