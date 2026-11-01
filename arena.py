#!/usr/bin/env python3
"""入口脚本：python arena.py "你的命题" """

import sys

from apps.arena.cli import main

if __name__ == "__main__":
    sys.exit(main())
