# doExercises
Script python per il download degli esercizi della piattaforma DoExercises (corso di probabilità e statistica).

### Utilizzo
Usare `python doexercises.py --help` ottenere informazioni sui comandi possibili.

### PDF
Per convertire le soluzioni in PDF occorre [`wkhtmltopdf`](https://github.com/wkhtmltopdf/wkhtmltopdf/releases). Se non lo si vuole installare, basta scaricarlo in una qualunque cartella e indicare il percorso all'eseguibile con il comando `--wk <percorso>` allo script.

Su Linux/X11 è possibile installare [`xfvb-run`](https://manpages.ubuntu.com/manpages/trusty/man1/xvfb-run.1.html) (fa parte del pacchetto `xfvb`, disponibile tramite i vari package manager). Lo script controlla se è installato e, se lo trova, converte i file in PDF usando vari processi in parallelo (controllati da `--jobs`), velocizzando **molto** la conversione.