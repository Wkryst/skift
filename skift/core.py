
"""scikit-learn classifier wrapper for fasttext."""

import os
import abc
from random import randint

import numpy as np
from fastText import train_supervised
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.utils.validation import check_is_fitted
from sklearn.utils.multiclass import unique_labels

from .util import dump_xy_to_fasttext_format


TEMP_DIR = os.path.expanduser('~/.temp')
os.makedirs(TEMP_DIR, exist_ok=True)


def temp_dataset_fpath():
    temp_fname = 'temp_ft_trainset_{}.ft'.format(randint(1, 99999))
    return os.path.join(TEMP_DIR, temp_fname)


class FtClassifierABC(BaseEstimator, ClassifierMixin, metaclass=abc.ABCMeta):
    """An abstact base class for sklearn classifier adapters for fasttext.

    Parameters
    ----------
    **kwargs
        Keyword arguments will be redirected to fasttext.train_supervised.
    """
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.kwargs.pop('input', None)  # remove the 'input' arg, if given

    ALLOWED_DTYPES_ = ['<U26', object]

    @staticmethod
    def _validate_x(X):
        try:
            if X.dtype not in FtClassifierABC.ALLOWED_DTYPES_:
                raise ValueError(
                    "FastTextClassifier methods must get a numpy array of "
                    "dtype object as the X parameter.")
            return np.array(X)
        except AttributeError:
            return FtClassifierABC._validate_x(np.array(X))

    @staticmethod
    def _validate_y(y):
        try:
            if len(y.shape) != 1:
                raise ValueError(
                    "FastTextClassifier methods must get a one-dimensional "
                    "numpy array as the y parameter.")
            return np.array(y)
        except AttributeError:
            return FtClassifierABC._validate_y(np.array(y))

    @abc.abstractmethod
    def _input_col(self, X):
        pass

    def fit(self, X, y):
        """Fits the classifier

        Parameters
        ----------
        X : array-like, shape = [n_samples, n_features]
            The training input samples.
        y : array-like, shape = [n_samples]
            The target values. An array of int.

        Returns
        -------
        self : object
            Returns self.
        """
        # Check that X and y have correct shape
        self._validate_x(X)
        y = self._validate_y(y)
        # Store the classes seen during fit
        self.classes_ = unique_labels(y)
        self.num_classes_ = len(self.classes_)
        self.class_labels_ = [
            '__label__{}'.format(lbl) for lbl in self.classes_]
        # Dump training set to a fasttext-compatible file
        self.temp_trainset_fpath = temp_dataset_fpath()
        input_col = self._input_col(X)
        dump_xy_to_fasttext_format(input_col, y, self.temp_trainset_fpath)
        # train
        self.model = train_supervised(
            input=self.temp_trainset_fpath, **self.kwargs)
        # Return the classifier
        return self

    @staticmethod
    def _clean_label(ft_label):
        return int(ft_label[9:])

    def _predict(self, X, k=1):
        # Ensure that fit had been called
        check_is_fitted(self, ['model'])

        # Input validation{
        self._validate_x(X)
        input_col = self._input_col(X)

        return [self.model.predict(text, k) for text in input_col]

    def predict(self, X):
        """Predict labels.

        Parameters
        ----------
        X : array-like of shape = [n_samples, n_features]
            The input samples.

        Returns
        -------
        y : array of int of shape = [n_samples]
            Predicted labels for the given inpurt samples.
        """
        return [
            self._clean_label(res[0][0])
            for res in self._predict(X)
        ]

    def _format_probas(self, result):
        lbl_prob_pairs = zip(result[0], result[1])
        sorted_lbl_prob_pairs = sorted(
            lbl_prob_pairs, key=lambda x: self.class_labels_.index(x[0]))
        return [x[1] for x in sorted_lbl_prob_pairs]

    def predict_proba(self, X):
        """Predict class probabilities for X.

        Parameters
        ----------
        X : array-like of shape = [n_samples, n_features]
            The input samples.

        Returns
        -------
        p : array of shape = [n_samples, n_classes]
            The class probabilities of the input samples. The order of the
            classes corresponds to that in the attribute classes_.
        """
        return [
            self._format_probas(res)
            for res in self._predict(X, self.num_classes_)
        ]


class FirstColFtClassifier(FtClassifierABC):
    """An sklearn classifier adapter for fasttext using the first column.

    Parameters
    ----------
    **kwargs
        Additional keyword arguments will be redirected to
        fasttext.train_supervised.
    """

    def _input_col(self, X):
        return X[:, 0]


class IdxBasedFtClassifier(FtClassifierABC):
    """An sklearn classifier adapter for fasttext that takes input by index.

    Parameters
    ----------
    input_ix : int
        The index of the text input column for fasttext.
    **kwargs
        Additional keyword arguments will be redirected to
        fasttext.train_supervised.
    """
    def __init__(self, input_ix, **kwargs):
        super().__init__()
        self.input_ix = input_ix

    def _input_col(self, X):
        return X[:, self.input_ix]


class FirstObjFtClassifier(FtClassifierABC):
    """An sklearn adapter for fasttext using the first object column as input.

    This classifier assume the X parameter for fit, predict and predict_proba
    is in all cases a pandas.DataFrame object.

    Parameters
    ----------
    **kwargs
        Keyword arguments will be redirected to fasttext.train_supervised.
    """

    def _input_col(self, X):
        input_col_name = None
        for col_name, dtype in X.dtypes.items():
            if dtype == object:
                input_col_name = col_name
                break
        if input_col_name:
            return X[input_col_name]
        raise ValueError("No object dtype column in input param X.")


class ColLblBasedFtClassifier(FtClassifierABC):
    """An sklearn adapter for fasttext taking input by column label.

    This classifier assume the X parameter for fit, predict and predict_proba
    is in all cases a pandas.DataFrame object.

    Parameters
    ----------
    input_col_lbl : str
        The label of the text input column for fasttext.
    **kwargs
        Keyword arguments will be redirected to fasttext.train_supervised.
    """

    def __init__(self, input_col_lbl, **kwargs):
        super().__init__()
        self.input_col_lbl = input_col_lbl

    def _input_col(self, X):
        return X[self.input_col_lbl]