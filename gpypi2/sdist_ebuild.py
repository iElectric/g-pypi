#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import distutils
from distutils.core import Command
from distutils.dist import Distribution
from ConfigParser import SafeConfigParser, NoOptionError, NoSectionError

from gpypi2.enamer import Enamer
from gpypi2.ebuild import Ebuild
from gpypi2.config import Config, ConfigManager


distutils_path = os.path.dirname(os.path.abspath(distutils.__file__))

class sdist_ebuild(Command):
    description = "create an ebuild file for Gentoo Linux"
    path_to_distutils_conf = os.path.join(distutils_path, 'distutils.cfg')

    user_options = [
        ('config-file=', 'c',
         "GPyPi configuration file"
         "[default: /etc/gpypi2]"),
        ('dist-dir=', 'd',
         "directory to put the source distribution archive(s) in "
         "[default: dist]"),
        ]

    argparse_config = {
        'overwrite': True,
    }
    default_format = {'posix': 'ebuild', 'nt': '' }

    def initialize_options (self):
        self.dist_dir = None

    def finalize_options (self):
        if self.dist_dir is None:
            self.dist_dir = "dist"

        if not os.path.isdir(self.dist_dir):
            os.makedirs(self.dist_dir)

    @classmethod
    def register(cls):
        """Writes gpypi2 project into distutils commmand_packages settings."""
        conf = SafeConfigParser()
        conf.read(cls.path_to_distutils_conf)

        d = Distribution()
        try:
            d.command_packages = conf.get('global', 'command_packages')
        except (NoOptionError, NoSectionError):
            pkg = []
            conf.add_section('global')
        else:
            pkg = d.get_command_packages()
        if 'gpypi2' not in pkg:
            pkg.append('gpypi2')
            conf.set('global', 'command_packages', ','.join(pkg))
            conf.write(open(cls.path_to_distutils_conf, 'w'))

    def run(self):
        """"""
        # TODO: configure logging
        self.argparse_config.update({
            'up_pn': self.distribution.get_name(),
            'up_pv': self.distribution.get_version(),
        })

        mgr = ConfigManager.load_from_ini("/etc/gpypi2")
        mgr.configs['argparse'] = Config(self.argparse_config)
        mgr.configs['setup_py'] = Config.from_setup_py(Enamer.parse_setup_py(self.distribution))
        # TODO: config option for ini
        ebuild = Ebuild(mgr)
        ebuild.unpacked_dir = os.getcwd()
        to = os.path.join(self.dist_dir, ebuild['p'] + '.ebuild')
        ebuild.create(to)
        print 'ebuild saved to %s' % to
