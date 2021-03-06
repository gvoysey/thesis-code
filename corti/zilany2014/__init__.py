# Copyright 2013-2014 Marek Rudnicki

# This file is part of cochlea.

# cochlea is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# cochlea is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with cochlea.  If not, see <http://www.gnu.org/licenses/>.


from __future__ import division, print_function, absolute_import

import progressbar

__author__ = "Marek Rudnicki"

import numpy as np

from . import _zilany2014
from .util import calc_cfs
from .zilany2014_rate import run_zilany2014_rate
from corti.base import periph_consts as p
from corti.periphery import PeripheryOutput, PeripheryConfiguration
from tqdm import tqdm


def run_zilany2014(
        sound,
        fs,
        anf_num,
        cf,
        species,
        seed,
        conf,
        level,
        output=None,
        cohc=1,
        cihc=1,
        powerlaw='approximate',
        ffGn=False
):
    """Run the inner ear model by [Zilany2014]_.

    This model is based on the original implementation provided by the
    authors.  The MEX specific code was replaced by Python code in C
    files.  We also compared the outputs of both implementation (see
    the `tests` directory for unit tests).


    Parameters
    ----------
    sound : array_like
        The input sound in Pa.
    fs : float
        Sampling frequency of the sound in Hz.
    anf_num : tuple
        The desired number of auditory nerve fibers per frequency
        channel (CF), (HSR#, MSR#, LSR#).  For example, (100, 75, 25)
        means that we want 100 HSR fibers, 75 MSR fibers and 25 LSR
        fibers per CF.
    cf : float or array_like or tuple
        The center frequency(s) of the simulated auditory nerve fibers.
        If float, then defines a single frequency channel.  If
        array_like (e.g. list or ndarray), then the frequencies are
        used.  If tuple, then must have exactly 3 elements (min_cf,
        max_cf, num_cf) and the frequencies are calculated using the
        Greenwood function.
    species : {'cat', 'human', 'human_glasberg1990'}
        Species.
    seed : int
        Random seed for the spike generator.
    conf: PeripheryConfiguration
        Runtime data.
    cohc : float <0-1>, optional
        Degredation of the outer hair cells.
    cihc : float <0-1>, optional
        Degredation of the inner hair cells.
    powerlaw : {'approximate', 'actual'}, optional
        Defines which power law implementation should be used.
    ffGn : bool
        Enable/disable factorial Gaussian noise.


    Returns
    -------
    spike_trains
        Auditory nerve spike trains.


    References
    ----------
    If you are using results of this or modified version of the model
    in your research, please cite [Zilany2014]_.


    .. [Zilany2014] Zilany, M. S., Bruce, I. C., & Carney,
       L. H. (2014). Updated parameters and expanded simulation
       options for a model of the auditory periphery. The Journal of
       the Acoustical Society of America, 135(1), 283-286.

    """
    assert np.max(sound) < 1000, "Signal should be given in Pa"
    assert sound.ndim == 1
    assert species in ('cat', 'human', 'human_glasberg1990')

    np.random.seed(seed)

    cfs = calc_cfs(cf, species)

    channel_args = [
        {
            'signal'  : sound,
            'cf'      : cf,
            'fs'      : fs,
            'cohc'    : cohc,
            'cihc'    : cihc,
            'anf_num' : anf_num,
            'powerlaw': powerlaw,
            'seed'    : seed,
            'conf'    : conf,
            'level'   : level,
            'species' : species,
            'ffGn'    : ffGn,
        }
        for cf in cfs
        ]

    ### Run model for each channel
    # nested = map(
    #        _run_channel,
    #        channel_args
    # )
    nested = []
    for i, arg in tqdm(enumerate(channel_args), desc='zilany'):
        nested.append(_run_channel(arg))

    np.fft.fftpack._fft_cache = {}

    return __munge(nested, sound, output)

    # short-circuiting this entirely --gv
    ### Unpack the results
    # trains = itertools.chain(*nested)
    # spike_trains = pd.DataFrame(list(trains))

    # return spike_trains


def __munge(zil, sound, output):
    cfCount = len(zil)
    timeLen = len(zil[0]['anfout']['hsr'])
    anfhs = np.zeros((timeLen, cfCount))
    anfms = np.zeros_like(anfhs)
    anfls = np.zeros_like(anfhs)

    retval = PeripheryOutput()
    retval.conf = zil[0]['conf']
    for i in range(cfCount):
        anfhs[:, i] = zil[i]['anfout']['hsr']
        anfms[:, i] = zil[i]['anfout']['msr']
        anfls[:, i] = zil[i]['anfout']['lsr']
    retval.output = {
        p.CenterFrequency              : np.array(list(reversed([zil[i]['cf'] for i in range(cfCount)]))),
        p.AuditoryNerveFiberHighSpont  : anfhs,
        p.AuditoryNerveFiberMediumSpont: anfms,
        p.AuditoryNerveFiberLowSpont   : anfls,
        p.StimulusLevel                : zil[0]['level'],
        p.Stimulus                     : sound,
    }
    if output is not None:
        retval.outputFolder = output
    return retval


def _run_channel(args):
    fs = args['fs']
    cf = args['cf']
    signal = args['signal']
    cohc = args['cohc']
    cihc = args['cihc']
    powerlaw = args['powerlaw']
    seed = args['seed']
    conf = args['conf']
    level = args['level']
    anf_num = args['anf_num']
    species = args['species']
    ffGn = args['ffGn']

    ### Run BM, IHC
    # noinspection PyTypeChecker
    vihc = _zilany2014.run_ihc(
            signal=signal,
            cf=cf,
            fs=fs,
            species=species,
            cohc=float(cohc),
            cihc=float(cihc)
    )

    duration = len(vihc) / fs
    anf_types = np.repeat(['hsr', 'msr', 'lsr'], anf_num)

    synout = {}
    trains = []
    for anf_type in anf_types:

        if anf_type not in synout:
            # Run synapse
            synout[anf_type] = _zilany2014.run_synapse(
                    fs=fs,
                    vihc=vihc,
                    cf=cf,
                    anf_type=anf_type,
                    powerlaw=powerlaw,
                    ffGn=ffGn
            )

        # Run spike generator
        spikes = _zilany2014.run_spike_generator(
                synout=synout[anf_type],
                fs=fs,
        )
    return {
        'cf'    : args['cf'],
        'fs'    : args['fs'],
        'anfout': synout,
        'conf'  : conf,
        'level' : level,
    }
