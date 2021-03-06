import math
from logging import error

import numpy as np
import yaml
from os import path
from scipy.io import wavfile

from corti.base import stimulusTemplatePath, stim_consts as sc


class Stimulus:
    P0 = 2e-5  # 20 micropascals

    def __init__(self, Fs=100e3):
        self.FS = Fs

    def seconds_to_samples(self, time: str) -> int:
        time = float(time)
        return int(round(self.FS * time))

    def to_pascals(self, waveform: np.ndarray, levels: [], stim_type: str) -> np.ndarray:
        """ Rescale a waveform so that the values are in units of pascals, and returns a matrix of waveforms column-wise
        by level.
        :parameter waveform:  The waveform.
        :parameter levels:     The desired resulting intensities, in dB re 20 uPa.
        """
        # make the waveform one-dimensional if it isn't already
        waveform = np.hstack(waveform)
        # normalize the stimulus waveform to its rms value
        if stim_type == sc.Click:
            normalized = waveform / abs(max(waveform))
        else:
            normalized = waveform / self.rms(waveform)
        # make the levels broadcastable
        levels = np.array(levels)[:, None]
        # compute the intensity in pascals
        scaling = self.spl_to_a(levels)
        return normalized * scaling

    def rms(self, sig_in: np.ndarray) -> np.ndarray:
        """ Compute the Root-Mean Squared (RMS) value of the long term input stimulus signal"""
        return math.sqrt(np.mean(sig_in * np.conj(sig_in)))

    def spl_to_a(self, spl_value: float) -> float:
        """Convert from dB SPL to RMS pascal"""
        return self.P0 * 10 ** (spl_value / 20)

    def make_click(self, config: dict) -> np.ndarray:
        """ Generate a click stimulus of a given prestimulus delay, stimulus duration, poststimulus delay, and levels.
        """
        pre = self.seconds_to_samples(config[sc.PrestimTime])
        stim = self.seconds_to_samples(config[sc.StimTime])
        post = self.seconds_to_samples(config[sc.PoststimTime])
        # the template for a click is a delay, a rectangular stimulus, and a delay.
        template = [np.zeros(pre), np.ones(stim), np.zeros(post)]
        return self.to_pascals(template, config[sc.Levels], config[sc.StimulusType])

    def make_chirp(self, config: {}) -> np.ndarray:
        pass

    def make_am(self, config: {}) -> np.ndarray:
        pass

    def custom_stimulus_template(self, templatePath: str) -> dict:
        """ Loads a user-created stimulus configuration from disk
        """
        return yaml.load(open(templatePath, "r"))

    def default_stimulus_template(self) -> dict:
        """ Returns the default stimulus configuration from the template
        """
        return yaml.load(open(stimulusTemplatePath, "r"))

    def generate_stimulus(self, stimulus_config: {}) -> {}:
        """ Generate a stimulus from a stimulus configuration and return it appended to the stimulus configuration.
        """
        if sc.Stimulus in stimulus_config:
            return stimulus_config
        stim_type = stimulus_config[sc.StimulusType]

        stimuli = {
            sc.Click: self.make_click(stimulus_config),
            sc.Chirp: self.make_chirp(stimulus_config),
            sc.AM: self.make_am(stimulus_config),
        }
        if stim_type in stimuli:
            stimulus_config[sc.Stimulus] = stimuli[stim_type]
            return stimulus_config
        else:
            try:
                return self.load_stimulus(stim_type, stimulus_config[sc.Levels])
            except:
                error("Cannot generate stimulus, wrong parameters given.")

    def load_stimulus(self, wav_path: str, level: [float]) -> {}:
        """ Loads and returns the specified wav file.
        """
        if not path.isfile(wav_path):
            raise FileNotFoundError("Could not locate file {0}".format(wav_path))
        fs, data = wavfile.read(wav_path)
        if fs != self.FS:
            raise NotImplementedError("Wav files must be sampled at {0}".format(self.FS))
        else:
            return {
                sc.Levels      : level,
                sc.StimulusType: "custom",
                sc.Stimulus    : self.to_pascals(data, level, sc.Custom)
            }
