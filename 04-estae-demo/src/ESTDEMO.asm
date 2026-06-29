*=====================================================================
* ESTDEMO -  ESTAE recovery demonstration
*---------------------------------------------------------------------
* Purpose     : Deliberately abend (S0C7), recover in an ESTAEX exit,
*               format key SDWA fields to WTO, then RETRY (resume,
*               RC 0) or PERCOLATE (let the abend stand) per PARM.
* Inputs      : EXEC PARM=RETRY (default) or PARM=PERC.
* Outputs     : WTO diagnostics to JESMSGLG (ROUTCDE=11). Step RC 0 on
*               retry; step abends S0C7 on percolate; RC 8 if ESTAEX
*               cannot be established.
* Registers   : Mainline R12 base, R13 save area, R5 -> RECAREA.
*               Recovery R3 -> SDWA, R12 reloaded base, R4 retry addr.
* Preserved   : Caller registers saved by @ENTER.
* Dependencies: @ENTER @LEAVE @HEXOUT (ANDRE.EPE.MACLIB); ESTAEX SETRP
*               WTO IHASDWA (SYS1.MACLIB / SYS1.MODGEN).
* Sample      : See ../jcl/RUNEST.jcl
*=====================================================================
R0       EQU   0
R1       EQU   1
R2       EQU   2
R3       EQU   3
R4       EQU   4
R5       EQU   5
R6       EQU   6
R7       EQU   7
R8       EQU   8
R9       EQU   9
R10      EQU   10
R11      EQU   11
R12      EQU   12
R13      EQU   13
R14      EQU   14
R15      EQU   15
ESTDEMO  CSECT
ESTDEMO  AMODE 31
ESTDEMO  RMODE ANY
         @ENTER
*---------------------------------------------------------------------
* Parse PARM:  R1 -> parm list, the entry -> halfword length + text.
* PARM=PERC selects percolate; blank or anything else -> retry.
*---------------------------------------------------------------------
         MVI   PERCFLG,C'N'        default = retry
         L     R2,0(,R1)           R2 -> parm string (LEN + text)
         LH    R3,0(,R2)           R3 = parm text length
         LTR   R3,R3               no parm at all?
         BZ    PARMSET
         CH    R3,=H'4'            shorter than 'PERC'?
         BL    PARMSET
         CLC   2(4,R2),=C'PERC'    percolate requested?
         BNE   PARMSET
         MVI   PERCFLG,C'Y'
PARMSET  DS    0H
*---------------------------------------------------------------------
* Start banner naming the chosen mode
*---------------------------------------------------------------------
         CLI   PERCFLG,C'Y'
         BE    BANPERC
         WTO   'ESTDEMO STARTING - RETRY MODE',ROUTCDE=(11)
         B     BANDONE
BANPERC  WTO   'ESTDEMO STARTING - PERCOLATE MODE',ROUTCDE=(11)
BANDONE  DS    0H
*---------------------------------------------------------------------
* Build the recovery parameter area: eyecatcher, mode flag, my base
* register, and the retry resume address.
*---------------------------------------------------------------------
         LA    R5,RECAREA
         USING RECPARM,R5
         MVC   RPEYE,=C'RPRM'
         MVC   RPFLAG,PERCFLG
         ST    R12,RPBASE          save base for the recovery exit
         LA    R0,RESUME           retry resume point
         ST    R0,RPRESUME
         DROP  R5
*---------------------------------------------------------------------
* Establish the recovery routine, then force the abend.
*---------------------------------------------------------------------
         ESTAEX RECEXIT,PARAM=RECAREA,TERM=YES
         LTR   R15,R15             established cleanly?
         BNZ   ESTFAIL
         WTO   'ESTDEMO - FORCING S0C7 NOW',ROUTCDE=(11)
         AP    BADPACK(4),PONE(2)  invalid packed -> S0C7
*---------------------------------------------------------------------
* Reaching here means the abend did not occur - unexpected.
*---------------------------------------------------------------------
         WTO   'ESTDEMO - ABEND DID NOT OCCUR',ROUTCDE=(11)
         @LEAVE RC=8
*---------------------------------------------------------------------
* RESUME - retry resumes here with the mainline registers restored.
*---------------------------------------------------------------------
RESUME   DS    0H
         ESTAEX 0                  cancel the recovery routine
         WTO   'ESTDEMO - RECOVERED VIA RETRY, CONTINUING',ROUTCDE=(11)
         @LEAVE RC=0
