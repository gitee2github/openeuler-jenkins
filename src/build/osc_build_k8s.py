# -*- encoding=utf-8 -*-
# **********************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2020-2020. All rights reserved.
# [openeuler-jenkins] is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#          http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# Author: 
# Create: 2020-09-23
# Description: build single package using obs
# **********************************************************************************

import os
import re
import sys
import logging.config
import logging
import argparse
import warnings
from xml.etree import ElementTree

from src.constant import Constant


class SinglePackageBuild(object):
    """
    build single package using obs
    """
    BUILD_IGNORED_GITEE_BRANCH = ["riscv"]
    PACKAGES_USE_ROOT = ["iproute", "libaio", "A-Ops", "multipath-tools", "libnetfilter_conntrack", "mcelog",
                         "openEuler_chroot", "conntrack-tools", "linux-sgx", "gala-gopher", "iputils"]

    def __init__(self, package, arch, target_branch):
        """
        
        :param package: package name
        :param arch: x86_64 or aarch64
        :param target_branch: branch pull request apply
        """
        self._package = package
        self._arch = arch
        self._branch = target_branch

    def get_need_build_obs_repos(self, project):
        """
        需要构建obs repo列表
        :return: list<dict>
        """
        return OBSProxy.list_repos_of_arch(project, self._package, self._arch, show_exclude=True)

    def build_obs_repos(self, project, repos, spec, work_dir, code_dir):
        """
        build
        :param project: 项目名
        :param repos: obs repo
        :param spec: 指定spec文件
        :param code_dir: 码云代码在本地路径
        :param work_dir:
        :return:
        """
        # osc co
        if not OBSProxy.checkout_package(project, self._package):
            logger.error("checkout ... failed")
            return 1

        logger.info("checkout ... ok")

        logger.info("prepare environ ... ok")

        # osc build
        for repo in repos:
            if repo["state"] == "excluded" and repo["mpac"] == "raspberrypi-kernel":
                logger.info("repo %s:%s excluded", repo["repo"], repo["mpac"])
                continue
            root_build = repo["mpac"] in self.PACKAGES_USE_ROOT
            if not OBSProxy.build_package(
                    project, self._package, repo["repo"], self._arch, spec, repo["mpac"], 
                    root_build=root_build, disable_cpio=True):
                logger.error("build %s ... failed", repo["repo"])
                return 3

            logger.info("build %s ... ok", repo["repo"])

        logger.debug("build all repos ... finished")

        return 0

    def _handle_package_meta(self, project, obs_work_dir, code_path):
        """
        _service文件重组

        <services>
            <service name="tar_scm_kernel_repo">
                <param name="scm">repo</param>
                <param name="url">next/openEuler/perl-Archive-Zip</param>
            </service>
        </services>

        :param project: obs项目
        :param obs_work_dir: obs工作目录
        :param code_path: 代码目录
        :return:
        """
        _service_file_path = os.path.join(obs_work_dir, project, self._package, "_service")
        tree = ElementTree.parse(_service_file_path)

        logger.info("before update meta------")
        ElementTree.dump(tree)
        sys.stdout.flush()

        services = tree.findall("service")

        for service in services:
            if service.get("name") == "tar_scm_repo_docker":
                service.set("name", "tar_local")
            elif service.get("name") == "tar_scm_repo":
                service.set("name", "tar_local")
            elif service.get("name") == "tar_scm_kernel_repo":
                service.set("name", "tar_local_kernel")
            elif service.get("name") == "tar_scm_kernels_repo":
                service.set("name", "tar_local_kernels")
            elif service.get("name") == "tar_scm":
                service.set("name", "tar_local_kernel")

            for param in service.findall("param"):
                if param.get("name") == "scm":
                    param.text = "local"
                elif param.get("name") == "tar_scm":
                    param.text = "tar_local"
                elif param.get("name") == "url":
                    if "openEuler_kernel" in param.text or "LTS_kernel" in param.text \
                            or "openEuler-kernel" in param.text \
                            or "openEuler-20.09_kernel" in param.text:
                        param.text = "{}/{}".format(code_path, "code")  # kernel special logical
                    else:
                        gitee_repo = re.sub(r"\.git", "", param.text.split("/")[-1])
                        param.text = "{}/{}".format(code_path, gitee_repo)

        logger.info("after update meta------")

        ElementTree.dump(tree)
        sys.stdout.flush()
        tree.write(_service_file_path)

    def _prepare_build_environ(self, project, obs_work_dir):
        """
        准备obs build环境
        :param project: obs项目
        :param obs_work_dir: obs工作目录
        :return:
        """
        _process_perl_path = os.path.realpath(os.path.join(os.path.realpath(__file__), "../process_service.pl"))
        _service_file_path = os.path.join(obs_work_dir, project, self._package, "_service")
        _obs_package_path = os.path.join(obs_work_dir, project, self._package)

        cmd = "perl {} -f {} -p {} -m {} -w {}".format(
            _process_perl_path, _service_file_path, project, self._package, _obs_package_path)

        ret, _, _ = shell_cmd_live(cmd, verbose=True)

        if ret:
            logger.error("prepare build environ error, %s", ret)
            return False

        return True

    def build(self, spec, work_dir, code_dir):
        """
        入口
        :param spec: 指定spec文件
        :param work_dir: obs工作目录
        :param code_dir: 代码目录
        :return:
        """
        if self._branch in self.BUILD_IGNORED_GITEE_BRANCH:
            logger.error("branch \"%s\" ignored", self._branch)
            return 0
        if self._branch.lower() in Constant.STOPPED_MAINTENANCE_BRANCH:
            logger.error("branch \"%s\" is no longer maintained!", self._branch)
            return 1

        has_any_repo_build = False
        project = 'home:nicliuqi'
        obs_repos = [{
            'repo': 'standard_' + self._arch.replace('-', '_'),
            'mpac': os.getenv('package'),
            'state': 'succeeded*'
        }]
        ret = self.build_obs_repos(project, obs_repos, spec, work_dir, code_dir)
        if ret > 0:
            logger.debug("build run return %s", ret)
            logger.error("build %s %s %s ... %s", project, self._package, self._arch, "failed")
            return 1     # finish if any error
        else:
            logger.info("build %s %s %s ... %s", project, self._package, self._arch, "ok")
            return 0


