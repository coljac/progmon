#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import random
import time
import os
import sys
import curses 
from csv import reader
# from threading import Thread
# from functools import partial
import subprocess
import datetime

def logfile(msg):
    if False:
    # if True:
        with open("log.log", "a") as f:
            f.write("Log: " + msg + "\n")
    pass

def main(stdscr, args):
    # with open("log.log", "w") as f:
        # f.write(str(args))
    poll_interval = args.poll_interval # * 1000
    target = args.target
    filename = args.jobfile 
    command = args.command
    label = args.label
    cmd_type="count"
    postscript = args.postscript
    if args.exists:
        cmd_type = "exists"
    elif args.equals:
        cmd_type = "equals"
    
    curses.curs_set(False)
    curses.use_default_colors()
    for i in range(0, curses.COLORS):
        curses.init_pair(i + 1, i, -1)

    y,x = stdscr.getmaxyx()
    watchpoll = 0
    stdscr.nodelay(1) 


    if args.jobfile is None:
        jobs = [Job(command, target=target, label=label, cmd_type=cmd_type, postscript=postscript)]
    else:
        jobs, ps = parse_input_file(filename)
        if postscript is None:
            postscript = ps

    watcher = Watcher(stdscr, poll_interval=poll_interval, jobs=jobs, continuous=args.continuous, 
            sequential=args.sequential, postscript=postscript, quit_on_end=args.quit)
    progress = 0

    while True:
        try:
            # Poll for updates if necessary
            now = time.time()
            if now - watchpoll > poll_interval:
                watchpoll = now
                watcher.poll()
                # pass 

            c = stdscr.getch()
            if c == ord('q'):
                break  # Exit the while()
            else:
                curses.napms(50)
            done = watcher.update()
            stdscr.refresh() 
            if done:
                break
        # except curses.ERR:
        except curses.error:
            break
    sys.exit(0)


