""" contains the VibronicModelKeys """

from enum import Enum


class VibronicModelKeys(Enum):
    """The VibronicModelKeys, which are the keys (strings) used in the .json files to identify the corresponding values
    """
    number_of_modes = "number of modes"
    number_of_surfaces = "number of surfaces"
    energies = "energies"
    frequencies = "frequencies"
    electronic_transition_dipole_moments = "electronic transition dipole moments"
    magnetic_transition_dipole_moments = "magnetic transition dipole moments"
    linear_couplings = "linear couplings"
    quadratic_couplings = "quadratic couplings"
    cubic_couplings = "cubic couplings"
    quartic_couplings = "quartic couplings"

    # Spin Orbit Couplings (SOC)
    """ Note that the `soc_constant_couplings` are technically the SOC corrections to the energies (`E`).
    However we treat them in a similar matter to the other couplings, for a consistent naming scheme.
    You could argue that the energies should be G0... fair enough, not going to drastically change all the code right now.
    """
    soc_constant_couplings = "SOC constant couplings"
    soc_linear_couplings = "SOC linear couplings"
    soc_quadratic_couplings = "SOC quadratic couplings"
    soc_cubic_couplings = "SOC cubic couplings"
    soc_quartic_couplings = "SOC quartic couplings"

    # aliases for the enum members
    N = number_of_modes
    A = number_of_surfaces
    E = energies
    w = frequencies
    etdm = electronic_transition_dipole_moments
    mtdm = magnetic_transition_dipole_moments
    G1 = linear_couplings
    G2 = quadratic_couplings
    G3 = cubic_couplings
    G4 = quartic_couplings

    # Spin Orbit Couplings (SOC)
    S0 = soc_constant_couplings
    S1 = soc_linear_couplings
    S2 = soc_quadratic_couplings
    S3 = soc_cubic_couplings
    S4 = soc_quartic_couplings

    @classmethod
    def change_dictionary_keys_from_enum_members_to_strings(cls, input_dict):
        """ does what it says """
        for key, value in list(input_dict.items()):
            if key in cls:
                input_dict[key.value] = value
                del input_dict[key]
        return

    @classmethod
    def change_dictionary_keys_from_strings_to_enum_members(cls, input_dict):
        """ does what it says """
        for key, value in list(input_dict.items()):
            input_dict[cls(key)] = value
            del input_dict[key]
        return

    @classmethod
    def key_list(cls):
        """Returns a list of all enum members that are omitted from the .json file if all of their array's values are 0
        """
        return [cls.E, cls.G1, cls.G2, cls.G3, cls.G4]

    @classmethod
    def coupling_list(cls):
        """Return a list of enum members corresponding to `coupling terms`.

        These are coefficients for the continues degrees of freedom."""
        return [cls.G1, cls.G2, cls.G3, cls.G4]

    @classmethod
    def soc_coupling_list(cls):
        """Return a list of enum members corresponding to `soc coupling terms`.

        These are coefficients for the spin-orbit-coupling degrees of freedom."""
        return [cls.S0, cls.S1, cls.S2, cls.S3, cls.S4]

    @classmethod
    def max_order(cls):
        """Return the maximal order of coupling terms currently implemented in the code."""
        return len(cls.coupling_list())
