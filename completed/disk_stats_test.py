"""
This script rewrites the original script: samples/disk_stats_test.sh.

The goal is to verify the disk mount status and evaluate disk statistics
after generating some disk activity.

Notes for Examiner:
1. I decided to use the cmd commands (like grep, ls, cat, hdparm)
   leveraging the `subprocess` module to keep the return codes consistent
   with the original script. However, Python has specific commands that
   can be used in replacement of these commands. As an example, I
   implemented the function `assert_stats_exists` to show how the `os`
   module can also be used.
2. An NVDIMM module might have a block device name containing the string
   "nvdimm". The original script only checks for "pmem", so I decided
   to add this extra value in the assertion.
3. In `grep`, I added the `-m 1` parameter to make every search stop
   as soon as the pattern is found.
4. Upon examining the original script, I noticed that the `check_return_code`
   function updates a global variable, `$STATUS`. Depending on the order
   in which files are checked, the `$STATUS` variable might end up
   with different results, potentially overriding a success with an error,
   or vice versa. Although not changing the final result, I decided to
   refactor how this is handled in the script.
5. I modified the script to skip generating disk activity if the disk is
   not recognized by the OS.
6. I observed a potential issue in the original script where it does not
   verify whether `$SYS_STAT_BEGIN` and `$SYS_STAT_END` are different,
   despite having a print statement that says: "Stats in
   /sys/block/$DISK/stat did not change." Actually, it is checking the
   status of the previous cmd command. I decided to add an extra
   verification on these variables.

Dependencies:
- Python 3
- `subprocess` module
- `os` module
- `time` module

Usage:
1. Run the script with the disk name as a command-line argument, e.g.,
   `python disk_stats_test.py sdb`. (If none is provided, "sda" is used
   by default.) Ensure to run the script with appropriate permissions to
   access disk information.

Output:
- If the disk is non-NVDIMM, mounted, and stats have changed after disk
  activity, it will print: "PASS: Finished testing stats for {disk}".

Tested on:
- Ubuntu 20.04
"""

import sys
import subprocess
import os
import time
from subprocess import CompletedProcess, CalledProcessError

SUCCESS = 0
GENERAL_ERROR = 1
NON_VOLATILE_MODULES = ["pmem", "nvdimm"]


def assert_non_nvdimm_disk(disk: str):
    contains_non_nvdimm = any(
        module in disk for module in NON_VOLATILE_MODULES
    )
    if contains_non_nvdimm:
        print(f"Disk {disk} appears to be an NVDIMM, skipping")
        sys.exit(SUCCESS)


def run(
    cmd: str, return_stdout: bool = False, error_message: str = None
) -> int | CompletedProcess:
    try:
        output = subprocess.run(
            cmd, shell=True, stdout=subprocess.PIPE, check=True, text=True
        )
        return output.stdout if return_stdout else SUCCESS
    except CalledProcessError as e:
        if error_message:
            print(f"ERROR: retval {e.returncode} : {error_message}")
        return e.output if return_stdout else e.returncode


def grep_disk(
    disk: str, filenames: list[str], echo_error: bool = True
) -> list[int]:
    return [
        run(
            f"grep {disk} {filename}",
            error_message=(
                f"Disk {disk} not found in {filename}" if echo_error else None
            ),
        )
        for filename in filenames
    ]


def ls_disk(disk: str, dirs: list[str]) -> list[int]:
    return [
        run(
            f"ls {dir}/{disk} > /dev/null 2>&1",
            error_message=f"Disk {disk} not found in {dir}",
        )
        for dir in dirs
    ]


def assert_disk_exists(disk: str):
    status_codes = grep_disk(disk, ["/proc/partitions"]) + ls_disk(
        disk, ["/sys/block/"]
    )
    if any(status_code != 0 for status_code in status_codes):
        sys.exit(GENERAL_ERROR)


def get_disk() -> str:
    return sys.argv[1] if len(sys.argv) > 1 else "sda"


def assert_stats_exists(disk: str):
    status_codes = grep_disk(disk, ["/proc/diskstats"])
    if status_codes[0] != 0:
        sys.exit(GENERAL_ERROR)
    filename = f"/sys/block/{disk}/stat"
    if not (os.path.exists(filename) and os.path.getsize(filename) > 0):
        print(
            f"ERROR: retval 1 : stat is either empty or non-existent "
            f"in /sys/block/{disk}/"
        )
        sys.exit(GENERAL_ERROR)


def get_baseline_stats(disk: str) -> tuple[str, str]:
    proc_stat = run(
        f'grep -w -m 1 "{disk}" /proc/diskstats', return_stdout=True
    )
    sys_stat = run(f"cat /sys/block/{disk}/stat", return_stdout=True)
    return proc_stat, sys_stat


def generate_activity(disk: str):
    run(f'hdparm -t "/dev/{disk}"')
    time.sleep(5)


def compare_stats(
    disk: str, before_stats: tuple[str, str], after_stats: tuple[str, str]
) -> int:
    if before_stats[0] == after_stats[0]:
        print_stats_not_changed(
            "/proc/diskstats", before_stats[0], after_stats[0]
        )
        return GENERAL_ERROR
    if before_stats[1] == after_stats[1]:
        print_stats_not_changed(
            f"/sys/block/{disk}/stat", before_stats[1], after_stats[1]
        )
        return GENERAL_ERROR
    return SUCCESS


def print_stats_not_changed(
    stats_type: str, before_stats: str, after_stats: str
):
    print(f"ERROR: retval 1 : Stats in {stats_type} did not change")
    # An improvement here would be to print as before/after instead
    # of output/output, as seen in the original script
    print(f"output: {before_stats}")
    print(f"output: {after_stats}")


if __name__ == "__main__":
    disk = get_disk()
    assert_non_nvdimm_disk(disk)
    assert_disk_exists(disk)
    assert_stats_exists(disk)

    stats_before = get_baseline_stats(disk)
    generate_activity(disk)
    stats_after = get_baseline_stats(disk)

    status = compare_stats(disk, stats_before, stats_after)
    if status == SUCCESS:
        print(f"PASS: Finished testing stats for {disk}")
    sys.exit(status)
