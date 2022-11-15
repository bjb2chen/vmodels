#!/bin/bash

#case-specific for filnam, eref, and omga
filnam="h2ocat_cct_gmcpt_6o7e_3st_diab"
eref=-75.8785697888
#frequency of the normal mode given in cm-1 unit
omga=3975.428

#conversion constant
ha2ev=27.2113961318
wn2ev=0.000123981
wn2eh=0.00000455633
ang2br=1.889725989
amu2me=1822.88839

nstate=`grep '# of states in CI      = ' "$filnam"_as0.0.out|tail -1|cut -d'=' -f2`
echo $nstate

if [ -f Ediab.dat ]
then
  rm -f Ediab.dat
fi

if [ -f Coup.dat ]
then
  rm -f Coup.dat
fi

for step in 0.0 0.1 0.2 0.3 0.4
do
# convert step from mass-weighted coordinates (sqrt(amu)*Angs) to dimensionless reduced coordiate q
  q=`echo "$step  * sqrt($amu2me)*$ang2br*sqrt($omga*$wn2eh)"|bc -l`
  echo -n $q "" >> Ediab.dat
  echo -n $q "" >> Coup.dat
  for ist in $(seq 1 1 $nstate)
  do
#   echo $step $ist
    Ediab_au=`grep "STATE #  $ist.S GMC-PT-LEVEL DIABATIC ENERGY=" "$filnam"_as"$step".out|tail -1|cut -c44-61`
    Ediab_ev=`echo " ($Ediab_au - $eref) * $ha2ev"|bc -l`
#   echo $step $ist $Ediab_ev
    echo -n $Ediab_ev "" >> Ediab.dat
    
#   loop over jst
    jlast=`echo " $ist -1"|bc -l`
    for jst in $(seq 1 1 $jlast)
    do
      echo $step $jst $ist
      Coup_ev=`grep "STATE #  $jst &  $ist.S GMC-PT-LEVEL COUPLING" "$filnam"_as"$step".out|tail -1|cut -c62-`
      echo -n $Coup_ev "" >> Coup.dat
    done
  done
  echo "" >> Ediab.dat
  echo "" >> Coup.dat
done