def init_args():
    """
    init args
    :return: 
    """
    parser = argparse.ArgumentParser()

    parser.add_argument("-p", type=str, dest="package", help="obs package")
    parser.add_argument("-a", type=str, dest="arch", help="build arch")
    parser.add_argument("-b", type=str, dest="branch", help="target branch that merged to ")
    parser.add_argument("-c", type=str, dest="code", help="code dir path")
    parser.add_argument("-w", type=str, dest="workspace", default=os.getcwd(), help="obs workspace dir path")

    parser.add_argument("-m", type=str, dest="comment_id", help="uniq comment id")
    parser.add_argument("-r", type=str, dest="repo", help="repo")
    parser.add_argument("--pr", type=str, dest="pr", help="pull request")
    parser.add_argument("-t", type=str, dest="account", help="gitee account")

    parser.add_argument("-o", type=str, dest="owner", default="src-openeuler", help="gitee owner")
    parser.add_argument("--spec", type=str, dest="spec", default="", help="spec files")

    return parser.parse_args()


if "__main__" == __name__:
    args = init_args()

    _ = not os.path.exists("log") and os.mkdir("log")
    logger_conf_path = os.path.realpath(os.path.join(os.path.realpath(__file__), "../../conf/logger.conf"))
    logging.config.fileConfig(logger_conf_path)
    logger = logging.getLogger("build")

    logger.info('osc buils k8s start')

    from src.utils.dist_dataset import DistDataset
    from src.proxy.git_proxy import GitProxy
    from src.proxy.obs_proxy import OBSProxy
    from src.proxy.kafka_proxy import KafkaProducerProxy
    from src.utils.shell_cmd import shell_cmd_live

    spb = SinglePackageBuild(args.package, args.arch, args.branch)
    rs = spb.build(args.spec, args.workspace, args.code)
    logger.info('osc build k8s ends')
    sys.exit(rs)
