# -*- mode:python; coding:utf-8 -*-
# Copyright (c) 2020 IBM Corp. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Starting point for the Trestle CLI."""

from ilcli import Command

from trestle.__init__ import __version__
from trestle.core.commands.add import AddCmd
from trestle.core.commands.assemble import AssembleCmd
from trestle.core.commands.create import CreateCmd
from trestle.core.commands.import_ import ImportCmd
from trestle.core.commands.init import InitCmd
from trestle.core.commands.merge import MergeCmd
from trestle.core.commands.remove import RemoveCmd
from trestle.core.commands.replicate import ReplicateCmd
from trestle.core.commands.split import SplitCmd
from trestle.core.commands.validate import ValidateCmd


class Trestle(Command):
    """Manage OSCAL files in a human friendly manner."""

    subcommands = [
        InitCmd, CreateCmd, SplitCmd, MergeCmd, ReplicateCmd, AddCmd, RemoveCmd, ValidateCmd, ImportCmd, AssembleCmd
    ]

    def _init_arguments(self):
        self.add_argument(
            '-V',
            '--version',
            help='Display the version of trestle.',
            action='version',
            version=f'Trestle version v{__version__}'
        )
        self.add_argument('-v', '--verbose', help='Display verbose output.', action='count', default=1)


def run():
    """Run the test cli."""
    exit(Trestle().run())


if __name__ == '__main__':
    run()
