import math
from logging import error

import numpy as np
import yaml
from os import path
from scipy.io import wavfile

from verhulst_runner.base import stimulusTemplatePath, stim_consts as sc


class Stimulus:
    FS = 100e3  # todo this is a magic number...
    P0 = 2e-5  # 20 micropascals

    def __init__(self, prestimulus_time: float = None, stimulus_time: float = None, poststimulus_time: float = None):
        self.poststimulus_time = poststimulus_time
        self.stimulus_time = stimulus_time
        self.prestimulus_time = prestimulus_time

    def _to_pascals(self, waveform: np.ndarray, level: float) -> np.ndarray:
        """ Rescales a given waveform so that the values are in units of pascals.
        :parameter waveform:  The waveform.
        :parameter level:     The desired resulting intensity, in dB re 20 uPa.
        """
        normalized = waveform / max(waveform)
        scaling = 2 * math.sqrt(2) * self.P0 * 10 ** (level / 20)
        return normalized * scaling

    def make_click(self, config: {}) -> np.ndarray:
        template = [np.zeros(config[sc.PrestimTime]), np.ones(config[sc.StimTime]), np.zeros(config[sc.PoststimTime])]
        # return self._to_pascals(template, level)
        pass

    def make_chirp(self, config: {}) -> np.ndarray:
        pass

    def make_am(self, config: {}) -> np.ndarray:
        pass

    def default_stimulus(self):
        return yaml.load(open(stimulusTemplatePath, "r"))

    def generate_stimulus(self, stimulus_config: {}) -> np.ndarray:
        stim_type = stimulus_config[sc.StimulusType]

        stimului = {
            sc.Click: self.make_click(stimulus_config),
            sc.Chirp: self.make_chirp(stimulus_config),
            sc.AM: self.make_am(stimulus_config)
        }
        if stim_type in stimului:
            return stimului[stim_type]
        else:
            error("Cannot generate stimulus, wrong parameters given.")

    def load_stimulus(self, wav_path: str, level: float) -> np.ndarray:
        """ Loads and returns the specified wav file.
        """
        if not path.isfile(wav_path):
            raise FileNotFoundError
        fs, data = wavfile.read(wav_path)
        if fs != self.FS:
            raise NotImplementedError("Wav files must be sampled at {0}".format(self.FS))
        else:
            return {
                sc.Levels: [level],
                sc.StimulusType: "custom",
                sc.Stimulus: self._to_pascals(data, level)
            }