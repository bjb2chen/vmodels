""" x """

# system imports
import os
from os.path import splitext
import sys
import types
import subprocess
import shutil
import re
# import json
import functools
import itertools as it

# third party imports
import numpy as np
import pprint


# local packages
import project_parameters as pp
from project_parameters import *  # eventually remove this


# ---------------------------------------------------------------------------------------
_possible_mctdh_headers = [
    'Frequencies',
    'Electronic Hamitonian',  # NOTE - THIS IS NOT A SPELLING ERROR (Hamitonian)
    'Electronic transition moments',
    'Magnetic transition moments',
    'Linear Coupling Constants',
    'Diagonal Quadratic Coupling Constants',
    'Off_diagonal Quadratic Coupling Constants',
    'Cubic Coupling Constants',
    'Quartic Coupling Constants',
    'Quintic Coupling Constants',
    'Sextic Coupling Constants',
    'Bi-Cubic Constants',
    'Bi-Quartic Constants',
    'end-parameter-section',
]

# ---------------------------------------------------------------------------------------


def subprocess_run_wrapper(*args, **kwargs):
    """ Subprocess.run() returns the value from std.in """

    assert len(args) == 1
    command = args[0]
    assert isinstance(command, str) or isinstance(command, list), (
        f"Bad arguments! First arg should only be str or list you provided {type(command)}"
    )

    if False and __debug__:  # for checking
        print(args)
        print(command)
        print(kwargs)

        breakpoint()

    if pp.dry_run:
        if isinstance(command, list):
            command = " ".join(command)+'\n'

        print(command)
        # fake a return value
        return_obj = types.SimpleNamespace()
        return_obj.returncode = 0
        return return_obj
    else:
        return subprocess.run(command, **kwargs)


def subprocess_call_wrapper(*args, **kwargs):
    """ subprocess.call only returns 1/0  """

    assert len(args) == 1
    command = args[0]
    assert isinstance(command, str) or isinstance(command, list), (
        f"Bad arguments! First arg should only be str or list you provided {type(command)}"
    )

    if False and __debug__:  # for checking
        print(args)
        print(command)
        print(kwargs)
        breakpoint()

    if pp.dry_run:
        if isinstance(command, list):
            command = " ".join(command)+'\n'
        print(command)

        # fake a return value
        return_obj = types.SimpleNamespace()
        return_obj.returncode = 0
        return return_obj
    else:
        return subprocess.call(command, **kwargs)


def os_system_wrapper(*args, **kwargs):
    """ os.system is needed for submitting jobs on nlogn!
        sbatch on nlogn only works with os
    """
    assert len(args) == 1
    command = args[0]

    if False and __debug__:  # for checking
        print(args)
        print(command)
        print(kwargs)
        breakpoint()

    if pp.dry_run:
        print(f"{command}\n")
        return
    else:
        return os.system(command, **kwargs)


def upper_triangle_loop_indices(max_num, number_of_indicies=2):
    """ Returns generator function providing indices to iterate over upper-triangle elements of a tensor/matrix.
    Only guaranteed to work for 2D matrix ... should work for 3D but haven't checked for certain yet.

    see stackoverflow link below for an explanation on how to do combination loops
    https://stackoverflow.com/questions/69321896/how-to-do-dependent-nested-loop-using-itertools-product
    """
    if True:
        assert number_of_indicies >= 2, "Don't use this fxn for 1D arrays / lists"
        return it.combinations(range(max_num), number_of_indicies)
    else:
        indices = []
        if number_of_indicies == 2:
            for n1 in range(max_num):
                for n2 in range(max_num):
                    if n1 < n2:
                        indices.append((n1, n2))

        elif number_of_indicies == 3:
            for n1 in range(max_num):
                for n2 in range(max_num):
                    for n3 in range(max_num):
                        if n1 < n2 and n2 < n3:
                            indices.append((n1, n2, n3))
        else:
            raise Exception(f"Not Implemented for {number_of_indicies=} > 3")

        return indices


# ---------------------------------------------------------------------------------------


linear_disp_keys = ["+1", "+2", "-1", "-2"]
bi_linear_disp_keys = ["++", "+-", "-+", "--"]

linear_disp_suffix = {
    "+1": 'plus',
    "+2": 'minus',
    "-1": 'plusx2',
    "-2": 'minusx2',
}

bi_linear_disp_suffix = {
    "++": 'pp',
    "+-": 'pm',
    "-+": 'mp',
    "--": 'mm',
}

# these could be lists or dicts... for now I'm just making them dicts
linear_disp_filenames = {
    k: f'dist_structure_{linear_disp_suffix[k]}'
    for k in linear_disp_keys
}

bi_linear_disp_filenames = {
    k: f'dist_structure_{bi_linear_disp_suffix[k]}'
    for k in bi_linear_disp_keys
}


def _remove_existing_distorted_structure_files(filename_dict):
    """ Delete existing distorted structure files """
    for filename in filename_dict.values():
        try:
            subprocess_run_wrapper(['rm', '-f', filename])
        except Exception as e:
            print(f"Error deleting {filename}: {str(e)}")
    return


# ---------------------------------------------------------------------------------------

def extract_lines_between_patterns(filename, start_pattern, end_pattern, collecting=False):
    """ Function to extract lines between patterns in a file """
    selected_lines = []
    # would be good to replace this with memory mapping find or grep command?
    with open(filename, 'r', errors='replace') as file:
        for line in file:
            if start_pattern in line:
                collecting = True
            if end_pattern in line:
                collecting = False
                # break  # pattern should only occur in file once
            if collecting:
                selected_lines.append(line)

    # del selected_lines[slice(0, nof_line_skip)]

    return selected_lines


def my_subgam(path, **kwargs):
    """ Create our own GAMESS job submission script
        Recording the script inside .slurm helps for recordkeeping """

    # if its easier to just change project parameters i would recommend doing
    # ncpus = pp.ncpus
    # nhour = pp.nhour
    # ngb = pp.ngb

    ncpus = kwargs.get('ncpus', 2)
    nhour = kwargs.get('nhour', 1)
    ngb = kwargs.get('ngb', 2)

    # Remove the ".inp" extension from the filename
    input_no_ext, extension = splitext(path)
    print(f"running calculations for {input_no_ext}")

    # wd = os.getcwd()

    file_contents = "".join([
        "#!/bin/bash\n",
        "#SBATCH --nodes=1\n",
        f"#SBATCH --ntasks={ncpus}\n",
        f"#SBATCH --mem-per-cpu={ngb}G\n",
        f"#SBATCH --time={nhour}:00:00\n",
        "\n",
        "cd $SLURM_SUBMIT_DIR\n",
        "\n",
        "export SLURM_CPUS_PER_TASK\n",
        'mkdir -p /home/$USER/.gamess_ascii_files/$SLURM_JOBID\n',
        f"/home/$USER/LOCAL/runG_diab {input_no_ext}.inp {ncpus} \n",
    ])

    with open(f"{input_no_ext}.slurm", "w") as slurm_file:
        slurm_file.write(file_contents)

    return f"{input_no_ext}.slurm"


def diabatization(**kwargs):
    """ Preform diabatization?

    Returns a dictionary of dictionaries `dist_coord`
    Whose keys are `displacement_keys` and `bi_linear_keys`.
    Each of those individual dictionaries store ( ... ?)

    (other info)
    """

    # -------------------------------------------------------------------------
    # unpacking (should get rid of these two lines eventually)
    # modes_included = kwargs['modes_included']
    filnam = filename = kwargs['project_filename']

    # kwargs has a bunch more items inside it
    freqcm = kwargs.get('freqcm')
    ndim = kwargs.get('ndim')
    refcoord = kwargs.get('refcoord')
    nrmmod = kwargs.get('nrmmod')
    natoms = kwargs.get('natoms')
    atmlst = kwargs.get('atmlst')
    chrglst = kwargs.get('chrglst')
    qsize = kwargs.get('qsize', 0.05)
    ha2ev = kwargs.get('ha2ev', 27.2113961318)
    wn2ev = kwargs.get('wn2ev', 0.000123981)
    wn2eh = kwargs.get('wn2eh', 0.00000455633)
    ang2br = kwargs.get('ang2br', 1.889725989)
    amu2me = kwargs.get('amu2me', 1822.88839)

    # if its easier to just change project parameters i would recommend doing
    # amu2me = pp.amu2me
    # <...> (etc.)
    # since you have to use these values everywhere I take back what I said about using kwargs
    # probably best to just use project parameters
    # -------------------------------------------------------------------------
    # Precomputed constants

    """
    it might be worth while to precompute constants here?
    for example in `_convert_qsize_to_rsize` we compute
        q / (pow(amu2me, 0.5) * ang2br * pow(omega * wn2eh, 0.5))

    this could be replace with
        q / qsize_to_rsize_conversion_factor[i]

    where we compute the factor for all modes included before hand
        qsize_to_rsize_conversion_factor[i] = [
            pow(amu2me, 0.5) * ang2br * pow(freqcm[i] * wn2eh, 0.5)
            for i in modes_included
        ]
    """

    # -------------------------------------------------------------------------

    # prepare the displaced/distored co-ordinates (the object we return)
    disp_coord = {}
    disp_coord.update({k: {} for k in linear_disp_keys})
    disp_coord.update({k: {} for k in bi_linear_disp_keys})

    # -------------------------------------------------------------------------
    # NEIL's mappings

    """ Note the indexing here!!
    For a system with 9 modes (and therefore 3 atoms, since Z * 3 = 9 = N_tot)
    there will be 9 frequencies `len(freqcm)` = 9
    So if `selected_mode_list` is [7, 8, 9]
    then `s_idx` will be [6, 7, 8]
    since `freqcm` is a length 9 array indexed at 0, `[6, 7, 8]` will return the 7th, 8th, 9th elements
    """
    s_idx = [i-1 for i in selected_mode_list]  # need to shift by 1 for 0-indexed arrays
    freq_array = freqcm[s_idx]  # freqcm[[6,7,8]] returns 7,8,9th freq values
    mode_array = nrmmod[:, s_idx]  # return 7,8,9th columns of Z*3 by Z*3 array, assume we return array
    atom_list = [*atmlst.values()]
    charge_list = [*chrglst.values()]

    # make a list for easy calculations
    ref_coord_array = np.array([*refcoord.values()])

    nof_surfaces = A  # alias
    nof_modes = N  # alias
    nof_atoms = Z  # alias

    NEW = np.newaxis  # alias

    if ((Z*3)**2 > 1e4):
        print("Maybe think about not precomputing? Check with Neil again?")
        breakpoint()
        import sys; sys.exit()
        # ---------------------------------------------------------------------
        # may want to consider indexing the array?

        # throw away the modes we don't need
        column_index = [j-1 for j in selected_mode_list]

        # anything whose dimensionality was N_tot we need to reduce
        # (throw away everything except the columns you needed)
        mode_array = np.array(mode_array[:, column_index])
        freq_array = np.array(freq_array[:, column_index])
        breakpoint()
        # ---------------------------------------------------------------------

    """ precomputing the bilinear makes a (ndim, nof_modes, nof_modes) sized numpy array
    for each of the 4 ++, +-, -+, -- bilinear keys.
    That might take too much memory... not sure?
    If it does then just disable this flag and compute the values inside the loop
    """
    precompute_bilinear = True
    # -------------------------------------------------------------------------

    def _preconvert_qsize_to_rsize(omega, q):
        """ Convert the reduced dimensionless q to the actual rsize in sqrt(amu)*Angs unit.
        Assumes that
            amu2me, ang2br, wn2eh
        are all constants imported from project_parameters.
        """
        R = q / (pow(amu2me, 0.5) * ang2br * pow(omega[:] * wn2eh, 0.5))
        return R

    def _precompute_linear_displacements(R_array, mode_array, reference, distored_coords):
        """
        `reference` is (Z*3, ) ~ x,y,and z coordinates for each atom
        `R_array` is assumed to be of dimension (N) ~ 1 value of displacement for all modes
        `mode_array` is assumed to be of dimension (Z*3, N)
        Z*3 == 9

        Use broadcasting.

        The first dimension iterates over the atoms and their xyz coordinates.
        The second dimension iterates over the normal modes.
        """
        Z, N = pp.Z, pp.N

        # the `:` of the second dimension of mode_array is what we index with i or j
        displacements = {
            "+1": reference[:, NEW] + 1.0 * R_array[NEW, :] * mode_array[:, :],
            "-1": reference[:, NEW] - 1.0 * R_array[NEW, :] * mode_array[:, :],
            "+2": reference[:, NEW] + 2.0 * R_array[NEW, :] * mode_array[:, :],
            "-2": reference[:, NEW] - 2.0 * R_array[NEW, :] * mode_array[:, :],
            #              (Z*3, 1)                 (1,  N)            (Z*3, N)
        }
        assert set(displacements.keys()) == set(linear_disp_keys), f"{linear_disp_keys=} no longer agree!"

        shape = (Z*3, N)
        for k in linear_disp_keys:
            assert displacements[k].shape == shape, f"{k=} {displacements[k].shape=} not {shape=}?"

        # store the displacements in the `distored_coords` dictionary
        for key in linear_disp_keys:
            distored_coords[key] = displacements[key]

        return  # don't need to return value, as `distored_coords` is a dictionary

    def _precompute_bilinear_displacements(R_array, mode_array, distored_coords):
        """
        `distored_coords` is assumed to be of dimension (Z*3, N)
        `R_array` is assumed to be of dimension (Z*3)
        `mode_array` is assumed to be of dimension (Z*3, N)
        Use broadcasting.

        The first dimension iterates over the atoms and their xyz coordinates.
        The second dimension iterates over the normal modes (i).
        The third dimension iterates over the normal modes (j).
        """
        Z, N = pp.Z, pp.N

        n = R_array.shape[0]
        assert n == mode_array.shape[1]

        displacements = {
            "++": distored_coords["+1"][:, :, NEW] + R_array[NEW, NEW, :] * mode_array[:, NEW, :],
            "+-": distored_coords["+1"][:, :, NEW] - R_array[NEW, NEW, :] * mode_array[:, NEW, :],
            "-+": distored_coords["-1"][:, :, NEW] + R_array[NEW, NEW, :] * mode_array[:, NEW, :],
            "--": distored_coords["-1"][:, :, NEW] - R_array[NEW, NEW, :] * mode_array[:, NEW, :],
            #                          (Z*3, N, 1)           (1,  1,   N)             (Z*3, 1, N)
        }
        assert set(displacements.keys()) == set(bi_linear_disp_keys), f"{bi_linear_disp_keys=} no longer agree!"

        shape = (Z*3, N, N)
        for k in bi_linear_disp_keys:
            assert displacements[k].shape == shape, f"{k=} {displacements[k].shape=} not {shape=}?"

        # store the displacements in the `distored_coords` dictionary
        for key in bi_linear_disp_keys:
            distored_coords[key] = displacements[key]

        return  # don't need to return value, as `distored_coords` is a dictionary

    def _save_distorted_structure(mode_idx, displaced_q, charge_list, atom_list, filename_list, key_list):
        """ save the distorted structure to the `distored_structure_filenames`
        `displaced_q` is an array of dimension (ndim, ndim)

        mode_idx can be (i, ) or (i, j, )
        so that
            d[(offset+0, *mode_idx)]
        is like
            d[a, i, j]
            or
            d[a, i]
        where the first index is picking the atom xyz
        and the second index is the first modes xyz
        and the third index is the second modex xyz
        """

        header, data = "{:<2s} {:} ", "{: .10f} " * 3
        template_string = header + data

        for key in key_list:
            file_contents = []
            d = displaced_q[key]
            for idx_atom in range(natoms):
                offset = 3*idx_atom  # 3 xyz-coordinates

                if False and len(mode_idx) > 1:
                    print(*mode_idx, d.shape); breakpoint()

                string = template_string.format(
                    atom_list[idx_atom], charge_list[idx_atom],
                    d[(offset+0, *mode_idx)],  # x component
                    d[(offset+1, *mode_idx)],  # y component
                    d[(offset+2, *mode_idx)],  # z component
                )
                file_contents.append(string)

                if False and __debug__:  # if you need to debug the string
                    print(string)

            if True and __debug__:  # if you need to debug the file_contents
                print(f"MODE: {str(mode_idx)}", *file_contents, sep='\n')
                # breakpoint()

            # write to file
            path = filename_list[key]
            with open(path, 'w') as fp:
                fp.write("\n".join(file_contents))

        return

    def _create_linear_diabatization_input_files(i, filename, qsize):
        """ this could be improved somewhat

        The `q1_label` goes from (1 -> nof_modes+1) rather than (0 -> nof_modes).
        """
        q1_label = pp.mode_map_dict[i]  # returns the label of the mode at the array's ith index
        refG_out = f"{filename}_refG.out"

        # Check if the reference geometry calculation is done?
        grace0 = subprocess_run_wrapper(["grep", "DONE WITH MP2 ENERGY", refG_out])
        ref_geom_flag_exists = bool(grace0.returncode == 0)

        for d1 in ['+', '-']:
            p_or_m = {'+': 'plus', '-': 'minus'}[d1]
            for suffix in ['', 'x2']:
                games_filename = f'{filename}_mode{q1_label}_{d1}{qsize}{suffix}'
                distored_struct_file = f'dist_structure_{p_or_m}{suffix}'

                shutil.copy('temp.inp', games_filename+'.inp')

                # if your going to do this why not just copy the file then append to it?
                # with open(games_inp_file, 'a') as inp_file:
                #     with open(distored_struct_file, 'r', errors='replace') as src_fp:
                #         inp_file.write(src_fp.read())
                #         inp_file.write(' $END')

                # so you only write to this file to then change another file?
                # but i guess its good to have a record of these files?
                #
                with open(distored_struct_file, 'r', errors='replace') as fp:
                    data = fp.read()

                with open(games_filename+'.inp', 'a') as fp:
                    fp.write(data)  # can you just do data + ' $END' in one write?
                    fp.write('\n $END')

                grace1 = subprocess_run_wrapper(["grep", "DONE WITH MP2 ENERGY", games_filename+'.out'])
                gamess_calculation_not_run = bool(grace1.returncode != 0)

                # This means that refG completed successfully and `diabmode*.out` not completed
                if (ref_geom_flag_exists and gamess_calculation_not_run) or pp.dry_run:
                    print(f"Running calculations for {games_filename}")
                    try:
                        os_system_wrapper("sbatch" + " " + my_subgam(games_filename+'.inp', ncpus=2, ngb=1, nhour=1))
                    except Exception as e:
                        print(f"Error running diabatization calculation: {str(e)}")
                else:
                    print(f"{games_filename} is done")

        return

    def _create_bilinear_diabatization_input_files(i, j, filename, qsize):
        """ this could be improved somewhat
        """
        q1_label = pp.mode_map_dict[i]  # returns the label of the mode at the array's i-th index
        q2_label = pp.mode_map_dict[j]  # returns the label of the mode at the array's j-th index

        refG_out = f"{filename}_refG.out"

        # Check if the reference geometry calculation is done?
        grace0 = subprocess_run_wrapper(["grep", "DONE WITH MP2 ENERGY", refG_out])
        ref_geom_flag_exists = bool(grace0.returncode == 0)

        for d1, d2 in it.product(['+', '-'], ['+', '-']):
            suffix = bi_linear_disp_suffix[d1+d2]

            games_filename = f'{filename}_mode{q1_label}_{d1}{qsize}_mode{q2_label}_{d2}{qsize}'
            distored_struct_file = f'dist_structure_{suffix}'

            shutil.copy('temp.inp', games_filename+'.inp')

            # so you only write to this file to then change another file?
            # but i guess its good to have a record of these files?
            with open(distored_struct_file, 'r', errors='replace') as fp:
                data = fp.read()

            with open(games_filename+'.inp', 'a') as fp:
                fp.write(data)  # can you just do data + ' $END' in one write?
                fp.write('\n $END')

            # Check if the calculation is done already
            grace2 = subprocess_run_wrapper(["grep", "DONE WITH MP2 ENERGY", games_filename + '.out'])
            gamess_calculation_not_run = bool(grace2.returncode != 0)

            # this will never work? grace0 is not defined
            if (ref_geom_flag_exists and gamess_calculation_not_run) or pp.dry_run:
                print(f"Running calculations for {games_filename}!")
                try:
                    os_system_wrapper("sbatch" + " " + my_subgam(games_filename+'.inp', ncpus=2, ngb=1, nhour=1))
                except Exception as e:
                    print(f"Error running diabatization calculation: {str(e)}")
            else:
                print(f"{games_filename} is already done.")

        return

    def _compute_bi_linear_displacements(i, j, R_array, mode_array, distored_coords):
        """
        The first dimension iterates over the atoms and their xyz coordinates
        The second dimension iterates over the normal modes
        """

        # the `:` elements are indexed by (c in range(1, ndim + 1))
        # the `:` of the second dimension of mode_array is what we index with j
        displacements = {  # numpy arrays of length `ndim`
            "++": distored_coords["+1"][:, i] + R_array[NEW, :] * mode_array[:, j],
            "+-": distored_coords["+1"][:, i] - R_array[NEW, :] * mode_array[:, j],
            "-+": distored_coords["-1"][:, i] + R_array[NEW, :] * mode_array[:, j],
            "--": distored_coords["-1"][:, i] - R_array[NEW, :] * mode_array[:, j],
        }

        for key in bi_linear_disp_keys:
            distored_coords[key] = displacements[key]

        return

    # -------------------------------------------------------------------------

    rsize = _preconvert_qsize_to_rsize(freq_array, qsize)

    # modify disp_coord in-place
    _precompute_linear_displacements(rsize, mode_array, ref_coord_array, disp_coord)

    # if precompute_bilinear:  # modify disp_coord in-place (may take a lot of memory?)
    _precompute_bilinear_displacements(rsize, mode_array, disp_coord)

    # Loop over modes (that you selected) and do linear displacements
    for i in range(N):

        _remove_existing_distorted_structure_files(linear_disp_filenames)
        index = (i, )
        _save_distorted_structure(
            index, disp_coord, charge_list, atom_list,
            linear_disp_filenames,
            linear_disp_keys
        )
        _create_linear_diabatization_input_files(i, filnam, qsize)

        # 2D distortion to get bilinear vibronic coupling
        for j in range(0, i):

            # if not precompute_bilinear:  # modify disp_coord in-place
            # _compute_bi_linear_displacements(i, j, rsize, mode_array, disp_coord)

            _remove_existing_distorted_structure_files(bi_linear_disp_filenames)
            # index = (i, j) if precompute_bilinear else (j, )
            index = (i, j)
            _save_distorted_structure(
                index, disp_coord, charge_list, atom_list,
                bi_linear_disp_filenames,
                bi_linear_disp_keys,
            )
            _create_bilinear_diabatization_input_files(i, j, filnam, qsize)

    return disp_coord


