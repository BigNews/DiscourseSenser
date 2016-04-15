#!/usr/bin/env python
# -*- coding: utf-8; mode: python; -*-

"""Module providing abstract interface class for Wang sense calssification.

Attributes:
WangBaseSenser (class):
  abstract class defining interface for explicit and implicit classifier

"""

##################################################################
# Imports
from __future__ import absolute_import, print_function

from dsenser.base import BaseSenser
from dsenser.constants import ARG1, ARG2, CONNECTIVE, DOC_ID, \
    RAW_TEXT, SENTENCES, SENSE, TOK_IDX, WORDS
from dsenser.resources import CHM, W2V
from dsenser.theano_utils import floatX, rmsprop, theano, \
    HE_UNIFORM, MAX_ITERS, ORTHOGONAL, TT

from collections import defaultdict, Counter
from datetime import datetime
import numpy as np
import re
import sys


##################################################################
# Variables and Constants
np.random.seed()

MAX = 1e10
INF = float('inf')
UNK_PROB = lambda: np.random.binomial(1, 0.05)
DIG_RE = re.compile(r"^[\d.]*\d[\d.]*$")


##################################################################
# Methods
def _norm_vec(a_x):
    """Normali length of the inout vector.

    Args:
    a_x (np.array):
    input vector

    Returns:
    (np.array):
    normalized vector

    """
    return a_x / (np.linalg.norm(a_x) or MAX)


def _norm_word(a_word):
    """Normalize word.

    Args:
    a_word (str):
    word to normalize

    Returns:
    (str):
    normalized word form

    """
    return DIG_RE.sub('1', a_word.lower())