*---------------------------------------------------------------------
* ESTAEX could not be established
*---------------------------------------------------------------------
ESTFAIL  DS    0H
         WTO   'ESTDEMO - ESTAEX ESTABLISH FAILED',ROUTCDE=(11)
         @LEAVE RC=8
*=====================================================================
* RECEXIT - the ESTAEX recovery routine.
*   R0 = 0 (SDWA present) or 12 (none); R1 -> SDWA; R2 -> PARAM area;
*   R13 -> RTM work area; R15 = entry point.
*=====================================================================
RECEXIT  DS    0H
         USING RECPARM,R2          PARAM area, addressed by R2
         L     R12,RPBASE          reload program base
         USING ESTDEMO,R12
*  R0 = 12 means no SDWA was provided (R1 then holds the abend code).
*  Any other entry code (0, 16, ...) carries an SDWA address in R1.
         C     R0,=F'12'           no SDWA provided?
         BE    NOSDWA
         LR    R3,R1               R3 -> SDWA
         USING SDWA,R3
*---------------------------------------------------------------------
* Format and report the diagnostics (hex field sits at text start,
* i.e. list-form label + 4, so no character counting is needed).
*---------------------------------------------------------------------
         @HEXOUT SDWAABCC,MSGCODE+4,LEN=4
         WTO   MF=(E,MSGCODE)
         @HEXOUT SDWAEC1,MSGPSW+4,LEN=8
         WTO   MF=(E,MSGPSW)
         @HEXOUT SDWAGR14,MSGREGS+4,LEN=8
         WTO   MF=(E,MSGREGS)
*---------------------------------------------------------------------
* Retry or percolate per the saved mode flag.
*---------------------------------------------------------------------
         CLI   RPFLAG,C'Y'         percolate requested?
         BE    DOPERC
         L     R4,RPRESUME         retry resume address
         SETRP RC=4,RETADDR=(R4),RETREGS=YES,FRESDWA=YES,WKAREA=(R3)
         BR    R14                 return to RTM -> retry
DOPERC   DS    0H
         WTO   'ESTDEMO RECOVERY - PERCOLATING ABEND',ROUTCDE=(11)
         SETRP RC=0,WKAREA=(R3)
         BR    R14                 return to RTM -> percolate
         DROP  R3
*---------------------------------------------------------------------
* No SDWA: cannot SETRP, so percolate regardless of the request.
*---------------------------------------------------------------------
NOSDWA   DS    0H
         WTO   'ESTDEMO RECOVERY - NO SDWA, PERCOLATING',ROUTCDE=(11)
         SLR   R15,R15             RC 0 = percolate
         BR    R14
         DROP  R12
*---------------------------------------------------------------------
* Constants and work areas (non-reentrant, like the rest of the set)
*---------------------------------------------------------------------
         LTORG
PERCFLG  DC    C'N'                Y = percolate, N = retry
PONE     DC    PL2'1'              valid packed addend
BADPACK  DC    XL4'C1C2C3C4'       invalid packed data -> S0C7
*---------------------------------------------------------------------
* Recovery parameter area (mapped by RECPARM below)
*---------------------------------------------------------------------
RECAREA  DS    XL16                mapped by RECPARM (4+1+3+4+4)
*---------------------------------------------------------------------
* WTO list-form messages. The hex placeholder is the first thing in
* the text, so it is patched at <label>+4 (the text start).
*---------------------------------------------------------------------
MSGCODE  WTO   '00000000=ABEND CODE (SDWAABCC)',ROUTCDE=(11),MF=L
MSGPSW   WTO   '0000000000000000=PSW (SDWAEC1)',ROUTCDE=(11),MF=L
MSGREGS  WTO   '0000000000000000=GPR 14-15 AT ERROR',ROUTCDE=(11),MF=L
         @HEXOUT MODE=DEFINE
*---------------------------------------------------------------------
* DSECTs
*---------------------------------------------------------------------
RECPARM  DSECT
RPEYE    DS    CL4                 eyecatcher 'RPRM'
RPFLAG   DS    C                   Y = percolate, N = retry
         DS    XL3                 align
RPBASE   DS    A                   saved program base (R12)
RPRESUME DS    A                   retry resume address
RECPARML EQU   *-RECPARM
         IHASDWA
         END   ESTDEMO
