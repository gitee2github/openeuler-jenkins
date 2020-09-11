# -*- encoding=utf-8 -*-
import os
import logging

from src.proxy.git_proxy import GitProxy
from src.utils.shell_cmd import shell_cmd_live

logger = logging.getLogger("ac")


class GiteeRepo(object):
    """
    analysis src-openeuler repo
    """
    def __init__(self, work_dir, decompress_dir):
        self._work_dir = work_dir
        self._decompress_dir = decompress_dir

        self._patch_files = []
        self._compress_files = []

        self.spec_file = None
        self.patch_dir_mapping = {}

        self.find_file_path()

    def find_file_path(self):
        """
        compress file, patch file, diff file, spec file
        """
        for dirpath, dirnames, filenames in os.walk(self._work_dir):
            for filename in filenames:
                rel_file_path = os.path.join(dirpath, filename).replace(self._work_dir, "").lstrip("/")
                if self.is_compress_file(filename):
                    logger.debug("find compress file: {}".format(rel_file_path))
                    self._compress_files.append(rel_file_path)
                elif self.is_patch_file(filename):
                    logger.debug("find patch file: {}".format(rel_file_path))
                    self._patch_files.append(rel_file_path)
                elif self.is_spec_file(filename):
                    logger.debug("find spec file: {}".format(rel_file_path))
                    self.spec_file = filename

    def patch_files_not_recursive(self):
        """
        获取当前目录下patch文件
        """
        return [filename for filename in os.listdir(self._work_dir)
                if os.path.isfile(os.path.join(self._work_dir, filename)) and self.is_patch_file(filename)]

    def decompress_file(self, file_path):
        """
        解压缩文件
        :param file_path:
        :return:
        """
        if self._is_compress_zip_file(file_path):
            decompress_cmd = "cd {}; unzip -d {} {}".format(self._work_dir, self._decompress_dir, file_path)
        elif self._is_compress_tar_file(file_path):
            decompress_cmd = "cd {}; tar -C {} -xavf {}".format(self._work_dir, self._decompress_dir, file_path)
        else:
            logger.warning("unsupport compress file: {}".format(file_path))
            return False

        ret, _, _ = shell_cmd_live(decompress_cmd)
        if ret:
            logger.debug("decompress failed")
            return False

        return True

    def decompress_all(self):
        """
        解压缩所有文件
        :return: 0/全部成功，1/部分成功，-1/全部失败
        """
        if not self._compress_files:
            logger.warning("no compressed source file")
        rs = [self.decompress_file(filepath) for filepath in self._compress_files]

        return 0 if all(rs) else (1 if any(rs) else -1)

    def apply_patch(self, patch, max_leading=5):
        """
        尝试所有路径和leading
        :param patch: 补丁
        :param max_leading: leading path
        """
        logger.debug("apply patch {}".format(patch))
        for patch_dir in [filename for filename in os.listdir(self._decompress_dir) 
                if os.path.isdir(os.path.join(self._decompress_dir, filename))] + ["."]:
            if patch_dir.startswith(".git"):
                continue
            for leading in xrange(max_leading + 1):
                logger.debug("try dir {} -p{}".format(patch_dir, leading))
                if GitProxy.apply_patch_at_dir(os.path.join(self._decompress_dir, patch_dir), 
                        os.path.join(self._work_dir, patch), leading):
                    logger.debug("patch success".format(leading))
                    self.patch_dir_mapping[patch] = patch_dir
                    return True

        logger.info("apply patch {} failed".format(patch))
        return False

    def apply_all_patches(self, *patches):
        """
        打补丁通常是有先后顺序的
        :param patches: 需要打的补丁
        """
        if not self._compress_files:
            logger.debug("no compress source file, not need apply patch")
            return 0

        rs = []
        for patch in patches:
            if patch in set(self._patch_files):
                rs.append(self.apply_patch(patch))
            else:
                logger.error("patch {} not exist".format(patch))
                rs.append(False)

        return 0 if all(rs) else (1 if any(rs) else -1)

    @staticmethod
    def is_py_file(filename):
        return filename.endswith((".py",))

    @staticmethod
    def is_go_file(filename):
        return filename.endswith((".go",))

    @staticmethod
    def is_c_cplusplus_file(filename):
        return filename.endswith((".c", ".cpp", ".cc", ".cxx", ".c++", ".h", ".hpp", "hxx"))

    @staticmethod
    def is_code_file(filename):
        return GiteeRepo.is_py_file(filename) \
               or GiteeRepo.is_go_file(filename) \
               or GiteeRepo.is_c_cplusplus_file(filename)

    @staticmethod
    def is_patch_file(filename):
        return filename.endswith((".patch", ".diff"))

    @staticmethod
    def is_compress_file(filename):
        return GiteeRepo._is_compress_tar_file(filename) or GiteeRepo._is_compress_zip_file(filename)

    @staticmethod
    def _is_compress_zip_file(filename):
        return filename.endswith((".zip",))

    @staticmethod
    def _is_compress_tar_file(filename):
        return filename.endswith((".tar.gz", ".tar.bz", ".tar.bz2", ".tar.xz", "tgz"))

    @staticmethod
    def is_spec_file(filename):
        return filename.endswith((".spec",))
