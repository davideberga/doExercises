import argparse
import glob
import json
import os
import re
import sys
import time
import urllib
from multiprocessing.pool import ThreadPool
from shutil import copy2
from threading import Thread
from typing import List

import requests
import subprocess

URLS = {
    "root": "http://datascience.maths.unitn.it",
    "solutions": "/ocpu/library/doexercises/R/getSolutions",
    "rendered": "/ocpu/library/doexercises/R/renderRmd"
}

headers = {
    "Content-Type": "application/json",
    "dataType": "text"
}

parser = argparse.ArgumentParser(
    description="Scarica soluzioni dalla piattaforma DoExercises")
parser.add_argument("-u", "--username",
                    help="username (nome.cognome)", default="", type=str)
parser.add_argument("-m", "--matricola",
                    help="numero di matricola", default="", type=str)
parser.add_argument("-f", "--force",
                    help="salta il controllo dei file già scaricati e li riscarica tutti", action="store_true")
parser.add_argument("-o", "--htmlout", help="definisce cartella di output dei file HTML",
                    default="./html/", type=str)
parser.add_argument("-p", "--pdfout", help="definisce cartella di output dei file PDF",
                    default="./pdf/", type=str)
parser.add_argument("--wk", help="definisce il percorso dell'eseguibile di wkhtmltopdf",
                    default="wkhtmltopdf", type=str)
parser.add_argument("--nopdf", help="disabilita la conversione in pdf", default=False, action="store_true")
parser.add_argument("-v", "--verbose",
                    help="aumenta verbosità dei log (stampa risposte del server etc)", action="store_true")
parser.add_argument("-j", "--jobs",
                    help="controlla il numero di thread usati per scaricare i file e convertire in PDF", default=4)
cli_args = parser.parse_args()


class Log():
    """Static class which provides simple colored logging"""
    _colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "endc": "\033[0m"
    }

    @staticmethod
    def _colorize(text: str, color: str) -> str:
        return Log._colors[color] + text + Log._colors["endc"]

    @staticmethod
    def info(text: str, args: str = "") -> None:
        """Print and format an info message

        Parameters
        ----------
        text : str
            The text to be printed (should include format curly braces '{}')

        args : str, optional
            The arguments to be passed to the str.format() function
        """
        print("[+] " + text.format(args))

    @staticmethod
    def error(text: str, args: str = "") -> None:
        """Print and format an error message (red)

        Parameters
        ----------
        text : str
            The text to be printed (should include format curly braces '{}')

        args : str, optional
            The arguments to be passed to the str.format() function
        """
        print(Log._colorize("[x] " + text.format(args), "red"))

    @staticmethod
    def success(text: str, args: str = "") -> None:
        """Print and format a success message (green)

        Parameters
        ----------
        text : str
            The text to be printed (should include format curly braces '{}')

        args : str, optional
            The arguments to be passed to the str.format() function
        """
        print(Log._colorize("[v] " + text.format(args), "green"))

    @staticmethod
    def debug(text: str, args: str = "") -> None:
        """Print and format a debug message (indented)

        Parameters
        ----------
        text : str
            The text to be printed (should include format curly braces '{}')

        args : str, optional
            The arguments to be passed to the str.format() function
        """
        if cli_args.verbose:
            print("\t " + text.strip().replace("\n", "\n\t").format(args))


def login() -> str:
    """Creates a new session on DoExercises

    Returns
    -------
    str
        The URL where all filenames can be found (both .md and rendered .html)
    """
    body = {
        "user": cli_args.username,
        "id": cli_args.matricola
    }

    try:
        resp = requests.post(URLS["root"] + URLS["solutions"],
                             headers=headers, json=body)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    Log.info("Logged in")
    Log.debug(resp.content.decode("UTF-8"))
    return resp.content.decode("UTF-8").splitlines()[1]


def fetch_file_names(path: str) -> List[str]:
    """
    Fetches all the .Rmd filenames from DoExercises' storage
    
    Parameters
    ----------
    path : str
        The address which will be queried for the list of filenames

    Returns
    -------
    List[str]
        The list of filenames found from the request
    """
    try:
        resp = requests.get(URLS["root"] + path, headers=headers)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    filenames = resp.content.decode("UTF-8").split("$files")[1]
    Log.info("Got filenames")
    Log.debug(resp.content.decode("UTF-8"))
    return re.findall(r"\"(.*\.Rmd)", filenames)


