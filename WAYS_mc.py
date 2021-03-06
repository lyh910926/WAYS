#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author  : Ganquan Mao (ganquan.mao@icloud.com)
# @Link    : https://argansos.github.io
# @Version : 3.6


import os
import time
import random
import numpy as np
import xarray as xr
import pandas as pd

import hypro
from core import toolkit
from core import errlib


# import warnings

# ==================== general configuration ====================
# parameter initialization
par_init = np.array([0, 2, 0, 0.5, 0.3, 0.8, 1, 3, 100, 1.2, 3, 100, 500])
lon = np.linspace(-179.75, 179.75, 720)
lat = np.linspace(89.75, -89.75, 360)

# basic settings for computation
file_config = './configs/WAYS.txt'

# special settings for calibration
file_par_setups = './configs/par_setups.txt'

# read configuration
par_setups = toolkit.read_par_setups(file_par_setups)

# path for crucial files
path_cf = './auxiliary'

# extract the configuration
config = {}
exec(open(file_config).read(), config)

path_i = config['path_i']
path_o_ = config['path_o_']
path_sinit_ = config['path_sinit_']
path_igss_ = config['path_igss_']

par_rix = config['par_rix']

var_id = config['var_id']
f_name = config['f_name']
file_syb = config['file_syb']


# ==================== simulation module ====================
# ==================== simulation module ====================

def simu(coord):
    # coord - [lat, lon]
    lat1 = coord[0]

    # par
    par = par_init.copy()

    i = lat.tolist().index(coord[0])
    j = lon.tolist().index(coord[1])

    prcp = dat_pr[:, i, j]
    tas = dat_tas[:, i, j]
    pet = dat_pet[:, i, j]

    # fill rzsc
    par[12] = rzsc[i, j]  # refresh rzsc

    # s_init
    s_init = sinit[:, i, j]

    if simax_cal:

        # tmin
        tmin = dat_tmin[:, i, j]

        # lu
        lu = int(dat_lu[i, j])

        # igs
        if len(igs) > 0:
            igss = igs[:, i, j]
        else:
            igss = ''

        # simux_pkg
        simax_pkg = [tmin, time_ix, lat1, lu, igss]
    else:
        simax_pkg = []

    mc_evap = np.empty(n_mc)
    mc_rzws = np.empty(n_mc)
    mc_qtot = np.empty(n_mc)

    for i_mc in range(n_mc):
        # replace the initial parameter with fitted one
        par[par_rix[0]] = random.uniform(par_setups[0][1], par_setups[0][2])
        par[par_rix[1]] = random.uniform(par_setups[1][1], par_setups[1][2])

        # replace the initial parameter with fitted one
        for i_ch in num_keep:
            par[par_rix[i_ch]] = par_replace[i_ch, i, j]

        evap, rzws, qtot, _, sinit_e, igs_e = hypro.run(prcp, tas, pet, par, s_init, simax_pkg)
        mc_evap[i_mc] = np.nanmean(evap)
        mc_rzws[i_mc] = np.nanmean(rzws)
        mc_qtot[i_mc] = np.nanmean(qtot)

    cv_evap = errlib.cv(mc_evap)
    cv_rzws = errlib.cv(mc_rzws)
    cv_qtot = errlib.cv(mc_qtot)

    # return values
    return i, j, sinit_e, igs_e, cv_evap, cv_rzws, cv_qtot


# ==================== key function to run modules ====================
# ==================== key function to run modules ====================

