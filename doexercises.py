import argparse
import json
import os
import re
import requests
from shutil import copy2
from threading import Thread
from typing import Dict, List
import urllib
import time

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
parser.add_argument("-o", "--output", help="definisce cartella di output dei file HTML",
                    default="./html/", type=str, nargs=1)
args = parser.parse_args()


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
        """Print and format an success message (green)
        Parameters
        ----------
        text : str
            The text to be printed (should include format curly braces '{}')
        
        args : str, optional
            The arguments to be passed to the str.format() function
        """
        print(Log._colorize("[v] " + text.format(args), "green"))


class Downloader(Thread):

    """A very basic multithreaded downloader for HTML files
    Attributes
    ----------
    file_url : str
        The actual URL to be fetched
    
    save_path : str
        The output file path
    """
    
    def __init__(self, file_url, save_path):
        """
        Parameters
        ----------
        file_url : str
            The actual URL to be fetched
        
        save_path : str
            The output file path
        """
        super().__init__()
        self.file_url = file_url
        self.save_path = save_path

    def run(self):
        """
        Override for the Thread.run() function, defines the actual logic to 
        be executed
        """
        urllib.request.urlretrieve(self.file_url, self.save_path)


def login() -> str:
    """Creates a new session on DoExercises
    Returns
    -------
    str
        The URL where all filenames can be found (both .md and rendered .html)
    """
    body = {
        "user": args.username,
        "id": args.matricola
    }

    try:
        resp = requests.post(root_url + solutions_address,
                             headers=headers, json=body)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    Log.info("Logged in")
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
    Log.info("Found {} exercises", len(filenames))
    for fn in filenames:
        outfile = fn.replace(".Rmd", ".html")
        body = {
            "file": fn,
            "output_file_name": outfile
        }
        Log.info("Downloading {}", outfile)
        try:
            resp = requests.post(root_url + renderRmd_address,
                                 headers=headers, json=body)
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)
        res_path = re.findall(r".*html", resp.content.decode("UTF-8"))[0]
        Downloader(root_url + res_path, outfolder + outfile).start()


if __name__ == "__main__":
    # Check username and matricola
    if args.username == "" or args.matricola == "":
        Log.error(
            "This script needs valid DoExercises credentials. Use 'python {} --help' to get usage information",
            __file__.split("/")[-1]
        )
        exit(1)
    
    path = login()
    filenames = fetch_file_names(path)
    
    outfolder = args.output
    # Sanitize the output path: append a '/' if not present already
    if outfolder[-1] != "/":
        outfolder += "/"
    # Create the folder if it doesn't exist yet
    if not os.path.exists(outfolder):
        Log.info("Creating output folder")
        os.makedirs(outfolder)

    try:
        fetch_rendered_files(filenames, outfolder)
    except KeyboardInterrupt:
        Log.error("Ending prematurely")
        # Wait for all downloads to finish
        time.sleep(1)
        os.exit(1)
    Log.success("Finished downloading")
