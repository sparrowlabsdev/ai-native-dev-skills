#!/usr/bin/env python3
"""A scripted stand-in for a model, for testing the command driver.

Reads the transcript on stdin and answers according to how many replies it has
already given: first a broken file, then the fix, then finish.
"""
import sys

transcript = sys.stdin.read()
replies = transcript.count("##### MODEL REPLY")

if "CHECK PASSED" in transcript.rsplit("##### HARNESS TURN", 1)[-1]:
    print("Done.\n````\n=== CALL finish ===\nAdded hello.txt; the check passes.\n=== END ===\n````")
elif replies == 0:
    print("Looking and writing.\n````\n"
          "=== CALL list_files ===\n"
          "=== CALL read_file path=README.md ===\n"
          "=== CALL read_file path=.env ===\n"
          "=== CALL write_file path=../outside.txt ===\nnope\n=== END ===\n"
          "=== CALL write_file path=hello.txt ===\nBROKEN\n=== END ===\n"
          "=== CALL run_check ===\n"
          "=== CALL finish ===\nall good\n=== END ===\n"
          "````")
else:
    print("Fixing.\n````\n"
          "=== CALL write_file path=hello.txt ===\nhello\n=== END ===\n"
          "=== CALL run_check name=default ===\n"
          "````")
