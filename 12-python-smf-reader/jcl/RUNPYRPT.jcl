//ANDREPY  JOB AMS-CLEAN,ANDRE,NOTIFY=ANDRE,CLASS=A,MSGLEVEL=(1,1)
//* Stage ANDRE.EPE.SMF30 (BDW/RDW intact) then report with python3
//STAGE    EXEC PGM=IEBGENER
//SYSPRINT DD SYSOUT=*
//SYSIN    DD DUMMY
//SYSUT1   DD DSN=ANDRE.EPE.SMF30,DISP=SHR,
//            DCB=(RECFM=U,BLKSIZE=32760)
//SYSUT2   DD PATH='/z/andre/smf30.bin',
//            PATHOPTS=(OWRONLY,OCREAT,OTRUNC),
//            PATHMODE=(SIRUSR,SIWUSR,SIRGRP),
//            FILEDATA=BINARY
//PYRPT    EXEC PGM=BPXBATCH,COND=(0,NE)
//STDOUT   DD SYSOUT=*
//STDERR   DD SYSOUT=*
//STDPARM  DD *
SH /apps/python/lpp/IBM/cyp/v3r13/pyz/bin/python3
   /z/andre/a12/src/smfrpt30.py /z/andre/smf30.bin
/*
