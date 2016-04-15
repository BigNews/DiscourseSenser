#!/usr//bin/env python
# -*- coding: utf-8; mode: python; -*-

"""Module providing class for LSTM sense disambiguation.

Attributes:
LSTMExplicitSenser (class):
  class that predicts senses of explicit relations

"""

##################################################################
# Imports
from __future__ import absolute_import, print_function

from dsenser.resources import W2V

from dsenser.lstm.base import LSTMBaseSenser
from dsenser.utils import timeit
from dsenser.theano_utils import floatX, rmsprop

##################################################################
# Variables and Constants


##################################################################
# Methods

##################################################################
# Class
class LSTMExplicitSenser(LSTMBaseSenser):
    """Class for LSTM disambiguation of explicit discourse relations.

    Attrs:
    n_y (int): number of distinct classes

    Methods:

    """

    @timeit("Training explicit LSTM classifier...")
    def train(self, *args, **kwargs):
        super(LSTMExplicitSenser, self).train(*args, **kwargs)
