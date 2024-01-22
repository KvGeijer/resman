#!/usr/bin/env python3

import time
import json
import argparse
import os
import sys

LOCK_FILE = "/etc/res_lock"
BLANK_DAT = {'username': '', 'reason': [''], 'start_time': 0, 'duration': 0}


class cols:
    WARNING = '\033[91m'
    ENDC = '\033[0m'
    OKGREEN = '\033[92m'


# Write reservation info into a given file, and also return the data as a
# dictionary.
def dumpdat(file, username, start, duration, reason):
    dat = {
        'start_time': start,
        'duration': duration,
        'username': username,
        'reason': reason
    }

    json.dump(dat, file)
    return dat


# Check if the lock file is reserved right now.
# If it is, return (True, dictionary of JSON data from file)
# Otherwise, return (False, blank dictionary of same schema)
def is_locked():
    try:
        file = open(LOCK_FILE, "r")
        dat = json.load(file)

        if dat['duration'] == -1:
            return True, dat

        end_time = dat['start_time'] + dat['duration']
        now = time.time()

        return now <= end_time, dat
    except (KeyError, json.JSONDecodeError):
        return False, BLANK_DAT
    except OSError:
        return False, BLANK_DAT


# Try to lock the file with given reservation info, but fail and return False
# if it's already locked
def try_lock(username, start, duration=3600, reason=""):
    locked, dat = is_locked()

    if locked:
        return False, dat
    else:
        with open(LOCK_FILE, 'w') as file:
            return True, dumpdat(file, username, start, duration, reason)


# Force unlock the lock file, by clearing it
def release():
    with open(LOCK_FILE, 'w') as file:
        file.truncate(0)


# Parse a time string in a form like:
# '1h30m' = 1 hour, 30 minutes
# '25m' = 0 hours, 25 minutes
# '10h' = 10 hours, 0 minutes
def timestring2secs(ts: str):
    if 'h' not in ts:
        ts = '0h' + ts
    if 'm' not in ts:
        ts = ts + '0m'

    h_ind = ts.index('h')

    try:
        h = int(ts[:h_ind])
        m = int(ts[h_ind + 1:-1])

        return h * 3600 + m * 60
    except ValueError:
        return None


def secs2timestring(snds: int):
    hours = snds // 3600
    mins = (snds := snds % 3600) // 60
    secs = snds % 60
    return f"{hours}h{mins}m{secs}s"


# Give a human readable explanation of data taken from the lock file.
def explain_failure(dat):
    print(f"Already locked by {dat['username']}!")
    print(f"Reason: '{dat['reason']}'")

    if dat['duration'] == -1:
        print("Reservation is until further notice, likely waiting for a \
command to finish running.")
    else:
        snds = int(dat['start_time'] + dat['duration'] - time.time())
        print(f"{secs2timestring(snds)} left on reservation")


def main():
    parser = argparse.ArgumentParser(
        prog='resman',
        description=f'A simple system resource allocation program. Persistent \
state stored in {LOCK_FILE}. \
This program does not impose any actual lock on system resource usage; it only\
 keeps track of which user (if any) has laid claim to it for the time being, \
and if applicable how long they have it reserved for. \
The purpose of this is to prevent two people accidentally running experiments \
at the same time.',
        epilog='Can also be run with no arguments, to check status. \
Exits with 0 if not reserved, or 1 if currently reserved. Just \
`echo $?` afterwards'
    )

    parser.add_argument('-d', '--duration', help='how long to reserve server \
use for (e.g. 1h30m, 25m, 4h)', default=-1)

    parser.add_argument('-U', '--user', help='who is using the server during \
the reservation? Default is you.', default=os.getlogin())

    parser.add_argument('-r', '--reason', help='what experiment are you \
running? default is blank. completely optional.', default=['<no reason given>'],
                        nargs='*')

    parser.add_argument('-x', '--run', metavar='COMMAND', help='if this flag \
is given, COMMAND is executed and the server is reserved until it finishes. \
In this case, DURATION is ignored.', nargs='*')

    parser.add_argument('-c', '--confirm', help='interactively tell the user \
the current status of things. if the server is reserved, they are prompted \
to press enter to confirm that they understand this.', action='store_true')

    args = parser.parse_args()
    args.reason = ' '.join(args.reason)

    locked, dat = is_locked()

    if args.confirm:
        if locked:
            print(cols.WARNING + "Be careful!" + cols.ENDC + " Someone is \
running an experiment right now.\nPlease avoid any significant CPU or memory \
usage for the time being.")
            print(f"User: {dat['username']}")
            print(f"Reason: {dat['reason']}")
            if dat['duration'] == -1:
                print("Time remaining: indeterminate (waiting for command to \
terminate)")
            else:
                snds = int(dat['start_time'] + dat['duration'] - time.time())
                print(f"Time remaining: {secs2timestring(snds)}")
            input(cols.WARNING + "Please press ENTER" + cols.ENDC + " to \
confirm that you've read this :)")
            return
        else:
            print(cols.OKGREEN + "No one is running any experiment right now, \
do what you like :)" + cols.ENDC)
            return

    # If no action params given, just return the lock status
    if args.duration == -1 and args.run is None:
        sys.exit(locked)

    # If locked, nicely explain why
    if locked:
        explain_failure(dat)
        sys.exit(os.EX_TEMPFAIL)

    if args.run:  # Lock for indeterminate time until command finishes
        try_lock(args.user, int(time.time()), -1, args.reason)
        cmd = ' '.join(args.run)
        res = os.system(cmd)
        print(f"Finished with exit code {res}; unlocking.")
        release()
    else:  # Lock for certain time and then exit
        dur_secs = timestring2secs(args.duration)

        if dur_secs is None:
            print("Failed to pass time string", file=sys.stderr)
            sys.exit(os.EX_DATAERR)

        print(f"Allocating server for {args.user} for {args.duration} \
({dur_secs}s):\nReason: {args.reason}")

        try_lock(args.user, int(time.time()), dur_secs, args.reason)


if __name__ == '__main__':
    main()