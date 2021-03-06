# Corti: a Flexible Modeling Environment for Evaluating Subcortical Auditory Systems.
[![Build Status](https://travis-ci.org/gvoysey/corti.svg?branch=master)](https://travis-ci.org/gvoysey/corti)

This repository contains a runtime environment for models of the auditory periphery,
brainstem, and midbrain.  The model(s) are adapted from Verhulst et. al (2012,15),
Nelson and Carney (2004), Carney (2015), and Zilany and Bruce (2014).

It is implemented in Python >=3.3, and currently supports OSX, Linux, and 64-bit
Windows.

The goal of this work is to explore the effects of Auditory Neuropathy on
representations of complex sounds throughout the early stages of the auditory system.

One model of the auditory periphery is simulated using the model developed by
Verhulst et. al., hosted
[here](https://github.com/AuditoryBiophysicsLab/verhulst-model-core).  This model
**will not be available** without that module installed; contact @gvoysey for access.

## Citing this software
[![DOI](https://zenodo.org/badge/23057/gvoysey/corti.svg)](https://zenodo.org/badge/latestdoi/23057/gvoysey/corti)

This code may be cited as:

Graham Voysey et al.. (2016). *Corti*: version 0.9. Zenodo. 10.5281/zenodo.57111

# Installation
This repository may be installed with `pip`, the python package manager:

```
pip install git+https://github.com/gvoysey/thesis-code.git@<TAG>
```

where `<TAG>` is a valid [release](https://github.com/gvoysey/thesis-code/releases)

or `@master`, to get the latest build from the master branch.

If you have cloned this repository locally and are running it in a virtual
environment (like you should be!), you can also install it from the cloned repo for
development purposes.

## Contributions
If you plan on developing this model further, please fork this repo and send me (@gvoysey) a pull request when you want me to integrate the changes upstream.

The easy way to install this repo locally is with the command `env/bin/pip install
git+file:///path/to/your/git/repo@mybranch` or `@mytag`.

# Usage

- `stimulus_generator --help` configure stimuli from WAV files or generate stimuli configuration templates.
 - `corti --help` load stimuli, configure model parameters, run model, plot output.

# Documentation
 - Real Soon Now.
 - The scientific basis of this code is discussed at length in my [thesis](https://github.com/gvoysey/thesis).
