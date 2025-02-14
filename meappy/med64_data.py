#!/usr/bin/env python
# coding: utf-8

import os, re
import csv
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import scipy.io
from scipy import signal, stats

# constants
bins_per_sec = 1000 # make 1000 for 1Hz analysis
lag_bins = 5
lag_bins_ms = np.arange(-lag_bins, lag_bins + 1) * (1000 / bins_per_sec)



def find_expt_files(data_dir):
    files = os.listdir(data_dir)

    re_units = re.compile(r'^units.*')
    re_tx = re.compile(r'^treatmentinfo.*')
    re_expr_id = re.compile(r"([0-9]{3}_[0-9]{2}h[0-9]{2}m[0-9]{2}s)\.['csv|mat']{3}")

    unit_files = dict()
    tx_files = dict()

    for file in files:
        expr_id = re_expr_id.findall(file)
        if expr_id:
            units_file = re_units.findall(file)
            if units_file:
                unit_files[expr_id[0]] = units_file[0]
            tx_file = re_tx.findall(file)
            if tx_file:
                tx_files[expr_id[0]] = tx_file[0]
    expt_list = sorted(list(unit_files.keys()))

    print('FOUND Data FILES:')
    print('Experiment IDs: \n\t' + '\n\t'.join(expt_list))
    print('Units Files: \n\t' + '\n\t'.join(unit_files.values()))
    print('Treatment Files: \n\t' + '\n\t'.join(tx_files.values()))
    
    return expt_list, tx_files, unit_files


def read_tx_file(tx_filename):
    tx_times = dict()
    with open(tx_filename) as csvDataFile:
        csvReader = csv.reader(csvDataFile)
        for row in csvReader:
            tx_times[row[1]] = float(row[0])
    return tx_times


def extract_units_mat_data(units_mat):
    """extract timestamps into flatter structure from units_xxx.mat file"""
    TS = 0
    MWAVE = 1
    data_key = mat_data_key(units_mat)
    num_units = units_mat[data_key][0].shape[0]
    timestamps = dict()
    for u in range(num_units):
        timestamps[u] = dict()
        timestamps[u]['timestamps'] = np.sort(units_mat[data_key][0][u][TS][0])
        timestamps[u]['waveform'] = units_mat[data_key][0][u][MWAVE]
    return timestamps


def mat_data_key(mat_dat_object):
    """Finds first key in object besides __header__, etc."""
    object_keys = mat_dat_object.keys()
    data_keys = [k for k in object_keys if ("__" not in k)]
    if (len(data_keys) > 1):
        print("Warning: More than one data key found in Matlab file")
    return data_keys[0]


def read_units_file(unit_filename):
    units_mat = scipy.io.loadmat(unit_filename)
    return extract_units_mat_data(units_mat)


def get_expt_data(data_dir, expt_id, unit_files, tx_files):
    unit_filename = data_dir + unit_files[expt_id]
    units_data = read_units_file(unit_filename)

    tx_filename = data_dir + tx_files[expt_id]
    tx_times = read_tx_file(tx_filename)
    
    return units_data, tx_times


def rug_thinning_factor(num_ts):
    """returns thinning factor for optimal visualization of rug.
    use return value as index slicing step size.
    """
    max_ts_num = 150
    if num_ts <= max_ts_num:
        return 1
    return int(num_ts / max_ts_num)


def get_hist_bins(timestamps, bin_sec):
    """Create bins for historgram plot using a bin duration
    of the desiganted bin_sec for number of seconds per bin.
    Returns ND array of beginning time of each bin, plus end 
    time of last bin. Starts first bin at zero.
    """
    num_bins = np.floor(timestamps.max() / bin_sec) + 1
    start = 0
    stop = num_bins * bin_sec
    return np.linspace(start, stop, num = (num_bins+1))


