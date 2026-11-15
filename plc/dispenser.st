PROGRAM dispenser
VAR
  Recipe AT %MW0 : UINT;
  Sequence AT %MW1 : UINT;
  Enable AT %MW2 : UINT;
  Measured AT %MW3 : UINT;
  Ack AT %MW4 : UINT;
  Valve AT %MW5 : UINT;
  Done AT %MW6 : UINT;
  Fault AT %MW7 : UINT;
  Active : BOOL := FALSE;
  Target : UINT := 0;
  Watchdog : TON;
END_VAR

IF Enable = 0 THEN
  Active := FALSE;
  Valve := 0;
  Done := 0;
  Fault := 0;
  Ack := Sequence;
ELSE
  IF Sequence <> Ack THEN
    Ack := Sequence;
    Target := Recipe;
    IF (Target > 0) AND (Target <= 1100) AND (Fault = 0) THEN
      Active := TRUE;
      Done := 0;
    ELSE
      Active := FALSE;
      Fault := 1;
    END_IF;
  END_IF;
END_IF;

Watchdog(IN := Active, PT := T#6s);
IF Active THEN
  IF Watchdog.Q OR (Measured >= 1100) THEN
    Active := FALSE;
    Fault := 1;
  ELSIF Measured >= Target THEN
    Active := FALSE;
    Done := 1;
  END_IF;
END_IF;
IF Active AND (Enable = 1) THEN
  Valve := 1;
ELSE
  Valve := 0;
END_IF;
END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK Main(INTERVAL := T#20ms, PRIORITY := 0);
    PROGRAM Inst0 WITH Main : dispenser;
  END_RESOURCE
END_CONFIGURATION
