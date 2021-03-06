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
"""Trestle Split Command."""
import pathlib
from typing import Dict, List

from ilcli import Command

from trestle.core import const
from trestle.core import utils
from trestle.core.base_model import OscalBaseModel
from trestle.core.commands import cmd_utils
from trestle.core.err import TrestleError
from trestle.core.models.actions import Action, CreatePathAction, WriteFileAction
from trestle.core.models.elements import Element, ElementPath
from trestle.core.models.file_content_type import FileContentType
from trestle.core.models.plans import Plan
from trestle.utils import fs


class SplitCmd(Command):
    """Split subcomponents on a trestle model."""

    name = 'split'

    def _init_arguments(self):
        self.add_argument(
            f'-{const.ARG_FILE_SHORT}',
            f'--{const.ARG_FILE}',
            help=const.ARG_DESC_FILE + ' to split.',
        )
        self.add_argument(
            f'-{const.ARG_ELEMENT_SHORT}',
            f'--{const.ARG_ELEMENT}',
            help=const.ARG_DESC_ELEMENT + ' to split.',
        )

    def _run(self, args):
        """Split an OSCAL file into elements."""
        # get the Model
        args = args.__dict__
        if args[const.ARG_FILE] is None:
            raise TrestleError(f'Argument "-{const.ARG_FILE_SHORT}" is required')

        file_path = pathlib.Path(args[const.ARG_FILE])
        content_type = FileContentType.to_content_type(file_path.suffix)

        # find the base directory of the file
        file_absolute_path = pathlib.Path(file_path.absolute())
        base_dir = file_absolute_path.parent

        model_type, _ = fs.get_stripped_contextual_model(file_absolute_path)

        # FIXME: Handle list/dicts
        model: OscalBaseModel = model_type.oscal_read(file_path)

        element_paths: List[ElementPath] = cmd_utils.parse_element_args(args[const.ARG_ELEMENT].split(','))

        split_plan = self.split_model(model, element_paths, base_dir, content_type)

        # Simulate the plan
        # if it fails, it would throw errors and get out of this command
        split_plan.simulate()

        # If we are here then simulation passed
        # so move the original file to the trash
        cmd_utils.move_to_trash(file_path)

        # execute the plan
        split_plan.execute()

    @classmethod
    def prepare_sub_model_split_actions(
        cls,
        sub_model_item: OscalBaseModel,
        sub_model_dir: pathlib.Path,
        file_prefix: str,
        content_type: FileContentType
    ) -> List[Action]:
        """Create split actions of sub model."""
        actions: List[Action] = []
        file_ext = FileContentType.to_file_extension(content_type)
        model_type = utils.classname_to_alias(type(sub_model_item).__name__, 'json')
        file_name = f'{file_prefix}{const.IDX_SEP}{model_type}{file_ext}'
        sub_model_file = sub_model_dir / file_name
        actions.append(CreatePathAction(sub_model_file))
        actions.append(WriteFileAction(sub_model_file, Element(sub_model_item, model_type), content_type))
        return actions

    @classmethod
    def get_sub_model_dir(cls, base_dir: pathlib.Path, sub_model: OscalBaseModel, dir_prefix: str) -> pathlib.Path:
        """Get the directory path for the given model."""
        model_type = utils.classname_to_alias(type(sub_model).__name__, 'json')
        dir_name = f'{dir_prefix}{const.IDX_SEP}{model_type}'
        sub_model_dir = base_dir / dir_name

        return sub_model_dir

    @classmethod
    def split_model_at_path_chain(
        cls,
        model_obj: OscalBaseModel,
        element_paths: List[ElementPath],
        base_dir: pathlib.Path,
        content_type: FileContentType,
        cur_path_index: int,
        split_plan: Plan,
        strip_root: bool
    ) -> Plan:
        """Recursively split the model at the provided chain of element paths.

        It assumes that a chain of element paths starts at the cur_path_index with the first path ending
        with a wildcard (*)

        It returns the index where the chain of path ends.

        For example, element paths could have a list of paths as below for a `TargetDefinition` model where
        the first path is the start of the chain.

        For each of the sub model described by the first element path (e.g target-defintion.targets.*) in the chain,
        the subsequent paths (e.g. target.target-control-implementations.*) will be applied recursively to retrieve
        the sub-sub models:
        [
            'target-definition.targets.*',
            'target.target-control-implementations.*'
        ]
        for a command like below:
           trestle split -f target.yaml -e target-definition.targets.*.target-control-implementations.*
        """
        # assume we ran the command below:
        # trestle split -f target.yaml -e target-definition.targets.*.target-control-implementations.*

        if split_plan is None:
            raise TrestleError('Split plan must have been initialized')

        if cur_path_index < 0:
            raise TrestleError('Current index of the chain of paths cannot be less than 0')

        # if there are no more element_paths, return the current plan
        if cur_path_index >= len(element_paths):
            return cur_path_index

        # initialize local variables
        element = Element(model_obj)
        stripped_field_alias = []

        # get the sub_model specified by the element_path of this round
        element_path = element_paths[cur_path_index]
        is_parent = cur_path_index + 1 < len(element_paths) and element_paths[cur_path_index
                                                                              + 1].get_parent() == element_path

        # check that the path is not multiple level deep
        path_parts = element_path.get()
        if path_parts[-1] == ElementPath.WILDCARD:
            path_parts = path_parts[:-1]

        if len(path_parts) > 2:
            msg = 'Trestle supports split of first level children only, '
            msg += f'found path "{element_path}" with level = {len(path_parts)}'
            raise TrestleError(msg)

        sub_models = element.get_at(element_path, False)  # we call sub_models as in plural, but it can be just one
        if sub_models is None:
            return cur_path_index

        # assume cur_path_index is the end of the chain
        # value of this variable may change during recursive split of the sub-models below
        path_chain_end = cur_path_index

        # if wildcard is present in the element_path and the next path in the chain has current path as the parent,
        # we need to split recursively and create separate file for each sub item
        # for example, in the first round we get the `targets` using the path `target-definition.targets.*`
        # so, now we need to split each of the target recursively. Note that target is an instance of dict
        # However, there can be other sub_model, which is of type list
        if is_parent and element_path.get_last() is not ElementPath.WILDCARD:
            # create dir for all sub model items
            sub_models_dir = base_dir / element_path.to_root_path()

            sub_model_plan = Plan()
            path_chain_end = cls.split_model_at_path_chain(
                sub_models, element_paths, sub_models_dir, content_type, cur_path_index + 1, sub_model_plan, True
            )
            sub_model_actions = sub_model_plan.get_actions()
            split_plan.add_actions(sub_model_actions)
        elif element_path.get_last() == ElementPath.WILDCARD:
            # create dir for all sub model items. e.g. `targets` or `groups`
            sub_models_dir = base_dir / element_path.to_file_path()

            # extract sub-models into a dict with appropriate prefix
            sub_model_items: Dict[str, OscalBaseModel] = {}
            if isinstance(sub_models, list):
                for i, sub_model_item in enumerate(sub_models):
                    # e.g. `groups/00000_groups/`
                    prefix = str(i).zfill(const.FILE_DIGIT_PREFIX_LENGTH)
                    sub_model_items[prefix] = sub_model_item
            elif isinstance(sub_models, dict):
                # prefix is the key of the dict
                sub_model_items = sub_models
            else:
                # unexpected sub model type for multi-level split with wildcard
                raise TrestleError(f'Sub element at {element_path} is not of type list or dict for further split')

            # process list sub model items
            for key in sub_model_items:
                prefix = key
                sub_model_item = sub_model_items[key]

                # recursively split the sub-model if there are more element paths to traverse
                # e.g. split target.target-control-implementations.*
                require_recursive_split = cur_path_index + 1 < len(element_paths) and element_paths[
                    cur_path_index + 1].get_parent() == element_path

                if require_recursive_split:
                    # prepare individual directory for each sub-model
                    # e.g. `targets/<UUID>__target/`
                    sub_model_dir = cls.get_sub_model_dir(sub_models_dir, sub_model_item, prefix)
                    sub_model_plan = Plan()
                    path_chain_end = cls.split_model_at_path_chain(
                        sub_model_item,
                        element_paths,
                        sub_model_dir,
                        content_type,
                        cur_path_index + 1,
                        sub_model_plan,
                        True
                    )
                    sub_model_actions = sub_model_plan.get_actions()
                else:
                    sub_model_actions = cls.prepare_sub_model_split_actions(
                        sub_model_item, sub_models_dir, prefix, content_type
                    )

                split_plan.add_actions(sub_model_actions)
        else:
            # the chain of path ends at the current index.
            # so no recursive call. Let's just write the sub model to the file and get out
            sub_model_file = base_dir / element_path.to_file_path(content_type)
            split_plan.add_action(CreatePathAction(sub_model_file))
            split_plan.add_action(
                WriteFileAction(sub_model_file, Element(sub_models, element_path.get_element_name()), content_type)
            )

        # Strip the root model and add a WriteAction for the updated model object in the plan
        if strip_root:
            stripped_field_alias.append(element_path.get_element_name())
            stripped_root = model_obj.stripped_instance(stripped_fields_aliases=stripped_field_alias)
            root_file = base_dir / element_path.to_root_path(content_type)
            split_plan.add_action(CreatePathAction(root_file))
            wrapper_alias = utils.classname_to_alias(stripped_root.__class__.__name__, 'json')
            split_plan.add_action(WriteFileAction(root_file, Element(stripped_root, wrapper_alias), content_type))

        # return the end of the current path chain
        return path_chain_end

    @classmethod
    def split_model(
        cls,
        model_obj: OscalBaseModel,
        element_paths: List[ElementPath],
        base_dir: pathlib.Path,
        content_type: FileContentType,
    ) -> Plan:
        """Split the model at the provided element paths.

        It returns a plan for the operation
        """
        # assume we ran the command below:
        # trestle split -f target.yaml
        #   -e 'target-definition.metadata,
        #   target-definition.targets.*.target-control-implementations.*'

        # initialize plan
        split_plan = Plan()

        # loop through the element path list and update the split_plan
        stripped_field_alias = []
        cur_path_index = 0
        while cur_path_index < len(element_paths):
            # extract the sub element name for each of the root path of the path chain
            element_path = element_paths[cur_path_index]

            if element_path.get_parent() is None and len(element_path.get()) > 1:
                stripped_part = element_path.get()[1]
                if stripped_part == ElementPath.WILDCARD:
                    stripped_field_alias.append('__root__')
                else:
                    stripped_field_alias.append(stripped_part)

            # split model at the path chain
            cur_path_index = cls.split_model_at_path_chain(
                model_obj, element_paths, base_dir, content_type, cur_path_index, split_plan, False
            )

            cur_path_index += 1

        # strip the root model object and add a WriteAction
        stripped_root = model_obj.stripped_instance(stripped_fields_aliases=stripped_field_alias)
        root_file = base_dir / element_paths[0].to_root_path(content_type)
        split_plan.add_action(CreatePathAction(root_file, True))
        wrapper_alias = utils.classname_to_alias(stripped_root.__class__.__name__, 'json')
        split_plan.add_action(WriteFileAction(root_file, Element(stripped_root, wrapper_alias), content_type))

        return split_plan
