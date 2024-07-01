# Copyright 2023 Katteli Inc.
# TestFlows.com Open-Source Software Testing Framework (http://testflows.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import re
import os
import textwrap
import hashlib
import difflib
import threading

from importlib.machinery import SourceFileLoader

from .errors import SnapshotError as SnapshotErrorBase
from .mode import *

lock = threading.Lock()


class SnapshotError(SnapshotErrorBase):
    def __init__(self, filename, name, snapshot_value, actual_value, diff=None):
        self.snapshot_value = snapshot_value
        self.actual_value = actual_value
        self.diff = diff
        self.filename = str(filename)
        self.name = str(name)

    def __bool__(self):
        return False

    def __repr__(self):
        r = "SnapshotError("
        r += "\nfilename=" + self.filename
        r += "\nname=" + self.name
        r += '\nsnapshot_value="""\n'
        r += textwrap.indent(self.snapshot_value, " " * 4)
        r += '""",\nactual_value="""\n'
        r += textwrap.indent(self.actual_value, " " * 4)
        r += '""",\ndiff="""\n'
        r += textwrap.indent(
            "\n".join(
                [
                    line.strip("\n")
                    for line in difflib.unified_diff(
                        self.snapshot_value.splitlines(),
                        self.actual_value.splitlines(),
                        self.filename,
                    )
                ]
            ),
            " " * 4,
        )
        r += '\n""")'
        return r


def varname(s):
    """Make valid Python variable name."""
    invalid_chars = re.compile("[^0-9a-zA-Z_]")
    invalid_start_chars = re.compile("^[^a-zA-Z_]+")

    name = invalid_chars.sub("_", str(s))
    name = invalid_start_chars.sub("", name)
    if not name:
        raise ValueError(f"can't convert to valid name '{s}'")
    return name


def write_to_snapshot(fd, name, repr_value):
    """Write entry to snapshot file object."""
    repr_value = repr_value.replace('"""', '""" + \'"""\' + r"""')

    with lock:
        if repr_value.endswith('"'):
            fd.write(f'''{name} = r"""{repr_value[:-1]}""" + '"'\n\n''')
        else:
            fd.write(f'''{name} = r"""{repr_value}"""\n\n''')


def rewrite_snapshot(filename):
    """Rewrite snapshot file."""
    if not filename.endswith(".snapshot"):
        raise ValueError(f"{filename} is not a snapshot")
    if not os.path.exists(filename):
        raise FileNotFoundError(f"does not exist: {filename}")

    module_name = f"snapshot_{hashlib.sha1(os.path.abspath(filename).encode('utf-8')).hexdigest()}"

    with lock:
        snapshot_module = SourceFileLoader(module_name, filename).load_module()

        with open(filename, "w") as fd:
            for name in dir(snapshot_module):
                if name.startswith("__"):
                    continue
                write_to_snapshot(fd, name, getattr(snapshot_module, name))


def snapshot(
    filename,
    repr_value,
    name="snapshot",
    mode=SNAPSHOT_MODE_CHECK | SNAPSHOT_MODE_UPDATE,
):
    """Check representation of the value against a snapshot value
    stored in a Python module.
    """
    name = varname(name) if name != "snapshot" else name

    if os.path.exists(filename):
        module_name = f"snapshot_{hashlib.sha1(os.path.abspath(filename).encode('utf-8')).hexdigest()}"
        snapshot_module = SourceFileLoader(module_name, filename).load_module()

        if hasattr(snapshot_module, name):
            snapshot_value = getattr(snapshot_module, name)
            if not (snapshot_value == repr_value):
                if mode & SNAPSHOT_MODE_CHECK:
                    return SnapshotError(filename, name, snapshot_value, repr_value)
            else:
                return True

    if not (mode & SNAPSHOT_MODE_UPDATE):
        return SnapshotError(filename, name, "", repr_value)

    # write or update snapshot entry
    with open(filename, "a") as fd:
        write_to_snapshot(fd, name=name, repr_value=repr_value)

    if mode & SNAPSHOT_MODE_REWRITE:
        rewrite_snapshot(filename)

    return True


# define version
snapshot.VERSION = 1
