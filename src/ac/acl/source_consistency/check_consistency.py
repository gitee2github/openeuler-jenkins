import hashlib
import logging
import os
import re
import stat
import shutil
import sqlite3
import subprocess
from sqlite3 import Error

from src.ac.framework.ac_base import BaseCheck
from src.ac.framework.ac_result import FAILED, SUCCESS, WARNING

logger = logging.getLogger("ac")


class CheckSourceConsistency(BaseCheck):
    """
    check source consistence
    """

    def __init__(self, workspace, repo, conf=None):
        super(CheckSourceConsistency, self).__init__(workspace, repo, conf)

        self._work_dir = os.path.join(workspace, "source_consistency")
        shutil.copytree(os.path.join(workspace, repo), self._work_dir)
        self._repo = repo
        self.temp_txt_path = os.path.join(self._work_dir, "temp.txt")
        self.rpmbuild_dir = os.path.join(workspace, "rpmbuild")
        self.rpmbuild_build_path = os.path.join(self.rpmbuild_dir, "BUILD")
        self.rpmbuild_sources_path = os.path.join(self.rpmbuild_dir, "SOURCES")
        self.database_path = "source_clean.db"
        self.con = self.create_connection()
        self.ask_warning = "If you have some questions, you can ask q_qiutangke@163.com!"

    def __call__(self, *args, **kwargs):
        """
        入口函数
        :param args:
        :param kwargs:
        :return:
        """
        logger.info("check %s source consistency. If sha256sum of repo source package is different from Official"
                    " website, check fail", self._repo)
        _ = not os.path.exists("log") and os.mkdir("log")
        try:
            return self.start_check_with_order("source_consistency")
        finally:
            if self.con is not None:
                self.con.close()
            self.clear_temp()

    @staticmethod
    def get_sha256sum(package):
        """
        计算文件的sha256sum值
        :param package:包路径
        :return:
        """
        logger.info("getting sha256sum of native source package...")
        native_sha256sum = ""
        try:
            with open(package, "rb") as f:
                sha256obj = hashlib.sha256()
                sha256obj.update(f.read())
                native_sha256sum = sha256obj.hexdigest()
        except Exception as e:
            logger.warning(e)
        if native_sha256sum == "":
            try:
                native_sha256sum = os.popen("sha256sum {0}".format(package)).read().split()[0]
            except Exception as e:
                logger.warning(e)
        return native_sha256sum.strip()

    def get_package_name(self, url):
        """
        从文件列表或者url中获取包名
        """
        package_name = os.popen("ls -S {0} |grep -v .spec |grep -v .yaml |grep -v .patch |grep -v .md |head -n "
                                "1".format(self._work_dir)).read().split()[0]
        if package_name == "":
            package_name = os.path.basename(url)
        return package_name

    def check_source_consistency(self):
        """
        检查源码包是否一致
        :return:
        """
        if not os.path.exists(os.path.join(self.rpmbuild_dir, "SOURCES")):
            os.makedirs(os.path.join(self.rpmbuild_dir, "SOURCES"))
        source_url = self.get_source_url()
        if source_url == "":
            logger.warning("Source keywords of spec content are invalid or spec content is illegal. " +
                           self.ask_warning)
            return WARNING

        package_name = self.get_package_name(source_url)
        if package_name not in os.listdir(self._work_dir):
            logger.warning("no source package file in the repo, the package name is " + package_name + ". " +
                           self.ask_warning)
            return WARNING

        native_sha256sum = self.get_sha256sum(os.path.join(self._work_dir, package_name))
        if native_sha256sum == "":
            logger.warning("get sha256sum of native source package failed, internal error. " + self.ask_warning)
            return WARNING

        remote_sha256sum = self.get_sha256sum_from_url(source_url)
        if remote_sha256sum == "":
            logger.warning("Failed to get sha256sum of official website source package, there is no sha256sum in "
                           "the system database")
            detail_info = self.check_spec_validity()
            if detail_info == "maybe url is unreachable":
                logger.warning("Maybe url is unreachable, you need to check the connectivity of url. If connectivity is"
                               " good, please ignore this warning! " + self.ask_warning)
                return WARNING
            else:
                logger.warning(detail_info + ", please check spec file! " + self.ask_warning)
                return WARNING

        if native_sha256sum != remote_sha256sum:
            logger.error("The sha256sum of source package is inconsistency, maybe you modified source code, "
                         "you must let the source package keep consistency with official website source package. " +
                         self.ask_warning)
            return FAILED

        return SUCCESS

    def get_source_url(self):
        """
        获取spec文件中的Source URL
        :return:
        """
        spec_name = ""
        files_list = os.listdir(self._work_dir)
        if len(files_list) == 0:
            logger.error("copy repo error, please check!")
            return ""
        if self._repo + ".spec" not in files_list:
            logger.warning("no such spec file: " + self._repo + ".spec")
            for file_name in files_list:
                if file_name.endswith(".spec"):
                    spec_name = file_name
                    break
            if spec_name == "":
                logger.error("no spec file, please check!")
                return ""
        source_url = self.get_source_from_spec(spec_name)
        # If program can't get source url from spec, try to get source url by rpmbuild
        if source_url == "":
            source_url = self.get_source_from_rpmbuild(spec_name)
        return source_url

    def check_spec_validity(self):
        """
        检查spec文件的合法性
        :return:
        """
        spec_name = ""
        files_list = os.listdir(self._work_dir)
        if self._repo + ".spec" not in files_list:
            spec_file_list = []
            for temp_file in files_list:
                if temp_file.endswith(".spec"):
                    spec_file_list.append(temp_file)
            if len(spec_file_list) == 1:
                spec_name = os.path.join(self._work_dir, spec_file_list[0])
            elif len(spec_file_list) > 1:
                for s_file in spec_file_list:
                    if self._repo in s_file or s_file in self._repo:
                        spec_name = os.path.join(self._work_dir, s_file)
                        break
            if spec_name == "":
                return "no spec file"
        else:
            spec_name = os.path.join(self._work_dir, self._repo + ".spec")
        source_url = self.spectool_check_source(spec_name)
        if not source_url.startswith("http"):
            return "source url format error"
        return "maybe url is unreachable"

    def get_source_from_rpmbuild(self, spec_name=""):
        """
        rpmbuild解析出可查询的Source URL
        :param spec_name:spec文件名
        :return:
        """
        if spec_name == "":
            spec_name = self._repo + ".spec"
        spec_file = os.path.join(self._work_dir, spec_name)
        self.generate_new_spec(spec_file)
        source_url = self.do_rpmbuild()
        return source_url

    def get_source_from_spec(self, spec_name=""):
        """
        spec文件中得到可查询的Source URL
        :param spec_name:spec文件名
        :return:
        """
        if spec_name == "":
            spec_name = self._repo + ".spec"
        spec_file = os.path.join(self._work_dir, spec_name)
        if not os.path.exists(spec_file):
            temp_file_list = os.listdir(self._work_dir)
            spec_file_list = []
            for temp_file in temp_file_list:
                if temp_file.endswith(".spec"):
                    spec_file_list.append(temp_file)
            if len(spec_file_list) == 1:
                spec_file = os.path.join(self._work_dir, spec_file_list[0])
            elif len(spec_file_list) > 1:
                for s_file in spec_file_list:
                    if self._repo in s_file or s_file in self._repo:
                        spec_file = os.path.join(self._work_dir, s_file)
                        break
            else:
                return ""
        source_url = self.spectool_check_source(spec_file)
        return source_url

    def spectool_check_source(self, spec_file):
        """
        执行spectool命令
        :param spec_file:spec文件名
        :return:
        """
        ret = subprocess.check_output(["/usr/bin/spectool", "-S", spec_file], shell=False)
        content = ret.decode('utf-8').strip()
        source_url = content.split(os.linesep)[0].strip() if os.linesep in content else content.strip()
        if ":" in source_url:
            source_url = ":".join(source_url.split(":")[1:]).strip()
        elif "No such file or directory" in source_url:
            return ""
        return source_url

    def generate_new_spec(self, spec_file):
        """
        读取spec文件并生成新的spec文件
        :param spec_file:spec文件名
        :return:
        """
        logger.info("reading spec file : %s ...", os.path.basename(spec_file))

        new_spec_file = os.path.join(self.rpmbuild_sources_path, "get_source.spec")
        cond_source = re.compile("^Source0*")
        source_url = ""
        new_spec_content = ""
        with open(spec_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("%prep"):
                    break
                elif cond_source.match(line) or re.match("^Source.*", line):
                    if source_url == "":
                        if ":" in line:
                            source_url = ":".join(line.split(":")[1:]).strip()
                new_spec_content += line + os.linesep
        new_spec_content += self.get_prep_function(source_url)
        logger.info("generating new spec file ...")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        modes = stat.S_IWUSR | stat.S_IRUSR
        with os.fdopen(os.open(new_spec_file, flags, modes), 'w') as f:
            f.write(new_spec_content)

    def get_prep_function(self, url):
        """
        生成spec文件%prep部分的内容
        :param url:source0的值
        :return:
        """
        logger.info("generating %prep function")
        function_content = "%prep" + os.linesep
        function_content += "source={0}".format(url) + os.linesep
        function_content += "cd {0}".format(self.rpmbuild_sources_path) + os.linesep
        function_content += "echo $source > {0}".format(self.temp_txt_path) + os.linesep
        return function_content

    def do_rpmbuild(self):
        """
        对新生成的spec文件执行rpmbuild
        :return:
        """
        logger.info("start to do rpmbuild")
        new_spec_file = os.path.join(self.rpmbuild_sources_path, "get_source.spec")
        res = os.system("rpmbuild -bp --nodeps {0} --define \"_topdir {1}\"".format(new_spec_file, self.rpmbuild_dir))
        if res != 0:
            logger.error("do rpmbuild fail")
        if not os.path.exists(self.temp_txt_path):
            return ""
        with open(self.temp_txt_path, "r") as f:
            source_url = f.read().strip()
        return source_url

    def create_connection(self):
        """
        与数据库建立连接
        :return:
        """
        logger.info("getting connection with source_clean.db ...")
        try:
            if os.path.exists(self.database_path):
                con = sqlite3.connect(self.database_path)
                return con
        except Error:
            logger.error(Error)
        return None

    def get_sha256sum_from_url(self, url):
        """
        查询数据库，获取url的sha256sum值
        :param url:source0的值
        :return:
        """
        logger.info("getting sha256sum of remote source package from source_clean.db ...")
        if self.con is None:
            logger.warning("failed to connect to database")
            return ""
        cursor_obj = self.con.cursor()
        cursor_obj.execute("SELECT sha256sum FROM source_package WHERE url = ?", (url,))
        row = cursor_obj.fetchone()
        if row:
            return row[0]
        return ""

    def clear_temp(self):
        """
        清理生成的中间文件
        :return:
        """
        if os.path.exists(self._work_dir):
            shutil.rmtree(self._work_dir)
        shutil.rmtree(self.rpmbuild_dir)
