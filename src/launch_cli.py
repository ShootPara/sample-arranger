"""Frozen console entry point; dispatch is an allowlist, never arbitrary Python."""
import sys
from runtime import initialize
import commands
import catalog


def main():
    initialize()
    module='commands'
    if len(sys.argv)>=3 and sys.argv[1]=='--module':
        module=sys.argv[2];sys.argv=[sys.argv[0],*sys.argv[3:]]
    if module not in ('commands','catalog'):raise SystemExit('unsupported internal module')
    (commands if module=='commands' else catalog).main()


if __name__=='__main__':main()
