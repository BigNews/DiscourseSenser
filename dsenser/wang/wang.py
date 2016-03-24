#!/usr//bin/env python
# -*- coding: utf-8; mode: python; -*-

"""Module providing class for Wang sense disambiguation.

Attributes:
WangSenser (class):
  class that always chooses majority category  for sense disambiguation

"""

##################################################################
# Imports
from __future__ import absolute_import, print_function

from dsenser.base import BaseSenser
from dsenser.constants import CONNECTIVE, RAW_TEXT, TOK_LIST
from dsenser.wang.explicit import WangExplicitSenser
from dsenser.wang.implicit import WangImplicitSenser

import numpy as np

##################################################################
# Variables and Constants


##################################################################
# Classes
class WangSenser(BaseSenser):
    """Class using Wang classification for disambiguating connectives.

    Attrs:
    explicit (ImplicitSenser): classifier for implicit discourse relations
    implicit (ExplicitSenser): classifier
    n_y (int): number of distinct classes

    Methods:

    """

    def __init__(self):
        """Class constructor.

        Args:

        """
        self.explicit = WangExplicitSenser()
        self.implicit = WangImplicitSenser()
        self.n_y = -1

    def train(self, a_train_data, a_dev_data=None, a_n_y=-1):
        """Method for training the model.

        Args:
        a_train_data (2-tuple(list, dict)):
          list of gold relations and dict with parses
        a_dev_data (2-tuple(list, dict) or None):
          list of development relations and dict with parses
        a_n_y (int):
          number of distinct classes

        Returns:
        (void)

        """
        self.n_y = a_n_y
        explicit_train, implicit_train = self._divide_ds(a_train_data)
        explicit_dev, implicit_dev = self._divide_ds(a_dev_data)
        self.explicit.train(explicit_train, explicit_dev, a_n_y)
        self.implicit.train(implicit_train, implicit_dev, a_n_y)

    def predict(self, a_rel, a_test_data):
        """Method for predicting sense of single relation.

        Args:
        a_rel (dict):
          discourse relation whose sense should be predicted
        a_test_data (2-tuple(dict, dict)):
          list of input JSON data

        Returns:
        str:
          most probable sense of discourse relation

        """
        if self._is_explicit(a_rel):
            return self.explicit.predict(a_rel)
        return self.implicit.predict(a_rel)

    def _free(self):
        """Free resources used by the model.

        Args:
        (void):

        Returns:
        (void):

        """
        del self.explicit
        del self.implicit
        self.n_y = -1

    def _divide_ds(self, a_ds):
        """Separate dataset into explicit and implicit instances.

        Args:
        a_ds (2-tuple(dict, dict)):
          list of gold relations and dict with parses

        Returns:
        (((list, dict), (list, dict))):
          trainings set with explicit and implicit connectives

        """
        if a_ds is None:
            return (([], {}), ([], {}))
        explicit_instances = []
        implicit_instances = []
        for irel in a_ds[0]:
            if self._is_explicit(irel):
                explicit_instances.append(irel)
            else:
                implicit_instances.append(irel)
        ret = ((explicit_instances, a_ds[1]),
               (implicit_instances, a_ds[1]))
        return ret

    def _is_explicit(self, a_rel):
        """Check whether given relation is explicit.

        Args:
        a_rel (dict):
          discourse relation to classify

        Returns:
        (bool):
          True if the relation is explicit

        """
        return bool(a_rel[CONNECTIVE][TOK_LIST])