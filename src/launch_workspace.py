"""Frozen GUI entry point; the console companion owns JSON worker I/O."""
from runtime import initialize
initialize()
from workspace import main

if __name__=='__main__':main()