##################################################################
# Class
class LSTMBaseSenser(BaseSenser):
    """Abstract class for disambiguating relation senses.

    Attrs:
    n_y (int): number of distinct classes

    Methods:

    """

    def __init__(self):
        """Class constructor.

        Args:

        """
        # access to the original word2vec resource
        self.ndim = 100
        self.lstm_dim = -1
        # mapping from word to its embedding index
        self.unk_w_i = 0
        self.w_i = 1
        self.w2emb_i = dict()
        # mapping from connective to its embedding index
        self.unk_c_i = 0
        self.c_i = 1
        self.c2emb_i = dict()
        # variables needed for training
        self._params = []
        self._w_stat = None
        self.W_EMB = self.CONN_EMB = self._cost = None
        # initialize theano functions to None
        self._reset_funcs()

    def train(self, a_train_data, a_dev_data=None, a_n_y=-1,
              a_i=-1, a_train_out=None, a_dev_out=None):
        """Method for training the model.

        Args:
        a_train_data (2-tuple(list, dict)):
          list of training JSON data
        a_dev_data (2-tuple(list, dict) or None):
          list of development JSON data
        a_n_y (int):
          number of distinct classes
        a_i (int):
          row index for the output predictions
        a_train_out (np.array or None):
          predictions for the training set
        a_dev_out (np.array or None):
          predictions for the training set

        Returns:
        (void):
          updates ``a_train_out`` and ``a_dev_out`` in place

        """
        self.n_y = a_n_y
        # allocate data to development set if there is none
        if a_dev_data is None:
            train_rels, parses = a_train_data
            docs = parses.keys()
            n_docs = len(docs)
            n_dev = max(n_docs / 10, 1)
            # sample without replacement
            dev_docs = set(np.random.choice(docs, n_dev, False))
            new_train_rels, dev_rels = [], []
            for irel in train_rels:
                if irel[DOC_ID] in dev_docs:
                    dev_rels.append(irel)
                else:
                    new_train_rels.append(irel)
            a_train_data = (new_train_rels, parses)
            a_dev_data = (dev_rels, parses)
        # convert training and development sets to features
        x_train, y_train = self._generate_ts(a_train_data,
                                             self.get_train_w_emb_i,
                                             self.get_train_c_emb_i)
        x_dev, y_dev = self._generate_ts(a_dev_data,
                                         self.get_test_w_emb_i,
                                         self.get_test_c_emb_i)
        # initialize the network
        self._init_nn()

        # perform the training
        train_cost = dev_cost = 0.
        min_train_cost = min_dev_cost = INF
        best_params = []
        for i in xrange(MAX_ITERS):
            train_cost = 0.
            start_time = datetime.utcnow()
            # perform one training iteration
            for (_, (emb1, emb2, conn)), y in zip(x_train, y_train):
                # print("x =", repr(x), file=sys.stderr)
                # print("y =", repr(y), file=sys.stderr)
                # F_OUT_ARG1, F_OUT_ARG2, I, EMB_CONN = self._debug_nn(*x)
                # print("F_OUT_ARG1 =", repr(F_OUT_ARG1), repr(F_OUT_ARG1.shape),
                #       file=sys.stderr)
                # print("F_OUT_ARG2 =", repr(F_OUT_ARG2), repr(F_OUT_ARG2.shape),
                #       file=sys.stderr)
                # print("I =", repr(I), repr(I.shape), file=sys.stderr)
                # print("EMB_CONN =", repr(EMB_CONN), repr(EMB_CONN.shape),
                #       file=sys.stderr)
                # sys.exit(66)
                train_cost += self._grad_shared(emb1, emb2, conn, y)
                self._update()
            # estimate the model on the dev set
            dev_cost = 0.
            for (_, (emb1, emb2, conn)), y in zip(x_train, y_train):
                dev_cost += self._compute_cost(emb1, emb2, conn, y)
            end_time = datetime.utcnow()
            time_delta = (end_time - start_time).seconds
            if min_dev_cost == INF or dev_cost < min_dev_cost:
                best_params = [p.get_value() for p in self._params]
                min_dev_cost = dev_cost
            print("Iteration {:d}:\ttrain_cost = {:f}\t"
                  "dev_cost={:f}\t({:.2f} sec)".format(
                      i, train_cost, dev_cost, time_delta), file=sys.stderr)
        if best_params:
            for p, val in zip(self._params, best_params):
                p.set_value(val)
        # make predictions for the judge
        if a_i >= 0:
            if a_train_out is not None:
                for i, x_i in x_train:
                    self._predict(x_i, a_train_out[i], a_i)
            if a_dev_out is not None:
                for i, x_i in x_dev:
                    self._predict(x_i, a_dev_out[i], a_i)
            else:
                for i, x_i in x_dev:
                    self._predict(x_i, a_train_out[i], a_i)
        # reset function members to allow cPickle store this model
        self._reset_funcs()

    def predict(self, a_rel, a_data, a_ret, a_i):
        """Method for predicting sense of single relation.

        Args:
        a_rel (dict):
          discourse relation whose sense should be predicted
        a_data (2-tuple(dict, dict)):
          list of input JSON data
        a_ret (np.array):
          output prediction vector
        a_i (int):
          row index in the output vector

        Returns:
        (void):
          updates ``a_ret`` in place

        """
        parses = a_data[-1]
        if self._predict_func is None:
            self._init_funcs()
        input_args = self._rel2x(a_rel, parses,
                                 self.get_test_w_emb_i,
                                 self.get_test_c_emb_i)
        return self._predict(input_args, a_ret, a_i)

    def _predict(self, a_args, a_ret, a_i):
        """Method for predicting sense of single relation.

        Args:
        a_args (list):
          list of input arguments to the prediction function
        a_ret (np.array):
          output prediction vector
        a_i (int):
          row index in the output vector

        Returns:
        (void):
          updates ``a_ret`` in place

        """
        # obtain model's estimates
        dec = self._predict_func(*a_args)
        if len(dec.shape) > 1:
            dec = np.mean(dec, axis=0)
        for i, ival in enumerate(dec):
            a_ret[a_i][i] = ival

    def _free(self):
        """Free resources used by the model.

        Args:
        (void):

        Returns:
        (void):

        """
        self.n_y = -1
        self._w_stat = None
        self._cleanup(self._params)
        self._params = []

    def _cleanup(self, a_vars):
        """Clean-up memory occupied by shared variables.

        Args:
        a_shared_vars: list(theano.shared)
          list of shared variables whose memory should be freed

        Returns:
        (void)

        """
        dim = 0
        for var_list in a_vars:
            for v in var_list:
                dim = len(v.shape.eval())
                v.set_value(np.zeros([0] * dim).astype(config.floatX))

    def _generate_ts(self, a_data, a_get_w_emb_i, a_get_c_emb_i):
        """Generate training set.

        Args:
        a_data (2-tuple(list, dict)):
          input data (discourse relations and parses)
        a_get_w_emb_i (method):
          custom method for retrieving the word embedding index
        a_get_c_emb_i (method):
          custom method for retrieving the conn embedding index

        Returns:
        (tuple(list, list)):
          lists of input features and expected classes

        """
        x, y = [], []
        if a_data is None:
            return (x, y)
        # generate features
        rels, parses = a_data
        # frequency of words in the corpus
        self._compute_w_stat(parses)
        for i, irel in rels:
            x.append((i, self._rel2x(irel, parses,
                                     a_get_w_emb_i,
                                     a_get_c_emb_i)))
            y.append(floatX(irel[SENSE]))
        return (x, y)

    def _rel2x(self, a_rel, a_parses, a_get_w_emb_i, a_get_c_emb_i):
        """Convert input relation to embeddings.

        Args:
        a_rel (dict):
          discourse relation whose tokens should be obtained
        a_parses (dict):
          parsed sentences
        a_get_w_emb_i (method):
          custom method for retrieving the word embedding index
        a_get_c_emb_i (method):
          custom method for retrieving the conn embedding index

        Returns:
        (np.array, np.array, np.array):
        embeddings of arg1, arg2, and connective

        """
        # print("rel2x: a_rel =", repr(a_rel))
        emb1 = self._arg2emb_idx(a_parses, a_rel, ARG1, a_get_w_emb_i)
        # print("emb_1 =", repr(emb1))
        emb2 = self._arg2emb_idx(a_parses, a_rel, ARG2, a_get_w_emb_i)
        # print("emb_2 =", repr(emb2))
        conn_toks = a_rel[CONNECTIVE][RAW_TEXT]
        # print("conn_toks =", repr(conn_toks))
        emb_conn = a_get_c_emb_i(conn_toks)
        # print("emb_conn =", repr(emb_conn))
        return (emb1, emb2, emb_conn)

    def _arg2emb_idx(self, a_parses, a_rel, a_arg, a_get_emb_i):
        """Extract classification features for a given relation.

        Args:
        a_parses (dict):
          parsed sentences
        a_rel (dict):
          discourse relation whose tokens should be obtained
        a_arg (str):
          relation argument to obtain senses for
        a_get_emb_i (method):
          custom method for retrieving the embedding index

        Returns:
        (np.array):
        convert input relation to word embedding matrix

        """
        toks = [t[0] for t in
                self._get_toks_pos(a_parses[a_rel[DOC_ID]][SENTENCES],
                                   a_rel, a_arg)]
        return np.asarray([a_get_emb_i(t) for t in toks], dtype="int32")

    def get_train_w_emb_i(self, a_word):
        """Obtain embedding index for the given word.

        Args:
        a_word (str):
        word whose embedding index should be retrieved

        Returns:
        (int):
        embedding index od the given connective

        """
        a_word = _norm_word(a_word)
        if a_word in self.w2emb_i:
            return self.w2emb_i[a_word]
        elif self._w_stat[a_word] < 2 and UNK_PROB():
            self.w2emb_i[a_word] = self.unk_w_i
            return self.unk_w_i
        else:
            i = self.w2emb_i[a_word] = self.w_i
            self.w_i += 1
            return i
        # elif a_word in self.w2v:
        #     i = self.w2emb_i[a_word] = self.w_i
        #     self.w_i += 1
        #     return i
        # else:
        #     return self.unk_w_i

    def get_train_c_emb_i(self, a_conn):
        """Obtain embedding index for the given connective.

        Args:
        a_conn (str):
        connective whose embedding index should be retrieved

        Returns:
        (int):
        embedding index of the given connective

        """
        a_conn, _ = CHM.map_raw_connective(a_conn.lower())
        if a_conn in self.c2emb_i:
            ret = self.c2emb_i[a_conn]
        else:
            i = self.c2emb_i[a_conn] = self.c_i
            self.c_i += 1
            ret = i
        return np.asarray(ret, dtype="int32")

    def get_test_w_emb_i(self, a_word):
        """Obtain embedding index for the given word.

        Args:
        a_word (str):
        word whose embedding index should be retrieved

        Returns:
        (int):
        embedding index od the given connective

        """
        a_word = _norm_word(a_word)
        if a_word in self.w2emb_i:
            return self.w2emb_i[a_word]
        return self.unk_w_i

    def get_test_c_emb_i(self, a_conn):
        """Obtain embedding index for the given connective.

        Args:
        a_conn (str):
        connective whose embedding index should be retrieved

        Returns:
        (int):
        embedding index of the given connective

        """
        a_conn, _ = CHM.map_raw_connective(a_conn.lower())
        if a_conn in self.c2emb_i:
            ret = self.c2emb_i[a_conn]
        else:
            ret = self.unk_c_i
        return np.asarray(ret, dtype="int32")

    def _init_nn(self):
        """Initialize neural network.

        Args:
        (void)

        Returns:
        (void)

        """
        self.lstm_dim = self.ndim - (self.ndim - self.n_y) / 2
        # indices of word embeddings
        self.W_INDICES_ARG1 = TT.ivector(name="W_INDICES_ARG1")
        self.W_INDICES_ARG2 = TT.ivector(name="W_INDICES_ARG2")
        # connective's index
        self.CONN_INDEX = TT.iscalar(name="CONN_INDEX")
        # initialize the matrix of word embeddings
        self._init_w_emb()
        self._params.append(self.W_EMB)
        # word embeddings of the arguments
        self.EMB_ARG1 = self.W_EMB[self.W_INDICES_ARG1]
        self.EMB_ARG2 = self.W_EMB[self.W_INDICES_ARG2]
        # connective's embedding
        self._init_conn_emb()
        self._params.append(self.CONN_EMB)
        self.EMB_CONN = self.CONN_EMB[self.CONN_INDEX]
        # initialize forward LSTM unit
        # invars = ((self.EMB_ARG1, False), (self.EMB_ARG1, True),
        #           (self.EMB_ARG2, False), (self.EMB_ARG2, True))
        invars = (self.EMB_ARG1, self.EMB_ARG2)
        params, outvars = self._init_lstm(invars)
        self._params.extend(params)
        self.F_OUT_ARG1, self.F_OUT_ARG2 = outvars
        # initialize backward LSTM unit
        # define final units
        self.I = TT.concatenate((self.F_OUT_ARG1, self.F_OUT_ARG2,
                                 self.EMB_CONN))
        self.I2Y = theano.shared(value=HE_UNIFORM((self.n_y,
                                                   self.lstm_dim * 3)),
                                 name="I2Y")
        self.y_bias = theano.shared(value=HE_UNIFORM((1, self.n_y)),
                                    name="y_bias")
        self._params.extend([self.I2Y, self.y_bias])
        self.Y_pred = TT.nnet.softmax(TT.dot(self.I2Y, self.I).T + self.y_bias)
        # initialize cost and optimization functions
        self.Y_gold = TT.vector(name="Y_gold")
        self._cost = TT.sum((self.Y_pred - self.Y_gold) ** 2)
        grads = TT.grad(self._cost, wrt=self._params)
        self._init_funcs(grads)

    def _init_w_emb(self):
        """Initialize task-specific word embeddings.

        Args:
        (void)

        Returns:
        (void)

        """
        self.W_EMB = theano.shared(
            value=HE_UNIFORM((self.w_i, self.ndim)), name="W_EMB")

    def _init_conn_emb(self):
        """Initialize task-specific connective embeddings.

        Args:
        (void)

        Returns:
        (void)

        """
        self.CONN_EMB = theano.shared(
            value=HE_UNIFORM((self.c_i, self.lstm_dim)),
            name="CONN_EMB")

    def _init_lstm(self, a_invars, a_sfx="-forward"):
        """Initialize LSTM layer.

        Args:
        a_invars (list(theano.shared)):
        list of input parameters as symbolic theano variable
        a_sfx (str):
        suffix to use for function and parameter names

        Returns:
        (2-tuple)
        parameters to be optimized and list of symbolic outputs from the
        function

        """
        lstm_dim = self.lstm_dim
        # initialize transformation matrices and bias term
        W_dim = (lstm_dim, self.ndim)
        W = np.concatenate([ORTHOGONAL(W_dim), ORTHOGONAL(W_dim),
                            ORTHOGONAL(W_dim), ORTHOGONAL(W_dim)],
                           axis=0)
        W = theano.shared(value=W, name="W" + a_sfx)

        U_dim = (lstm_dim, lstm_dim)
        U = np.concatenate([ORTHOGONAL(U_dim), ORTHOGONAL(U_dim),
                            ORTHOGONAL(U_dim), ORTHOGONAL(U_dim)],
                           axis=0)
        U = theano.shared(value=U, name="U" + a_sfx)
        V = ORTHOGONAL(U_dim)   # V for vendetta
        V = theano.shared(value=V, name="V" + a_sfx)

        b_dim = (1, lstm_dim * 4)
        b = theano.shared(value=HE_UNIFORM(b_dim), name="b" + a_sfx)

        params = [W, U, V, b]

        # custom function for splitting up matrix parts
        def _slice(_x, n, dim):
            if _x.ndim == 3:
                return _x[:, :, n * dim:(n + 1) * dim]
            return _x[:, n * dim:(n + 1) * dim]

        # define recurrent LSTM unit
        def _step(x_, h_, c_):
            """Recurrent LSTM unit.

            Note:
            The general order of function parameters to fn is:
            sequences (if any), prior result(s) (if needed),
            non-sequences (if any)

            Args:
            x_ (theano.shared): input vector
            h_ (theano.shared): output vector
            c_ (theano.shared): memory state

            Returns:
            (2-tuple(h, c))
            new hidden and memory states

            """
            # pre-compute common terms:
            # W \in R^{236 x 100}
            # x \in R^{1 x 100}
            # U \in R^{236 x 59}
            # h \in R^{1 x 59}
            # b \in R^{1 x 236}
            # xhb \in R^{1 x 236}
            xhb = (TT.dot(W, x_.T) + TT.dot(U, h_.T)).T + b
            # compute gates and output
            # i \in R^{1 x 59}
            i = TT.nnet.sigmoid(_slice(xhb, 0, lstm_dim))
            # f \in R^{1 x 59}
            f = TT.nnet.sigmoid(_slice(xhb, 1, lstm_dim))
            # c \in R^{1 x 59}
            c = TT.tanh(_slice(xhb, 2, lstm_dim))
            # c \in R^{1 x 59}
            c = i * c + f * c_
            # V \in R^{59 x 59}
            # o \in R^{1 x 59}
            o = TT.nnet.sigmoid(_slice(xhb, 3, lstm_dim) +
                                TT.dot(V, c.T).T)
            # h \in R^{1 x 59}
            h = o * TT.tanh(c)
            # return current output and memory state
            return h.flatten(), c.flatten()

        m = 0
        n = lstm_dim
        ov = h = c = None
        outvars = []
        for iv in a_invars:
            m = iv.shape[0]
            ret, _ = theano.scan(_step,
                                 sequences=[iv],
                                 outputs_info=[floatX(np.zeros((n,))),
                                               floatX(np.zeros((n,)))],
                                 name="LSTM" + str(iv) + a_sfx,
                                 n_steps=m)
            ov = TT.mean(ret[0], axis=0)
            # ov = ret[0]
            outvars.append(ov)
        return params, outvars

    def _compute_w_stat(self, a_parses):
        """Compute word frequencies on the corpus.

        Args:
        a_parses (dict):
        CoNLL parses

        Returns:
        (void):
        modifies instance variables in place

        """
        self._w_stat = Counter(_norm_word(w[TOK_IDX])
                               for doc in a_parses.itervalues()
                               for sent in doc[SENTENCES]
                               for w in sent[WORDS])

    def _init_funcs(self, a_grads=None):
        """Compile theano functions.

        Args:
        a_grads (theano.shared or None):
        gradients of the trainign function

        Returns:
        (void):
        modifies instance variables in place

        """
        if a_grads:
            self._grad_shared, self._update = rmsprop(self._params, a_grads,
                                                      [self.W_INDICES_ARG1,
                                                       self.W_INDICES_ARG2,
                                                       self.CONN_INDEX],
                                                      self.Y_gold,
                                                      self._cost)
        if self._compute_cost is None:
            self._compute_cost = theano.function([self.W_INDICES_ARG1,
                                                  self.W_INDICES_ARG2,
                                                  self.CONN_INDEX,
                                                  self.Y_gold], self._cost,
                                                 name="_compute_cost")
        # initialize prediction function
        if self._predict_func is None:
            self._predict_func = theano.function([self.W_INDICES_ARG1,
                                                  self.W_INDICES_ARG2,
                                                  self.CONN_INDEX],
                                                 self.Y_pred,
                                                 name="_predict_func")
        # initialize debug function
        if self._debug_nn is None:
            self._debug_nn = theano.function([self.W_INDICES_ARG1,
                                              self.W_INDICES_ARG2,
                                              self.CONN_INDEX],
                                             [self.F_OUT_ARG1, self.F_OUT_ARG2,
                                              self.I, self.EMB_CONN],
                                             name="_debug_nn")

    def _reset_funcs(self):
        """Set all compiled theano functions to None.

        Args:
        (void):

        Returns:
        (void):
        modifies instance variables in place

        """
        self._grad_shared = None
        self._update = None
        self._compute_cost = None
        self._predict_func = None
        self._debug_nn = None
