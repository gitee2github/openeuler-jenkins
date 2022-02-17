# -*- encoding=utf-8 -*-
"""
# **********************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2020-2020. All rights reserved.
# [openeuler-jenkins] is licensed under the Mulan PSL v1.
# You can use this software according to the terms and conditions of the Mulan PSL v1.
# You may obtain a copy of Mulan PSL v1 at:
#     http://license.coscl.org.cn/MulanPSL
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v1 for more details.
# Author:
# Create: 2021-05-27
# Description: obs repo as dnf source
# **********************************************************************************
"""
from src.proxy.requests_proxy import do_requests
import logging

logger = logging.getLogger("common")


class OBSRepoSource(object):
    """
    生成obs实时仓作为rpm源的配置
    """
    def __init__(self, repo_host):
        """

        :param repo_host: obs仓库host
        """
        self._current_repo_host = repo_host

    @staticmethod
    def repo_format(repo_id, repo_name, repo_baseurl, priority=None):
        """
        repo内容格式
        :param repo_id:
        :param repo_name:
        :param repo_baseurl:
        :param priority:
        :return:
        """
        if priority:
            return "[{}]\nname={}\nbaseurl={}\nenabled=1\ngpgcheck=0\npriority={}\n".format(repo_id, repo_name, repo_baseurl, priority)
        else:
            return "[{}]\nname={}\nbaseurl={}\nenabled=1\ngpgcheck=0\n".format(repo_id, repo_name,repo_baseurl)

    def generate_repo_info(self, obs_branch_list, arch, repo_name_prefix):
        """
        不同的分支生成不同的repo
        :param obs_branch_list:
        :param arch:
        :param repo_name_prefix:
        :return:
        """
        repo_config = ""
        priority = 1
        for obs_branch in obs_branch_list:
            branch = obs_branch.replace(":", ":/")
            url = "{}/{}/standard_{}".format(self._current_repo_host, branch, arch)
            if do_requests("GET", url) == 0:
                logger.debug("add openstack base repo: %s", url)
                repo_config += self.repo_format(obs_branch, repo_name_prefix + "_" + branch, url, priority)
                priority += 1

        return repo_config