def fetch_rendered_files(filenames: List[str], outfolder: str) -> None:
    """Downloads rendered HTML files from DoExercises' storage
    Parameters
    ----------
    filenames : List[str]
        A list of the filenames to look for on the server

    outfolder : str
        The folder in which to place the downloaded files
    """
    def _fetch_file(filename: str) -> None:
        outfile = filename.replace(".Rmd", ".html")
        body = {
            "file": filename,
            "output_file_name": outfile
        }
        Log.info("Downloading {}", outfile)
        try:
            resp = requests.post(URLS["root"] + URLS["rendered"],
                                 headers=headers, json=body)
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)
        res_path = re.findall(r".*html$", resp.content.decode("UTF-8"), re.MULTILINE)[0]
        Log.debug("Found path: {}", res_path)
        urllib.request.urlretrieve(URLS["root"] + res_path, outfolder + outfile)

    pool = ThreadPool(cli_args.jobs)
    Log.debug("Using {} threads", cli_args.jobs)
    try:
        pool.map(_fetch_file, filenames)
    except KeyboardInterrupt:
        Log.error("Terminating prematurely")
        Log.info("Finishing pending downloads")
        # Wait for all downloads to finish
        pool.terminate()
        pool.join()
        sys.exit(1)
        return
    pool.close()
    pool.join()
    Log.success("Finished downloading")


def check_existing_files(filenames: List[str], outfolder: str, ext: str = "") -> List[str]:
    """Checks whether any files from a list of .Rmd files was already downloaded
    in the ouput folder

    Parameters
    ----------
    filenames : List[str]
        A list of the filenames to look for on the output folder

    outfolder : str
        The folder in which downloaded files are placed

    ext : str, optional
        If set, replaces each file extension with this parameter

    Returns
    -------
    List[str]
        The elements of `filenames` which are not present in `outfolder`
    """
    def _format_filename(filename: str) -> str:
        if ext == "": return filename
        return os.path.splitext(filename)[0] + ext

    Log.info("Checking existing files")
    ret = []
    for fn in filenames:
        # If a file with extension `ext` already exists in `outfolder`, skip it
        if os.path.isfile(outfolder + _format_filename(fn)): continue
        ret.append(fn)

    Log.debug("Skipping {} files", len(filenames) - len(ret))
    return ret


def which(cmd, mode=os.F_OK | os.X_OK, path=None):
    """Given a command, mode, and a PATH string, return the path which
    conforms to the given mode on the PATH, or None if there is no such
    file.
    `mode` defaults to os.F_OK | os.X_OK. `path` defaults to the result
    of os.environ.get("PATH"), or can be overridden with a custom search
    path.
    """
    def _access_check(fn, mode):
        return (os.path.exists(fn) and os.access(fn, mode)
            and not os.path.isdir(fn))

    # If we're given a path with a directory part, look it up directly rather
    # than referring to PATH directories. This includes checking relative to the
    # current directory, e.g. ./script
    if os.path.dirname(cmd):
        if _access_check(cmd, mode):
            return cmd
        return None

    use_bytes = isinstance(cmd, bytes)

    if path is None:
        path = os.environ.get("PATH", None)
        if path is None:
            try:
                path = os.confstr("CS_PATH")
            except (AttributeError, ValueError):
                # os.confstr() or CS_PATH is not available
                path = os.defpath
        # bpo-35755: Don't use os.defpath if the PATH environment variable is
        # set to an empty string

    # PATH='' doesn't match, whereas PATH=':' looks in the current directory
    if not path:
        return None

    path = os.fsdecode(path)
    path = path.split(os.pathsep)

    if sys.platform == "win32":
        # The current directory takes precedence on Windows.
        if os.curdir not in path:
            path.insert(0, os.curdir)

        # PATHEXT is necessary to check on Windows.
        pathext = os.environ.get("PATHEXT", "").split(os.path.sep)
        # See if the given file matches any of the expected path extensions.
        # This will allow us to short circuit when given "python.exe".
        # If it does match, only test that one, otherwise we have to try
        # others.
        if any(cmd.lower().endswith(ext.lower()) for ext in pathext):
            files = [cmd]
        else:
            files = [cmd + ext for ext in pathext]
    else:
        # On other platforms you don't have things like PATHEXT to tell you
        # what file suffixes are executable, so just pass on cmd as-is.
        files = [cmd]

    seen = set()
    for dir in path:
        normdir = os.path.normcase(dir)
        if not normdir in seen:
            seen.add(normdir)
            for thefile in files:
                name = os.path.join(dir, thefile)
                if _access_check(name, mode):
                    return name
    return None


