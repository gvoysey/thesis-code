# -*- coding: utf-8 -*-
import ctypes
import platform

import numpy as np
import progressbar
from blessings import Terminal
from scipy import signal
from scipy.integrate import ode

from .core import *

term = Terminal()


class Writer(object):
    """Create an object with a write method that writes to a
 specific place on the screen, defined at instantiation.
 This is the glue between blessings and progressbar.
 """

    def __init__(self, location):
        """
     Input: location - tuple of ints (x, y), the position
                       of the bar in the terminal
     """
        self.location = location

    def write(self, string):
        with term.location(*self.location):
            print(string)


DOUBLE = ctypes.c_double
INT = ctypes.c_int
PINT = ctypes.POINTER(ctypes.c_int)
PLONG = ctypes.POINTER(ctypes.c_long)
PDOUBLE = ctypes.POINTER(ctypes.c_double)


class TridiagMatrix(ctypes.Structure):
    _fields_ = [("aa", ctypes.POINTER(ctypes.c_double)),
                ("bb", ctypes.POINTER(ctypes.c_double)),
                ("cc", ctypes.POINTER(ctypes.c_double))]


# load C library
system = platform.system().lower()
if system == "darwin":
    tridiagName = "tridiag.so_darwin"
elif system == "linux":
    tridiagName = "tridiag.so_linux"
elif system == "windows":
    tridiagName = "tridiag.so_windows"
else:
    raise NotImplementedError("this library only runs on mac and linux right now.")
    # tridiagName = "tridiag.so_windows" (one day!)

libtrisolv = np.ctypeslib.load_library(tridiagName, resources_root)

# load tridiagonal solver function and defines input
libtrisolv.solve_tridiagonal.restype = None
libtrisolv.solve_tridiagonal.argtypes = [ctypes.POINTER(TridiagMatrix),  # aa
                                         PDOUBLE,  # vv
                                         PDOUBLE,  # solution
                                         INT,  # nrows
                                         ]

libtrisolv.delay_line.restype = None  # TODO SPEEDUP W POINTERS!
libtrisolv.delay_line.argtypes = [PDOUBLE,  # in_matrix
                                  PINT,  # delay1
                                  PINT,  # delay2
                                  PINT,  # delay1
                                  PINT,  # delay1
                                  PDOUBLE,  # dev
                                  PDOUBLE,  # YZweig
                                  INT,  # delay_buffer_length
                                  INT  # n
                                  ]


# definition of the function


def TLsolver(t, y, model):  # y''=dv/dt y'=v
    n = model.n + 1
    frac = (t - model.lastT) / model.dt
    a = model.interplPoint1
    b = model.interplPoint2
    c = model.interplPoint3
    d = model.interplPoint4
    cminusb = c - b
    # fast cubic interpolation
    F0 = b + frac * \
             (cminusb - 0.1666667 * (1. - frac) *
              ((d - a - 3.0 * cminusb) * frac + (d + 2.0 * a - 3.0 * b)))
    model.Vtmp = y[0:n]
    model.Ytmp = y[n:2 * n]
    if model.use_Zweig:  # non-linearities here
        factor = 100
        Vvect = np.abs(model.Vtmp) / model.RthV1
        Sxp = (Vvect - 1.) * model.const_nl1
        Syp = model.Sb * np.sqrt(1 + (Sxp / model.Sa) ** 2)
        Sy = Sxp * model.sinTheta + Syp * model.cosTheta
        SheraP = model.PoleS + Sy / factor
        SheraP = np.fmin(SheraP, model.PoleE)
        # update non-linear parameters here only if the pole displacement is
        # larger than 1%
        if (np.max(abs(SheraP[1:n] - model.SheraP[1:n]) /
                       abs(model.SheraP[1:n])) > 0.01):
            model.SheraP = SheraP
            model.SheraParameters()
            model.ZweigImpedance()
            model.current_t = t
    model.Dev[0:n] = model.Dev[0:n] + frac
    libtrisolv.delay_line(
        model.Ybuffer_pointer, model.Zrp_pointer, model.Zrp1_pointer,
        model.Zrp2_pointer, model.Zrp3_pointer, model.Dev_pointer,
        model.YZweig_pointer, ctypes.c_int(model.YbufferLgt),
        ctypes.c_int(model.n + 1))
    model.Dev[0:n] = model.Dev[0:n] - frac
    model.calculate_g()
    model.calculate_right(F0)
    # compute q
    libtrisolv.solve_tridiagonal(
        ctypes.byref(model.tridata), model.r_pointer, model.Qpointer,
        ctypes.c_int(n))
    # ME equation
    zero_val = (model.RK4_0 * model.Qsol[
        0] + model.RK4G_0 * (model.g[0] + model.p0x * F0))
    Vderivative = (model.Qsol - model.g)
    Vderivative[0] = zero_val
    # output the velocity input as displacement derivative output.
    solution = np.concatenate([Vderivative, model.Vtmp])
    return solution