class Watcher(object):
    """ This class maintains a list of jobs - wrappers around some command to be run - 
    and presents a visual representation of the current status of the task compared to 
    a benchmark presented by the user. 
    """
    TICK = "✓"
    CROSS = "✘"
    PAUSED = "⏳"

    def __init__(self, stdscr, jobs=[], poll_interval=2, width=None, sequential=False, continuous=False,
            postscript=None, quit_on_end=False):

        self.start_time = time.time()
        self.screen = stdscr
        self.quit_on_end = quit_on_end
        self.postscript_result = None
        self.postscript = postscript
        self.height, self.width = self.screen.getmaxyx()
        self.logmessage = ""
        self.continuous = continuous
        self.sequential = sequential
        self.cursor = (0, -1)
        self.jobs = jobs
        self.poll_interval = poll_interval
        self.barwidth=width
        self.logmessage = None

    def run_command(self, command):

        if command is None:
            return None 

        task = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        result = task.stdout.read()
        logfile("Running " + command)
        # assert task.wait() == 0

        try:
            returnval = int(result.strip())
        except ValueError:
            returnval = result.strip()
        logfile("Returning: " + str(returnval))
        return returnval

    def poll(self):
        firstjob = None
        for i, job in enumerate(self.jobs):
            # if job.polltime is not None:
                # pass # TODO
            if self.sequential and firstjob is not None:
                job.status = "paused"
                continue
            if not self.continuous and job.status == "complete":
                continue

            # if job.status == "paused" or (job.status == "complete" and not self.continuous):
                # if job.cmd_type == "count":
                    # job.progress = 0
                # continue

            logfile("!" + (str(job)))

            job.status = "running"
            firstjob = job
            if job.cmd_type == "exists":
                logfile("Looking for file " + job.target)
                p = os.path.exists(job.target)
            else:
                p = self.run_command(job.command)
                if type(p) == bytes:
                    p = p.decode("UTF-8")

                job.last_return = p

                logfile("Got type " + str(type(p)))
                if job.cmd_type == "equals":
                    logfile("Comparing '" + p + "' and '" + job.target + "'")
                    p = (p == job.target)
                else:
                    try:
                        prog = int(p)
                    except ValueError:
                        prog = p

            job.progress = p

    def update(self):
        self.height, self.width = self.screen.getmaxyx()
        h_format = curses.A_REVERSE
        self.screen.addstr(0, 0, ("progbar - %.1f seconds" % self.poll_interval).center(self.width), curses.color_pair(0)) # + curses.A_REVERSE)

        for i, j in enumerate(self.jobs):
            # self.screen.addstr(y, startx, self.progbars[i], curses.color_pair(color))
            self.progbar(j, position=i, show=True)

            # if j.label is not None:
                # self.screen.addstr(y, self.barwidth + 20, label, curses.color_pair(0))
            # progress = self.poll(c[1])

        complete_jobs = [j for j in self.jobs if j.status == "complete"]
        logfile("Complete: %d" % len(complete_jobs))

        if self.postscript_result is not None:
            self.screen.addstr(len(self.jobs)*2 + 2, 5, self.postscript_result)
        elif (len(complete_jobs) == len(self.jobs)): # and not self.continuous 
            logfile("Yes, all jobs complete; " + str(self.postscript))
            if self.postscript is not None:
                logfile("running!")
                self.postscript_result = self.run_command(self.postscript)
            if self.quit_on_end:
                return True

        a = datetime.timedelta(seconds=(time.time() - self.start_time))
        self.logmessage = str(a).split('.')[0]


        if self.logmessage:
            self.screen.addstr(self.height-1, 0, self.logmessage)

        return False
            

    def progbar(self, job, show=True, position=0):
        barwidth = self.barwidth
        if barwidth is None:
            barwidth = int(self.width/3)

        y = 2 + (position * 2)
        startx = 4 
        color = 3 # Green
        percent_string = "" 

        if job.cmd_type == "count":
            if type(job.progress) != int:
                color = 2 # red
                percent = 0
                percent_string = "??"
            else: 
                percent = float(job.progress)/float(job.target)
                if percent >= 1:
                    job.status = "complete"
                percent_string = "%0d%%  " % (percent*100)

        # elif job.cmd_type == "exists":
        else:
            if job.progress:
                percent = 1
                color = 3
                job.status = "complete"
            else:
                percent = 0
                color = 4

        if job.status == "paused":
            color = 9
            percent_string = " " + self.PAUSED

        if percent >= 1:
            percent_string = " " + self.TICK

        length = int(barwidth * percent)
        # self.log("%d/%d" % (job.progress, ))

        if length > barwidth:
            length = barwidth
            color = 2
        elif job.status == "complete":
            color = 47

        if job.cmd_type == "equals" and percent == 0 and len(job.last_return) > 0:
            # if len(job.last_return) > 0:
            percent_string = " " + self.CROSS
            progstring = "[" +  job.last_return[0:barwidth-2].center(barwidth) + "] %s  "  % percent_string
        else:
            progstring = (("[" + ("#" * length) + " "*(barwidth-length) + "] %s  " % percent_string))

        # progstring = (("[" + ("#" * length) + " "*(barwidth-length) + "] %0d%%" % (percent*100)))
        h_format = curses.A_BOLD

        self.screen.addstr(y, 5, progstring, curses.color_pair(color)) # + curses.A_REVERSE)
        if job.label is not None:
            label_color = 0
            if job.status == "paused":
                label_color = 247
            # self.screen.setcharset("UTF-8")
            self.screen.addstr(y, barwidth+15, job.label, curses.color_pair(label_color))




    def log(self, message):
        self.logmessage = message

    def spawn(self, target, args=(), kwargs={}):
        # t = Thread(target=target, args=args)
        # if kwargs is not None:
        t = Thread(target=target, args=args, kwargs=kwargs)
        t.setDaemon(True)
        t.start()