# ---------------------------------------------------------------------------------------
# Now we move on to extract vibronic coupling constants using finite difference
# and write the data in an mctdh operator file


def extract_ground_state_energy(hessout, pattern):
    try:
        command = f'grep "{pattern}" {hessout} | tail -1 | cut -c40-'
        result = subprocess_run_wrapper(command, shell=True, text=True, capture_output=True)
        output = float(result.stdout.strip().replace(" ", ""))
        return output
    except Exception as e:
        print("Cannot find ground state energy")
        return None


def _extract_energy_from_gamessoutput(file_path, pattern, column_specification_string, backup_line_idx):
    try:
        # Use subprocess.run with the direct command
        command = f'grep "{pattern}" "{file_path}" | {column_specification_string}'
        result = subprocess_run_wrapper(command, shell=True, text=True, capture_output=True)

        # If there is output, convert it to float
        try:
            output = float(result.stdout.strip().replace(" ", ""))
            return output
        except Exception as e:
            if False:  # try to find out reason for grep failing
                print("Grep failed?!")
                print(command)
                print("Please try grep command manually before proceeding")
                breakpoint()

            with open(file_path, 'r', errors='replace') as file:
                for line in reversed(file.readlines()):
                    match = re.search(pattern, line)
                    if match:
                        return float(line[backup_line_idx].strip().replace(" ", ""))

    except subprocess.CalledProcessError:
        # Return None if there is an error
        return None


def extract_in_Hartrees(file_path, pattern):
    """ This picks up the energy in Hartrees.

    Lines in the file might look like this:

        --- DIABATIC ENERGIES (DIAGONAL ELEMENT) ---       HARTREE            EV
        STATE #  1'S GMC-PT-LEVEL DIABATIC ENERGY=     -75.798270171       0.000000000
        STATE #  2'S GMC-PT-LEVEL DIABATIC ENERGY=     -75.708488402       2.443086361

    This function gets the numbers from the HARTREE column
    """
    column_specification_string = "tail -1 | cut -c44-61"
    backup_line_idx = slice(44, 62)  # equivalent to array[62:]
    return _extract_energy_from_gamessoutput(
        file_path, pattern,
        column_specification_string,
        backup_line_idx
    )


def extract_in_eV(file_path, pattern):
    """ This picks up the energy in eV.

    Lines in the file might look like this:

        --- DIABATIC ENERGIES (DIAGONAL ELEMENT) ---       HARTREE            EV
        STATE #  1'S GMC-PT-LEVEL DIABATIC ENERGY=     -75.798270171       0.000000000
        STATE #  2'S GMC-PT-LEVEL DIABATIC ENERGY=     -75.708488402       2.443086361

    This function gets the numbers from the EV column
    """
    column_specification_string = "tail -1 | cut -c62-"
    backup_line_idx = slice(62, None)  # equivalent to array[62:]
    return _extract_energy_from_gamessoutput(
        file_path, pattern,
        column_specification_string,
        backup_line_idx
    )


def refG_extract(file_path, pattern):
    """ This picks up the energy in eV. """
    return extract_in_eV(file_path, pattern)


def extract_diabatic_energy(file_path, pattern):
    """ This picks up the energy in Hartrees. """
    return extract_in_Hartrees(file_path, pattern)


def extract_coupling_energy(file_path, pattern):
    """ this picks up the energy in eV (same as refG_extract) """
    return extract_in_eV(file_path, pattern)


def find_nstate(file_path, pattern='# of states in CI      = '):
    with open(file_path, 'r', errors='replace') as file:
        for line in file:
            if pattern in line:
                return int(line.split('=')[1].strip())
    return None  # Return None if the pattern is not found


def extract_DSOME(fname, nof_states):

    start_pattern = "HSO MATRIX IN DIABATIC REPRESENTATION (DIRECT MAXIMIZATION)"
    end_pattern = 'SOC EIG. VALUES and VECTORS IN DIABATS (DIRECT MAX.)'

    sed_command = f"sed -n '/{start_pattern}/,/{end_pattern}/p' {fname}"
    result = subprocess_run_wrapper(sed_command, shell=True, text=True, capture_output=True)

    line_list = result.stdout.splitlines()
    # i believe there is another way to check if the result is empty?
    # I think the `result` object has error codes or some such?

    if isinstance(line_list, list) and line_list != []:
        selected_lines = result.stdout.splitlines()
    else:
        print('Cannot use sed to extract')
        selected_lines = extract_lines_between_patterns(  # fallback to slow pythonic extraction
            f'{fname}',
            f'{start_pattern}',
            f'{end_pattern}',
        )
        print(f'Using selected lines from {fname}, opened via python')

    DSOME_set = {}
    full_extracted_set = {}
    summed_set_real = {}
    summed_set_imag = {}
    append_J = {}

    for DSOMEline in selected_lines:
        if "STATE #" in DSOMEline:
            try:
                ist = DSOMEline[9:12].strip().replace(" ", "")
                jst = DSOMEline[14:16].strip().replace(" ", "")
                kst = ist + ' & ' + jst + ',' + DSOMEline[31:33]
                real = DSOMEline[48:61].strip().replace(" ", "")
                imaginary = DSOMEline[63:75].strip().replace(" ", "")

                if '*' in real:
                    real = 0
                if '*' in imaginary:
                    imaginary = 0

                DSOME_set[kst] = complex(float(real), float(imaginary))

            except Exception as e:
                print(f"Error processing line: {DSOMEline} - {e}")

    assert isinstance(nof_states, int), "can be removed after code is fully updated"

    # see hyperlink for a nice way to do combination loops
    # https://stackoverflow.com/questions/69321896/how-to-do-dependent-nested-loop-using-itertools-product
    # I also made the optional function `upper_triangle_loop_indices`
    for l_idx, r_idx in upper_triangle_loop_indices(nof_states, 2):

        for level_idx in range(1, 3):  # this should be replaced with array assignment
            full_extracted_set[l_idx, r_idx, level_idx] = DSOME_set[f'{l_idx} & {r_idx}, {level_idx}']

    if False:  # old approach
        real_sum = full_extracted_set[l_idx, r_idx, 1].real + full_extracted_set[l_idx, r_idx, 2].real
        summed_set_real[l_idx, r_idx] = real_sum

        imag_sum = full_extracted_set[l_idx, r_idx, 1].imag + full_extracted_set[l_idx, r_idx, 2].imag
        summed_set_imag[l_idx, r_idx] = imag_sum
    else:
        # can't we just add and then extract the real/imag components?
        new_number = full_extracted_set[l_idx, r_idx, 1] + full_extracted_set[l_idx, r_idx, 2]
        summed_set_real[l_idx, r_idx] = new_number.real
        summed_set_imag[l_idx, r_idx] = new_number.imag

    # how does this work??
    append_J[l_idx, r_idx] = complex(0, summed_set_imag[l_idx, r_idx])

    # return full_extracted_set, summed_set_real, summed_set_imag, append_J
    return [summed_set_real, summed_set_imag]