class CochleaModel:
    # init constants
    def __init__(self):
        self.ttridiag = 0
        self.calling_function = 0
        self.cochleaLength = .035
        self.bmMass = 0.5
        self.bmImpedanceFactor = 1
        self.scalaWidth = 0.001
        self.scalaHeight = 0.001
        self.helicotremaWidth = 0.001
        self.rho = float(1e3)
        self.Normal_Q = 20
        self.Greenwood_A = 20682
        self.Greenwood_alpha = 61.765
        self.Greenwood_B = 140.6
        self.stapesArea = float(3e-6)
        self.EardrumArea = float(60e-6)
        self.MiddleEarResonanceFrequency = float(2e3)
        self.MiddleEarQualityFactor = 0.4
        self.SpecificAcousticImpedanceOfAir = 415
        self.middleEarTransformer = 30
        self.damping_coupler = float(140e5)
        self.mass_coupler = float(43.2e2)
        self.stiffness_coupler = 1. / float(2.28e-11)
        self.p0 = float(2e-5)
        self.ZweigQ = 1 / 0.0606
        self.ZweigFactor = 1.7435
        self.ZweigQAtBoundaries = 20
        self.ZweigBeta = 10000
        self.ZweigGamma = 6200
        self.ZweigN = 1.5
        self.SheraMuMax = 4.3
        self.RMSref = 0.6124
        self.Rme = float(0.3045192500000000e12)  # TODO setRme function
        # variable to check if the model is initialized before calling the solver
        self._is_init = 0
        self.interplPoint1 = 0
        self.interplPoint2 = 0
        self.interplPoint3 = 0
        self.interplPoint4 = 0

    # function to initialize all the parameters
    def init_model(self, stim, samplerate, sections, probe_freq, sheraPo,
                   compression_slope=0.4, Zweig_irregularities=1,
                   non_linearity_type="vel", KneeVar=1.,
                   low_freq_irregularities=1, subject=1, IrrPct=0.05):
        self.low_freq_irregularities = low_freq_irregularities
        self.SheraPo = np.zeros(sections + 1)
        self.SheraPo = self.SheraPo + sheraPo  # can be vector or single value, line changed so it can work with both single and vector
        self.KneeVar = (KneeVar)
        self.IrrPct = IrrPct
        self.non_linearity = 0
        self.use_Zweig = 1
        if Zweig_irregularities == 0:
            self.use_Zweig = 0
        if non_linearity_type == "disp":  # todo as enum
            self.non_linearity = 1
        elif non_linearity_type == "vel":
            self.non_linearity = 2
        else:
            self.non_linearity = 0  # linear model
        self.n = sections
        self.fs = samplerate
        self.dt = 1. / self.fs
        self.probe_freq = probe_freq
        self.init_cochlea()
        self.initMiddleEar()
        self.SetDampingAndStiffness()
        self.initZweig()
        self.initGaussianElimination()
        self.compression_slope_param(compression_slope)
        self.is_init = 1
        self.lastT = 0
        self.seed = subject  # change here the seed
        np.random.RandomState(self.seed)
        np.random.seed(self.seed)
        self.Rth = 2 * (np.random.random(self.n + 1) - 0.5)
        self.Rth_norm = 10 ** (self.Rth / 20. / self.KneeVar)
        lf_limit = self.ctr
        if self.use_Zweig:
            factor = 100
            n = self.n + 1
            Rth = self.Rth
            Rth_norm = self.Rth_norm
            # Normalized RTH, so save a bit of computation
            self.RthY1 = self.Yknee1 * Rth_norm
            self.RthY2 = self.Yknee2 * Rth_norm
            self.RthV1 = self.Vknee1 * Rth_norm
            self.RthV2 = self.Vknee2 * Rth_norm

            Rndm = self.IrrPct * Rth / 2.
            self.PoleS = (1 + Rndm) * self.SheraPo

            self.RthY1[lf_limit:n] = self.Yknee1
            self.RthY2[lf_limit:n] = self.Yknee2
            self.RthV1[lf_limit:n] = self.Vknee1
            self.RthV2[lf_limit:n] = self.Vknee2
            self.PoleS[lf_limit:n] = self.SheraPo[lf_limit:n]
            Theta0 = np.arctan(
                ((self.PoleE - self.PoleS) * factor) /
                ((self.RthV2 / self.RthV1) - 1.))
            Theta = Theta0 / 2.
            Sfoc = (self.PoleS * factor) / (self.RthV2 / self.RthV1)
            Se = np.cos((np.pi - Theta0) * 0.5)
            self.Sb = Sfoc * Se
            self.Sa = Sfoc * np.sqrt(1. - ((Se ** 2)))
            self.const_nl1 = np.cos(Theta) / np.cos(2 * Theta)
            self.cosTheta = np.cos(Theta)
            self.sinTheta = np.sin(Theta)

        #
        # PURIAM1 FILTER             ###
        #
        puria_gain = 10 ** (18. / 20.) * 2.
        #         was the orignal Puria in 2012
        #        second order butterworth
        #        b, a = signal.butter(
        #           1, [100. / (samplerate / 2.), 3000. / (samplerate / 2)],
        #            'bandpass')
        #         self.stim = signal.lfilter(b * puria_gain, a, stim)

        #        #below is the modified version.
        b, a = signal.butter(1, [600. / (samplerate / 2.), 3000. / (samplerate / 2)], 'bandpass')
        self.stim = signal.lfilter(b * puria_gain, a, stim)

    # from initalizeCochlea.f90
    def init_cochlea(self):
        self.bm_length = self.cochleaLength - self.helicotremaWidth
        self.bm_width = self.scalaWidth
        self.bm_mass = self.bmMass * self.bmImpedanceFactor
        self.ZweigMso = 2. * self.rho / (self.bm_width * self.scalaHeight)
        self.ZweigL = 1. / (2.3030 * self.Greenwood_alpha)
        self.ZweigOmega_co = 2.0 * np.pi * self.Greenwood_A
        self.ZweigMpo = (self.ZweigMso * (self.ZweigL ** 2)) / ((4 * self.ZweigN) ** 2)
        self.Ko = self.ZweigMpo * (self.ZweigOmega_co ** 2)
        self.x = np.array(np.linspace(0, self.bm_length, self.n + 1), order='C')
        self.dx = self.bm_length / (1. * self.n)

        #
        # intialize other variables here for practical purposes
        #

        self.g = np.zeros_like(self.x)
        self.Vtmp = np.zeros_like(self.x)
        self.Ytmp = np.zeros_like(self.x)
        self.Atmp = np.zeros_like(self.x)
        self.right = np.zeros_like(self.x)
        self.r_pointer = self.right.ctypes.data_as(PDOUBLE)
        self.zerosdummy = np.zeros_like(self.x)
        self.gamma = np.zeros_like(self.x)
        self.Qsol = np.zeros_like(self.x)
        self.Qpointer = self.Qsol.ctypes.data_as(PDOUBLE)

    def initMiddleEar(self):
        self.q0_factor = self.ZweigMpo * self.bm_width
        self.p0x = self.ZweigMso * self.dx / (1. * self.ZweigMpo * self.bm_width)
        self.d_m_factor = -self.p0x * self.stapesArea * self.Rme
        self.RK4_0 = -(self.bm_width * self.ZweigMpo) / (self.stapesArea)
        self.RK4G_0 = (self.ZweigMpo * self.bm_width) / (self.ZweigMso * self.stapesArea * self.dx)

    def SetDampingAndStiffness(self):
        self.f_resonance = self.Greenwood_A * (10 ** (-self.Greenwood_alpha * self.x)) - self.Greenwood_B
        self.ctr = np.argmin(np.abs(self.f_resonance - 100.))
        if (self.low_freq_irregularities):
            self.ctr = self.n + 1
        self.onek = np.argmin(np.abs(self.f_resonance - 1000.))
        self.omega = 2. * np.pi * self.f_resonance
        self.omega2 = self.omega ** 2
        self.Sherad_factor = np.array(self.omega)
        self.SheraP = np.zeros_like(self.x)
        self.SheraD = np.zeros_like(self.x)
        self.SheraRho = np.zeros_like(self.x)
        self.SheraMu = np.zeros_like(self.x)
        self.SheraP = self.SheraPo + self.SheraP
        self.c = 120.8998691636393  # todo what IS this?

        #
        # PROBE POINTS               ##
        #
        if self.probe_freq == 'all':
            # todo this should be np.linspace() !
            self.probe_points = np.zeros(len(self.f_resonance) - 1)
            for i in range(len(self.f_resonance) - 1):
                self.probe_points[i] = i + 1
            self.probe_points = (self.probe_points)
            self.cf = (self.f_resonance[1:len(self.f_resonance)])
        elif self.probe_freq == 'half':
            self.probe_points = np.zeros((len(self.f_resonance) - 1) / 2)
            for i in range((len(self.f_resonance) - 1) / 2):
                self.probe_points[i] = i + 1
            self.probe_points = (self.probe_points)
            self.cf = (self.f_resonance[range(1, len(self.f_resonance), 2)])
        else:
            self.probe_points = np.zeros(self.probe_freq.size, dtype=int)
            for i in range(len(self.probe_freq)):
                idx_help = abs((self.f_resonance) - np.float(self.probe_freq[i]))
                self.probe_points[i] = np.argmin(idx_help)
            self.cf = self.f_resonance[self.probe_points]
        self.probe_points = np.array(self.probe_points)

    def initZweig(self):
        n = self.n + 1
        self.exact_delay = self.SheraMuMax / (self.f_resonance * self.dt)
        self.delay = np.floor(self.exact_delay) + 1
        self.YbufferLgt = int(np.amax(self.delay))
        self.Ybuffer = np.zeros([n, self.YbufferLgt])
        # Ybuffer implemented here as a dense matrix
        # (python for cycles are slow...)
        self.Ybuffer = np.array(self.Ybuffer, order='C', ndmin=2, dtype=float)
        self.Ybuffer_pointer = self.Ybuffer.ctypes.data_as(PDOUBLE)
        self.ZweigSample1 = np.zeros_like(self.exact_delay)
        self.Zwp = int(0)
        self.ZweigSample1[0] = 1.
        self.ZweigSample2 = self.ZweigSample1 + 1
        # init buffers etc...
        self.Dev = np.zeros_like(self.x)
        self.Dev_pointer = self.Dev.ctypes.data_as(PDOUBLE)
        self.YZweig = np.zeros_like(self.x)
        self.YZweig_pointer = self.YZweig.ctypes.data_as(PDOUBLE)
        self.Zrp = np.array(np.zeros(n), dtype=np.int32, order='C')
        self.Zrp_pointer = self.Zrp.ctypes.data_as(PINT)
        self.Zrp1 = np.array(np.zeros(n), dtype=np.int32, order='C')
        self.Zrp1_pointer = self.Zrp1.ctypes.data_as(PINT)
        self.Zrp2 = np.array(np.zeros(n), dtype=np.int32, order='C')
        self.Zrp2_pointer = self.Zrp2.ctypes.data_as(PINT)
        self.Zrp3 = np.array(np.zeros(n), dtype=np.int32, order='C')
        self.Zrp3_pointer = self.Zrp3.ctypes.data_as(PINT)

    # set tridiagonal matrix values for transmission line
    def initGaussianElimination(self):
        n = self.n + 1
        self.ZweigMs = (self.ZweigMso * self.ZweigOmega_co) / self.omega
        self.ZweigMp = self.Ko / (self.ZweigOmega_co * self.omega)
        self.ZASQ = np.zeros_like(self.x)
        self.ZASC = np.zeros_like(self.x)
        self.ZAL = np.zeros_like(self.x)
        self.ZAH = np.zeros_like(self.x)
        # init values of transmission line
        self.ZASQ[0] = 1.
        self.ZASC[0] = 1 + self.ZweigMso * self.dx
        self.ZAH[0] = -1.
        self.ZAL[1:n] = -self.ZweigMs[1:n]
        self.ZAH[1:n - 1] = -self.ZweigMs[0:n - 2]
        self.ZASQ[1:n] = self.omega[1:n] * self.ZweigMs[1:n] * self.ZweigMs[
                                                               0:n - 1] * (self.dx ** 2) / (
                             self.ZweigOmega_co * self.ZweigMpo)
        self.ZASC[1:n] = self.ZASQ[1:n] + \
                         self.ZweigMs[1:n] + self.ZweigMs[0:n - 1]
        self.tridata = TridiagMatrix()
        self.tridata.aa = self.ZAL.ctypes.data_as(PDOUBLE)
        self.tridata.bb = self.ZASC.ctypes.data_as(PDOUBLE)
        self.tridata.cc = self.ZAH.ctypes.data_as(PDOUBLE)

    def calculate_g(self):  # same as in fortran
        n = self.n + 1
        self.g[0] = self.d_m_factor * self.Vtmp[0]
        dtot = self.Sherad_factor * self.SheraD
        stot = (self.omega2) * (self.Ytmp + (self.SheraRho * self.YZweig))
        self.g[1:n] = (dtot[1:n] * self.Vtmp[1:n]) + stot[1:n]

    def calculate_right(self, F0):  # same as in fortran
        n = self.n + 1
        self.right[0] = self.g[0] + self.p0x * F0
        self.right[1:n] = self.ZASQ[1:n] * self.g[1:n]

    def SheraParameters(self):  # same as in fortran
        a = (self.SheraP + np.sqrt((self.SheraP ** 2.) +
                                   self.c * (1.0 - self.SheraP ** 2))) / self.c
        self.SheraD = 2.0 * (self.SheraP - a)
        self.SheraMu = 1. / (a)
        # print self.SheraMu
        self.SheraRho = 2. * a * \
                        np.sqrt(1. - (self.SheraD / 2.) ** 2.) * np.exp(-self.SheraP / a)

    def ZweigImpedance(self):
        n = self.n + 1
        MudelayExact = self.SheraMu / (self.omega * self.dt)
        Mudelay = np.floor(MudelayExact) + 1.
        self.Dev[:] = Mudelay - MudelayExact
        self.Zrp1[0:n] = (
                             (self.Zwp + self.YbufferLgt) - Mudelay[0:n]) % self.YbufferLgt
        const = self.YbufferLgt - 1
        self.Zrp[0:n] = (self.Zrp1[0:n] + const) % self.YbufferLgt
        self.Zrp2[0:n] = (self.Zrp1[0:n] + 1) % self.YbufferLgt
        self.Zrp3[0:n] = (self.Zrp2[0:n] + 1) % self.YbufferLgt

    def compression_slope_param(self, slope):
        self.Yknee1 = float(6.9183e-10)
        self.Vknee1 = float(4.3652e-6)
        self.PoleE = np.zeros_like(self.x)
        if (slope == 0.3):
            self.Yknee2 = float(7.015e-9)
            self.Vknee2 = float(4.426e-5)
            Ax = (0.7 - 0.06) / (87.77 - 30)
            Bx = self.SheraPo - Ax * 30
            self.PoleE = self.PoleE + Ax * 87.77 + Bx
        elif (slope == 0.2):
            self.Yknee2 = float(3.228e-9)
            self.Vknee2 = float(2.037e-5)
            Ax = (0.7 - 0.06) / (80.59 - 30)
            Bx = self.SheraPo - Ax * 30
            self.PoleE = self.PoleE + Ax * 80.59 + Bx
        elif (slope == 0.5):
            self.Yknee2 = float(1.766e-8)
            self.Vknee2 = float(1.114e-4)
            Ax = (0.7 - 0.06) / (97.82 - 30)
            Bx = self.SheraPo - Ax * 30
            self.PoleE = self.PoleE + Ax * 97.82 + Bx
        else:
            self.Yknee2 = float(1.5488e-8)
            self.Vknee2 = float(9.7836e-5)
            Ax = (0.7 - 0.06) / (97.4 - 30.)
            Bx = self.SheraPo - Ax * 30.
            self.PoleE = self.PoleE + Ax * 97.4 + Bx

    def polecalculation(self):  # TODO
        # non-linearities  can be Wrapped from C for an additional boost, but
        # must be done carefully (efficient memory allocation)
        factor = 100.
        # lf_limit = self.ctr
        # n = self.n + 1
        if (self.use_Zweig):
            if self.non_linearity == 1:  # To check
                # non-linearity DISP cost about three times more than in
                # fortran (Not implemented now)
                Yknee1CST = self.RthY1 * self.omega[self.onek]
                Yknee2CST = self.RthY2 * self.omega[self.onek]
                Yknee1F = Yknee1CST / self.omega
                Yknee2F = Yknee2CST / self.omega
                Yvect = np.abs(self.Ytmp / Yknee1F)
                Theta0 = np.arctan(
                    ((self.PoleE - self.PoleS) / ((Yknee2F / Yknee1F) - 1.)))
                Theta = Theta0 / 2.
                # save 2 call to trigonometric function on vector by storing
                # some data
                cos_Theta = np.cos(Theta)
                sin_Theta = np.sin(Theta)
                cos_Theta0 = 2 * cos_Theta ** 2 - 1
                Sfoc = self.PoleS * factor * (Yknee2F / Yknee1F)
                Se = sin_Theta
                Sb = Sfoc * Se
                Sa = Sfoc * np.sqrt(1. - (1. * (Se ** 2)))
                Sxp = (Yvect - 1.) * cos_Theta / cos_Theta0
                Syp = Sb * np.sqrt(1 + (Sxp / Sa) ** 2)
                Sy = Sxp * sin_Theta + Syp * cos_Theta
                self.SheraP = self.PoleS + Sy / factor

            elif self.non_linearity == 2:  # non-linearity VEL
                Vvect = np.abs(self.Vtmp) / self.RthV1
                Sxp = (Vvect - 1.) * self.const_nl1
                Syp = self.Sb * np.sqrt(1 + (Sxp / self.Sa) ** 2)
                Sy = Sxp * self.sinTheta + Syp * self.cosTheta
                self.SheraP = self.PoleS + Sy / factor

        self.SheraP = np.fmin(self.SheraP, self.PoleE)

    def solve(self, location=None):
        n = self.n + 1
        if not self.is_init:
            print("Error: model to be initialized")
        length = np.size(self.stim) - 2
        time_length = length * self.dt
        # each probe point signal in a row
        self.Vsolution = np.zeros([length + 2, len(self.probe_points)])
        self.Ysolution = np.zeros([length + 2, len(self.probe_points)])
        self.oto_emission = np.zeros(length + 2)
        self.time_axis = np.linspace(0, time_length, length)
        r = ode(TLsolver).set_integrator('dopri5', rtol=1e-2, atol=1e-13)
        r.set_f_params(self)
        r.set_initial_value(np.concatenate([np.zeros_like(self.x), np.zeros_like(self.x)]))
        r.t = 0

        self.last_t = 0.0
        self.current_t = r.t
        self.polecalculation()
        self.SheraParameters()
        self.ZweigImpedance()
        # w = Writer(location) #, fd=w
        # with progressbar.ProgressBar(max_value=length, fd=w) as bar:  # when run from a command line
        with progressbar.ProgressBar(max_value=length) as bar:
            for j in range(length):
                if j > 0:
                    self.interplPoint1 = self.stim[j - 1]
                # assign the stimulus points and interpolation parameters
                self.interplPoint2 = self.stim[j]
                self.interplPoint3 = self.stim[j + 1]
                self.interplPoint4 = self.stim[j + 2]
                r.integrate(r.t + self.dt)

                self.lastT = r.t
                self.Vtmp = r.y[0:n]
                self.Ytmp = r.y[n:2 * n]  # Non linearities HERE
                self.Zwp = (self.Zwp + 1) % self.YbufferLgt  # update Zweig Buffer
                self.Ybuffer[:, self.Zwp] = self.Ytmp
                self.ZweigImpedance()
                self.current_t = r.t
                if (self.probe_freq == 'all'):
                    self.Vsolution[j, :] = self.Vtmp[1:n]  #
                    self.Ysolution[j, :] = self.Ytmp[1:n]
                elif (self.probe_freq == 'half'):
                    self.Vsolution[j, :] = self.Vtmp[range(1, n, 2)]
                    self.Ysolution[j, :] = self.Ytmp[range(1, n, 2)]
                else:
                    #                print(self.probe_points)
                    self.Vsolution[j, :] = self.Vtmp[self.probe_points]  # storing the decided probe points
                    self.Ysolution[j, :] = self.Ytmp[self.probe_points]

                self.oto_emission[j] = self.Qsol[0]
                bar.update(j)
        # filter out the otoacoustic emission
        b, a = signal.butter(1, [600. / (self.fs / 2), 3000. / (self.fs / 2)], 'bandpass')
        self.oto_emission = signal.lfilter(b * self.q0_factor, a, self.oto_emission)
