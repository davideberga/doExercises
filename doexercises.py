import argparse
import json
import os
import re
import sys
import time
import urllib
from multiprocessing.pool import ThreadPool
from shutil import copy2
from threading import Thread
from typing import Dict, List

import requests

root_url = 'http://datascience.maths.unitn.it'
solutions_address = '/ocpu/library/doexercises/R/getSolutions'
renderRmd_address = '/ocpu/library/doexercises/R/renderRmd'

headers = {
    "Content-Type": "application/json",
    "dataType": "text"
}

parser = argparse.ArgumentParser(
    description="Scarica soluzioni dalla piattaforma DoExercises")
parser.add_argument("-u", "--username",
                    help="username (nome.cognome)", default="", type=str, nargs=1)
parser.add_argument("-m", "--matricola",
                    help="numero di matricola", default="", type=str, nargs=1)
parser.add_argument("-f", "--force",
                    help="salta il controllo dei file già scaricati e li ri-scarica tutti", action="store_true")
parser.add_argument("-o", "--output", help="definisce cartella di output dei file HTML",
                    default="./html/", type=str, nargs=1)
parser.add_argument("-v", "--verbose",
                    help="aumenta verbosità dei log (stampa risposte del server etc)", action="store_true")
parser.add_argument("-j", "--jobs",
                    help="controlla il numero di thread usati per scaricare i file", default=4, nargs=1)
cli_args = parser.parse_args()

pool = ThreadPool(cli_args.jobs)


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
        resp = requests.post(root_url + solutions_address,
                             headers=headers, json=body)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    Log.info("Logged in")
    Log.debug(resp.content.decode("UTF-8"))
    return resp.content.decode("UTF-8").splitlines()[1]


def fetch_file_names(path: str) -> List[str]:
    """Fetches all the .Rmd filenames from DoExercises' storage
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
        resp = requests.get(root_url + path, headers=headers)
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
            resp = requests.post(root_url + renderRmd_address,
                                 headers=headers, json=body)
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)
        res_path = re.findall(r".*html$", resp.content.decode("UTF-8"), re.MULTILINE)[0]
        Log.debug("Found path: {}", res_path)
        urllib.request.urlretrieve(root_url + res_path, outfolder + outfile)

    Log.debug("Using {} threads", cli_args.jobs)
    pool.map(_fetch_file, filenames)
    pool.close()


def check_existing_files(filenames: List[str], outfolder: str) -> List[str]:
    """
    Checks whether any files from a list of .Rmd files was already downloaded
    in the ouput folder
    Parameters
    ----------
    filenames : List[str]
        A list of the filenames to look for on the output folder

    outfolder : str
        The folder in which downloaded files are placed
    """
    Log.info("Checking existing files")
    ret = []
    for fn in filenames:
        fn_noext = fn.replace(".Rmd", ".html")
        if os.path.isfile(outfolder + fn_noext): continue
        ret.append(fn)

    Log.debug("Skipping {} files", len(filenames) - len(ret))
    return ret

if __name__ == "__main__":
    # Check username and matricola
    if cli_args.username == "" or cli_args.matricola == "":
        Log.error(
            "This script needs valid DoExercises credentials. Use 'python {} --help' to get usage information",
            __file__.split("/")[-1]
        )
        sys.exit(1)

    path = login()

    outfolder = cli_args.output
    # Sanitize the output path: append a '/' if not present already
    if outfolder[-1] != "/":
        outfolder += "/"
    # Create the folder if it doesn't exist yet
    if not os.path.exists(outfolder):
        Log.info("Creating output folder")
        os.makedirs(outfolder)

    filenames = check_existing_files(fetch_file_names(path), outfolder)

    try:
        fetch_rendered_files(filenames, outfolder)
    except KeyboardInterrupt:
        Log.error("Terminating prematurely")
        Log.info("Finishing pending downloads")
        # Wait for all downloads to finish
        pool.terminate()
        pool.join()
        sys.exit(1)

    pool.join()
    Log.success("Finished downloading")