def run(time_s, time_e, rzsc_type, phenology='no', mctimes='100', par_ch='01', config_name='WAYS.txt', debug=[], coord=[]):

    from multiprocessing import Pool

    global time_ix, rzsc, par_replace, dat_pr, dat_tas, dat_pet, sinit, simax_cal, file_config, n_mc, num_keep

    if len(mctimes) > 0:
        n_mc = int(mctimes)

    if len(par_ch) > 0:
        num_ch = []
        for i_ch in par_ch:
            num_ch.append(int(i_ch))
        num_full = set([0, 1])
        num_keep = list(num_full - set(num_ch))

    # configuration file
    file_config = os.path.join('./configs', config_name)

    # time information
    time_ix = [time_s, time_e]

    if phenology == 'yes':
        simax_cal = True
        phe_type = 'phe'
    elif phenology == 'no':
        simax_cal = False
        phe_type = 'nophe'

    # par
    file_par = os.path.join(path_cf, 'par_' + rzsc_type + '_' + phe_type + '.nc4')
    ds_par = xr.open_dataset(file_par)
    var_list = [var_name for var_name in ds_par.data_vars]
    par_replace = np.empty([len(var_list), len(ds_par.lat.values), len(ds_par.lon.values)])
    for k in range(len(var_list)):
        par_replace[k, :, :] = ds_par[var_list[k]].values

    # rzsc
    file_rzsc = os.path.join(path_cf, 'rzsc_xx.nc4').replace('xx', rzsc_type)
    ds_rzsc = xr.open_dataset(file_rzsc)
    rzsc = ds_rzsc.rzsc.values

    # reading data (forcing)
    year_s, year_e = toolkit.se_extract(time_s, time_e)
    ncfiles = toolkit.namestr(var_id, file_syb, f_name, year_s, year_e)
    ds_pr = xr.open_mfdataset(toolkit.fullfile(path_i, ncfiles['pr']))
    ds_tas = xr.open_mfdataset(toolkit.fullfile(path_i, ncfiles['tas']))
    ds_pet = xr.open_mfdataset(toolkit.fullfile(path_i, ncfiles['pet']))
    ds_pet['time'] = ds_pr['time'].copy()

    ds_pr = ds_pr.sel(time=slice(time_s, time_e))
    ds_tas = ds_tas.sel(time=slice(time_s, time_e))
    ds_pet = ds_pet.sel(time=slice(time_s, time_e))

    # check the unit
    if ds_pr.pr.attrs['units'].lower() == 'kg m-2 s-1':
        prcp_ratio = 24 * 60 * 60
    else:
        prcp_ratio = 1

    if ds_tas.tas.attrs['units'].lower() == 'k':
        tas_ratio = -273.15
    else:
        tas_ratio = 0

    dat_pr = ds_pr.pr.values * prcp_ratio
    dat_tas = ds_tas.tas.values + tas_ratio
    dat_pet = ds_pet.pet.values

    # s_init
    path_sinit = path_sinit_ + '_' + rzsc_type + '_' + phe_type
    file_sinit = os.path.join(path_sinit, 'sinit_' + year_s + '.nc4')
    if os.path.isfile(file_sinit):
        ds = xr.open_dataset(file_sinit)
        sinit = ds[list(ds.data_vars)[0]].values
    else:
        sinit = np.empty([5, len(lat), len(lon)])

    if simax_cal:
        global dat_tmin, dat_lu, igs
        # tmin
        ds_tmin = xr.open_mfdataset(toolkit.fullfile(path_i, ncfiles['tasmin']))
        ds_tmin = ds_tmin.sel(time=slice(time_s, time_e))
        if ds_tmin.tasmin.attrs['units'].lower() == 'k':
            tmin_ratio = -273.15
        else:
            tmin_ratio = 0
        dat_tmin = ds_tmin.tasmin.values + tmin_ratio

        # lu
        file_lu = os.path.join(path_cf, 'modis_lu2001.nc')
        ds_lu = xr.open_dataset(file_lu)
        dat_lu = ds_lu.lu.values

        # igs
        path_igss = path_igss_ + '_' + rzsc_type + '_' + phe_type
        file_igs = os.path.join(path_igss, 'igs_' + year_s + '.nc4')
        if os.path.isfile(file_igs):
            ds_igs = xr.open_dataset(file_igs)
            igs = ds_igs[list(ds_igs.data_vars)[0]].values
        else:
            igs = ''

    # debug code
    if coord:
        return simu(coord)

    # drop out pixels that are not in the domain based on fitted parameters
    ds = xr.open_dataset(file_par)
    mask = ds[[x for x in ds.data_vars][0]].where(~np.isnan(ds[[x for x in ds.data_vars][0]]))
    coords = mask.to_dataframe().dropna(how='all').index.values.tolist()
    if debug:
        coords = coords[debug[0]:debug[1]]

    # processing
    t1 = time.time()  # time it
    pool = Pool()
    results = pool.map(simu, coords)
    pool.close()
    t2 = time.time()  # time it
    print('Elapsed Time for Calculation:', (t2 - t1) / 3600, 'Hours')

    # debug code
    if debug:
        return

    # initialize the matrix
    R = np.empty((5, 360, 720))
    R[:] = np.nan
    G = np.empty((21, 360, 720))
    G[:] = np.nan
    X0 = np.empty((360, 720))
    X0[:] = np.nan
    X1 = X0.copy()
    X2 = X0.copy()

    # extract the results from the mp-pool
    for element in results:
        R[:, element[0], element[1]] = element[2]
        if simax_cal:
            G[:, element[0], element[1]] = element[3]
        X0[element[0], element[1]] = element[4]
        X1[element[0], element[1]] = element[5]
        X2[element[0], element[1]] = element[6]

    # construct the output netcdf file
    ds_init = xr.Dataset({'s_init': (['time', 'lat', 'lon'], R)}, coords={'lon': (['lon'], lon), 'lat': (['lat'], lat), 'time': pd.date_range('1901-01-01', periods=5)})
    ds_evap = xr.Dataset({'evap': (['lat', 'lon'], X0)}, coords={'lon': (['lon'], lon), 'lat': (['lat'], lat)})
    ds_rzws = xr.Dataset({'rzws': (['lat', 'lon'], X1)}, coords={'lon': (['lon'], lon), 'lat': (['lat'], lat)})
    ds_qtot = xr.Dataset({'qtot': (['lat', 'lon'], X2)}, coords={'lon': (['lon'], lon), 'lat': (['lat'], lat)})
    if simax_cal:
        ds_igss = xr.Dataset({'igs': (['time', 'lat', 'lon'], G)}, coords={'lon': (['lon'], lon), 'lat': (['lat'], lat), 'time': pd.date_range('1901-01-01', periods=21)})

    # generate the standard filename
    syb = 'ways_ffff_hist_nosoc_co2_vvvv_global_tttt_ssss_eeee.nc4'
    syb = syb.replace('ffff', config['f_name'])
    syb = syb.replace('tttt', 'daily')
    syb = syb.replace('ssss', year_s)
    syb = syb.replace('eeee', year_e)

    path_o = path_o_ + '_' + rzsc_type + '_' + phe_type + '_mc_' + par_ch + '_' + mctimes
    file_o_evap = os.path.join(path_o, syb.replace('vvvv', 'evap'))
    file_o_rzws = os.path.join(path_o, syb.replace('vvvv', 'rzws'))
    file_o_qtot = os.path.join(path_o, syb.replace('vvvv', 'qtot'))

    fname_o_init = 's_init_' + str(int(year_e) + 1) + '.nc4'
    file_o_init = os.path.join(path_sinit, fname_o_init)

    if simax_cal:
        fname_o_igss = 'igs_' + str(int(year_e) + 1) + '.nc4'
        file_o_igss = os.path.join(path_igss, fname_o_igss)

    # path
    if not os.path.exists(path_sinit):
        os.makedirs(path_sinit)
    if not os.path.exists(path_o):
        os.makedirs(path_o)
    if simax_cal:
        if not os.path.exists(path_igss):
            os.makedirs(path_igss)

    # saving
    ds_evap.to_netcdf(file_o_evap, format='netCDF4', engine='netcdf4', encoding={'evap': {'zlib': True, 'complevel': 5}})
    ds_rzws.to_netcdf(file_o_rzws, format='netCDF4', engine='netcdf4', encoding={'rzws': {'zlib': True, 'complevel': 5}})
    ds_qtot.to_netcdf(file_o_qtot, format='netCDF4', engine='netcdf4', encoding={'qtot': {'zlib': True, 'complevel': 5}})
    ds_init.to_netcdf(file_o_init, format='netCDF4', engine='netcdf4', encoding={'s_init': {'zlib': True, 'complevel': 5}})
    if simax_cal:
        ds_igss.to_netcdf(file_o_igss, format='netCDF4', engine='netcdf4', encoding={'igs': {'zlib': True, 'complevel': 5}})

    t3 = time.time()  # time it
    print('Elapsed Time for Saving:', (t3 - t2) / 3600, 'Hours')

    print('Job Done!')


# ==================== __main__ ====================
# ==================== __main__ ====================

if __name__ == '__main__':

    t1 = time.time()

    run('2001-01-01', '2010-12-31', 'cru', mctimes=100, debug=[0, 1])

    print(time.time() - t1)
