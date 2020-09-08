# -*- encoding=utf-8 -*-
import os
import shutil
import logging

from src.utils.shell_cmd import shell_cmd_live

logger = logging.getLogger("common")


class OBSProxy(object):
    @staticmethod
    def is_project_has_package(project, package):
        """
        包是否在项目中
        :param project:
        :param package:
        :return:
        """
        return not not OBSProxy.list_project(project, package)

    @staticmethod
    def list_project(project, package=""):
        """
        列出项目下包列表
        :param project:
        :param package:
        :return:
        """
        cmd = "osc ll {} {}".format(project, package)
        ret, rs, _ = shell_cmd_live(cmd, cap_out=True)
        if ret:
            logger.error("list project package error, {}".format(ret))
            return None

        return rs

    @staticmethod
    def list_repos_of_arch(project, package, arch):
        """
        获取包的repo列表
        :param project:
        :param package:
        :return:
        """
        cmd = "osc results {} {} -a {}".format(project, package, arch)
        ret, out, _ = shell_cmd_live(cmd, cap_out=True)
        if ret:
            logger.debug("list obs repos of arch error, {}".format(ret))
            return []

        rs = []
        for line in out:
            repo, arch, state = line.split()
            rs.append({"repo": repo, "state": state})

        return rs

    @staticmethod
    def checkout_package(project, package):
        """
        checkout
        :param project:
        :param package:
        :return: 成功返回True，失败返回False
        """
        # pod cache
        os.path.isdir(project) and shutil.rmtree(project)

        cmd = "osc co {} {}".format(project, package)
        logger.info("osc co {} {}".format(project, package))
        ret, _, _ = shell_cmd_live(cmd, verbose=True)

        if ret:
            logger.error("checkout package error, {}".format(ret))
            return False

        return True

    @staticmethod
    def build_package(project, package, repo, arch, debug=False):
        """
        build
        :param project:
        :param package:
        :param repo:
        :param arch:
        :param debug:
        :return:
        """
        package_path = "{}/{}".format(project, package)
        cmd = "cd {}; osc build {} {} {} --no-verify --clean".format(
            package_path, repo, arch, "--disable-debuginfo" if not debug else "")

        logger.info("osc build {} {} {} --no-verify --clean".format(
            repo, arch, "--disable-debuginfo" if not debug else ""))
        ret, _, _ = shell_cmd_live(cmd, verbose=True)

        if ret:
            logger.error("build package error, {}".format(ret))
            return False

        return True
