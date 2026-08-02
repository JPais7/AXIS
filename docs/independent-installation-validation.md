# Independent installation validation

This protocol tests whether a person who did not develop AXIS can install the
published release and run its synthetic demonstration on a separate computer.
It downloads no biomedical data and should take approximately five minutes
after Python is installed.

## Eligibility

The validator must not have configured the AXIS development environment or
helped implement the installation procedure on the computer being tested.
The same person may report a failed attempt: failures are useful portability
evidence and must not be silently excluded.

## Requirements

- a computer with internet access;
- Python 3.12;
- no existing AXIS virtual environment is required.

## Windows PowerShell

```powershell
python --version
python -m venv axis-validation
.\axis-validation\Scripts\python.exe -m pip install --upgrade pip
.\axis-validation\Scripts\python.exe -m pip install https://github.com/JPais7/AXIS/archive/refs/tags/v0.2.0.zip
.\axis-validation\Scripts\axis.exe demo --output axis-demo-output
```

## macOS or Linux

```shell
python3.12 --version
python3.12 -m venv axis-validation
./axis-validation/bin/python -m pip install --upgrade pip
./axis-validation/bin/python -m pip install https://github.com/JPais7/AXIS/archive/refs/tags/v0.2.0.zip
./axis-validation/bin/axis demo --output axis-demo-output
```

## Success criteria

The final command must report `Synthetic demo passed: 9/9 checks.`. The file
`axis-demo-output/demo-report.json` must report:

- `status` equal to `passed`;
- `synthetic` and `offline` equal to `true`;
- 9 total checks, 9 passed and 0 failed;
- the Python version and operating-system platform used for the run.

Do not edit the report. Do not include passwords, access tokens, private data
or biomedical participant data in the validation record.

## Reporting

Open an
[independent validation report](https://github.com/JPais7/AXIS/issues/new?template=independent_validation.yml)
and record the operating system, Python version, final console result and the
non-sensitive contents of `demo-report.json`. Report any manual intervention
or error, even if the demonstration eventually succeeds.

The project authors review the report before marking independent installation
as complete. A successful run demonstrates installation portability and
deterministic execution of the synthetic example; it does not validate the
biomedical conclusions or establish clinical utility.
