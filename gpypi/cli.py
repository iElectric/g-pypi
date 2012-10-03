#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Command-line code for :mod:`gpypi`

"""

import os
import sys
import pdb
import logging

import argparse

from yolk.pypi import CheeseShop
from yolk.yolklib import get_highest_version
from yolk.setuptools_support import get_download_uri

from gpypi import __version__
from gpypi.exc import *
from gpypi.enamer import Enamer
from gpypi.config import Config, ConfigManager
from gpypi.ebuild import Ebuild
from gpypi.portage_utils import PortageUtils
from gpypi.utils import PortageFormatter, PortageStreamHandler

# Portages' security level
from portage.data import secpass, portage_gid

log = logging.getLogger(__name__)


class GPyPI(object):
    """
    Main class for GPyPi interface

    :param package_name: case-insensitive package name
    :type package_name: string

    :param version: package version
    :type version: string

    :param options: command-line options
    :type options: ArgParse options

    """

    def __init__(self, package_name, version, options):
        self.package_name = package_name
        self.version = version
        self.options = options
        self.tree = [(package_name, version)]
        self.pypi = CheeseShop()

    def create_ebuilds(self):
        """
        Create ebuild for given package_name and any ebuilds for dependencies
        if needed. If no version is given we use the highest available.

        """
        while len(self.tree):
            (project_name, version) = self.tree.pop(0)
            self.package_name = project_name
            self.version = version
            requires = self.do_ebuild()
            if requires:
                for req in requires:
                    if self.options.no_deps:
                        pass
                    else:
                        self.handle_dependencies(req.project_name)
            # TODO: disable some options after first ebuild is created
            #self.options.overwrite = False
            #self.options.category = None

    def handle_dependencies(self, project_name):
        """Add dependency if not already in self.tree"""
        pkgs = []
        if len(self.tree):
            for deps in self.tree:
                pkgs.append(deps[0])

        if project_name not in pkgs:
            # TODO: document that we can not query pypi with version spec or use distutils2
            # for dependencies
            self.tree.append((project_name, None))
            log.info("Dependency needed: %s" % project_name)

    def url_from_pypi(self):
        """
        Query PyPI to find a package's URI

        :returns: source URL string

        """
        try:
            return self.pypi.get_download_urls(self.package_name, self.version, pkg_type="source")[0]
        except IndexError:
            return None

    def url_from_setuptools(self):
        """
        Use setuptools to find a package's URI

        :returns: source URL string or None

        """
        #if self.options.subversion:
        #    src_uri = get_download_uri(self.package_name, "dev", "source")
        #else:
        return get_download_uri(self.package_name, self.version, "source", self.options.index_url)

    def find_uri(self, method="all"):
        """
        Returns download URI for package
        If no package version was given it returns highest available
        Setuptools should find anything xml-rpc can and more.

        :param method: download method can be 'xml-rpc', 'setuptools', or 'all'
        :type method: string

        :returns download_url string

        """
        download_url = None

        if method == "all" or method == "xml-rpc":
            download_url = self.url_from_pypi()

        if (method == "all" or method == "setuptools") and not download_url:
            #Sometimes setuptools can find a package URI if PyPI doesn't have it
            download_url = self.url_from_setuptools()

        # TODO: configuratior
        log.debug("Package URI: %s " % download_url)

        return download_url

    def do_ebuild(self):
        """
        Get SRC_URI using PyPI and attempt to create ebuild

        :returns: tuple with exit code and pkg_resources requirement

        """
        #Get proper case for project name:
        (self.package_name, versions) = self.pypi.query_versions_pypi(self.package_name)

        if not versions:
            log.error("No package %s on PyPi." % self.package_name)
            return

        if self.version and (self.version not in versions):
            log.error("No package %s for version %s on PyPi." % (self.package_name, self.version))
            return
        else:
            self.version = get_highest_version(versions)

        # TODO: self.options.uri only for first ebuild
        # TODO: make find_uri method configurable
        download_url = self.find_uri()

        log.info('Generating ebuild: %s %s', self.package_name, self.version)
        log.debug('URI from PyPi: %s', download_url)

        self.options.configs['argparse']['uri'] = download_url
        self.options.configs['argparse']['up_pn'] = self.package_name
        self.options.configs['argparse']['up_pv'] = self.version

        ebuild = Ebuild(self.options)
        ebuild.set_metadata(self.query_metadata())

        if self.options.command == 'echo':
            ebuild.print_formatted()
        else:
            ebuild.create()
        return ebuild.requires

    def query_metadata(self):
        """
        Get package metadata from PyPI

        :returns: metadata text

        """

        if self.version:
            return self.pypi.release_data(self.package_name, self.version)
        else:
            (pn, vers) = self.pypi.query_versions_pypi(self.package_name)
            return self.pypi.release_data(self.package_name, get_highest_version(vers))


class CLI(object):
    """
    Dispatcher based on parsed arguments. Holds
    all commands methods.

    :param config: Options to be used when making ebuilds
    :type config: :class:`gpypi.config.ConfigManager`
    :param command: Command name to execute
    :type command: string

    """

    def __init__(self, config):
        self.config = config
        try:
            getattr(self, config.command)()
        except GPyPiException, e:
            log.error("%s: %s", e.__class__.__name__, e)

    def create(self):
        """"""
        gpypi = GPyPI(self.config.up_pn, self.config.up_pv, self.config)
        gpypi.create_ebuilds()
        # TODO: atomic cleanup

    def install(self):
        """"""
        self.create()
        package = Enamer.parse_pn(self.config.up_pn)[0]
        os.execvp('emerge', ['emerge', '-av', package or self.config.up_pn])
        # TODO: support for emerge arguments
        # TODO: install exact version

    def echo(self):
        """"""
        gpypi = GPyPI(self.config.up_pn, self.config.up_pv, self.config)
        gpypi.do_ebuild()
        # TODO: cleanup

    def sync(self):
        """"""
        pypi = CheeseShop()
        for package in pypi.list_packages():
            (pn, vers) = pypi.query_versions_pypi(package)
            for version in vers:
                # TODO: parse_* will not return anything for correct atoms
                atom = Enamer.construct_atom(Enamer.parse_pn(pn)[0], self.config.category, Enamer.parse_pv(version[0]))

                # we skip existing ebuilds
                if PortageUtils.ebuild_exists(atom):
                    continue
                try:
                    url = pypi.get_download_urls(pn, version)[0]
                    # TODO: use setuptools way also
                except IndexError:
                    log.warn('Skipping %s, no download url', atom)
                else:
                    try:
                        self.config.configs['argparse']['uri'] = url
                        self.config.configs['argparse']['up_pn'] = pn
                        self.config.configs['argparse']['up_pv'] = version
                        gpypi = GPyPI(pn, version, self.config)
                        gpypi.create_ebuilds()
                    except KeyboardInterrupt:
                        raise
                    except:
                        log.exception('Unexpected error occured during ebuild creation:')


def main(args=sys.argv[1:]):
    """Parse command-line options and do it.
    Core function for gpypi command.

    Dispatches commands to :class:`gpypi.cli.CLI`
    """
    main_parser = argparse.ArgumentParser(prog='gpypi',
        description="Builds ebuilds from PyPi.")
    main_parser.add_argument('-v', '--version', action='version',
        version='%(prog)s ' + __version__)

    # global options
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-P", "--PN", action='store', dest="pn",
        help=Config.allowed_options['pn'][0])
    parser.add_argument("-V", "--PV", action='store', dest="pv",
        help=Config.allowed_options['pv'][0])
    parser.add_argument("--MY-PV", action='store', dest="my_pv",
        help=Config.allowed_options['my_pv'][0])
    parser.add_argument("--MY-PN", action='store', dest="my_pn",
        help=Config.allowed_options['my_pn'][0])
    parser.add_argument("--MY-P", action='store', dest="my_p",
        help=Config.allowed_options['my_p'][0])
    parser.add_argument("--homepage", action='store', dest="homepage",
        help=Config.allowed_options['homepage'][0])
    parser.add_argument("--keywords", action='store', dest="keywords",
        help=Config.allowed_options['keywords'][0])
    parser.add_argument("--license", action='store', dest="license",
        help=Config.allowed_options['license'][0])
    parser.add_argument("--description", action='store', dest="description",
        help=Config.allowed_options['description'][0])
    # TODO: set long_description in pypi/setup_py
    parser.add_argument("--long-description", action='store', dest="long_description",
        help=Config.allowed_options['long_description'][0])
    parser.add_argument("-u", "--uri", action='store', dest="uri",
        help=Config.allowed_options['uri'][0])
    parser.add_argument("-i", "--index-url", action='store', dest="index_url",
        help=Config.allowed_options['index_url'][0])
    # TODO: release yolk with support to query third party PyPi
    # TODO: test --index-url is always taken in account
    parser.add_argument('--nocolors', action='store_true', dest='nocolors',
        help=Config.allowed_options['nocolors'][0])
    parser.add_argument("--config-file", action='store', dest="config_file",
        default="/etc/gpypi", help="Absolute path to a config file")

    logging_group = parser.add_mutually_exclusive_group()
    logging_group.add_argument("-q", "--quiet", action='store_true',
        dest="quiet", default=False, help="Show less output.")
    logging_group.add_argument("-d", "--debug", action='store_true',
        dest="debug", default=False, help="Show debug information.")

    # ebuild handling options
    ebuild_parser = argparse.ArgumentParser(add_help=False)
    ebuild_parser.add_argument('up_pn', action='store', metavar="package name")
    ebuild_parser.add_argument('up_pv', nargs='?', default=None, metavar="package version")

    # create & install options
    create_install_parser = argparse.ArgumentParser(add_help=False)
    create_install_parser.add_argument("-l", "--overlay", action='store', dest='overlay',
        metavar='OVERLAY_NAME', help=Config.allowed_options['overlay'][0])
    create_install_parser.add_argument("-o", "--overwrite", action='store_true',
        dest="overwrite", help=Config.allowed_options['overwrite'][0])
    create_install_parser.add_argument("--no-deps", action='store_true', dest="no_deps",
        help=Config.allowed_options['no_deps'][0])
    create_install_parser.add_argument("-c", "--category", action='store',
        dest="category", help=Config.allowed_options['category'][0])
    # TODO: pretend
    #create_install_parser.add_argument("-p", "--pretend", action='store_true',
        #dest="pretend", default=False, help="Print ebuild to stdout, "
        #"don't write ebuild file, don't download SRC_URI.")

    # workflow
    workflow_parser = create_install_parser.add_argument_group('Workflow control',
        'Generate metadata, manifest, changelog ...')
    workflow_parser.add_argument("--metadata-disable", action="store_true",
        dest="metadata_disable", help=Config.allowed_options['metadata_disable'][0])
    workflow_parser.add_argument("--metadata-disable-echangelog-user", action="store_true",
        dest="metadata_use_echangelog_user",
        help=Config.allowed_options['metadata_use_echangelog_user'][0])
    workflow_parser.add_argument("--metadata-herd", action="store",
        dest="metadata_herd", help=Config.allowed_options['metadata_herd'][0])
    workflow_parser.add_argument("--metadata-maintainer-description", action="store",
        dest="metadata_maintainer_description", help=Config.allowed_options['metadata_maintainer_description'][0])
    workflow_parser.add_argument("--metadata-maintainer-email", action="store",
        dest="metadata_maintainer_email", help=Config.allowed_options['metadata_maintainer_email'][0])
    workflow_parser.add_argument("--metadata-maintainer-name", action="store",
        dest="metadata_maintainer_name", help=Config.allowed_options['metadata_maintainer_name'][0])
    # echangelog
    workflow_parser.add_argument("--echangelog-disable", action="store_true",
        dest="echangelog_disable", help=Config.allowed_options['echangelog_disable'][0])
    workflow_parser.add_argument("--echangelog-message", action="store",
        dest="echangelog_message", help=Config.allowed_options['echangelog_message'][0])
    # repoman
    workflow_parser.add_argument("--repoman-commands", action="store",
        dest="repoman_commands", help=Config.allowed_options['repoman_commands'][0])

    ## subcommands
    subparsers = main_parser.add_subparsers(title="commands", dest="command")

    parser_create = subparsers.add_parser('create', help="Write ebuild and it's dependencies to an overlay",
        description="Write ebuild and it's dependencies to an overlay",
        parents=[parser, ebuild_parser, create_install_parser])

    parser_echo = subparsers.add_parser('echo', help="Echo ebuild to stdout",
        description="Echo ebuild to stdout",
        parents=[parser, ebuild_parser])
    parser_echo.add_argument("--format", action='store', dest="format",
        help=Config.allowed_options['format'][0])
    parser_echo.add_argument("--background", action='store', dest="background",
        help=Config.allowed_options['background'][0])

    parser_install = subparsers.add_parser('install', help="Install ebuild and it's dependencies",
        description="Install ebuild and it's dependencies",
        parents=[parser, ebuild_parser, create_install_parser])

    parser_pypi = subparsers.add_parser('sync', help="Populate all packages from pypi into an overlay",
        description="Populate all packages from pypi into an overlay",
        parents=[parser, create_install_parser])

    args = main_parser.parse_args(args)

    # TODO: configurable logging
    if args.nocolors:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(message)s"))
    else:
        ch = PortageStreamHandler()
        ch.setFormatter(PortageFormatter("%(message)s"))
    logger = logging.getLogger()
    logger.addHandler(ch)

    if args.debug:
        logger.setLevel(logging.DEBUG)
    elif args.quiet:
        logger.setLevel(logging.WARN)
    else:
        logger.setLevel(logging.INFO)

    # portage group access must be used for write permission in overlay and for
    # unpacking of ebuilds
    if secpass < 1:
        log.warn('Should be run as root or in group ' + str(portage_gid) +
                ". Expect more problems to come.\n")

    config_mgr = ConfigManager.load_from_ini(args.config_file)
    config_mgr.configs['argparse'] = Config.from_argparse(args)

    # handle command
    try:
        CLI(config_mgr)
    except:
        # enter pdb debugger when debugging is enabled
        if args.debug:
            pdb.post_mortem()
        else:
            raise

if __name__ == "__main__":
    main()