class Job(object):
    def __init__(self, command, cmd_type="count", label=None, polltime=None, **kwargs):
        logfile("Job %s %s" % (str(label), str(cmd_type)))
        self.command = command
        self.cmd_type = cmd_type
        self.polltime = polltime
        self.label = label
        self.progress = None
        self.timeout = kwargs.get("timeout", None)
        self.failure = kwargs.get("failure", None)
        self.target = None
        self.last_return = ""
        self.status = "running" # complete, paused, failed

        if cmd_type == "count": # Numerical progress
            try:
                self.target = int(kwargs.get("target", 1))
            except ValueError:
                self.cmd_type = "equals"
                self.target = kwargs.get("target", "")
        elif cmd_type == "exists": # If file exists
            self.target = kwargs.get("target", "job.out")
        elif cmd_type == "equals": # Some string comparison
            self.target = kwargs.get("target", "done")
        elif cmd_type == "qsubfinished": # COmplete when job not found
            self.qsub = kwargs.get("jobid", 0)
        elif cmd_type == "qsubcount":
            self.qsubcount = kwargs.get("target", 0)
    

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return " / ".join([str(bob) for bob in [self.cmd_type, self.command, self.target]])


def parse_input_file(inputfile):
    jobs = []
    # Wait for jobs to finish,target,4,'qq | wc -l' 
    # Look for output file,exists,/home/coljac/spod
    # Wait for some output,equals,'hello there','cat /tmp/progress'

    postscript = None
    with open(inputfile, "r") as inp:
        for line in reader(inp, quotechar="'"):
            if line[0].startswith("!"):
                postscript = " ".join(line)[1:]
                logfile("Got postscript " + postscript)
                continue
            job_label = line[0]
            job_type = line[1]
            target = line[2]
            command = None
            if len(line) > 3:
                command = line[3]
            jobs.append(Job(command, cmd_type=job_type, label=job_label, 
                target=target))
    return jobs, postscript

            

if __name__=="__main__":
    if len(sys.argv) < 2:
        print("progmon -h for help.")
        exit(0)
    parser = argparse.ArgumentParser(description="Watches processes for you. Specify a command to watch and a target " + 
            "number, or provide a file with a list of jobs.\nExample: pb -t 100 'ls . | wc -l'")
    parser.add_argument(
        "-n", "--poll-interval",
        type=float,
        default=2,
        help="Time interval for polling."
    )
    parser.add_argument(
            "-t", "--target",
            type=str,
            default="100",
            help="The target number for the specified process."
        )
    parser.add_argument(
            "-f", "--jobfile",
            type=str,
            default=None,
            help="Input file with list of items to monitor."
            )
    parser.add_argument(
            "-l", "--label",
            type=str,
            default=None,
            help="String label for task."
            )
    parser.add_argument(
            "-q", "--quit",
            action="store_true",
            help="Quit when all jobs complete."
            )
    parser.add_argument(
            "-p", "--postscript",
            type=str,
            default=None,
            help="Command to execute when all tasks complete."
        )

    typegroup = parser.add_mutually_exclusive_group()
    typegroup.add_argument(
            "-x", "--exists",
            action="store_true",
            help="Job looks to see if file specified in target exists."
            )
    typegroup.add_argument(
            "-e", "--equals",
            action="store_true",
            help="Job looks to see if command evaluates to string in target."
            )
    typegroup.add_argument(
            "--count",
            action="store_true",
            help="Job tracks progress of numerical command output with respect to target. (Default)"
            )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
            "-s", "--sequential",
            action="store_true",
            help="(File only) Pause job until earlier jobs complete."
            )
    group.add_argument(
            "-c", "--continuous",
            action="store_true",
            help="Monitor tasks after completion."
            )
    parser.add_argument(
            "--jobfile-help",
            action="store_true",
            help="Display format of job file with examples."
            )
    parser.add_argument("command", help="The command to run, which should evaluate to a number. " + 
        "Ignored if job file specified.", nargs='?')
    args = parser.parse_args()

    if args.jobfile_help:

        print("""
The jobfile should contain a list of jobs, one per line, with the following comma-delimited format:

    <job name or description>,<type of job>,<target>,<command to run>

The type of job can be one of: 

    "count" - show progress towards the specified target as measured by the command
    "exists" - Report on existence of file, specified as the target (command ignored)
    "equals" - Report on whether the command evaluates to the string specified as the target

Examples:

    Wait for 100 files,count,100,'ls outputdir/ | wc -l'
    Wait for finished file,exists,./complete.out
    Wait for status to change,equals,'Status: great','tail -1 job.status'

An optional last line, prefaced with a '!', is the postscript to be executed when all jobs are complete.
        """)
        exit(0)
    curses.wrapper(main, args)
