#!/usr/bin/env python
"""
Corti: A tool for subcortical models of the auditory system.

Usage:
    corti -h | --help
    corti --version
    corti [--out <outpath>]
                   [--peripheryType <model>]
                   [-c | --clean]
                   [-v | --verbose]
                   [--pSave <peripheryFlag>]
                   [--stimulusFile <stimulusPath> | (--wavFile <wavPath> --level <spl>)]
                   [--no-cf-weighting]
                   [--neuropathy <degradation>]
                   [--noBrainstem | --brainstemType <brainstem>]
                   [--pypet]

Options:
    -h --help                       Show this screen and exit.
    --version                       Display the version and exit.
    --peripheryType=<model>         Use either the 'VERHULST' or 'ZILANY' peripheral model. [default: VERHULST]
    --out=<outpath>                 Specify the output location for saved data. [default: ~/corti-output]
    --pSave=<peripheryFlag>         Which components of the peripheral response to save:
                                    'c' : Center Frequencies
                                    'a' : Basilar Membrane Acceleration (not supported)
                                    'v' : Basilar Membrane Velocity (Verhulst model only)
                                    'i' : Inner Hair Cell Potentials (Verhulst model only)
                                    'h' : High Spontaneous Rate Fiber IFRs
                                    'l' : Low Spontaneous Rate Fiber IFRs
                                    'm' : Medium Spontaneous Rate Fiber IFRs
                                    'e' : Otoacoustic Emissions (Verhulst model only)
                                    's' : The stimulus waveform
                                    'd' : The stimulus level
                                    [default: cavihlmesd]
    --noBrainstem                   Simulate the periphery only.
    --brainstemType=<brainstem>     Which brainstem and midbrain model to use: 'NELSON_CARNEY_2004' or 'CARNEY_2015'
                                    [default: NELSON_CARNEY_2004]
    --no-cf-weighting               Don't sigmoidally weight how many low, medium, and high SR fibers innervate each CF.
    --stimulusFile=<stimulusPath>   Provide one or more stimuli templates as YAML (see stimulus_generator --help ).
                                    If no option is provided, an 80dB click will be used.
    --wavFile=<wavPath>             Provide a custom stimulus from a pre-recorded WAV file.
    --level=<spl>                   Specify the peak sound level(s) of the WAV specified with --wavFile.
                                    Separate values with commas.
    -c --clean                      Previous runs will be deleted to save disk space.
    --neuropathy=<degradation>      Specify the damage to the auditory periphery to be applied.
                                    Use 'mild', 'moderate', or 'severe' to apply uniform 10, 25, or 50% damage to all
                                    fiber types, or specify 'ls-mild', 'ls-moderate', or 'ls-severe' to selectively
                                    degrade low-SR fibers only. [default: none]
    --pypet                         Set this option when calling this script from pypet.  Data saving will be managed by
                                    PyPet, and no summary figures will be generated.
    -v --verbose                    Display detailed debug log output to STDOUT.
"""

import sys
from datetime import datetime
from logging import info, getLogger, ERROR

import os
import shutil
from docopt import docopt
from os import path, system, name

from corti import Periphery, Stimulus, __version__
from corti.analysis.plots import save_summary_pdf
from corti.auditory_nerve_response import AuditoryNerveResponse
from corti.base import runtime_consts, PeripheryType, an_consts as a
from corti.brainstem import simulate_brainstem
from corti.periphery_configuration import PeripheryConfiguration


