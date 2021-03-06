import os
import itertools
import logging

from django.core.management.base import BaseCommand

from chemtools.structure import Atom, Bond
from chemtools.constants import NUMCORES, RGROUPS, ARYL


logger = logging.getLogger(__name__)


COREPARTS = ["*~0", "*~1", "~0", "~1"]
XRPARTS = ["*+0", "*+1"]
ARYLPARTS = ["~0", "~1", "+0", "+1"]

# Convention for marking ends of fragments
# [LEFT, RIGHT, BOTTOM, TOP]
ENDS = ["Sg", "Bh", "Hs", "Mt"]
# Convention for marking X/Y of core
XY = {"Ge": "XX", "As": "YY"}
PARTSLIST = [COREPARTS, XRPARTS, ARYLPARTS]


def parse_mol2(filename):
    with open(filename, 'r') as f:
        atoms = []
        bonds = []
        state = -2
        for line in f:
            if "@<TRIPOS>" in line:
                state += 1
            elif state == 0:
                x, y, z, e = line.split()[-4:]
                atoms.append(Atom(x, y, z, e, atoms))
            elif state == 1:
                a1, a2, t = line.split()[-3:]
                atom1 = atoms[int(a1) - 1]
                atom2 = atoms[int(a2) - 1]
                bonds.append(Bond((atom1, atom2), t, bonds))
        return atoms, bonds


class Command(BaseCommand):
    args = ''
    help = 'Extract mol2 data'

    def handle(self, base="chemtools", *args, **options):
	    for fname in os.listdir(os.path.join(base, "mol2")):
	        name, ext = os.path.splitext(fname)
	        for i, x in enumerate([NUMCORES, RGROUPS, ARYL]):
	            if name in x:
	                parts = PARTSLIST[i]

	        atoms, bonds = parse_mol2(os.path.join(base, "mol2", fname))
	        with open(os.path.join(base, "data", name), 'w') as f:
	            for atom in atoms:
	                if atom.element in ENDS:
	                    atom.element = parts[ENDS.index(atom.element)]
	                if atom.element in XY:
	                    atom.element = XY[atom.element]
	                f.write(str(atom) + '\n')
	            f.write('\n')
	            for bond in bonds:
	                f.write(' '.join(bond.mol2.split()[1:]) + '\n')
	        logger.debug("Converted %s to %s" % (fname, os.path.join(base, "data", name)))