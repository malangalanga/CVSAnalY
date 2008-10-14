# Copyright (C) 2006 LibreSoft
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors :
#       Alvaro Navarro <anavarro@gsyc.escet.urjc.es>
#       Carlos Garcia Campos <carlosgc@gsyc.escet.urjc.es>

"""
Main funcion of cvsanaly. Fun starts here!

@author:       Alvaro Navarro, Carlos Garcia Campos
@organization: LibreSoft
@copyright:    LibreSoft
@license:      GNU GPL version 2 or any later version
@contact:      libresoft-tools-devel@lists.morfeo-project.org
"""

import os
import getopt

from repositoryhandler.backends import create_repository, create_repository_from_path, RepositoryUnknownError
from ParserFactory import create_parser_from_logfile, create_parser_from_repository
from Database import (create_database, TableAlreadyExists, AccessDenied, DatabaseNotFound,
                      DatabaseDriverNotSupported, DBRepository, statement, initialize_ids,
		      DatabaseException)
from DBContentHandler import DBContentHandler
from Log import LogReader, LogWriter
from ExtensionsManager import ExtensionsManager, InvalidExtension, InvalidDependency
from Config import Config, ErrorLoadingConfig
from utils import printerr, printout, uri_to_filename
from FindProgram import find_program

# Some stuff about the project
version = "2.0"
author = "(C) 2004,2008 %s <%s>" % ("LibreSoft", "libresoft-tools-devel@lists.morfeo-project.org")
name = "cvsanaly2 %s - LibreSoft Group http://www.libresoft.es" % (version)
credits = "%s \n%s\n" % (name, author)

def usage ():
    print credits
    print "Usage: cvsanaly2 [options] [URI]"
    print """
Analyze the given URI. An URI can be a checked out directory, 
or a remote URL pointing to a repository. If URI is omitted,
the current working directory will be used as a checked out directory.

Options:

  -h, --help                     Print this usage message.
  -V, --version                  Show version
  -g, --debug                    Enable debug mode
  -q, --quiet                    Run silently, only print error messages
      --profile                  Enable profiling mode
  -f, --config-file              Use a custom configuration file
      --with-lines=yes/no/auto   Get lines added/removed per commit (auto). Disabled by default 
                                 only for SVN repositories because of performance reasons.

  -l, --repo-logfile=path        Logfile to use instead of getting log from the repository
  -s, --save-logfile[=path]      Save the repository log to the given path
      --extensions=ext1,ext2,    List of extensions to run        

Database:

      --db-driver                Output database driver [sqlite|mysql|postgres] (sqlite)
  -u, --db-user                  Database user name (operator)
  -p, --db-password              Database user password
  -d, --db-database              Database name (cvsanaly)
  -H, --db-hostname              Name of the host where database server is running (localhost)

Metrics Options:

      --metrics-all              Get metrics for every revision, not only for HEAD
"""

