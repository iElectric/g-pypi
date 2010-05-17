#!/usr/bin/env python
# pylint: disable-msg=C0301,W0613,W0612,C0103,E0611,W0511

"""

Various functions dealing with portage

"""

import sys
import os
import commands
import logging

from portage import config as portage_config
from portage import settings as portage_settings

try:
    # portage >= 2.2
    from portage import dep as portage_dep
except ImportError:
    # portage <= 2.1
    from portage import portage_dep

# TODO: find more clean way
sys.path.insert(0, "/usr/lib/gentoolkit/pym")
import gentoolkit


ENV = portage_config(clone=portage_settings).environ()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())


def get_repo_names():
    """
    Return a dict of overlay names with their paths
    e.g.
    {'reponame': '/path/to/repo', ...}

    :returns: dict with repoman/paths

    """
    porttrees = [ENV['PORTDIR']] + \
        [os.path.realpath(t) for t in ENV["PORTDIR_OVERLAY"].split()]
    treemap = {}
    for path in porttrees:
        repo_name_path = os.path.join(path, 'profiles/repo_name')
        try:
            repo_name = open(repo_name_path, 'r').readline().strip()
            treemap[repo_name] = path
        except (OSError, IOError):
            log.warn("No repo_name in %s" % path)
    return treemap

def get_installed_ver(cpn):
    """
    Return PV for installed version of package

    :param cpn: cat/pkg-ver
    :type cpn: string
    :returns: string version or None if not pkg installed

    """
    try:
        #Return first version installed
        #XXX Log warning if more than one installed (SLOT)?
        pkg = gentoolkit.find_installed_packages(cpn, masked=True)[0]
        return pkg.get_version()
    except:
        return

def valid_cpn(cpn):
    """
    Return True if cpn is valid portage category/pn-pv

    :param cpn: cat/pkg-ver
    :type cpn: string
    :returns: bool

    """
    if portage_dep.isvalidatom(cpn):
        return True
    else:
        return False


def ebuild_exists(cat_pkg):
    """
    Checks if an ebuild exists in portage tree or overlay

    :param cat_pkg: portage category/packagename
    :type cat_pkg: string
    :returns: bool

    """
    pkgs = gentoolkit.find_packages(cat_pkg)
    if len(pkgs):
        return True
    else:
        return False

#def run_tests(ebuild_path):
#    """
#    Use portage to run tests

#    Some day I'll figure out how to get portage to do this directly. Some day.

#    @param ebuild_path: full path to ebuild
#    @type ebuild_path: string
#    @returns: None if succeed, raises OSError if fails to unpack

#    """
#    cmd = "/usr/bin/python /usr/bin/ebuild %s test" % ebuild_path
#    print cmd
#    (status, output) = commands.getstatusoutput(cmd)
#    print output
#    print status

def unpack_ebuild(ebuild_path):
    """
    Use portage to unpack an ebuild.

    :param ebuild_path: full path to ebuild
    :type ebuild_path: string
    :returns: None if succeed, raises OSError if fails to unpack

    # TODO: Some day I'll figure out how to get portage to do this directly. Some day.
    """
    (status, output) = commands.getstatusoutput("ebuild %s digest setup clean unpack" % ebuild_path)
    if status:
        # Portage's error message, sometimes.
        # Couldn't determine PN or PV so we misnamed ebuild
        if 'does not follow correct package syntax' in output:
            log.error(output)
            log.error("Misnamed ebuild: %s" % ebuild_path)
            log.error("Try using -n or -v to force PN or PV")
            os.unlink(ebuild_path)
        else:
            log.error(output)
            raise OSError

def find_s_dir(p, cat):
    """
    Try to get ${S} by determining what directories were unpacked

    :param p: portage ${P}
    :type p: string
    :param cat: valid portage category
    :type cat: string
    :returns: string with directory name if detected, empty string
              if S=WORKDIR, None if couldn't find S

    """
    workdir = get_workdir(p, cat)
    files = os.listdir(workdir)
    dirs = []
    for unpacked in files:
        if os.path.isdir(os.path.join(workdir, unpacked)):
            dirs.append(unpacked)
    if len(dirs) == 1:
        #Only one directory, must be it.
        return dirs[0]
    elif not len(dirs):
        #Unpacked in cwd
        return ""
    else:
        #XXX Need to search whole tree for setup.py
        log.error("Can't determine ${S}")
        log.error("Unpacked multiple directories: %s" % dirs)

def get_workdir(p, cat):
    """
    Return WORKDIR

    :param p: portage ${P}
    :param cat: valid portage category
    :type p: string
    :type cat: string
    :return: string of portage_tmpdir/cp

    """
    return '%s/portage/%s/%s/work' % (get_portage_tmpdir(), cat, p)

def get_portdir_overlay():
    """Return PORTDIR_OVERLAY from /etc/make.conf"""
    return ENV['PORTDIR_OVERLAY'].split(" ")[0]

def get_portage_tmpdir():
    """Return PORTAGE_TMPDIR from /etc/make.conf"""
    return ENV["PORTAGE_TMPDIR"]

def get_portdir():
    """Return PORTDIR from /etc/make.conf"""
    return ENV["PORTDIR"]

def get_keyword():
    """Return first ACCEPT_KEYWORDS from /etc/make.conf"""
    #Choose the first arch they have, in case of multiples.

    try:
        arch = ENV["ACCEPT_KEYWORDS"].split(' ')[0]
    except KeyError:
        log.error("No ACCEPT_KEYWORDS found, using ~x86")
        arch = '~x86'

    #New ebuilds must be ~arch

    if not arch.startswith('~'):
        arch = "~%s" % arch
    return arch

def make_overlay_dir(category, pn, overlay):
    """
    Create directory(s) in overlay for ebuild

    :param category: valid portage category
    :type category: string
    :param pn: portage ${PN}
    :type pn: string
    :param overlay: portage overlay directory
    :type overlay: string
    :return: string of full directory name

    """

    ebuild_dir = os.path.join(overlay, category, pn)
    if not os.path.isdir(ebuild_dir):
        try:
            os.makedirs(ebuild_dir)
        except OSError, err:
            #XXX Use logger
            log.error(err)
            sys.exit(2)
    return ebuild_dir

def find_egg_info_dir(root):
    """
    Locate all files matching supplied filename pattern in and below
    supplied root directory.
    """
    for path, dirs, files in os.walk(os.path.abspath(root)):
        for this_dir in dirs:
            if this_dir.endswith(".egg-info"):
                return os.path.normpath(os.path.join(path, this_dir, ".."))
