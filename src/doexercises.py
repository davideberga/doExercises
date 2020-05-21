import argparse
import json
import os
import re
import requests
from shutil import copy2
from threading import Thread
from typing import Dict, List
import urllib

root_url = 'http://datascience.maths.unitn.it'
login_address = '/ocpu/library/doexercises/R/logIn'
solutions_address = '/ocpu/library/doexercises/R/getSolutions'
renderRmd_address = '/ocpu/library/doexercises/R/renderRmd'

headers = {
    "Content-Type": "application/json",
    "dataType": "text"
}

parser = argparse.ArgumentParser(description="Scarica soluzioni dalla piattaforma DoExercises")
parser.add_argument("-u", "--username", help="username (nome.cognome)", type=str, nargs=1)
parser.add_argument("-m", "--matricola", help="numero di matricola", type=str, nargs=1)
parser.add_argument("-o", "--output", help="definisce cartella di output dei file HTML", default="./html/", type=str, nargs=1)
args = parser.parse_args()

class Log():
    _colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "endc": "\033[0m"
    }

    @staticmethod
    def _colorize(text: str, color: str) -> str:
        return Log._colors[color] + text + Log._colors["endc"]

    @staticmethod
    def info(text: str, args: str = ""):
        print("[+] " + text.format(args))

    @staticmethod
    def error(text: str, args: str = ""):
        print("[x] " + Log._colorize(text.format(args), "red"))

    @staticmethod
    def success(text: str, args: str = ""):
        print("[v] " + Log._colorize(text.format(args), "green"))

class Downloader(Thread):
    def __init__(self, file_url, save_path):
        super().__init__()
        self.file_url = file_url
        self.save_path = save_path

    def run(self):
        urllib.request.urlretrieve(self.file_url, self.save_path)

def login() -> str:
    body = {
        "user": args.username,
        "id": args.matricola
    }

    try:
        resp = requests.post(root_url + solutions_address, headers=headers, json=body)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    Log.info("Logged in")
    return resp.content.decode("UTF-8").splitlines()[1]


def fetch_file_names(path: str) -> List[str]:
    try:
        resp = requests.get(root_url + path, headers=headers)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    filenames = resp.content.decode("UTF-8").split("$files")[1]
    Log.info("Got filenames")
    return re.findall(r"\"(.*\.Rmd)", filenames)


def fetch_rendered_files(filenames: List[str], outfolder: str) -> None:
    Log.info("Need to download {} exercises", len(filenames))
    for fn in filenames:
        outfile = fn.replace(".Rmd", ".html")
        body = {
            "file": fn,
            "output_file_name": outfile
        }
        Log.info("Downloading {}", outfile)
        try:
            resp = requests.post(root_url + renderRmd_address, headers=headers, json=body)
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)
        res_path = resp.content.decode("UTF-8").splitlines()[8]
        Downloader(root_url + res_path, outfolder + outfile).start()
        

path = login()
filenames = fetch_file_names(path)
outfolder = args.output
if outfolder[-1] != "/": outfolder += "/"
if not os.path.exists(outfolder):
    os.makedirs(outfolder)
fetch_rendered_files(filenames, outfolder)
Log.success("Finished downloading")