def main(inputargs):
    args = docopt(__doc__, version=__version__, argv=inputargs)
    pypet = args["--pypet"]
    # configure the log level appropriately
    if not args["--verbose"]:
        getLogger().setLevel(ERROR)

    # configure the stimulus
    stimuli_dict = _make_stimuli(args)
    # actually run the simulation
    system('cls' if name == 'nt' else 'clear')
    # configure the periphery to run
    conf = PeripheryConfiguration(dataFolder=__set_output_dir(args["--out"], pypet),
                                  storeFlag=args["--pSave"],
                                  stimuli=stimuli_dict,
                                  modelType=PeripheryType[args["--peripheryType"].upper()],
                                  degradation=args["--neuropathy"],
                                  pypet=pypet)
    info("Simulating periphery ({0}) response ...".format(args["--peripheryType"]))

    # run all the levels through the periphery model
    peripheryResults = Periphery(conf).run()

    # Create the auditory nerve response
    info("Simulating auditory nerve response ...")

    if args["--no-cf-weighting"]:
        auditoryNerveResponses = [AuditoryNerveResponse(p, args["--neuropathy"]).unweighted_an_response() for p in
                                  peripheryResults]
    else:
        auditoryNerveResponses = [AuditoryNerveResponse(p, args["--neuropathy"]).cf_weighted_an_response() for p in
                                  peripheryResults]

    # run the brainstem and midbrain models, if requested
    if not args["--noBrainstem"]:
        info("Simulating brainstem response ...")
        brainResults = simulate_brainstem([(periphs, anrs, args["--brainstemType"])
                                           for periphs, anrs in zip(peripheryResults, auditoryNerveResponses)])
    else:
        brainResults = None

    # Generate summary plots
    if not pypet:
        info("Generating summary figures ...")
        save_summary_pdf(periphery=peripheryResults,
                         brain=brainResults,
                         anr=auditoryNerveResponses,
                         conf=conf,
                         fileName="summary-plots.pdf",
                         outputPath=peripheryResults[0].outputFolder)

    # Delete old runs, if requested.
    if args["--clean"]:
        info("Cleaning up previous model runs ... ")
        __clean(conf.dataFolder, peripheryResults[0].outputFolder)

    info("Simulation finished.")
    if pypet:
        return (
            peripheryResults,
            [{a.SumANR: x} for x in auditoryNerveResponses],
            brainResults
        )
    else:
        return 0


def _sanitize_level(levels: str):
    """ Takes a string list of level parameters and converts them to a list of floats.
    """
    if levels is None:
        return
    return [float(f) for f in levels.split(",") if levels and f]


def __clean(rootDir: str, current_results: str) -> None:
    """
    Removes all the previous model runs except the current one found in the current base output directory.
    All directories that are named like model output directories are removed recursively; no other files are touched.
    """
    contents = os.listdir(rootDir)
    if runtime_consts.ModelDirectoryLabelName not in contents:
        info("Specified directory was not a model output directory. No data removed.")
        return
    for d in contents:
        if (not d == path.basename(current_results)) and \
                path.isdir(path.join(rootDir, d)) and \
                datetime.strptime(d, runtime_consts.ResultDirectoryNameFormat):
            shutil.rmtree(path.join(rootDir, d))
            info("removed " + d)
    pass


def __touch(fname, times=None):
    """ As coreutils touch.
    """
    with open(fname, 'a+'):
        os.utime(fname, times)


def __set_output_dir(temp: str, pypet: bool) -> str:
    """ Returns a fully qualified path to the model output root directory.
    The directory is created if it does not exist.
    """
    if pypet:
        return
    # just in case we're on windows.
    temp.replace("\\", "\\\\")

    retval = path.realpath(path.join(*path.split(path.expanduser(temp))))
    if path.isfile(retval):
        retval = path.dirname(retval)
    # if the output path exists and is empty, make it the output root and return it.
    if path.exists(retval) and not os.listdir(retval):
        __touch(path.join(retval, runtime_consts.ModelDirectoryLabelName))
        return retval
    # if it exists and has stuff in it, make a subdirectory in it, make IT the root, and return it.
    elif path.exists(retval) and os.listdir(retval):
        if path.basename(retval) != runtime_consts.DefaultModelOutputDirectoryRoot:
            retval = path.join(retval, runtime_consts.DefaultModelOutputDirectoryRoot)
        if not path.exists(retval):
            os.makedirs(retval, exist_ok=True)
        __touch(path.join(retval, runtime_consts.ModelDirectoryLabelName))
        return retval
    # if it doesn't exist, make it, make it the root, and return it.
    elif not path.exists(retval):
        os.makedirs(retval)
        __touch(path.join(retval, runtime_consts.ModelDirectoryLabelName))
        return retval


def _make_stimuli(args: dict) -> dict:
    stim_loc = args["--stimulusFile"]
    wav_path = args["--wavFile"]
    levels = _sanitize_level(args["--level"])
    s = Stimulus()
    if stim_loc:
        # use a user-configured stimulus file.
        stimuli_dict = s.custom_stimulus_template(stim_loc)
    elif not wav_path:
        # use the default stimulus.
        stimuli_dict = s.default_stimulus_template()
    else:
        # use a user-created wav stimulus.
        stimuli_dict = s.load_stimulus(wav_path, levels)
    stimuli_dict = s.generate_stimulus(stimuli_dict)
    return stimuli_dict


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] if len(sys.argv) > 1 else ""))  # guaranteed to pass the right number of arguments.