def main (argv):
    # Short (one letter) options. Those requiring argument followed by :
    short_opts = "hVgqf:l:s:u:p:d:H:"
    # Long options (all started by --). Those requiring argument followed by =
    long_opts = ["help", "version", "debug", "quiet", "profile", "config-file=", 
                 "repo-logfile=", "save-logfile=", "with-lines=", "db-user=", "db-password=",
                 "db-hostname=", "db-database=", "db-driver=", "extensions=", "metrics-all"]

    # Default options
    debug = None
    quiet = None
    profile = None
    configfile = None
    user = None
    passwd = None
    hostname = None
    database = None
    driver = None
    logfile = None
    save_logfile = None
    lines = None
    extensions = None
    metrics_all = None

    try:
        opts, args = getopt.getopt (argv, short_opts, long_opts)
    except getopt.GetoptError, e:
        printerr (str (e))
        return 1

    for opt, value in opts:
        if opt in ("-h", "--help", "-help"):
            usage ()
            return 0
        elif opt in ("-V", "--version"):
            print version
            return 0
        elif opt in ("--debug", "-g"):
            debug = True
        elif opt in ("--quiet", "-q"):
            quiet = True
        elif opt in ("--profile", ):
            profile = True
        elif opt in ("-f", "--config-file"):
            configfile = value
        elif opt in ("--with-lines", ):
            if value == 'yes' or value == 'Yes':
                lines = True
            elif value == 'no' or value == 'No':
                lines = False
        elif opt in ("-u", "--db-user"):
            user = value
        elif opt in ("-p", "--db-password"):
            passwd = value
        elif opt in ("-H", "--db-hostname"):
            hostname = value
        elif opt in ("-d", "--db-database"):
            database = value
        elif opt in ("--db-driver"):
            driver = value
        elif opt in ("-l", "--repo-logfile"):
            logfile = value
        elif opt in ("-s", "--save-logfile"):
            save_logfile = value
        elif opt in ("--extensions", ):
            extensions = value.split (',')
        elif opt in ("--metrics-all", ):
            metrics_all = True

    if len (args) <= 0:
        uri = os.getcwd ()
    else:
        uri = args[0]

    config = Config ()
    try:
        if configfile is not None:
            config.load_from_file (configfile)
        else:
            config.load ()
    except ErrorLoadingConfig, e:
        printerr (e.message)
        return 1

    if debug is not None:
        config.debug = debug
    if quiet is not None:
        config.quiet = quiet
    if profile is not None:
        config.profile = profile
    if logfile is not None:
        config.repo_logfile = logfile
    if save_logfile is not None:
        config.save_logfile = save_logfile
    if driver is not None:
        config.db_driver = driver
    if user is not  None:
        config.db_user = user
    if passwd is not None:
        config.db_password = passwd
    if hostname is not None:
        config.db_hostname = hostname
    if database is not None:
        config.db_database = database
    if extensions is not None:
        config.extensions.extend ([item for item in extensions if item not in config.extensions])
    if metrics_all is not None:
        config.metrics_all = metrics_all

    if config.debug:
        import repositoryhandler.backends
        repositoryhandler.backends.DEBUG = True

    reader = LogReader ()

    # Create repository
    path = uri_to_filename (uri)
    if path is not None:
        try:
            repo = create_repository_from_path (path)
        except RepositoryUnknownError:
            printerr ("Path %s doesn't seem to point to a repository supported by cvsanaly", (path,))
            return 1
        except Exception, e:
            printerr ("Unknown error creating repository for path %s (%s)", (path, str (e)))
            return 1
    else:
        repo = create_repository ('svn', uri)

    reader.set_repo (repo, path or uri)

    if lines is not None:
        config.lines = lines
    else:
        if repo.get_type () == 'svn':
            config.lines = False

    if config.lines and repo.get_type () == 'svn':
        if find_program ("diffstat") is None:
            config.lines = False
            printout ("Warning: lines added/removed will be disabled since "
                      "diffstat command was not found in path")

    # Create parser
    if config.repo_logfile is not None:
        parser = create_parser_from_logfile (config.repo_logfile)
        reader.set_logfile (config.repo_logfile)
    else:
        parser = create_parser_from_repository (repo)

    parser.set_repository (repo)

    if parser is None:
        printerr ("Failed to create parser")
        return 1

    # TODO: check parser type == logfile type

    try:
        emg = ExtensionsManager (config.extensions)
    except InvalidExtension, e:
        printerr ("Invalid extension %s", (e.name))
        return 1
    except InvalidDependency, e:
        printerr ("Extension %s depends on extension %s which is not a valid extension", (e.name1, e.name2))
        return 1
    except Exception, e:
        printerr ("Unknown extensions error: %s", (str (e)))
        return 1
    
    db_exists = False

    try:
        db = create_database (config.db_driver,
                              config.db_database,
                              config.db_user,
                              config.db_password,
                              config.db_hostname)
    except AccessDenied, e:
        printerr ("Error creating database: %s", (e.message))
        return 1
    except DatabaseNotFound:
        printerr ("Database %s doesn't exist. It must be created before running cvsanaly", (config.db_database))
        return 1
    except DatabaseDriverNotSupported:
        printerr ("Database driver %s is not supported by cvsanaly", (config.db_driver))
        return 1
    
    cnn = db.connect ()
    cursor = cnn.cursor ()
    try:
        db.create_tables (cursor)
        cnn.commit ()
    except TableAlreadyExists:
        db_exists = True
    except DatabaseException, e:
        printerr ("Database error: %s", (e.message))
        return 1

    # Add repository to Database
    if db_exists:
        cursor.execute (statement ("SELECT id from repositories where uri = ?", db.place_holder), (repo.get_uri (),))
        rep = cursor.fetchone ()
        initialize_ids (db, cursor)
        cursor.close ()
        
    if not db_exists or rep is None:
        # We consider the name of the repo as the last item of the root path
        name = repo.get_uri ().rstrip ("/").split ("/")[-1].strip ()
        cursor = cnn.cursor ()
        rep = DBRepository (None, repo.get_uri (), name, repo.get_type ())
        cursor.execute (statement (DBRepository.__insert__, db.place_holder), (rep.id, rep.uri, rep.name, rep.type))
        cursor.close ()
        cnn.commit ()

    cnn.close ()

    # Start the parsing process
    def new_line (line, user_data):
        parser, writer = user_data
        
        parser.feed (line)
        writer and writer.add_line (line)

    writer = None
    if config.save_logfile is not None:
        writer = LogWriter (config.save_logfile)
        
    printout ("Parsing log for %s (%s)", (uri, repo.get_type ()))
    parser.set_content_handler (DBContentHandler (db))
    reader.start (new_line, (parser, writer))
    parser.end ()
    writer and writer.close ()

    # Run extensions
    printout ("Executing extensions")
    emg.run_extensions (repo, db)

