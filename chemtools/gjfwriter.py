import functools
import collections
import base64
import logging
import re

import numpy
from numpy.linalg import norm

import structure
from constants import KEYWORDS, NUMBERS
from mol_name import get_exact_name
from ml import get_decay_distance_correction_feature_vector, \
    get_naive_feature_vector, get_decay_feature_vector, \
    get_properties_from_decay_with_predictions
import dataparser


logger = logging.getLogger(__name__)


def cache(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        name = '_' + f.__name__.lstrip('get')
        value = self.__dict__.get(name, None)
        if value is None:
            value = f(self, *args, **kwargs)
        self.__dict__[name] = value
        return self.__dict__[name]
    return wrapper


class Molecule(object):

    def __init__(self, name, **kwargs):
        self.name = name
        self.keywords = kwargs.get('keywords', KEYWORDS)
        self.nprocshared = kwargs.get('nprocshared', 16)
        self.mem = kwargs.get('memory', 59)
        self.charge = kwargs.get('charge', 0)
        self.multiplicty = kwargs.get('multiplicity', 1)
        self.perturb = kwargs.get('perturb', 0.0)
        self.scale = kwargs.get('scale', 10)
        self._structure = None

    @property
    @cache
    def structure(self):
        return self._structure
    @structure.setter
    def structure(self, value):
        self._structure = value

    def from_gjf(self, f):
        self.structure = structure.from_gjf(f)

    def from_log(self, f):
        self.structure = structure.from_log(f)

    def get_gjf(self):
        starter = []
        if self.nprocshared is not None:
            starter.append("%%nprocshared=%d" % self.nprocshared)

        if self.structure.frozen:
            geom = "geom=(modredundant,connectivity)"
        else:
            geom = "geom=connectivity"

        starter.extend([
            "%%mem=%dGB" % self.mem,
            "%%chk=%s.chk" % self.name,
            "# %s %s" % (self.keywords, geom),
            "",
            self.name,
            "",
            "%d %d" % (self.charge, self.multiplicty),
            ""
        ])
        string = "\n".join(starter)
        string += self.structure.gjf
        return string

    def get_mol2(self):
        header = "@<TRIPOS>MOLECULE\n%s\n" % self.name
        body = self.structure.mol2
        return header + body

    def get_png(self, scale=None):
        if scale is None:
            scale = self.scale
        return self.structure.draw(scale).getvalue()

    def get_png_data_url(self, scale=None):
        if scale is None:
            scale = self.scale
        string = "data:image/png;base64,"
        return string + base64.b64encode(self.get_png(scale))

    def get_svg(self, scale=None):
        if scale is None:
            scale = self.scale
        return self.structure.draw(scale, svg=True).getvalue()

    def get_svg_data_url(self, scale=None):
        if scale is None:
            scale = self.scale
        string = "data:image/svg;base64,"
        return string + base64.b64encode(self.get_svg(scale))

    @cache
    def get_coulomb_matrix(self):
        coords = []
        other = []

        for atom in self.structure.atoms:
            coords.append(atom.xyz)
            other.append(NUMBERS[atom.element])

        N = len(self.structure.atoms)
        data = numpy.matrix(numpy.zeros((N, N)))
        for i, x in enumerate(coords):
            for j, y in enumerate(coords[:i]):
                val = (other[i] * other[j]) / norm(x - y)
                data[i, j] = val
                data[j, i] = val

        diag = [0.5 * x ** 2.4 for x in other]
        for i, x in enumerate(diag):
            data[i, i] = x

        return data

    @cache
    def get_coulomb_matrix_feature(self):
        data = self.get_coulomb_matrix()
        vector = []
        end = []
        for i in xrange(data.shape[0]):
            for j in xrange(0, i):
                vector.append(data[i, j])
            end.append(data[i, i])
        return vector + end

    def _get_element_counts(self):
        elems = [x.element for x in self.structure.atoms]
        return collections.Counter(elems)

    def get_formula(self):
        values = self._get_element_counts()
        return ''.join(key + str(values[key]) for key in sorted(values.keys()))


class Benzobisazole(Molecule):

    def __init__(self, name, **kwargs):
        super(Benzobisazole, self).__init__(name, **kwargs)
        self._exact_name = None
        self._structure_type = None

    @property
    @cache
    def structure(self):
        struct = structure.from_name(self.name)
        if self.perturb:
            struct.perturb(delta=self.perturb)
        return struct

    def get_exact_name(self, spacers=False):
        if self._exact_name is None:
            self._exact_name, self._structure_type = get_exact_name(self.name,
                                                                spacers=True)
        if spacers:
            return self._exact_name
        else:
            return self._exact_name.replace('*', '')

    @cache
    def get_naive_feature_vector(self, **kwargs):
        exact_name = self.get_exact_name(spacers=True)
        return get_naive_feature_vector(exact_name, **kwargs)

    @cache
    def get_decay_feature_vector(self, **kwargs):
        exact_name = self.get_exact_name(spacers=True)
        return get_decay_feature_vector(exact_name, **kwargs)

    @cache
    def get_decay_distance_correction_feature_vector(self, **kwargs):
        exact_name = self.get_exact_name(spacers=True)
        return get_decay_distance_correction_feature_vector(exact_name,
                                                            **kwargs)
    @cache
    def get_property_limits(self):
        results = {
            "n": [None, None, None],
            "m": [None, None, None]
        }
        for direction in results:
            try:
                groups = []
                xvals = range(1, 5)
                for j in xvals:
                    if direction in self.name:
                        expr = "%s\d+" % direction
                        replace = "%s%d" % (direction, j)
                        temp_name = re.sub(expr, replace, self.name)
                    else:
                        temp_name = self.name + "_%s%d" % (direction, j)

                    struct = Benzobisazole(temp_name)
                    groups.append(struct.get_property_predictions())

                lim_results = dataparser.predict_values(xvals, *zip(*groups))
                properties = ["homo", "lumo", "gap"]
                results[direction] = [lim_results[x][0] for x in properties]
            except Exception:
                logger.info("Improper property limits: %s - %s" %
                            (self.name, direction))
                pass
        return results

