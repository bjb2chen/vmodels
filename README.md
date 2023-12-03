# vmodels

### Repository for vibronic models construction. Developed in collaboration between Nooijen/Zeng group.

### Protocol procedure. Instructions on how to run the code:
#### - You first need to ensure you have GAMESS with Toby's diabatization (gmcpt.src) module installed.
#### - Configure rungms, runG_diab, and subgam.diab scripts to the appropriate $USER.
#### - Create GAMESS scratch directories if necessary (.gamess_ascii_files and gamess_scr)
#### - Have an input geometry written in ref_structure
#### - Have temp.inp written

### The main diabatization function (lines ~300-450) works by first doing linear coupling (+, -, +x2, -x2), then the subroutine loops over bilinear couplings (plusplus, pm, mp, mm)

#### The following are human input to parameters:
#### modes_excluded and qsize.

Video recording on how to run the diabatization code (assuming you have GAMESS with gmcpt module already): https://youtu.be/nLIn-N0oB-0

[Project Poster Reference](https://github.com/bjb2chen/vmodels/files/10171706/SCP2022_bjc_20685630_White.pdf)

Note to self: I have to get good, ignore the math and just focus on the process. The math will fall out once you are making progress.