def mctdh(**kwargs):
    """ description of function """

    try:  # remove the previous file, as we are about to write to it
        subprocess_run_wrapper(['rm', '-f', 'mctdh.op'])
    except Exception as e:
        print(f"Error deleting {'mctdh.op'}: {str(e)}")
        breakpoint()

    # -------------------------------------------------------------------------
    suppress_zeros = True
    # extract necessary parameters
    nstate, nmodes = A, N

    ndim = kwargs.get('ndim')  # shouldn't need this anymore?
    freqcm = kwargs.get('freqcm')
    nrmmod = kwargs.get('nrmmod')

    s_idx = [i-1 for i in selected_mode_list]  # need to shift by 1 for 0-indexed arrays
    freq_array = freqcm[s_idx]  # assume we return the array
    # mode_array = nrmmod[:, s_idx]  # assume we return the array

    dipoles = kwargs.get('dipoles')
    diabatize = kwargs.get('diabatize')
    hessout = kwargs.get('hessout')

    # constants
    qsize = kwargs.get('qsize', 0.05)
    ha2ev = kwargs.get('ha2ev', 27.2113961318)
    wn2ev = kwargs.get('wn2ev', 0.000123981)

    # -------------------------------------------------------------------------
    # prepare various lists and dictionaries

    # prepare filenames
    zeroth_filename = f'{file_name}_refG.out'

    def _make_displacement_filenames():

        N = pp.N  # make explicit for linter
        linear_displacement_filenames = {}
        bilinear_displacement_filenames = {}

        for i in range(N):
            q1_label = pp.mode_map_dict[i]
            for key in linear_disp_keys:
                d1 = key[0]  # select plus or minus?
                suffix = {'1': '', '2': 'x2'}[key[1]]  # number of +1/+2/-1/-2 maps to suffix
                linear_displacement_filenames[(key, i)] = str(
                    f'{file_name}_mode{q1_label}_{d1}{qsize}{suffix}.out'
                )

        # the order j-before-i is important to match toby's
        # `_mode8_+0.05_mode7` (larger number on the left style)
        for i, j in upper_triangle_loop_indices(N, 2):
            # the labels are reversed because of the file names being lower triangle
            q1_label, q2_label = pp.mode_map_dict[j], pp.mode_map_dict[i]
            for d1, d2 in it.product(['+', '-'], ['+', '-']):

                key = d1+d2  # just in case
                assert key in bi_linear_disp_keys, f"{d1+d2=} is not in {bi_linear_disp_keys=}"

                bilinear_displacement_filenames[(key, i, j)] = str(
                   f'{file_name}_mode{q1_label}_{d1}{qsize}_mode{q2_label}_{d2}{qsize}.out'
                )
        return linear_displacement_filenames, bilinear_displacement_filenames

    linear_displacement_filenames, bilinear_displacement_filenames = _make_displacement_filenames()

    # for key, v in bilinear_displacement_filenames.items():
    #     print(key,  v)
    # breakpoint()

    # -------------------------------------------------------------------------
    # bad practice, works for now and we can refactor once we've finished figuring out the end product
    format_string = "{label:<25s}={value:>-15.6f}{units:>8s}\n"
    make_line = functools.partial(format_string.format, units=", ev")

    def build_op_section(job_title):
        """Returns a string which defines the `OP_DEFINE-SECTION` of an .op file"""
        start_op, end_op = "OP_DEFINE-SECTION", "end-op_define-section"
        start_title, end_title = "title", "end-title"
        return '\n'.join([
            start_op,
            start_title,
            f"{job_title:s}",
            end_title,
            end_op,
        ])

    # ---------------------------------------------

    def build_frequencies(frequencies):
        """Return a string containing the frequency information of a .op file."""
        return ''.join([
            make_line(label=f"w{i+1:0>2d}", value=w)
            # make_line(label=f"w{mode_map_dict[i]:0>2d}", value=w)
            for i, w in enumerate(frequencies)
        ])

    def _incasedebug_E0(E0_array):
        """Return a string containing the energy information of a .op file.
        Has extra code for debugging
        """
        assert False, "only use for debug"

        def one_block_column_aligned():
            # iterates over columns first
            return ''.join([
                make_line(label=f"EH_s{row+1:0>2d}_s{col+1:0>2d}", value=E0_array[row, col])
                for col in range(A)
                for row in range(0, col+1)
                # if not np.isclose(E0_array[row, col], 0.0)  # if you don't want to print the zeros;
            ])

        def one_block_row_aligned():
            # iterates over rows first
            return ''.join([
                make_line(label=f"EH_s{row+1:0>2d}_s{col+1:0>2d}", value=E0_array[row, col])
                for row in range(A)
                for col in range(row, A)
                # if not np.isclose(E0_array[row, col], 0.0)  # if you don't want to print the zeros;
            ])

        def two_blocks():
            diag_block = ''.join([
                make_line(label=f"EH_s{a+1:0>2d}_s{a+1:0>2d}", value=E0_array[a, a])
                for a in range(A)
                # if not np.isclose(E0_array[row, col], 0.0)  # if you don't want to print the zeros;
            ])
            # iterates over columns first (upper triangle)
            off_diag_block = ''.join([
                make_line(label=f"EH_s{row+1:0>2d}_s{col+1:0>2d}", value=E0_array[row, col])
                for row, col in upper_triangle_loop_indices(A, 2)
                # if not np.isclose(E0_array[row, col], 0.0)  # if you don't want to print the zeros;
            ])
            return diag_block + "\n" + off_diag_block

        # many possible methods
        if False:  # to compare methods turn to True
            s = one_block_column_aligned()
            print('one block, column aligned', s, sep='\n')

            s = one_block_row_aligned()
            print('one block, row aligned', s, sep='\n')

            # I think two blocks looks better personally
            s = two_blocks()
            print('two blocks', s, sep='\n')
            breakpoint()

        return two_blocks()

    def build_E0(E0_array):
        """Return a string containing the energy information of a .op file."""

        diag_block = ''.join([
            make_line(label=f"EH_s{a+1:0>2d}_s{a+1:0>2d}", value=E0_array[a, a])
            for a in range(A)
            if not suppress_zeros or not np.isclose(E0_array[a, a], 0.0)  # if you don't want to print the zeros;
        ])

        # iterates over columns first (upper triangle)
        off_diag_block = ''.join([
            make_line(label=f"EH_s{row+1:0>2d}_s{col+1:0>2d}", value=E0_array[row, col])
            for row, col in upper_triangle_loop_indices(A, 2)
            if not suppress_zeros or not np.isclose(E0_array[row, col], 0.0)  # if you don't want to print the zeros;
        ])
        return diag_block + "\n" + off_diag_block

    def build_electronic_moments(dipoles_dict):
        """ Returns a string containing electronic transition dipole moments
            that will be written to a .op file. Takes in dipoles from extract_etdm

            We label both states using the key in the `dipoles_dict` FOR NOW (may change later)
            By default all values in *.op files are in atomic units (au) but we want to explicitly label them
            for clarity.
        """
        make_line_au = functools.partial(format_string.format, units=", au")

        def make_xyz_blocks():
            block = ""
            """ Write the xyz component of each excitation as a single block """
            for key in dipoles_dict.keys():
                src, dst = key[0], key[1]  # the #'s identifying the states between which the excitation is occuring
                block += "".join([
                    make_line_au(label=f"E{op}_s{src:>02d}_s{dst:>02d}", value=dipoles_dict[key][xyz_idx])
                    for xyz_idx, op in enumerate(['x', 'y', 'z'])
                    # always print all transition dipole moments out even if zero
                ]) + "\n"

            return block

        def make_state_blocks():
            """ Write all Ex transitions as one block, then repeat with Ey, and then Ez"""
            block = ""
            for xyz_idx, op in enumerate(['x', 'y', 'z']):
                for key in dipoles_dict.keys():
                    src, dst = key[0], key[1]  # the #'s identifying the states between which the excitation is occuring
                    block += "".join([
                        make_line_au(label=f"E{op}_s{src:>02d}_s{dst:>02d}", value=dipoles_dict[key][xyz_idx])
                        # always print all transition dipole moments out even if zero
                    ])
                block += "\n"

            return block

        # just-in-case
        for key in dipoles_dict.keys():  # all keys are length 2 tuples
            assert isinstance(key, tuple) and len(key) == 2

        if True:  # xyz_blocks
            block = make_xyz_blocks()
        else:
            block = make_state_blocks()

        return block

    def build_magnetic_moments():
        raise Exception("Function not implemented yet")

    def build_linear_coupling(lin_dict, A, N):
        """Return a string containing the linear coupling constant information of a .op file.
        `lin_dict` is a dictionary
        for a `selected_mode_list = [7, 8, 9]`
            mode_map_dict[0] = 7
        and so
            lin_dict[mode_map_dict[0]]
        will return the array associated with the key `7`
        Thus
            lin_dict[i][a, a]
        is `lin_dict[i]` returning an array `x`
        and that array is indexed like so: `x[a, a]`
        """

        # make ordered-list of arrays stored in `lin_dict`
        assert len(lin_dict.keys()) == N
        linear = [lin_dict[mode_map_dict[i]] for i in range(N)]

        return '\n'.join([
            ''.join([
                make_line(
                    label=f"C1_s{a+1:0>2d}_s{a+1:0>2d}_v{i+1:0>2d}",
                    value=linear[i][a, a]
                )
                for a, i in it.product(range(A), range(N))
                if not suppress_zeros or not np.isclose(linear[i][a, a], 0.0)
            ]),
            ''.join([
                make_line(
                    label=f"C1_s{a2+1:0>2d}_s{a1+1:0>2d}_v{i+1:0>2d}",
                    value=linear[i][a2, a1]
                )
                for a1, a2, i in it.product(range(A), range(A), range(N))
                if a1 != a2
                and (not suppress_zeros or not np.isclose(linear[i][a2, a1], 0.0))
            ]),
        ])

    def build_quadratic_coupling(quad_dict, A, N):
        """Return a string containing the quadratic coupling constant information of a .op file."""

        # make ordered-list of arrays stored in `lin_data`
        assert len(quad_dict.keys()) == N
        quad = [quad_dict[mode_map_dict[i]] for i in range(N)]

        return '\n'.join([
            ''.join([
                make_line(
                    label=f"C2_s{a+1:0>2d}s{a+1:0>2d}_v{i+1:0>2d}v{i+1:0>2d}",
                    value=quad[i][a, a]
                )
                for a, i in it.product(range(A), range(N))
                if not np.isclose(quad[i][a, a], 0.0)
            ]),
            ''.join([
                make_line(
                    label=f"C2_s{a1+1:0>2d}s{a2+1:0>2d}_v{i+1:0>2d}v{i+1:0>2d}",
                    value=quad[i][a1, a2]
                )
                for a1, a2, i in it.product(range(A), range(A), range(N))
                if (a1 < a2)
                and (not suppress_zeros or not np.isclose(quad[i][a2, a1], 0.0))
            ]),
        ])

    def build_bilinear_coupling(bi_lin_dict, A, N):
        """Return a string containing the BI-Linear coupling constant information of a .op file.

        We first make a new dictionary whose keys are  0-indexed (0, 1) based on `selected_mode_list`.

        So if `bi_lin_dict` has keys
            (7, 8)
        then `bi_lin` has the same values for a corresponding key
            (0, 1)
        """

        bi_lin = {}
        for key in bi_lin_dict.keys():
            new_key = (
                selected_mode_list.index(key[0]),
                selected_mode_list.index(key[1])
            )
            bi_lin[new_key] = bi_lin_dict[key]

        return '\n'.join([
            ''.join([
                make_line(
                    label=f"C1_s{a+1:0>2d}s{a+1:0>2d}_v{j1+1:0>2d}v{j2+1:0>2d}",
                    # value=0.0
                    value=bi_lin[(j1, j2)][a, a]
                )
                for a, j1, j2 in it.product(range(A), range(N), range(N))
                if (j1 < j2)
                and (not suppress_zeros or not np.isclose(bi_lin[(j1, j2)][a, a], 0.0))
            ]),
            ''.join([
                make_line(
                    label=f"C1_s{a1+1:0>2d}s{a2+1:0>2d}_v{j1+1:0>2d}v{j2+1:0>2d}",
                    # value=0.0
                    value=bi_lin[(j1, j2)][a1, a2]
                )
                for a1, a2, j1, j2 in it.product(range(A), range(A), range(N), range(N))
                if (a1 < a2) and (j1 < j2)
                and (not suppress_zeros or not np.isclose(bi_lin[(j1, j2)][a1, a2], 0.0))
            ]),
        ])

    def _SOC_Somehwere():
        # ------------------------------------------------------------
        # some SOC stuff that could be moved elsewhere?
        SOC_check = subprocess_run_wrapper(['grep', "(DIRECT MAX.)", zeroth_filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        SOC_flag = SOC_check.returncode == 0

        if SOC_flag:
            # Extract DSOME_cm_0
            DSOME_cm_0 = extract_DSOME(zeroth_filename, nstate)
            DSOME_cm_0_real, DSOME_cm_0_imag = DSOME_cm_0[0], DSOME_cm_0[1]
        # ------------------------------------------------------------
        return

    heading, params = [], []
    EH, SOC, linear, quadratic, bilinear = [], [], [], [], []

    displacement_keys = ["+1", "+2", "-1", "-2"]

    format_string = "{label:<25s}={value:>-15.9f}{units:>8s}\n"
    make_line = functools.partial(format_string.format, units=", ev")

    spacer_format_string = f"# {'-':^60s} #\n"
    hfs = header_format_string = "# {:^60s} #\n" + spacer_format_string

    linear.append(hfs.format('Linear Coupling Constants'))
    quadratic.append(hfs.format('Quadratic Coupling Constants'))
    bilinear.append(hfs.format('Bilinear Coupling Constants'))

    def extract_E0(hessout, A=pp.A):
        """ The energy values associated with the reference geometry.
        These energies don't depend on the modes
        """

        # strings used by `grep` to locate values to extract
        a_pattern = 'STATE #.* {col}.S GMC-PT-LEVEL DIABATIC ENERGY='
        ba_pattern = 'STATE #.* {row} &.* {col}.S GMC-PT-LEVEL COUPLING'

        # ground state of the (optimized geometry?) (includes fictitious surface? no/yes?)
        GSE_pattern = 'TOTAL ENERGY ='
        GSE = extract_ground_state_energy(hessout, GSE_pattern)

        # 1st diabat's energy
        D1E = extract_diabatic_energy(zeroth_filename, a_pattern.format(col=1))
        linear_shift = (D1E - GSE) * ha2ev
        print(
            f'The ground state energy is: {GSE} Hartree\n'
            f'Diabat #1 energy is: {D1E} Hartree\n'
            f'Linear shift value: {linear_shift} eV\n'
        )

        # A = pp.A + 1  # +1 for ground state's as fictitious first row/col
        A = pp.A  #?
        shape = (A, A)
        E0_array = np.zeros(shape)

        if False:  # debug
            def _reminder_produce_upper_triangle_indices(s):
                """ Assume a square matrix of shape (s, s).
                Prints the row, col indices that would index the upper triangle
                Just reminder code.
                """
                print("Indices using it.combinations")
                for row, col in it.combinations(range(s), 2):
                    print(f"{row=} {col=}")

                # this is just a wrapper for it.combinations
                for row, col in upper_triangle_loop_indices(s, 2):
                    print(f"{row=} {col=}")

                print("Indices using nested loops")
                for col in range(s):
                    for row in range(0, col):
                        print(f"{row=} {col=}")

                print("Indices assuming we start at 1")
                # assume indices start at 1
                for col in range(1, s+1):
                    for row in range(1, col):
                        print(f"{row=} {col=}")
                return

            _reminder_produce_upper_triangle_indices(A)
            breakpoint()

        if False:  # matches the bash style from Toby
            for a in range(A):
                E0_array[a, a] = refG_extract(zeroth_filename, a_pattern.format(col=a+1))
                E0_array[a, a] += linear_shift
                for b in range(a):
                    E0_array[b, a] = refG_extract(zeroth_filename, ba_pattern.format(row=b+1, col=a+1))
            # print(E0_array)

        if True:  # this makes more sense based on what I see in the file
            for a in range(A):
                E0_array[a, a] = extract_in_eV(zeroth_filename, a_pattern.format(col=a+1))
                E0_array[a, a] += linear_shift

            for a, b in upper_triangle_loop_indices(A, 2):
                E0_array[a, b] = extract_in_eV(zeroth_filename, ba_pattern.format(row=a+1, col=b+1))
            # for row, col in upper_triangle_loop_indices(A, 2):
            #     E0_array[row, col] = extract_in_eV(zeroth_filename, ba_pattern.format(row=row+1, col=col+1))
            # print(E0_array)

        if False:  # debug outputs (keep them out of the loops above for simplicity)
            for a in range(A):
                print(f"Diabatic energy at state {a+1}: {E0_array[a, a]}")
            for a, b in upper_triangle_loop_indices(A, 2):
                print(f"Coupling energy at state {a+1} & {b+1}: {E0_array[a, b]}")
            # for row, col in upper_triangle_loop_indices(A, 2):
            #     print(f"Coupling energy at state {row+1} & {col+1}: {E0_array[row, col]}")
            print(E0_array)

        # added at the last minute
        E0_array_ev = E0_array
        E0_array_au = np.zeros(shape)

        # now also get the array in atomic units (Hartrees)
        for a in range(A):
            E0_array_au[a, a] = extract_in_Hartrees(zeroth_filename, a_pattern.format(col=a+1))

        for a, b in upper_triangle_loop_indices(A, 2):
            E0_array_au[a, b] = extract_in_Hartrees(zeroth_filename, ba_pattern.format(row=a+1, col=b+1))

        return E0_array_ev, E0_array_au

    def extract_energies_benny():

        for kmode in range(N):  # kmode is array index of selected_mode_list
            imode = pp.mode_map_dict[kmode] #

            displacement_filenames = {
                "+1": f'{filnam}_mode{imode}_+{qsize}.out',
                "+2": f'{filnam}_mode{imode}_+{qsize}x2.out',
                "-1": f'{filnam}_mode{imode}_-{qsize}.out',
                "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
            }

            vibron_ev = freqcm[imode-1] * wn2ev
            params.append(make_line(label=f"w{imode:>02d}", value=vibron_ev))
            # params.append("\n")
            # Coupling.append("#Linear and quadratic diagonal and off-diagonal vibronic coupling constants:\n")

            grace_code = {}
            for key in displacement_keys:
                grace_code[key] = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", displacement_filenames[key]])

            """ either of these work (logic wise)
                if any(code != 0 for code in grace_code.values()):
                if not all(code == 0 for code in grace_code.values()):
            """

            if not all(code == 0 for code in grace_code.values()):
                params.append(f"not good to extract. Skipping mode {imode} for extracting vibronic couplings\n")

            else:  # otherwise we're good to extract
                print("\n good to extract\n")
                # Extract the diagonal and off-diagonal vibronic coupling
                for ist in range(1, nstate + 1):

                    def _make_diag_lin_quad(i):
                        pattern = f'STATE #.* {i}.S GMC-PT-LEVEL DIABATIC ENERGY='

                        # Ediab_au = [extract_diabatic_energy(displacement_filenames[kmode][k], pattern) for k in displacement keys]  $ one liner list comprehension
                        # Ediab_au = {k: extract_diabatic_energy(displacement_filenames[kmode][k], pattern) for k in displacement keys}  # one liner dictionary comprehension
                        Ediab_au = {}
                        for key in displacement_keys:
                            Ediab_au[key] = extract_diabatic_energy(displacement_filenames[key], pattern)

                        # Extract Ediab_au_0
                        Ediab_au_0 = extract_diabatic_energy(zeroth_filename, pattern)
                        linear_diag_ev = (Ediab_au["+1"] - Ediab_au["-1"]) * ha2ev / (2 * qsize)
                        quadratic_diag_ev = (Ediab_au["+2"] + Ediab_au["-2"] - 2.0 * Ediab_au_0) * ha2ev / (4.0 * qsize * qsize)

                        # We only view the difference between the actual force constant and the vibron
                        # as the quadratic diagonal coupling for the diabatic state.
                        quadratic_diag_ev = quadratic_diag_ev - vibron_ev

                        # Print and store results
                        print(f"State {i} Linear Diagonal: {linear_diag_ev} Quadratic Diagonal: {quadratic_diag_ev}, ev\n")

                        # machine accuracy is typically 16 digits
                        s1 = make_line(label=f"C1_s{i:>02d}_s{i:>02d}_v{imode:>02d}", value=linear_diag_ev)
                        s2 = make_line(label=f"C2_s{i:>02d}s{i:>02d}_v{imode:>02d}v{imode:>02d}", value=quadratic_diag_ev)
                        return s1, s2

                    s1, s2 = _make_diag_lin_quad(ist)
                    linear.append(s1)
                    quadratic.append(s2)

                    # # Loop over jst
                    jlast = ist - 1
                    for jst in range(1, jlast + 1):

                        def _make_offdiag_lin_quad(i, j):
                            pattern = f'STATE #.* {j} &.* {i}.S GMC-PT-LEVEL COUPLING'

                            # Extract Coup_ev_0
                            Coup_ev_0 = extract_coupling_energy(zeroth_filename, pattern)

                            Coup_ev = {}
                            for key in displacement_keys:
                                Coup_ev[key] = extract_diabatic_energy(displacement_filenames[key], pattern)

                            # Compute linear off-diagonal coupling
                            linear_offdiag_ev = (Coup_ev["+1"] - Coup_ev["-1"]) / (2 * qsize)
                            # Compute quadratic off-diagonal coupling
                            quadratic_offdiag_ev = (Coup_ev["+2"] + Coup_ev["-2"] - 2.0 * Coup_ev_0) / (4.0 * qsize * qsize)

                            # Print and store results
                            print(f"State {j} & {i} Linear Off-Diagonal: {linear_offdiag_ev}\n")
                            print(f"State {j} & {i} Quadratic Off-Diagonal: {quadratic_offdiag_ev}\n")
                            s1 = make_line(label=f"C1_s{j:>02d}_s{i:>02d}_v{imode:>02d}", value=linear_offdiag_ev)
                            s2 = make_line(label=f"C2_s{j:>02d}s{i:>02d}_v{imode:>02d}v{imode:>02d}", value=quadratic_offdiag_ev)
                            return s1, s2

                        s1, s2 = _make_diag_lin_quad(ist)
                        linear.append(s1)
                        quadratic.append(s2)

                        """ this is just representative (you can delete - just for learning purposes)
                        if False: # don't actually try to do right now
                            order_name = {1: 'Linear', 2: 'Quadratic'}
                            for i in [1, 2]:
                                _number = [linear_offdiag_ev, quadratic_offdiag_ev][i]
                                print(f"State {jst} & {ist} {order_name[i]} Off-Diagonal: {_number}\n")
                                oprder_list[i].append(make_line(label=f"C{i}_s{jst:>02d}_s{ist:>02d}_v{imode:>02d}", value=_number))
                        """

            # Extracting bilinear vibronic coupling
            # Coupling.append("#Bilinear diagonal and off-diagonal vibronic coupling constants:\n")

            for lmode in range(0, kmode):
                jmode = pp.mode_map_dict[lmode]
                breakpoint()

                bi_linear_displacement_filenames = {
                    "++": f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_+{qsize}.out',
                    "+-": f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_-{qsize}.out',
                    "-+": f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_+{qsize}.out',
                    "--": f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_-{qsize}.out',
                }

                grace_code_pp = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", f"{filnam}_mode{imode}_+{qsize}_mode{jmode}_+{qsize}.out"])
                grace_code_pm = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", f"{filnam}_mode{imode}_+{qsize}_mode{jmode}_-{qsize}.out"])
                grace_code_mp = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", f"{filnam}_mode{imode}_-{qsize}_mode{jmode}_+{qsize}.out"])
                grace_code_mm = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", f"{filnam}_mode{imode}_-{qsize}_mode{jmode}_-{qsize}.out"])

                if all(code == 0 for code in [grace_code_pp, grace_code_pm, grace_code_mp, grace_code_mm]):
                    print(f"\n Good to extract bilinear for modes {imode} {jmode} \n")
                    for ist in range(1, nstate + 1):
                        pattern = f'STATE #.* {ist}.S GMC-PT-LEVEL DIABATIC ENERGY='

                        # do this style again?
                        # big_displacement_keys = ['++', '+-', '-+', '--']
                        # Ediab_au = {}
                        # for key in displacement_keys:
                        #     Ediab_au[key] = extract_diabatic_energy(big_displacement_filenames[key], pattern)


                        # Extract Ediab_au_pp
                        Ediab_au_pp = extract_diabatic_energy(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_+{qsize}.out', pattern)

                        # Extract Ediab_au_pm
                        Ediab_au_pm = extract_diabatic_energy(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_-{qsize}.out', pattern)

                        # Extract Ediab_au_mp
                        Ediab_au_mp = extract_diabatic_energy(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_+{qsize}.out', pattern)

                        # Extract Ediab_au_mm
                        Ediab_au_mm = extract_diabatic_energy(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_-{qsize}.out', pattern)

                        bilinear_diag_ev = (Ediab_au_pp + Ediab_au_mm - Ediab_au_pm - Ediab_au_mp ) * ha2ev / (4.0 * qsize * qsize )

                        print(f"State {ist} Bilinear Diagonal: {bilinear_diag_ev}\n")
                        bilinear.append(make_line(label=f"C1_s{ist:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}", value=bilinear_diag_ev))

                        # # Loop over jst
                        jlast = ist - 1
                        for jst in range(1, jlast + 1):
                            pattern = f'STATE #.* {jst} &.* {ist}.S GMC-PT-LEVEL COUPLING'
                            # Extract Coup_ev_pp
                            Coup_ev_pp = extract_coupling_energy(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_+{qsize}.out', pattern)
                            # Extract Coup_ev_pm
                            Coup_ev_pm = extract_coupling_energy(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_-{qsize}.out', pattern)

                            # Extract Coup_ev_mp
                            Coup_ev_mp = extract_coupling_energy(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_+{qsize}.out', pattern)

                            # Extract Coup_ev_mm
                            Coup_ev_mm = extract_coupling_energy(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_-{qsize}.out', pattern)

                            bilinear_offdiag_ev = ( Coup_ev_pp + Coup_ev_mm - Coup_ev_pm - Coup_ev_mp ) / (4.0 * qsize * qsize )

                            print(f"State {jst} & {ist} Bilinear Off-Diagonal: {bilinear_offdiag_ev}\n")
                            bilinear.append(make_line(label=f"C1_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}", value=bilinear_offdiag_ev))

                            if SOC_flag:

                                try:

                                    # Extract DSOME_cm_pp
                                    DSOME_cm_pp = extract_DSOME(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_+{qsize}.out', nstate)
                                    DSOME_cm_pp_real, DSOME_cm_pp_imag = DSOME_cm_pp[0], DSOME_cm_pp[1]

                                    # Extract DSOME_cm_pm
                                    DSOME_cm_pm = extract_DSOME(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_-{qsize}.out', nstate)
                                    DSOME_cm_pm_real, DSOME_cm_pm_imag = DSOME_cm_pm[0], DSOME_cm_pm[1]

                                    # Extract DSOME_cm_mp
                                    DSOME_cm_mp = extract_DSOME(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_+{qsize}.out', nstate)
                                    DSOME_cm_mp_real, DSOME_cm_mp_imag = DSOME_cm_mp[0], DSOME_cm_mp[1]

                                    # Extract DSOME_cm_mm
                                    DSOME_cm_mm = extract_DSOME(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_-{qsize}.out', nstate)
                                    DSOME_cm_mm_real, DSOME_cm_mm_imag = DSOME_cm_mm[0], DSOME_cm_mm[1]


                                except Exception as e:
                                    print(f"Error in SOC: {str(e)}")
                else:
                    print(f"not good to extract. Skipping mode {imode} mode {jmode} for extracting bilinear vibronic couplings")

    def extract_etdm(file_path, verbose=True):
        """ Extracts the electronic transition dipole moments from refG.out
            It will extract tdm from diabat 1 -> diabat 2,3,...
            Returns dipoles, a dictionary of tdm values, columns are x,y,z

            e.g. {2: ('-0.000000', '0.182262', '0.000000'),
                  3: ('-0.000000', '0.000000', '0.000000')}
        """
        def extract_ground_to_excited_state_transition_dipoles(selected_lines):
            """ x """
            dipoles = {}

            for line in selected_lines:
                try:
                    state, pair, x, y, z = line.strip().split()
                    state, pair = int(state), int(pair)
                    if pair == state:  # transition from the fictitious ground state (0) -> to `state` #
                        pair = 0
                    dipoles[(pair, state)] = [float(x), float(y), float(z)]

                except Exception as e:
                    print(f"Error processing line: {line} - {e}")
                    breakpoint()

            return dipoles

        tdipole_block = extract_lines_between_patterns(
            file_path,
            "TRANSITION DIPOLES BETWEEN DIABATS",
            "TRANSITION DIPOLES BETWEEN DIRECT MAX. DIABATS"
        )

        selected_lines = [  # remove all '\n' and blank lines
            line.strip() for line in tdipole_block
            if "#" not in line and line.strip() != ""
        ]

        selected_lines = selected_lines[2:]  # skip the 2 headers as shown below
        """     TRANSITION DIPOLES BETWEEN DIABATS (in A.U.):
                STATE PAIR      X         Y         Z               """

        dipoles = extract_ground_to_excited_state_transition_dipoles(selected_lines)

        if verbose and __debug__:
            pprint.pprint(tdipole_block)
            pprint.pprint(dipoles)

        return dipoles

    def extract_linear(array_style=True):
        """
        For some reason the diagonal (of linear and quadratic) needs to be in Hartrees???
        and the off-diagaonal in eV??

        """
        linear_dictionary = {}

        # strings used by `grep` to locate values to extract
        a_pattern = 'STATE #.* {col}.S GMC-PT-LEVEL DIABATIC ENERGY='
        ba_pattern = 'STATE #.* {row} &.* {col}.S GMC-PT-LEVEL COUPLING'

        shape = (A, A)

        def extract_energy_at_displaced_geometry(path, key):
            """ x """
            array = np.zeros(shape)

            for a in range(A):
                array[a, a] = extract_in_Hartrees(path, a_pattern.format(col=a+1))

            for a, b in upper_triangle_loop_indices(A, 2):
                array[a, b] = extract_in_eV(path, ba_pattern.format(row=a+1, col=b+1))

            if False:  # debug printing
                for a in range(A):
                    print(f"Linear energy {key=} at state {a+1}: {array[a, a]}")
                for a, b in upper_triangle_loop_indices(A, 2):
                    print(f"Linear energy {key=} at state {a+1} & {b+1}: {array[a, b]}")
                print(path); print(array); breakpoint()  # debug

            return array
        #
        for i in range(N):
            temp_dict = {}  # stores temporary arrays (they are different every single i \in N loop)
            for key in ["+1", "-1"]:
                path = linear_displacement_filenames[(key, i)]
                temp_dict[key] = extract_energy_at_displaced_geometry(path, key)

                # temp_dict[key] = np.random.rand(*shape)
                # # set lower triangle to zero
                # for i, j in upper_triangle_loop_indices(N, 2):
                #     temp_dict[key][j, i] = 0.0

                # breakpoint()
            if array_style:
                linear_ev = (temp_dict["+1"] - temp_dict["-1"]) / (2*qsize)
                for a in range(A):  # make sure we multiply the diagonal by ha2ev
                    linear_ev[a, a] *= ha2ev
                if False: print(linear_ev); breakpoint()  # debug

            else:  # do it with loops
                linear_ev = np.zeros(shape)
                for a in range(A):
                    linear_ev[a, a] = (temp_dict["+1"][a, a] - temp_dict["-1"][a, a]) * ha2ev / (2 * qsize)
                    for b in range(a):
                        linear_ev[b, a] = (temp_dict["+1"][b, a] - temp_dict["-1"][b, a]) / (2 * qsize)
                if False: print(linear_ev); breakpoint()  # debug

            linear_dictionary[mode_map_dict[i]] = linear_ev

        return linear_dictionary

    def extract_quadratic(E0_array_eV, E0_array_au, vibron_ev, array_style=False):

        quadratic_dictionary = {}

        # strings used by `grep` to locate values to extract
        a_pattern = 'STATE #.* {col}.S GMC-PT-LEVEL DIABATIC ENERGY='
        ba_pattern = 'STATE #.* {row} &.* {col}.S GMC-PT-LEVEL COUPLING'
        shape = (A, A)

        def extract_energy_at_displaced_geometry(path, key):
            """ x """
            array = np.zeros(shape)

            for a in range(A):
                array[a, a] = extract_in_Hartrees(path, a_pattern.format(col=a+1))

            for a, b in upper_triangle_loop_indices(A, 2):
                array[a, b] = extract_in_eV(path, ba_pattern.format(row=a+1, col=b+1))

            if False and __debug__:  # debug printing
                for a in range(A):
                    print(f"Quadratic energy {key=} at state {a+1}: {array[a, a]}")
                for a, b in upper_triangle_loop_indices(A, 2):
                    print(f"Quadratic energy {key=} at state {a+1} & {b+1}: {array[a, b]}")
                print(path); print(array); breakpoint()  # debug

            return array

        def _compute_using_array_style(i, temp_dict):
            # until we change the extraction
            temp_fake_E0_array = np.copy(E0_array_eV)
            for a in range(A):  # make sure the diagonal is in Hartrees
                temp_fake_E0_array[a, a] = E0_array_au[a, a]
            #
            quad_ev = temp_dict["+2"] + temp_dict["-2"] - 2.0 * temp_fake_E0_array
            for a in range(A):  # make sure we multiply the diagonal by ha2ev
                quad_ev[a, a] *= ha2ev

            quad_ev /= (2. * qsize) ** 2
            for a in range(A):  # make sure we subtract the vibron_ev on the diagonal
                quad_ev[a, a] -= vibron_ev[i]

            return quad_ev

        def _compute_using_forloop_style(i, temp_dict):
            quad_ev = np.zeros(shape)
            for a in range(A):
                quad_ev[a, a] = temp_dict["+2"][a, a] + temp_dict["-2"][a, a]
                quad_ev[a, a] -= 2.0 * E0_array_au[a, a]
                quad_ev[a, a] *= ha2ev  # convert back to eV's  (only for the diagonal)
                quad_ev[a, a] /= (2. * qsize) ** 2  # or equivalently: (4.0 * qsize * qsize)
                quad_ev[a, a] -= vibron_ev[i]
                for b in range(a):
                    quad_ev[b, a] = temp_dict["+2"][b, a] + temp_dict["-2"][b, a]
                    quad_ev[b, a] -= 2.0 * E0_array_eV[b, a]
                    quad_ev[b, a] /= (2. * qsize) ** 2   # or equivalently: (4.0 * qsize * qsize)

            return quad_ev

        for i in range(N):

            temp_dict = {}  # stores temporary arrays (they are different every single i \in N loop)
            for key in ["+2", "-2"]:
                path = linear_displacement_filenames[(key, i)]
                temp_dict[key] = extract_energy_at_displaced_geometry(path, key)
            if False and __debug__: print(temp_dict["+2"], '\n', temp_dict["-2"]); breakpoint()

            if not array_style: # do it with for loops
                quad_ev = _compute_using_forloop_style(i, temp_dict)
                if False and __debug__: print(i, quad_ev, vibron_ev); breakpoint()
            else:
                quad_ev = _compute_using_array_style(i, temp_dict)
                if False and __debug__: print(quad_ev); breakpoint()

            quadratic_dictionary[mode_map_dict[i]] = quad_ev

        return quadratic_dictionary

    def extract_bilinear(array_style=False):

        bilinear_dictionary = {}

        # strings used by `grep` to locate values to extract
        a_pattern = 'STATE #.* {col}.S GMC-PT-LEVEL DIABATIC ENERGY='
        ba_pattern = 'STATE #.* {row} &.* {col}.S GMC-PT-LEVEL COUPLING'
        A, N = pp.A, pp.N  # stop flake8 from complaining
        shape = (A, A)

        def extract_energy_at_displaced_geometry(path, key):
            """ x """
            array = np.zeros(shape)

            for a in range(A):
                array[a, a] = extract_in_Hartrees(path, a_pattern.format(col=a+1))

            for a, b in upper_triangle_loop_indices(A, 2):
                array[a, b] = extract_in_eV(path, ba_pattern.format(row=a+1, col=b+1))

            if False and __debug__:  # debug printing
                for a in range(A):
                    print(f"Bilinear energy {key=} at state {a+1}: {array[a, a]}")
                for a, b in upper_triangle_loop_indices(A, 2):
                    print(f"Bilinear energy {key=} at state {a+1} & {b+1}: {array[a, b]}")
                print(path); print(array); breakpoint()  # debug

            return array

        def _compute_using_array_style(temp_dict):
            """
            Remember that the diagonal of `temp_dict` are in hartrees,
            while the off-diagonal are in eV.
            """
            bilin_ev = np.zeros(shape)

            bilin_ev += temp_dict['++'] - temp_dict['+-']
            bilin_ev += temp_dict['--'] - temp_dict['-+']

            for a in range(A):  # make sure we multiply the diagonal by ha2ev
                bilin_ev[a, a] *= ha2ev

            bilin_ev /= (2. * qsize) ** 2
            return bilin_ev

        def _compute_using_forloop_style(i, j, temp_dict):
            """ bilin_ev needs to run through all temp_dict[key], so beyond '++'.
            You only get '--'' after temp_dict fully built
            """
            bilin_ev = np.zeros(shape)
            counter = 0

            for a in range(A):
                bilin_ev[a, a] += temp_dict['++'][a, a] - temp_dict['+-'][a, a]
                bilin_ev[a, a] += temp_dict['--'][a, a] - temp_dict['-+'][a, a]
                bilin_ev[a, a] *= ha2ev   # convert back to eV's (only for the diagonal)
                bilin_ev[a, a] /= (4.0 * qsize * qsize)

                for b in range(a):
                    bilin_ev[b, a] += temp_dict['++'][b, a] - temp_dict['+-'][b, a]
                    bilin_ev[b, a] += temp_dict['--'][b, a] - temp_dict['-+'][b, a]
                    bilin_ev[b, a] /= (4.0 * qsize * qsize)

                    if True and __debug__:
                        counter += 1
                        print(f'BILIN_EV at mode {i} & {j}, processing iteration #{counter}, states {b+1} & {a+1}')
                        pprint.pprint(bilin_ev)

            return bilin_ev

        for i, j in upper_triangle_loop_indices(N, 2):

            temp_dict = {}  # stores temporary arrays (different every single i,j \in N x N loop)
            for d1, d2 in it.product(['+', '-'], ['+', '-']):
                key = d1+d2
                path = bilinear_displacement_filenames[(key, i, j)]
                temp_dict[key] = extract_energy_at_displaced_geometry(path, key)
                print(i, j, path)

            if True and __debug__:
                print(f'TEMP DICT at mode {i} & {j}'); pprint.pprint(temp_dict)

            if not array_style:  # do it with for loops
                bilin_ev = _compute_using_forloop_style(i, j, temp_dict)
                if False and __debug__: print(i, j, bilin_ev); breakpoint()
            else:
                bilin_ev = _compute_using_array_style(temp_dict)
                if False and __debug__:
                    print(f'BI-Linear at mode {i} & {j}');
                    pprint.pprint(bilin_ev);
                    breakpoint()

            bilinear_dictionary[mode_map_dict[i], mode_map_dict[j]] = bilin_ev

        print(f"FULL BILINEAR DICTIONARY! {bilinear_dictionary}")
        return bilinear_dictionary

    def build_parameter_section(model, nof_states, nof_modes):
        """Returns a string which defines the `PARAMETER-SECTION` of an .op file"""
        start, end = "PARAMETER-SECTION", "end-parameter-section"
        header_string = "#{0:^47}#\n#{spacer:^47}#\n"
        make_header = functools.partial(header_string.format, spacer='-' * 45)
        # ----------------------------------------------------------
        # read in all the necessary parameters
        dipoles = model['dipoles']
        vibron_ev = model['vibron eV']
        E0_array_eV = model['E0 eV']

        lin_data, quad_data, bilin_data = model['Linear'], model['Quadratic'],  model['BiLinear']
        # ----------------------------------------------------------
        # begin to assemble the parameter section
        return_list = [
            start,
            make_header('Frequencies'), build_frequencies(vibron_ev),
            make_header('Electronic Hamitonian'), build_E0(E0_array_eV),
            make_header('Electronic transition moments'), build_electronic_moments(dipoles),
            # make_header('Magnetic transition moments'), build_magnetic_moments(M_moments),
        ]

        return_list.extend([
            make_header('Linear Coupling Constants'),  build_linear_coupling(lin_data, nof_states, nof_modes),
            make_header('Quadratic Coupling Constants'), build_quadratic_coupling(quad_data, nof_states, nof_modes),
            make_header('Diagonal Bilinear Coupling Constants'), build_bilinear_coupling(bilin_data, nof_states, nof_modes),
        ])

        if False:  # SOC_flag
            return_list.extend([
                make_header('SOC'), build_linear_coupling(X_lin, nof_states, nof_modes),
            ])
        return_list.append(end)

        return '\n'.join(return_list)
    # # ----------------------------------------------------------

    def label_momentum(N):
        """Return a string containing the momentum labelling of a .op file."""
        spacer = '|'
        return '\n'.join([
            f"1.00*w{i:0>2d}{spacer:>12}{i+1:<3d}KE"
            for i in range(1, N+1)
        ]) + '\n'

    def label_position(N):
        """Return a string containing the position labelling of a .op file."""
        spacer = '|'
        return '\n'.join([
            f"0.50*w{i:0>2d}{spacer:>12}{i+1:<3d}q^2"
            for i in range(1, N+1)
        ]) + '\n'

    def label_energies(A):
        """Return a string containing the energy labelling of a .op file."""
        spacer = '|'
        return '\n'.join([
            f"EH_s{a:0>2d}_s{a:0>2d}{spacer:>15}1 S{a:d}&{a:d}"
            for a in range(1, A+1)
        ]) + '\n'

    def label_linear_coupling(lin_dict, A, N):
        """Return a string containing the linear coupling constant labelling of a .op file."""
        spacer = '|'

        assert len(lin_dict.keys()) == N
        linear_terms = [lin_dict[mode_map_dict[i]] for i in range(N)]

        return '\n'.join([
            (
                f"C1_s{a:0>2d}_s{a:0>2d}_v{i:0>2d}"
                f"{spacer:>11}1 S{a:d}&{a:d}"
                f"{spacer:>4}{i+1}  q"
            )
            for a, i in it.product(range(1, A+1), range(1, N+1))
            if not suppress_zeros or not np.isclose(linear_terms[i-1][a-1, a-1], 0.0)
        ] + [
            ''  # creates a blank line between the (surface) diagonal and off-diagonal linear terms
        ] + [
            (
                f"C1_s{a2:0>2d}_s{a1:0>2d}_v{i:0>2d}"
                f"{spacer:>11}1 S{a2:d}&{a1:d}"
                f"{spacer:>4}{i+1}  q"
            )
            for a1, a2, i in it.product(range(1, A+1), range(1, A+1), range(1, N+1))
            if (a1 != a2)
            and (not suppress_zeros or not np.isclose(linear_terms[i-1][a2-1, a1-1], 0.0))
        ]) + '\n'

    def label_quadratic_coupling(quad_dict, A, N, diagonal=False):
        """Return a string containing the quadratic coupling constant labelling of a .op file."""
        spacer = '|'

        assert len(quad_dict.keys()) == N
        quadratic_terms = [quad_dict[mode_map_dict[i]] for i in range(N)]

        return '\n'.join([
            (
                f"C2_s{a:0>2d}s{a:0>2d}_v{i:0>2d}v{i:0>2d}"
                f"{spacer:>9}1 S{a:d}&{a:d}"
                f"{spacer:>4}{i+1}  q^2"
            )
            for a, i in it.product(range(1, A+1), range(1, N+1))
            if not suppress_zeros or not np.isclose(quadratic_terms[i-1][a-1, a-1], 0.0)
        ] + [
                ''  # creates a blank line between the (surface) diagonal and off-diagonal linear terms
        ] + [
            (
                f"C2_s{a2:0>2d}s{a1:0>2d}_v{i:0>2d}v{i:0>2d}"
                f"{spacer:>9}1 S{a2:d}&{a1:d}"
                f"{spacer:>4}{i+1}  q^2"
            )
            for a1, a2, i in it.product(range(1, A+1), range(1, A+1), range(1, N+1))
            if (a1 < a2)
            if not suppress_zeros or not np.isclose(quadratic_terms[i-1][a2-1, a1-1], 0.0)
        ])

    def label_BiLinear_coupling(bi_lin_dict, A, N, diagonal=False):
        """Return a string containing the quadratic coupling constant labelling of a .op file."""
        spacer = '|'

        bilinear_terms = {}
        for key in bi_lin_dict.keys():
            new_key = (
                selected_mode_list.index(key[0]),
                selected_mode_list.index(key[1])
            )
            bilinear_terms[new_key] = bi_lin_dict[key]

        return '\n'.join([
            (
                f"C1_s{a:0>2d}s{a:0>2d}_v{j1:0>2d}v{j2:0>2d}"
                f"{spacer:>9}1 S{a:d}&{a:d}"
                f"{spacer:>4}{j1+1}  q{spacer:>6}{j2+1}  q"
            )
            for a, j1, j2 in it.product(range(1, A+1), range(1, N+1), range(1, N+1))
            if (j1 < j2)
            and (not suppress_zeros or not np.isclose(bilinear_terms[(j1-1, j2-1)][a-1, a-1], 0.0))
        ] + [
                ''  # creates a blank line between the (surface) diagonal and off-diagonal linear terms
        ] + [
            (
                f"C1_s{a1:0>2d}s{a2:0>2d}_v{j1:0>2d}v{j2:0>2d}"
                f"{spacer:>9}1 S{a1:d}&{a2:d}"
                f"{spacer:>4}{j1+1}  q{spacer:>6}{j2+1}  q"
            )
            for a1, a2, j1, j2 in it.product(range(1, A+1), range(1, A+1), range(1, N+1), range(1, N+1))
            if (a1 < a2) and (j1 < j2)
            and (not suppress_zeros or not np.isclose(bilinear_terms[(j1-1, j2-1)][a1-1, a2-1], 0.0))
        ])

    def benny_label_SOC_section():

        spacer_format_string = f"# {'-':^60s} #\n"
        hfs = header_format_string = "# {:^60s} #\n" + spacer_format_string
        block = hfs.format("SOC FULL HAMILTONIAN SOC OFF-DIAGONAL VIBRONIC COUPLINGS")

        # prepare `make_line`
        format_string_1 = "{label:<25s}{link:<20s}\n"
        format_string_2 = "{label:<25s}{link:<20s}\n"
        format_string_3 = "{label:<25s}{link:<20s}\n"
        format_string_4 = "{label:<25s}{link:<20s}\n"

        make_line_1 = functools.partial(format_string_1.format)
        make_line_2 = functools.partial(format_string_2.format)
        make_line_3 = functools.partial(format_string_3.format)
        make_line_4 = functools.partial(format_string_4.format)

        for i, a in it.product(range(1,N+1), range(1,A+1)):
            for j, b in it.product(range(1,i+1), range(1,a+1)):
                i_label, j_label = modes_included[[i, j]]
                print(f"{i=}, {j=}, {a=}, {b=}")

                l1 = "C1_s{:>02d}_s{:>02d}_v{:>02d}".formmat(j, i, a)
                make_line(label=f"I*{l1}r", link=f"|1 Z{b}&{a} | {j+1} q")
                make_line(label=f"-I*{l1}i", link=f"|1 Z{a}&{b} | {j+1} q")

                l2 = "C2_s{:>02d}_s{:>02d}_v{:>02d}".formmat(j, i, a)
                make_line(label=f"I*{l2}r", link=f"|1 Z{b}&{a} | {j+1} q^2")
                make_line(label=f"-I*{l2}i", link=f"|1 Z{a}&{b} | {j+1} q^2")

                l3 = "C1_s{:>02d}_s{:>02d}_v{:>02d}_v{:>02d}".formmat(j, i, i_label, j_label)
                make_line(label=f"I*{l3}r", link=f"|1 Z{b}&{a} | {j+1} q | {i+1} q")
                make_line(label=f"-I*{l3}i", link=f"|1 Z{a}&{b} | {j+1} q | {i+1} q")

                l4 = "SOC_s{:>02d}_s{:>02d}_v{:>02d}_v{:>02d}".formmat(j, i, i_label, j_label)
                make_line(label=f"I*{l4}r", link=f"|1 Z{b}&{a} | {j+1} q")
                make_line(label=f"-I*{l4}i", link=f"|1 Z{a}&{b} | {j+1} q")
        return

    def build_hamiltonian_section(model, nof_states, nof_modes, SOC_flag=False):
        """Returns a string which defines the `HAMILTONIAN-SECTION` of an .op file"""
        start, end = "HAMILTONIAN-SECTION", "end-hamiltonian-section"
        spec = ''.join([
            ' modes   |  el  |',
            ''.join([f" v{N+1:0>2d}|" for N in range(nof_modes)]),
            '\n'
        ])

        return_list = [
            start,
            spec,
            label_momentum(nof_modes),
            label_position(nof_modes),
            label_energies(nof_states),
        ]

        if "Linear" in model.keys():
            return_list.append(
                label_linear_coupling(model['Linear'], nof_states, nof_modes)
            )
        if "Quadratic" in model.keys():
            return_list.append(
                label_quadratic_coupling(model['Quadratic'], nof_states, nof_modes)
            )
        if "BiLinear" in model.keys():
            return_list.append(
                label_BiLinear_coupling(model['BiLinear'], nof_states, nof_modes)
            )

        if "SOC" in model.keys():
            return_list.append(
                benny_label_SOC_section(model['SOC'], nof_states, nof_modes)
            )

        return_list.append(end)

        return '\n'.join(return_list)
    # # ----------------------------------------------------------

    def neil_build_dipole_moments_section(nof_states, nof_modes):
        """Returns a string which defines the `HAMILTONIAN-SECTION_Ex` of an .op file"""
        start, end = "HAMILTONIAN-SECTION_Ex", "end-hamiltonian-section"
        spec = ''.join([
            ' modes   |  el  |',
            ''.join([f" v{n+1:0>2d}|" for n in range(nof_modes)]),
            '\n'
        ])

        def label_dipole_moments_energies(A):
            """Return a string containing the dipole moments energy labelling of a .op file."""
            spacer = '|'
            return '\n'.join([
                f"Ex_s00_s{a:0>2d}{spacer:>15}1 S{A:d}&{a:d}"
                for a in range(1, A)
            ]) + '\n'

        string = '\n'.join([
            start,
            spec,
            label_dipole_moments_energies(nof_states),
            end,
        ])
        return string

    def build_operator_onto_dipole_moments_section(model, A, N):
        """  """
        block = f"\nHAMILTONIAN-SECTION_Ex\n"

        # Write modes and mode labels
        mode_number_key = [selected_mode_list[i] for i in range(N)]
        h_labels = ["modes", "el", ] + [
            f"v{s:>02d}"
            for s in mode_number_key
        ]

        block += " | ".join(h_labels) + "\n"
        block += f"{'-'*47}\n\n"

        for j in range(1, A+1):
            block += f"1.0         |1 S{A+1}&{j}\n" # A+1, set ground state as fictitious +1 state

        block += "\nend-hamiltonian-section\n"

        return block

    # ----------------------------------------------------------

    def _write_op():

        job_title = f'{filnam} {A} states + ' + str(N) + ' modes'

        # do all the extraction first

        vibron_ev = freq_array * wn2ev
        E0_array_eV, E0_array_au = extract_E0(hessout)
        model = {
            "vibron eV": vibron_ev,
            "E0 eV": E0_array_eV,
            "E0 au": E0_array_au,
            "dipoles": extract_etdm(zeroth_filename),
            "Linear": extract_linear(),
            "Quadratic": extract_quadratic(E0_array_eV, E0_array_au, vibron_ev),
            "BiLinear": extract_bilinear(),
        }

        file_contents = "\n".join([
            build_op_section(job_title),
            build_parameter_section(model, A, N),
            build_hamiltonian_section(model, A, N),
            build_operator_onto_dipole_moments_section(model, A, N),
            "end-operator\n"
        ])

        if True:
            for i in range(N):
                new_i = mode_map_dict[i]
                file_contents = file_contents.replace(f'v{i+1:>02d}', f'v{new_i:>02d}')
                file_contents = file_contents.replace(f'w{i+1:>02d}', f'w{new_i:>02d}')

        with open('mctdh.op', 'w') as fp:
            fp.write(file_contents)

    def confirm_necessary_files_exist():

        def _confirm_linear_are_good(bad_mode=False):
            """ confirm all displacement_input_files are good for all selected modes """
            for i in range(N):
                grace_code = {}
                for key in linear_disp_keys:
                    grace_code[key] = subprocess_call_wrapper([
                        "grep", "DONE WITH MP2 ENERGY",
                        linear_displacement_filenames[(key, i)]
                    ])
                    print(f" ..... in file {linear_displacement_filenames[(key, i)]}")

                if not all(code == 0 for code in grace_code.values()):
                    mode_label = pp.mode_map_dict[i]
                    print(f"Linear/Quad mode {mode_label} not good to extract.\n")
                    bad_mode = True

            return bad_mode

        def _confirm_bilinear_are_good(bad_mode=False):
            """ confirm all displacement_input_files are good for all selected modes """
            for i, j in upper_triangle_loop_indices(N, 2):
                grace_code = {}
                for key in bi_linear_disp_keys:
                    grace_code[key] = subprocess_call_wrapper([
                        "grep", "DONE WITH MP2 ENERGY",
                        bilinear_displacement_filenames[(key, i, j)]
                    ])
                    print(f" ..... in file {bilinear_displacement_filenames[(key, i, j)]}")

                if not all(code == 0 for code in grace_code.values()):
                    mode_label = (pp.mode_map_dict[i], pp.mode_map_dict[j])
                    print(f"Bilinear mode {mode_label} not good to extract.\n")
                    bad_mode = True

            return bad_mode

        def refG_file_exists():
            refG_exists = bool(subprocess_call_wrapper(["ls", zeroth_filename]) == 0)
            if not refG_exists:
                """ If refG doesn't exist, then maybe we can find the .... from other files `blah.txt`
                but also maybe they don't exist... need to check later
                """
                print(f"Skip extracting Hamiltonians from the non-existing {zeroth_filename}")
                breakpoint()
                raise Exception("need to add failback code if can't find refG")

            return refG_exists

        flag = bool(
            _confirm_linear_are_good()
            or _confirm_bilinear_are_good()
            or refG_file_exists()
        )
        return flag
    # ------------------------------------------------------------------------

    # execution starts here!!
    if not confirm_necessary_files_exist():
        print("Bad input files detected, please fix.")
        import sys; sys.exit()

    _write_op()

    breakpoint()

    # ------------------------------------------------------------------------
    import sys; sys.exit()
    # ------------------------------------------------------------------------

    def old_code_block():
        # different header style
        hfs = header_format_string = spacer_format_string + "# {:^60s} #\n" + spacer_format_string

        file_contents += _make_ETD_block(header_format_string)
        file_contents += "end-parameter-section\n"

        # ----------------------------------------------------------

        format_string = "{label:<25s}={value:>-15.9f}{units:>8s}\n"
        make_line = functools.partial(format_string.format, units=", ev")

        distcoord_plus, distcoord_minus, distcoord_plus_x2, distcoord_minus_x2 = diabatize[0], diabatize[1], diabatize[2], diabatize[3]
        distcoord_pp, distcoord_pm, distcoord_mp, distcoord_mm = diabatize[4], diabatize[5], diabatize[6], diabatize[7]

        coord_disp_plus = {}
        coord_disp_minus = {}
        coord_disp_plusx2 = {}
        coord_disp_minusx2 = {}
        coord_disp_pp = {}
        coord_disp_pm = {}
        coord_disp_mp = {}
        coord_disp_mm = {}

        for icomp in range(1, ndim + 1):
            coord_disp_plus[icomp] = distcoord_plus[icomp]
            print(f'icomp: {icomp}, coord_disp_plus: {coord_disp_plus[icomp]}')
            coord_disp_minus[icomp] = distcoord_minus[icomp]
            print(f'icomp: {icomp}, coord_disp_minus: {coord_disp_minus[icomp]}')
            coord_disp_plusx2[icomp] = distcoord_plus_x2[icomp]
            print(f'icomp: {icomp}, coord_disp_plusx2: {coord_disp_plusx2[icomp]}')
            coord_disp_minusx2[icomp] = distcoord_minus_x2[icomp]
            print(f'icomp: {icomp}, coord_disp_minusx2: {coord_disp_minusx2[icomp]}')
            coord_disp_pp[icomp] = distcoord_pp[icomp]
            print(f'icomp: {icomp}, coord_disp_pp: {coord_disp_pp[icomp]}')
            coord_disp_pm[icomp] = distcoord_pm[icomp]
            print(f'icomp: {icomp}, coord_disp_pm: {coord_disp_pm[icomp]}')
            coord_disp_mp[icomp] = distcoord_mp[icomp]
            print(f'icomp: {icomp}, coord_disp_mp: {coord_disp_mp[icomp]}')
            coord_disp_mm[icomp] = distcoord_mm[icomp]
            print(f'icomp: {icomp}, coord_disp_mm: {coord_disp_mm[icomp]}')

        spacer_format_string = f"# {'-':^60s} #\n"
        hfs = header_format_string = "# {:^60s} #\n" + spacer_format_string

        params.append(hfs.format('Frequencies'))
        linear.append(hfs.format('Linear Coupling Constants'))
        quadratic.append(hfs.format('Quadratic Coupling Constants'))
        bilinear.append(hfs.format('Bilinear Coupling Constants'))

        # Loop through modes
        for kmode in range(1, nmodes + 1):
            imode = modes_included[kmode]

            displacement_filenames = {
                "+1": f'{filnam}_mode{imode}_+{qsize}.out',
                "+2": f'{filnam}_mode{imode}_+{qsize}x2.out',
                "-1": f'{filnam}_mode{imode}_-{qsize}.out',
                "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
                # "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
                # "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
                # "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
                # "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
            }

            vibron_ev = freqcm[imode] * wn2ev
            Params.append(make_line(label=f"w{imode:>02d}", value=vibron_ev))
            # Params.append("\n")
            # Coupling.append("#Linear and quadratic diagonal and off-diagonal vibronic coupling constants:\n")

            grace_code = {}
            for key in displacement_keys:
                grace_code[key] = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", displacement_filenames[key]])

            """ either of these work (logic wise)
                if any(code != 0 for code in grace_code.values()):
                if not all(code == 0 for code in grace_code.values()):
            """

            if not all(code == 0 for code in grace_code.values()):
                print(f"not good to extract. Skipping mode {imode} for extracting vibronic couplings\n")

            else:  # otherwise we're good to extract
                print("\n good to extract\n")
                # Extract the diagonal and off-diagonal vibronic coupling
                for ist in range(1, nstate + 1):

                    def _make_diag_lin_quad(i):
                        pattern = f'STATE #.* {i}.S GMC-PT-LEVEL DIABATIC ENERGY='

                        # Ediab_au = [extract_diabatic_energy(displacement_filenames[kmode][k], pattern) for k in displacement keys]  $ one liner list comprehension
                        # Ediab_au = {k: extract_diabatic_energy(displacement_filenames[kmode][k], pattern) for k in displacement keys}  # one liner dictionary comprehension
                        Ediab_au = {}
                        for key in displacement_keys:
                            Ediab_au[key] = extract_diabatic_energy(displacement_filenames[key], pattern)

                        # Extract Ediab_au_0
                        Ediab_au_0 = extract_diabatic_energy(zeroth_filename, pattern)
                        linear_diag_ev = (Ediab_au["+1"] - Ediab_au["-1"]) * ha2ev / (2 * qsize)
                        quadratic_diag_ev = (Ediab_au["+2"] + Ediab_au["-2"] - 2.0 * Ediab_au_0) * ha2ev / (4.0 * qsize * qsize)

                        # We only view the difference between the actual force constant and the vibron
                        # as the quadratic diagonal coupling for the diabatic state.
                        quadratic_diag_ev = quadratic_diag_ev - vibron_ev

                        # Print and store results
                        print(f"State {i} Linear Diagonal: {linear_diag_ev} Quadratic Diagonal: {quadratic_diag_ev}, ev\n")

                        # machine accuracy is typically 16 digits
                        s1 = make_line(label=f"C1_s{i:>02d}_s{i:>02d}_v{imode:>02d}", value=linear_diag_ev)
                        s2 = make_line(label=f"C2_s{i:>02d}s{i:>02d}_v{imode:>02d}v{imode:>02d}", value=quadratic_diag_ev)
                        return s1, s2

                    s1, s2 = _make_diag_lin_quad(ist)
                    Linear.append(s1)
                    Quadratic.append(s2)

                    # # Loop over jst
                    jlast = ist - 1
                    for jst in range(1, jlast + 1):

                        def _make_offdiag_lin_quad(i, j):
                            pattern = f'STATE #.* {j} &.* {i}.S GMC-PT-LEVEL COUPLING'

                            # Extract Coup_ev_0
                            Coup_ev_0 = extract_coupling_energy(zeroth_filename, pattern)

                            Coup_ev = {}
                            for key in displacement_keys:
                                Coup_ev[key] = extract_diabatic_energy(displacement_filenames[key], pattern)

                            # Compute linear off-diagonal coupling
                            linear_offdiag_ev = (Coup_ev["+1"] - Coup_ev["-1"]) / (2 * qsize)
                            # Compute quadratic off-diagonal coupling
                            quadratic_offdiag_ev = (Coup_ev["+2"] + Coup_ev["-2"] - 2.0 * Coup_ev_0) / (4.0 * qsize * qsize)

                            # Print and store results
                            print(f"State {j} & {i} Linear Off-Diagonal: {linear_offdiag_ev}\n")
                            print(f"State {j} & {i} Quadratic Off-Diagonal: {quadratic_offdiag_ev}\n")
                            s1 = make_line(label=f"C1_s{j:>02d}_s{i:>02d}_v{imode:>02d}", value=linear_offdiag_ev)
                            s2 = make_line(label=f"C2_s{j:>02d}s{i:>02d}_v{imode:>02d}v{imode:>02d}", value=quadratic_offdiag_ev)
                            return s1, s2

                        s1, s2 = _make_diag_lin_quad(ist, jst)
                        Linear.append(s1)
                        Quadratic.append(s2)

                        """ this is just representative (you can delete - just for learning purposes)
                        if False: # don't actually try to do right now
                            order_name = {1: 'Linear', 2: 'Quadratic'}
                            for i in [1, 2]:
                                _number = [linear_offdiag_ev, quadratic_offdiag_ev][i]
                                print(f"State {jst} & {ist} {order_name[i]} Off-Diagonal: {_number}\n")
                                oprder_list[i].append(make_line(label=f"C{i}_s{jst:>02d}_s{ist:>02d}_v{imode:>02d}", value=_number))
                        """


            # Extracting bilinear vibronic coupling
            # Coupling.append("#Bilinear diagonal and off-diagonal vibronic coupling constants:\n")
            lmode_last = kmode - 1
            for lmode in range(1, lmode_last + 1):
                jmode = modes_included[lmode]

                grace_code_pp = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", f"{filnam}_mode{imode}_+{qsize}_mode{jmode}_+{qsize}.out"])
                grace_code_pm = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", f"{filnam}_mode{imode}_+{qsize}_mode{jmode}_-{qsize}.out"])
                grace_code_mp = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", f"{filnam}_mode{imode}_-{qsize}_mode{jmode}_+{qsize}.out"])
                grace_code_mm = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", f"{filnam}_mode{imode}_-{qsize}_mode{jmode}_-{qsize}.out"])

                if all(code == 0 for code in [grace_code_pp, grace_code_pm, grace_code_mp, grace_code_mm]):
                    print(f"\n Good to extract bilinear for modes {imode} {jmode} \n")
                    for ist in range(1, nstate + 1):
                        pattern = f'STATE #.* {ist}.S GMC-PT-LEVEL DIABATIC ENERGY='

                        # do this style again?
                        # big_displacement_keys = ['++', '+-', '-+', '--']
                        # Ediab_au = {}
                        # for key in displacement_keys:
                        #     Ediab_au[key] = extract_diabatic_energy(big_displacement_filenames[key], pattern)


                        # Extract Ediab_au_pp
                        Ediab_au_pp = extract_diabatic_energy(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_+{qsize}.out', pattern)

                        # Extract Ediab_au_pm
                        Ediab_au_pm = extract_diabatic_energy(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_-{qsize}.out', pattern)

                        # Extract Ediab_au_mp
                        Ediab_au_mp = extract_diabatic_energy(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_+{qsize}.out', pattern)

                        # Extract Ediab_au_mm
                        Ediab_au_mm = extract_diabatic_energy(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_-{qsize}.out', pattern)

                        bilinear_diag_ev = (Ediab_au_pp + Ediab_au_mm - Ediab_au_pm - Ediab_au_mp ) * ha2ev / (4.0 * qsize * qsize )

                        print(f"State {ist} Bilinear Diagonal: {bilinear_diag_ev}\n")
                        Bilinear.append(make_line(label=f"C1_s{ist:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}", value=bilinear_diag_ev))

                        # # Loop over jst
                        jlast = ist - 1
                        for jst in range(1, jlast + 1):
                            pattern = f'STATE #.* {jst} &.* {ist}.S GMC-PT-LEVEL COUPLING'
                            # Extract Coup_ev_pp
                            Coup_ev_pp = extract_coupling_energy(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_+{qsize}.out', pattern)
                            # Extract Coup_ev_pm
                            Coup_ev_pm = extract_coupling_energy(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_-{qsize}.out', pattern)

                            # Extract Coup_ev_mp
                            Coup_ev_mp = extract_coupling_energy(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_+{qsize}.out', pattern)

                            # Extract Coup_ev_mm
                            Coup_ev_mm = extract_coupling_energy(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_-{qsize}.out', pattern)

                            bilinear_offdiag_ev = ( Coup_ev_pp + Coup_ev_mm - Coup_ev_pm - Coup_ev_mp ) / (4.0 * qsize * qsize )

                            print(f"State {jst} & {ist} Bilinear Off-Diagonal: {bilinear_offdiag_ev}\n")
                            Bilinear.append(make_line(label=f"C1_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}", value=bilinear_offdiag_ev))

                            if SOC_flag:

                                try:

                                    # Extract DSOME_cm_pp
                                    DSOME_cm_pp = extract_DSOME(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_+{qsize}.out', nstate)
                                    DSOME_cm_pp_real, DSOME_cm_pp_imag = DSOME_cm_pp[0], DSOME_cm_pp[1]

                                    # Extract DSOME_cm_pm
                                    DSOME_cm_pm = extract_DSOME(f'{filnam}_mode{imode}_+{qsize}_mode{jmode}_-{qsize}.out', nstate)
                                    DSOME_cm_pm_real, DSOME_cm_pm_imag = DSOME_cm_pm[0], DSOME_cm_pm[1]

                                    # Extract DSOME_cm_mp
                                    DSOME_cm_mp = extract_DSOME(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_+{qsize}.out', nstate)
                                    DSOME_cm_mp_real, DSOME_cm_mp_imag = DSOME_cm_mp[0], DSOME_cm_mp[1]

                                    # Extract DSOME_cm_mm
                                    DSOME_cm_mm = extract_DSOME(f'{filnam}_mode{imode}_-{qsize}_mode{jmode}_-{qsize}.out', nstate)
                                    DSOME_cm_mm_real, DSOME_cm_mm_imag = DSOME_cm_mm[0], DSOME_cm_mm[1]


                                except Exception as e:
                                    print(f"Error in SOC: {str(e)}")
                else:
                    print(f"not good to extract. Skipping mode {imode} mode {jmode} for extracting bilinear vibronic couplings")

        if SOC_flag:
            for kmode in range(1, nmodes + 1):
                imode = modes_included[kmode]

                displacement_filenames = {
                    "+1": f'{filnam}_mode{imode}_+{qsize}.out',
                    "+2": f'{filnam}_mode{imode}_+{qsize}x2.out',
                    "-1": f'{filnam}_mode{imode}_-{qsize}.out',
                    "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
                    # "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
                    # "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
                    # "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
                    # "-2": f'{filnam}_mode{imode}_-{qsize}x2.out',
                }

                DSOME_cm = {}
                for key in displacement_keys:
                    try:
                        dsome_real, dsome_imag = extract_DSOME(displacement_filenames[key], nstate)
                        DSOME_cm[k] = {'real': dsome_real, 'imag': dsome_imag}
                        # DSOME_cm[key] = [dsome_real, dsome_imag]
                    except Exception as e:
                        print(f"Error in SOC: {str(e)}")
                        pass  # keep executing, we just needed to log that there was an error
                        # breakpoint()  # if you needed to investigate the cause of the error

                DSOME_cm_plus_real = DSOME_cm["+1"]['real']
                DSOME_cm_plus_imag = DSOME_cm["+1"]['imag']
                DSOME_cm_minus_real = DSOME_cm["-1"]['real']
                DSOME_cm_minus_imag = DSOME_cm["-1"]['imag']
                DSOME_cm_plusx2_real = DSOME_cm["+2"]['real']
                DSOME_cm_plusx2_imag = DSOME_cm["+2"]['imag']
                DSOME_cm_minusx2_real = DSOME_cm["+2"]['real']
                DSOME_cm_minusx2_imag = DSOME_cm["+2"]['imag']


                lmode_last = kmode - 1
                for lmode in range(1, lmode_last + 1):
                    jmode = modes_included[lmode]
                    for ist in range(1, nstate + 1):
                        jlast = ist - 1
                        for jst in range(1, jlast + 1):

                            # intialize dictionaries to contain
                            linear_SOC_cm_real = {}
                            linear_SOC_cm_imag = {}
                            quadratic_SOC_cm_real = {}
                            quadratic_SOC_cm_imag = {}
                            bilinear_SOC_cm_real = {}
                            bilinear_SOC_cm_imag = {}
                            full_Ham_SOC_cm_real = {}
                            full_Ham_SOC_cm_imag = {}

                            # Set jst ist tuple as index
                            idx = (jst, ist)

                            # Compute linear SOC
                            DSOME_cm_plus_real[idx] *= coord_disp_plus[imode]
                            DSOME_cm_plus_imag[idx] *= coord_disp_plus[imode]
                            DSOME_cm_minus_real[idx] *= coord_disp_minus[imode]
                            DSOME_cm_minus_imag[idx] *= coord_disp_minus[imode]
                            linear_SOC_cm_real[idx] = (DSOME_cm_plus_real[idx] - DSOME_cm_minus_real[idx]) / (2 * qsize)
                            linear_SOC_cm_imag[idx] = (DSOME_cm_plus_imag[idx] - DSOME_cm_minus_imag[idx]) / (2 * qsize)

                            # Compute quadratic SOC
                            DSOME_cm_plusx2_real[idx] *= coord_disp_plusx2[imode] * coord_disp_plusx2[imode]
                            DSOME_cm_plusx2_imag[idx] *= coord_disp_plusx2[imode] * coord_disp_plusx2[imode]
                            DSOME_cm_minusx2_real[idx] *= coord_disp_minusx2[imode] * coord_disp_minusx2[imode]
                            DSOME_cm_minusx2_imag[idx] *= coord_disp_minusx2[imode] * coord_disp_minusx2[imode]
                            quadratic_SOC_cm_real[idx] = (DSOME_cm_plusx2_real[idx] + DSOME_cm_minusx2_real[idx] - 2.0 * DSOME_cm_0_real[idx]) / (4.0 * qsize * qsize)
                            quadratic_SOC_cm_imag[idx] = (DSOME_cm_plusx2_imag[idx] + DSOME_cm_minusx2_imag[idx] - 2.0 * DSOME_cm_0_imag[idx]) / (4.0 * qsize * qsize)

                            # Compute bilinear SOC
                            DSOME_cm_pp_real[idx] *= coord_disp_pp[imode] * coord_disp_pp[jmode]
                            DSOME_cm_pp_imag[idx] *= coord_disp_pp[imode] * coord_disp_pp[jmode]
                            DSOME_cm_mm_real[idx] *= coord_disp_mm[imode] * coord_disp_mm[jmode]
                            DSOME_cm_mm_imag[idx] *= coord_disp_mm[imode] * coord_disp_mm[jmode]
                            DSOME_cm_pm_real[idx] *= coord_disp_pm[imode] * coord_disp_pm[jmode]
                            DSOME_cm_pm_imag[idx] *= coord_disp_pm[imode] * coord_disp_pm[jmode]
                            DSOME_cm_mp_real[idx] *= coord_disp_mp[imode] * coord_disp_mp[jmode]
                            DSOME_cm_mp_imag[idx] *= coord_disp_mp[imode] * coord_disp_mp[jmode]
                            bilinear_SOC_cm_real[idx] = (DSOME_cm_pp_real[idx] + DSOME_cm_mm_real[idx] - DSOME_cm_pm_real[idx] - DSOME_cm_mp_real[idx] ) / (4.0 * qsize * qsize )
                            bilinear_SOC_cm_imag[idx] = (DSOME_cm_pp_imag[idx] + DSOME_cm_mm_imag[idx] - DSOME_cm_pm_imag[idx] - DSOME_cm_mp_imag[idx] ) / (4.0 * qsize * qsize )

                            # Compute full SOC
                            full_Ham_SOC_cm_real[idx] = (DSOME_cm_0_real[idx] + linear_SOC_cm_real[idx] + quadratic_SOC_cm_real[idx] + bilinear_SOC_cm_real[idx])
                            full_Ham_SOC_cm_imag[idx] = (DSOME_cm_0_imag[idx] + linear_SOC_cm_imag[idx] + quadratic_SOC_cm_imag[idx] + bilinear_SOC_cm_imag[idx])

                            # Hij^(0) + lij^(1)*x_1 + lij^(2)*x_2 + 0.5qij^(1)*x_1 ^ 2 + 0.5qij^(2)*x_2 ^ 2 + bij^(1,2) * x_1 x_2
                            # Does this mean I have to extract the atom coordinates from every file too?
                            # print(imode, icomp, refcoord[icomp], nrmmod[icomp, imode], coord_disp_plus, coord_disp_minus, distcoord_plus[icomp], distcoord_minus[icomp])
                            # Probably is distcoord_plus and distcoord_minus for x1,x2 respectively

                            # Print and store results
                            SOC.append(make_line(label=f"C1_s{jst:>02d}_s{ist:>02d}_v{imode:>02d}r", value=linear_SOC_cm_real[idx], units=', cm-1'))
                            SOC.append(make_line(label=f"C1_s{jst:>02d}_s{ist:>02d}_v{imode:>02d}i", value=linear_SOC_cm_imag[idx], units=', cm-1'))
                            SOC.append("\n")

                            SOC.append(make_line(label=f"C2_s{jst:>02d}s{ist:>02d}_v{imode:>02d}r", value=quadratic_SOC_cm_real[idx], units=', cm-1'))
                            SOC.append(make_line(label=f"C2_s{jst:>02d}s{ist:>02d}_v{imode:>02d}i", value=quadratic_SOC_cm_imag[idx], units=', cm-1'))
                            SOC.append("\n")

                            SOC.append(make_line(label=f"C1_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}r", value=bilinear_SOC_cm_real[idx], units=', cm-1'))
                            SOC.append(make_line(label=f"C1_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}i", value=bilinear_SOC_cm_imag[idx], units=', cm-1'))
                            SOC.append("\n")

                            print(f"State {jst:>02d} & {ist:>02d} SOC (real) at modes {imode:>02d} & {jmode:>02d} {full_Ham_SOC_cm_real[idx]}, cm-1\n")
                            SOC.append(make_line(label=f"SOC_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}r", value=full_Ham_SOC_cm_real[idx], units=', cm-1'))

                            print(f"State {jst:>02d} & {ist:>02d} SOC (imag) at modes {imode:>02d} & {jmode:>02d} {full_Ham_SOC_cm_imag[idx]}, cm-1\n")
                            SOC.append(make_line(label=f"SOC_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}i", value=full_Ham_SOC_cm_imag[idx], units=', cm-1'))
                            SOC.append("\n")

        file_contents = params + ['\n',]
        file_contents += linear + ['\n',]
        file_contents += quadratic + ['\n',]
        file_contents += bilinear + ['\n',]
        file_contents += SOC + ['\n',]

        # Params.append("\n")
        # Params.extend(Linear)
        # Params.append("\n")
        # Params.extend(Quadratic)
        # Params.append("\n")
        # Params.extend(Bilinear)
        # Params.append("\n")
        # Params.extend(SOC)
        # Params.append("\n")

        # different header style
        hfs = header_format_string = spacer_format_string + "# {:^60s} #\n" + spacer_format_string

        file_contents += _make_ETD_block(header_format_string)
        file_contents += "end-parameter-section\n"

        header_name_list = [
            "HAMILTONIAN-SECTION",
            "KINETIC OPERATOR FOR NORMAL MODES",
            "HARMONIC OSCILLATOR POTENTIALS FOR NORMAL MODES",
            "ELECTRONIC COUPLING AT REFERENCE STRUCTURE",
            "LINEAR DIAGONAL VIBRONIC COUPLINGS",
            "LINEAR OFF-DIAGONAL VIBRONIC COUPLINGS",
            "QUADRATIC DIAGONAL VIBRONIC COUPLINGS",
            "QUADRATIC OFF-DIAGONAL VIBRONIC COUPLINGS",
            "BILINEAR DIAGONAL VIBRONIC COUPLINGS",
            "BILINEAR OFF-DIAGONAL VIBRONIC COUPLINGS",
        ]

        # Open mctdh.op file for writing
        with open('mctdh.op', 'a') as mctdh_file:

            labels = [

            ]

            # this part isn't done yet ---- IN PROGRESS

            def _make_hamiltonian_section():

                block = header_format_string.format(header_name_list[0])

                # Write modes and mode labels
                mode_labels = [f"v{n:>02d}" for n in pp.selected_mode_list]
                block += "modes | el | " + " | ".join(mode_labels) + "\n"

                for i, label in enumerate(pp.selected_mode_list):
                    block += f"1.00*w{label:>02d}   |{i+2} KE\n"
                    block += f"0.50*w{label:>02d}   |{i+2} q^2\n"

                for a in range(1, A+2):
                    block += f"EH_s{a:>02d}_s{a:>02d} |1 S{a}&{a}\n"

                block += "\n"

                _list1 = [
                    "EH_s{}_s{}",
                    "C1_s{}_s{}_v{}",
                    "C1_s{}_s{}_v{}_v{}",
                    "C2_s{}_s{}_v{}_v{}",
                ]

                _list2 = [
                    "|1 S{a:}&{a:} |{i:} q",
                    "|1 S{b:}&{a:} |{i:} q",
                    "|1 S{a:}&{a:} |{i:} q^2",
                    "|1 S{a:}&{a:} |{i:} q |{j:} q",
                    "|1 S{b:}&{a:} |{i:} q |{j:} q",
                ]

            def label_linear_coupling(linear_terms, A, N):
                """Return a string containing the linear coupling constant labelling of a .op file."""
                spacer = '|'
                if diagonal:
                    return '\n'.join([
                        f"C1_s{a:0>2d}_s{a:0>2d}_v{i:0>2d}{spacer:>11}1 S{a:d}&{a:d}{spacer:>4}{i+1}  q"
                        for a, i in it.product(range(1, A+1), range(1, N+1))
                        if not np.isclose(linear_terms[i-1, a-1], 0.0)
                    ]) + '\n'
                else:
                    return '\n'.join([
                        f"C1_s{a:0>2d}_s{a:0>2d}_v{i:0>2d}{spacer:>11}1 S{a:d}&{a:d}{spacer:>4}{i+1}  q"
                        for a, i in it.product(range(1, A+1), range(1, N+1))
                    ] + [
                        ''  # creates a blank line between the (surface) diagonal and off-diagaonl linear terms
                    ] + [
                        f"C1_s{a2:0>2d}_s{a1:0>2d}_v{i:0>2d}{spacer:>11}1 S{a2:d}&{a1:d}{spacer:>4}{i+1}  q"
                        for a1, a2, i in it.product(range(1, A+1), range(1, A+1), range(1, N+1))
                        if (a1 != a2)
                    ]) + '\n'


                for a in range(1, A+1):
                    for b in range(1, a):
                        block += f"EH_s{b:>02d}_s{a:>02d}  |1 S{b}&{a}\n"

                # Write LINEAR AND QUADRATIC DIAGONAL VIBRONIC COUPLINGS
                for i, a in it.product(range(1, N+1), range(1, A+1)):
                    i_label = mode_map_dict[i]
                    block += f"C1_s{a:>02d}_s{a:>02d}_v{i_label:>02d} |1 S{a}&{a} |{i+1} q\n"

                # Write LINEAR AND QUADRATIC OFF-DIAGONAL VIBRONIC COUPLINGS
                for i, a in it.product(range(1, N+1), range(1, A+1)):
                    i_label = mode_map_dict[i]
                    for b in range(1, a):
                        block += (
                            f"C1_s{b:>02d}_s{a:>02d}_v{i_label:>02d}"
                            f" |1 S{b}&{a} |{i+1} q\n"
                        )

                # Write LINEAR AND QUADRATIC DIAGONAL VIBRONIC COUPLINGS
                for i, a in it.product(range(1, N+1), range(1, A+1)):
                    i_label = mode_map_dict[i]
                    block += (
                        f"0.50*C2_s{a:>02d}s{a:>02d}_v{i_label:>02d}v{i_label:>02d}"
                        f" |1 S{a}&{a} |{i+1} q^2\n"
                    )

                # Write BILINEAR DIAGONAL VIBRONIC COUPLINGS
                for i, a in it.product(range(1, N+1), range(1, A+1)):
                    for j in range(1, i):
                        i_label, j_label = mode_map_dict[[i, j]]
                        block += (
                                f"C1_s{a:>02d}s{a:>02d}_v{i_label:>02d}v{j_label:>02d}"
                                f" |1 S{a}&{a} |{i+1} q |{j+1} q\n"
                            )

                # Write BILINEAR OFF-DIAGONAL VIBRONIC COUPLINGS
                for i, a in it.product(range(1, N+1), range(1, A+1)):
                    for j, b in it.product(range(1, i), range(1, a)):
                        i_label, j_label = mode_map_dict[[i, j]]
                        block += (
                                f"C1_s{b:>02d}s{a:>02d}_v{i_label:>02d}v{j_label:>02d}"
                                f" |1 S{b}&{a} |{i+1} q |{j+1} q\n"
                            )

                # ------------------------------------------------------------
                # Write KINETIC OPERATOR FOR NORMAL MODES (mostly fine)
                for imode_include in range(1, nmodes + 1):
                    mode_count = imode_include + 1
                    mctdh_file.write(f"1.00*w{modes_included[imode_include]:>02d}   |{mode_count} KE\n")

                # Write HARMONIC OSCILLATOR POTENTIALS FOR NORMAL MODES
                for imode_include in range(1, nmodes + 1):
                    mode_count = imode_include + 1
                    mctdh_file.write(f"0.50*w{modes_included[imode_include]:>02d}   |{mode_count}  q^2\n")

                # Write ELECTRONIC COUPLING AT REFERENCE STRUCTURE
                for ist in range(1, nstate + 2):
                    mctdh_file.write(f"EH_s{ist:>02d}_s{ist:>02d} |1 S{ist}&{ist}\n")

                mctdh_file.write("\n")
                for ist in range(1, nstate + 1):
                    jlast = ist - 1
                    for jst in range(1, jlast + 1):
                        mctdh_file.write(f"EH_s{jst:>02d}_s{ist:>02d}  |1 S{jst}&{ist}\n")

                # Write LINEAR AND QUADRATIC DIAGONAL VIBRONIC COUPLINGS
                for kmode in range(1, nmodes + 1):
                    imode = modes_included[kmode]
                    kmode_count = kmode + 1
                    for ist in range(1, nstate + 1):
                        mctdh_file.write(f"C1_s{ist:>02d}_s{ist:>02d}_v{imode:>02d} |1 S{ist}&{ist} |{kmode_count} q\n")

                # Write LINEAR AND QUADRATIC OFF-DIAGONAL VIBRONIC COUPLINGS
                for kmode in range(1, nmodes + 1):
                    imode = modes_included[kmode]
                    kmode_count = kmode + 1
                    for ist in range(1, nstate + 1):
                        jlast = ist - 1
                        for jst in range(1, jlast + 1):
                            mctdh_file.write(f"C1_s{jst:>02d}_s{ist:>02d}_v{imode:>02d} |1 S{jst}&{ist} |{kmode_count} q\n")

                # Write LINEAR AND QUADRATIC DIAGONAL VIBRONIC COUPLINGS
                for kmode in range(1, nmodes + 1):
                    imode = modes_included[kmode]
                    kmode_count = kmode + 1
                    for ist in range(1, nstate + 1):
                        mctdh_file.write(f"0.50*C2_s{ist:>02d}s{ist:>02d}_v{imode:>02d}v{imode:>02d} |1 S{ist}&{ist} |{kmode_count} q^2\n")

                # Write LINEAR AND QUADRATIC OFF-DIAGONAL VIBRONIC COUPLINGS
                for kmode in range(1, nmodes + 1):
                    imode = modes_included[kmode]
                    kmode_count = kmode + 1
                    for ist in range(1, nstate + 1):
                        jlast = ist - 1
                        for jst in range(1, jlast + 1):
                            mctdh_file.write(f"0.50*C2_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{imode:>02d} |1 S{jst}&{ist} |{kmode_count} q^2\n")

                # Write BILINEAR DIAGONAL VIBRONIC COUPLINGS
                for kmode in range(1, nmodes + 1):
                    imode = modes_included[kmode]
                    kmode_count = kmode + 1
                    lmode_last = kmode - 1
                    for lmode in range(1, lmode_last + 1):
                        jmode = modes_included[lmode]
                        lmode_count = lmode + 1
                        for ist in range(1, nstate + 1):
                            mctdh_file.write(f"C1_s{ist:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d} |1 S{ist}&{ist} |{lmode_count} q |{kmode_count} q\n")

                # Write BILINEAR OFF-DIAGONAL VIBRONIC COUPLINGS
                for kmode in range(1, nmodes + 1):
                    imode = modes_included[kmode]
                    kmode_count = kmode + 1
                    lmode_last = kmode - 1
                    for lmode in range(1, lmode_last + 1):
                        jmode = modes_included[lmode]
                        lmode_count = lmode + 1
                        for ist in range(1, nstate + 1):
                            jlast = ist - 1
                            for jst in range(1, jlast + 1):
                                mctdh_file.write(f"C1_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d} |1 S{jst}&{ist} |{lmode_count} q |{kmode_count} q\n")


                mctdh_file.write("-----------------------------------------\n")
                mctdh_file.write("\nend-hamiltonian-section\n\n")

            if SOC_flag:  # all the code inside this IF should eventually move to a seperate function (like factored out)

                soc_extension_list_string = []

                key_order = [  # (THE ORDER IS VERY IMPORTANT)
                    'Linear-Real',
                    'Linear-Imag',
                    'Quadratic-Real',
                    'Quadratic-Imag',
                    'Bilinear-Real',
                    'Bilinear-Imag',
                    'SOC-Real',
                    'SOC-Imag',
                ]
                hamiltonian_blocks = {k: "" for k in key_order}
                # ----------------------------------------------------------------------

                # prepare `make_line`
                format_string = "{label:<25s}{link:<20s}\n"
                make_line = functools.partial(format_string.format)

                # Write FULL HAMILTONIAN SOC OFF-DIAGONAL VIBRONIC COUPLINGS

                """ there is ways to do this, but it may not be worth the effort right now
                for k, l, i, j in it.product():
                    hamiltonian_blocks['Linear-Real'] += make_line(label=f"I*C1_s{jst:>02d}_s{ist:>02d}_v{imode:>02d}r", link=f"|1 Z{jst}&{ist} | {kmode_count} q")  # noqa: E501
                    hamiltonian_blocks['Linear-Real'] += make_line(label=f"-I*C1_s{jst:>02d}_s{ist:>02d}_v{imode:>02d}i", link=f"|1 Z{ist}&{jst} | {kmode_count} q")  # noqa: E501
                for k, l, i, j in it.product():
                    hamiltonian_blocks['Quadratic-Real'] += make_line(label=f"I*C2_s{jst:>02d}s{ist:>02d}_v{imode:>02d}r", link=f"|1 Z{jst}&{ist} | {kmode_count} q^2")  # noqa: E501
                    hamiltonian_blocks['Quadratic-Real'] += make_line(label=f"-I*C2_s{jst:>02d}s{ist:>02d}_v{imode:>02d}i", link=f"|1 Z{ist}&{jst} | {kmode_count} q^2")  # noqa: E501
                <...> (and so forth)
                """

                # do the work
                for kmode in range(1, nmodes + 1):
                    imode = modes_included[kmode]
                    lmode_last = kmode - 1
                    for lmode in range(1, lmode_last + 1):
                        jmode = modes_included[lmode]
                        for ist in range(1, nstate + 1):
                            jlast = (ist - 1)
                            for jst in range(1, jlast + 1):

                                # note to self: the I* is performing ARITHMETIC on SOr_{jst}_{ist} prepared earlier, does that mean we neeed to remove the l and _m{imode}
                                hamiltonian_blocks['Linear-Real'] += make_line(label=f"I*C1_s{jst:>02d}_s{ist:>02d}_v{imode:>02d}r", link=f"|1 Z{jst}&{ist} | {kmode_count} q")  # noqa: E501
                                hamiltonian_blocks['Linear-Imag'] += make_line(label=f"-I*C1_s{jst:>02d}_s{ist:>02d}_v{imode:>02d}i", link=f"|1 Z{ist}&{jst} | {kmode_count} q")  # noqa: E501

                                hamiltonian_blocks['Quadratic-Real'] += make_line(label=f"I*C2_s{jst:>02d}s{ist:>02d}_v{imode:>02d}r", link=f"|1 Z{jst}&{ist} | {kmode_count} q^2")  # noqa: E501
                                hamiltonian_blocks['Quadratic-Imag'] += make_line(label=f"-I*C2_s{jst:>02d}s{ist:>02d}_v{imode:>02d}i", link=f"|1 Z{ist}&{jst} | {kmode_count} q^2")  # noqa: E501

                                hamiltonian_blocks['Bilinear-Real'] += make_line(label=f"I*C1_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}r", link=f"|1 Z{jst}&{ist} | {lmode_count} q |{kmode_count} q")  # noqa: E501
                                hamiltonian_blocks['Bilinear-Imag'] += make_line(label=f"-I*C1_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}i", link=f"|1 Z{ist}&{jst} | {lmode_count} q |{kmode_count} q")  # noqa: E501

                                hamiltonian_blocks['SOC-Real'] += make_line(label=f"I*SOC_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}r", link=f"|1 Z{jst}&{ist} | {kmode_count} q")  # noqa: E501
                                hamiltonian_blocks['SOC-Imag'] += make_line(label=f"-I*SOC_s{jst:>02d}s{ist:>02d}_v{imode:>02d}v{jmode:>02d}i", link=f"|1 Z{ist}&{jst} | {kmode_count} q")  # noqa: E501

                for k in key_order:  # glue the blocks together
                    output_string += hamiltonian_blocks[k] + "\n"

                print("Hey check the output string, and the hamiltonian_blocks"); breakpoint()
                mctdh_file.write(output_string)
                del hamiltonian_blocks  # don't need anymore

        if SOC_flag:
            file_contents += _make_SOC_section()

        file_contents += _make_Hamiltonian_operate_Ex_section()
        file_contents += "end-operator\n"

        with open("mctdh.op", "w") as fp:
            fp.write("".join(file_contents))

    return

# ---------------------------------------------------------------------------------------
# helper functions for `main()`


def read_freq_values(hessout):
    """ Function to read frequency values from selected lines """
    selected_lines = extract_lines_between_patterns(
        hessout,
        "FREQUENCIES IN CM",
        "REFERENCE ON SAYVETZ CONDITIONS"
    )

    freq_value_set = []
    for freqline in selected_lines:
        if "FREQUENCY:" in freqline:
            freq_value_set.append(freqline[18:])

    return freq_value_set


def read_mode_values(hessout):
    """ Function to extract filtered set of lines """
    selected_lines = extract_lines_between_patterns(
        hessout,
        "FREQUENCIES IN CM",
        "REFERENCE ON SAYVETZ CONDITIONS"
    )
    mode_value_set = []

    for idx, modeline in enumerate(selected_lines):
        if len(modeline) > 3 and modeline[2].isdigit():
            # mode_value_set.append(selected_lines[idx][20:])
            # mode_value_set.append(selected_lines[idx+1][20:])
            # mode_value_set.append(selected_lines[idx+2][20:])
            for i in range(3):  # 3 for x,y,z
                mode_value_set.append(selected_lines[idx + i][20:])

    return mode_value_set


def get_number_of_atoms(hessout):
    """ Function to get the number of atoms from the hessout file """

    # would be good to replace this with memory mapping find or grep command?
    with open(hessout, 'r', errors='replace') as hess_file:
        for line in hess_file:
            if ' TOTAL NUMBER OF ATOMS' in line:
                natoms = int(line.split('=')[1])
                return natoms


def _extract_freq_and_mode_from_hessian(path):
    """ x """
    freq_value_set, filtered_set = read_freq_values(path), read_mode_values(path)

    with open('mode.dat', 'w') as fp:
        fp.writelines(filtered_set)

    with open('freq.dat', 'w') as fp:
        fp.writelines(freq_value_set)

    return


def process_mode_freq(ndim, nof_cols=5, float_length=12):
    """ """
    nof_groups = ndim // nof_cols  # integer division
    nof_leftover_modes = ndim % nof_cols
    print(
        f"Dimension of all xyz coordinates: {ndim}\n"
        f"{ndim / 3} atoms, split into {nof_groups} groups with {nof_leftover_modes} left over\n",
    )

    # -------------------------------------------------------------------------
    with open("mode.dat", 'r', errors='replace') as mode_file:
        lines_mode = mode_file.readlines()

    mode_list = [[float(n) for n in line.strip().split()] for line in lines_mode]

    # glue the groups onto each other (we only care about the first ndim)
    for i in range(ndim):
        for g in range(nof_groups):
            mode_list[i].extend(mode_list[i+(ndim*(g+1))])

    # throw away the lists we don't need anymore
    mode_list = mode_list[:ndim]

    # turn into numpy array
    modes_array = np.array(mode_list)  # should be square?

    # -------------------------------------------------------------------------
    with open("freq.dat", 'r', errors='replace') as freq_file:
        lines_freq = freq_file.readlines()

    freq_list = [[float(n) for n in line.strip().replace('I', '').split()] for line in lines_freq]
    frequences = list(it.chain(*freq_list))  # single list
    freq_array = np.array(frequences)

    # freqcm = {}
    # for i in range(len(frequences)):
    #     key = pp.modes_included[i]
    #     freqcm[key] = frequences[i]

    # -------------------------------------------------------------------------
    if False and __debug__:   # print all frequencies
        string = "\n".join([f"frequency: {i} {freq_array[i]} CM-1" for i in range(ndim)])
        print(string)

    # return mode_array, freqcm
    return modes_array, freq_array


def compose_ref_structure(ref_file, hessout, nof_atoms):
    coord_lines = extract_lines_between_patterns(hessout, 'EQUILIBRIUM GEOMETRY LOCATED', 'INTERNUCLEAR DISTANCES')

    good_ref_structure = bool(len(coord_lines) > 2)

    if not good_ref_structure:
        print(f'Unsuccessful extraction of equilibrium geometry from {hessout}. Please prepare ref_structure manually.')
        breakpoint()  # do we want to continue execution, or do we actually want to stop the program?
        import sys; sys.exit()

    if good_ref_structure:

        """ we don't need to delete the file if we simply write a new file
        try:
            subprocess_run_wrapper(['rm', '-f', ref_file])
        except Exception as e:
            print(f"Error deleting {ref_file}: {str(e)}")
        """

        # the last element of coord_lines is an empty line (`\n`)
        assert coord_lines[-1] == '\n'

        # remove empty lines
        coord_lines = [l for l in coord_lines if l != '\n']

        # we want the lines at the end of the file (the last nof_atoms/Z lines)
        file_contents = "".join(coord_lines[-nof_atoms:])

        with open(ref_file, 'w') as fp:
            fp.write(file_contents)

        print(f'Successfully extracted equilibrium geometry from {hessout} and prepared ref_structure.')

    return coord_lines


def read_reference_structure(file_path, verbose=True):
    """ Read in the reference structure.
    The ref_structure has to be prepared by human-being and adopts the following format
        ##### SAMPLE REF STRUCT #######
        N           7.0   0.0000000000  -0.0000000000  -0.1693806842
        H           1.0  -0.4653267700   0.8059696078   0.2564602281
        H           1.0  -0.4653267700  -0.8059696078   0.2564602281
        H           1.0   0.9306535400   0.0000000000   0.2564602281
        ###############################

    This function
    """

    # atom_dict, charge_dict, ref_coords = {}, {}, {}
    atom_dict, charge_dict = {}, {}
    temp_coord_list = []

    with open(file_path, 'r', errors='replace') as struct_file:
        lines = struct_file.readlines()

    for i, line in enumerate(lines):
        atom_name, charge, *coords = line.split()

        assert isinstance(atom_name, str), f"{atom_name=} is not a string?"
        assert isinstance(charge, str), f"{charge=} is not a string?"
        assert isinstance(coords, list) and len(coords) == 3, f"{charge=} is not a list of length 3?"

        if verbose and __debug__: print(atom_name, charge, coords)

        atom_dict[i+1], charge_dict[i+1] = atom_name, charge
        temp_coord_list.append(coords)

    # flatten list and apply float to each element
    values = [*map(float, it.chain(*temp_coord_list))]
    keys = range(1, len(values)+1)  # numbers 1,2,3, ...

    # make the reference co-ordinate dictionary
    ref_coords = dict(zip(keys, values))

    if verbose and __debug__: print(atom_dict, charge_dict, ref_coords, sep='\n')

    return atom_dict, charge_dict, ref_coords


def refG_calc(refgeo, input_filename, output_filename):
    """
    Do diabatization calculation at the reference non-distorted structure.
    This calculation shall be a repetition of a calculation in preparing `temp.inp`.
    """

    # Check if the calculation has already been run
    grace_exists = subprocess_call_wrapper(["grep", "DONE WITH MP2 ENERGY", output_filename]) == 0

    if grace_exists:
        print("Calculation at the reference structure has already been done.")
        return

    else:
        print("Run calculation at the undistorted reference structure")

        shutil.copy("temp.inp", input_filename)

        with open(refgeo, 'r', errors='replace') as ref_structure:
            data = ref_structure.read()

        # in this case we append the reference structure to file contents from "temp.inp"
        with open(input_filename, "a") as fp:
            fp.write(data)
            fp.write(" $END\n")

        # Submit and run the refG calculation (you may need to customize this command based on your setup)
        # refG_job_result = subprocess_run_wrapper(["./subgam.diab", input_filename, "4", "0", "1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os_system_wrapper("sbatch" + ' -W' + " " + my_subgam(input_filename, ncpus=2, ngb=1, nhour=1))  # the wait

        # At this point, refG calculation has completed successfully.
        print("Calculation at the reference structure is done.")

    return

# ---------------------------------------------------------------------------------------


def main(ref_file="ref_structure", ncols=5, **kwargs):
    """ x """
    hessian_filename = kwargs['hessian_filename']
    _extract_freq_and_mode_from_hessian(hessian_filename)

    nof_atoms = natoms = get_number_of_atoms(hessian_filename)
    ndim = nof_atoms * 3

    assert Z == nof_atoms, f"{Z=} is not {nof_atoms=}!?"
    assert N_tot == ndim, f"{N_tot=} is not {ndim=}!?"

    nrmmod, freqcm = process_mode_freq(N_tot, ncols)

    compose_ref_structure(ref_file, hessian_filename, nof_atoms)

    atmlst, chrglst, refcoord = read_reference_structure(ref_file)

    refG_calc(ref_file, kwargs['refG_in'], kwargs['refG_out'])

    # -------------------------------------------------------------------------
    diabatization_kwargs = kwargs.copy()
    diabatization_kwargs.update({
        'ndim': ndim,
        'freqcm': freqcm,
        'refcoord': refcoord,
        'nrmmod': nrmmod,
        'natoms': natoms,
        'atmlst': atmlst,
        'chrglst': chrglst,
        'qsize': pp.qsize,
        'ha2ev': pp.ha2ev,
        'wn2ev': pp.wn2ev,
        'wn2eh': pp.wn2eh,
        'ang2br': pp.ang2br,
        'amu2me': pp.amu2me
    })
    # name, modes = pp.filnam, pp.modes_included
    diabatize = diabatization(**diabatization_kwargs)
    print("Diabatization successfully modified")

    mctdh_input_kwargs = kwargs.copy()
    mctdh_input_kwargs.update({
        'qsize': pp.qsize,
        'ha2ev': pp.ha2ev,
        'wn2ev': pp.wn2ev,
        'wn2eh': pp.wn2eh,
        'ang2br': pp.ang2br,
        'amu2me': pp.amu2me,
        'nof_electronic_states': pp.A,
        'ndim': ndim,
        'freqcm': freqcm,
        'nrmmod': nrmmod,
        'diabatize': diabatize,
        'hessout': kwargs['hessian_filename'],
    })

    # name, modes = pp.filnam, pp.modes_included
    mctdh(**mctdh_input_kwargs)
    print("mctdh successfully modified"); return

    print('The run was a success!')

    shutil.copy("mctdh.op", kwargs['project_filename'] + '.op')

    if (extra_debug := False):
        print('---------nrm mod done-----------')
        pprint.pprint(nrmmod)
        print('---------freqcm done-----------')
        pprint.pprint(freqcm)
        print('---------selected_mode_list done-----------')
        pprint.pprint(selected_mode_list)
        print('---------atmlst done-----------')
        pprint.pprint(atmlst)
        print('---------chrglst done-----------')
        pprint.pprint(chrglst)
        print('---------refcoord done-----------')
        pprint.pprint(refcoord)
    # ...
    return


# ---------------------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python your_script.py <hessout_file>")
        sys.exit(1)

    hessian_filename = sys.argv[1]  # read in name of hessian file
    kwargs = {'hessian_filename': hessian_filename}

    # everything we add to `kwargs` is 'imported' from project parameters

    kwargs.update({
        'project_filename': pp.filnam,
        'refG_in': f"{pp.filnam}_refG.inp",  # reference geometry
        'refG_out': f"{pp.filnam}_refG.out",  # reference geometry
        # 'modes_included': pp.modes_included,
    })

    main(**kwargs)
