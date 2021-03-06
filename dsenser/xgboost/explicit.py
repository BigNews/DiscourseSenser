#!/usr/bin/env python
# -*- coding: utf-8; mode: python; -*-

"""Module for XGBoost disambiguation of explicit relations.

Attributes:
  XGBoostExplicitSenser (class):
    class that xgboost sense prediction of explicit relations

"""

##################################################################
# Imports
from __future__ import absolute_import, print_function

from dsenser.utils import timeit
from dsenser.wang.explicit import WangExplicitSenser
from dsenser.xgboost.xgboostbase import XGBoostBaseSenser


##################################################################
# Classes
class XGBoostExplicitSenser(XGBoostBaseSenser, WangExplicitSenser):
    """Subclass of explicit WangSenser using XGBoost.

    """

    @timeit("Training explicit XGBoost classifier...")
    def train(self, *args, **kwargs):
        super(WangExplicitSenser, self).train(*args, **kwargs)