def plot_expt_histo(timestamps, tx_times, bin_sec):
    num_ts = timestamps.shape[0]
    bins = get_hist_bins(timestamps, bin_sec)
    max_tx = max(tx_times.values())

    fig, ax1 = plt.subplots(figsize=(8,4))
    ax2 = ax1.twinx()

    # plot kernel density
    density = stats.kde.gaussian_kde(timestamps)
    x = np.arange(timestamps.min(), timestamps.max(), 0.1)
    kde_x = density(x)
    ax2.plot(x, kde_x)
    
    # plot hist
    # N is the count in each bin, bins is the lower-limit of the bin
    counts, bin_edges = np.histogram(timestamps, bins=bins)
    N, bins, patches = ax1.hist(bins[:-1], bins=bins, weights=(counts/bin_sec), alpha=0.4)

    # plot rug
    thin_rug = rug_thinning_factor(num_ts) # improves visualization, make func
    rug_height = N.min() #kde_x.min()
    ax1.plot(timestamps[::thin_rug], [rug_height]*len(timestamps[::thin_rug]), '|', color='k');

    # plot treatment boundary times
    y_span = np.linspace(0, N.max(), num=2)

    for tx, tx_time in tx_times.items():
        ax1.plot((tx_time * np.ones(2)), y_span)
        ax1.annotate(tx, (tx_time, 0.5), rotation=90)
    
    plt.xlim(0, max_tx)

    ax1.set_ylabel('Unit Activity (Hz)')
    ax1.set_xlabel('Experiment Time (s)')
    ax2.set_ylabel('Kernel Density')
    plt.show()


def get_array_from_ts(timestamps, ts_index_max=None):
    if not ts_index_max:
        ts_index_max = int(timestamps.max() * bins_per_sec) + 1
    ts_array = np.zeros(ts_index_max)
    ts_event_indices = (timestamps * bins_per_sec).astype(int)

    for i in ts_event_indices:
        ts_array[i] += 1
    return ts_array


def autocorr(timestamps):
    """return the auto-correlation of a list of time stamps of activity.
    The auto-correlation is done at 1 ms resolution and -5 to +5 ms lags.
    RETURN array of auto-correlation values in 1 ms bins from -5 to +5 sliding
    lag.
    """
    ts_array = get_array_from_ts(timestamps)
    ts_arr_lag = ts_array[lag_bins:-lag_bins]
    autocorr = (signal.correlate(ts_array, ts_arr_lag, mode = 'valid') 
                / (ts_array.sum() + 1))
    return lag_bins_ms, autocorr


def crosscorr(timestamps_a, timestamps_b):
    """return the cross-correlation of two list of time stamps of activities
    """
    ts_max = np.append(timestamps_a, timestamps_b).max()
    ts_index_max = int(ts_max * bins_per_sec) + 1

    ts_array_a = get_array_from_ts(timestamps_a, ts_index_max)
    ts_array_b = get_array_from_ts(timestamps_b, ts_index_max)
    ts_arr_b_lag = ts_array_b[lag_bins:-lag_bins]
    crosscorr = (signal.correlate(ts_array_a, ts_arr_b_lag, mode = 'valid') 
                / (ts_array_a.sum() + 1))
    return lag_bins_ms, crosscorr


def make_grid_array(num_units):
    """takes any number of units >3 and returns an array of indices
    for ploting a grid of units
    """
    num_units = num_units if num_units >= 4 else 4
    max_cols = 4
    x=np.arange(num_units)
    dim2 = min(int(np.floor(np.sqrt(num_units))), max_cols)
    dim1 = int(np.ceil(num_units / dim2))
    x.resize(dim1*dim2)
    x.shape
    return x.reshape(dim1,dim2)


