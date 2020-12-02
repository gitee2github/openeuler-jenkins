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
# Create: 2020-09-29
# Description: report obs package build info
# **********************************************************************************
"""

import gevent
from gevent import monkey
monkey.patch_all()
import logging.config
import logging
import os
import argparse
import time
import xml.etree.ElementTree as ET
import json

logger = logging.getLogger("common")


class JobBuildHistory(object):
    @staticmethod
    def get_package_job_duration(project, package, repo, arch):
        """
        获取任务构建时间信息
        :param project:
        :param package:
        :param repo:
        :param arch:
        :return:
        """
        history = OBSProxy.build_history(project, package, repo, arch)
        root = ET.fromstring(history)
        duration = [int(ele.get("duration")) for ele in root.findall("entry")]

        if not duration:
            return {"package": package, "max": 0, "min": 0, "average": 0, "times": 0}

        return {"package": package, "max": max(duration), "min": min(duration),
                "average": sum(duration) / len(duration), "times": len(duration)}

    @staticmethod
    def get_packages_job_duration(project, repo, arch, *packages):
        """
        获取多个包任务构建时间信息
        :param project:
        :param packages:
        :param repo:
        :param arch:
        :return:
        """
        concurrency = 100
        batch = (len(packages) + concurrency - 1) / concurrency

        rs = []
        for index in range(batch):
            works = [gevent.spawn(JobBuildHistory.get_package_job_duration, project, package, repo, arch)
                     for package in packages[index * concurrency: (index + 1) * concurrency]]
            logger.info("{} works, {}/{} ".format(len(works), index + 1, batch))
            gevent.joinall(works)
            for work in works:
                logger.info("{}: {}".format(work.value["package"], work.value))
                rs.append(work.value)

            time.sleep(1)

        rs.sort(key=lambda item: item["max"])
        return rs

    @staticmethod
    def get_jobs_duration(project, repo, arch):
        """
        获取项目下所有包构建时间信息
        :param project:
        :param repo:
        :param arch:
        :return:
        """
        packages = OBSProxy.list_project(project)

        return JobBuildHistory.get_packages_job_duration(project, repo, arch, *packages)


if "__main__" == __name__:
    args = argparse.ArgumentParser()

    args.add_argument("-p", type=str, dest="project", help="obs project")
    args.add_argument("-g", type=str, dest="packages", nargs="+", help="package")
    args.add_argument("-r", type=str, dest="repo", help="repo")
    args.add_argument("-a", type=str, dest="arch", help="arch")
    args.add_argument("-o", type=str, dest="output", help="output file")

    args = args.parse_args()

    not os.path.exists("log") and os.mkdir("log")
    logger_conf_path = os.path.realpath(os.path.join(os.path.realpath(__file__), "../../conf/logger.conf"))
    logging.config.fileConfig(logger_conf_path)
    logger = logging.getLogger("build")

    from src.proxy.obs_proxy import OBSProxy

    if args.packages:
        result = JobBuildHistory.get_packages_job_duration(args.project, args.repo, args.arch, *args.packages)
    else:
        result = JobBuildHistory.get_jobs_duration(args.project, args.repo, args.arch)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f)
