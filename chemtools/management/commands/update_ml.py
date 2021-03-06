import os
import itertools
import cPickle

from django.core.management.base import BaseCommand
from django.core.files import File
import numpy
import scipy.optimize
from sklearn import svm
from sklearn import cross_validation
from sklearn.metrics import mean_absolute_error

from data.models import DataPoint, Predictor
from project.utils import StringIO


def lock(func):
    def wrapper(*args, **kwargs):
        # Not very safe, but it will work well enough
        if os.path.exists(".updating_ml"):
            print "Already running"
            return
        with open(".updating_ml", "w"):
            try:
                value = func(*args, **kwargs)
            except Exception as e:
                print e
                value = None
        os.remove(".updating_ml")
        return value
    return wrapper


class Command(BaseCommand):
    args = ''
    help = 'Update ML data'

    def handle(self, *args, **options):
        run_all()


def test_clf_kfold(X, y, clf, folds=10):
    train = numpy.zeros(folds)
    cross = numpy.zeros(folds)
    folds = cross_validation.KFold(y.shape[0], n_folds=folds)
    for i, (train_idx, test_idx) in enumerate(folds):
        X_train = X[train_idx]
        X_test = X[test_idx]
        y_train = y[train_idx].T.tolist()[0]
        y_test = y[test_idx].T.tolist()[0]
        clf.fit(X_train, y_train)
        train[i] = mean_absolute_error(clf.predict(X_train), y_train)
        cross[i] = mean_absolute_error(clf.predict(X_test), y_test)
    return (train.mean(), train.std()), (cross.mean(), cross.std())


def scan(X, y, function, params):
    size = [len(x) for x in params.values()]
    train_results = numpy.zeros(size)
    test_results = numpy.zeros(size)
    keys = params.keys()
    values = params.values()
    for group in itertools.product(*values):
        idx = tuple([a.index(b) for a, b in zip(values, group) if len(a) > 1])
        a = dict(zip(keys, group))
        clf = function(**a)
        train, test = test_clf_kfold(X, y, clf)
        train_results[idx] = train[0]
        test_results[idx] = test[0]
    return train_results, test_results


class OptimizedCLF(object):

    def __init__(self, X, y, func, params):
        self.params = params
        self.func = func
        self.X = X
        self.y = y
        self.optimized_clf = None
        self.optimized_params = None

    def __call__(self, *args):
        a = dict(zip(self.params.keys(), *args))
        clf = self.func(**a)
        train, test = test_clf_kfold(self.X, self.y, clf, folds=5)
        return test[0]

    def get_optimized_clf(self):
        if not len(self.params.keys()):
            self.optimized_clf = self.func()
        if self.optimized_clf is not None:
            return self.optimized_clf
        items = self.params.items()
        types = set([list, tuple])
        listparams = dict((k, v) for k, v in items if type(v) in types)
        itemparams = dict((k, v) for k, v in items if type(v) not in types)
        listvalues = []
        itemvalues = []
        if listparams:
            _, test = scan(self.X, self.y, self.func, listparams)
            listvalues = []
            temp = numpy.unravel_index(test.argmin(), test.shape)
            for i, pick in enumerate(listparams.values()):
                listvalues.append(pick[temp[i]])
            listvalues = listvalues[::-1]
        if itemparams:
            bounds = ((1e-8, None), ) * len(self.params.keys())
            results = scipy.optimize.fmin_l_bfgs_b(
                self,
                self.params.values(),
                bounds=bounds,
                approx_grad=True,
                epsilon=0.1,
                maxiter=15,
                maxfun=30,
            )
            itemvalues = results[0].tolist()
        keys = listparams.keys() + itemparams.keys()
        values = listvalues + itemvalues
        self.optimized_params = dict(zip(keys, values))
        self.optimized_clf = self.func(**self.optimized_params)
        return self.optimized_clf


def fit_func(X, y, clf=None):
    func = svm.SVR
    if clf is None:
        params = {"C": 10, "gamma": 0.05}
    else:
        print "Using previous clf"
        params = {"C": clf.C, "gamma": clf.gamma}

    clf = OptimizedCLF(X, y, func, params).get_optimized_clf()
    train, test = test_clf_kfold(X, y, clf, folds=10)
    clf.fit(X, y.T.tolist()[0])
    clf.test_error = test
    return clf


def get_first_layer(X, homo, lumo, gap, in_clfs=None):
    print "Creating first layer"
    if in_clfs is not None:
        in_homo_clf, in_lumo_clf, in_gap_clf = in_clfs
    else:
        in_homo_clf, in_lumo_clf, in_gap_clf = [None] * 3

    homo_clf = fit_func(X, homo, clf=in_homo_clf)
    lumo_clf = fit_func(X, lumo, clf=in_lumo_clf)
    gap_clf = fit_func(X, gap, clf=in_gap_clf)
    return homo_clf, lumo_clf, gap_clf


def get_second_layer(X, homo, lumo, gap, clfs, in_pred_clfs=None):
    print "Creating second layer"
    if in_pred_clfs is not None:
        in_pred_homo, in_pred_lumo, in_pred_gap = in_pred_clfs
    else:
        in_pred_homo, in_pred_lumo, in_pred_gap = [None] * 3

    homo_clf, lumo_clf, gap_clf = clfs
    homop = numpy.matrix(homo_clf.predict(X)).T
    lumop = numpy.matrix(lumo_clf.predict(X)).T
    gapp = numpy.matrix(gap_clf.predict(X)).T

    X_homo = numpy.concatenate([X, lumop, gapp], 1)
    X_lumo = numpy.concatenate([X, gapp, homop], 1)
    X_gap = numpy.concatenate([X, homop, lumop], 1)

    pred_homo_clf = fit_func(X_homo, homo, clf=in_pred_homo)
    pred_lumo_clf = fit_func(X_lumo, lumo, clf=in_pred_lumo)
    pred_gap_clf = fit_func(X_gap, gap, clf=in_pred_gap)
    return pred_homo_clf, pred_lumo_clf, pred_gap_clf


def save_clfs(clfs, pred_clfs):
    print "Saving clfs"

    with StringIO(name="decay_predictors.pkl") as f:
        cPickle.dump((clfs, pred_clfs), f, protocol=-1)
        f.seek(0)

        homo, lumo, gap = pred_clfs
        pred = Predictor(
            homo_error=homo.test_error[0],
            lumo_error=lumo.test_error[0],
            gap_error=gap.test_error[0],
            pickle=File(f),
        )
        pred.save()


@lock
def run_all():
    pred = Predictor.objects.latest()
    latest = DataPoint.objects.latest()

    if latest.created < pred.created:
        print "No Update"
        return

    print "Loading Data"
    FEATURE, HOMO, LUMO, GAP = DataPoint.get_all_data()
    in_clfs, in_pred_clfs = pred.get_predictors()
    clfs = get_first_layer(FEATURE, HOMO, LUMO, GAP, in_clfs)
    pred_clfs = get_second_layer(FEATURE, HOMO, LUMO, GAP, clfs, in_pred_clfs)
    save_clfs(clfs, pred_clfs)
