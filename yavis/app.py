"""Hauptschleife: Aktivierungswort -> Befehl -> Antwort (nur Sprache)."""
import logging, re, sys, threading
from . import config
from .memory import Memory
from .tools import Tools
from .brain import Brain
from .speech import Ears, Mouth, split_wake, norm
from .setup_ollama import ensure_ollama

YES = ("ja", "jawohl", "bestätig", "mach das", "okay", "ok", "klar", "gerne")
NO = ("nein", "abbrechen", "stopp", "nicht")
GOOD = ("das war gut", "das war richtig", "gut gemacht", "das war super")
BAD = ("das war falsch", "das war schlecht", "das war nicht richtig", "das stimmt nicht")


def is_yes(t): n = norm(t); return any(w in n for w in YES) and not any(w in n.split() for w in NO)


def main():
    cfg = config.load()
    logging.basicConfig(filename=str(config.DATA_DIR / "yavis.log"), level=logging.INFO,
                        format="%(asctime)s %(message)s")
    mem = Memory(config.DATA_DIR / "memory.db")
    ears, mouth = Ears(cfg), Mouth(cfg)

    def confirm(question):
        mouth.say(question + " Bitte sage Ja oder Nein.")
        t = ears.transcribe(ears.record(max_wait=10))
        return is_yes(t)

    brain = Brain(cfg, mem, Tools(cfg, mem, confirm))
    stop = threading.Event()
    _tray(stop)

    try:
        ensure_ollama(cfg, logging.info)
        ears.load()
    except Exception as e:
        logging.error(e)
        mouth.say("Master, die Einrichtung ist unvollständig. Bitte starte die YAVIS-Ersteinrichtung.")
        return
    mouth.say("Master, YAVIS ist bereit.")

    while not stop.is_set():
        try:
            text = ears.transcribe(ears.record())
            woke, cmd = split_wake(text, cfg["wake_words"])
            if not woke:
                continue
            if len(cmd) < 3:
                mouth.say("Ja, Master?")
                cmd = ears.transcribe(ears.record(max_wait=8))
                if not cmd:
                    continue
            logging.info("Befehl: %s", cmd)
            n = norm(cmd)
            if any(w in n for w in ("beenden", "schlaf ein", "tschüss")) and len(n.split()) < 4:
                mouth.say("Bis später, Master.")
                break
            if any(n.startswith(p) for p in GOOD):
                mem.add_feedback(*brain.last, 1, cmd)
                mouth.say("Danke, Master. Ich merke mir das.")
                continue
            if any(n.startswith(p) for p in BAD):
                mem.add_feedback(*brain.last, -1, cmd)
                mouth.say("Verstanden, Master. Ich werde es besser machen.")
                continue
            mouth.say(brain.respond(cmd))
        except Exception as e:
            logging.exception("Fehler")
            try:
                mouth.say("Entschuldigung Master, da ist ein Fehler aufgetreten.")
            except Exception:
                pass


def _tray(stop):
    try:
        import pystray
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (64, 64), "#1a1a2e")
        ImageDraw.Draw(img).text((18, 22), "Y", fill="white")
        icon = pystray.Icon("YAVIS", img, "YAVIS läuft",
                            pystray.Menu(pystray.MenuItem("Beenden", lambda i, _: (stop.set(), i.stop(), __import__("os")._exit(0)))))
        threading.Thread(target=icon.run, daemon=True).start()
    except Exception:
        pass
