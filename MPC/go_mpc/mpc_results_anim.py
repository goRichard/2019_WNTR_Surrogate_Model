import pandas
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.animation import FuncAnimation, FFMpegWriter, ImageMagickWriter

import pickle
import wntr
import wntr.metrics.economic as economics
import sys
sys.path.append('../../Code/')
from testWN import testWN as twm
import numpy as np
import pandas as pd
import scipy.io as sio
from go_mpc import go_mpc
from casadi import *
import pdb

colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

matplotlib.rcParams['font.size'] = 12
matplotlib.rcParams['axes.unicode_minus'] = False
matplotlib.rcParams['svg.fonttype'] = 'none'

output_format = 'gif'
"""
-------------------------------------------------------
Load Network
-------------------------------------------------------
"""
inp_file = '../../Code/c-town_true_network_simplified_controls.inp'
ctown = twm(inp_file)

## nodes = ctown.getNodeName()
link_names = ctown.getLinkName()
node_names = ctown.getNodeName()
pump_df = pd.DataFrame(np.ones(len(link_names[0])).reshape(1, -1), columns=link_names[0])
valves_df = pd.DataFrame(2*np.ones(len(link_names[2])).reshape(1, -1), columns=link_names[2])
pv_df = pd.concat((pump_df, valves_df), axis=1)

nw_node_df = pd.DataFrame(ctown.wn.nodes.todict())
nw_link_df = pd.DataFrame(ctown.wn.links.todict())


n_horizon = 10
nn_model_name = '018_man_4x50_25cl'
nn_model_path = './model/{}/'.format(nn_model_name)
cluster_labels = pd.read_json(nn_model_path+'cluster_labels_25cl.json')
pressure_factor = pd.read_json(nn_model_path+'pressure_factor_25cl.json')
gmpc = go_mpc(n_horizon, nn_model_path, nn_model_name, cluster_labels, pressure_factor, 0, 1)


"""
-------------------------------------------------------
Load Results
-------------------------------------------------------
"""
data_path = '/home/ffiedler/tubCloud/Shared/WDN_SurrogateModels/_RESULTS/MPC/001_economic/'
mpc_res = sio.loadmat(data_path + '027_mod_018_results_full_mpc_sol.mat')
obj_x_full = mpc_res['x_mpc_full']
obj_aux_full = mpc_res['mpc_aux_full']

with open(data_path+'027_mod_018_results_sim_time.pkl', 'rb') as f:
    results = pickle.load(f)


fig = plt.figure(figsize=(12, 7))
ax1 = plt.subplot2grid((4, 5), (0, 0), rowspan=4, colspan=2)
ax2 = plt.subplot2grid((4, 5), (0, 2), colspan=3)
ax3 = plt.subplot2grid((4, 5), (1, 2), colspan=3, sharex=ax2)
ax4 = plt.subplot2grid((4, 5), (2, 2), colspan=3, sharex=ax2)
ax5 = plt.subplot2grid((4, 5), (3, 2), colspan=3, sharex=ax2)

ax2.yaxis.tick_right()
ax2.yaxis.set_label_position("right")
ax2.get_xaxis().set_visible(False)

ax3.yaxis.tick_right()
ax3.yaxis.set_label_position("right")
ax3.get_xaxis().set_visible(False)

ax4.yaxis.tick_right()
ax4.yaxis.set_label_position("right")

ax5.yaxis.tick_right()
ax5.yaxis.set_label_position("right")

ax2.set_ylabel('Tank level [m]')
ax3.set_ylabel('Pump speed [-]')
ax4.set_ylabel('Normalized \n valve setting [-]')
ax5.set_ylabel('Minimal \n pressure [m]')
ax5.set_xlabel('time [h]')

fig.align_ylabels()
fig.tight_layout()
fig.tight_layout(pad=0.5)

results.node['pressure'][node_names[0]].head()
tank_level = results.node['pressure'][node_names[0]].to_numpy()
pump_speed = results.link['setting'][link_names[0]].to_numpy()
norm_valve = (results.link['setting'][link_names[2]]/np.array([600, 600, 600, 70])).to_numpy()
jun_cl_press_min_res = results.press_cl_min.to_numpy()

time = (results.node['pressure'].index/3600).to_numpy()
dt = 1  # h
plot_horizon = 20

t_end_anim = 180  # time.shape[0]