def convert_to_pdf(htmlfolder: str, filenames: List[str], outfolder: str = "./pdf/", cmd: str = "wkhtmltopdf") -> None:
    """Converts a list of files in a folder to PDF using `wkhtmltopdf`. If `xvfb-run` is present,
    the process is automatically parallelized

    Parameters
    ----------
    htmlfolder : str
        The folder containing the web pages to convert
    
    filenames : str
        The list of filenames to convert

    outfolder : str, optional
        The folder where PDF files are to be placed

    cmd : str, optional
        The path of the `wkhtmltopdf` executable
    """
    def _convert_file_parallel(filename: str):
        infile = filename.replace(".Rmd", ".html")
        outfile = filename.replace(".Rmd", ".pdf")
        os.system(
            "xvfb-run --auto-servernum --server-args='-screen 0, 1920x1080x24' {} --use-xserver --javascript-delay 4000 ./{} ./pdf/{}"
                .format(cmd, htmlfolder + infile, outfile)
        )

    def _convert_file(filename: str):
        infile = filename.replace(".Rmd", ".html")
        outfile = filename.replace(".Rmd", ".pdf")
        os.system("{} --javascript-delay 4000 ./{} ./pdf/{}".format(cmd, htmlfolder + infile, outfile))

    pool = ThreadPool(cli_args.jobs)
    Log.info("Converting {} files to PDF", len(filenames))

    # Use xvfb-run if installed only on Linux, to convert files concurrently
    if which("xvfb-run") and sys.platform.startswith("linux"):
        Log.info("Detected xfvb-run. Using {} threads", cli_args.jobs)
        try:
            pool.map(_convert_file_parallel, filenames)
        except KeyboardInterrupt:
            Log.error("Terminating prematurely")
            Log.info("Finishing pending conversions")
            # Wait for all conversions to finish
            pool.terminate()
            pool.join()
            sys.exit(1)
            return
        pool.close()
        pool.join()
    else:
        for fn in filenames:
            _convert_file(fn)

    Log.success("Finished converting files to PDF")


if __name__ == "__main__":
    # Check username and matricola
    if cli_args.username == "" or cli_args.matricola == "":
        Log.error(
            "This script needs valid DoExercises credentials. Use 'python {} --help' to get usage information",
            __file__.split("/")[-1]
        )
        sys.exit(1)

    path = login()

    html_outfolder = cli_args.htmlout
    # Sanitize the output path: append a '/' if not present already
    if html_outfolder[-1] != os.path.sep:
        html_outfolder += os.path.sep
    # Create the folder if it doesn't exist yet
    if not os.path.exists(html_outfolder):
        Log.info("Creating output folder")
        os.makedirs(html_outfolder)

    # Get all the .Rmd filenames from the server
    filenames = fetch_file_names(path)
    fetch_rendered_files(
        check_existing_files(filenames, html_outfolder, ".html"), 
        html_outfolder
    )

    # Check if wkhtmltopdf is installed
    wkhtmltopdf = which(cli_args.wk)
    if not cli_args.nopdf and not wkhtmltopdf:
        Log.error("wkhtmltopdf not installed (or not found as '{}') - skipping PDF conversion", cli_args.wk)
        sys.exit(1)
    elif cli_args.nopdf:
        sys.exit(0)
    
    pdf_outfolder = cli_args.pdfout
    # Sanitize the output path: append a '/' if not present already
    if pdf_outfolder[-1] != os.path.sep:
        pdf_outfolder += os.path.sep
    # Create the folder if it doesn't exist yet
    if not os.path.exists(pdf_outfolder):
        Log.info("Creating PDF output folder")
        os.makedirs(pdf_outfolder)
    # Run the conversion
    convert_to_pdf(
        html_outfolder,
        check_existing_files(filenames, html_outfolder, ".pdf"),
        cli_args.pdfout,
        cli_args.wk
    )
