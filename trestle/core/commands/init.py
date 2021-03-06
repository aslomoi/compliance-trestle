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
"""Trestle Init Command."""

import os
from shutil import copyfile

from ilcli import Command

from pkg_resources import resource_filename

import trestle.core.const as const


class InitCmd(Command):
    """Initialize a trestle working directory."""

    name = 'init'

    def _run(self, args):
        """Create a trestle project in the current directory."""
        dir_path = os.getcwd()

        try:
            # Create directories
            self._create_directories()

            # Create config file
            self._copy_config_file()

            self.out(f'Initialized trestle project successfully in {dir_path}')

        except BaseException as err:
            self.err(f'Initialization failed: {err}')
            return 1

    def _create_directories(self):
        """Create the directory tree if it does not exist."""
        # Prepare directory list to be created
        directory_list = [const.TRESTLE_CONFIG_DIR]
        for model_dir in const.MODELTYPE_TO_MODELMODULE.keys():
            directory_list.append(model_dir)
            directory_list.append(os.path.join(const.TRESTLE_DIST_DIR, model_dir))

        # Create directories
        for directory in directory_list:
            os.makedirs(name=directory, exist_ok=True)

    def _copy_config_file(self):
        """Copy the initial config.ini file to .trestle directory."""
        source_path = resource_filename('trestle.resources', const.TRESTLE_CONFIG_FILE)
        destination_path = os.path.join(const.TRESTLE_CONFIG_DIR, const.TRESTLE_CONFIG_FILE)
        copyfile(source_path, destination_path)