def update(t):
    print(t)
    try:
        cb = ax1.collections[1].colorbar
        cb.remove()
    except:
        None

    ax1.cla()
    ax2.cla()
    ax3.cla()
    ax4.cla()
    ax5.cla()

    press_now = results.node['pressure'].iloc[t]
    valves_now = results.link['setting'][link_names[2]].iloc[t]/np.array([600, 600, 600, 70])
    pumps_now = results.link['setting'][link_names[0]].iloc[t]

    wntr.graphics.plot_network(ctown.wn, node_attribute=press_now[node_names[2]], node_size=40,
                               node_cmap='CMRmap', add_colorbar=True, ax=ax1)  # CMRmap

    mesh = ax1.collections[1]
    mesh.set_clim(0, 150)

    for i, link_i in enumerate(link_names[0]):
        start_i = nw_link_df[link_i].loc['start_node'].__dict__['_coordinates']
        end_i = nw_link_df[link_i].loc['end_node'].__dict__['_coordinates']
        data = np.array([start_i, end_i]).T
        pump_line = ax1.plot(data[0], data[1], linewidth=pumps_now[link_i]*8, color=colors[0])

        # ax1.text(*start_i, link_i, ha="center", va="center",
        #          bbox=dict(boxstyle="round", ec='k', fc=colors[0], alpha=0.3))

    for i, link_i in enumerate(link_names[2]):
        start_i = nw_link_df[link_i].loc['start_node'].__dict__['_coordinates']
        end_i = nw_link_df[link_i].loc['end_node'].__dict__['_coordinates']
        data = np.array([start_i, end_i]).T
        valve_line = ax1.plot(data[0], data[1], linewidth=valves_now[link_i]*8, color=colors[1])

        # ax1.text(*start_i, link_i, ha="center", va="center",
        #          bbox=dict(boxstyle="round", ec='k', fc=colors[1], alpha=0.3))

    for i, node_i in enumerate(node_names[0]):
        coords_i = nw_node_df[node_i].loc['coordinates']
        tank_dot = ax1.scatter(coords_i[0], coords_i[1], s=20*press_now[node_i], color=colors[2])
        # ax1.text(*coords_i, node_i, ha="center", va="center",
        #          bbox=dict(boxstyle="round", ec='k', fc=colors[2], alpha=0.3))

        # ax1.text(*coords_i, node_i, ha="center", va="center",
        #          bbox=dict(boxstyle="round", ec='k', fc=colors[3], alpha=0.3))

    for i, node_i in enumerate(node_names[1]):
        coords_i = nw_node_df[node_i].loc['coordinates']
        reservoir_dot = ax1.scatter(coords_i[0], coords_i[1], s=50, color=colors[3])

    #ax1.legend(pump_line+valve_line+[tank_dot, reservoir_dot], ['pumps', 'valves', 'tanks', 'reservoir'], loc='upper left')

    # Get current x prediction:
    if t > 0:
        obj_x_now = gmpc.obj_x(obj_x_full[t-1, :])
        obj_aux_now = gmpc.mpc_obj_aux(obj_aux_full[t-1, :])

        time_pred = np.arange(t, t+11*dt, dt)-dt
        t_start = np.maximum(0, t-plot_horizon)
        x_pred = horzcat(*obj_x_now['x', :, 'tank_press']).full().T
        # Tank level plot:
        ax2.plot(time[t_start:t], tank_level[t_start:t, :])
        ax2.set_prop_cycle(None)
        ax2.plot(time_pred, x_pred, '--')
        ax2.set_ylabel('Tank level [m]')
        ax2.set_ylim(0, 6)

        pump_pred = horzcat(*obj_x_now['u', :, 'head_pump']).full().T
        # Tank level plot:
        ax3.step(time[t_start:t], pump_speed[t_start:t, :])
        ax3.set_prop_cycle(None)
        ax3.step(time_pred[:-1], pump_pred, '--')
        ax3.set_ylabel('Pump speed [-]')
        ax3.set_ylim(0, 1)

        PRvalve_pred = horzcat(*obj_x_now['u', :, 'PRValve']).full().T/600
        TCvalve_pred = horzcat(*obj_x_now['u', :, 'TCValve']).full().T/70
        valve_pred = np.concatenate((PRvalve_pred, TCvalve_pred), axis=1)
        ax4.step(time[t_start:t], norm_valve[t_start:t, :])
        ax4.set_prop_cycle(None)
        ax4.step(time_pred[:-1], valve_pred, '--')

        ax4.set_ylabel('Normalized \n valve setting [-]')
        ax4.set_ylim(0, 1)

        jun_cl_press_min_sc = horzcat(*obj_aux_now['nl_cons', :, 'jun_cl_press_min']).full().T
        jun_cl_press_min_eps = horzcat(*obj_x_now['eps', :, 'jun_cl_press_min']).full().T
        jun_cl_press_min = jun_cl_press_min_sc-jun_cl_press_min_eps

        ax5.plot(time[t_start:t], jun_cl_press_min_res[t_start:t, :])
        ax5.set_prop_cycle(None)
        ax5.plot(time_pred[:-1], jun_cl_press_min, '--')

        ax5.set_ylabel('minimal \n pressure [m]')
        ax5.set_xlabel('time [h]')
        ax5.set_ylim(-10, 120)


anim = FuncAnimation(fig, update, frames=t_end_anim, repeat=False)

if 'mp4' in output_format:
    FFWriter = FFMpegWriter(fps=6, extra_args=['-vcodec', 'libx264'])
    anim.save('anim.mp4', writer=FFWriter)
elif 'gif' in output_format:
    gif_writer = ImageMagickWriter(fps=3)
    anim.save('anim.gif', writer=gif_writer)
else:
    plt.show()