def plot_autocorr_grid(units_data, num_units):
    """
    works for min of 4 plots

    :param units_data: array of units timestamps
    :param num_units: optional. number of units to plot. default is all
    :return: None, displays matplotlib plot
    """
    if not num_units:
        num_units = len(units_data.keys())

    grid_array = make_grid_array(num_units)
    nrows, ncols = grid_array.shape

    autocorrs_units = dict()

    fig, axs = plt.subplots(*grid_array.shape, sharex='all', figsize=(ncols*3,nrows*2))

    for row, cols in enumerate(grid_array):
        for col, unit in enumerate(cols):
            if not (unit == 0 and col != 0):
                lag_bins_ms, autocorrs_units[unit] = autocorr(units_data[unit]['timestamps'])
                axs[row, col].bar(lag_bins_ms, autocorrs_units[unit])
                axs[row, col].set_title('Unit # ' + str(unit))
            if row == (nrows-1):
                axs[row, col].set_xlabel('lag in ms')
            if col == 0:
                axs[row, col].set_ylabel('correlation')
    plt.suptitle(f'Auto-Correlogram', y=(1 - 0.008*nrows));


def plot_crosscorr_grid(units_data, reference_unit, num_units):
    if not num_units:
        num_units = len(units_data.keys())
    grid_array = make_grid_array(num_units)
    nrows, ncols = grid_array.shape

    crosscorrs_units = dict()

    fig, axs = plt.subplots(*grid_array.shape, sharex='all', figsize=(ncols*3,nrows*2))

    for row, cols in enumerate(grid_array):
        for col, unit in enumerate(cols):
            if not (unit == 0 and col != 0):
                lag_bins_ms, crosscorrs_units[unit] = crosscorr(units_data[reference_unit]['timestamps'],
                                             units_data[unit]['timestamps'])
                axs[row, col].bar(lag_bins_ms, crosscorrs_units[unit])
                axs[row, col].set_title('Unit # ' + str(unit))
            if row == (nrows-1):
                axs[row, col].set_xlabel('lag in ms')
            if col == 0:
                axs[row, col].set_ylabel('correlation')
    plt.suptitle('Cross-Correlograms', y=(1 - 0.008*nrows));


def hist_subplot(units_data, unit, tx_times, bin_sec, row, col, axs1, axs2, nrows, ncols):
    timestamps = units_data[unit]['timestamps']

    num_ts = timestamps.shape[0]
    bins = get_hist_bins(timestamps, bin_sec)
    max_tx = max(tx_times.values())

    # plot hist
    # N is the count in each bin, bins is the lower-limit of the bin
    counts, bin_edges = np.histogram(timestamps, bins=bins)
    N, bins, patches = axs1[row, col].hist(bins[:-1], bins=bins, weights=(counts/bin_sec), alpha=0.4)

    # plot rug
    thin_rug = rug_thinning_factor(num_ts) # improves visualization, make func
    rug_height = N.min()
    axs1[row, col].plot(timestamps[::thin_rug], [rug_height]*len(timestamps[::thin_rug]), '|', color='k');

    # plot treatment boundary times
    y_span = np.linspace(0, N.max(), num=2)
    
    for tx, tx_time in tx_times.items():
        axs1[row, col].plot((tx_time * np.ones(2)), y_span)
        axs1[row, col].annotate(tx, (tx_time, (N.max()*0.1)), rotation=90)

    plt.xlim(0, max_tx)

    axs1[row, col].set_title('Unit # ' + str(unit)) 
    if col == 0:
        axs1[row, col].set_ylabel('Unit Activity (Hz)')
    if row == (nrows-1):
        axs1[row, col].set_xlabel('Experiment Time (s)')


def plot_hist_grid(units_data, tx_times, bin_sec, num_units):
    grid_array = make_grid_array(num_units)
    nrows, ncols = grid_array.shape

    fig, axs1 = plt.subplots(*grid_array.shape, sharex='all', figsize=(ncols*4,nrows*3))
    axs2 = axs1 

    for row, cols in enumerate(grid_array):
        for col, unit in enumerate(cols):
            if not (unit == 0 and col != 0):
                hist_subplot(units_data, unit, tx_times, bin_sec, row, col, axs1, axs2, nrows, ncols)
    return fig
