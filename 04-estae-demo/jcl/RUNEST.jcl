//ESTRUN   JOB AMS-CLEAN,
//             ANDRE,
//             NOTIFY=ANDRE,CLASS=A,
//             MSGLEVEL=(1,1)
//*------------------------------------------------------------------*
//*  RUN ESTDEMO BOTH WAYS.                                          *
//*  STEP1 PARM=RETRY    - recovers and retries, expect RC 0.        *
//*  STEP2 PARM=PERC     - recovers and percolates, expect S0C7.     *
//*  Recovery diagnostics are WTO'd to JESMSGLG (ROUTCDE=11).        *
//*  SYSUDUMP is coded for portability; on systems that suppress     *
//*  dumps the WTO lines carry the evidence.                         *
//*------------------------------------------------------------------*
//RETRY   EXEC PGM=ESTDEMO,PARM=RETRY
//STEPLIB  DD  DSN=ANDRE.EPE.LOAD,DISP=SHR
//SYSUDUMP DD  SYSOUT=*
//*------------------------------------------------------------------*
//*  Run the percolate variant regardless of STEP1's result.         *
//*------------------------------------------------------------------*
//PERC    EXEC PGM=ESTDEMO,PARM=PERC,COND=EVEN
//STEPLIB  DD  DSN=ANDRE.EPE.LOAD,DISP=SHR
//SYSUDUMP DD  SYSOUT=*
